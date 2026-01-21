"""
Governor CLI: The gate for file mutations.

Commands:
    governor init              - Initialize governor in repo
    governor propose           - Submit a proposal with claims
    governor verify <id>       - Verify a proposal
    governor apply <id>        - Apply a verified proposal
    governor facts             - Query facts ledger
    governor decisions         - Query decisions ledger
"""

import json
import sys
from pathlib import Path
from uuid import UUID

import click

from .claims import Claim, ClaimType, decision, file_exists, claim_tests_pass, changeset
from .envelopes import EnvelopeMode, get_current_envelope, set_envelope, clear_envelope
from .fsm import ProposalFSM, ProposalState, RejectionInfo, ClaimError, create_proposal
from .ledgers import FactLedger, DecisionLedger
from .verifiers import create_default_verifiers


GOVERNOR_DIR = ".governor"
PROPOSALS_FILE = "proposals.json"


def get_governor_dir(ctx: click.Context) -> Path:
    """Get the governor directory path."""
    return Path(ctx.obj.get("root", ".")) / GOVERNOR_DIR


def ensure_initialized(ctx: click.Context) -> Path:
    """Ensure governor is initialized, return governor dir."""
    gov_dir = get_governor_dir(ctx)
    if not gov_dir.exists():
        click.echo("Error: Governor not initialized. Run 'governor init' first.", err=True)
        ctx.exit(1)
    return gov_dir


def load_proposals(gov_dir: Path) -> dict[str, dict]:
    """Load proposals from disk."""
    proposals_path = gov_dir / PROPOSALS_FILE
    if not proposals_path.exists():
        return {}
    return json.loads(proposals_path.read_text())


def save_proposals(gov_dir: Path, proposals: dict[str, dict]) -> None:
    """Save proposals to disk."""
    proposals_path = gov_dir / PROPOSALS_FILE
    proposals_path.write_text(json.dumps(proposals, indent=2))


@click.group()
@click.option(
    "--root", "-r",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Project root directory",
)
@click.pass_context
def cli(ctx: click.Context, root: str) -> None:
    """Epistemic Governor - Gate for file mutations."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize governor in the current directory."""
    root = Path(ctx.obj["root"])
    gov_dir = root / GOVERNOR_DIR

    if gov_dir.exists():
        click.echo(f"Governor already initialized at {gov_dir}")
        return

    # Create directory structure
    gov_dir.mkdir()
    (gov_dir / "facts").mkdir()
    (gov_dir / "facts" / "receipts").mkdir()
    (gov_dir / "decisions").mkdir()

    # Create empty index files
    (gov_dir / "facts" / "index.json").write_text("[]")
    (gov_dir / "decisions" / "index.json").write_text("[]")
    (gov_dir / PROPOSALS_FILE).write_text("{}")

    # Create config file
    config = """\
# Governor configuration
[test]
command = ["pytest", "-q"]
timeout_seconds = 300

[envelopes]
default = "strict"

[envelopes.exploratory]
require_receipts = false

[envelopes.strict]
require_receipts = true
"""
    (gov_dir / "config.toml").write_text(config)

    # Create .gitignore
    gitignore = """\
# Local debugging only
rejections.log
"""
    (gov_dir / ".gitignore").write_text(gitignore)

    click.echo(f"Initialized governor at {gov_dir}")


@cli.command()
@click.option("--patch", "-p", type=click.Path(exists=True), help="Path to patch file")
@click.option("--claim", "-c", multiple=True, help="Claim in format: type=value,key=value,...")
@click.pass_context
def propose(ctx: click.Context, patch: str | None, claim: tuple[str, ...]) -> None:
    """
    Submit a proposal with claims.

    Claims are specified as: type=<type>,<key>=<value>,...

    Examples:
        --claim "type=file_exists,path=src/main.py"
        --claim "type=tests_pass,command=pytest -q"
        --claim "type=decision,topic=framework,choice=react"
    """
    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    # Parse claims
    claims = []
    for claim_str in claim:
        try:
            parsed = parse_claim(claim_str)
            claims.append(parsed)
        except ValueError as e:
            click.echo(f"Error parsing claim: {e}", err=True)
            ctx.exit(1)

    if not claims and not patch:
        click.echo("Error: Must provide at least one claim or a patch", err=True)
        ctx.exit(1)

    # If patch provided, add changeset claim
    if patch:
        patch_content = Path(patch).read_text()
        claims.append(changeset(patch_content))

    # Create proposal
    fsm = create_proposal(claims, patch_path=patch)
    fsm.propose()

    # Save proposal
    proposals = load_proposals(gov_dir)
    proposals[str(fsm.proposal.id)] = fsm.proposal.to_dict()
    save_proposals(gov_dir, proposals)

    click.echo(f"Proposal created: {fsm.proposal.id}")
    click.echo(f"State: {fsm.state.value}")
    click.echo(f"Claims: {len(claims)}")

    for i, c in enumerate(claims):
        click.echo(f"  [{i}] {c.describe()}")


@cli.command()
@click.argument("proposal_id")
@click.option("--json", "json_output", is_flag=True, help="Output results as JSON")
@click.pass_context
def verify(ctx: click.Context, proposal_id: str, json_output: bool) -> None:
    """Verify a proposal by running checks and producing receipts."""
    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    # Load proposal
    proposals = load_proposals(gov_dir)

    if proposal_id not in proposals:
        click.echo(f"Error: Proposal {proposal_id} not found", err=True)
        ctx.exit(1)

    from .fsm import Proposal
    proposal = Proposal.from_dict(proposals[proposal_id])
    fsm = ProposalFSM(proposal)

    if fsm.state != ProposalState.PROPOSED:
        click.echo(f"Error: Proposal is in {fsm.state.value} state, cannot verify", err=True)
        ctx.exit(1)

    # Get current envelope
    envelope = get_current_envelope(gov_dir)
    click.echo(f"Operating in {envelope.mode.value} mode")

    # Check for decision conflicts before verification (unless envelope allows)
    decision_ledger = DecisionLedger(gov_dir)
    conflicts = []

    if not envelope.allow_conflicts:
        for i, claim in enumerate(proposal.claims):
            if claim.type == ClaimType.DECISION:
                conflict = decision_ledger.check_conflict(claim)
                if conflict:
                    conflicts.append((i, claim, conflict))

    if conflicts and not envelope.allow_conflicts:
        rejection = RejectionInfo(
            reason="Decision conflicts with existing decisions",
            conflicting_decisions=[c.id for _, _, c in conflicts],
            details={
                "conflicts": [
                    {
                        "claim_index": i,
                        "proposed": {"topic": claim.topic, "choice": claim.choice},
                        "existing": {"topic": conflict.topic, "choice": conflict.choice, "id": str(conflict.id)},
                    }
                    for i, claim, conflict in conflicts
                ]
            },
        )
        fsm.reject(rejection)
        proposals[proposal_id] = fsm.proposal.to_dict()
        save_proposals(gov_dir, proposals)

        if json_output:
            import json as json_mod
            output = {
                "status": "rejected",
                "proposal_id": proposal_id,
                "rejection": rejection.to_dict(),
                "suggestions": rejection.get_suggestions(),
            }
            click.echo(json_mod.dumps(output, indent=2))
        else:
            click.echo("Decision conflict(s) detected:\n", err=True)
            for i, claim, conflict in conflicts:
                click.echo(f"  Claim [{i}]: {claim.topic} = {claim.choice}", err=True)
                click.echo(f"    Conflicts with existing: {conflict.topic} = {conflict.choice}", err=True)
                click.echo(f"    Existing decision ID: {conflict.id}", err=True)
                click.echo()

            click.echo("Suggestions:", err=True)
            for suggestion in rejection.get_suggestions():
                click.echo(f"  • {suggestion}", err=True)

        ctx.exit(1)

    # Run verifiers
    verifier = create_default_verifiers(root)
    results = verifier.verify_all(proposal.claims)

    # Check results
    failed_indices = []
    claim_errors = []
    receipts = []

    for i, result in enumerate(results):
        if result.success:
            receipts.append(result.receipt)
            if not json_output:
                click.echo(f"  [✓] Claim {i}: verified")
        else:
            failed_indices.append(i)
            # Create detailed error
            error_type = "verification_failed"
            suggestion = None
            if result.error and "not found" in result.error.lower():
                error_type = "file_not_found"
                suggestion = f"Create the file or check the path: {proposal.claims[i].path}"
            elif result.error and "exit code" in result.error.lower():
                error_type = "tests_failed"
                suggestion = "Fix failing tests before proposing"

            claim_errors.append(ClaimError(
                claim_index=i,
                error_type=error_type,
                message=result.error or "Unknown error",
                suggestion=suggestion,
            ))

            if not json_output:
                click.echo(f"  [✗] Claim {i}: {result.error}")

    if failed_indices:
        if envelope.require_receipts:
            # Reject in strict mode
            rejection = RejectionInfo(
                reason="Verification failed",
                failed_claims=failed_indices,
                claim_errors=claim_errors,
            )
            fsm.reject(rejection)
            proposals[proposal_id] = fsm.proposal.to_dict()
            save_proposals(gov_dir, proposals)

            if json_output:
                import json as json_mod
                output = {
                    "status": "rejected",
                    "proposal_id": proposal_id,
                    "rejection": rejection.to_dict(),
                    "suggestions": rejection.get_suggestions(),
                }
                click.echo(json_mod.dumps(output, indent=2))
            else:
                click.echo(f"\nProposal REJECTED: {len(failed_indices)} claim(s) failed")
                click.echo("\nErrors:")
                for error in claim_errors:
                    click.echo(f"  [{error.claim_index}] {error.error_type}: {error.message}")
                    if error.suggestion:
                        click.echo(f"      Suggestion: {error.suggestion}")
                click.echo("\nSuggestions:")
                for suggestion in rejection.get_suggestions():
                    click.echo(f"  • {suggestion}")

            ctx.exit(1)
        else:
            # In exploratory mode, warn but continue
            click.echo(f"\n⚠️  Warning: {len(failed_indices)} claim(s) failed verification")
            click.echo("Continuing in exploratory mode (receipts not required)")
            # Create stub receipts for failed claims
            from datetime import datetime, timezone
            from .receipts import FileSnapshot
            for i in failed_indices:
                stub = FileSnapshot(
                    path=f"exploratory:{i}",
                    blob_hash="exploratory",
                    size_bytes=0,
                    timestamp=datetime.now(timezone.utc),
                )
                receipts.append(stub)

    # All passed - verify
    fsm.verify(receipts)
    proposals[proposal_id] = fsm.proposal.to_dict()
    save_proposals(gov_dir, proposals)

    click.echo(f"\nProposal VERIFIED: {len(receipts)} receipt(s) produced")
    click.echo(f"Run 'governor apply {proposal_id}' to apply the changes")


@cli.command()
@click.argument("proposal_id")
@click.pass_context
def apply(ctx: click.Context, proposal_id: str) -> None:
    """Apply a verified proposal."""
    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    # Load proposal
    proposals = load_proposals(gov_dir)

    if proposal_id not in proposals:
        click.echo(f"Error: Proposal {proposal_id} not found", err=True)
        ctx.exit(1)

    from .fsm import Proposal
    proposal = Proposal.from_dict(proposals[proposal_id])
    fsm = ProposalFSM(proposal)

    if fsm.state != ProposalState.VERIFIED:
        click.echo(f"Error: Proposal is in {fsm.state.value} state, cannot apply", err=True)
        click.echo("Only VERIFIED proposals can be applied")
        ctx.exit(1)

    # Apply the patch if present
    if proposal.patch_path:
        import subprocess
        try:
            result = subprocess.run(
                ["git", "apply", proposal.patch_path],
                cwd=root,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                fsm.reject(RejectionInfo(
                    reason=f"Patch apply failed: {result.stderr}",
                ))
                proposals[proposal_id] = fsm.proposal.to_dict()
                save_proposals(gov_dir, proposals)
                click.echo(f"Error: {result.stderr}", err=True)
                ctx.exit(1)
        except Exception as e:
            click.echo(f"Error applying patch: {e}", err=True)
            ctx.exit(1)

    # Get current envelope
    envelope = get_current_envelope(gov_dir)

    # Update ledgers with facts/decisions
    fact_ledger = FactLedger(gov_dir)
    decision_ledger = DecisionLedger(gov_dir)

    for claim, receipt in zip(proposal.claims, proposal.receipts):
        if claim.type == ClaimType.DECISION:
            if envelope.commit_decisions:
                # Check for conflicts
                conflict = decision_ledger.check_conflict(claim)
                if conflict:
                    click.echo(f"Warning: Overwriting decision on '{claim.topic}'")

                decision_ledger.add(claim)
                click.echo(f"  Added decision: {claim.topic} = {claim.choice}")
            else:
                click.echo(f"  Skipped decision (exploratory mode): {claim.topic} = {claim.choice}")
        else:
            # Add as fact with file hashes for decay tracking
            file_hashes = {}
            if claim.path:
                # Extract current file hash for staleness detection
                full_path = root / claim.path
                if full_path.exists() and full_path.is_file():
                    import hashlib
                    file_hashes[claim.path] = hashlib.sha256(
                        full_path.read_bytes()
                    ).hexdigest()

            fact_ledger.add(claim, receipt, file_hashes=file_hashes)
            click.echo(f"  Added fact: {claim.describe()}")

    # Mark as applied
    fsm.apply()
    proposals[proposal_id] = fsm.proposal.to_dict()
    save_proposals(gov_dir, proposals)

    click.echo(f"\nProposal APPLIED")


@cli.command()
@click.option("--topic", "-t", help="Filter by topic")
@click.pass_context
def facts(ctx: click.Context, topic: str | None) -> None:
    """Query the facts ledger."""
    gov_dir = ensure_initialized(ctx)

    ledger = FactLedger(gov_dir)
    all_facts = ledger.all()

    if not all_facts:
        click.echo("No facts recorded")
        return

    click.echo(f"Facts ({len(all_facts)}):\n")

    for fact in sorted(all_facts, key=lambda f: f.created_at, reverse=True):
        click.echo(f"  [{fact.id}]")
        click.echo(f"    {fact.claim.describe()}")
        click.echo(f"    Created: {fact.created_at.isoformat()}")
        click.echo()


@cli.command()
@click.option("--topic", "-t", help="Filter by topic")
@click.pass_context
def decisions(ctx: click.Context, topic: str | None) -> None:
    """Query the decisions ledger."""
    gov_dir = ensure_initialized(ctx)

    ledger = DecisionLedger(gov_dir)
    active = ledger.query(topic)

    if not active:
        click.echo("No decisions recorded" if not topic else f"No decisions for topic '{topic}'")
        return

    click.echo(f"Active decisions ({len(active)}):\n")

    for dec in active:
        click.echo(f"  [{dec.topic}] {dec.choice}")
        if dec.rationale:
            click.echo(f"    Rationale: {dec.rationale}")
        click.echo(f"    ID: {dec.id}")
        click.echo()


@cli.command()
@click.option("--auto-prune", "-p", is_flag=True, help="Automatically remove stale facts")
@click.pass_context
def decay(ctx: click.Context, auto_prune: bool) -> None:
    """Check for and optionally remove stale facts."""
    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    ledger = FactLedger(gov_dir)
    facts = ledger.all()

    if not facts:
        click.echo("No facts to check")
        return

    click.echo(f"Checking {len(facts)} fact(s) for staleness...\n")

    stale_facts = []
    for fact in facts:
        is_stale = ledger.check_staleness(fact, base_path=root)
        status = "STALE" if is_stale else "ok"
        icon = "⚠️ " if is_stale else "✓ "

        click.echo(f"  {icon}[{status}] {fact.claim.describe()}")

        if is_stale:
            stale_facts.append(fact)

    click.echo()

    if not stale_facts:
        click.echo("All facts are fresh")
        return

    click.echo(f"Found {len(stale_facts)} stale fact(s)")

    if auto_prune:
        for fact in stale_facts:
            ledger.invalidate(fact.id)
        click.echo(f"Pruned {len(stale_facts)} stale fact(s)")
    else:
        click.echo("Run with --auto-prune to remove stale facts")


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of proposals to show")
@click.pass_context
def status(ctx: click.Context, limit: int) -> None:
    """Show proposal status."""
    gov_dir = ensure_initialized(ctx)

    proposals = load_proposals(gov_dir)

    if not proposals:
        click.echo("No proposals")
        return

    click.echo(f"Proposals ({len(proposals)}):\n")

    from .fsm import Proposal
    items = list(proposals.items())[:limit]

    for pid, data in items:
        proposal = Proposal.from_dict(data)
        state_icon = {
            ProposalState.DRAFT: "📝",
            ProposalState.PROPOSED: "📋",
            ProposalState.VERIFIED: "✓",
            ProposalState.APPLIED: "✅",
            ProposalState.REJECTED: "❌",
        }.get(proposal.state, "?")

        click.echo(f"  {state_icon} [{proposal.state.value}] {pid[:8]}...")
        click.echo(f"     Claims: {len(proposal.claims)}")
        click.echo()


@cli.command()
@click.argument("mode", type=click.Choice(["exploratory", "strict"]), required=False)
@click.option("--clear", "-c", is_flag=True, help="Clear envelope override, use default")
@click.pass_context
def envelope(ctx: click.Context, mode: str | None, clear: bool) -> None:
    """
    Get or set the operating envelope.

    Envelopes control how strictly the governor enforces rules:
    - exploratory: Hypotheses allowed, decisions not committed
    - strict: All claims require receipts, full enforcement

    Examples:
        governor envelope              # Show current envelope
        governor envelope exploratory  # Switch to exploratory mode
        governor envelope strict       # Switch to strict mode
        governor envelope --clear      # Revert to default
    """
    gov_dir = ensure_initialized(ctx)

    if clear:
        clear_envelope(gov_dir)
        click.echo("Envelope override cleared, using default from config")
        return

    if mode:
        try:
            envelope_mode = EnvelopeMode(mode)
            set_envelope(gov_dir, envelope_mode)
            click.echo(f"Envelope set to: {mode}")
        except ValueError:
            click.echo(f"Error: Unknown envelope mode: {mode}", err=True)
            ctx.exit(1)
    else:
        # Show current envelope
        current = get_current_envelope(gov_dir)
        click.echo(f"Current envelope: {current.mode.value}")
        click.echo(f"  require_receipts: {current.require_receipts}")
        click.echo(f"  commit_decisions: {current.commit_decisions}")
        click.echo(f"  allow_conflicts: {current.allow_conflicts}")


@cli.command()
@click.argument("decision_id")
@click.option("--choice", "-c", required=True, help="New choice value")
@click.option("--rationale", "-r", help="Reason for the revision")
@click.pass_context
def revise(ctx: click.Context, decision_id: str, choice: str, rationale: str | None) -> None:
    """
    Revise an existing decision.

    This is the proper way to change a decision - explicitly supersede it.

    Example:
        governor revise <decision-id> --choice vue --rationale "Migrating from React"
    """
    gov_dir = ensure_initialized(ctx)

    decision_ledger = DecisionLedger(gov_dir)

    try:
        old_id = UUID(decision_id)
    except ValueError:
        click.echo(f"Error: Invalid decision ID: {decision_id}", err=True)
        ctx.exit(1)

    old_decision = decision_ledger.get(old_id)
    if not old_decision:
        click.echo(f"Error: Decision {decision_id} not found", err=True)
        ctx.exit(1)

    # Create new decision claim with same topic
    new_claim = decision(old_decision.topic, choice)

    # Revise
    new_decision = decision_ledger.revise(old_id, new_claim, rationale=rationale)

    if new_decision:
        click.echo(f"Decision revised:")
        click.echo(f"  Topic: {new_decision.topic}")
        click.echo(f"  Old choice: {old_decision.choice}")
        click.echo(f"  New choice: {new_decision.choice}")
        if rationale:
            click.echo(f"  Rationale: {rationale}")
        click.echo(f"  New ID: {new_decision.id}")
    else:
        click.echo("Error: Revision failed", err=True)
        ctx.exit(1)


def parse_claim(claim_str: str) -> Claim:
    """
    Parse a claim string into a Claim object.

    Format: type=<type>,key=value,key=value,...

    Examples:
        type=file_exists,path=src/main.py
        type=tests_pass,command=pytest -q
        type=decision,topic=framework,choice=react
    """
    parts = {}
    for part in claim_str.split(","):
        if "=" not in part:
            raise ValueError(f"Invalid claim part: {part}")
        key, value = part.split("=", 1)
        parts[key.strip()] = value.strip()

    if "type" not in parts:
        raise ValueError("Claim must have 'type' field")

    claim_type = parts.pop("type")

    if claim_type == "file_exists":
        if "path" not in parts:
            raise ValueError("file_exists claim requires 'path'")
        return file_exists(parts["path"])

    elif claim_type == "tests_pass":
        if "command" not in parts:
            raise ValueError("tests_pass claim requires 'command'")
        # Split command by spaces
        cmd = tuple(parts["command"].split())
        return claim_tests_pass(cmd)

    elif claim_type == "decision":
        if "topic" not in parts or "choice" not in parts:
            raise ValueError("decision claim requires 'topic' and 'choice'")
        return decision(parts["topic"], parts["choice"])

    elif claim_type == "changeset":
        if "diff" not in parts:
            raise ValueError("changeset claim requires 'diff'")
        return changeset(parts["diff"])

    else:
        raise ValueError(f"Unknown claim type: {claim_type}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
