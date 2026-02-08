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
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import click

from .claims import Claim, ClaimType, decision, file_exists, claim_tests_pass, changeset, work_reservation
from .envelopes import EnvelopeMode, get_current_envelope, set_envelope, clear_envelope
from .fsm import ProposalFSM, ProposalState, RejectionInfo, ClaimError, create_proposal
from .ledgers import FactLedger, DecisionLedger
from .permissions import PermissionManager, AgentPermissions, PROFILES, create_default_config
from .storage import get_storage
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


@click.group(invoke_without_command=True)
@click.option(
    "--root", "-r",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Project root directory",
)
@click.pass_context
def cli(ctx: click.Context, root: str) -> None:
    """Agent Governor - AI that remembers your rules.

    \b
    Quick start:
      governor                    See status and quick commands
      governor fiction init       Start a story project
      governor code init          Start a code project

    \b
    Fiction (for writers):
      governor fiction            All fiction commands
      governor fiction character  Manage characters
      governor fiction world      Manage world rules

    \b
    Code (for developers):
      governor code               All code commands
      governor code decision      Manage decisions
      governor code constraint    Manage constraints

    \b
    Universal:
      governor check <file>       Check content
      governor resolve            Handle pending issues

    \b
    Advanced:
      governor advanced           Power user commands (50+)
    """
    ctx.ensure_object(dict)
    ctx.obj["root"] = root

    # Show friendly status when no subcommand is provided
    if ctx.invoked_subcommand is None:
        from .cli_friendly import show_friendly_status
        show_friendly_status(ctx)


@cli.command()
@click.option("--v2", "use_v2", is_flag=True, help="Initialize with SQLite backend (v2)")
@click.pass_context
def init(ctx: click.Context, use_v2: bool) -> None:
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

    # Create empty index files (v1 compatibility)
    (gov_dir / "facts" / "index.json").write_text("[]")
    (gov_dir / "decisions" / "index.json").write_text("[]")
    (gov_dir / PROPOSALS_FILE).write_text("{}")

    # Create default config with permissions
    create_default_config(gov_dir)

    # Create .gitignore
    gitignore = """\
# Local debugging only
rejections.log
# SQLite database (local state)
governor.db
governor.db-wal
governor.db-shm
"""
    (gov_dir / ".gitignore").write_text(gitignore)

    # Initialize SQLite storage if v2 mode
    if use_v2:
        storage = get_storage(gov_dir)
        click.echo(f"Initialized SQLite database at {gov_dir / 'governor.db'}")

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

    click.echo("\nProposal APPLIED")


@cli.command()
@click.option("--topic", "-t", help="Filter by topic")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def facts(ctx: click.Context, topic: str | None, as_json: bool) -> None:
    """Query the facts ledger."""
    gov_dir = ensure_initialized(ctx)

    ledger = FactLedger(gov_dir)
    all_facts = ledger.all()

    if as_json:
        click.echo(json.dumps([f.to_dict() for f in all_facts], indent=2))
        return

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def decisions(ctx: click.Context, topic: str | None, as_json: bool) -> None:
    """Query the decisions ledger."""
    gov_dir = ensure_initialized(ctx)

    ledger = DecisionLedger(gov_dir)
    active = ledger.query(topic)

    if as_json:
        click.echo(json.dumps([d.to_dict() for d in active], indent=2))
        return

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--claims", "show_claims", is_flag=True, help="Show claim status weather report")
@click.pass_context
def status(ctx: click.Context, limit: int, as_json: bool, show_claims: bool) -> None:
    """Show proposal status. With --claims, show claim weather report."""
    gov_dir = ensure_initialized(ctx)

    # If --claims flag, show claim status summary
    if show_claims:
        from .epistemic import EpistemicLedger
        from .claim_status import create_claim_status_dashboard

        ledger = EpistemicLedger()
        dashboard = create_claim_status_dashboard(ledger)

        if as_json:
            summary = dashboard.get_summary()
            click.echo(json.dumps(summary.to_dict(), indent=2))
        else:
            click.echo(dashboard.format_summary())
        return

    proposals = load_proposals(gov_dir)

    if as_json:
        from .fsm import Proposal
        items = list(proposals.items())[:limit]
        result = [Proposal.from_dict(data).to_dict() for _pid, data in items]
        click.echo(json.dumps(result, indent=2))
        return

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
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--schema", type=click.Choice(["v1", "v2"]), default="v2",
              help="Schema version: v1 (legacy) or v2 (canonical ViewModel)")
@click.pass_context
def state(ctx: click.Context, as_json: bool, schema: str) -> None:
    """Show aggregated governor state.

    Returns a single JSON object with all governor state sections.
    Requires --json flag (designed for tooling consumption).

    Schema v2 (default) returns the canonical GovernorViewModel with 8 sections:
    session, regime, decisions, claims, evidence, violations, execution, stability.

    Schema v1 returns the legacy format for backward compatibility.
    """
    if not as_json:
        click.echo("Usage: governor state --json [--schema v1|v2]")
        click.echo("This command outputs aggregated state as JSON for tooling.")
        return

    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    from .viewmodel import build_viewmodel, build_v1_state

    if schema == "v1":
        result = build_v1_state(gov_dir, root)
    else:
        vm = build_viewmodel(gov_dir, root)
        result = vm.to_dict()

    click.echo(json.dumps(result, indent=2))


@cli.command()
@click.option("--limit", "-n", default=20, help="Number of rejections to show")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def rejections(ctx: click.Context, limit: int, json_output: bool) -> None:
    """
    Show rejection history.

    Displays recently rejected proposals with their rejection reasons.
    This is useful for debugging and understanding why proposals failed.

    Note: Rejection history is local only (not git-tracked).
    """
    gov_dir = ensure_initialized(ctx)

    proposals = load_proposals(gov_dir)

    # Filter to rejected proposals
    from .fsm import Proposal
    rejected = []
    for pid, data in proposals.items():
        proposal = Proposal.from_dict(data)
        if proposal.state == ProposalState.REJECTED and proposal.rejection:
            rejected.append((pid, proposal))

    # Sort by creation time (most recent first)
    rejected.sort(key=lambda x: x[1].created_at, reverse=True)
    rejected = rejected[:limit]

    if not rejected:
        click.echo("No rejected proposals")
        return

    if json_output:
        output = []
        for pid, proposal in rejected:
            output.append({
                "id": pid,
                "created_at": proposal.created_at.isoformat(),
                "claims": [c.describe() for c in proposal.claims],
                "rejection": proposal.rejection.to_dict(),
            })
        click.echo(json.dumps(output, indent=2))
        return

    click.echo(f"Rejected proposals ({len(rejected)}):\n")

    for pid, proposal in rejected:
        click.echo(f"  ❌ {pid[:8]}...")
        click.echo(f"     Reason: {proposal.rejection.reason}")

        if proposal.rejection.failed_claims:
            click.echo(f"     Failed claims: {proposal.rejection.failed_claims}")

        if proposal.rejection.claim_errors:
            for error in proposal.rejection.claim_errors[:3]:
                click.echo(f"       [{error.claim_index}] {error.error_type}: {error.message}")

        if proposal.rejection.conflicting_decisions:
            click.echo(f"     Conflicts: {len(proposal.rejection.conflicting_decisions)} decision(s)")

        suggestions = proposal.rejection.get_suggestions()
        if suggestions:
            click.echo(f"     Suggestion: {suggestions[0]}")

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
        click.echo("Decision revised:")
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


# Hook command group
@cli.group()
@click.pass_context
def hook(ctx: click.Context) -> None:
    """
    Git hook management.

    Install and manage the pre-commit hook that enforces governor approval.
    """
    pass


@hook.command("install")
@click.pass_context
def hook_install(ctx: click.Context) -> None:
    """Install the pre-commit hook."""
    from .hooks import install_hook, get_git_root

    root = Path(ctx.obj["root"])
    git_root = get_git_root(root)

    if not git_root:
        click.echo("Error: Not in a git repository", err=True)
        ctx.exit(1)

    success, message = install_hook(git_root)

    if success:
        click.echo(message)
    else:
        click.echo(f"Error: {message}", err=True)
        ctx.exit(1)


@hook.command("uninstall")
@click.pass_context
def hook_uninstall(ctx: click.Context) -> None:
    """Uninstall the pre-commit hook."""
    from .hooks import uninstall_hook, get_git_root

    root = Path(ctx.obj["root"])
    git_root = get_git_root(root)

    if not git_root:
        click.echo("Error: Not in a git repository", err=True)
        ctx.exit(1)

    success, message = uninstall_hook(git_root)

    if success:
        click.echo(message)
    else:
        click.echo(f"Error: {message}", err=True)
        ctx.exit(1)


@hook.command("status")
@click.pass_context
def hook_status(ctx: click.Context) -> None:
    """Show hook installation status."""
    from .hooks import get_hook_status, get_git_root

    root = Path(ctx.obj["root"])
    git_root = get_git_root(root)

    if not git_root:
        click.echo("Error: Not in a git repository", err=True)
        ctx.exit(1)

    status = get_hook_status(git_root)

    click.echo("Git Hook Status:")
    click.echo(f"  Installed: {'yes' if status['installed'] else 'no'}")

    if status["installed"]:
        click.echo(f"  Is Governor hook: {'yes' if status['is_governor_hook'] else 'no'}")
        click.echo(f"  Executable: {'yes' if status['executable'] else 'no'}")

    if status["has_backup"]:
        click.echo("  Backup exists: yes")


@hook.command("pre-commit")
@click.option("--bypass", is_flag=True, help="Bypass the check")
@click.option("--check-continuity", "-c", is_flag=True, help="Also check staged content for continuity violations")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode for violation resolution")
@click.option("--mode", "hook_mode", type=click.Choice(["code", "fiction", "nonfiction"]), default="code", help="Context mode for continuity checking")
@click.pass_context
def hook_pre_commit(ctx: click.Context, bypass: bool, check_continuity: bool, interactive: bool, hook_mode: str) -> None:
    """
    Run the pre-commit check.

    This is called by the git pre-commit hook script.
    Can also be run directly with --interactive for violation resolution.

    With --check-continuity, staged file contents are checked against anchors.
    With --interactive, blocking violations trigger the resolution flow.

    Examples:
        governor hook pre-commit
        governor hook pre-commit --check-continuity --interactive
    """
    from .hooks import run_pre_commit_check, get_git_root, get_staged_files
    from .violation_resolver import ViolationResolver

    root = Path(ctx.obj["root"])
    git_root = get_git_root(root)
    gov_dir = root / ".governor"

    # First check for pending violations from previous runs
    if gov_dir.exists():
        resolver = ViolationResolver(gov_dir, mode=hook_mode, context_id="hook_precommit")
        pending = resolver.get_pending()
        if pending:
            click.echo(click.style("[Governor] Pending violation requires resolution:", fg="yellow"))
            click.echo()
            for v in pending.violations:
                desc = v.get("description", str(v))
                click.echo(f"  • {desc}")
            click.echo()
            click.echo("Resolve before committing:")
            click.echo("  governor lite fix      # Regenerate compliant content")
            click.echo("  governor lite revise   # Update the constraint")
            click.echo("  governor lite proceed  # Log as exception")
            click.echo()
            click.echo("Or view details with: governor lite pending")
            ctx.exit(1)
            return

    # Standard pre-commit approval check
    success, message = run_pre_commit_check(git_root, bypass=bypass)

    if not success:
        click.echo(message)
        ctx.exit(1)
        return

    # Optionally check continuity on staged content
    if check_continuity and gov_dir.exists():
        continuity_ok, continuity_msg = _check_staged_continuity(
            ctx, git_root, gov_dir, interactive, hook_mode
        )
        if not continuity_ok:
            click.echo(continuity_msg)
            ctx.exit(1)
            return

    click.echo(message)


def _check_staged_continuity(
    ctx: click.Context,
    git_root: Path,
    gov_dir: Path,
    interactive: bool,
    mode: str,
) -> tuple[bool, str]:
    """Check staged file contents for continuity violations."""
    import subprocess
    from .check import run_check
    from .violation_resolver import (
        ViolationResolver,
        ResolutionAction,
        format_violation_prompt,
        get_mode_choices,
    )

    # Get staged files
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return True, ""  # Can't get staged files, pass through

    staged_files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    if not staged_files:
        return True, ""

    # Check each staged file
    blocking_violations = []
    blocked_content_parts = []

    for file_path in staged_files:
        # Skip .governor files
        if file_path.startswith(".governor/"):
            continue

        # Get staged content
        content_result = subprocess.run(
            ["git", "show", f":{file_path}"],
            cwd=git_root,
            capture_output=True,
        )
        if content_result.returncode != 0:
            continue

        try:
            content = content_result.stdout.decode("utf-8")
        except UnicodeDecodeError:
            continue  # Skip binary files

        check_result = run_check(
            content,
            file_path,
            run_security=True,
            run_continuity=True,
            governor_dir=gov_dir,
        )

        for f in check_result.findings:
            if f.severity == "error":
                blocking_violations.append({
                    "file": file_path,
                    "anchor_id": f.code,
                    "description": f"{file_path}: {f.message}",
                    "severity": "reject",
                    "evidence": [f.suggestion] if f.suggestion else [],
                })
                blocked_content_parts.append(f"=== {file_path} ===\n{content}")

    if not blocking_violations:
        return True, ""

    # Violations found
    click.echo()
    click.echo(click.style(f"[Governor] {len(blocking_violations)} blocking violation(s) in staged files:", fg="red"))
    for v in blocking_violations:
        click.echo(f"  • {v['description']}")
    click.echo()

    if not interactive:
        click.echo("COMMIT BLOCKED: Staged files have continuity violations.")
        click.echo()
        click.echo("To resolve:")
        click.echo("  1. Fix the violations and re-stage")
        click.echo("  2. Or run: governor hook pre-commit --check-continuity --interactive")
        click.echo("  3. Or bypass with: git commit --no-verify (not recommended)")
        return False, ""

    # Interactive mode
    blocked_response = "\n\n".join(blocked_content_parts)
    resolver = ViolationResolver(gov_dir, mode=mode, context_id="hook_precommit")
    run_id = f"precommit_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    pending = resolver.create_pending(blocking_violations, blocked_response, run_id)

    click.echo(format_violation_prompt(blocking_violations, mode))
    click.echo()

    # Interactive resolution loop
    while True:
        try:
            user_input = click.prompt("Choice", default="", show_default=False)
        except click.exceptions.Abort:
            click.echo("\nAborted. Pending violation saved for later resolution.")
            return False, "Commit blocked - pending violation"

        action = resolver.is_resolution_command(user_input)
        if action is None:
            click.echo()
            click.echo("Invalid choice. Please enter 1, 2, 3 or: fix | revise | proceed")
            click.echo()
            for choice in get_mode_choices(mode):
                click.echo(f"  {choice}")
            click.echo()
            continue

        if action == ResolutionAction.FIX:
            click.echo()
            click.echo("[Governor] Fix: Edit the staged files to comply with constraints,")
            click.echo("then re-stage and commit.")
            resolver.clear_pending()
            return False, "Commit blocked - fix staged files and retry"

        elif action == ResolutionAction.REVISE:
            result_obj = resolver.resolve_revise(pending)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            if result_obj.anchor_update:
                for anchor_id in result_obj.anchor_update.get("revised_anchors", []):
                    click.echo(f"  - Revised: {anchor_id}")
            # Allow commit to proceed
            return True, ""

        elif action == ResolutionAction.PROCEED:
            scope = click.prompt("Exception scope", default="single_instance",
                               type=click.Choice(["single_instance", "session", "project"]))
            result_obj = resolver.resolve_proceed(pending, scope=scope)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            # Allow commit to proceed
            return True, ""


@hook.command("bypass")
@click.pass_context
def hook_bypass(ctx: click.Context) -> None:
    """
    Create a one-time bypass for the next commit.

    Use this for emergency commits that need to skip governor approval.
    The bypass is consumed after one commit.
    """
    gov_dir = ensure_initialized(ctx)

    bypass_file = gov_dir / ".bypass"
    bypass_file.write_text("")

    click.echo("One-time bypass created")
    click.echo("Next commit will skip governor check")
    click.echo("(Bypass is automatically removed after use)")


@cli.command("wrap")
@click.argument("command", nargs=-1, required=True)
@click.option("--auto-approve", "-a", is_flag=True, help="Auto-approve in exploratory mode")
@click.option("--check-continuity", "-c", is_flag=True, help="Check file changes for continuity violations")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode: offer fix/revise/proceed on violations")
@click.option("--mode", "wrap_mode", type=click.Choice(["code", "fiction", "nonfiction"]), default="code", help="Context mode for continuity checking")
@click.pass_context
def wrap(ctx: click.Context, command: tuple[str, ...], auto_approve: bool, check_continuity: bool, interactive: bool, wrap_mode: str) -> None:
    """
    Wrap an agent command with governor enforcement.

    Monitors file changes made by the agent and ensures they go
    through the governor approval workflow.

    With --check-continuity, file changes are checked against anchors.
    With --interactive, blocking violations trigger the resolution flow.

    Examples:
        governor wrap -- python script.py
        governor wrap --auto-approve -- claude-code
        governor wrap -- npm run build
        governor wrap --check-continuity --interactive -- claude-code
    """
    from .wrapper import wrap_agent, AgentWrapper

    root = Path(ctx.obj["root"])
    gov_dir = root / ".governor"

    if check_continuity and not gov_dir.exists():
        click.echo("Warning: --check-continuity requires initialized governor. Running without continuity checks.", err=True)
        check_continuity = False

    if not check_continuity:
        # Original behavior
        exit_code, message = wrap_agent(
            list(command),
            root=root,
            auto_approve=auto_approve,
        )
        click.echo(message)
        ctx.exit(exit_code)
        return

    # Enhanced wrap with continuity checking
    exit_code, message = _wrap_with_continuity_check(
        ctx, list(command), root, gov_dir, auto_approve, interactive, wrap_mode
    )
    click.echo(message)
    ctx.exit(exit_code)


def _wrap_with_continuity_check(
    ctx: click.Context,
    command: list[str],
    root: Path,
    gov_dir: Path,
    auto_approve: bool,
    interactive: bool,
    mode: str,
) -> tuple[int, str]:
    """Wrap command with continuity violation checking."""
    from .wrapper import AgentWrapper, rollback_changes
    from .check import run_check
    from .violation_resolver import (
        ViolationResolver,
        ResolutionAction,
        format_violation_prompt,
        get_mode_choices,
    )
    from .envelopes import get_current_envelope

    wrapper = AgentWrapper(root, gov_dir, auto_approve=auto_approve)
    exit_code, changes = wrapper.run(command)

    if not changes:
        return exit_code, "No file changes detected"

    # Check changed files for violations
    blocking_violations = []
    for change in changes:
        if change.change_type in ("created", "modified") and change.new_content:
            try:
                content = change.new_content.decode("utf-8")
            except UnicodeDecodeError:
                continue  # Skip binary files

            result = run_check(
                content,
                change.path,
                run_security=True,
                run_continuity=True,
                governor_dir=gov_dir,
            )

            # Collect blocking errors
            for f in result.findings:
                if f.severity == "error":
                    blocking_violations.append({
                        "file": change.path,
                        "anchor_id": f.code,
                        "description": f.message,
                        "severity": "reject",
                        "evidence": [f.suggestion] if f.suggestion else [],
                    })

    if not blocking_violations:
        # No violations - proceed with normal approval flow
        envelope = get_current_envelope(gov_dir)
        if auto_approve and not envelope.require_receipts:
            return exit_code, f"Approved {len(changes)} file change(s) - no violations"
        return exit_code, f"{len(changes)} file change(s) detected - no violations"

    # Violations found
    click.echo()
    click.echo(click.style(f"[Governor] {len(blocking_violations)} blocking violation(s) in changed files:", fg="red"))
    for v in blocking_violations:
        click.echo(f"  • {v['file']}: {v['description']}")
    click.echo()

    if not interactive:
        # Non-interactive: rollback and exit
        rollback_changes(root, changes)
        click.echo("Changes rolled back due to violations.")
        click.echo()
        click.echo("To resolve interactively, run with --interactive flag:")
        click.echo(f"  governor wrap --check-continuity --interactive -- {' '.join(command)}")
        click.echo()
        click.echo("Or resolve manually:")
        click.echo("  governor lite pending  # View pending violations")
        click.echo("  governor lite fix      # Regenerate compliant content")
        click.echo("  governor lite revise   # Update the constraint")
        click.echo("  governor lite proceed  # Log as exception")
        return 1, "Blocked due to continuity violations"

    # Interactive mode
    # Aggregate content for pending violation
    all_content = []
    for change in changes:
        if change.change_type in ("created", "modified") and change.new_content:
            try:
                all_content.append(f"=== {change.path} ===\n{change.new_content.decode('utf-8')}")
            except UnicodeDecodeError:
                pass
    blocked_response = "\n\n".join(all_content)

    resolver = ViolationResolver(gov_dir, mode=mode, context_id="cli_wrap")
    run_id = f"wrap_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    pending = resolver.create_pending(blocking_violations, blocked_response, run_id)

    click.echo(format_violation_prompt(blocking_violations, mode))
    click.echo()

    # Interactive resolution loop
    while True:
        try:
            user_input = click.prompt("Choice", default="", show_default=False)
        except click.exceptions.Abort:
            rollback_changes(root, changes)
            click.echo("\nAborted. Changes rolled back.")
            return 1, "Aborted by user"

        action = resolver.is_resolution_command(user_input)
        if action is None:
            click.echo()
            click.echo("Invalid choice. Please enter 1, 2, 3 or: fix | revise | proceed")
            click.echo()
            for choice in get_mode_choices(mode):
                click.echo(f"  {choice}")
            click.echo()
            continue

        if action == ResolutionAction.FIX:
            rollback_changes(root, changes)
            click.echo()
            click.echo("[Governor] Fix requires manual correction or chat backend.")
            click.echo("Changes have been rolled back. Edit files and re-run the command.")
            resolver.clear_pending()
            return 1, "Fix selected - changes rolled back for manual correction"

        elif action == ResolutionAction.REVISE:
            result_obj = resolver.resolve_revise(pending)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            if result_obj.anchor_update:
                for anchor_id in result_obj.anchor_update.get("revised_anchors", []):
                    click.echo(f"  - Revised: {anchor_id}")
            # Keep changes - they're now permitted
            return exit_code, f"Constraints revised. {len(changes)} file change(s) now permitted."

        elif action == ResolutionAction.PROCEED:
            scope = click.prompt("Exception scope", default="single_instance",
                               type=click.Choice(["single_instance", "session", "project"]))
            result_obj = resolver.resolve_proceed(pending, scope=scope)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            # Keep changes - exception logged
            return exit_code, f"Exception logged. {len(changes)} file change(s) permitted."


@cli.command("changes")
@click.pass_context
def changes(ctx: click.Context) -> None:
    """
    Show uncommitted file changes and their approval status.

    Shows which files have been modified and whether they've been
    approved through the governor workflow.
    """
    from .wrapper import DirectorySnapshot
    from .hooks import get_approved_files, get_git_root

    root = Path(ctx.obj["root"])
    gov_dir = root / ".governor"

    if not gov_dir.exists():
        click.echo("Governor not initialized")
        ctx.exit(1)

    git_root = get_git_root(root)
    if not git_root:
        click.echo("Not in a git repository")
        ctx.exit(1)

    # Get approved files
    approved = get_approved_files(gov_dir)

    # Get current changes from git
    import subprocess
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )

    if not result.stdout.strip():
        click.echo("No uncommitted changes")
        return

    click.echo("Uncommitted changes:\n")

    for line in result.stdout.strip().split("\n"):
        if not line.strip():
            continue

        status = line[:2]
        file_path = line[3:].strip()

        # Handle renamed files
        if " -> " in file_path:
            file_path = file_path.split(" -> ")[1]

        is_approved = file_path in approved or file_path.startswith(".governor/")
        icon = "✓" if is_approved else "✗"
        approval = "approved" if is_approved else "NOT approved"

        click.echo(f"  {icon} [{status.strip() or 'M'}] {file_path} ({approval})")

    click.echo()

    unapproved = [
        line[3:].strip()
        for line in result.stdout.strip().split("\n")
        if line.strip() and line[3:].strip() not in approved
        and not line[3:].strip().startswith(".governor/")
    ]

    if unapproved:
        click.echo(f"{len(unapproved)} file(s) need governor approval before commit")
    else:
        click.echo("All changes are approved")


# MCP command group
@cli.group()
@click.pass_context
def mcp(ctx: click.Context) -> None:
    """
    MCP (Model Context Protocol) server management.

    Run governor as an MCP server for integration with Claude Desktop
    and other MCP-compatible clients.
    """
    pass


@mcp.command("serve")
@click.pass_context
def mcp_serve(ctx: click.Context) -> None:
    """
    Run the MCP server.

    This starts a JSON-RPC server on stdio that implements the
    Model Context Protocol. Configure this in your MCP client
    (e.g., Claude Desktop) to use governor tools.

    Example Claude Desktop config:
        {
            "mcpServers": {
                "governor": {
                    "command": "governor",
                    "args": ["mcp", "serve"]
                }
            }
        }
    """
    from .mcp_server import run_mcp_server

    root = Path(ctx.obj["root"])
    run_mcp_server(root)


@mcp.command("tools")
@click.pass_context
def mcp_tools(ctx: click.Context) -> None:
    """List available MCP tools."""
    from .mcp_server import create_mcp_server

    root = Path(ctx.obj["root"])
    server = create_mcp_server(root)

    tools = server.list_tools()

    click.echo(f"Available MCP tools ({len(tools)}):\n")

    for tool in tools:
        click.echo(f"  {tool['name']}")
        click.echo(f"    {tool['description']}")
        click.echo()


@mcp.command("call")
@click.argument("tool_name")
@click.option("--arg", "-a", multiple=True, help="Tool argument in key=value format")
@click.pass_context
def mcp_call(ctx: click.Context, tool_name: str, arg: tuple[str, ...]) -> None:
    """
    Call an MCP tool directly.

    Useful for testing tools without an MCP client.

    Examples:
        governor mcp call governor_status
        governor mcp call governor_propose -a 'claims=[{"type":"file_exists","path":"test.py"}]'
    """
    from .mcp_server import create_mcp_server

    root = Path(ctx.obj["root"])
    server = create_mcp_server(root)

    # Parse arguments
    arguments = {}
    for a in arg:
        if "=" not in a:
            click.echo(f"Invalid argument format: {a}", err=True)
            click.echo("Use key=value format", err=True)
            ctx.exit(1)

        key, value = a.split("=", 1)

        # Try to parse as JSON
        try:
            arguments[key] = json.loads(value)
        except json.JSONDecodeError:
            arguments[key] = value

    result = server.call_tool(tool_name, arguments)

    click.echo(json.dumps(result, indent=2))

    if not result.get("success", True):
        ctx.exit(1)


# Agent command group (dispatcher protocol)
@cli.group()
@click.pass_context
def agent(ctx: click.Context) -> None:
    """
    Agent management for multi-agent coordination.

    Register agents, check permissions, and manage agent state.
    """
    pass


@agent.command("register")
@click.option("--id", "agent_id", required=True, help="Unique agent identifier")
@click.option("--class", "agent_class", default="default", help="Agent class (default, architect, implementer, docs)")
@click.option("--capabilities", "-c", default="", help="Comma-separated capabilities (changeset, fact, decision)")
@click.pass_context
def agent_register(ctx: click.Context, agent_id: str, agent_class: str, capabilities: str) -> None:
    """
    Register an agent with the governor.

    Agents must register before they can claim tasks or submit proposals.

    Examples:
        governor agent register --id "worker-1" --class implementer
        governor agent register --id "architect-1" --class architect --capabilities "changeset,fact,decision"
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    now = datetime.now(timezone.utc)
    caps = [c.strip() for c in capabilities.split(",") if c.strip()]

    # Get permissions for this agent class
    perm_manager = PermissionManager(gov_dir)
    perms = perm_manager.get_permissions(agent_id, agent_class)

    # Check if agent already exists
    existing = storage.get_by_id("agents", agent_id)
    if existing:
        # Update registration
        storage.update(
            "agents",
            "id",
            agent_id,
            {
                "agent_class": agent_class,
                "capabilities_json": json.dumps(caps),
                "last_heartbeat": now.isoformat(),
                "permissions_json": json.dumps(perms.to_dict()),
            },
        )
        click.echo(f"Agent '{agent_id}' updated")
    else:
        # New registration
        storage.insert(
            "agents",
            {
                "id": agent_id,
                "agent_class": agent_class,
                "capabilities_json": json.dumps(caps),
                "registered_at": now.isoformat(),
                "last_heartbeat": now.isoformat(),
                "permissions_json": json.dumps(perms.to_dict()),
            },
        )
        click.echo(f"Agent '{agent_id}' registered")

    click.echo(f"  Class: {agent_class}")
    click.echo(f"  Capabilities: {caps or ['(default)']}")
    click.echo(f"  Can propose decisions: {perms.can_propose_decisions}")
    click.echo(f"  Can propose changesets: {perms.can_propose_changesets}")


@agent.command("list")
@click.option("--class", "agent_class", help="Filter by agent class")
@click.pass_context
def agent_list(ctx: click.Context, agent_class: str | None) -> None:
    """List registered agents."""
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    where = {"agent_class": agent_class} if agent_class else None
    agents = storage.query("agents", where=where, order_by="registered_at DESC")

    if not agents:
        click.echo("No agents registered")
        return

    click.echo(f"Registered agents ({len(agents)}):\n")

    now = datetime.now(timezone.utc)
    for agent in agents:
        last_hb = datetime.fromisoformat(agent["last_heartbeat"])
        age = now - last_hb
        status = "active" if age.total_seconds() < 300 else "stale"
        status_icon = "✓" if status == "active" else "⚠️"

        caps = json.loads(agent["capabilities_json"])

        click.echo(f"  {status_icon} {agent['id']}")
        click.echo(f"     Class: {agent['agent_class']}")
        click.echo(f"     Capabilities: {caps or ['(default)']}")
        click.echo(f"     Last seen: {age.total_seconds():.0f}s ago ({status})")
        click.echo()


@agent.command("permissions")
@click.argument("agent_id")
@click.option("--class", "agent_class", help="Override agent class")
@click.pass_context
def agent_permissions(ctx: click.Context, agent_id: str, agent_class: str | None) -> None:
    """
    Show permissions for an agent.

    Examples:
        governor agent permissions worker-1
        governor agent permissions unknown-agent --class architect
    """
    gov_dir = ensure_initialized(ctx)

    # Check if agent is registered
    storage = get_storage(gov_dir)
    registered = storage.get_by_id("agents", agent_id)

    if registered and not agent_class:
        agent_class = registered["agent_class"]

    perm_manager = PermissionManager(gov_dir)
    perms = perm_manager.get_permissions(agent_id, agent_class)

    click.echo(f"Permissions for '{agent_id}':")
    if agent_class:
        click.echo(f"  (class: {agent_class})")
    click.echo()

    click.echo(f"  can_propose_decisions: {perms.can_propose_decisions}")
    click.echo(f"  can_propose_changesets: {perms.can_propose_changesets}")
    click.echo(f"  can_propose_facts: {perms.can_propose_facts}")
    click.echo(f"  can_propose_reservations: {perms.can_propose_reservations}")
    click.echo()
    click.echo(f"  allowed_paths: {perms.allowed_paths}")
    click.echo(f"  denied_paths: {perms.denied_paths}")
    click.echo()
    click.echo(f"  allowed_decision_topics: {perms.allowed_decision_topics or '(all)'}")
    click.echo(f"  max_files_per_changeset: {perms.max_files_per_changeset}")


@agent.command("heartbeat")
@click.option("--id", "agent_id", required=True, help="Agent identifier")
@click.pass_context
def agent_heartbeat(ctx: click.Context, agent_id: str) -> None:
    """
    Send a heartbeat to keep agent registration active.

    Agents should send heartbeats periodically (every 60s recommended).
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    now = datetime.now(timezone.utc)

    updated = storage.update(
        "agents",
        "id",
        agent_id,
        {"last_heartbeat": now.isoformat()},
    )

    if updated:
        click.echo(f"Heartbeat recorded for '{agent_id}'")
    else:
        click.echo(f"Error: Agent '{agent_id}' not registered", err=True)
        ctx.exit(1)


# Task command group (dispatcher protocol)
@cli.group()
@click.pass_context
def task(ctx: click.Context) -> None:
    """
    Task management for multi-agent coordination.

    Claim tasks, send heartbeats, and mark tasks complete.
    """
    pass


@task.command("claim")
@click.option("--agent-id", required=True, help="Agent claiming the task")
@click.option("--task", "task_desc", required=True, help="Task description")
@click.option("--scope", required=True, help="Comma-separated file paths")
@click.option("--eta", "eta_minutes", type=int, default=30, help="Estimated time in minutes")
@click.pass_context
def task_claim(ctx: click.Context, agent_id: str, task_desc: str, scope: str, eta_minutes: int) -> None:
    """
    Claim a task/work reservation.

    Creates a work reservation for the specified scope, preventing conflicts
    with other agents.

    Examples:
        governor task claim --agent-id worker-1 --task "implement /users endpoint" --scope "src/api/users.py,tests/test_users.py"
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    # Check agent is registered
    agent = storage.get_by_id("agents", agent_id)
    if not agent:
        click.echo(f"Error: Agent '{agent_id}' not registered. Run 'governor agent register' first.", err=True)
        ctx.exit(1)

    # Parse scope
    scope_paths = [p.strip() for p in scope.split(",") if p.strip()]

    # Check permissions
    perm_manager = PermissionManager(gov_dir)
    perms = perm_manager.get_permissions(agent_id, agent["agent_class"])

    for path in scope_paths:
        if not perms.can_touch_path(path):
            click.echo(f"Error: Agent '{agent_id}' cannot touch path '{path}'", err=True)
            ctx.exit(1)

    # Check for conflicting reservations
    now = datetime.now(timezone.utc)
    active_reservations = storage.query(
        "reservations",
        where=None,
        order_by="started_at DESC",
    )

    for res in active_reservations:
        if res["completed_at"]:
            continue
        expires = datetime.fromisoformat(res["expires_at"])
        if expires < now:
            continue

        res_scope = json.loads(res["scope_json"])
        overlap = set(res_scope) & set(scope_paths)
        if overlap:
            click.echo("Error: Scope conflict with existing reservation", err=True)
            click.echo(f"  Task: {res['task']}", err=True)
            click.echo(f"  Agent: {res['agent_id']}", err=True)
            click.echo(f"  Overlapping paths: {overlap}", err=True)
            ctx.exit(1)

    # Create reservation
    task_id = str(uuid4())
    expires_at = now + timedelta(minutes=eta_minutes)

    storage.insert(
        "reservations",
        {
            "id": task_id,
            "task": task_desc,
            "scope_json": json.dumps(scope_paths),
            "agent_id": agent_id,
            "started_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "completed_at": None,
        },
    )

    # Update agent heartbeat
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    click.echo(f"Task claimed: {task_id}")
    click.echo(f"  Agent: {agent_id}")
    click.echo(f"  Task: {task_desc}")
    click.echo(f"  Scope: {scope_paths}")
    click.echo(f"  ETA: {eta_minutes} minutes")
    click.echo(f"  Expires: {expires_at.isoformat()}")


@task.command("heartbeat")
@click.option("--agent-id", required=True, help="Agent identifier")
@click.option("--task-id", required=True, help="Task/reservation ID")
@click.option("--extend", "extend_minutes", type=int, default=30, help="Extend reservation by minutes")
@click.pass_context
def task_heartbeat(ctx: click.Context, agent_id: str, task_id: str, extend_minutes: int) -> None:
    """
    Send heartbeat for an active task, extending the reservation.

    Examples:
        governor task heartbeat --agent-id worker-1 --task-id abc123
        governor task heartbeat --agent-id worker-1 --task-id abc123 --extend 60
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    # Get reservation
    reservation = storage.get_by_id("reservations", task_id)
    if not reservation:
        click.echo(f"Error: Task '{task_id}' not found", err=True)
        ctx.exit(1)

    if reservation["agent_id"] != agent_id:
        click.echo(f"Error: Task '{task_id}' is owned by '{reservation['agent_id']}', not '{agent_id}'", err=True)
        ctx.exit(1)

    if reservation["completed_at"]:
        click.echo(f"Error: Task '{task_id}' is already completed", err=True)
        ctx.exit(1)

    # Extend reservation
    now = datetime.now(timezone.utc)
    new_expires = now + timedelta(minutes=extend_minutes)

    storage.update(
        "reservations",
        "id",
        task_id,
        {"expires_at": new_expires.isoformat()},
    )

    # Update agent heartbeat
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    click.echo("Task heartbeat recorded")
    click.echo(f"  Task: {task_id}")
    click.echo(f"  New expiry: {new_expires.isoformat()}")


@task.command("complete")
@click.option("--agent-id", required=True, help="Agent identifier")
@click.option("--task-id", required=True, help="Task/reservation ID")
@click.option("--proposal-id", help="Associated proposal ID (if any)")
@click.pass_context
def task_complete(ctx: click.Context, agent_id: str, task_id: str, proposal_id: str | None) -> None:
    """
    Mark a task as complete.

    Examples:
        governor task complete --agent-id worker-1 --task-id abc123
        governor task complete --agent-id worker-1 --task-id abc123 --proposal-id def456
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    # Get reservation
    reservation = storage.get_by_id("reservations", task_id)
    if not reservation:
        click.echo(f"Error: Task '{task_id}' not found", err=True)
        ctx.exit(1)

    if reservation["agent_id"] != agent_id:
        click.echo(f"Error: Task '{task_id}' is owned by '{reservation['agent_id']}', not '{agent_id}'", err=True)
        ctx.exit(1)

    if reservation["completed_at"]:
        click.echo(f"Task '{task_id}' was already completed", err=True)
        ctx.exit(1)

    # Mark complete
    now = datetime.now(timezone.utc)

    storage.update(
        "reservations",
        "id",
        task_id,
        {"completed_at": now.isoformat()},
    )

    # Update agent heartbeat
    storage.update("agents", "id", agent_id, {"last_heartbeat": now.isoformat()})

    click.echo(f"Task completed: {task_id}")
    click.echo(f"  Agent: {agent_id}")
    click.echo(f"  Task: {reservation['task']}")
    if proposal_id:
        click.echo(f"  Proposal: {proposal_id}")

    # Show duration
    started = datetime.fromisoformat(reservation["started_at"])
    duration = now - started
    click.echo(f"  Duration: {duration.total_seconds() / 60:.1f} minutes")


@task.command("list")
@click.option("--agent-id", help="Filter by agent")
@click.option("--active-only", is_flag=True, help="Only show active (non-expired, non-completed) tasks")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def task_list(ctx: click.Context, agent_id: str | None, active_only: bool, as_json: bool) -> None:
    """List tasks/reservations."""
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    where = {"agent_id": agent_id} if agent_id else None
    reservations = storage.query("reservations", where=where, order_by="started_at DESC")

    if not reservations:
        if as_json:
            click.echo("[]")
        else:
            click.echo("No tasks found")
        return

    now = datetime.now(timezone.utc)
    displayed = []

    for res in reservations:
        completed = res["completed_at"] is not None
        expires = datetime.fromisoformat(res["expires_at"])
        expired = expires < now

        if active_only and (completed or expired):
            continue

        displayed.append((res, completed, expired))

    if not displayed:
        if as_json:
            click.echo("[]")
        else:
            click.echo("No active tasks found")
        return

    if as_json:
        result = []
        for res, completed, expired in displayed:
            task_status = "completed" if completed else ("expired" if expired else "active")
            result.append({
                "id": res["id"],
                "task": res["task"],
                "agent_id": res["agent_id"],
                "scope": json.loads(res["scope_json"]),
                "status": task_status,
                "started_at": res["started_at"],
                "expires_at": res["expires_at"],
                "completed_at": res["completed_at"],
            })
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(f"Tasks ({len(displayed)}):\n")

    for res, completed, expired in displayed:
        if completed:
            status = "completed"
            icon = "✅"
        elif expired:
            status = "expired"
            icon = "⏰"
        else:
            status = "active"
            icon = "🔄"

        scope = json.loads(res["scope_json"])

        click.echo(f"  {icon} [{status}] {res['id'][:8]}...")
        click.echo(f"     Task: {res['task']}")
        click.echo(f"     Agent: {res['agent_id']}")
        click.echo(f"     Scope: {scope}")

        started = datetime.fromisoformat(res["started_at"])
        if completed:
            completed_at = datetime.fromisoformat(res["completed_at"])
            duration = completed_at - started
            click.echo(f"     Duration: {duration.total_seconds() / 60:.1f} minutes")
        else:
            expires = datetime.fromisoformat(res["expires_at"])
            remaining = (expires - now).total_seconds() / 60
            click.echo(f"     Expires in: {remaining:.1f} minutes")
        click.echo()


@task.command("cancel")
@click.option("--agent-id", required=True, help="Agent identifier")
@click.option("--task-id", required=True, help="Task/reservation ID")
@click.pass_context
def task_cancel(ctx: click.Context, agent_id: str, task_id: str) -> None:
    """
    Cancel a task/reservation without completing it.

    This releases the scope for other agents to claim.
    """
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    # Get reservation
    reservation = storage.get_by_id("reservations", task_id)
    if not reservation:
        click.echo(f"Error: Task '{task_id}' not found", err=True)
        ctx.exit(1)

    if reservation["agent_id"] != agent_id:
        click.echo(f"Error: Task '{task_id}' is owned by '{reservation['agent_id']}', not '{agent_id}'", err=True)
        ctx.exit(1)

    if reservation["completed_at"]:
        click.echo(f"Error: Task '{task_id}' is already completed", err=True)
        ctx.exit(1)

    # Delete reservation (cancel)
    storage.delete("reservations", "id", task_id)

    click.echo(f"Task cancelled: {task_id}")
    click.echo(f"  Scope released: {json.loads(reservation['scope_json'])}")


# Issue/Task command group
@cli.group()
@click.pass_context
def issue(ctx: click.Context) -> None:
    """
    Issue/task management.

    Create, track, and organize tasks with subtasks, dependencies,
    labels, milestones, and time tracking.
    """
    pass


@issue.command("add")
@click.argument("title")
@click.option("--description", "-d", default="", help="Task description")
@click.option("--priority", "-p", type=click.Choice(["critical", "high", "medium", "low", "none"]), default="medium")
@click.option("--parent", help="Parent task ID for subtask")
@click.option("--milestone", "-m", help="Milestone ID or name")
@click.option("--label", "-l", multiple=True, help="Label name(s)")
@click.pass_context
def issue_add(
    ctx: click.Context,
    title: str,
    description: str,
    priority: str,
    parent: str | None,
    milestone: str | None,
    label: tuple[str, ...],
) -> None:
    """
    Create a new task/issue.

    Examples:
        governor issue add "Implement login"
        governor issue add "Fix bug" -p high -l bug -l urgent
        governor issue add "Subtask" --parent abc123
    """
    from .tasks import get_task_manager, Priority

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    # Map priority
    priority_map = {
        "critical": Priority.CRITICAL,
        "high": Priority.HIGH,
        "medium": Priority.MEDIUM,
        "low": Priority.LOW,
        "none": Priority.NONE,
    }

    # Resolve parent
    parent_id = None
    if parent:
        try:
            parent_id = UUID(parent)
        except ValueError:
            click.echo(f"Error: Invalid parent ID: {parent}", err=True)
            ctx.exit(1)

    # Resolve milestone
    milestone_id = None
    if milestone:
        try:
            milestone_id = UUID(milestone)
        except ValueError:
            # Try by name
            milestones = tm.list_milestones(include_closed=True)
            for m in milestones:
                if m.name.lower() == milestone.lower():
                    milestone_id = m.id
                    break
            if not milestone_id:
                click.echo(f"Error: Milestone not found: {milestone}", err=True)
                ctx.exit(1)

    # Resolve labels
    label_ids = []
    for lbl in label:
        existing = tm.get_label_by_name(lbl)
        if existing:
            label_ids.append(existing.id)
        else:
            # Create the label
            new_label = tm.create_label(lbl)
            label_ids.append(new_label.id)
            click.echo(f"Created label: {lbl}")

    task = tm.create_task(
        title=title,
        description=description,
        priority=priority_map[priority],
        parent_id=parent_id,
        milestone_id=milestone_id,
        label_ids=label_ids,
    )

    click.echo(f"Created task: {task.id}")
    click.echo(f"  Title: {task.title}")
    if parent_id:
        click.echo(f"  Parent: {parent_id}")


@issue.command("list")
@click.option("--status", "-s", type=click.Choice(["open", "in_progress", "blocked", "done", "all"]), default="open")
@click.option("--milestone", "-m", help="Filter by milestone")
@click.option("--label", "-l", help="Filter by label")
@click.option("--tree", "-t", is_flag=True, help="Show as tree view")
@click.option("--archived", "-a", is_flag=True, help="Include archived tasks")
@click.pass_context
def issue_list(
    ctx: click.Context,
    status: str,
    milestone: str | None,
    label: str | None,
    tree: bool,
    archived: bool,
) -> None:
    """List tasks/issues."""
    from .tasks import get_task_manager, TaskStatus

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    # Resolve milestone
    milestone_id = None
    if milestone:
        try:
            milestone_id = UUID(milestone)
        except ValueError:
            milestones = tm.list_milestones(include_closed=True)
            for m in milestones:
                if m.name.lower() == milestone.lower():
                    milestone_id = m.id
                    break

    if tree:
        output = tm.format_tree(milestone_id)
        click.echo(output)
        return

    # Resolve label
    label_id = None
    if label:
        lbl = tm.get_label_by_name(label)
        if lbl:
            label_id = lbl.id

    # Get tasks
    status_filter = None if status == "all" else TaskStatus(status)
    tasks = tm.list_tasks(
        status=status_filter,
        milestone_id=milestone_id,
        include_archived=archived,
        label_id=label_id,
    )

    if not tasks:
        click.echo("No tasks found")
        return

    click.echo(f"Tasks ({len(tasks)}):\n")

    status_icons = {
        TaskStatus.OPEN: "○",
        TaskStatus.IN_PROGRESS: "●",
        TaskStatus.BLOCKED: "⊗",
        TaskStatus.DONE: "✓",
        TaskStatus.ARCHIVED: "▣",
    }

    for task in tasks:
        icon = status_icons.get(task.status, "?")
        priority_str = ""
        if task.priority.value <= 2:
            priority_str = f" [{task.priority.name}]"

        labels_str = ""
        if task.label_ids:
            label_names = []
            for lid in task.label_ids:
                lbl = tm.get_label(lid)
                if lbl:
                    label_names.append(lbl.name)
            if label_names:
                labels_str = f" ({', '.join(label_names)})"

        click.echo(f"  {icon} {task.title}{priority_str}{labels_str}")
        click.echo(f"    ID: {task.id}")
        if task.is_subtask:
            click.echo(f"    Parent: {task.parent_id}")
        click.echo()


@issue.command("show")
@click.argument("task_id")
@click.pass_context
def issue_show(ctx: click.Context, task_id: str) -> None:
    """Show detailed task information."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
    except ValueError:
        click.echo(f"Error: Invalid task ID: {task_id}", err=True)
        ctx.exit(1)

    task = tm.get_task(tid)
    if not task:
        click.echo(f"Error: Task not found: {task_id}", err=True)
        ctx.exit(1)

    click.echo(f"Task: {task.title}")
    click.echo(f"  ID: {task.id}")
    click.echo(f"  Status: {task.status.value}")
    click.echo(f"  Priority: {task.priority.name}")

    if task.description:
        click.echo(f"\n  Description: {task.description}")

    if task.parent_id:
        parent = tm.get_task(task.parent_id)
        click.echo(f"\n  Parent: {parent.title if parent else task.parent_id}")

    subtasks = tm.get_subtasks(task.id)
    if subtasks:
        click.echo(f"\n  Subtasks ({len(subtasks)}):")
        for st in subtasks:
            click.echo(f"    - {st.title} [{st.status.value}]")

    if task.label_ids:
        labels = [tm.get_label(lid) for lid in task.label_ids]
        click.echo(f"\n  Labels: {', '.join(l.name for l in labels if l)}")

    if task.milestone_id:
        milestone = tm.get_milestone(task.milestone_id)
        click.echo(f"  Milestone: {milestone.name if milestone else task.milestone_id}")

    blocking = tm.get_blocking_tasks(task.id)
    if blocking:
        click.echo(f"\n  Blocked by ({len(blocking)}):")
        for bt in blocking:
            click.echo(f"    - {bt.title}")

    dependents = tm.get_dependent_tasks(task.id)
    if dependents:
        click.echo(f"\n  Blocking ({len(dependents)}):")
        for dt in dependents:
            click.echo(f"    - {dt.title}")

    related = tm.get_related_tasks(task.id)
    if related:
        click.echo(f"\n  Related ({len(related)}):")
        for rt in related:
            click.echo(f"    - {rt.title}")

    # Time tracking
    total_time = tm.get_total_time(task.id)
    if total_time.total_seconds() > 0:
        hours = total_time.total_seconds() / 3600
        click.echo(f"\n  Time tracked: {hours:.1f}h")

    running = tm.get_running_timer(task.id)
    if running:
        click.echo(f"  Timer running: {running.duration}")

    click.echo(f"\n  Created: {task.created_at.isoformat()}")
    click.echo(f"  Updated: {task.updated_at.isoformat()}")
    if task.closed_at:
        click.echo(f"  Closed: {task.closed_at.isoformat()}")


@issue.command("start")
@click.argument("task_id")
@click.pass_context
def issue_start(ctx: click.Context, task_id: str) -> None:
    """Start working on a task."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
    except ValueError:
        click.echo(f"Error: Invalid task ID: {task_id}", err=True)
        ctx.exit(1)

    task = tm.start_task(tid)
    if not task:
        click.echo(f"Error: Task not found: {task_id}", err=True)
        ctx.exit(1)

    click.echo(f"Started: {task.title}")
    click.echo(f"  Status: {task.status.value}")

    if task.status.value == "blocked":
        blocking = tm.get_blocking_tasks(task.id)
        click.echo("\n  Blocked by:")
        for bt in blocking:
            click.echo(f"    - {bt.title}")


@issue.command("done")
@click.argument("task_id")
@click.pass_context
def issue_done(ctx: click.Context, task_id: str) -> None:
    """Mark a task as done."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
    except ValueError:
        click.echo(f"Error: Invalid task ID: {task_id}", err=True)
        ctx.exit(1)

    task = tm.complete_task(tid)
    if not task:
        click.echo(f"Error: Task not found: {task_id}", err=True)
        ctx.exit(1)

    click.echo(f"Completed: {task.title}")

    # Check if this unblocked anything
    dependents = tm.get_dependent_tasks(task.id)
    unblocked = [d for d in dependents if d.status.value == "open"]
    if unblocked:
        click.echo("\n  Unblocked:")
        for t in unblocked:
            click.echo(f"    - {t.title}")


@issue.command("block")
@click.argument("task_id")
@click.argument("blocked_by_id")
@click.pass_context
def issue_block(ctx: click.Context, task_id: str, blocked_by_id: str) -> None:
    """Add a blocking dependency."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
        bid = UUID(blocked_by_id)
    except ValueError as e:
        click.echo(f"Error: Invalid ID: {e}", err=True)
        ctx.exit(1)

    success = tm.add_dependency(tid, bid)
    if success:
        click.echo(f"Added dependency: {task_id} is blocked by {blocked_by_id}")
    else:
        click.echo("Error: Could not add dependency (may create circular dependency)", err=True)
        ctx.exit(1)


@issue.command("unblock")
@click.argument("task_id")
@click.argument("blocked_by_id")
@click.pass_context
def issue_unblock(ctx: click.Context, task_id: str, blocked_by_id: str) -> None:
    """Remove a blocking dependency."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
        bid = UUID(blocked_by_id)
    except ValueError as e:
        click.echo(f"Error: Invalid ID: {e}", err=True)
        ctx.exit(1)

    tm.remove_dependency(tid, bid)
    click.echo(f"Removed dependency: {task_id} is no longer blocked by {blocked_by_id}")


@issue.command("link")
@click.argument("task_id_1")
@click.argument("task_id_2")
@click.pass_context
def issue_link(ctx: click.Context, task_id_1: str, task_id_2: str) -> None:
    """Link two related tasks."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid1 = UUID(task_id_1)
        tid2 = UUID(task_id_2)
    except ValueError as e:
        click.echo(f"Error: Invalid ID: {e}", err=True)
        ctx.exit(1)

    success = tm.link_tasks(tid1, tid2)
    if success:
        click.echo(f"Linked tasks: {task_id_1} <-> {task_id_2}")
    else:
        click.echo("Error: Could not link tasks", err=True)
        ctx.exit(1)


@issue.command("archive")
@click.option("--older-than", "-o", type=int, default=30, help="Archive done tasks older than N days")
@click.option("--task-id", "-t", help="Archive specific task")
@click.pass_context
def issue_archive(ctx: click.Context, older_than: int, task_id: str | None) -> None:
    """Archive completed tasks."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    if task_id:
        try:
            tid = UUID(task_id)
        except ValueError:
            click.echo(f"Error: Invalid task ID: {task_id}", err=True)
            ctx.exit(1)

        task = tm.archive_task(tid)
        if task:
            click.echo(f"Archived: {task.title}")
        else:
            click.echo(f"Error: Task not found: {task_id}", err=True)
            ctx.exit(1)
    else:
        count = tm.archive_done_tasks(older_than)
        click.echo(f"Archived {count} task(s) completed more than {older_than} days ago")


# Label commands
@issue.group()
@click.pass_context
def label(ctx: click.Context) -> None:
    """Label management."""
    pass


@label.command("add")
@click.argument("name")
@click.option("--color", "-c", default="#808080", help="Hex color (e.g., #ff0000)")
@click.option("--description", "-d", default="", help="Label description")
@click.pass_context
def label_add(ctx: click.Context, name: str, color: str, description: str) -> None:
    """Create a new label."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    label = tm.create_label(name, color, description)
    click.echo(f"Created label: {label.name}")
    click.echo(f"  ID: {label.id}")
    click.echo(f"  Color: {label.color}")


@label.command("list")
@click.pass_context
def label_list(ctx: click.Context) -> None:
    """List all labels."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    labels = tm.list_labels()
    if not labels:
        click.echo("No labels defined")
        return

    click.echo(f"Labels ({len(labels)}):\n")
    for lbl in labels:
        click.echo(f"  {lbl.color} {lbl.name}")
        if lbl.description:
            click.echo(f"    {lbl.description}")


# Milestone commands
@issue.group()
@click.pass_context
def milestone(ctx: click.Context) -> None:
    """Milestone management."""
    pass


@milestone.command("add")
@click.argument("name")
@click.option("--description", "-d", default="", help="Milestone description")
@click.option("--due", help="Due date (YYYY-MM-DD)")
@click.pass_context
def milestone_add(ctx: click.Context, name: str, description: str, due: str | None) -> None:
    """Create a new milestone."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    due_date = None
    if due:
        try:
            due_date = datetime.strptime(due, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            click.echo(f"Error: Invalid date format: {due}", err=True)
            ctx.exit(1)

    milestone = tm.create_milestone(name, description, due_date)
    click.echo(f"Created milestone: {milestone.name}")
    click.echo(f"  ID: {milestone.id}")
    if due_date:
        click.echo(f"  Due: {due_date.date()}")


@milestone.command("list")
@click.option("--closed", "-c", is_flag=True, help="Include closed milestones")
@click.pass_context
def milestone_list(ctx: click.Context, closed: bool) -> None:
    """List milestones with progress."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    milestones = tm.list_milestones(include_closed=closed)
    if not milestones:
        click.echo("No milestones defined")
        return

    click.echo(f"Milestones ({len(milestones)}):\n")
    for m in milestones:
        progress = tm.get_milestone_progress(m.id)
        status = "CLOSED" if m.is_closed else "OPEN"

        click.echo(f"  [{status}] {m.name}")
        click.echo(f"    ID: {m.id}")
        if m.due_date:
            click.echo(f"    Due: {m.due_date.date()}")
        click.echo(f"    Progress: {progress['done']}/{progress['total']} ({progress['percent_complete']}%)")
        if progress['blocked'] > 0:
            click.echo(f"    Blocked: {progress['blocked']}")
        click.echo()


@milestone.command("close")
@click.argument("milestone_id")
@click.pass_context
def milestone_close(ctx: click.Context, milestone_id: str) -> None:
    """Close a milestone."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        mid = UUID(milestone_id)
    except ValueError:
        click.echo(f"Error: Invalid milestone ID: {milestone_id}", err=True)
        ctx.exit(1)

    m = tm.close_milestone(mid)
    if m:
        click.echo(f"Closed milestone: {m.name}")
    else:
        click.echo(f"Error: Milestone not found: {milestone_id}", err=True)
        ctx.exit(1)


# Time tracking commands
@issue.group()
@click.pass_context
def timer(ctx: click.Context) -> None:
    """Time tracking."""
    pass


@timer.command("start")
@click.argument("task_id")
@click.option("--note", "-n", default="", help="Note for this time entry")
@click.pass_context
def timer_start(ctx: click.Context, task_id: str, note: str) -> None:
    """Start a timer for a task."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
    except ValueError:
        click.echo(f"Error: Invalid task ID: {task_id}", err=True)
        ctx.exit(1)

    entry = tm.start_timer(tid, note)
    task = tm.get_task(tid)
    click.echo(f"Timer started for: {task.title if task else task_id}")
    click.echo(f"  Entry ID: {entry.id}")


@timer.command("stop")
@click.argument("task_id")
@click.pass_context
def timer_stop(ctx: click.Context, task_id: str) -> None:
    """Stop the timer for a task."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    try:
        tid = UUID(task_id)
    except ValueError:
        click.echo(f"Error: Invalid task ID: {task_id}", err=True)
        ctx.exit(1)

    entry = tm.stop_timer(tid)
    if entry:
        hours = entry.duration.total_seconds() / 3600
        click.echo(f"Timer stopped. Duration: {hours:.2f}h")
    else:
        click.echo("No running timer for this task")


@timer.command("status")
@click.pass_context
def timer_status(ctx: click.Context) -> None:
    """Show all running timers."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    # Find all running timers by checking active tasks
    tasks = tm.list_tasks()
    running = []
    for task in tasks:
        entry = tm.get_running_timer(task.id)
        if entry:
            running.append((task, entry))

    if not running:
        click.echo("No running timers")
        return

    click.echo(f"Running timers ({len(running)}):\n")
    for task, entry in running:
        hours = entry.duration.total_seconds() / 3600
        click.echo(f"  {task.title}")
        click.echo(f"    Running: {hours:.2f}h")
        if entry.note:
            click.echo(f"    Note: {entry.note}")
        click.echo()


# Session commands
@issue.group()
@click.pass_context
def session(ctx: click.Context) -> None:
    """Session management with handoff notes."""
    pass


@session.command("start")
@click.option("--agent-id", "-a", help="Agent identifier")
@click.pass_context
def session_start(ctx: click.Context, agent_id: str | None) -> None:
    """Start a new work session."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    # Check for existing active session
    existing = tm.get_active_session(agent_id)
    if existing:
        click.echo(f"Warning: Active session already exists: {existing.id}")
        click.echo("End it first with 'governor issue session end'")
        return

    session = tm.start_session(agent_id)
    click.echo(f"Session started: {session.id}")
    click.echo(f"  Started: {session.started_at.isoformat()}")

    # Show handoff from previous session
    last = tm.get_last_session(agent_id)
    if last:
        click.echo("\n--- Previous Session Handoff ---")
        click.echo(tm.format_handoff(last))


@session.command("end")
@click.option("--summary", "-s", default="", help="Session summary")
@click.option("--next", "next_steps", multiple=True, help="Next step(s)")
@click.option("--blocker", "-b", multiple=True, help="Blocker(s)")
@click.option("--notes", "-n", default="", help="Additional notes")
@click.pass_context
def session_end(
    ctx: click.Context,
    summary: str,
    next_steps: tuple[str, ...],
    blocker: tuple[str, ...],
    notes: str,
) -> None:
    """End the current session with handoff notes."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    session = tm.get_active_session()
    if not session:
        click.echo("No active session")
        return

    session = tm.end_session(
        session.id,
        summary=summary,
        next_steps=list(next_steps),
        blockers=list(blocker),
        notes=notes,
    )

    click.echo(f"Session ended: {session.id}")
    click.echo(f"  Duration: {session.duration}")

    if summary:
        click.echo(f"\n  Summary: {summary}")
    if next_steps:
        click.echo("\n  Next steps:")
        for step in next_steps:
            click.echo(f"    - {step}")
    if blocker:
        click.echo("\n  Blockers:")
        for b in blocker:
            click.echo(f"    - {b}")


@session.command("handoff")
@click.option("--agent-id", "-a", help="Agent identifier")
@click.pass_context
def session_handoff(ctx: click.Context, agent_id: str | None) -> None:
    """Show the most recent handoff notes."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    handoff = tm.format_handoff()
    click.echo(handoff)


@session.command("list")
@click.option("--limit", "-n", type=int, default=10, help="Number of sessions to show")
@click.pass_context
def session_list(ctx: click.Context, limit: int) -> None:
    """List recent sessions."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    sessions = tm.list_sessions(limit)
    if not sessions:
        click.echo("No sessions found")
        return

    click.echo(f"Sessions ({len(sessions)}):\n")
    for s in sessions:
        status = "ACTIVE" if s.is_active else "ended"
        click.echo(f"  [{status}] {s.id}")
        click.echo(f"    Started: {s.started_at.isoformat()}")
        if s.ended_at:
            click.echo(f"    Ended: {s.ended_at.isoformat()}")
            click.echo(f"    Duration: {s.duration}")
        if s.summary:
            click.echo(f"    Summary: {s.summary[:60]}...")
        click.echo()


# Recommendation command
@issue.command("next")
@click.option("--agent-id", "-a", help="Agent identifier")
@click.pass_context
def issue_next(ctx: click.Context, agent_id: str | None) -> None:
    """
    Recommend what to work on next.

    Considers:
    - Task priority
    - Milestone deadlines
    - Blocking relationships
    - Recent activity
    """
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    recommendations = tm.recommend_next(agent_id)

    if not recommendations:
        click.echo("No tasks to recommend. All done!")
        return

    click.echo("Recommended tasks:\n")
    for i, task in enumerate(recommendations, 1):
        priority_str = f"[{task.priority.name}]" if task.priority.value <= 2 else ""

        reason = []
        if task.status.value == "in_progress":
            reason.append("in progress")

        if task.milestone_id:
            milestone = tm.get_milestone(task.milestone_id)
            if milestone and milestone.due_date:
                days = (milestone.due_date - datetime.now(timezone.utc)).days
                if days < 7:
                    reason.append(f"due in {days}d")

        dependents = tm.get_dependent_tasks(task.id)
        blocked_count = sum(1 for d in dependents if d.status.value == "blocked")
        if blocked_count > 0:
            reason.append(f"unblocks {blocked_count}")

        reason_str = f" ({', '.join(reason)})" if reason else ""

        click.echo(f"  {i}. {task.title} {priority_str}{reason_str}")
        click.echo(f"     ID: {task.id}")
        click.echo()


# Export/Import commands
@issue.command("export")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.pass_context
def issue_export(ctx: click.Context, output: str | None) -> None:
    """Export all task data to JSON."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    data = tm.export_json()
    json_str = json.dumps(data, indent=2)

    if output:
        Path(output).write_text(json_str)
        click.echo(f"Exported to: {output}")
    else:
        click.echo(json_str)


@issue.command("import")
@click.argument("file", type=click.Path(exists=True))
@click.option("--replace", "-r", is_flag=True, help="Replace existing data (default: merge)")
@click.pass_context
def issue_import(ctx: click.Context, file: str, replace: bool) -> None:
    """Import task data from JSON."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    data = json.loads(Path(file).read_text())
    counts = tm.import_json(data, merge=not replace)

    click.echo("Import complete:")
    click.echo(f"  Tasks: {counts['tasks']}")
    click.echo(f"  Labels: {counts['labels']}")
    click.echo(f"  Milestones: {counts['milestones']}")
    click.echo(f"  Sessions: {counts['sessions']}")


# Tree view command
@issue.command("tree")
@click.option("--milestone", "-m", help="Filter by milestone")
@click.pass_context
def issue_tree(ctx: click.Context, milestone: str | None) -> None:
    """Display tasks as a tree."""
    from .tasks import get_task_manager

    gov_dir = ensure_initialized(ctx)
    tm = get_task_manager(gov_dir)

    milestone_id = None
    if milestone:
        try:
            milestone_id = UUID(milestone)
        except ValueError:
            milestones = tm.list_milestones(include_closed=True)
            for m in milestones:
                if m.name.lower() == milestone.lower():
                    milestone_id = m.id
                    break

    output = tm.format_tree(milestone_id)
    click.echo(output)


# Graph command group (audit surface)
@cli.group()
@click.pass_context
def graph(ctx: click.Context) -> None:
    """
    Audit graph operations.

    Maltego-style graph of governor state for auditing:
    - Claims -> Evidence edges (provenance)
    - Actions -> Preconditions (what had to be true)
    - Sessions -> Handoffs -> Drift (state changes)
    - Actors -> Authority scope (who can assert what)
    """
    pass


@graph.command("export")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "cytoscape", "graphviz", "obsidian"]), default="json")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.pass_context
def graph_export(ctx: click.Context, fmt: str, output: str | None) -> None:
    """
    Export the audit graph.

    Formats:
    - json: Generic JSON (nodes + edges)
    - cytoscape: Cytoscape.js compatible
    - graphviz: DOT format (render with `dot -Tpng`)
    - obsidian: Obsidian Canvas format (.canvas)

    Examples:
        governor graph export -f json -o audit.json
        governor graph export -f graphviz | dot -Tpng -o graph.png
        governor graph export -f obsidian -o audit.canvas
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    if fmt == "json":
        content = graph.to_json()
    elif fmt == "cytoscape":
        content = json.dumps(graph.to_cytoscape(), indent=2)
    elif fmt == "graphviz":
        content = graph.to_graphviz()
    elif fmt == "obsidian":
        content = json.dumps(graph.to_obsidian_canvas(), indent=2)
    else:
        content = graph.to_json()

    if output:
        Path(output).write_text(content)
        click.echo(f"Exported to: {output}")
    else:
        click.echo(content)


@graph.command("stats")
@click.pass_context
def graph_stats(ctx: click.Context) -> None:
    """Show graph statistics."""
    from .graph import build_graph, NodeType, EdgeType

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    # Count nodes by type
    node_counts: dict[str, int] = {}
    for node in graph.nodes.values():
        type_name = node.type.value
        node_counts[type_name] = node_counts.get(type_name, 0) + 1

    # Count edges by type
    edge_counts: dict[str, int] = {}
    for edge in graph.edges:
        type_name = edge.type.value
        edge_counts[type_name] = edge_counts.get(type_name, 0) + 1

    click.echo("Audit Graph Statistics\n")
    click.echo(f"Total nodes: {len(graph.nodes)}")
    click.echo(f"Total edges: {len(graph.edges)}")

    if node_counts:
        click.echo("\nNodes by type:")
        for type_name, count in sorted(node_counts.items()):
            click.echo(f"  {type_name}: {count}")

    if edge_counts:
        click.echo("\nEdges by type:")
        for type_name, count in sorted(edge_counts.items()):
            click.echo(f"  {type_name}: {count}")


@graph.command("weak")
@click.option("--threshold", "-t", type=int, default=1, help="Minimum receipts required")
@click.pass_context
def graph_weak(ctx: click.Context, threshold: int) -> None:
    """
    Transform: Find proposals with weak grounding.

    Shows proposals with fewer than threshold supporting receipts.
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    weak = graph.weak_grounding(threshold)

    if not weak:
        click.echo(f"No proposals with fewer than {threshold} receipt(s)")
        return

    click.echo(f"Proposals with weak grounding ({len(weak)}):\n")
    for node in weak:
        click.echo(f"  {node.label}")
        click.echo(f"    State: {node.properties.get('state', 'unknown')}")
        if node.timestamp:
            click.echo(f"    Created: {node.timestamp.isoformat()}")
        click.echo()


@graph.command("unverified")
@click.pass_context
def graph_unverified(ctx: click.Context) -> None:
    """
    Transform: Show claims lacking evidence.

    Lists claims that have no supporting receipts.
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    unverified = graph.claims_without_evidence()

    if not unverified:
        click.echo("All claims have supporting evidence")
        return

    click.echo(f"Claims without evidence ({len(unverified)}):\n")
    for node in unverified:
        click.echo(f"  {node.label}")
        if node.properties:
            for key, value in node.properties.items():
                if key not in ("description",) and value:
                    click.echo(f"    {key}: {value}")
        click.echo()


@graph.command("rejections")
@click.pass_context
def graph_rejections(ctx: click.Context) -> None:
    """
    Transform: Analyze rejection patterns.

    Groups rejections by root cause to identify common failure modes.
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    patterns = graph.rejection_patterns()

    if not patterns:
        click.echo("No rejections found")
        return

    click.echo("Rejection patterns:\n")
    for pattern, proposals in sorted(patterns.items(), key=lambda x: -len(x[1])):
        click.echo(f"  {pattern}: {len(proposals)} rejection(s)")
        for proposal in proposals[:3]:
            click.echo(f"    - {proposal.label}")
        if len(proposals) > 3:
            click.echo(f"    ... and {len(proposals) - 3} more")
        click.echo()


@graph.command("drift")
@click.pass_context
def graph_drift(ctx: click.Context) -> None:
    """
    Transform: Analyze session drift.

    Shows contradictions and forgotten items across sessions.
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    drift_events = graph.session_drift()

    if not drift_events:
        click.echo("No drift detected across sessions")
        return

    click.echo(f"Session drift events ({len(drift_events)}):\n")
    for event in drift_events:
        click.echo(f"  {event['type'].upper()}")
        click.echo(f"    After session: {event['previous_session'][:8]}...")
        click.echo(f"    Count: {event['count']}")
        for detail in event.get("details", [])[:3]:
            click.echo(f"      - {detail}")
        click.echo()


@graph.command("authority")
@click.pass_context
def graph_authority(ctx: click.Context) -> None:
    """
    Transform: Show actor authority map.

    Displays what each agent has done (proposals, decisions, tasks).
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    authority = graph.actor_authority_map()

    if not authority:
        click.echo("No agents found")
        return

    click.echo("Agent authority map:\n")
    for agent_id, counts in sorted(authority.items()):
        click.echo(f"  {agent_id}:")
        for action, count in counts.items():
            if count > 0:
                click.echo(f"    {action}: {count}")
        click.echo()


@graph.command("collapse")
@click.option("--title", "-t", default="Summary", help="Title for the summary")
@click.option("--task", help="Collapse subgraph for a specific task")
@click.option("--decision", help="Collapse decision chain for a specific decision")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.option("--format", "-f", "fmt", type=click.Choice(["json", "markdown"]), default="markdown")
@click.option("--notes", "-n", default="", help="Additional notes to include")
@click.pass_context
def graph_collapse(
    ctx: click.Context,
    title: str,
    task: str | None,
    decision: str | None,
    output: str | None,
    fmt: str,
    notes: str,
) -> None:
    """
    Transform: Collapse a subgraph into a stable summary object.

    Creates a reusable insight artifact that captures:
    - What was decided
    - What evidence supported it
    - What contradictions were resolved
    - Key invariants established

    Examples:
        governor graph collapse --title "Auth Implementation"
        governor graph collapse --task <task-id> --title "Task Summary"
        governor graph collapse --decision <decision-id> --title "Decision Chain"
        governor graph collapse -f json -o summary.json
    """
    from .graph import build_graph

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    # Determine what to collapse
    subgraph = None

    if task:
        subgraph = graph.subgraph_for_task(f"task:{task}" if not task.startswith("task:") else task)
        if not subgraph.nodes:
            click.echo(f"Error: Task not found: {task}", err=True)
            ctx.exit(1)

    if decision:
        decision_id = f"decision:{decision}" if not decision.startswith("decision:") else decision
        subgraph = graph.expand_dependency_chain(decision_id)
        if not subgraph.nodes:
            click.echo(f"Error: Decision not found: {decision}", err=True)
            ctx.exit(1)

    # Create summary
    summary = graph.collapse(subgraph, title=title, notes=notes)

    # Output
    if fmt == "markdown":
        content = summary.to_markdown()
    else:
        content = json.dumps(summary.to_dict(), indent=2)

    if output:
        Path(output).write_text(content)
        click.echo(f"Summary written to: {output}")
        click.echo(f"  Nodes collapsed: {len(summary.node_ids)}")
        click.echo(f"  Decisions: {len(summary.decisions)}")
        click.echo(f"  Invariants: {len(summary.invariants)}")
    else:
        click.echo(content)


@graph.command("view")
@click.option("--port", "-p", type=int, default=8765, help="Port for local server")
@click.pass_context
def graph_view(ctx: click.Context, port: int) -> None:
    """
    Launch interactive graph viewer in browser.

    Starts a local server and opens the graph visualization.
    """
    from .graph import build_graph
    import http.server
    import socketserver
    import webbrowser
    import threading

    gov_dir = ensure_initialized(ctx)
    graph = build_graph(gov_dir)

    # Generate HTML with embedded graph data
    html_content = generate_viewer_html(graph)

    # Write to temp file
    viewer_path = gov_dir / "viewer.html"
    viewer_path.write_text(html_content)

    click.echo(f"Starting viewer at http://localhost:{port}")
    click.echo("Press Ctrl+C to stop")

    # Simple HTTP server
    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(gov_dir), **kwargs)

        def log_message(self, format, *args):
            pass  # Suppress logging

    try:
        with socketserver.TCPServer(("", port), Handler) as httpd:
            webbrowser.open(f"http://localhost:{port}/viewer.html")
            httpd.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nStopped viewer")
    finally:
        viewer_path.unlink(missing_ok=True)


def generate_viewer_html(graph) -> str:
    """Generate an interactive HTML viewer using vis.js."""
    graph_data = graph.to_cytoscape()

    # Convert to vis.js format
    vis_nodes = []
    vis_edges = []

    colors = {
        "proposal": "#e3f2fd",
        "claim": "#fff3e0",
        "receipt": "#e8f5e9",
        "decision": "#fce4ec",
        "task": "#f3e5f5",
        "session": "#e0f7fa",
        "agent": "#fff8e1",
        "rejection": "#ffebee",
        "fact": "#f1f8e9",
        "file": "#eceff1",
        "milestone": "#e8eaf6",
    }

    for element in graph_data["elements"]:
        data = element["data"]
        if "source" in data:
            # Edge
            vis_edges.append({
                "from": data["source"],
                "to": data["target"],
                "label": data.get("type", ""),
                "arrows": "to",
            })
        else:
            # Node
            node_type = data.get("type", "unknown")
            vis_nodes.append({
                "id": data["id"],
                "label": data.get("label", data["id"])[:30],
                "title": data.get("label", data["id"]),
                "color": colors.get(node_type, "#ffffff"),
                "group": node_type,
            })

    return f'''<!DOCTYPE html>
<html>
<head>
    <title>Governor Audit Graph</title>
    <script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
    <style>
        body {{ margin: 0; padding: 0; font-family: system-ui, sans-serif; }}
        #graph {{ width: 100vw; height: 100vh; }}
        #legend {{
            position: absolute;
            top: 10px;
            right: 10px;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            font-size: 12px;
        }}
        .legend-item {{
            display: flex;
            align-items: center;
            margin: 5px 0;
        }}
        .legend-color {{
            width: 20px;
            height: 20px;
            margin-right: 8px;
            border-radius: 3px;
        }}
        #info {{
            position: absolute;
            bottom: 10px;
            left: 10px;
            background: white;
            padding: 10px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            max-width: 400px;
            display: none;
        }}
    </style>
</head>
<body>
    <div id="graph"></div>
    <div id="legend">
        <strong>Node Types</strong>
        {"".join(f'<div class="legend-item"><div class="legend-color" style="background:{color}"></div>{name}</div>' for name, color in colors.items())}
    </div>
    <div id="info"></div>
    <script>
        var nodes = new vis.DataSet({json.dumps(vis_nodes)});
        var edges = new vis.DataSet({json.dumps(vis_edges)});

        var container = document.getElementById('graph');
        var data = {{ nodes: nodes, edges: edges }};
        var options = {{
            physics: {{
                stabilization: {{ iterations: 100 }},
                barnesHut: {{ gravitationalConstant: -2000 }}
            }},
            interaction: {{ hover: true }},
            nodes: {{
                shape: 'box',
                font: {{ size: 12 }}
            }},
            edges: {{
                font: {{ size: 10, align: 'middle' }},
                smooth: {{ type: 'cubicBezier' }}
            }}
        }};

        var network = new vis.Network(container, data, options);

        network.on('click', function(params) {{
            var info = document.getElementById('info');
            if (params.nodes.length > 0) {{
                var nodeId = params.nodes[0];
                var node = nodes.get(nodeId);
                info.innerHTML = '<strong>' + node.group + '</strong><br>' + node.title;
                info.style.display = 'block';
            }} else {{
                info.style.display = 'none';
            }}
        }});
    </script>
</body>
</html>'''


# Ops (SRE/Operations) command group
@cli.group()
@click.pass_context
def ops(ctx: click.Context) -> None:
    """
    SRE/Operations constraint system.

    Mechanical verification for operational claims:
    - Policy packs (installable constraints per environment)
    - Claim gating with proof types
    - Incident timeline integrity
    - Change management enforcement

    The keystone: No claim without proof.
    """
    pass


@ops.command("init")
@click.option("--pack", "-p", multiple=True, help="Built-in policy pack to install")
@click.pass_context
def ops_init(ctx: click.Context, pack: tuple[str, ...]) -> None:
    """
    Initialize ops governor in the current directory.

    Creates .governor/ops/ directory structure and optionally
    installs built-in policy packs.

    Examples:
        governor ops init
        governor ops init -p deploy/safe_rollout
        governor ops init -p incident/strict -p change_mgmt/basic
    """
    from ops_governor import PolicyRegistry, install_builtin_pack, BUILTIN_PACKS

    root = Path(ctx.obj["root"])
    gov_dir = root / ".governor"

    if not gov_dir.exists():
        click.echo("Error: Governor not initialized. Run 'governor init' first.", err=True)
        ctx.exit(1)

    ops_dir = gov_dir / "ops"
    if ops_dir.exists():
        click.echo(f"Ops governor already initialized at {ops_dir}")
    else:
        ops_dir.mkdir()
        (ops_dir / "policies").mkdir()
        (ops_dir / "claims").mkdir()
        (ops_dir / "incidents").mkdir()
        click.echo(f"Initialized ops governor at {ops_dir}")

    # Install requested packs
    registry = PolicyRegistry(ops_dir)
    for pack_name in pack:
        if pack_name in BUILTIN_PACKS:
            result = install_builtin_pack(registry, pack_name)
            if result:
                click.echo(f"Installed policy pack: {pack_name}")
            else:
                click.echo(f"Failed to install: {pack_name}", err=True)
        else:
            click.echo(f"Unknown pack: {pack_name}. Available: {list(BUILTIN_PACKS.keys())}", err=True)


@ops.command("policy")
@click.argument("action", type=click.Choice(["list", "show"]))
@click.argument("name", required=False)
@click.pass_context
def ops_policy(ctx: click.Context, action: str, name: str | None) -> None:
    """
    Manage policy packs.

    Examples:
        governor ops policy list
        governor ops policy show deploy/safe_rollout
    """
    from ops_governor import PolicyRegistry, BUILTIN_PACKS

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized. Run 'governor ops init' first.", err=True)
        ctx.exit(1)

    registry = PolicyRegistry(ops_dir)

    if action == "list":
        installed = registry.list_installed()
        click.echo(f"Installed policy packs ({len(installed)}):")
        for pack in installed:
            status = "enabled" if pack.enabled else "disabled"
            click.echo(f"  [{status}] {pack.name}: {pack.description}")

        click.echo("\nAvailable built-in packs:")
        for pack_name in BUILTIN_PACKS:
            click.echo(f"  {pack_name}")

    elif action == "show":
        if not name:
            click.echo("Error: Pack name required for 'show'", err=True)
            ctx.exit(1)

        pack = registry.get_pack(name)
        if not pack:
            click.echo(f"Pack not found: {name}", err=True)
            ctx.exit(1)

        click.echo(f"Policy Pack: {pack.name}")
        click.echo(f"  Version: {pack.version}")
        click.echo(f"  Description: {pack.description}")
        click.echo(f"  Enabled: {pack.enabled}")
        click.echo(f"\n  Claims ({len(pack.claims)}):")
        for claim in pack.claims:
            click.echo(f"    - {claim.id}: {claim.description}")
            click.echo(f"      Required proofs: {[r.proof_type.value for r in claim.requirements]}")


@ops.command("claim")
@click.argument("action", type=click.Choice(["verify", "list"]))
@click.argument("claim_id", required=False)
@click.option("--evidence", "-e", multiple=True, help="Evidence in type:value format")
@click.pass_context
def ops_claim(ctx: click.Context, action: str, claim_id: str | None, evidence: tuple[str, ...]) -> None:
    """
    Manage operational claims.

    Examples:
        governor ops claim list
        governor ops claim verify deploy:pre_checks -e healthcheck:passed -e rollback_plan:exists
    """
    from ops_governor import PolicyRegistry, ClaimVerifier, ProofCollector, ProofType

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized. Run 'governor ops init' first.", err=True)
        ctx.exit(1)

    registry = PolicyRegistry(ops_dir)

    if action == "list":
        # List all available claims from installed packs
        packs = registry.list_installed()
        if not packs:
            click.echo("No policy packs installed")
            return

        click.echo("Available claims:\n")
        for pack in packs:
            if not pack.enabled:
                continue
            click.echo(f"  {pack.name}:")
            for claim in pack.claims:
                click.echo(f"    {claim.id}: {claim.description}")

    elif action == "verify":
        if not claim_id:
            click.echo("Error: claim_id required for 'verify'", err=True)
            ctx.exit(1)

        # Find the claim definition
        claim_def = None
        for pack in registry.list_installed():
            if not pack.enabled:
                continue
            for claim in pack.claims:
                if claim.id == claim_id:
                    claim_def = claim
                    break
            if claim_def:
                break

        if not claim_def:
            click.echo(f"Claim not found: {claim_id}", err=True)
            ctx.exit(1)

        # Parse evidence
        collector = ProofCollector()
        for ev in evidence:
            if ":" not in ev:
                click.echo(f"Invalid evidence format: {ev} (use type:value)", err=True)
                ctx.exit(1)
            proof_type_str, value = ev.split(":", 1)
            try:
                proof_type = ProofType(proof_type_str)
            except ValueError:
                click.echo(f"Unknown proof type: {proof_type_str}", err=True)
                click.echo(f"Valid types: {[pt.value for pt in ProofType]}")
                ctx.exit(1)
            collector.add_evidence(proof_type, {"value": value})

        # Verify
        verifier = ClaimVerifier(registry)
        result = verifier.verify_claim(claim_def, collector.get_evidence())

        if result["verified"]:
            click.echo(f"VERIFIED: {claim_id}")
            click.echo(f"  All {len(claim_def.requirements)} requirement(s) satisfied")
        else:
            click.echo(f"FAILED: {claim_id}")
            for failure in result.get("failures", []):
                click.echo(f"  Missing: {failure}")


@ops.command("incident")
@click.argument("action", type=click.Choice(["create", "status", "list"]))
@click.option("--id", "incident_id", help="Incident ID")
@click.option("--severity", "-s", type=click.Choice(["sev1", "sev2", "sev3", "sev4", "sev5"]), default="sev3")
@click.option("--title", "-t", help="Incident title")
@click.option("--status", "new_status", type=click.Choice(["detected", "acknowledged", "investigating", "mitigating", "resolved", "closed"]))
@click.option("--message", "-m", help="Status message")
@click.pass_context
def ops_incident(
    ctx: click.Context,
    action: str,
    incident_id: str | None,
    severity: str,
    title: str | None,
    new_status: str | None,
    message: str | None,
) -> None:
    """
    Manage incidents.

    Examples:
        governor ops incident create -s sev2 -t "Database latency spike"
        governor ops incident status --id INC-001 --status investigating -m "Checking query patterns"
        governor ops incident list
    """
    from ops_governor import Incident, IncidentSeverity, IncidentStatus, IncidentEvent
    from datetime import datetime, timezone

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"
    incidents_dir = ops_dir / "incidents"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized. Run 'governor ops init' first.", err=True)
        ctx.exit(1)

    if action == "create":
        if not title:
            click.echo("Error: --title required for create", err=True)
            ctx.exit(1)

        # Generate incident ID
        existing = list(incidents_dir.glob("INC-*.json"))
        next_num = len(existing) + 1
        inc_id = f"INC-{next_num:03d}"

        sev_map = {
            "sev1": IncidentSeverity.SEV1,
            "sev2": IncidentSeverity.SEV2,
            "sev3": IncidentSeverity.SEV3,
            "sev4": IncidentSeverity.SEV4,
            "sev5": IncidentSeverity.SEV5,
        }

        now = datetime.now(timezone.utc)
        incident = Incident(
            id=inc_id,
            title=title,
            severity=sev_map[severity],
            status=IncidentStatus.DETECTED,
            detected_at=now,
            timeline=[
                IncidentEvent(
                    timestamp=now,
                    event_type="created",
                    description=f"Incident created: {title}",
                    actor="governor",
                )
            ],
        )

        # Save incident
        incident_file = incidents_dir / f"{inc_id}.json"
        incident_file.write_text(json.dumps({
            "id": incident.id,
            "title": incident.title,
            "severity": incident.severity.value,
            "status": incident.status.value,
            "detected_at": incident.detected_at.isoformat(),
            "timeline": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "event_type": e.event_type,
                    "description": e.description,
                    "actor": e.actor,
                }
                for e in incident.timeline
            ],
        }, indent=2))

        click.echo(f"Created incident: {inc_id}")
        click.echo(f"  Title: {title}")
        click.echo(f"  Severity: {severity}")

    elif action == "status":
        if not incident_id:
            click.echo("Error: --id required for status", err=True)
            ctx.exit(1)

        incident_file = incidents_dir / f"{incident_id}.json"
        if not incident_file.exists():
            click.echo(f"Incident not found: {incident_id}", err=True)
            ctx.exit(1)

        data = json.loads(incident_file.read_text())

        if new_status:
            # Update status
            now = datetime.now(timezone.utc)
            data["status"] = new_status
            data["timeline"].append({
                "timestamp": now.isoformat(),
                "event_type": "status_change",
                "description": message or f"Status changed to {new_status}",
                "actor": "governor",
            })
            incident_file.write_text(json.dumps(data, indent=2))
            click.echo(f"Updated {incident_id} status to: {new_status}")
        else:
            # Show status
            click.echo(f"Incident: {data['id']}")
            click.echo(f"  Title: {data['title']}")
            click.echo(f"  Severity: {data['severity']}")
            click.echo(f"  Status: {data['status']}")
            click.echo("\n  Timeline:")
            for event in data["timeline"]:
                click.echo(f"    [{event['timestamp']}] {event['event_type']}: {event['description']}")

    elif action == "list":
        incidents = list(incidents_dir.glob("INC-*.json"))
        if not incidents:
            click.echo("No incidents found")
            return

        click.echo(f"Incidents ({len(incidents)}):\n")
        for inc_file in sorted(incidents, reverse=True):
            data = json.loads(inc_file.read_text())
            click.echo(f"  [{data['severity']}] {data['id']}: {data['title']}")
            click.echo(f"    Status: {data['status']}")


@ops.command("packs")
@click.pass_context
def ops_packs(ctx: click.Context) -> None:
    """List available built-in policy packs."""
    from ops_governor import BUILTIN_PACKS

    click.echo("Built-in policy packs:\n")
    for name, creator in BUILTIN_PACKS.items():
        pack = creator()
        click.echo(f"  {name}")
        click.echo(f"    {pack.description}")
        click.echo(f"    Claims: {len(pack.claims)}")
        click.echo()


# Runbook subgroup under ops
@ops.group()
@click.pass_context
def runbook(ctx: click.Context) -> None:
    """
    Manage operational runbooks.

    Runbooks are structured procedures for operational tasks.
    They can be verified, converted to claims, and tracked.
    """
    pass


@runbook.command("list")
@click.pass_context
def runbook_list(ctx: click.Context) -> None:
    """List available runbooks."""
    from ops_governor import RunbookVerifier

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized. Run 'governor ops init' first.", err=True)
        ctx.exit(1)

    verifier = RunbookVerifier(ops_dir)

    if not verifier.runbooks_dir.exists():
        click.echo("No runbooks found. Create one with: governor ops runbook create <name>")
        return

    runbooks = list(verifier.runbooks_dir.glob("*.json"))
    if not runbooks:
        click.echo("No runbooks found. Create one with: governor ops runbook create <name>")
        return

    click.echo(f"Runbooks ({len(runbooks)}):\n")
    for rb_file in sorted(runbooks):
        try:
            data = json.loads(rb_file.read_text())
            name = data.get("name", rb_file.stem)
            desc = data.get("description", "")
            steps = len(data.get("steps", []))

            click.echo(f"  {name}: {desc}")
            click.echo(f"    Steps: {steps}")
        except json.JSONDecodeError:
            click.echo(f"  {rb_file.stem}: (invalid JSON)")


@runbook.command("create")
@click.argument("name")
@click.option("--description", "-d", help="Runbook description")
@click.pass_context
def runbook_create(ctx: click.Context, name: str, description: str | None) -> None:
    """
    Create a new runbook.

    Examples:
        governor ops runbook create deploy_api
        governor ops runbook create incident_response -d "Standard incident response"
    """
    from ops_governor import RunbookVerifier

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized. Run 'governor ops init' first.", err=True)
        ctx.exit(1)

    verifier = RunbookVerifier(ops_dir)

    # Create a minimal runbook
    runbook = verifier.create_runbook(
        name=name,
        description=description or f"Runbook: {name}",
        steps=[
            {
                "description": "Step 1 - Edit this runbook",
                "command": "echo 'TODO: Add actual commands'",
                "expected_exit_code": 0,
            }
        ],
    )

    click.echo(f"Created runbook: {name}")
    click.echo(f"  Location: {verifier.runbooks_dir / f'{name}.json'}")
    click.echo("\nEdit the JSON file to add your steps.")


@runbook.command("show")
@click.argument("name")
@click.pass_context
def runbook_show(ctx: click.Context, name: str) -> None:
    """Show runbook details."""
    from ops_governor import RunbookVerifier

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized.", err=True)
        ctx.exit(1)

    verifier = RunbookVerifier(ops_dir)
    rb = verifier.load_runbook(name)

    if not rb:
        click.echo(f"Runbook not found: {name}", err=True)
        ctx.exit(1)

    click.echo(f"Runbook: {rb['name']}")
    click.echo(f"Description: {rb.get('description', '')}")
    click.echo(f"Version: {rb.get('version', '1.0')}")

    click.echo(f"\nSteps ({len(rb.get('steps', []))}):")
    for i, step in enumerate(rb.get("steps", [])):
        click.echo(f"\n  [{i}] {step.get('description', f'Step {i}')}")
        if step.get("command"):
            click.echo(f"      Command: {step['command']}")

    if rb.get("rollback_steps"):
        click.echo(f"\nRollback Steps ({len(rb['rollback_steps'])}):")
        for i, step in enumerate(rb["rollback_steps"]):
            click.echo(f"  [{i}] {step.get('description', f'Rollback {i}')}")


@runbook.command("generate-claims")
@click.argument("name")
@click.option("--install", "-i", is_flag=True, help="Install as policy pack")
@click.pass_context
def runbook_generate_claims(ctx: click.Context, name: str, install: bool) -> None:
    """
    Generate claim requirements from a runbook.

    Each runbook step becomes a proof requirement that must be satisfied.

    Examples:
        governor ops runbook generate-claims deploy_api
        governor ops runbook generate-claims deploy_api --install
    """
    from ops_governor import RunbookVerifier, PolicyRegistry, PolicyPack, ClaimDefinition

    root = Path(ctx.obj["root"])
    ops_dir = root / ".governor" / "ops"

    if not ops_dir.exists():
        click.echo("Error: Ops governor not initialized.", err=True)
        ctx.exit(1)

    verifier = RunbookVerifier(ops_dir)
    rb = verifier.load_runbook(name)

    if not rb:
        click.echo(f"Runbook not found: {name}", err=True)
        ctx.exit(1)

    requirements = verifier.generate_claim_requirements(name)

    if not requirements:
        click.echo("No requirements generated (runbook may be empty)")
        return

    click.echo(f"Generated {len(requirements)} claim requirements:\n")
    for i, req in enumerate(requirements):
        click.echo(f"  [{i}] {req.description}")
        click.echo(f"      Type: {req.proof_type.value}")

    if install:
        claim_name = f"runbook:{name}"
        claim_def = ClaimDefinition(
            name=claim_name,
            description=f"Complete runbook: {rb.get('description', name)}",
            requirements=requirements,
        )

        pack = PolicyPack(
            name=f"runbook/{name}",
            description=f"Generated from runbook: {name}",
            claims=[claim_def],
        )

        registry = PolicyRegistry(ops_dir)
        registry.register(pack)

        click.echo(f"\nInstalled policy pack: runbook/{name}")
        click.echo(f"  Claim: {claim_name}")
        click.echo(f"\nVerify with: governor ops claim verify {claim_name}")


# =============================================================================
# Epistemic Commands
# =============================================================================


EPISTEMIC_LEDGER_FILE = "epistemic_ledger.json"


def get_epistemic_ledger(gov_dir: Path):
    """Get or create the epistemic ledger. Uses SQLite when available, falls back to JSON."""
    from .epistemic import EpistemicLedger
    from .storage import get_storage
    from .evidence_store import EvidenceStore

    db_path = gov_dir / "governor.db"
    if db_path.exists():
        storage = get_storage(gov_dir)
        evidence_store = EvidenceStore(storage)
        return EpistemicLedger(storage=storage, evidence_store=evidence_store)

    # Fallback: JSON file (legacy)
    ledger_path = gov_dir / EPISTEMIC_LEDGER_FILE
    if ledger_path.exists():
        data = json.loads(ledger_path.read_text())
        return EpistemicLedger.from_dict(data)

    return EpistemicLedger()


def save_epistemic_ledger(gov_dir: Path, ledger) -> None:
    """Save the epistemic ledger to disk. Skips JSON when storage-backed."""
    if ledger.storage is not None:
        # Writes are already persisted through write-through; no JSON needed
        return
    ledger_path = gov_dir / EPISTEMIC_LEDGER_FILE
    ledger_path.write_text(ledger.to_json())


@cli.group()
@click.pass_context
def epistemic(ctx: click.Context) -> None:
    """
    Epistemic governance: provenance, confidence, and evidence tracking.

    Track how claims are established (provenance), confidence levels,
    and detect dangerous claims (high confidence without evidence).
    """
    pass


@epistemic.command("status")
@click.pass_context
def epistemic_status(ctx: click.Context) -> None:
    """Show epistemic ledger status and metrics."""
    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    metrics = ledger.get_metrics()

    click.echo("Epistemic Ledger Status:\n")
    click.echo(f"  Step: {metrics['step']}")
    click.echo(f"  Total claims: {metrics['total_claims']}")
    click.echo(f"  Active: {metrics['active_claims']}")
    click.echo(f"  Blocked: {metrics['blocked_claims']}")
    click.echo(f"  Retracted: {metrics['retracted_claims']}")
    click.echo()

    # Highlight dangerous claims
    dangerous = metrics['dangerous_claims']
    if dangerous > 0:
        click.echo(f"  ⚠️  DANGEROUS CLAIMS: {dangerous}")
        click.echo("      (high confidence without evidence)")
    else:
        click.echo("  ✓ No dangerous claims")
    click.echo()

    click.echo("  Provenance distribution:")
    for prov, count in metrics['provenance_distribution'].items():
        if count > 0:
            click.echo(f"    {prov}: {count}")

    click.echo()
    click.echo("  Confidence distribution:")
    conf = metrics['confidence_distribution']
    click.echo(f"    High (>=0.7): {conf['high']}")
    click.echo(f"    Medium (0.3-0.7): {conf['medium']}")
    click.echo(f"    Low (<0.3): {conf['low']}")

    if metrics['total_promotions_attempted'] > 0:
        click.echo()
        click.echo("  Promotion stats:")
        click.echo(f"    Attempted: {metrics['total_promotions_attempted']}")
        click.echo(f"    Forbidden: {metrics['total_promotions_forbidden']}")
        click.echo(f"    Rate: {metrics['forbidden_promotion_rate']:.1%}")


@epistemic.command("claims")
@click.option("--provenance", "-p", help="Filter by provenance type")
@click.option("--agent", "-a", help="Filter by source agent")
@click.option("--ungrounded", "-u", is_flag=True, help="Show only ungrounded claims")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def epistemic_claims(
    ctx: click.Context,
    provenance: str | None,
    agent: str | None,
    ungrounded: bool,
    as_json: bool,
) -> None:
    """List grounded claims in the epistemic ledger."""
    from .epistemic import Provenance

    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    claims = ledger.active_claims()

    # Apply filters
    if provenance:
        try:
            prov = Provenance(provenance)
            claims = [c for c in claims if c.provenance == prov]
        except ValueError:
            click.echo(f"Invalid provenance: {provenance}", err=True)
            click.echo(f"Valid: {', '.join(p.value for p in Provenance)}")
            ctx.exit(1)

    if agent:
        claims = [c for c in claims if c.source_agent_id == agent]

    if ungrounded:
        claims = [c for c in claims if not c.is_grounded]

    if as_json:
        click.echo(json.dumps([c.to_dict() for c in claims], indent=2, default=str))
        return

    if not claims:
        click.echo("No claims found")
        return

    click.echo(f"Grounded claims ({len(claims)}):\n")

    for claim in claims:
        danger_icon = "⚠️ " if claim.is_dangerous else ""
        grounded_icon = "✓" if claim.is_grounded else "○"

        click.echo(f"  {danger_icon}[{claim.claim_id}]")
        click.echo(f"    {grounded_icon} {claim.content[:60]}{'...' if len(claim.content) > 60 else ''}")
        click.echo(f"    Provenance: {claim.provenance.value}, Confidence: {claim.confidence:.2f}")

        if claim.evidence_refs:
            click.echo(f"    Evidence: {len(claim.evidence_refs)} ref(s)")

        if claim.source_agent_id:
            click.echo(f"    Source: {claim.source_agent_id}")

        click.echo()


@epistemic.command("dangerous")
@click.option("--block", is_flag=True, help="Block all dangerous claims")
@click.pass_context
def epistemic_dangerous(ctx: click.Context, block: bool) -> None:
    """List or block dangerous claims (high confidence + ungrounded)."""
    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    dangerous = ledger.dangerous_claims()

    if not dangerous:
        click.echo("✓ No dangerous claims found")
        return

    click.echo(f"⚠️  Found {len(dangerous)} dangerous claim(s):\n")
    click.echo("(High confidence without evidence)\n")

    for claim in dangerous:
        click.echo(f"  [{claim.claim_id}]")
        click.echo(f"    {claim.content[:70]}{'...' if len(claim.content) > 70 else ''}")
        click.echo(f"    Provenance: {claim.provenance.value}")
        click.echo(f"    Confidence: {claim.confidence:.2f} (threshold: 0.70)")
        click.echo()

    if block:
        for claim in dangerous:
            ledger.block(claim.claim_id, "Dangerous claim: high confidence without evidence")
        save_epistemic_ledger(gov_dir, ledger)
        click.echo(f"Blocked {len(dangerous)} dangerous claim(s)")


@epistemic.command("create")
@click.argument("content")
@click.option("--provenance", "-p", default="assumed", help="Provenance type")
@click.option("--confidence", "-c", type=float, help="Confidence level (0-1)")
@click.option("--agent", "-a", help="Source agent ID")
@click.pass_context
def epistemic_create(
    ctx: click.Context,
    content: str,
    provenance: str,
    confidence: float | None,
    agent: str | None,
) -> None:
    """Create a new grounded claim."""
    from .epistemic import Provenance, DEFAULT_CONFIDENCE

    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    try:
        prov = Provenance(provenance)
    except ValueError:
        click.echo(f"Invalid provenance: {provenance}", err=True)
        click.echo(f"Valid: {', '.join(p.value for p in Provenance)}")
        ctx.exit(1)

    if confidence is None:
        confidence = DEFAULT_CONFIDENCE.get(prov, 0.5)

    claim = ledger.new_claim(content, prov, confidence, source_agent_id=agent)

    save_epistemic_ledger(gov_dir, ledger)

    click.echo(f"Created claim: {claim.claim_id}")
    click.echo(f"  Content: {content[:60]}{'...' if len(content) > 60 else ''}")
    click.echo(f"  Provenance: {claim.provenance.value}")
    click.echo(f"  Confidence: {claim.confidence:.2f}")
    click.echo(f"  Grounded: {'yes' if claim.is_grounded else 'no'}")

    if claim.is_dangerous:
        click.echo("  ⚠️  WARNING: This claim is dangerous (high confidence without evidence)")


@epistemic.command("evidence")
@click.argument("claim_id")
@click.option("--type", "ev_type", required=True, help="Evidence type (tool_trace, url, document, human_input, receipt)")
@click.option("--locator", "-l", required=True, help="Evidence locator (URL, hash, trace ID, etc.)")
@click.option("--scope", "-s", required=True, help="What aspect of the claim this supports")
@click.pass_context
def epistemic_evidence(
    ctx: click.Context,
    claim_id: str,
    ev_type: str,
    locator: str,
    scope: str,
) -> None:
    """Attach evidence to a claim."""
    from .epistemic import EvidenceRef, EvidenceType

    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    if claim_id not in ledger.claims:
        click.echo(f"Claim not found: {claim_id}", err=True)
        ctx.exit(1)

    try:
        evidence_type = EvidenceType(ev_type)
    except ValueError:
        click.echo(f"Invalid evidence type: {ev_type}", err=True)
        click.echo(f"Valid: {', '.join(e.value for e in EvidenceType)}")
        ctx.exit(1)

    ref = EvidenceRef(
        ref_id=f"ev_{uuid4().hex[:8]}",
        ref_type=evidence_type,
        locator=locator,
        scope=scope,
        retrieved_at=datetime.now(),
    )

    ledger.attach_evidence(claim_id, ref)
    save_epistemic_ledger(gov_dir, ledger)

    claim = ledger.get(claim_id)
    click.echo(f"Attached evidence to {claim_id}")
    click.echo(f"  Type: {evidence_type.value}")
    click.echo(f"  Locator: {locator}")
    click.echo(f"  Scope: {scope}")
    click.echo(f"  Claim is now grounded: {'yes' if claim.is_grounded else 'no'}")


@epistemic.command("promote")
@click.argument("claim_id")
@click.argument("new_provenance")
@click.pass_context
def epistemic_promote(ctx: click.Context, claim_id: str, new_provenance: str) -> None:
    """Promote a claim to a new provenance level."""
    from .epistemic import Provenance, PromotionResult

    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    if claim_id not in ledger.claims:
        click.echo(f"Claim not found: {claim_id}", err=True)
        ctx.exit(1)

    try:
        new_prov = Provenance(new_provenance)
    except ValueError:
        click.echo(f"Invalid provenance: {new_provenance}", err=True)
        click.echo(f"Valid: {', '.join(p.value for p in Provenance)}")
        ctx.exit(1)

    claim = ledger.get(claim_id)
    old_prov = claim.provenance

    # Check first
    allowed, reason = ledger.can_promote(claim_id, new_prov)
    if not allowed:
        click.echo(f"Cannot promote: {reason}", err=True)
        if "evidence" in reason.lower():
            click.echo("Hint: Attach evidence first with 'governor epistemic evidence'")
        ctx.exit(1)

    result = ledger.promote(claim_id, new_prov)
    save_epistemic_ledger(gov_dir, ledger)

    if result == PromotionResult.SUCCESS:
        click.echo(f"Promoted {claim_id}")
        click.echo(f"  {old_prov.value} -> {new_prov.value}")
    else:
        click.echo(f"Promotion failed: {result.value}", err=True)
        ctx.exit(1)


@epistemic.command("retract")
@click.argument("claim_id")
@click.option("--reason", "-r", default="Manual retraction", help="Reason for retraction")
@click.pass_context
def epistemic_retract(ctx: click.Context, claim_id: str, reason: str) -> None:
    """Retract a claim (successful recovery, not failure)."""
    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    if claim_id not in ledger.claims:
        click.echo(f"Claim not found: {claim_id}", err=True)
        ctx.exit(1)

    ledger.retract(claim_id, reason)
    save_epistemic_ledger(gov_dir, ledger)

    click.echo(f"Retracted {claim_id}")
    click.echo(f"  Reason: {reason}")
    click.echo()
    click.echo("Note: Retraction is success, not failure.")
    click.echo("It means the claim was explicitly withdrawn.")


@epistemic.command("decay")
@click.option("--amount", "-a", type=float, default=0.1, help="Decay amount (default: 0.1)")
@click.option("--dry-run", is_flag=True, help="Show what would be decayed without applying")
@click.pass_context
def epistemic_decay(ctx: click.Context, amount: float, dry_run: bool) -> None:
    """Decay confidence on ungrounded claims."""
    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    ungrounded = ledger.ungrounded_claims()

    if not ungrounded:
        click.echo("No ungrounded claims to decay")
        return

    click.echo(f"{'Would decay' if dry_run else 'Decaying'} {len(ungrounded)} ungrounded claim(s) by {amount}:\n")

    for claim in ungrounded:
        old_conf = claim.confidence
        new_conf = max(0.0, old_conf - amount)
        click.echo(f"  [{claim.claim_id}] {old_conf:.2f} -> {new_conf:.2f}")

    if not dry_run:
        count = ledger.decay_ungrounded_confidence(amount)
        save_epistemic_ledger(gov_dir, ledger)
        click.echo(f"\nDecayed {count} claim(s)")
    else:
        click.echo("\n(dry run - no changes made)")


@epistemic.command("tick")
@click.pass_context
def epistemic_tick(ctx: click.Context) -> None:
    """Advance the epistemic ledger step counter."""
    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)

    old_step = ledger.step
    ledger.tick()
    save_epistemic_ledger(gov_dir, ledger)

    click.echo(f"Step advanced: {old_step} -> {ledger.step}")


# ============================================================================
# Regime Detection Commands
# ============================================================================

REGIME_STATE_FILE = "regime_state.json"


def get_regime_detector(gov_dir: Path):
    """Get or create the regime detector."""
    from .regime import RegimeDetector, RegimeSignals, OperationalRegime

    state_path = gov_dir / REGIME_STATE_FILE

    detector = RegimeDetector()

    if state_path.exists():
        data = json.loads(state_path.read_text())
        detector = RegimeDetector.from_dict(data)

    return detector


def save_regime_detector(gov_dir: Path, detector) -> None:
    """Save the regime detector state to disk."""
    state_path = gov_dir / REGIME_STATE_FILE
    state_path.write_text(json.dumps(detector.to_dict(), indent=2))


@cli.group()
@click.pass_context
def regime(ctx: click.Context) -> None:
    """
    Regime detection: operational health monitoring.

    Monitors system health signals and classifies operational regime:
    - ELASTIC: Stable, normal operation
    - WARM: Drifting but recoverable
    - DUCTILE: Path-dependent, manual intervention may be needed
    - UNSTABLE: Critical state, emergency stop recommended
    """
    pass


@regime.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def regime_status(ctx: click.Context, as_json: bool) -> None:
    """Show current operational regime and signals."""
    from .regime import OperationalRegime

    gov_dir = ensure_initialized(ctx)
    detector = get_regime_detector(gov_dir)

    state = detector.get_state()

    if as_json:
        click.echo(json.dumps(state, indent=2))
        return

    regime_val = state["current_regime"]
    signals = state["current_signals"]

    # Color-code the regime
    regime_colors = {
        "elastic": "green",
        "warm": "yellow",
        "ductile": "red",
        "unstable": "bright_red",
    }

    color = regime_colors.get(regime_val, "white")
    click.echo(f"Regime: {click.style(regime_val.upper(), fg=color, bold=True)}")

    if state["warnings"]:
        click.echo("\nWarnings:")
        for warning in state["warnings"]:
            click.echo(f"  - {warning}")

    click.echo("\nSignals:")
    click.echo(f"  hysteresis:             {signals['hysteresis']:.3f}")
    click.echo(f"  relaxation_time:        {signals['relaxation_time']:.3f}")
    click.echo(f"  tool_gain:              {signals['tool_gain']:.3f}")
    click.echo(f"  anisotropy:             {signals['anisotropy']:.3f}")
    click.echo(f"  provenance_deficit:     {signals['provenance_deficit']:.3f}")
    click.echo(f"  budget_pressure:        {signals['budget_pressure']:.3f}")
    click.echo(f"  contradiction_open:     {signals['contradiction_open_rate']:.3f}")
    click.echo(f"  contradiction_close:    {signals['contradiction_close_rate']:.3f}")
    click.echo(f"  rejection_rate:         {signals['rejection_rate']:.3f}")
    click.echo(f"  dangerous_claim_rate:   {signals['dangerous_claim_rate']:.3f}")

    # Show recommended actions
    try:
        from .regime import OperationalRegime as OR
        current = OR(regime_val)
        actions = current.recommended_actions
        if actions:
            click.echo(f"\nRecommended actions: {', '.join(actions)}")
    except Exception:
        pass


@regime.command("history")
@click.option("--limit", "-n", default=10, help="Number of transitions to show")
@click.pass_context
def regime_history(ctx: click.Context, limit: int) -> None:
    """Show regime transition history."""
    gov_dir = ensure_initialized(ctx)
    detector = get_regime_detector(gov_dir)

    history = detector.get_history()

    if not history:
        click.echo("No regime transitions recorded.")
        return

    click.echo(f"Regime Transitions (last {limit}):\n")

    for entry in history[-limit:]:
        ts = entry["timestamp"]
        from_r = entry["from_regime"]
        to_r = entry["to_regime"]
        warnings = entry.get("warnings", [])

        click.echo(f"  {ts}: {from_r} -> {to_r}")
        if warnings:
            for w in warnings:
                click.echo(f"    warning: {w}")


@regime.command("signals")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def regime_signals(ctx: click.Context, as_json: bool) -> None:
    """Show current regime signals in detail."""
    gov_dir = ensure_initialized(ctx)
    detector = get_regime_detector(gov_dir)

    signals = detector.current_signals.to_dict()

    if as_json:
        click.echo(json.dumps(signals, indent=2))
    else:
        click.echo("Current Signals:\n")
        for key, value in sorted(signals.items()):
            click.echo(f"  {key}: {value}")


@regime.command("update")
@click.option("--hysteresis", type=float, help="Set hysteresis value")
@click.option("--relaxation", type=float, help="Set relaxation time value")
@click.option("--tool-gain", type=float, help="Set tool gain value")
@click.option("--anisotropy", type=float, help="Set anisotropy value")
@click.option("--provenance-deficit", type=float, help="Set provenance deficit value")
@click.option("--budget-pressure", type=float, help="Set budget pressure value")
@click.pass_context
def regime_update(
    ctx: click.Context,
    hysteresis: float | None,
    relaxation: float | None,
    tool_gain: float | None,
    anisotropy: float | None,
    provenance_deficit: float | None,
    budget_pressure: float | None,
) -> None:
    """Update signals and check for regime transition."""
    from .regime import RegimeSignals

    gov_dir = ensure_initialized(ctx)
    detector = get_regime_detector(gov_dir)

    # Build updated signals
    current = detector.current_signals
    new_signals = RegimeSignals(
        hysteresis=hysteresis if hysteresis is not None else current.hysteresis,
        relaxation_time=relaxation if relaxation is not None else current.relaxation_time,
        tool_gain=tool_gain if tool_gain is not None else current.tool_gain,
        anisotropy=anisotropy if anisotropy is not None else current.anisotropy,
        provenance_deficit=provenance_deficit if provenance_deficit is not None else current.provenance_deficit,
        budget_pressure=budget_pressure if budget_pressure is not None else current.budget_pressure,
        contradiction_open_rate=current.contradiction_open_rate,
        contradiction_close_rate=current.contradiction_close_rate,
        rejection_rate=current.rejection_rate,
        dangerous_claim_rate=current.dangerous_claim_rate,
    )

    old_regime = detector.current_regime
    new_regime, warnings = detector.update(new_signals)

    save_regime_detector(gov_dir, detector)

    if new_regime != old_regime:
        click.echo(f"Regime transition: {old_regime.value} -> {new_regime.value}")
        if warnings:
            click.echo("Warnings:")
            for w in warnings:
                click.echo(f"  - {w}")
    else:
        click.echo(f"Regime unchanged: {new_regime.value}")


@regime.command("thresholds")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def regime_thresholds(ctx: click.Context, as_json: bool) -> None:
    """Show regime detection thresholds."""
    gov_dir = ensure_initialized(ctx)
    detector = get_regime_detector(gov_dir)

    thresholds = detector.thresholds.to_dict()

    if as_json:
        click.echo(json.dumps(thresholds, indent=2))
    else:
        click.echo("Regime Detection Thresholds:\n")
        click.echo("WARM thresholds (any indicator triggers WARM):")
        click.echo(f"  hysteresis_warm:        {thresholds['hysteresis_warm']}")
        click.echo(f"  relaxation_warm:        {thresholds['relaxation_warm']}")
        click.echo(f"  rejection_rate_warm:    {thresholds['rejection_rate_warm']}")
        click.echo(f"  contradiction_warm:     {thresholds['contradiction_warm']}")
        click.echo(f"  dangerous_claim_warm:   {thresholds['dangerous_claim_warm']}")

        click.echo("\nDUCTILE thresholds (multiple indicators trigger DUCTILE):")
        click.echo(f"  hysteresis_ductile:     {thresholds['hysteresis_ductile']}")
        click.echo(f"  anisotropy_ductile:     {thresholds['anisotropy_ductile']}")
        click.echo(f"  ductile_indicator_count:{thresholds['ductile_indicator_count']}")

        click.echo("\nUNSTABLE thresholds (critical - any triggers UNSTABLE):")
        click.echo(f"  tool_gain_unstable:     {thresholds['tool_gain_unstable']}")
        click.echo(f"  budget_pressure_unstable:{thresholds['budget_pressure_unstable']}")
        click.echo(f"  dangerous_claim_unstable:{thresholds['dangerous_claim_unstable']}")


@regime.command("reset")
@click.option("--confirm", is_flag=True, help="Confirm reset")
@click.pass_context
def regime_reset(ctx: click.Context, confirm: bool) -> None:
    """Reset regime detector to default state."""
    from .regime import RegimeDetector

    gov_dir = ensure_initialized(ctx)

    if not confirm:
        click.echo("Use --confirm to reset regime detector state.")
        return

    detector = RegimeDetector()
    save_regime_detector(gov_dir, detector)
    click.echo("Regime detector reset to default state (ELASTIC).")


# =============================================================================
# Boil Control Commands
# =============================================================================

BOIL_STATE_FILE = "boil_state.json"


def get_boil_controller(gov_dir: Path):
    """Get the boil controller, loading from disk if available."""
    from .boil import BoilController, ControlMode

    state_path = gov_dir / BOIL_STATE_FILE
    controller = BoilController()

    if state_path.exists():
        data = json.loads(state_path.read_text())
        controller = BoilController.from_dict(data)

    return controller


def save_boil_controller(gov_dir: Path, controller) -> None:
    """Save the boil controller state to disk."""
    state_path = gov_dir / BOIL_STATE_FILE
    state_path.write_text(json.dumps(controller.to_dict(), indent=2))


@cli.group()
@click.pass_context
def boil(ctx: click.Context) -> None:
    """
    Boil control: named presets with dwell time enforcement.

    Control modes (like kettle temperature settings):
    - GREEN_TEA: Delicate - tight bounds, strict authority
    - WHITE_TEA: Light - slightly more tolerance
    - OOLONG: Balanced - standard bounds (default)
    - BLACK_TEA: Robust - higher tolerance
    - FRENCH_PRESS: Aggressive - near limits but bounded
    - BOIL: Sentinel - tripwires only, no gradual control
    """
    pass


@boil.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def boil_status(ctx: click.Context, as_json: bool) -> None:
    """Show current boil control status."""
    from .boil import ControlMode

    gov_dir = ensure_initialized(ctx)
    controller = get_boil_controller(gov_dir)

    state = controller.get_state()
    preset_info = controller.get_preset_info()

    if as_json:
        combined = {**state, "preset": preset_info}
        click.echo(json.dumps(combined, indent=2))
        return

    # Mode name with description
    mode = ControlMode(state["mode"])
    click.echo(f"Mode: {click.style(mode.value.upper(), fg='cyan')} - {mode.description}")
    click.echo()

    # Current regime with color
    regime_colors = {
        "elastic": "green",
        "warm": "yellow",
        "ductile": "red",
        "unstable": "bright_red",
    }
    regime = state["regime"]
    click.echo(f"Regime: {click.style(regime.upper(), fg=regime_colors.get(regime, 'white'))}")
    click.echo(f"Turn: {state['turn']}")
    click.echo(f"Turns in regime: {state['turns_in_regime']}")

    if state.get("pending_transition"):
        click.echo(f"Pending transition: {click.style(state['pending_transition'].upper(), fg='yellow')} (blocked by dwell)")

    click.echo()
    click.echo("Preset configuration:")
    click.echo(f"  Claim budget: {preset_info['claim_budget']}")
    click.echo(f"  Novelty tolerance: {preset_info['novelty_tolerance']}")
    click.echo(f"  Authority posture: {preset_info['authority_posture']}")
    click.echo(f"  Min dwell turns: {preset_info['min_dwell']}")

    click.echo()
    click.echo("Active tripwires:")
    for name, active in preset_info["tripwires"].items():
        status = click.style("ON", fg="green") if active else click.style("off", fg="red")
        click.echo(f"  {name}: {status}")

    click.echo()
    click.echo(f"Events logged: {state['events_count']}")


@boil.command("set")
@click.argument("mode", type=click.Choice([
    "green_tea", "white_tea", "oolong", "black_tea", "french_press", "boil"
], case_sensitive=False))
@click.pass_context
def boil_set(ctx: click.Context, mode: str) -> None:
    """Change to a different control mode (preset)."""
    from .boil import ControlMode

    gov_dir = ensure_initialized(ctx)
    controller = get_boil_controller(gov_dir)

    old_mode = controller.preset.mode
    new_mode = ControlMode(mode.lower())
    controller.set_mode(new_mode)
    save_boil_controller(gov_dir, controller)

    click.echo(f"Mode changed: {old_mode.value} -> {click.style(new_mode.value.upper(), fg='cyan')}")
    click.echo(f"Description: {new_mode.description}")


@boil.command("presets")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def boil_presets(ctx: click.Context, as_json: bool) -> None:
    """List all available presets."""
    from .boil import list_presets

    presets = list_presets()

    if as_json:
        click.echo(json.dumps(presets, indent=2))
        return

    click.echo("Available control modes:\n")
    for p in presets:
        click.echo(f"{click.style(p['mode'].upper(), fg='cyan')}")
        click.echo(f"  {p['description']}")
        click.echo(f"  Claim budget: {p['claim_budget']}, Novelty: {p['novelty_tolerance']}")
        click.echo(f"  Authority: {p['authority_posture']}, Tripwires: {p['tripwires_active']}/4")
        click.echo()


@boil.command("events")
@click.option("--limit", "-n", default=10, help="Number of events to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def boil_events(ctx: click.Context, limit: int, as_json: bool) -> None:
    """Show recent boil control events."""
    gov_dir = ensure_initialized(ctx)
    controller = get_boil_controller(gov_dir)

    events = controller.get_events(limit=limit)

    if as_json:
        click.echo(json.dumps(events, indent=2))
        return

    if not events:
        click.echo("No events recorded.")
        return

    click.echo(f"Recent events (last {len(events)}):\n")
    for e in events:
        timestamp = e["timestamp"][:19]  # Truncate for readability
        event_type = e["event_type"]
        details = e["details"]

        # Color by event type
        type_colors = {
            "tripwire": "red",
            "mode_change": "cyan",
            "dwell_hold": "yellow",
            "transition_allowed": "green",
        }
        colored_type = click.style(event_type, fg=type_colors.get(event_type, "white"))

        click.echo(f"[{timestamp}] {colored_type}")
        for key, value in details.items():
            click.echo(f"  {key}: {value}")
        click.echo()


@boil.command("process")
@click.option("--hysteresis", type=float, default=0.1, help="Hysteresis signal")
@click.option("--tool-gain", type=float, default=0.3, help="Tool gain signal")
@click.option("--provenance-deficit", type=float, default=0.0, help="Provenance deficit")
@click.option("--rejection-rate", type=float, default=0.0, help="Rejection rate")
@click.option("--dangerous-rate", type=float, default=0.0, help="Dangerous claim rate")
@click.option("--contradiction-open", type=float, default=0.0, help="Contradiction open rate")
@click.option("--contradiction-close", type=float, default=0.0, help="Contradiction close rate")
@click.pass_context
def boil_process(
    ctx: click.Context,
    hysteresis: float,
    tool_gain: float,
    provenance_deficit: float,
    rejection_rate: float,
    dangerous_rate: float,
    contradiction_open: float,
    contradiction_close: float,
) -> None:
    """Process a turn through boil control with given signals."""
    from .regime import RegimeSignals

    gov_dir = ensure_initialized(ctx)
    controller = get_boil_controller(gov_dir)

    signals = RegimeSignals(
        hysteresis=hysteresis,
        tool_gain=tool_gain,
        provenance_deficit=provenance_deficit,
        rejection_rate=rejection_rate,
        dangerous_claim_rate=dangerous_rate,
        contradiction_open_rate=contradiction_open,
        contradiction_close_rate=contradiction_close,
    )

    response = controller.process_turn(signals)
    save_boil_controller(gov_dir, controller)

    # Display response
    regime_colors = {
        "elastic": "green",
        "warm": "yellow",
        "ductile": "red",
        "unstable": "bright_red",
    }

    regime = response["regime"]
    action = response["action"]
    click.echo(f"Turn {response['turn']} processed")
    click.echo(f"Regime: {click.style(regime.upper(), fg=regime_colors.get(regime, 'white'))}")
    click.echo(f"Action: {action}")

    if response.get("tripwire"):
        click.echo(click.style(f"TRIPWIRE: {response['tripwire']}", fg="red", bold=True))

    if response.get("dwell_blocked"):
        click.echo(click.style(f"Transition to {response['pending_transition']} blocked by dwell", fg="yellow"))


@boil.command("reset")
@click.option("--confirm", is_flag=True, help="Confirm reset")
@click.option("--mode", type=click.Choice([
    "green_tea", "white_tea", "oolong", "black_tea", "french_press", "boil"
], case_sensitive=False), default="oolong", help="Mode to reset to")
@click.pass_context
def boil_reset(ctx: click.Context, confirm: bool, mode: str) -> None:
    """Reset boil controller to default state."""
    from .boil import BoilController, ControlMode

    gov_dir = ensure_initialized(ctx)

    if not confirm:
        click.echo("Use --confirm to reset boil controller state.")
        click.echo(f"This will reset to {mode.upper()} mode with ELASTIC regime.")
        return

    new_mode = ControlMode(mode.lower())
    controller = BoilController(new_mode)
    save_boil_controller(gov_dir, controller)
    click.echo(f"Boil controller reset to {click.style(mode.upper(), fg='cyan')} mode (ELASTIC regime).")


# =============================================================================
# Jurisdiction Commands
# =============================================================================

JURISDICTION_STATE_FILE = "jurisdiction_state.json"


def get_jurisdiction_manager(gov_dir: Path):
    """Get the jurisdiction manager, loading from disk if available."""
    from .jurisdictions import JurisdictionManager

    state_path = gov_dir / JURISDICTION_STATE_FILE
    manager = JurisdictionManager()

    if state_path.exists():
        data = json.loads(state_path.read_text())
        manager = JurisdictionManager.from_dict(data)

    return manager


def save_jurisdiction_manager(gov_dir: Path, manager) -> None:
    """Save the jurisdiction manager state to disk."""
    state_path = gov_dir / JURISDICTION_STATE_FILE
    state_path.write_text(json.dumps(manager.to_dict(), indent=2))


@cli.group()
@click.pass_context
def jurisdiction(ctx: click.Context) -> None:
    """
    Jurisdiction: context-aware epistemic governance.

    Different reasoning contexts have different rules:
    - FACTUAL: Strict evidence, contradictions block
    - SPECULATIVE: Provisional claims, no closure, exploration
    - ADVERSARIAL: Devil's advocate, contradictions expected
    - NARRATIVE: Fiction mode, story-internal consistency
    - And more...
    """
    pass


@jurisdiction.command("status")
@click.pass_context
def jurisdiction_status(ctx: click.Context) -> None:
    """Show current jurisdiction status."""
    gov_dir = ensure_initialized(ctx)
    manager = get_jurisdiction_manager(gov_dir)
    status = manager.get_status()

    j = manager.current_jurisdiction
    click.echo(f"Jurisdiction: {click.style(j.name.upper(), fg='cyan')}")
    if j.output_label:
        click.echo(f"Output label: {j.output_label}")
    click.echo(f"Description: {j.description}")
    click.echo()

    click.echo(f"Budget: {status['budget']:.1f}")
    click.echo(f"Refill rate: {status['refill_rate']:.1f} per turn")
    click.echo()

    click.echo("Policies:")
    click.echo(f"  Contradiction: {status['contradiction_policy']}")
    click.echo(f"  Closure allowed: {status['closure_allowed']}")
    click.echo(f"  Export to factual: {status['export_allowed']}")
    click.echo()

    stats = status["stats"]
    click.echo("Statistics:")
    click.echo(f"  Claims made: {stats['claims_made']}")
    click.echo(f"  Contradictions opened: {stats['contradictions_opened']}")
    click.echo(f"  Contradictions resolved: {stats['contradictions_resolved']}")
    click.echo(f"  Exports made: {stats['exports_made']}")


@jurisdiction.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def jurisdiction_list(ctx: click.Context, as_json: bool) -> None:
    """List all available jurisdictions."""
    from .jurisdictions import get_all_jurisdictions

    jurisdictions = get_all_jurisdictions()

    if as_json:
        data = {name: j.to_dict() for name, j in jurisdictions.items()}
        click.echo(json.dumps(data, indent=2))
        return

    click.echo("Available jurisdictions:\n")
    for name, j in jurisdictions.items():
        click.echo(f"{click.style(name.upper(), fg='cyan')}")
        click.echo(f"  {j.description}")
        if j.output_label:
            click.echo(f"  Label: {j.output_label}")
        click.echo(f"  Contradiction policy: {j.contradiction_policy.value}")
        click.echo(f"  Closure allowed: {j.closure_allowed}")
        click.echo()


@jurisdiction.command("set")
@click.argument("name", type=click.Choice([
    "factual", "speculative", "counterfactual", "adversarial",
    "narrative", "forensic", "pedagogical", "audit"
], case_sensitive=False))
@click.pass_context
def jurisdiction_set(ctx: click.Context, name: str) -> None:
    """Switch to a different jurisdiction."""
    gov_dir = ensure_initialized(ctx)
    manager = get_jurisdiction_manager(gov_dir)

    old_name = manager.current_jurisdiction.name
    success, msg = manager.switch_jurisdiction(name.lower())

    if success:
        save_jurisdiction_manager(gov_dir, manager)
        j = manager.current_jurisdiction
        click.echo(f"Switched: {old_name} -> {click.style(j.name.upper(), fg='cyan')}")
        click.echo(f"Description: {j.description}")
        if j.output_label:
            click.echo(f"Output label: {j.output_label}")
        click.echo(f"Budget: {manager.current_budget:.1f}")
    else:
        click.echo(click.style(f"Error: {msg}", fg="red"))


@jurisdiction.command("tick")
@click.pass_context
def jurisdiction_tick(ctx: click.Context) -> None:
    """Advance turn, refilling budget."""
    gov_dir = ensure_initialized(ctx)
    manager = get_jurisdiction_manager(gov_dir)

    old_budget = manager.current_budget
    new_budget = manager.tick()
    save_jurisdiction_manager(gov_dir, manager)

    click.echo(f"Budget refilled: {old_budget:.1f} -> {new_budget:.1f}")
    click.echo(f"Refill rate: {manager.current_jurisdiction.budget.refill_rate:.1f}")


@jurisdiction.command("claim")
@click.option("--speculative", is_flag=True, help="Mark as speculative claim")
@click.option("--adversarial", is_flag=True, help="Mark as adversarial claim")
@click.pass_context
def jurisdiction_claim(ctx: click.Context, speculative: bool, adversarial: bool) -> None:
    """Make a claim (consumes budget)."""
    gov_dir = ensure_initialized(ctx)
    manager = get_jurisdiction_manager(gov_dir)

    success, msg = manager.make_claim(is_speculative=speculative, is_adversarial=adversarial)

    if success:
        save_jurisdiction_manager(gov_dir, manager)
        click.echo(click.style(msg, fg="green"))
    else:
        click.echo(click.style(f"Failed: {msg}", fg="red"))


@jurisdiction.command("export")
@click.option("--has-evidence", is_flag=True, help="Claim has promotion evidence")
@click.pass_context
def jurisdiction_export(ctx: click.Context, has_evidence: bool) -> None:
    """Export a claim to factual jurisdiction."""
    gov_dir = ensure_initialized(ctx)
    manager = get_jurisdiction_manager(gov_dir)

    success, msg = manager.export_to_factual(has_evidence=has_evidence)

    if success:
        save_jurisdiction_manager(gov_dir, manager)
        click.echo(click.style(msg, fg="green"))
    else:
        click.echo(click.style(f"Failed: {msg}", fg="red"))


@jurisdiction.command("info")
@click.argument("name", type=click.Choice([
    "factual", "speculative", "counterfactual", "adversarial",
    "narrative", "forensic", "pedagogical", "audit"
], case_sensitive=False))
@click.pass_context
def jurisdiction_info(ctx: click.Context, name: str) -> None:
    """Show detailed info about a jurisdiction."""
    from .jurisdictions import get_jurisdiction

    j = get_jurisdiction(name.lower())
    if j is None:
        click.echo(click.style(f"Unknown jurisdiction: {name}", fg="red"))
        return

    click.echo(f"Jurisdiction: {click.style(j.name.upper(), fg='cyan')}")
    click.echo(f"Description: {j.description}")
    if j.output_label:
        click.echo(f"Output label: {j.output_label}")
    click.echo()

    click.echo("Evidence admissibility:")
    for e in sorted(j.admissible_evidence, key=lambda x: x.value):
        click.echo(f"  - {e.value}")
    click.echo()

    click.echo("Budget profile:")
    b = j.budget
    click.echo(f"  Claim cost: {b.claim_cost}")
    click.echo(f"  Contradiction cost: {b.contradiction_cost}")
    click.echo(f"  Resolution cost: {b.resolution_cost}")
    click.echo(f"  Export cost: {b.export_cost}")
    click.echo(f"  Refill rate: {b.refill_rate}")
    if b.speculative_discount != 1.0:
        click.echo(f"  Speculative discount: {b.speculative_discount}")
    if b.adversarial_discount != 1.0:
        click.echo(f"  Adversarial discount: {b.adversarial_discount}")
    click.echo()

    click.echo("Policies:")
    click.echo(f"  Spillover: {j.spillover.value}")
    click.echo(f"  Contradiction: {j.contradiction_policy.value}")
    click.echo(f"  Contradiction tolerance: {j.contradiction_tolerance}")
    click.echo(f"  Closure allowed: {j.closure_allowed}")
    click.echo(f"  Closure requires evidence: {j.closure_requires_evidence}")
    click.echo(f"  Export to factual allowed: {j.export_to_factual_allowed}")
    click.echo(f"  Export requires promotion: {j.export_requires_promotion}")


@jurisdiction.command("reset")
@click.option("--confirm", is_flag=True, help="Confirm reset")
@click.option("--to", "to_jurisdiction", type=click.Choice([
    "factual", "speculative", "counterfactual", "adversarial",
    "narrative", "forensic", "pedagogical", "audit"
], case_sensitive=False), default="factual", help="Jurisdiction to reset to")
@click.pass_context
def jurisdiction_reset(ctx: click.Context, confirm: bool, to_jurisdiction: str) -> None:
    """Reset jurisdiction manager to default state."""
    from .jurisdictions import JurisdictionManager

    gov_dir = ensure_initialized(ctx)

    if not confirm:
        click.echo("Use --confirm to reset jurisdiction manager state.")
        click.echo(f"This will reset to {to_jurisdiction.upper()} jurisdiction with full budget.")
        return

    manager = JurisdictionManager(to_jurisdiction.lower())
    save_jurisdiction_manager(gov_dir, manager)
    click.echo(f"Jurisdiction manager reset to {click.style(to_jurisdiction.upper(), fg='cyan')}.")


# ============================================================================
# Security Commands
# ============================================================================

@cli.group()
def security() -> None:
    """Security scanning and vulnerability detection."""
    pass


@security.command("scan")
@click.option("--path", "-p", default=".", help="Path to scan (file or directory)")
@click.option("--severity", "-s", type=click.Choice(["critical", "high", "medium", "low"]), default="low", help="Minimum severity to report")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def security_scan(ctx: click.Context, path: str, severity: str, json_output: bool) -> None:
    """Scan files for security vulnerabilities."""
    from .security import SecurityVerifier, SecurityConfig, Severity

    config = SecurityConfig(min_severity=Severity(severity))
    verifier = SecurityVerifier(config)

    scan_path = Path(path).resolve()

    if scan_path.is_file():
        findings = verifier.scan_file(scan_path)
    else:
        findings = verifier.scan_directory(scan_path)

    if json_output:
        click.echo(json.dumps([f.to_dict() for f in findings], indent=2))
        return

    if not findings:
        click.echo(click.style("No security issues found.", fg="green"))
        return

    # Group by severity
    by_severity: dict[str, list] = {}
    for f in findings:
        sev = f.severity.value
        if sev not in by_severity:
            by_severity[sev] = []
        by_severity[sev].append(f)

    click.echo(f"Found {len(findings)} security issue(s):\n")

    severity_order = ["critical", "high", "medium", "low"]
    severity_colors = {"critical": "red", "high": "yellow", "medium": "blue", "low": "white"}

    for sev in severity_order:
        if sev not in by_severity:
            continue
        findings_list = by_severity[sev]
        color = severity_colors[sev]

        click.echo(click.style(f"{sev.upper()} ({len(findings_list)})", fg=color, bold=True))
        for f in findings_list:
            click.echo(f"  {f.file_path}:{f.line_number}")
            click.echo(f"    [{f.vuln_type.value}] {f.message}")
            if f.suggestion:
                click.echo(f"    Suggestion: {f.suggestion}")
        click.echo()


@security.command("diff")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def security_diff(ctx: click.Context, json_output: bool) -> None:
    """Scan staged git changes for security vulnerabilities."""
    from .security import SecurityVerifier
    import subprocess

    # Get staged diff
    result = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        click.echo(click.style("Failed to get git diff.", fg="red"))
        return

    if not result.stdout.strip():
        click.echo("No staged changes.")
        return

    verifier = SecurityVerifier()
    findings = verifier.scan_diff(result.stdout)

    if json_output:
        click.echo(json.dumps([f.to_dict() for f in findings], indent=2))
        return

    if not findings:
        click.echo(click.style("No security issues in staged changes.", fg="green"))
        return

    click.echo(f"Found {len(findings)} security issue(s) in staged changes:\n")

    for f in findings:
        color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "white"}[f.severity.value]
        click.echo(click.style(f"  [{f.severity.value.upper()}] {f.vuln_type.value}", fg=color))
        click.echo(f"    {f.file_path}:{f.line_number}")
        click.echo(f"    {f.message}")
        if f.suggestion:
            click.echo(f"    Suggestion: {f.suggestion}")
        click.echo()


# ============================================================================
# Watch Commands
# ============================================================================

@cli.group()
def watch() -> None:
    """Watch mode for continuous file monitoring."""
    pass


@watch.command("start")
@click.option("--path", "-p", default=".", help="Path to watch")
@click.option("--interval", "-i", type=float, default=1.0, help="Poll interval in seconds")
@click.option("--no-security", is_flag=True, help="Disable security scanning")
@click.pass_context
def watch_start(ctx: click.Context, path: str, interval: float, no_security: bool) -> None:
    """Start watching for file changes."""
    from .watch import FileWatcher, WatchConfig, WatchEvent

    watch_path = Path(path).resolve()

    def on_event(event: WatchEvent) -> None:
        timestamp = event.timestamp.strftime("%H:%M:%S")

        if event.event_type == "change":
            change_type = event.data.get("change_type", "unknown")
            colors = {"created": "green", "modified": "yellow", "deleted": "red"}
            color = colors.get(change_type, "white")
            click.echo(f"[{timestamp}] {click.style(change_type.upper(), fg=color)} {event.data.get('path', '')}")

        elif event.event_type == "security":
            sev = event.data.get("severity", "low")
            color = {"critical": "red", "high": "yellow", "medium": "blue", "low": "white"}[sev]
            click.echo(f"[{timestamp}] {click.style('SECURITY', fg=color)} {event.message}")

        elif event.event_type == "status":
            click.echo(f"[{timestamp}] {click.style('STATUS', fg='cyan')} {event.message}")

        elif event.event_type == "error":
            click.echo(f"[{timestamp}] {click.style('ERROR', fg='red')} {event.message}")

    config = WatchConfig(
        poll_interval=interval,
        security_scan=not no_security,
        on_event=on_event,
    )

    watcher = FileWatcher(watch_path, config)

    click.echo(f"Watching {watch_path} (Ctrl+C to stop)...")
    watcher.initialize()
    watcher.run()


@watch.command("check")
@click.option("--path", "-p", default=".", help="Path to check")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def watch_check(ctx: click.Context, path: str, json_output: bool) -> None:
    """Check for changes once (non-blocking)."""
    from .watch import WatchSession

    watch_path = Path(path).resolve()
    session = WatchSession(watch_path)
    session.start()
    changes, findings = session.check()

    if json_output:
        click.echo(json.dumps({
            "changes": [c.to_dict() for c in changes],
            "findings": [f.to_dict() for f in findings],
        }, indent=2))
        return

    if not changes and not findings:
        click.echo("No changes detected.")
        return

    if changes:
        click.echo(f"Changes ({len(changes)}):")
        for c in changes:
            colors = {"created": "green", "modified": "yellow", "deleted": "red"}
            color = colors.get(c.change_type, "white")
            click.echo(f"  {click.style(c.change_type.upper(), fg=color)} {c.path}")

    if findings:
        click.echo(f"\nSecurity findings ({len(findings)}):")
        for f in findings:
            click.echo(f"  [{f.severity.value}] {f.file_path}:{f.line_number} - {f.message}")


# ============================================================================
# Claude Code Hooks Commands
# ============================================================================

@cli.group("claude-hooks")
def claude_hooks() -> None:
    """Claude Code integration hooks."""
    pass


@claude_hooks.command("install")
@click.option("--no-pre", is_flag=True, help="Don't install pre-tool hook")
@click.option("--no-post", is_flag=True, help="Don't install post-tool hook")
@click.option("--no-notify", is_flag=True, help="Don't install notification hook")
@click.pass_context
def claude_hooks_install(ctx: click.Context, no_pre: bool, no_post: bool, no_notify: bool) -> None:
    """Install Claude Code hooks for governor integration."""
    from .claude_hooks import install_claude_hooks, HookConfig, create_blocked_commands_file

    root = Path(ctx.obj["root"])

    config = HookConfig(
        pre_tool_use=not no_pre,
        post_tool_use=not no_post,
        notification=not no_notify,
    )

    success, message = install_claude_hooks(root, config)

    if success:
        click.echo(click.style("Claude Code hooks installed.", fg="green"))
        click.echo(f"  {message}")

        # Create blocked commands file
        blocked_file = create_blocked_commands_file(root)
        click.echo(f"  Created: {blocked_file}")

        click.echo()
        click.echo("Hooks will intercept file/command operations.")
        click.echo("Configure approved files: .governor/approved_files.json")
        click.echo("Configure blocked commands: .governor/blocked_commands.json")
    else:
        click.echo(click.style(f"Failed: {message}", fg="red"))


@claude_hooks.command("uninstall")
@click.pass_context
def claude_hooks_uninstall(ctx: click.Context) -> None:
    """Uninstall Claude Code hooks."""
    from .claude_hooks import uninstall_claude_hooks

    root = Path(ctx.obj["root"])
    success, message = uninstall_claude_hooks(root)

    if success:
        click.echo(click.style("Claude Code hooks uninstalled.", fg="green"))
        click.echo(f"  {message}")
    else:
        click.echo(click.style(f"Failed: {message}", fg="red"))


@claude_hooks.command("status")
@click.pass_context
def claude_hooks_status(ctx: click.Context) -> None:
    """Show Claude Code hooks status."""
    from .claude_hooks import get_hook_status

    root = Path(ctx.obj["root"])
    status = get_hook_status(root)

    click.echo("Claude Code Hooks Status:")
    click.echo(f"  Hooks directory exists: {'yes' if status['hooks_dir_exists'] else 'no'}")

    if status["scripts_installed"]:
        click.echo(f"  Scripts installed: {', '.join(status['scripts_installed'])}")
    else:
        click.echo("  Scripts installed: none")

    click.echo(f"  Claude settings exists: {'yes' if status['claude_settings_exists'] else 'no'}")

    if status["hooks_configured"]:
        click.echo(f"  Hooks configured: {', '.join(status['hooks_configured'])}")
    else:
        click.echo("  Hooks configured: none")


@claude_hooks.command("approve")
@click.argument("files", nargs=-1)
@click.pass_context
def claude_hooks_approve(ctx: click.Context, files: tuple[str, ...]) -> None:
    """Add files to the approved list."""
    from .claude_hooks import create_approved_files_file

    root = Path(ctx.obj["root"])
    gov_dir = root / ".governor"

    # Load existing approved files
    approved_file = gov_dir / "approved_files.json"
    if approved_file.exists():
        approved = set(json.loads(approved_file.read_text()))
    else:
        approved = set()

    # Add new files
    for f in files:
        approved.add(f)

    create_approved_files_file(root, list(approved))
    click.echo(f"Approved {len(files)} file(s). Total approved: {len(approved)}")


@claude_hooks.command("block")
@click.argument("pattern")
@click.pass_context
def claude_hooks_block(ctx: click.Context, pattern: str) -> None:
    """Add a command pattern to the blocked list."""
    root = Path(ctx.obj["root"])
    gov_dir = root / ".governor"

    # Load existing blocked patterns
    blocked_file = gov_dir / "blocked_commands.json"
    if blocked_file.exists():
        blocked = json.loads(blocked_file.read_text())
    else:
        blocked = []

    if pattern not in blocked:
        blocked.append(pattern)
        blocked_file.write_text(json.dumps(blocked, indent=2))
        click.echo(f"Added blocked pattern: {pattern}")
    else:
        click.echo(f"Pattern already blocked: {pattern}")


# ============================================================================
# Routing Commands
# ============================================================================

@cli.group()
def routing() -> None:
    """Multi-agent routing: route tasks to appropriate model tiers."""
    pass


@routing.command("status")
@click.pass_context
def routing_status(ctx: click.Context) -> None:
    """Show routing configuration and model registry status."""
    from .routing import Router

    gov_dir = ensure_initialized(ctx)
    router = Router()

    click.echo("Routing Configuration:")
    click.echo(f"  Enabled: {router.config.enabled}")
    click.echo(f"  Default tier: {router.config.default_tier.value}")
    click.echo(f"  Adaptive routing: {router.config.adaptive_enabled}")
    click.echo()

    click.echo("Tier Thresholds:")
    click.echo(f"  LOCAL max complexity: {router.config.local_max_complexity}")
    click.echo(f"  FAST max complexity: {router.config.fast_max_complexity}")
    click.echo(f"  STANDARD max complexity: {router.config.standard_max_complexity}")
    click.echo()

    click.echo("Model Registry:")
    registry_data = router.registry.to_dict()
    for name, model in registry_data["models"].items():
        status = registry_data["status"].get(name, {})
        available = "✓" if status.get("available", True) else "✗"
        tier = model["tier"]
        in_flight = status.get("tasks_in_flight", 0)
        success = status.get("success_rate", 1.0)
        click.echo(f"  [{available}] {name} ({tier}) - {in_flight} in flight, {success:.0%} success")


@routing.command("models")
@click.option("--tier", "-t", type=click.Choice(["local", "fast", "standard", "heavy"]), help="Filter by tier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def routing_models(tier: str | None, as_json: bool) -> None:
    """List registered models and their capabilities."""
    import json
    from .routing import Router, ModelTier

    router = Router()
    data = router.registry.to_dict()

    if tier:
        tier_filter = ModelTier(tier)
        filtered = {
            name: model
            for name, model in data["models"].items()
            if ModelTier(model["tier"]) == tier_filter
        }
        data["models"] = filtered

    if as_json:
        click.echo(json.dumps(data, indent=2))
    else:
        for name, model in data["models"].items():
            status = data["status"].get(name, {})
            click.echo(f"\n{name}:")
            click.echo(f"  Tier: {model['tier']}")
            click.echo(f"  Context window: {model['context_window']:,}")
            click.echo(f"  Code quality: {model['code_quality']:.0%}")
            click.echo(f"  Available: {status.get('available', True)}")
            if status.get("tasks_in_flight", 0) > 0:
                click.echo(f"  Tasks in flight: {status['tasks_in_flight']}")


@routing.command("estimate")
@click.argument("description")
@click.option("--files", "-f", multiple=True, help="Files involved")
@click.option("--claim-type", "-c", type=click.Choice([
    "file_exists", "symbol_defined", "api_surface",
    "tests_pass", "decision", "changeset"
]), help="Claim type")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def routing_estimate(
    description: str,
    files: tuple[str, ...],
    claim_type: str | None,
    as_json: bool
) -> None:
    """Estimate complexity and recommended tier for a task."""
    import json
    from .routing import estimate_complexity
    from .claims import Claim, ClaimType

    claims = []
    if claim_type:
        ct = ClaimType(claim_type)
        if ct == ClaimType.FILE_EXISTS and files:
            claims = [Claim(type=ct, path=f) for f in files]
        elif ct == ClaimType.TESTS_PASS:
            claims = [Claim(type=ct, command=("pytest",))]

    estimate = estimate_complexity(claims, description, list(files))

    if as_json:
        output = {
            "score": estimate.score,
            "recommended_tier": estimate.recommended_tier.value,
            "is_simple": estimate.is_simple,
            "is_moderate": estimate.is_moderate,
            "is_complex": estimate.is_complex,
            "factors": estimate.factors,
            "reasoning": estimate.reasoning,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"Complexity Score: {estimate.score:.2f}")
        click.echo(f"Recommended Tier: {estimate.recommended_tier.value.upper()}")
        click.echo(f"Reasoning: {estimate.reasoning}")
        click.echo()
        click.echo("Factors:")
        for factor, value in estimate.factors.items():
            click.echo(f"  {factor}: {value:.2f}")


@routing.command("route")
@click.argument("description")
@click.option("--files", "-f", multiple=True, help="Files involved")
@click.option("--force-tier", "-t", type=click.Choice(["local", "fast", "standard", "heavy"]), help="Force specific tier")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def routing_route(
    description: str,
    files: tuple[str, ...],
    force_tier: str | None,
    as_json: bool
) -> None:
    """Route a task to a model and show the decision."""
    import json
    from .routing import Router, ModelTier

    router = Router()

    tier = ModelTier(force_tier) if force_tier else None
    decision = router.route(
        claims=[],
        description=description,
        files=list(files),
        force_tier=tier,
    )

    if as_json:
        output = {
            "task_id": str(decision.task_id),
            "selected_model": decision.selected_model,
            "selected_tier": decision.selected_tier.value,
            "complexity_score": decision.complexity.score,
            "fallback_models": decision.fallback_models,
            "reasoning": decision.reasoning,
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"Task ID: {decision.task_id}")
        click.echo(f"Selected Model: {decision.selected_model}")
        click.echo(f"Selected Tier: {decision.selected_tier.value.upper()}")
        click.echo(f"Complexity: {decision.complexity.score:.2f}")
        click.echo(f"Reasoning: {decision.reasoning}")
        if decision.fallback_models:
            click.echo(f"Fallbacks: {', '.join(decision.fallback_models[:3])}")


@routing.command("register")
@click.argument("name")
@click.option("--tier", "-t", required=True, type=click.Choice(["local", "fast", "standard", "heavy"]), help="Model tier")
@click.option("--context-window", "-c", default=8192, help="Context window size")
@click.option("--code-quality", "-q", default=0.5, help="Code quality score (0-1)")
def routing_register(
    name: str,
    tier: str,
    context_window: int,
    code_quality: float
) -> None:
    """Register a custom model in the registry."""
    from .routing import Router, ModelTier, ModelCapabilities

    router = Router()
    caps = ModelCapabilities(
        name=name,
        tier=ModelTier(tier),
        context_window=context_window,
        code_quality=code_quality,
    )
    router.registry.register(caps)
    click.echo(f"Registered model: {name} (tier: {tier})")


@routing.command("available")
@click.argument("name")
@click.option("--set/--unset", "available", default=True, help="Set availability")
def routing_available(name: str, available: bool) -> None:
    """Set model availability status."""
    from .routing import Router

    router = Router()
    if router.registry.get_capabilities(name) is None:
        click.echo(f"Model not found: {name}", err=True)
        raise SystemExit(1)

    router.registry.mark_available(name, available)
    status = "available" if available else "unavailable"
    click.echo(f"Marked {name} as {status}")


# =============================================================================
# Scar Commands (Failure Provenance & Constraint Hysteresis)
# =============================================================================


@cli.group()
def scar():
    """Failure provenance & constraint hysteresis (scars and shields)."""
    pass


@scar.command("list")
@click.option("--hard", is_flag=True, help="Show only hard scars (full veto)")
@click.option("--soft", is_flag=True, help="Show only soft scars (relaxed)")
@click.pass_context
def scar_list(ctx, hard, soft):
    """List all scars (action restrictions from internal failures)."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo("No scar ledger found. No failures recorded yet.")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))

    if hard:
        scars = ledger.get_hard_scars()
        label = "hard"
    elif soft:
        scars = ledger.get_soft_scars()
        label = "soft"
    else:
        scars = ledger.get_active_scars()
        label = "all"

    if not scars:
        click.echo(f"No {label} scars found.")
        return

    click.echo(f"\n{label.upper()} SCARS ({len(scars)}):")
    click.echo("-" * 60)
    for s in scars:
        status = "HARD" if s.is_hard else f"soft ({s.stiffness:.2f})"
        click.echo(f"  {s.scar_id}: {s.region}")
        click.echo(f"    stiffness: {s.stiffness:.3f} [{status}]  cost: {s.effective_cost:.1f}x")
        click.echo(f"    evidence: {s.evidence_count}/{s.required_evidence}  provenance: {s.provenance.value}")
        if s.description:
            click.echo(f"    desc: {s.description}")
        click.echo()


@scar.command("shields")
@click.pass_context
def scar_shields(ctx):
    """List all shields (input restrictions from external failures)."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo("No scar ledger found.")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))
    shields = ledger.get_active_shields()

    if not shields:
        click.echo("No active shields.")
        return

    click.echo(f"\nACTIVE SHIELDS ({len(shields)}):")
    click.echo("-" * 60)
    for s in shields:
        blocked = "BLOCKED" if s.is_fully_blocked else f"{s.permeability:.0%} open"
        click.echo(f"  {s.shield_id}: {s.source}")
        click.echo(f"    permeability: {blocked}  severity: {s.severity:.2f}")
        click.echo(f"    stable cycles: {s.stable_cycles_observed}/{s.stable_cycles_required}")
        click.echo()


@scar.command("history")
@click.option("--limit", "-n", default=20, help="Number of events to show")
@click.option("--region", "-r", default=None, help="Filter by region")
@click.pass_context
def scar_history(ctx, limit, region):
    """Show failure history with provenance classification."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo("No scar ledger found.")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))

    if region:
        events = ledger.get_failures_by_region(region)
    else:
        events = ledger.get_failure_history(limit=limit)

    if not events:
        click.echo("No failure events recorded.")
        return

    click.echo(f"\nFAILURE HISTORY ({len(events)} events):")
    click.echo("-" * 70)
    for e in events:
        prov = e.provenance.value if e.provenance else "unknown"
        click.echo(f"  [{e.timestamp.strftime('%Y-%m-%d %H:%M')}] {e.region}")
        click.echo(f"    provenance: {prov}  rho: {e.surprise_ratio:.3f}  response: {e.response_type}")
        if e.description:
            click.echo(f"    desc: {e.description}")
        click.echo()


@scar.command("anneal")
@click.option("--region", "-r", default=None, help="Record evidence for specific region")
@click.option("--dry-run", is_flag=True, help="Show what would be annealed without doing it")
@click.pass_context
def scar_anneal(ctx, region, dry_run):
    """Anneal scars (relax stiffness under evidence of stability)."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo("No scar ledger found.")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))

    if region:
        # Record evidence for a specific region
        if ledger.record_stability_evidence(region):
            click.echo(f"Recorded stability evidence for: {region}")
        else:
            click.echo(f"No scar found for region: {region}")
            return

    # Show what can be annealed
    annealable = [s for s in ledger.get_active_scars() if s.can_anneal()]
    if not annealable:
        click.echo("No scars ready for annealing (need more evidence).")
        for s in ledger.get_active_scars():
            click.echo(f"  {s.region}: {s.evidence_count}/{s.required_evidence} evidence")
        return

    if dry_run:
        click.echo(f"\nWould anneal {len(annealable)} scars:")
        for s in annealable:
            click.echo(f"  {s.region}: {s.stiffness:.3f} -> ~{max(s.anneal_floor, s.stiffness * 0.9):.3f}")
        return

    results = ledger.anneal_scars()

    if results:
        click.echo(f"\nAnnealed {len(results)} scars:")
        for scar_id, amount in results.items():
            scar = ledger.get_scar(scar_id)
            click.echo(f"  {scar.region}: relaxed by {amount:.3f} -> {scar.stiffness:.3f}")

        # Save
        scar_path.write_text(json.dumps(ledger.to_dict(), indent=2, default=str))
        click.echo("Saved.")
    else:
        click.echo("No scars were annealed.")


@scar.command("stats")
@click.pass_context
def scar_stats(ctx):
    """Show scar/shield statistics and system health."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo("No scar ledger found. System is unscarred.")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))
    metrics = ledger.get_metrics()
    summary = ledger.get_summary()

    click.echo(f"\nSCAR SYSTEM STATUS: {summary['health']}")
    click.echo("=" * 50)
    click.echo(f"  Failures: {summary['failures']}")
    click.echo(f"  Scars:    {summary['scars']}")
    click.echo(f"  Shields:  {summary['shields']}")
    click.echo()
    click.echo("Metrics:")
    click.echo(f"  avg stiffness:    {metrics['avg_stiffness']:.3f}")
    click.echo(f"  avg permeability: {metrics['avg_permeability']:.3f}")
    click.echo(f"  total anneals:    {metrics['total_anneals']}")
    click.echo(f"  shield releases:  {metrics['total_shield_releases']}")
    click.echo()
    click.echo("Config:")
    click.echo(f"  rho_lo: {ledger.config.rho_lo}  rho_hi: {ledger.config.rho_hi}")
    click.echo(f"  regularity_bound: {ledger.config.regularity_bound}")


@scar.command("record")
@click.argument("region")
@click.option("--obs-shift", type=float, default=0.0, help="Observation shift (delta_y)")
@click.option("--pred-error", type=float, default=1.0, help="Prediction error")
@click.option("--magnitude", type=float, default=1.0, help="Error magnitude")
@click.option("--source", type=str, default=None, help="Input source (for shields)")
@click.option("--description", "-d", type=str, default="", help="Description")
@click.pass_context
def scar_record(ctx, region, obs_shift, pred_error, magnitude, source, description):
    """Record a failure event and classify provenance."""
    from .scars import ScarLedger, ScarConfig

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if scar_path.exists():
        ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))
    else:
        ledger = ScarLedger()

    event = ledger.record_failure(
        region=region,
        observation_shift=obs_shift,
        prediction_error=pred_error,
        error_magnitude=magnitude,
        description=description,
        source=source,
    )

    prov = event.provenance.value if event.provenance else "unknown"
    click.echo(f"Failure recorded: {event.event_id}")
    click.echo(f"  provenance: {prov}  rho: {event.surprise_ratio:.3f}")
    click.echo(f"  response: {event.response_type}")

    if event.scar_id:
        scar = ledger.get_scar(event.scar_id)
        click.echo(f"  scar: {event.scar_id} (stiffness: {scar.stiffness:.3f})")
    if event.shield_id:
        shield = ledger.get_shield(event.shield_id)
        click.echo(f"  shield: {event.shield_id} (permeability: {shield.permeability:.3f})")

    # Save
    scar_path.write_text(json.dumps(ledger.to_dict(), indent=2, default=str))


@scar.command("check")
@click.argument("region")
@click.pass_context
def scar_check(ctx, region):
    """Check if an action in a region is admissible."""
    from .scars import ScarLedger

    gov_dir = ensure_initialized(ctx)
    scar_path = gov_dir / "scars.json"

    if not scar_path.exists():
        click.echo(f"ADMISSIBLE: {region} (no scar ledger)")
        return

    ledger = ScarLedger.from_dict(json.loads(scar_path.read_text()))
    admissible, cost, scar = ledger.check_admissible(region)

    if admissible:
        if scar:
            click.echo(f"ADMISSIBLE (with cost): {region}")
            click.echo(f"  cost multiplier: {cost:.1f}x")
            click.echo(f"  scar stiffness: {scar.stiffness:.3f}")
        else:
            click.echo(f"ADMISSIBLE: {region} (no scar)")
    else:
        click.echo(f"BLOCKED: {region}")
        click.echo(f"  scar: {scar.scar_id} (stiffness: {scar.stiffness:.3f})")
        click.echo(f"  cost: {cost:.1f}x")
        click.echo("  Action requires annealing or explicit override.")


# =============================================================================
# Ultrastability (S₁ Adaptive Control)
# =============================================================================


@cli.group("adapt")
@click.pass_context
def adapt_cmd(ctx):
    """Ultrastability controller — S₁ adaptive parameter tuning."""
    pass


@adapt_cmd.command("status")
@click.pass_context
def adapt_status(ctx):
    """Show current ultrastability state."""
    from .ultrastability import UltrastabilityController

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if not adapt_path.exists():
        ctrl = UltrastabilityController()
        click.echo("Ultrastability: not initialized (showing defaults)")
    else:
        ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))

    state = ctrl.get_state()
    click.echo(f"Epoch: {state['epoch']}")
    frozen_status = click.style("FROZEN", fg="red") if state["frozen"] else click.style("active", fg="green")
    click.echo(f"Status: {frozen_status}")
    if state["freeze_reason"]:
        click.echo(f"Freeze reason: {state['freeze_reason']}")
    if state["freeze_pathologies"]:
        click.echo(f"Pathologies: {', '.join(state['freeze_pathologies'])}")
    click.echo(f"Recent epochs: {state['recent_epochs']}")
    click.echo(f"Total adaptations: {state['total_adaptations']}")


@adapt_cmd.command("params")
@click.pass_context
def adapt_params(ctx):
    """Show current S₁ regulatory parameters."""
    from .ultrastability import UltrastabilityController

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if adapt_path.exists():
        ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))
    else:
        ctrl = UltrastabilityController()

    click.echo("S₁ Regulatory Parameters:")
    for spec in ctrl.parameters.all_specs:
        bar_len = int(spec.normalized * 20)
        bar = "#" * bar_len + "." * (20 - bar_len)
        click.echo(f"  {spec.name:25s} {spec.current:>10.1f}  [{spec.floor:.0f}-{spec.ceiling:.0f}]  [{bar}]")
        if spec.description:
            click.echo(f"  {'':25s} {spec.description}")


@adapt_cmd.command("history")
@click.option("-n", "--limit", type=int, default=20, help="Number of records")
@click.pass_context
def adapt_history(ctx, limit):
    """Show adaptation history."""
    from .ultrastability import UltrastabilityController

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if not adapt_path.exists():
        click.echo("No adaptation history.")
        return

    ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))
    records = ctrl.history.records[-limit:]

    if not records:
        click.echo("No adaptations recorded.")
        return

    click.echo(f"Adaptation history (last {limit}):")
    for r in records:
        direction = "+" if r.direction.value == "increase" else "-"
        clamped = " [CLAMPED]" if r.was_clamped else ""
        click.echo(f"  epoch {r.epoch_id}: {r.parameter} {r.old_value:.1f} → {r.new_value:.1f} ({direction}{abs(r.delta):.1f}){clamped}")
        click.echo(f"    reason: {r.reason}")


@adapt_cmd.command("consider")
@click.option("--turns", type=int, default=100, help="Turns in epoch")
@click.option("--blocks", type=int, default=0, help="Budget blocks")
@click.option("--c-open", type=int, default=0, help="Open contradictions")
@click.option("--violations", type=int, default=0, help="Violations")
@click.option("--dangerous", type=int, default=0, help="Dangerous claims")
@click.option("--regime", type=str, default="ELASTIC", help="Current regime")
@click.option("--apply", "apply_decision", is_flag=True, help="Apply if ADAPT")
@click.pass_context
def adapt_consider(ctx, turns, blocks, c_open, violations, dangerous, regime, apply_decision):
    """Observe an epoch and consider adaptation."""
    from .ultrastability import UltrastabilityController, EpochObservation

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if adapt_path.exists():
        ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))
    else:
        ctrl = UltrastabilityController()

    obs = EpochObservation(
        turns=turns,
        budget_blocks=blocks,
        c_open=c_open,
        violations=violations,
        dangerous_claims=dangerous,
        regime=regime,
    )
    ctrl.observe_epoch(obs)

    decision = ctrl.consider_adaptation()

    verdict_colors = {
        "hold": "green", "adapt": "yellow", "freeze": "red", "alert": "red",
    }
    click.secho(f"Verdict: {decision.verdict.value}", fg=verdict_colors.get(decision.verdict.value, "white"))
    click.echo(f"Reason: {decision.reason}")

    if decision.parameter:
        click.echo(f"Parameter: {decision.parameter}")
        click.echo(f"  {decision.current_value:.1f} → {decision.proposed_value:.1f} (Δ{decision.delta:+.1f})")

    if decision.pathologies:
        click.echo(f"Pathologies: {', '.join(p.value for p in decision.pathologies)}")

    if apply_decision and decision.verdict.value == "adapt":
        ctrl.apply_adaptation(decision)
        click.echo("Applied.")

    ctrl.advance_epoch()
    adapt_path.write_text(json.dumps(ctrl.to_dict(), indent=2, default=str))
    click.echo("State saved.")


@adapt_cmd.command("unfreeze")
@click.argument("reason")
@click.pass_context
def adapt_unfreeze(ctx, reason):
    """Unfreeze adaptation after human review."""
    from .ultrastability import UltrastabilityController

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if not adapt_path.exists():
        click.echo("No ultrastability state.")
        return

    ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))

    if not ctrl.frozen:
        click.echo("Controller is not frozen.")
        return

    ctrl.unfreeze(reason)
    adapt_path.write_text(json.dumps(ctrl.to_dict(), indent=2, default=str))
    click.secho("Unfrozen.", fg="green")
    click.echo(f"Reason: {reason}")


@adapt_cmd.command("metrics")
@click.pass_context
def adapt_metrics(ctx):
    """Show adaptation metrics."""
    from .ultrastability import UltrastabilityController

    gov_dir = ensure_initialized(ctx)
    adapt_path = gov_dir / "ultrastability.json"

    if not adapt_path.exists():
        click.echo("No adaptation data.")
        return

    ctrl = UltrastabilityController.from_dict(json.loads(adapt_path.read_text()))
    m = ctrl.get_metrics()

    click.echo("Ultrastability Metrics")
    click.echo(f"  total epochs:      {m['total_epochs']}")
    click.echo(f"  total adaptations: {m['total_adaptations']}")
    click.echo(f"  clamped:           {m['clamped_count']}")
    frozen_status = click.style("YES", fg="red") if m["frozen"] else "no"
    click.echo(f"  frozen:            {frozen_status}")

    if m["adaptations_by_parameter"]:
        click.echo()
        click.echo("  By parameter:")
        for param, count in sorted(m["adaptations_by_parameter"].items(), key=lambda x: x[1], reverse=True):
            click.echo(f"    {param}: {count}")

    click.echo()
    click.echo("  By direction:")
    click.echo(f"    increase: {m['adaptations_by_direction']['increase']}")
    click.echo(f"    decrease: {m['adaptations_by_direction']['decrease']}")


# =============================================================================
# Grounding Audit Pipeline
# =============================================================================


@cli.group("audit")
@click.pass_context
def audit_cmd(ctx):
    """Grounding audit pipeline — hallucination detection and prevention."""
    pass


@audit_cmd.command("run")
@click.argument("assertion_id")
@click.option("--evidence-count", "-e", type=int, default=0, help="Number of evidence items")
@click.option("--evidence-strength", "-s", type=float, default=0.0, help="Sum of evidence strengths")
@click.option("--novel-numbers", "-n", type=int, default=0, help="Novel numbers in claim")
@click.option("--claim-type", "-t", type=click.Choice(["static_fact", "volatile_fact", "code", "math", "procedure", "judgment"]), default="static_fact")
@click.option("--risk", "-r", type=click.Choice(["low", "medium", "high"]), default="low")
@click.option("--scope", type=click.Choice(["internal_premise", "user_output", "action_trigger"]), default="user_output")
@click.option("--stage", type=click.Choice(["pre_commit", "post_commit", "periodic", "incident"]), default="pre_commit")
@click.option("--counterevidence", is_flag=True, help="Flag that counter-evidence exists")
@click.pass_context
def audit_run(ctx, assertion_id, evidence_count, evidence_strength, novel_numbers,
              claim_type, risk, scope, stage, counterevidence):
    """Run a grounding audit on an assertion."""
    from .audit import (
        AuditPipeline, AuditStage, ClaimRisk, AssertionScope,
        DetectionSignals,
    )

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if audit_path.exists():
        pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))
    else:
        pipeline = AuditPipeline()

    signals = DetectionSignals(
        evidence_count=evidence_count,
        evidence_strength_sum=evidence_strength,
        novel_number_count=novel_numbers,
    )

    result = pipeline.audit(
        assertion_id=assertion_id,
        signals=signals,
        claim_type=claim_type,
        risk=ClaimRisk(risk),
        scope=AssertionScope(scope),
        stage=AuditStage(stage),
        has_counterevidence=counterevidence,
    )

    audit_path.write_text(json.dumps(pipeline.to_dict(), indent=2, default=str))

    # Display result
    status_colors = {
        "grounded": "green",
        "weak": "yellow",
        "ungrounded": "red",
        "contradicted": "red",
        "unknown": "yellow",
    }
    decision_colors = {
        "allow_hard": "green",
        "downgrade_soft": "yellow",
        "block": "red",
        "needs_more_work": "yellow",
    }

    click.echo(f"Audit: {result.audit_id}")
    click.echo(f"  assertion: {result.assertion_id}")
    click.echo(f"  stage:     {result.stage.value}")
    click.secho(f"  status:    {result.status.value}", fg=status_colors.get(result.status.value, "white"))
    click.secho(f"  decision:  {result.decision.value}", fg=decision_colors.get(result.decision.value, "white"))
    click.echo(f"  severity:  {result.severity.value}")

    if result.failure_modes:
        modes = ", ".join(m.value for m in result.failure_modes)
        click.echo(f"  failures:  {modes}")

    if result.leak_score > 0:
        click.echo(f"  leak_score: {result.leak_score:.1f}")


@audit_cmd.command("history")
@click.option("-n", "--limit", type=int, default=20, help="Number of recent audits")
@click.option("--problematic", is_flag=True, help="Show only problematic audits")
@click.pass_context
def audit_history(ctx, limit, problematic):
    """Show recent audit history."""
    from .audit import AuditPipeline

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if not audit_path.exists():
        click.echo("No audit history. Run 'governor audit run' first.")
        return

    pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))

    if problematic:
        audits = pipeline.get_problematic_audits(limit)
        click.echo(f"Problematic audits (last {limit}):")
    else:
        audits = pipeline.get_recent_audits(limit)
        click.echo(f"Recent audits (last {limit}):")

    if not audits:
        click.echo("  (none)")
        return

    for a in audits:
        status_icon = {"grounded": "+", "weak": "~", "ungrounded": "!", "contradicted": "X", "unknown": "?"}
        icon = status_icon.get(a.status.value, "?")
        modes = ", ".join(m.value for m in a.failure_modes) if a.failure_modes else "-"
        click.echo(f"  [{icon}] {a.audit_id} | {a.assertion_id} | {a.stage.value} | {a.status.value} | {a.decision.value} | {modes}")


@audit_cmd.command("policy")
@click.option("--claim-type", "-t", type=str, default=None, help="Filter by claim type")
@click.option("--risk", "-r", type=click.Choice(["low", "medium", "high"]), default=None)
@click.pass_context
def audit_policy(ctx, claim_type, risk):
    """Show current policy thresholds."""
    from .audit import AuditPipeline, ClaimRisk

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if audit_path.exists():
        pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))
    else:
        pipeline = AuditPipeline()

    click.echo(f"Policy entries: {len(pipeline.policy_store.policies)}")
    click.echo(f"Adjustments made: {len(pipeline.policy_store.adjustment_history)}")
    click.echo()

    for key, entry in sorted(pipeline.policy_store.policies.items()):
        if claim_type and entry.claim_type != claim_type:
            continue
        if risk and entry.risk != ClaimRisk(risk):
            continue

        click.echo(f"  {key}:")
        click.echo(f"    k_required={entry.k_required}  independence={entry.independence_threshold:.2f}  "
                    f"min_strength={entry.min_evidence_strength:.2f}")
        click.echo(f"    max_novel_numbers={entry.max_novel_numbers}  max_specious={entry.max_specious_precision:.2f}  "
                    f"ttl={entry.ttl_seconds:.0f}s  stabilization={entry.stabilization_rounds}")


@audit_cmd.command("stats")
@click.pass_context
def audit_stats(ctx):
    """Show audit pipeline statistics."""
    from .audit import AuditPipeline

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if not audit_path.exists():
        click.echo("No audit data. Run 'governor audit run' first.")
        return

    pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))
    m = pipeline.get_metrics()

    click.echo("Audit Pipeline Statistics")
    click.echo(f"  total audits:      {m['total_audits']}")
    click.echo(f"  clean:             {m['total_clean']} ({m['clean_rate']:.1%})")
    click.echo(f"  problematic:       {m['total_problematic']} ({m['problematic_rate']:.1%})")
    click.echo(f"  policy adjustments: {m['policy_adjustments']}")

    if m["top_failure_modes"]:
        click.echo()
        click.echo("  Top failure modes:")
        for mode, count in m["top_failure_modes"]:
            click.echo(f"    {mode}: {count}")


@audit_cmd.command("adapt")
@click.option("--window", "-w", type=int, default=50, help="Window size for rate calculation")
@click.option("--dry-run", is_flag=True, help="Show what would change without applying")
@click.pass_context
def audit_adapt(ctx, window, dry_run):
    """Run adaptive threshold tuning based on recent audit outcomes."""
    from .audit import AuditPipeline

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if not audit_path.exists():
        click.echo("No audit data. Run audits first.")
        return

    pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))

    if dry_run:
        # Compute but don't save
        adjustments = pipeline.adapt_thresholds(window)
        if not adjustments:
            click.echo("No adjustments needed (rates below thresholds or insufficient data).")
        else:
            click.echo(f"Would make {len(adjustments)} adjustment(s):")
            for adj in adjustments:
                click.echo(f"  {adj['key']}: {adj['field']} by {adj['amount']} ({adj['reason']})")
    else:
        adjustments = pipeline.adapt_thresholds(window)
        if not adjustments:
            click.echo("No adjustments needed.")
        else:
            click.echo(f"Applied {len(adjustments)} adjustment(s):")
            for adj in adjustments:
                click.echo(f"  {adj['key']}: {adj['field']} by {adj['amount']} ({adj['reason']})")
            audit_path.write_text(json.dumps(pipeline.to_dict(), indent=2, default=str))
            click.echo("Pipeline state saved.")


@audit_cmd.command("rates")
@click.option("--window", "-w", type=int, default=100, help="Window size")
@click.pass_context
def audit_rates(ctx, window):
    """Show failure mode rates over recent window."""
    from .audit import AuditPipeline

    gov_dir = ensure_initialized(ctx)
    audit_path = gov_dir / "audit_pipeline.json"

    if not audit_path.exists():
        click.echo("No audit data.")
        return

    pipeline = AuditPipeline.from_dict(json.loads(audit_path.read_text()))
    rates = pipeline.get_failure_mode_rates(window)

    if not rates:
        click.echo("No failure modes recorded.")
        return

    click.echo(f"Failure mode rates (window={window}):")
    for mode, rate in sorted(rates.items(), key=lambda x: x[1], reverse=True):
        bar = "#" * int(rate * 40)
        click.echo(f"  {mode:30s} {rate:5.1%} {bar}")


# ── Homeostat (exploration budgets, adaptive gain scheduling) ─────────────────

@cli.group("explore")
@click.pass_context
def explore_cmd(ctx):
    """Homeostat — exploration budgets and adaptive gain scheduling."""
    pass


@explore_cmd.command("status")
@click.pass_context
def explore_status(ctx):
    """Show homeostat state: mode, context, budget, urgency."""
    from .homeostat import Homeostat

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if not homeo_path.exists():
        click.echo("Homeostat not initialised. Run 'governor explore observe' first.")
        return

    h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    diag = h.get_diagnostics()

    click.echo(f"Mode:             {diag['mode']}")
    click.echo(f"Context:          {diag['context']}")
    click.echo(f"Description:      {diag['context_description']}")
    click.echo(f"EMA urgency:      {diag['ema_urgency']:.4f}")
    click.echo(f"Effective urgency: {diag['effective_urgency']:.4f}")
    click.echo(f"Urgency trend:    {diag['urgency_trend']:+.6f}")
    click.echo(f"Observations:     {diag['observations']}")
    click.echo(f"Transitions:      {diag['transitions']}")
    budget = diag["budget"]
    click.echo(f"Budget:           {budget['remaining']:.2f} / {budget['max_budget']:.1f}"
               f"  (can_explore={budget['can_explore']})")


@explore_cmd.command("enter")
@click.argument("context")
@click.pass_context
def explore_enter(ctx, context):
    """Enter an exploration context (research, brainstorm, hypothesis, synthesis, devils_advocate, calibration)."""
    from .homeostat import Homeostat, ExplorationContext

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if not homeo_path.exists():
        click.echo("Homeostat not initialised. Run 'governor explore observe' first.")
        return

    try:
        ec = ExplorationContext(context)
    except ValueError:
        click.echo(f"Unknown context: {context}")
        click.echo(f"Available: {', '.join(c.value for c in ExplorationContext)}")
        return

    h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    ok = h.enter_exploration(ec)
    if ok:
        homeo_path.write_text(json.dumps(h.to_dict(), indent=2, default=str))
        p = h.get_profile()
        click.echo(f"Entered: {ec.value}")
        click.echo(f"  {p.description}")
        click.echo(f"  Budget cost/turn: {p.budget_cost:.2f}")
        click.echo(f"  Urgency dampening: {p.urgency_dampening:.1%}")
        click.echo(f"  Commitment tentativeness: {p.commitment_tentativeness:.1%}")
    else:
        click.echo(f"Cannot enter {ec.value}: insufficient exploration budget "
                    f"({h.budget.remaining:.2f} < {h.budget.min_to_explore:.2f})")


@explore_cmd.command("exit")
@click.pass_context
def explore_exit(ctx):
    """Return to standard context."""
    from .homeostat import Homeostat

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if not homeo_path.exists():
        click.echo("Homeostat not initialised.")
        return

    h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    h.exit_exploration()
    homeo_path.write_text(json.dumps(h.to_dict(), indent=2, default=str))
    click.echo(f"Returned to standard. Budget: {h.budget.remaining:.2f}")


@explore_cmd.command("budget")
@click.pass_context
def explore_budget(ctx):
    """Show exploration budget status."""
    from .homeostat import Homeostat

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if not homeo_path.exists():
        click.echo("Homeostat not initialised.")
        return

    h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    b = h.budget
    bar_len = int(b.remaining / b.max_budget * 30)
    bar = "#" * bar_len + "." * (30 - bar_len)
    click.echo(f"Budget: [{bar}] {b.remaining:.2f} / {b.max_budget:.1f}")
    click.echo(f"Can explore: {b.can_explore()}")
    click.echo(f"Regen rate:  {b.regen_rate}/turn (standard)")
    click.echo(f"Min to explore: {b.min_to_explore}")


@explore_cmd.command("profiles")
@click.pass_context
def explore_profiles(ctx):
    """List all available exploration profiles."""
    from .homeostat import list_profiles

    for p in list_profiles():
        click.echo(f"  {p.context.value:18s} cost={p.budget_cost:.2f}  "
                    f"dampening={p.urgency_dampening:.0%}  "
                    f"tentative={p.commitment_tentativeness:.0%}")
        click.echo(f"    {p.description}")


@explore_cmd.command("observe")
@click.option("--revision-rate", type=float, default=0.0, help="Revision rate")
@click.option("--contradiction-rate", type=float, default=0.0, help="Contradiction rate")
@click.option("--hedge-rate", type=float, default=0.0, help="Hedge rate")
@click.option("--refusal-rate", type=float, default=0.0, help="Refusal rate")
@click.option("--support-deficit", type=float, default=0.0, help="Support deficit rate")
@click.option("--retrieval-coverage", type=float, default=1.0, help="Retrieval coverage")
@click.option("--instability", type=float, default=0.0, help="Thermal instability")
@click.option("--domain", type=str, default="general", help="Domain for setpoints")
@click.pass_context
def explore_observe(ctx, revision_rate, contradiction_rate, hedge_rate,
                    refusal_rate, support_deficit, retrieval_coverage,
                    instability, domain):
    """Observe vitals and compute tuning deltas."""
    from .homeostat import Homeostat, EpistemicVitals, create_homeostat

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if homeo_path.exists():
        h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    else:
        h = create_homeostat(domain=domain)

    vitals = EpistemicVitals(
        revision_rate=revision_rate,
        contradiction_rate=contradiction_rate,
        hedge_rate=hedge_rate,
        refusal_rate=refusal_rate,
        support_deficit_rate=support_deficit,
        retrieval_coverage=retrieval_coverage,
        thermal_instability=instability,
    )

    tuning = h.observe(vitals)
    homeo_path.write_text(json.dumps(h.to_dict(), indent=2, default=str))

    click.echo(f"Context:    {h.context.value}")
    click.echo(f"EMA urgency: {h.ema_urgency:.4f}")
    click.echo("Tuning deltas:")
    click.echo(f"  confidence_mult:  {tuning.confidence_ceiling_mult:.3f}")
    click.echo(f"  support_bias:     {tuning.require_support_bias:+.3f}")
    click.echo(f"  retrieval_bias:   {tuning.retrieval_force_bias:+.3f}")
    click.echo(f"  hedge_preference: {tuning.hedge_preference:+.3f}")
    click.echo(f"  refuse_preference:{tuning.refuse_preference:+.3f}")
    click.echo(f"  revision_cost:    {tuning.revision_cost_mult:.3f}")
    click.echo(f"  horizon_mult:     {tuning.horizon_mult:.3f}")


@cli.command("vitals")
@click.pass_context
def vitals_cmd(ctx):
    """Show current vitals and setpoint deviations."""
    from .homeostat import Homeostat

    gov_dir = ensure_initialized(ctx)
    homeo_path = gov_dir / "homeostat.json"

    if not homeo_path.exists():
        click.echo("No homeostat data. Run 'governor explore observe' first.")
        return

    h = Homeostat.from_dict(json.loads(homeo_path.read_text()))
    if not h.history:
        click.echo("No observations recorded yet.")
        return

    last = h.history[-1]
    v = last.vitals
    errors = h.setpoints.compute_error(v)

    click.echo(f"Turn: {v.turn}  Commits: {v.total_commits}  Proposals: {v.total_proposals}")
    click.echo(f"Thermal regime: {v.thermal_regime}")
    click.echo(f"EMA urgency: {h.ema_urgency:.4f}")
    click.echo()
    click.echo(f"{'Metric':<24s} {'Value':>7s} {'Target':>7s} {'Error':>7s}")
    click.echo("-" * 50)

    rows = [
        ("revision_rate", v.revision_rate, h.setpoints.revision_target, errors["revision"]),
        ("contradiction_rate", v.contradiction_rate, h.setpoints.contradiction_target, errors["contradiction"]),
        ("hedge_rate", v.hedge_rate, h.setpoints.hedge_target, errors["hedge"]),
        ("refusal_rate", v.refusal_rate, h.setpoints.refusal_target, errors["refusal"]),
        ("support_deficit", v.support_deficit_rate, h.setpoints.support_deficit_target, errors["support_deficit"]),
        ("retrieval_coverage", v.retrieval_coverage, h.setpoints.retrieval_coverage_target, errors["retrieval_coverage"]),
        ("thermal_instability", v.thermal_instability, h.setpoints.instability_target, errors["instability"]),
    ]
    for name, val, target, err in rows:
        flag = "!" if err > 0.1 else " "
        click.echo(f"{flag} {name:<22s} {val:7.3f} {target:7.3f} {err:7.3f}")


# =====================================================================
# Strict Programmer Mode
# =====================================================================

def get_strict_gate(gov_dir: Path):
    """Load or create a StrictModeGate."""
    from .strict import StrictModeGate
    gate_path = gov_dir / "strict_gate.json"
    if gate_path.exists():
        return StrictModeGate.from_dict(json.loads(gate_path.read_text()))
    return StrictModeGate()


def save_strict_gate(gov_dir: Path, gate) -> None:
    gate_path = gov_dir / "strict_gate.json"
    gate_path.write_text(json.dumps(gate.to_dict(), indent=2))


@cli.group("strict")
@click.pass_context
def strict_cmd(ctx):
    """Strict programmer mode — fail-closed governance for production contexts."""
    pass


@strict_cmd.command("status")
@click.pass_context
def strict_status(ctx):
    """Show strict mode gate status and statistics."""
    from .strict import StrictModeGate

    gov_dir = ensure_initialized(ctx)
    gate = get_strict_gate(gov_dir)
    s = gate.stats()

    click.echo("=== Strict Programmer Mode ===")
    click.echo(f"Policy: hard_threshold={gate.policy.hard_threshold}  "
               f"soft_threshold={gate.policy.soft_threshold}")
    click.echo(f"Risk adjustment: k_increase={gate.policy.k_increase}  "
               f"independence_boost={gate.policy.independence_boost}")
    click.echo(f"Speculative facts: {'allowed' if gate.policy.speculative_facts_allowed else 'blocked'}")
    click.echo()

    if s["total"] == 0:
        click.echo("No evaluations recorded.")
        return

    click.echo(f"Total evaluations: {s['total']}")
    click.echo(f"  HARD:    {s['hard']} ({s['hard_rate']:.1%})")
    click.echo(f"  SOFT:    {s['soft']} ({s['soft_rate']:.1%})")
    click.echo(f"  REFUSED: {s['refused']} ({s['refusal_rate']:.1%})")


@strict_cmd.command("evaluate")
@click.argument("category", type=click.Choice([
    "static_fact", "volatile_fact", "code", "procedure", "judgment", "plan",
]))
@click.option("--risk", type=click.Choice(["low", "medium", "high"]), default="low")
@click.option("--evidence-count", type=int, default=0)
@click.option("--independence", type=float, default=0.0)
@click.option("--has-source", is_flag=True)
@click.option("--has-version", is_flag=True)
@click.option("--has-verification-date", is_flag=True)
@click.option("--has-ttl", is_flag=True)
@click.option("--ttl-hours", type=float, default=None)
@click.option("--has-prerequisites", is_flag=True)
@click.option("--has-failure-modes", is_flag=True)
@click.option("--has-rollback", is_flag=True)
@click.option("--is-runnable", is_flag=True)
@click.option("--is-pseudocode", is_flag=True)
@click.option("--falsifier-ran", is_flag=True)
@click.option("--has-platform-context", is_flag=True)
@click.pass_context
def strict_evaluate(ctx, category, risk, evidence_count, independence,
                    has_source, has_version, has_verification_date,
                    has_ttl, ttl_hours, has_prerequisites, has_failure_modes,
                    has_rollback, is_runnable, is_pseudocode, falsifier_ran,
                    has_platform_context):
    """Evaluate a claim under strict mode."""
    from .strict import ClaimCategory, RiskLevel

    gov_dir = ensure_initialized(ctx)
    gate = get_strict_gate(gov_dir)

    result = gate.evaluate(
        ClaimCategory(category),
        RiskLevel(risk),
        evidence_count=evidence_count,
        independence_score=independence,
        has_source=has_source,
        has_version=has_version,
        has_verification_date=has_verification_date,
        has_ttl=has_ttl,
        ttl_hours=ttl_hours,
        has_prerequisites=has_prerequisites,
        has_failure_modes=has_failure_modes,
        has_rollback=has_rollback,
        is_runnable=is_runnable,
        is_labeled_pseudocode=is_pseudocode,
        falsifier_ran=falsifier_ran,
        has_platform_context=has_platform_context,
    )

    save_strict_gate(gov_dir, gate)

    click.echo(f"Category: {result.category.value}  Risk: {result.risk.value}")
    click.echo(f"Commit level: {result.commit_level.value}")
    click.echo(f"Satisfaction: {result.satisfaction_ratio:.1%}")
    if result.satisfied:
        click.echo(f"  Satisfied: {', '.join(result.satisfied)}")
    if result.unsatisfied:
        click.echo(f"  Unsatisfied: {', '.join(result.unsatisfied)}")
    click.echo(f"Recommendation: {result.recommendation}")
    if result.refusal_message:
        click.echo(f"Refusal: {result.refusal_message}")


@strict_cmd.command("requirements")
@click.argument("category", type=click.Choice([
    "static_fact", "volatile_fact", "code", "procedure", "judgment", "plan",
]))
@click.option("--risk", type=click.Choice(["low", "medium", "high"]), default="low")
@click.pass_context
def strict_requirements(ctx, category, risk):
    """Show requirements for a claim category."""
    from .strict import ClaimCategory, RiskLevel, StrictPolicy

    policy = StrictPolicy()
    cat = ClaimCategory(category)
    r = RiskLevel(risk)

    if cat in policy.soft_only:
        click.echo(f"{cat.value} is always SOFT — no hard requirements.")
        return

    req = policy.get_risk_adjusted(cat, r)
    click.echo(f"Requirements for {cat.value} at {r.value} risk:")
    click.echo(f"  min_evidence_count: {req.min_evidence_count}")
    click.echo(f"  min_independence: {req.min_independence}")
    for field_name in [
        "requires_source", "requires_version", "requires_verification_date",
        "requires_ttl", "requires_prerequisites", "requires_failure_modes",
        "requires_rollback", "requires_runnable", "falsifier_required",
        "requires_platform_context",
    ]:
        val = getattr(req, field_name)
        if val:
            click.echo(f"  {field_name}: {val}")
    if req.max_ttl_hours is not None:
        click.echo(f"  max_ttl_hours: {req.max_ttl_hours}")


@strict_cmd.command("history")
@click.option("--limit", default=20)
@click.pass_context
def strict_history(ctx, limit):
    """Show recent evaluation history."""
    gov_dir = ensure_initialized(ctx)
    gate = get_strict_gate(gov_dir)

    history = gate.history[-limit:]
    if not history:
        click.echo("No evaluations recorded.")
        return

    click.echo(f"{'Category':<16s} {'Risk':<8s} {'Level':<10s} {'Ratio':>6s}")
    click.echo("-" * 44)
    for ev in history:
        click.echo(f"{ev.category.value:<16s} {ev.risk.value:<8s} "
                    f"{ev.commit_level.value:<10s} {ev.satisfaction_ratio:5.1%}")


@strict_cmd.command("reset")
@click.option("--confirm", is_flag=True, required=True,
              help="Confirm reset of evaluation history")
@click.pass_context
def strict_reset(ctx, confirm):
    """Reset strict mode evaluation history."""
    gov_dir = ensure_initialized(ctx)
    gate = get_strict_gate(gov_dir)
    old_count = gate.total_evaluations
    gate.reset()
    save_strict_gate(gov_dir, gate)
    click.echo(f"Reset strict mode gate. Cleared {old_count} evaluations.")


def get_drift_detector(gov_dir: Path):
    """Load or create a DriftDetector."""
    from .drift import DriftDetector
    drift_path = gov_dir / "drift_detector.json"
    if drift_path.exists():
        return DriftDetector.from_dict(json.loads(drift_path.read_text()))
    return DriftDetector()


def save_drift_detector(gov_dir: Path, detector) -> None:
    drift_path = gov_dir / "drift_detector.json"
    drift_path.write_text(json.dumps(detector.to_dict(), indent=2))


@cli.group("drift")
@click.pass_context
def drift_cmd(ctx):
    """Drift detection — defense against temporal asymmetry attacks."""
    pass


@drift_cmd.command("status")
@click.pass_context
def drift_status(ctx):
    """Show drift detector status and alert level."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    click.echo("=== Drift Detector ===")
    click.echo(f"Turn: {detector.turn}")
    click.echo(f"Alert level: {detector.current_alert}")
    click.echo(f"Tracked premises: {len(detector.quarantine.premises)}")
    click.echo(f"Tracked agents: {len(detector.agents)}")
    click.echo(f"Unresolved contradictions: {len(detector.unresolved_contradictions)}")

    metrics = detector.quarantine.get_metrics()
    click.echo()
    click.echo(f"Quarantine: {metrics['quarantined_premises']} quarantined, "
               f"{metrics['total_quarantined_ever']} total ever, "
               f"{metrics['total_released']} released")

    if detector.last_signals:
        s = detector.last_signals
        click.echo()
        click.echo("Last signals:")
        click.echo(f"  premise_recurrence_rate: {s.premise_recurrence_rate:.3f}")
        click.echo(f"  attention_skew: {s.attention_skew:.3f}")
        click.echo(f"  temporal_coherence_gradient: {s.temporal_coherence_gradient:.3f}")
        click.echo(f"  max_contradiction_age: {s.max_contradiction_age}")
        click.echo(f"  single_source_rate: {s.single_source_rate:.3f}")


@drift_cmd.command("update")
@click.pass_context
def drift_update(ctx):
    """Compute signals and update alert level."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    alert, signals, reasons = detector.update()
    save_drift_detector(gov_dir, detector)

    click.echo(f"Alert: {alert}")
    click.echo(f"Reasons: {', '.join(reasons)}")
    click.echo()
    click.echo("Signals:")
    for k, v in signals.to_dict().items():
        click.echo(f"  {k}: {v}")


@drift_cmd.command("record")
@click.argument("content")
@click.option("--agent-id", default=None, help="Source agent ID")
@click.option("--has-evidence", is_flag=True, help="Premise has evidence")
@click.option("--contested", is_flag=True, help="Premise is contested")
@click.option("--topic", default=None, help="Topic tag")
@click.pass_context
def drift_record(ctx, content, agent_id, has_evidence, contested, topic):
    """Record an assertion for drift tracking."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    rec = detector.record_assertion(
        content, agent_id=agent_id, has_evidence=has_evidence,
        contested=contested, topic=topic,
    )
    save_drift_detector(gov_dir, detector)

    click.echo(f"Recorded premise: {rec.content_summary}")
    click.echo(f"  occurrences: {rec.occurrences}  weight: {rec.weight:.2f}")
    if rec.quarantined:
        click.echo("  STATUS: QUARANTINED")


@drift_cmd.command("quarantined")
@click.pass_context
def drift_quarantined(ctx):
    """List quarantined premises."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    quarantined = detector.quarantine.quarantined_premises()
    if not quarantined:
        click.echo("No quarantined premises.")
        return

    click.echo(f"{'Summary':<40s} {'Occ':>4s} {'Weight':>7s} {'Stale':>6s}")
    click.echo("-" * 60)
    for rec in quarantined:
        click.echo(f"{rec.content_summary[:40]:<40s} {rec.occurrences:>4d} "
                   f"{rec.weight:>7.2f} {rec.turns_without_evidence:>6d}")


@drift_cmd.command("agents")
@click.pass_context
def drift_agents(ctx):
    """Show agent activity tracking."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    if not detector.agents:
        click.echo("No agents tracked.")
        return

    click.echo(f"{'Agent':<20s} {'Assert':>7s} {'Contest':>8s} {'Ratio':>7s} {'Coher':>7s}")
    click.echo("-" * 52)
    for agent in detector.agents.values():
        click.echo(f"{agent.agent_id[:20]:<20s} {agent.total_assertions:>7d} "
                   f"{agent.contested_assertions:>8d} "
                   f"{agent.contested_ratio:>7.2f} {agent.temporal_coherence:>7.2f}")


@drift_cmd.command("history")
@click.option("--limit", default=20)
@click.pass_context
def drift_history(ctx, limit):
    """Show alert transition history."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)

    history = detector.alert_history[-limit:]
    if not history:
        click.echo("No alert transitions recorded.")
        return

    click.echo(f"{'Turn':>6s} {'Alert':<12s} {'Reasons'}")
    click.echo("-" * 60)
    for turn, alert, reasons in history:
        click.echo(f"{turn:>6d} {alert:<12s} {', '.join(reasons)}")


@drift_cmd.command("tick")
@click.pass_context
def drift_tick(ctx):
    """Advance drift detector turn counter."""
    gov_dir = ensure_initialized(ctx)
    detector = get_drift_detector(gov_dir)
    detector.tick()
    save_drift_detector(gov_dir, detector)
    click.echo(f"Advanced to turn {detector.turn}")


@drift_cmd.command("reset")
@click.option("--confirm", is_flag=True, required=True,
              help="Confirm reset of drift detector state")
@click.pass_context
def drift_reset(ctx, confirm):
    """Reset drift detector state."""
    from .drift import DriftDetector
    gov_dir = ensure_initialized(ctx)
    detector = DriftDetector()
    save_drift_detector(gov_dir, detector)
    click.echo("Drift detector reset to initial state.")


# ============================================================================
# Claim Diff Commands
# ============================================================================

CLAIM_DIFF_SNAPSHOT_FILE = "claim_diff_snapshot.json"
CLAIM_DIFF_HISTORY_FILE = "claim_diff_history.json"


def get_claim_diff_snapshot(gov_dir: Path):
    """Load the last saved ledger snapshot for diffing."""
    from .claim_diff import LedgerSnapshot
    path = gov_dir / CLAIM_DIFF_SNAPSHOT_FILE
    if path.exists():
        data = json.loads(path.read_text())
        # Reconstruct from dict
        from .claim_diff import ClaimSnapshot
        claims = {}
        claims_by_hash: dict[str, list[str]] = {}
        for cid, cd in data.get("claims", {}).items():
            snap = ClaimSnapshot(
                claim_id=cd["claim_id"],
                content=cd["content"],
                content_hash=cd["content_hash"],
                provenance=cd["provenance"],
                confidence=cd["confidence"],
                evidence_count=cd["evidence_count"],
                evidence_ref_ids=tuple(cd.get("evidence_ref_ids", [])),
                status=cd["status"],
                is_grounded=cd["is_grounded"],
                is_dangerous=cd["is_dangerous"],
                source_agent_id=cd.get("source_agent_id"),
            )
            claims[cid] = snap
            if snap.content_hash not in claims_by_hash:
                claims_by_hash[snap.content_hash] = []
            claims_by_hash[snap.content_hash].append(cid)
        return LedgerSnapshot(
            step=data["step"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            claims=claims,
            claims_by_hash=claims_by_hash,
            total_claims=data["total_claims"],
            active_count=data["active_count"],
            dangerous_count=data["dangerous_count"],
        )
    return None


def save_claim_diff_snapshot(gov_dir: Path, snapshot) -> None:
    """Save a ledger snapshot for future diffing."""
    path = gov_dir / CLAIM_DIFF_SNAPSHOT_FILE
    path.write_text(json.dumps(snapshot.to_dict(), indent=2, default=str))


def get_claim_diff_history(gov_dir: Path):
    """Load diff history."""
    from .claim_diff import DiffHistory
    path = gov_dir / CLAIM_DIFF_HISTORY_FILE
    if path.exists():
        data = json.loads(path.read_text())
        history = DiffHistory(max_history=data.get("max_history", 100))
        # We store summaries, not full results — enough for trend analysis
        return history, data.get("diffs", [])
    return DiffHistory(), []


def save_claim_diff_history(gov_dir: Path, history, raw_diffs: list) -> None:
    """Save diff history."""
    path = gov_dir / CLAIM_DIFF_HISTORY_FILE
    output = {
        "max_history": history.max_history,
        "count": len(history.diffs),
        "diffs": [d.to_dict() for d in history.diffs],
    }
    path.write_text(json.dumps(output, indent=2, default=str))


@cli.group("claim-diff")
@click.pass_context
def claim_diff_cmd(ctx):
    """Claim diff — detect epistemic state changes between turns.

    Catches confidence drift, provenance laundering,
    evidence erosion, and silent retraction.
    """
    pass


@claim_diff_cmd.command("status")
@click.pass_context
def claim_diff_status(ctx):
    """Show diff tracking state and violation counts."""
    gov_dir = ensure_initialized(ctx)
    snapshot = get_claim_diff_snapshot(gov_dir)
    history, raw = get_claim_diff_history(gov_dir)

    click.echo("=== Claim Diff ===")
    if snapshot:
        click.echo(f"Last snapshot: step {snapshot.step} ({snapshot.total_claims} claims)")
    else:
        click.echo("Last snapshot: none (run 'governor claim-diff snapshot' first)")

    click.echo(f"History entries: {len(history.diffs)}")

    if history.diffs:
        total_violations = sum(len(d.violations) for d in history.diffs)
        total_drift = sum(d.confidence_drift_count for d in history.diffs)
        total_launder = sum(d.provenance_laundering_count for d in history.diffs)
        click.echo(f"Total violations: {total_violations}")
        click.echo(f"  Confidence drift: {total_drift}")
        click.echo(f"  Provenance laundering: {total_launder}")


@claim_diff_cmd.command("snapshot")
@click.pass_context
def claim_diff_snapshot(ctx):
    """Take snapshot of current epistemic ledger."""
    from .claim_diff import snapshot_ledger

    gov_dir = ensure_initialized(ctx)
    ledger = get_epistemic_ledger(gov_dir)
    snap = snapshot_ledger(ledger)
    save_claim_diff_snapshot(gov_dir, snap)

    click.echo(f"Snapshot taken at step {snap.step}")
    click.echo(f"  Total claims: {snap.total_claims}")
    click.echo(f"  Active: {snap.active_count}")
    click.echo(f"  Dangerous: {snap.dangerous_count}")


@claim_diff_cmd.command("run")
@click.pass_context
def claim_diff_run(ctx):
    """Diff current ledger vs last snapshot, append to history."""
    from .claim_diff import snapshot_ledger, ClaimDiffer, DiffHistory

    gov_dir = ensure_initialized(ctx)
    old_snapshot = get_claim_diff_snapshot(gov_dir)

    if old_snapshot is None:
        click.echo("No previous snapshot. Run 'governor claim-diff snapshot' first.", err=True)
        ctx.exit(1)
        return

    ledger = get_epistemic_ledger(gov_dir)
    new_snapshot = snapshot_ledger(ledger)

    differ = ClaimDiffer()
    result = differ.diff(old_snapshot, new_snapshot)

    # Update history
    history, _ = get_claim_diff_history(gov_dir)
    history.add(result)
    save_claim_diff_history(gov_dir, history, [])

    # Save new snapshot as baseline
    save_claim_diff_snapshot(gov_dir, new_snapshot)

    s = result.summary
    click.echo(f"Diff: step {s['steps']}")
    click.echo(f"  Preserved: {s['preserved']}")
    click.echo(f"  Mutated: {s['mutated']}")
    click.echo(f"  Added: {s['added']}")
    click.echo(f"  Dropped: {s['dropped']}")
    click.echo(f"  Violations: {s['violations']}")

    if result.has_violations:
        click.echo()
        for v in result.violations:
            color = "red" if v.severity >= 0.8 else "yellow"
            click.echo(click.style(
                f"  [{v.violation_type.value}] {v.content_summary[:60]}",
                fg=color,
            ))
            click.echo(f"    Severity: {v.severity:.2f} — {v.details}")


@claim_diff_cmd.command("violations")
@click.option("--all", "show_all", is_flag=True, help="Show all violations from history")
@click.option("--type", "vtype", default=None, help="Filter by violation type")
@click.pass_context
def claim_diff_violations(ctx, show_all, vtype):
    """List violations from most recent diff (or all history)."""
    gov_dir = ensure_initialized(ctx)
    history, _ = get_claim_diff_history(gov_dir)

    if not history.diffs:
        click.echo("No diff history. Run 'governor claim-diff run' first.")
        return

    diffs = history.diffs if show_all else [history.diffs[-1]]
    all_violations = []
    for d in diffs:
        for v in d.violations:
            if vtype is None or v.violation_type.value == vtype:
                all_violations.append((d, v))

    if not all_violations:
        click.echo("No violations found.")
        return

    click.echo(f"{'Type':<25s} {'Severity':>8s}  {'Claim'}")
    click.echo("-" * 70)
    for d, v in all_violations:
        click.echo(f"{v.violation_type.value:<25s} {v.severity:>8.2f}  {v.content_summary[:35]}")


@claim_diff_cmd.command("history")
@click.option("--limit", default=20, help="Max entries to show")
@click.pass_context
def claim_diff_history(ctx, limit):
    """Show diff history (step ranges, mutation/violation counts)."""
    gov_dir = ensure_initialized(ctx)
    history, _ = get_claim_diff_history(gov_dir)

    if not history.diffs:
        click.echo("No diff history.")
        return

    recent = history.diffs[-limit:]
    click.echo(f"{'Steps':<14s} {'Mut':>4s} {'Viol':>5s} {'Sev':>6s} {'Drift':>6s} {'Laund':>6s}")
    click.echo("-" * 45)
    for d in recent:
        steps = f"{d.before_step}->{d.after_step}"
        click.echo(f"{steps:<14s} {d.total_mutations:>4d} {len(d.violations):>5d} "
                   f"{d.total_severity:>6.2f} {d.confidence_drift_count:>6d} "
                   f"{d.provenance_laundering_count:>6d}")


@claim_diff_cmd.command("trend")
@click.pass_context
def claim_diff_trend(ctx):
    """Show trend analysis (drift/laundering/severity per diff)."""
    gov_dir = ensure_initialized(ctx)
    history, _ = get_claim_diff_history(gov_dir)

    if not history.diffs:
        click.echo("No diff history for trend analysis.")
        return

    drift = history.confidence_drift_trend()
    launder = history.laundering_trend()
    severity = history.severity_trend()
    violations = history.violation_trend()

    click.echo(f"{'#':>3s}  {'Drift':>6s} {'Laund':>6s} {'Viol':>5s} {'Sev':>7s}")
    click.echo("-" * 32)
    for i in range(len(drift)):
        click.echo(f"{i+1:>3d}  {drift[i]:>6d} {launder[i]:>6d} "
                   f"{violations[i]:>5d} {severity[i]:>7.2f}")

    # Summary
    click.echo()
    if any(d > 0 for d in drift):
        click.echo(click.style("Confidence drift detected in history.", fg="yellow"))
    if any(l > 0 for l in launder):
        click.echo(click.style("Provenance laundering detected in history.", fg="red"))


@claim_diff_cmd.command("laundering")
@click.pass_context
def claim_diff_laundering(ctx):
    """Shortcut: run diff and show only laundering violations."""
    from .claim_diff import snapshot_ledger, ClaimDiffer, DiffHistory

    gov_dir = ensure_initialized(ctx)
    old_snapshot = get_claim_diff_snapshot(gov_dir)

    if old_snapshot is None:
        click.echo("No previous snapshot. Run 'governor claim-diff snapshot' first.", err=True)
        ctx.exit(1)
        return

    ledger = get_epistemic_ledger(gov_dir)
    new_snapshot = snapshot_ledger(ledger)

    differ = ClaimDiffer(
        detect_confidence_drift=False,
        detect_evidence_erosion=False,
        detect_silent_retraction=False,
    )
    result = differ.diff(old_snapshot, new_snapshot)

    laundering = [
        v for v in result.violations
        if v.violation_type.value == "provenance_laundering"
    ]

    if not laundering:
        click.echo("No provenance laundering detected.")
        return

    click.echo(f"Provenance laundering: {len(laundering)} violation(s)\n")
    for v in laundering:
        click.echo(click.style(f"  [{v.claim_id}] {v.content_summary[:60]}", fg="red"))
        click.echo(f"    {v.details}")


@claim_diff_cmd.command("reset")
@click.option("--confirm", is_flag=True, required=True,
              help="Confirm reset of diff history and snapshots")
@click.pass_context
def claim_diff_reset(ctx, confirm):
    """Clear history and snapshots."""
    gov_dir = ensure_initialized(ctx)

    snapshot_path = gov_dir / CLAIM_DIFF_SNAPSHOT_FILE
    history_path = gov_dir / CLAIM_DIFF_HISTORY_FILE

    removed = 0
    if snapshot_path.exists():
        snapshot_path.unlink()
        removed += 1
    if history_path.exists():
        history_path.unlink()
        removed += 1

    click.echo(f"Claim diff state reset. Removed {removed} file(s).")


# =============================================================================
# Claim Signal Extraction
# =============================================================================


@cli.group("signals")
@click.pass_context
def signals_cmd(ctx):
    """Claim signal extraction — detect implicit claims from text."""
    pass


@signals_cmd.command("extract")
@click.argument("text")
@click.pass_context
def signals_extract(ctx, text):
    """Extract signals from provided text."""
    from .claim_signals import SignalExtractor

    extractor = SignalExtractor()
    result = extractor.extract(text)

    click.echo(f"Text hash: {result.text_hash}")
    click.echo(f"Total signals: {result.total_signals}")
    click.echo(f"Speculative content: {result.has_speculative_content}")
    click.echo(f"Assertiveness score: {result.assertiveness_score:.2f}")
    click.echo()

    for cat_name, count in result.signals_by_category.items():
        if count > 0:
            click.echo(f"  {cat_name}: {count}")

    if result.matches:
        click.echo()
        for m in result.matches:
            click.echo(
                f"  [{m.category.value}] {m.value}"
                + (f"  (line {m.line_number})" if m.line_number else "")
            )


@signals_cmd.command("scan")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def signals_scan(ctx, path):
    """Scan a file for claim signals."""
    from .claim_signals import SignalExtractor

    extractor = SignalExtractor()
    result = extractor.scan_file(path)

    click.echo(f"File: {path}")
    click.echo(f"Total signals: {result.total_signals}")
    click.echo(f"Speculative content: {result.has_speculative_content}")
    click.echo(f"Assertiveness score: {result.assertiveness_score:.2f}")
    click.echo()

    for cat_name, count in result.signals_by_category.items():
        if count > 0:
            click.echo(f"  {cat_name}: {count}")

    if result.matches:
        click.echo()
        for m in result.matches:
            line_info = f":L{m.line_number}" if m.line_number else ""
            click.echo(f"  [{m.category.value}] {m.value}{line_info}")


@signals_cmd.command("register")
@click.argument("text")
@click.option("--agent-id", default=None, help="Source agent ID for registered claims")
@click.option("--confidence", type=float, default=0.2, help="Confidence for registered claims")
@click.pass_context
def signals_register(ctx, text, agent_id, confidence):
    """Extract signals AND register as ASSUMED claims in epistemic ledger."""
    from .claim_signals import SignalExtractor, register_signals
    from .epistemic import EpistemicLedger

    gov_dir = ensure_initialized(ctx)

    extractor = SignalExtractor()
    result = extractor.extract(text)

    ledger = EpistemicLedger()
    # Load existing ledger state if available
    ledger_path = gov_dir / "epistemic_ledger.json"
    if ledger_path.exists():
        import json as _json
        data = _json.loads(ledger_path.read_text())
        for cid, cdata in data.get("claims", {}).items():
            from .epistemic import GroundedClaim
            ledger.claims[cid] = GroundedClaim.from_dict(cdata)
        ledger.step = data.get("step", 0)

    claim_ids = register_signals(
        ledger, result,
        source_agent_id=agent_id,
        confidence=confidence,
    )

    # Save updated ledger
    ledger_path.write_text(ledger.to_json())

    click.echo(f"Extracted {result.total_signals} signal(s), registered {len(claim_ids)} claim(s).")
    for cid in claim_ids:
        claim = ledger.get(cid)
        click.echo(f"  {cid}: {claim.content} (conf={claim.confidence:.2f})")


@signals_cmd.command("score")
@click.argument("text")
@click.pass_context
def signals_score(ctx, text):
    """Show assertiveness score only."""
    from .claim_signals import assertiveness_score as compute_score

    score = compute_score(text)
    click.echo(f"Assertiveness score: {score:.2f}")

    if score == 0.0:
        click.echo("  No assertive language detected.")
    elif score < 0.4:
        click.echo("  Low assertiveness.")
    elif score < 0.7:
        click.echo("  Moderate assertiveness.")
    else:
        click.echo("  High assertiveness — review for unsupported claims.")


# =============================================================================
# Config Profiles
# =============================================================================


@cli.group("profile")
@click.pass_context
def profile_cmd(ctx):
    """Config profiles — named governance presets."""
    pass


@profile_cmd.command("list")
@click.pass_context
def profile_list(ctx):
    """List available profiles."""
    from .profiles import get_profile_manager, BUILTIN_PROFILES

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)
    active_name, _ = mgr.get_active()

    for name, p in mgr.list_profiles().items():
        marker = " *" if name == active_name else ""
        builtin = " (builtin)" if name in BUILTIN_PROFILES else " (custom)"
        click.echo(f"  {name}{marker}{builtin}")
        click.echo(f"    {p.description}" if p.description else "")


@profile_cmd.command("use")
@click.argument("name")
@click.pass_context
def profile_use(ctx, name):
    """Activate a profile and apply its settings."""
    from .profiles import get_profile_manager, apply_profile

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)

    try:
        settings = mgr.activate(name)
    except KeyError:
        click.echo(f"Error: Profile '{name}' not found.", err=True)
        ctx.exit(1)
        return

    applied = apply_profile(gov_dir, settings)

    click.echo(f"Profile '{name}' activated.")
    for key, val in applied.items():
        click.echo(f"  {key}: {val}")


@profile_cmd.command("status")
@click.pass_context
def profile_status(ctx):
    """Show the active profile."""
    from .profiles import get_profile_manager

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)
    name, settings = mgr.get_active()

    if name is None:
        click.echo("No active profile.")
        return

    click.echo(f"Active profile: {name}")
    click.echo(f"  Envelope:     {settings.envelope_mode}")
    click.echo(f"  Boil preset:  {settings.boil_preset}")
    click.echo(f"  Jurisdiction: {settings.jurisdiction}")
    click.echo(f"  Strict mode:  {'enabled' if settings.strict_mode else 'disabled'}")
    if settings.description:
        click.echo(f"  Description:  {settings.description}")


@profile_cmd.command("off")
@click.pass_context
def profile_off(ctx):
    """Deactivate the current profile."""
    from .profiles import get_profile_manager

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)
    mgr.deactivate()
    click.echo("Profile deactivated.")


@profile_cmd.command("create")
@click.argument("name")
@click.option("--envelope", type=click.Choice(["strict", "exploratory"]), required=True)
@click.option("--boil", required=True, help="Boil preset (GREEN_TEA, WHITE_TEA, OOLONG, BLACK_TEA, FRENCH_PRESS, BOIL)")
@click.option("--jurisdiction", required=True, help="Jurisdiction name")
@click.option("--strict/--no-strict", default=True, help="Enable strict mode")
@click.option("--description", "-d", default="", help="Profile description")
@click.pass_context
def profile_create(ctx, name, envelope, boil, jurisdiction, strict, description):
    """Create a custom profile."""
    from .profiles import get_profile_manager, ProfileSettings

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)

    settings = ProfileSettings(
        envelope_mode=envelope,
        boil_preset=boil.upper(),
        jurisdiction=jurisdiction.upper(),
        strict_mode=strict,
        description=description,
    )

    try:
        mgr.create(name, settings)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Profile '{name}' created.")


@profile_cmd.command("delete")
@click.argument("name")
@click.pass_context
def profile_delete(ctx, name):
    """Delete a custom profile."""
    from .profiles import get_profile_manager

    gov_dir = ensure_initialized(ctx)
    mgr = get_profile_manager(gov_dir)

    try:
        mgr.delete(name)
    except (ValueError, KeyError) as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Profile '{name}' deleted.")


# =============================================================================
# Quorum commands
# =============================================================================


@cli.group("quorum")
@click.pass_context
def quorum_cmd(ctx):
    """Quorum state machine — multi-agent consensus protocol for claim commitment."""
    pass


@quorum_cmd.command("status")
@click.argument("proposal_id")
@click.pass_context
def quorum_status(ctx, proposal_id):
    """Show quorum state for a proposal."""
    from .quorum import QuorumManager, QuorumStatus

    gov_dir = ensure_initialized(ctx)
    mgr = QuorumManager()
    qs = mgr.get_quorum(proposal_id)
    if qs is None:
        click.echo(f"No quorum found for proposal '{proposal_id}'", err=True)
        ctx.exit(1)
        return

    click.echo(f"Proposal: {qs.proposal_id}")
    click.echo(f"Claim type: {qs.claim_type.value}")
    click.echo(f"Status: {qs.status.value}")
    click.echo(f"Votes: {qs.total_votes} (approve={qs.approval_count}, reject={qs.rejection_count}, abstain={qs.abstain_count})")
    click.echo(f"Approval ratio: {qs.approval_ratio:.2f}")
    click.echo(f"Threshold: {qs.policy.approval_threshold}")
    click.echo(f"Min voters (k): {qs.policy.min_voters}")
    click.echo(f"Δt window: {qs.policy.delta_t.total_seconds()}s")
    click.echo(f"Requires human: {qs.policy.requires_human}")
    if qs.stabilized_at:
        click.echo(f"Stabilized at: {qs.stabilized_at.isoformat()}")
    if qs.reached_at:
        click.echo(f"Reached at: {qs.reached_at.isoformat()}")
    if qs.failed_reason:
        click.echo(f"Failed reason: {qs.failed_reason}")


@quorum_cmd.command("vote")
@click.argument("proposal_id")
@click.option("--agent-id", required=True, help="Voting agent ID")
@click.option("--verdict", type=click.Choice(["approve", "reject", "abstain"]), required=True)
@click.option("--reason", "-r", required=True, help="Reason for vote")
@click.pass_context
def quorum_vote(ctx, proposal_id, agent_id, verdict, reason):
    """Cast a vote on a proposal."""
    from .quorum import QuorumManager, VoteVerdict

    gov_dir = ensure_initialized(ctx)
    mgr = QuorumManager()
    vote = mgr.cast_vote(
        proposal_id,
        agent_id,
        VoteVerdict(verdict),
        reason,
    )
    if vote is None:
        click.echo("Vote rejected (proposal not found, already voted, or quorum not accepting votes).", err=True)
        ctx.exit(1)
        return

    click.echo(f"Vote cast: {vote.vote_id}")
    click.echo(f"Verdict: {vote.verdict.value}")
    qs = mgr.get_quorum(proposal_id)
    if qs:
        click.echo(f"Quorum status: {qs.status.value}")


@quorum_cmd.command("policy")
@click.argument("claim_type")
@click.pass_context
def quorum_policy(ctx, claim_type):
    """Show quorum policy for a claim type."""
    from .quorum import ClaimType, DEFAULT_POLICIES

    try:
        ct = ClaimType(claim_type)
    except ValueError:
        click.echo(f"Unknown claim type: {claim_type}", err=True)
        click.echo(f"Valid types: {', '.join(c.value for c in ClaimType)}")
        ctx.exit(1)
        return

    p = DEFAULT_POLICIES[ct]
    click.echo(f"Claim type: {p.claim_type.value}")
    click.echo(f"Min voters (k): {p.min_voters}")
    click.echo(f"Approval threshold: {p.approval_threshold}")
    click.echo(f"Δt stability window: {p.delta_t.total_seconds()}s")
    click.echo(f"Volatility class: {p.volatility.value}")
    click.echo(f"Requires human: {p.requires_human}")
    click.echo(f"Timeout: {p.timeout.total_seconds()}s")


@quorum_cmd.command("policies")
@click.pass_context
def quorum_policies(ctx):
    """List all quorum policies."""
    from .quorum import ClaimType, DEFAULT_POLICIES

    click.echo(f"{'Type':<16} {'k':>3} {'Threshold':>10} {'Δt':>8} {'Volatility':<12} {'Human':>6}")
    click.echo("-" * 60)
    for ct in ClaimType:
        p = DEFAULT_POLICIES[ct]
        dt = f"{p.delta_t.total_seconds():.0f}s"
        click.echo(
            f"{ct.value:<16} {p.min_voters:>3} {p.approval_threshold:>10.2f} {dt:>8} "
            f"{p.volatility.value:<12} {'yes' if p.requires_human else 'no':>6}"
        )


@quorum_cmd.command("history")
@click.option("--limit", "-n", default=20, help="Number of entries to show")
@click.pass_context
def quorum_history(ctx, limit):
    """Show recent quorum activity."""
    from .quorum import QuorumManager

    gov_dir = ensure_initialized(ctx)
    mgr = QuorumManager()
    entries = mgr.history[-limit:]
    if not entries:
        click.echo("No quorum activity recorded.")
        return

    for entry in entries:
        ts = entry.get("timestamp", "?")
        event = entry.get("event", "?")
        pid = entry.get("proposal_id", "?")
        extra = {k: v for k, v in entry.items() if k not in {"timestamp", "event", "proposal_id"}}
        extra_str = f" {extra}" if extra else ""
        click.echo(f"[{ts}] {event} proposal={pid}{extra_str}")


# =============================================================================
# Independence scoring commands
# =============================================================================


@cli.group("independence")
@click.pass_context
def independence_cmd(ctx):
    """Cooperative redundancy — independence scoring for quorum votes."""
    pass


@independence_cmd.command("score")
@click.argument("proposal_id")
@click.pass_context
def independence_score_cmd(ctx, proposal_id):
    """Score independence of votes on a proposal."""
    from .independence import IndependenceScorer
    from .quorum import QuorumManager

    gov_dir = ensure_initialized(ctx)
    mgr = QuorumManager()
    qs = mgr.get_quorum(proposal_id)
    if qs is None:
        click.echo(f"No quorum found for proposal '{proposal_id}'", err=True)
        ctx.exit(1)
        return

    scorer = IndependenceScorer()
    result = scorer.score_votes(qs.votes)
    click.echo(f"Proposal: {proposal_id}")
    click.echo(f"Independence score: {result.score:.3f}")
    click.echo(f"Independent count: {result.independent_count}/{result.total_signatures}")
    click.echo(f"Passes threshold (≥{scorer.threshold}): {'yes' if result.passes_threshold else 'no'}")

    if result.violations:
        click.echo("\nViolations:")
        for v in result.violations:
            click.echo(f"  - {v}")

    if result.pairwise_scores:
        click.echo(f"\n{'Agent A':<20} {'Agent B':<20} {'Jaccard':>8}")
        click.echo("-" * 50)
        for a, b, s in result.pairwise_scores:
            click.echo(f"{a:<20} {b:<20} {s:>8.3f}")


@independence_cmd.command("check")
@click.argument("proposal_id")
@click.option("--threshold", "-t", default=0.3, type=float, help="Independence threshold")
@click.pass_context
def independence_check(ctx, proposal_id, threshold):
    """Check if a proposal meets independence requirements."""
    from .independence import IndependenceScorer
    from .quorum import QuorumManager

    gov_dir = ensure_initialized(ctx)
    mgr = QuorumManager()
    qs = mgr.get_quorum(proposal_id)
    if qs is None:
        click.echo(f"No quorum found for proposal '{proposal_id}'", err=True)
        ctx.exit(1)
        return

    scorer = IndependenceScorer(threshold=threshold)
    result = scorer.score_votes(qs.votes)

    if result.passes_threshold:
        click.echo(f"PASS: Independence score {result.score:.3f} ≥ {threshold}")
    else:
        click.echo(f"FAIL: Independence score {result.score:.3f} < {threshold}")
        if result.violations:
            for v in result.violations:
                click.echo(f"  Violation: {v}")
        ctx.exit(1)


# =============================================================================
# Semantic variety commands
# =============================================================================


@cli.group("semvar")
@click.pass_context
def semvar_cmd(ctx):
    """Semantic variety — post-commit text transform to break repetition."""
    pass


@semvar_cmd.command("transform")
@click.argument("text")
@click.option("--turn", "-t", default=0, type=int, help="Current turn number")
@click.option("--user-text", "-u", default="", help="User's text for echo exception")
@click.pass_context
def semvar_transform(ctx, text, turn, user_text):
    """Transform text with semantic variety substitutions."""
    from .semvar import SemVarEngine, SemVarConfig

    engine = SemVarEngine(SemVarConfig())
    result = engine.transform(text, turn=turn, user_text=user_text)
    click.echo(result.transformed)
    if result.substitutions:
        click.echo(f"\n--- {result.rewrites_applied} substitution(s) applied ---")
        for orig, repl in result.substitutions:
            click.echo(f'  "{orig}" → "{repl}"')
    if result.burst_fixes > 0:
        click.echo(f"Burst fixes: {result.burst_fixes}")
    if result.used_original:
        click.echo("(guard blocked transform, used original)")


@semvar_cmd.command("phrases")
@click.option("--tag", "-t", default=None, help="Filter by meaning tag")
@click.pass_context
def semvar_phrases(ctx, tag):
    """List phrases in the phrase bank."""
    from .semvar import PhraseBank, MeaningTag

    bank = PhraseBank()
    entries = bank.entries

    if tag:
        try:
            mt = MeaningTag(tag)
        except ValueError:
            click.echo(f"Unknown tag: {tag}", err=True)
            click.echo(f"Valid tags: {', '.join(t.value for t in MeaningTag)}")
            ctx.exit(1)
            return
        entries = [e for e in entries if e.tag == mt]

    click.echo(f"{'Phrase':<35} {'Tag':<20} {'Register':<10} {'Alternatives':>5}")
    click.echo("-" * 75)
    for e in entries:
        click.echo(
            f"{e.phrase:<35} {e.tag.value:<20} {e.register.value:<10} {len(e.alternatives):>5}"
        )


@semvar_cmd.command("config")
@click.pass_context
def semvar_config(ctx):
    """Show semantic variety configuration."""
    from .semvar import SemVarConfig

    cfg = SemVarConfig()
    click.echo(f"Enabled: {cfg.enabled}")
    click.echo(f"Cooldown turns: {cfg.cooldown_turns}")
    click.echo(f"Max rewrites per transform: {cfg.max_rewrites}")
    click.echo(f"N-gram size: {cfg.ngram_size}")
    click.echo(f"User-echo exception: {cfg.user_echo_exception}")


# =============================================================================
# Auto-tuning commands
# =============================================================================


@cli.group("tune")
@click.pass_context
def tune_cmd(ctx):
    """Automated tuning — threshold learning, reset tracking, calibration, budget sweep."""
    pass


@tune_cmd.command("status")
@click.pass_context
def tune_status(ctx):
    """Show tuning state."""
    from .auto_tuning import AutoTuner

    gov_dir = ensure_initialized(ctx)
    tuner_path = gov_dir / "auto_tuner.json"
    if tuner_path.exists():
        import json
        data = json.loads(tuner_path.read_text())
        at = AutoTuner.from_dict(data)
    else:
        at = AutoTuner()

    status = at.get_status()
    click.echo("Threshold Tuner:")
    click.echo(f"  Observations: {status['threshold_tuner']['observations']}")
    click.echo(f"  Min samples/regime: {status['threshold_tuner']['min_samples_per_regime']}")
    click.echo("Reset Tracker:")
    click.echo(f"  Total records: {status['reset_tracker']['total_records']}")
    click.echo(f"  Pending: {status['reset_tracker']['pending']}")
    click.echo(f"  Completed: {status['reset_tracker']['completed']}")
    click.echo("Setpoint Calibrator:")
    click.echo(f"  Domain: {status['setpoint_calibrator']['domain']}")
    click.echo(f"  Phase: {status['setpoint_calibrator']['phase']}")
    click.echo(f"  Baseline observations: {status['setpoint_calibrator']['baseline_observations']}")


@tune_cmd.command("thresholds")
@click.option("--analyze", "do_analyze", is_flag=True, help="Report threshold suggestions")
@click.option("--apply", "do_apply", is_flag=True, help="Apply confident suggestions")
@click.pass_context
def tune_thresholds(ctx, do_analyze, do_apply):
    """Analyze or apply threshold suggestions."""
    import json
    from .auto_tuning import AutoTuner
    from .regime import RegimeThresholds

    gov_dir = ensure_initialized(ctx)
    tuner_path = gov_dir / "auto_tuner.json"
    if tuner_path.exists():
        data = json.loads(tuner_path.read_text())
        at = AutoTuner.from_dict(data)
    else:
        at = AutoTuner()

    thresholds = RegimeThresholds()
    thresh_path = gov_dir / "regime_thresholds.json"
    if thresh_path.exists():
        thresholds = RegimeThresholds.from_dict(json.loads(thresh_path.read_text()))

    analysis = at.analyze_thresholds(thresholds)
    click.echo(f"Total samples: {analysis.total_samples}")
    click.echo(f"Accuracy: {analysis.accuracy:.2%}")
    click.echo(f"False positives: {analysis.fp_count}")
    click.echo(f"False negatives: {analysis.fn_count}")

    if analysis.suggestions:
        click.echo(f"\nSuggestions ({len(analysis.suggestions)}):")
        for s in analysis.suggestions:
            click.echo(f"  {s.threshold_name}: {s.current_value:.4f} -> {s.suggested_value:.4f} "
                       f"(confidence={s.confidence:.2f}, fp={s.fp_rate:.2%}, fn={s.fn_rate:.2%})")
            click.echo(f"    Reason: {s.reason}")
    else:
        click.echo("\nNo suggestions (insufficient data or current thresholds are optimal)")

    if do_apply and analysis.suggestions:
        new_thresholds = at.threshold_tuner.apply_suggestions(thresholds, analysis.suggestions)
        thresh_path.write_text(json.dumps(new_thresholds.to_dict(), indent=2))
        click.echo("\nApplied confident suggestions to regime_thresholds.json")


@tune_cmd.command("resets")
@click.option("--report", "do_report", is_flag=True, help="Show reset effectiveness stats")
@click.option("--pending", "do_pending", is_flag=True, help="Show pending reset tracking")
@click.pass_context
def tune_resets(ctx, do_report, do_pending):
    """Reset effectiveness tracking."""
    import json
    from .auto_tuning import AutoTuner

    gov_dir = ensure_initialized(ctx)
    tuner_path = gov_dir / "auto_tuner.json"
    if tuner_path.exists():
        data = json.loads(tuner_path.read_text())
        at = AutoTuner.from_dict(data)
    else:
        at = AutoTuner()

    if do_pending:
        click.echo(f"Pending resets: {at.reset_tracker.pending_count}")
        click.echo(f"Completed resets: {at.reset_tracker.completed_count}")
        return

    report = at.reset_report()
    click.echo(f"Total resets: {report.total_resets}")
    click.echo(f"Completed: {report.total_completed}")
    click.echo(f"Overall success rate: {report.overall_success_rate:.2%}")

    if report.by_type:
        click.echo("\nBy type:")
        for type_name, summary in report.by_type.items():
            click.echo(f"  {type_name}:")
            click.echo(f"    Total: {summary.total}, Restored: {summary.restored_count}")
            click.echo(f"    Success rate: {summary.success_rate:.2%}")
            if summary.avg_turns_to_restore is not None:
                click.echo(f"    Avg turns to restore: {summary.avg_turns_to_restore:.1f}")
            if summary.regime_distribution_after_5:
                click.echo(f"    Regime dist @5: {summary.regime_distribution_after_5}")


@tune_cmd.command("calibrate")
@click.option("--begin-baseline", "do_begin", is_flag=True, help="Start baseline collection")
@click.option("--end-baseline", "do_end", is_flag=True, help="End baseline, compute profile")
@click.option("--run", "do_run", is_flag=True, help="Compute calibrated setpoints")
@click.pass_context
def tune_calibrate(ctx, do_begin, do_end, do_run):
    """Setpoint calibration."""
    import json
    from .auto_tuning import AutoTuner

    gov_dir = ensure_initialized(ctx)
    tuner_path = gov_dir / "auto_tuner.json"
    if tuner_path.exists():
        data = json.loads(tuner_path.read_text())
        at = AutoTuner.from_dict(data)
    else:
        at = AutoTuner()

    cal = at.setpoint_calibrator

    if do_begin:
        cal.begin_baseline()
        tuner_path.write_text(json.dumps(at.to_dict(), indent=2))
        click.echo("Baseline collection started. Record observations with governor explore observe.")
        return

    if do_end:
        profile = cal.end_baseline()
        if profile is None:
            click.echo(f"Insufficient data ({len(cal._baseline_observations)} < {cal.MIN_BASELINE_SAMPLES})", err=True)
            ctx.exit(1)
            return
        tuner_path.write_text(json.dumps(at.to_dict(), indent=2))
        click.echo(f"Baseline computed from {profile.observation_count} observations")
        click.echo(f"  Domain: {profile.domain}")
        click.echo(f"  Revision rate: {profile.natural_revision_rate:.4f} (sd={profile.revision_stddev:.4f})")
        click.echo(f"  Contradiction rate: {profile.natural_contradiction_rate:.4f} (sd={profile.contradiction_stddev:.4f})")
        click.echo(f"  Hedge rate: {profile.natural_hedge_rate:.4f} (sd={profile.hedge_stddev:.4f})")
        click.echo(f"  Refusal rate: {profile.natural_refusal_rate:.4f} (sd={profile.refusal_stddev:.4f})")
        click.echo(f"  Rev-retraction correlation: {profile.revision_retraction_correlation:.3f}")
        return

    if do_run:
        result = cal.calibrate()
        if result.calibrated_setpoints is None:
            click.echo("No baseline profile. Run --begin-baseline first.", err=True)
            ctx.exit(1)
            return
        tuner_path.write_text(json.dumps(at.to_dict(), indent=2))
        sp = result.calibrated_setpoints
        click.echo(f"Calibration complete (confidence={result.confidence:.2f})")
        click.echo(f"  Revision target: {sp.revision_target:.4f}")
        click.echo(f"  Contradiction target: {sp.contradiction_target:.4f}")
        click.echo(f"  Hedge target: {sp.hedge_target:.4f}")
        click.echo(f"  Refusal target: {sp.refusal_target:.4f}")
        click.echo(f"  Support deficit target: {sp.support_deficit_target:.4f}")
        click.echo(f"  Retrieval coverage target: {sp.retrieval_coverage_target:.4f}")
        return

    click.echo(f"Phase: {cal.phase.value}")
    click.echo(f"Domain: {cal.domain}")
    click.echo(f"Baseline observations: {len(cal._baseline_observations)}")
    if cal._baseline_profile:
        click.echo("Baseline profile: computed")
    else:
        click.echo("Baseline profile: not yet computed")


@tune_cmd.command("budget")
@click.option("--parameter", "-p", required=True, help="Parameter name to show sweep results for")
@click.pass_context
def tune_budget(ctx, parameter):
    """Show budget sweep results for a parameter."""
    import json
    from .auto_tuning import BudgetSweeper

    gov_dir = ensure_initialized(ctx)
    sweep_path = gov_dir / f"sweep_{parameter}.json"
    if not sweep_path.exists():
        click.echo(f"No sweep data for parameter '{parameter}'", err=True)
        ctx.exit(1)
        return

    data = json.loads(sweep_path.read_text())
    sweeper = BudgetSweeper.from_dict(data)
    result = sweeper.analyze()

    click.echo(f"Parameter: {result.parameter_name}")
    click.echo(f"Points: {len(result.points)}")
    click.echo(f"Safety invariant held: {result.safety_invariant_held}")
    click.echo(f"Recommended value: {result.recommended_value}")

    if result.pareto_frontier:
        click.echo(f"\nPareto frontier ({len(result.pareto_frontier)} points):")
        for p in result.pareto_frontier:
            click.echo(f"  value={p.parameter_value:.2f}  quality={p.quality_score:.3f}  tightness={p.constraint_tightness:.3f}")


@tune_cmd.command("reset")
@click.option("--confirm", is_flag=True, required=True, help="Confirm clearing all tuning state")
@click.pass_context
def tune_reset(ctx, confirm):
    """Clear all tuning state."""
    import json
    from .auto_tuning import AutoTuner

    gov_dir = ensure_initialized(ctx)
    tuner_path = gov_dir / "auto_tuner.json"
    at = AutoTuner()
    tuner_path.write_text(json.dumps(at.to_dict(), indent=2))
    click.echo("Tuning state cleared.")


# =============================================================================
# Convergence Tuning (sub-group under tune)
# =============================================================================


@tune_cmd.group("convergence")
@click.pass_context
def tune_convergence_cmd(ctx):
    """Convergence auto-tuning — offline system identification + proposal engine."""
    pass


@tune_convergence_cmd.command("status")
@click.pass_context
def tune_convergence_status(ctx):
    """Show convergence tuning state."""
    from .convergence_tuning import ConvergenceTuner, ProposalStore

    gov_dir = ensure_initialized(ctx)
    store = ProposalStore(gov_dir.parent if gov_dir.name == ".governor" else gov_dir)
    tuner = ConvergenceTuner(store=store, gov_dir=gov_dir)
    status = tuner.get_status()

    click.echo("Convergence Tuner Status:")
    click.echo(f"  Store: {status['store_dir']}")
    click.echo(f"  Total proposals: {status['total_proposals']}")
    click.echo(f"  Total applies: {status['total_applies']}")
    if status["proposal_counts"]:
        click.echo("  By status:")
        for s, c in sorted(status["proposal_counts"].items()):
            click.echo(f"    {s}: {c}")
    else:
        click.echo("  No proposals yet.")


@tune_convergence_cmd.command("propose")
@click.option("--window", default="30d", help="Time window (e.g., 30d)")
@click.option("--mode", default=None, help="Mode filter (fiction, nonfiction, puppet, code, ops)")
@click.option("--namespace", default=None, help="Anchor namespace")
@click.option("--max", "max_proposals", default=10, type=int, help="Max proposals to generate")
@click.pass_context
def tune_convergence_propose(ctx, window, mode, namespace, max_proposals):
    """Generate tuning proposals from convergence telemetry."""
    import json
    from datetime import datetime, timedelta, timezone
    from .convergence_tuning import ConvergenceTuner, ProposalStore, Regime
    from .telemetry import TelemetryConfig, StructuredLogger

    gov_dir = ensure_initialized(ctx)
    root = gov_dir.parent if gov_dir.name == ".governor" else gov_dir
    store = ProposalStore(root)
    tuner = ConvergenceTuner(store=store, gov_dir=gov_dir)

    # Parse window
    since = None
    if window.endswith("d"):
        try:
            days = int(window[:-1])
            since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        except ValueError:
            click.echo(f"Invalid window: {window}", err=True)
            ctx.exit(1)
            return

    # Load telemetry events
    config = TelemetryConfig.load(gov_dir)
    log_dir = gov_dir / config.log_dir
    logger = StructuredLogger(log_dir, config)
    events = logger.query(since=since)

    if not events:
        click.echo("No telemetry events found.")
        return

    proposals = tuner.propose(
        events, mode=mode, anchor_namespace=namespace,
        since=since, max_proposals=max_proposals,
    )

    if not proposals:
        click.echo("No tuning opportunities identified.")
        return

    click.echo(f"Generated {len(proposals)} proposal(s):")
    for p in proposals:
        targets = ", ".join(p.scope.targets)
        click.echo(f"  {p.proposal_id}: {targets} ({p.change_set.type.value})")
        if p.predicted_impact.rationale:
            click.echo(f"    Rationale: {p.predicted_impact.rationale[0]}")


@tune_convergence_cmd.command("apply")
@click.argument("proposal_id")
@click.option("--by", "applied_by", required=True, help="Who is applying")
@click.option("--new-config-hash", default="", help="New config hash")
@click.option("--previous-config-hash", default="", help="Previous config hash")
@click.option("--model-id", default="", help="Current model ID for regime check")
@click.option("--mode", default="", help="Current mode for regime check")
@click.option("--notes", default="", help="Apply notes")
@click.pass_context
def tune_convergence_apply(ctx, proposal_id, applied_by, new_config_hash,
                           previous_config_hash, model_id, mode, notes):
    """Apply a proposal with admissibility checks."""
    from .convergence_tuning import ConvergenceTuner, ProposalStore, TuningApply

    gov_dir = ensure_initialized(ctx)
    root = gov_dir.parent if gov_dir.name == ".governor" else gov_dir
    store = ProposalStore(root)
    tuner = ConvergenceTuner(store=store, gov_dir=gov_dir)

    result = tuner.apply(
        proposal_id, applied_by=applied_by,
        new_config_hash=new_config_hash,
        previous_config_hash=previous_config_hash,
        current_model_id=model_id,
        current_mode=mode,
        notes=notes,
    )

    if isinstance(result, TuningApply):
        click.echo(f"Applied: {result.trial_id}")
        click.echo(f"  Proposal: {result.proposal_id}")
        click.echo(f"  Applied by: {result.applied_by}")
    else:
        click.echo("Apply FAILED — admissibility check violations:", err=True)
        for r in result:
            if not r.passed:
                click.echo(f"  [{r.check_name}]", err=True)
                for v in r.violations:
                    click.echo(f"    - {v}", err=True)
        ctx.exit(1)


@tune_convergence_cmd.command("rollback")
@click.argument("trial_id")
@click.pass_context
def tune_convergence_rollback(ctx, trial_id):
    """Roll back a trial."""
    from .convergence_tuning import ConvergenceTuner, ProposalStore

    gov_dir = ensure_initialized(ctx)
    root = gov_dir.parent if gov_dir.name == ".governor" else gov_dir
    store = ProposalStore(root)
    tuner = ConvergenceTuner(store=store, gov_dir=gov_dir)

    if tuner.rollback(trial_id):
        click.echo(f"Rolled back trial: {trial_id}")
    else:
        click.echo(f"Trial not found: {trial_id}", err=True)
        ctx.exit(1)


@tune_convergence_cmd.command("proposals")
@click.option("--status", default=None, help="Filter by status (proposed, approved, applied, etc.)")
@click.pass_context
def tune_convergence_proposals(ctx, status):
    """List tuning proposals."""
    from .convergence_tuning import ProposalStore, ProposalStatus

    gov_dir = ensure_initialized(ctx)
    root = gov_dir.parent if gov_dir.name == ".governor" else gov_dir
    store = ProposalStore(root)

    status_filter = None
    if status:
        try:
            status_filter = ProposalStatus(status)
        except ValueError:
            click.echo(f"Invalid status: {status}. Valid: {[s.value for s in ProposalStatus]}", err=True)
            ctx.exit(1)
            return

    proposals = store.list_proposals(status=status_filter)

    if not proposals:
        click.echo("No proposals found.")
        return

    click.echo(f"Proposals ({len(proposals)}):")
    for p in proposals:
        targets = ", ".join(p.scope.targets)
        click.echo(f"  {p.proposal_id}  [{p.approval.status.value}]  {targets}")


@tune_convergence_cmd.command("show")
@click.argument("proposal_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def tune_convergence_show(ctx, proposal_id, as_json):
    """Show proposal details."""
    import json
    from .convergence_tuning import ProposalStore

    gov_dir = ensure_initialized(ctx)
    root = gov_dir.parent if gov_dir.name == ".governor" else gov_dir
    store = ProposalStore(root)

    p = store.get_proposal(proposal_id)
    if p is None:
        click.echo(f"Proposal not found: {proposal_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(p.to_dict(), indent=2))
        return

    click.echo(f"Proposal: {p.proposal_id}")
    click.echo(f"  Schema: {p.schema_version}")
    click.echo(f"  Created: {p.created_at_utc}")
    click.echo(f"  Status: {p.approval.status.value}")
    click.echo(f"  Mode: {p.scope.mode.value}")
    click.echo(f"  Namespace: {p.scope.anchor_namespace}")
    click.echo(f"  Targets: {', '.join(p.scope.targets)}")
    click.echo(f"  Change type: {p.change_set.type.value}")
    click.echo(f"  Changes: {len(p.change_set.changes)}")
    click.echo(f"  Episodes observed: {p.evidence_window.episodes_observed}")
    click.echo(f"  Confidence: {p.predicted_impact.confidence.value}")
    if p.predicted_impact.rationale:
        click.echo(f"  Rationale: {p.predicted_impact.rationale[0]}")
    click.echo(f"  Trial: {p.trial_plan.trial_id}")
    click.echo(f"  Requires human: {p.approval.requires_human}")
    if p.approval.applied_at_utc:
        click.echo(f"  Applied at: {p.approval.applied_at_utc}")
        click.echo(f"  Applied by: {p.approval.approved_by}")


# =============================================================================
# Tainted Claim Similarity
# =============================================================================


@cli.group("taint")
@click.pass_context
def taint_cmd(ctx):
    """Tainted claim similarity — recurrence detection for bad claims."""
    pass


@taint_cmd.command("status")
@click.pass_context
def taint_status(ctx):
    """Show taint index status and statistics."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)
    s = idx.stats()

    click.echo(f"Tainted claims: {s['total_tainted']}")
    for ttype, count in s.get("by_type", {}).items():
        click.echo(f"  {ttype}: {count}")
    click.echo(f"Index tokens: {s['index_tokens']}")
    click.echo(f"Total events: {s['total_events']}")
    click.echo(f"Flagged events: {s['flagged_events']}")


@taint_cmd.command("list")
@click.pass_context
def taint_list(ctx):
    """List all tainted claims in the index."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)
    claims = idx.list_tainted()

    if not claims:
        click.echo("No tainted claims.")
        return

    for tc in claims:
        click.echo(f"  [{tc.taint_type.value}] {tc.claim_id}")
        click.echo(f"    text: {tc.normalized_text[:80]}{'...' if len(tc.normalized_text) > 80 else ''}")
        click.echo(f"    time: {tc.timestamp}")


@taint_cmd.command("add")
@click.argument("claim_id")
@click.argument("text")
@click.option("--type", "taint_type", type=click.Choice(["contradicted", "retracted"]),
              default="contradicted", help="Why the claim is tainted")
@click.pass_context
def taint_add(ctx, claim_id, text, taint_type):
    """Add a claim to the taint index."""
    from .taint import TaintIndex, TaintType

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)
    tt = TaintType(taint_type)
    tc = idx.add_tainted(claim_id, text, tt)

    click.echo(f"Added tainted claim: {tc.claim_id} ({tt.value})")
    click.echo(f"  Tokens: {len(tc.fingerprint.tokens)}")


@taint_cmd.command("remove")
@click.argument("claim_id")
@click.pass_context
def taint_remove(ctx, claim_id):
    """Remove a claim from the taint index."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)

    if idx.remove_tainted(claim_id):
        click.echo(f"Removed: {claim_id}")
    else:
        click.echo(f"Not found: {claim_id}", err=True)
        ctx.exit(1)


@taint_cmd.command("check")
@click.argument("text")
@click.option("--claim-id", default="", help="ID for the new claim being checked")
@click.pass_context
def taint_check(ctx, text, claim_id):
    """Check text against the taint index."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)
    result = idx.check(text, new_claim_id=claim_id)

    click.echo(f"Verdict: {result.verdict.value}")
    click.echo(f"Best score: {result.best_score:.3f}")
    click.echo(f"Checked against: {result.checked_against} claims")
    click.echo(f"Input tokens: {result.input_token_count}")

    if result.matches:
        click.echo(f"\nMatches ({len(result.matches)}):")
        for m in result.matches:
            flag = " *FLAGGED*" if m.similarity >= m.threshold else ""
            exact = " [exact]" if m.exact else ""
            click.echo(f"  {m.tainted_claim_id}: {m.similarity:.3f} ({m.taint_type.value}){exact}{flag}")


@taint_cmd.command("events")
@click.option("--clear", is_flag=True, help="Clear event history after display")
@click.pass_context
def taint_events(ctx, clear):
    """Show taint similarity events."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)
    idx = TaintIndex(governor_dir=gov_dir)
    events = idx.events()

    if not events:
        click.echo("No taint events.")
        return

    for e in events:
        flag = "EXACT" if e.exact else f"{e.similarity:.3f}"
        click.echo(f"  {e.new_claim_id} ~ {e.matched_claim_id}: {flag} ({e.taint_type.value})")

    if clear:
        count = idx.clear_events()
        click.echo(f"\nCleared {count} events.")


@taint_cmd.command("reset")
@click.option("--confirm", is_flag=True, required=True, help="Confirm clearing taint index")
@click.pass_context
def taint_reset(ctx, confirm):
    """Clear the taint index and event history."""
    from .taint import TaintIndex

    gov_dir = ensure_initialized(ctx)

    # Overwrite with empty state
    idx = TaintIndex(governor_dir=gov_dir)
    old_count = idx.count()
    old_events = len(idx.events())

    idx._claims.clear()
    idx._inverted.clear()
    idx._hash_index.clear()
    idx._events.clear()
    idx._save()
    idx._save_events()

    click.echo(f"Taint index cleared. Removed {old_count} claims and {old_events} events.")


# =============================================================================
# Puppet Mode
# =============================================================================


@cli.group("puppet")
@click.pass_context
def puppet_cmd(ctx):
    """Puppet mode — persona pinning with semantic safety."""
    pass


@puppet_cmd.command("list")
@click.pass_context
def puppet_list(ctx):
    """List available puppet profiles."""
    from .puppet import PuppetRegistry, _BUILTIN_PROFILES

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    for pid in reg.list_profiles():
        profile = reg.get(pid)
        marker = " *" if reg._active == pid else ""
        builtin = " (builtin)" if pid in _BUILTIN_PROFILES else " (custom)"
        click.echo(f"  {pid}{marker}{builtin}")
        if profile and profile.description:
            click.echo(f"    {profile.description}")


@puppet_cmd.command("show")
@click.argument("puppet_id")
@click.pass_context
def puppet_show(ctx, puppet_id):
    """Show details of a puppet profile."""
    import json
    from .puppet import PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)
    profile = reg.get(puppet_id)

    if profile is None:
        click.echo(f"Error: Puppet profile '{puppet_id}' not found.", err=True)
        ctx.exit(1)
        return

    click.echo(f"Puppet: {profile.puppet_id}")
    click.echo(f"Version: {profile.version}")
    click.echo(f"Description: {profile.description}")
    click.echo(f"Register: {profile.voice.register.value}")
    click.echo(f"Tone: {', '.join(profile.voice.tone_tags)}")
    click.echo(f"Verbosity cap: {profile.voice.verbosity_cap_tokens}")
    click.echo(f"Forbidden phrases: {', '.join(profile.voice.forbidden_phrases)}")
    click.echo(f"Disclaimer: {profile.disclaimer.tag_format.value} '{profile.disclaimer.tag_text}'")
    click.echo(f"Safety: spice={profile.safety.allow_spice}, insults_forbidden={profile.safety.forbid_insults}")


@puppet_cmd.command("activate")
@click.argument("puppet_id")
@click.pass_context
def puppet_activate(ctx, puppet_id):
    """Activate a puppet profile."""
    from .puppet import PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    try:
        profile = reg.activate(puppet_id)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Puppet '{puppet_id}' activated.")
    click.echo(f"  Register: {profile.voice.register.value}")
    click.echo(f"  Disclaimer: {profile.disclaimer.tag_text or '(none)'}")


@puppet_cmd.command("deactivate")
@click.pass_context
def puppet_deactivate(ctx):
    """Deactivate the current puppet."""
    from .puppet import PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)
    reg.deactivate()
    click.echo("Puppet deactivated.")


@puppet_cmd.command("status")
@click.pass_context
def puppet_status(ctx):
    """Show active puppet status."""
    from .puppet import PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    if not reg.is_active():
        click.echo("No puppet active.")
        return

    profile = reg.active_profile()
    click.echo(f"Active puppet: {profile.puppet_id}")
    click.echo(f"  Description: {profile.description}")
    click.echo(f"  Register: {profile.voice.register.value}")
    click.echo(f"  Tone: {', '.join(profile.voice.tone_tags)}")
    click.echo(f"  Verbosity cap: {profile.voice.verbosity_cap_tokens}")
    click.echo(f"  Disclaimer: {profile.disclaimer.tag_text or '(none)'}")


@puppet_cmd.command("create")
@click.argument("puppet_id")
@click.option("--file", "filepath", type=click.Path(exists=True), help="JSON file with profile definition")
@click.pass_context
def puppet_create(ctx, puppet_id, filepath):
    """Create a custom puppet profile from JSON (stdin or --file)."""
    import json
    from .puppet import PuppetProfile, PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    if filepath:
        data = json.loads(Path(filepath).read_text())
    else:
        raw = click.get_text_stream("stdin").read()
        if not raw.strip():
            click.echo("Error: Provide JSON via stdin or --file.", err=True)
            ctx.exit(1)
            return
        data = json.loads(raw)

    data["puppet_id"] = puppet_id
    profile = PuppetProfile.from_dict(data)

    try:
        reg.create(profile)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Puppet profile '{puppet_id}' created.")


@puppet_cmd.command("delete")
@click.argument("puppet_id")
@click.pass_context
def puppet_delete(ctx, puppet_id):
    """Delete a custom puppet profile."""
    from .puppet import PuppetRegistry

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    try:
        reg.delete(puppet_id)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Puppet profile '{puppet_id}' deleted.")


@puppet_cmd.command("test")
@click.argument("puppet_id")
@click.pass_context
def puppet_test(ctx, puppet_id):
    """Test a puppet profile with sample text."""
    from .puppet import PuppetRegistry, PuppetRenderer, create_skeleton

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)
    profile = reg.get(puppet_id)

    if profile is None:
        click.echo(f"Error: Puppet profile '{puppet_id}' not found.", err=True)
        ctx.exit(1)
        return

    sample = "The system is likely experiencing latency issues. There are approximately 42 pending requests. According to [1], this might be related to the database connection pool."
    skeleton = create_skeleton(sample)
    renderer = PuppetRenderer()
    result = renderer.render(skeleton, profile)

    click.echo(f"Profile: {puppet_id}")
    click.echo(f"Verdict: {result.verdict.value}")
    click.echo(f"Attempts: {result.attempts}")
    click.echo(f"Disclaimer: {result.disclaimer_applied}")
    click.echo(f"Forbidden removed: {result.forbidden_phrases_removed}")
    click.echo(f"\n--- Original ---\n{result.original}")
    click.echo(f"\n--- Rendered ---\n{result.rendered}")

    if result.guard_result.violations:
        click.echo(f"\nViolations: {len(result.guard_result.violations)}")
        for v in result.guard_result.violations:
            click.echo(f"  [{v.rule_id.value}] {v.description}")

    if result.guard_result.warnings:
        click.echo(f"\nWarnings: {len(result.guard_result.warnings)}")
        for w in result.guard_result.warnings:
            click.echo(f"  [{w.warn_id.value}] {w.description}")


@puppet_cmd.command("render")
@click.argument("text")
@click.pass_context
def puppet_render(ctx, text):
    """Render text through the active puppet."""
    from .puppet import PuppetRegistry, PuppetRenderer, create_skeleton

    gov_dir = ensure_initialized(ctx)
    reg = PuppetRegistry(governor_dir=gov_dir)

    if not reg.is_active():
        click.echo("Error: No puppet active. Use 'governor puppet activate <id>' first.", err=True)
        ctx.exit(1)
        return

    profile = reg.active_profile()
    skeleton = create_skeleton(text)
    renderer = PuppetRenderer()
    result = renderer.render(skeleton, profile)

    click.echo(result.rendered)

    if result.guard_result.warnings:
        for w in result.guard_result.warnings:
            click.echo(click.style(f"  warning: [{w.warn_id.value}] {w.description}", fg="yellow"), err=True)


# =============================================================================
# Spine commands (Phase A2: project structure locking)
# =============================================================================


@cli.group("spine")
@click.pass_context
def spine_cmd(ctx):
    """Manage locked project spines (structural constraints)."""
    pass


@spine_cmd.command("lock")
@click.argument("spine_id")
@click.option("--description", "-d", default="", help="Spine description")
@click.option("--file", "-f", "spec_file", type=click.Path(exists=True), help="JSON file with spine structure")
@click.option("--required-file", "-rf", multiple=True, help="Add a required file")
@click.option("--required-dir", "-rd", multiple=True, help="Add a required directory")
@click.option("--forbid", multiple=True, help="Add a forbidden path pattern")
@click.pass_context
def spine_lock(ctx, spine_id, description, spec_file, required_file, required_dir, forbid):
    """Lock a project spine (structural constraints)."""
    from .spine import Spine, SpineManager

    gov_dir = ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    manager = SpineManager(root)

    structure = {}
    if spec_file:
        structure = json.loads(Path(spec_file).read_text())
    else:
        if required_file:
            structure["files"] = {f: "required" for f in required_file}
        if required_dir:
            structure["directories"] = {d: "required" for d in required_dir}
        if forbid:
            structure["forbidden_paths"] = list(forbid)

    spine = Spine(id=spine_id, structure=structure, description=description)
    manager.lock(spine)
    click.echo(f"Spine '{spine_id}' locked.")
    if structure:
        for key, val in structure.items():
            click.echo(f"  {key}: {val}")


@spine_cmd.command("unlock")
@click.argument("spine_id")
@click.option("--confirm", is_flag=True, required=True, help="Confirm unlock")
@click.pass_context
def spine_unlock(ctx, spine_id, confirm):
    """Unlock (remove) a spine."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)
    if manager.unlock(spine_id):
        click.echo(f"Spine '{spine_id}' unlocked.")
    else:
        click.echo(f"Spine '{spine_id}' not found.", err=True)
        ctx.exit(1)


@spine_cmd.command("list")
@click.pass_context
def spine_list(ctx):
    """List all locked spines."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)
    spines = manager.list_spines()

    if not spines:
        click.echo("No spines locked.")
        return

    active = manager.active_spine()
    for s in spines:
        marker = " *" if active and active.id == s.id else ""
        click.echo(f"  {s.id}{marker}: {s.description or '(no description)'}")
        if s.structure.get("files"):
            click.echo(f"    files: {list(s.structure['files'].keys())}")
        if s.structure.get("forbidden_paths"):
            click.echo(f"    forbidden: {s.structure['forbidden_paths']}")


@spine_cmd.command("show")
@click.argument("spine_id")
@click.pass_context
def spine_show(ctx, spine_id):
    """Show details of a spine."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)
    spine = manager.get(spine_id)

    if not spine:
        click.echo(f"Spine '{spine_id}' not found.", err=True)
        ctx.exit(1)
        return

    click.echo(f"Spine: {spine.id}")
    click.echo(f"Description: {spine.description or '(none)'}")
    click.echo(f"Locked at: {spine.locked_at}")
    click.echo(f"Locked by: {spine.locked_by}")
    click.echo(f"Unlock requires: {spine.unlock_requires}")
    click.echo("\nStructure:")
    click.echo(json.dumps(spine.structure, indent=2))


@spine_cmd.command("activate")
@click.argument("spine_id")
@click.pass_context
def spine_activate(ctx, spine_id):
    """Set a spine as the active constraint."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)
    if manager.set_active(spine_id):
        click.echo(f"Spine '{spine_id}' activated.")
    else:
        click.echo(f"Spine '{spine_id}' not found.", err=True)
        ctx.exit(1)


@spine_cmd.command("deactivate")
@click.pass_context
def spine_deactivate(ctx):
    """Deactivate the current spine."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)
    manager.deactivate()
    click.echo("Spine deactivated.")


@spine_cmd.command("check")
@click.option("--file-modified", "-m", multiple=True, help="Files being modified")
@click.option("--file-created", "-c", multiple=True, help="Files being created")
@click.option("--file-deleted", "-d", multiple=True, help="Files being deleted")
@click.pass_context
def spine_check(ctx, file_modified, file_created, file_deleted):
    """Check a proposal against the active spine."""
    from .spine import SpineManager

    root = Path(ctx.obj["root"])
    manager = SpineManager(root)

    if manager.active_spine() is None:
        click.echo("No active spine.")
        return

    proposal = {
        "files_modified": list(file_modified),
        "files_created": list(file_created),
        "files_deleted": list(file_deleted),
    }
    result = manager.verify_proposal(proposal)

    if result.valid:
        click.echo("Proposal is spine-compliant.")
    else:
        click.echo(f"Spine violations ({len(result.violations)}):")
        for v in result.violations:
            click.echo(f"  [{v.path}] {v.message}")


# =============================================================================
# Invariant management commands (Deferred 1: invariant lifecycle)
# =============================================================================


def _generate_invariant_id(kind: str, params: dict) -> str:
    """Generate a default ID from kind and params."""
    if kind == "test":
        cmd = params.get("command", "pytest")
        return f"test_{cmd.replace('/', '_').replace(' ', '_')}"
    elif kind == "file-exists":
        path = params.get("path", "unknown")
        return f"file_{path.replace('/', '_').replace('.', '_')}"
    elif kind == "dir-exists":
        path = params.get("path", "unknown")
        return f"dir_{path.replace('/', '_').replace('.', '_')}"
    elif kind == "forbidden":
        pat = params.get("pattern", "unknown")
        return f"forbidden_{pat.replace('*', 'star').replace('/', '_').replace('.', '_')}"
    elif kind == "no-secrets":
        return "no_secrets"
    elif kind == "max-file-size":
        kb = params.get("max_kb", 500)
        return f"max_file_size_{kb}kb"
    return f"inv_{kind}"


def _print_invariant_result(result, inv=None) -> None:
    """Print a formatted invariant check result."""
    status = click.style("PASS", fg="green") if result.passed else click.style("FAIL", fg="red")
    msg = result.message
    suffix = ""
    if inv and inv.on_violation == "warn":
        suffix = click.style(" (warn)", fg="yellow")
    click.echo(f"  [{status}] {result.invariant_id}: {msg}{suffix}")


@cli.group("invariant")
@click.pass_context
def invariant_cmd(ctx):
    """Manage persistent invariant specs."""
    pass


@invariant_cmd.command("add")
@click.argument("kind", type=click.Choice(["test", "file-exists", "dir-exists", "forbidden", "no-secrets", "max-file-size"]))
@click.option("--id", "spec_id", default=None, help="Custom invariant ID")
@click.option("--path", "path_param", default=None, help="Path (for file-exists, dir-exists)")
@click.option("--pattern", default=None, help="Glob pattern (for forbidden)")
@click.option("--command", default=None, help="Test command (for test)")
@click.option("--args", default=None, help="Test args, space-separated (for test)")
@click.option("--max-kb", type=int, default=None, help="Max file size in KB (for max-file-size)")
@click.option("--description", default=None, help="Description (for forbidden)")
@click.option("--on-violation", type=click.Choice(["block", "warn"]), default="block", help="Action on violation")
@click.pass_context
def invariant_add(ctx, kind, spec_id, path_param, pattern, command, args, max_kb, description, on_violation):
    """Add a persistent invariant spec."""
    from .invariant_store import InvariantSpec, InvariantStore, VALID_KINDS

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    store = InvariantStore(root)

    # Build params from options
    params: dict = {}
    if kind == "test":
        if command is None:
            command = "pytest"
        params["command"] = command
        if args:
            params["args"] = args
    elif kind in ("file-exists", "dir-exists"):
        if path_param is None:
            click.echo(f"Error: --path required for kind '{kind}'.", err=True)
            ctx.exit(1)
            return
        params["path"] = path_param
    elif kind == "forbidden":
        if pattern is None:
            click.echo("Error: --pattern required for kind 'forbidden'.", err=True)
            ctx.exit(1)
            return
        params["pattern"] = pattern
        if description:
            params["description"] = description
    elif kind == "no-secrets":
        pass
    elif kind == "max-file-size":
        if max_kb is None:
            max_kb = 500
        params["max_kb"] = max_kb

    # Generate or use provided ID
    if spec_id is None:
        spec_id = _generate_invariant_id(kind, params)

    spec = InvariantSpec(
        id=spec_id,
        kind=kind,
        params=params,
        on_violation=on_violation,
    )

    # Validate
    errors = spec.validate_params()
    if errors:
        for e in errors:
            click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    store.add(spec)
    violation_label = click.style("warn", fg="yellow") if on_violation == "warn" else "block"
    click.echo(f"Invariant '{spec_id}' added (kind={kind}, on_violation={violation_label}).")
    if params:
        for k, v in params.items():
            click.echo(f"  {k}: {v}")


@invariant_cmd.command("list")
@click.pass_context
def invariant_list(ctx):
    """List all invariant specs."""
    from .invariant_store import InvariantStore

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    store = InvariantStore(root)
    specs = store.list_all()

    if not specs:
        click.echo("No invariants defined.")
        return

    for spec in specs:
        status = "enabled" if spec.enabled else click.style("disabled", fg="yellow")
        violation = click.style("warn", fg="yellow") if spec.on_violation == "warn" else "block"
        click.echo(f"  {spec.id:30s}  kind={spec.kind:15s}  on_violation={violation:5s}  {status}")

    click.echo(f"\nTotal: {len(specs)}")


@invariant_cmd.command("show")
@click.argument("spec_id")
@click.pass_context
def invariant_show(ctx, spec_id):
    """Show details of an invariant spec."""
    from .invariant_store import InvariantStore

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    store = InvariantStore(root)
    spec = store.get(spec_id)

    if spec is None:
        click.echo(f"Invariant '{spec_id}' not found.", err=True)
        ctx.exit(1)
        return

    click.echo(f"ID: {spec.id}")
    click.echo(f"Kind: {spec.kind}")
    click.echo(f"On violation: {spec.on_violation}")
    click.echo(f"Enabled: {spec.enabled}")
    click.echo(f"Created: {spec.created_at}")
    if spec.params:
        click.echo("Params:")
        for k, v in spec.params.items():
            click.echo(f"  {k}: {v}")


@invariant_cmd.command("remove")
@click.argument("spec_id")
@click.pass_context
def invariant_remove(ctx, spec_id):
    """Remove an invariant spec."""
    from .invariant_store import InvariantStore

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    store = InvariantStore(root)

    if store.remove(spec_id):
        click.echo(f"Invariant '{spec_id}' removed.")
    else:
        click.echo(f"Invariant '{spec_id}' not found.", err=True)
        ctx.exit(1)


@invariant_cmd.command("check")
@click.option("--id", "spec_id", default=None, help="Check a specific invariant (default: all)")
@click.pass_context
def invariant_check(ctx, spec_id):
    """Run invariant checks (materialize and verify)."""
    from .invariant_store import InvariantStore

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])
    store = InvariantStore(root)

    if spec_id:
        inv = store.materialize(spec_id)
        if inv is None:
            click.echo(f"Invariant '{spec_id}' not found or failed to materialize.", err=True)
            ctx.exit(1)
            return
        result = inv.check(root=root, files_touched=[])
        _print_invariant_result(result, inv)
        if not result.passed:
            ctx.exit(1)
        return

    inv_set = store.materialize_all()
    if not inv_set.invariants:
        click.echo("No invariants to check.")
        return

    results = inv_set.check_all(root=root, files_touched=[])
    passed = 0
    failed = 0
    warned = 0
    for result in results:
        inv = inv_set.get(result.invariant_id)
        _print_invariant_result(result, inv)
        if result.passed:
            passed += 1
        elif inv and inv.on_violation == "warn":
            warned += 1
        else:
            failed += 1

    click.echo(f"\nSummary: {passed} passed, {failed} failed, {warned} warned")
    if failed > 0:
        ctx.exit(1)


# =============================================================================
# Autonomous session commands (Phase A3: session lifecycle)
# =============================================================================


@cli.group("autonomous")
@click.pass_context
def autonomous_cmd(ctx):
    """Manage autonomous execution sessions."""
    pass


@autonomous_cmd.command("list")
@click.option("--active", "active_only", is_flag=True, help="Show only active sessions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def auto_list(ctx, active_only, as_json):
    """List autonomous execution sessions."""
    from .execution import SessionManager

    root = Path(ctx.obj["root"])
    manager = SessionManager(root)
    sessions = manager.list_sessions(active_only=active_only)

    if as_json:
        click.echo(json.dumps([s.to_dict() for s in sessions], indent=2))
        return

    if not sessions:
        click.echo("No sessions found.")
        return

    for s in sessions:
        status_color = {
            "running": "green",
            "paused": "yellow",
            "stopped": "red",
            "completed": "blue",
        }.get(s.status.value, "white")

        click.echo(
            f"  {s.session_id}  "
            f"{click.style(s.status.value, fg=status_color):12s}  "
            f"iter={s.used.iterations}  "
            f"tokens={s.used.tokens}  "
            f"task={s.task[:50]}"
        )
    click.echo(f"\nTotal: {len(sessions)}")


@autonomous_cmd.command("show")
@click.argument("session_id")
@click.pass_context
def auto_show(ctx, session_id):
    """Show details of an execution session."""
    from .execution import SessionManager

    root = Path(ctx.obj["root"])
    manager = SessionManager(root)
    state = manager.get(session_id)

    if state is None:
        click.echo(f"Session '{session_id}' not found.", err=True)
        ctx.exit(1)
        return

    click.echo(f"Session: {state.session_id}")
    click.echo(f"Task: {state.task}")
    click.echo(f"Status: {state.status.value}")
    if state.stop_reason:
        click.echo(f"Stop reason: {state.stop_reason.value}")
    click.echo(f"Spine: {state.spine_id or '(none)'}")
    click.echo(f"Invariants: {state.invariant_ids or '(none)'}")
    click.echo(f"Started: {state.started_at}")
    if state.last_checkpoint:
        click.echo(f"Last checkpoint: {state.last_checkpoint}")
    click.echo("\nUsage:")
    click.echo(f"  Iterations: {state.used.iterations}")
    click.echo(f"  Tokens: {state.used.tokens}")
    click.echo(f"  Time: {state.used.elapsed_seconds:.1f}s")
    click.echo(f"  Cost: ${state.used.cost_usd:.4f}")

    if state.budget.max_iterations or state.budget.max_tokens:
        click.echo("\nBudget:")
        if state.budget.max_iterations:
            click.echo(f"  Max iterations: {state.budget.max_iterations}")
        if state.budget.max_tokens:
            click.echo(f"  Max tokens: {state.budget.max_tokens}")
        if state.budget.max_time_seconds:
            click.echo(f"  Max time: {state.budget.max_time_seconds}s")
        if state.budget.max_cost_usd:
            click.echo(f"  Max cost: ${state.budget.max_cost_usd:.2f}")

    if state.violations:
        click.echo(f"\nViolations ({len(state.violations)}):")
        for v in state.violations:
            click.echo(f"  [{v['invariant_id']}] {v['message']}")

    if state.progress:
        click.echo("\nProgress:")
        for k, v in state.progress.items():
            click.echo(f"  {k}: {v}")


@autonomous_cmd.command("delete")
@click.argument("session_id")
@click.option("--confirm", is_flag=True, required=True, help="Confirm deletion")
@click.pass_context
def auto_delete(ctx, session_id, confirm):
    """Delete an execution session."""
    from .execution import SessionManager

    root = Path(ctx.obj["root"])
    manager = SessionManager(root)
    if manager.delete(session_id):
        click.echo(f"Session '{session_id}' deleted.")
    else:
        click.echo(f"Session '{session_id}' not found.", err=True)
        ctx.exit(1)


@autonomous_cmd.command("handoff")
@click.argument("session_id")
@click.pass_context
def auto_handoff(ctx, session_id):
    """Show handoff summary for a session (for human review)."""
    from .execution import SessionManager

    root = Path(ctx.obj["root"])
    manager = SessionManager(root)
    state = manager.get(session_id)

    if state is None:
        click.echo(f"Session '{session_id}' not found.", err=True)
        ctx.exit(1)
        return

    click.echo("=" * 60)
    click.echo(f"HANDOFF: Session {state.session_id}")
    click.echo("=" * 60)
    click.echo(f"Task: {state.task}")
    click.echo(f"Status: {state.status.value}")
    if state.stop_reason:
        click.echo(f"Stop reason: {state.stop_reason.value}")
    click.echo(f"Iterations completed: {state.used.iterations}")
    click.echo(f"Tokens used: {state.used.tokens}")
    click.echo(f"Cost: ${state.used.cost_usd:.4f}")

    if state.violations:
        click.echo(f"\nViolations encountered: {len(state.violations)}")
        for v in state.violations:
            click.echo(f"  - [{v['invariant_id']}] {v['message']}")

    if state.progress:
        click.echo("\nProgress notes:")
        for k, v in state.progress.items():
            click.echo(f"  {k}: {v}")

    if state.is_active:
        remaining = state.budget.remaining(state.used)
        if remaining:
            click.echo("\nRemaining budget:")
            for k, v in remaining.items():
                click.echo(f"  {k}: {v}")

    click.echo("=" * 60)


@autonomous_cmd.command("run")
@click.option("--task", required=True, help="Task description for the execution")
@click.option("--budget", "budget_spec", default=None, help="Budget spec (e.g. 'tokens=100000,iterations=50')")
@click.option("--spine-id", default=None, help="Spine to enforce during execution")
@click.option("--dry-run", is_flag=True, help="Validate config, create PAUSED session, report what would happen")
@click.pass_context
def auto_run(ctx, task, budget_spec, spine_id, dry_run):
    """Run an autonomous execution session."""
    from .execution import ExecutionBudget, ExecutionStatus, SessionManager
    from .executor import AutonomousExecutor, ExecutorConfig, StepResult
    from .invariant_store import InvariantStore
    from .spine import SpineManager

    ensure_initialized(ctx)
    root = Path(ctx.obj["root"])

    # Parse budget
    if budget_spec:
        budget = ExecutionBudget.from_spec(budget_spec)
    else:
        budget = ExecutionBudget(max_iterations=1)

    # Validate spine if specified
    spine_manager = SpineManager(root)
    if spine_id:
        spine = spine_manager.get(spine_id)
        if spine is None:
            click.echo(f"Spine '{spine_id}' not found.", err=True)
            ctx.exit(1)
            return

    # Materialize invariants from store
    store = InvariantStore(root)
    inv_set = store.materialize_all()

    # Session manager
    session_manager = SessionManager(root)

    if dry_run:
        # Create PAUSED session and report
        state = session_manager.create(
            task=task,
            spine_id=spine_id,
            invariant_ids=[i.id for i in inv_set.invariants],
            budget=budget,
        )
        state.pause()
        session_manager.save(state)

        click.echo("Dry run — session created in PAUSED state.")
        click.echo(f"  Session ID: {state.session_id}")
        click.echo(f"  Task: {task}")
        click.echo(f"  Spine: {spine_id or '(none)'}")
        click.echo(f"  Invariants: {len(inv_set.invariants)}")
        for inv in inv_set.invariants:
            click.echo(f"    - {inv.id} ({inv.on_violation})")
        click.echo("  Budget:")
        if budget.max_iterations is not None:
            click.echo(f"    max_iterations: {budget.max_iterations}")
        if budget.max_tokens is not None:
            click.echo(f"    max_tokens: {budget.max_tokens}")
        if budget.max_time_seconds is not None:
            click.echo(f"    max_time: {budget.max_time_seconds}s")
        if budget.max_cost_usd is not None:
            click.echo(f"    max_cost: ${budget.max_cost_usd:.2f}")
        return

    # Normal mode: noop step that completes in 1 iteration
    def noop_step(state, iteration):
        return StepResult(
            success=True,
            message=f"Noop step {iteration} (no real agent)",
            done=True,
        )

    executor = AutonomousExecutor(
        spine_manager=spine_manager,
        invariants=inv_set,
        session_manager=session_manager,
        config=ExecutorConfig(checkpoint_interval=1),
    )

    click.echo(f"Starting execution: {task}")
    click.echo(f"  Spine: {spine_id or '(none)'}")
    click.echo(f"  Invariants: {len(inv_set.invariants)}")

    final_state = executor.execute(
        step_fn=noop_step,
        task=task,
        budget=budget,
        spine_id=spine_id,
    )

    # Report results
    status_color = {
        "running": "green",
        "paused": "yellow",
        "stopped": "red",
        "completed": "blue",
    }.get(final_state.status.value, "white")

    click.echo(f"\nSession: {final_state.session_id}")
    click.echo(f"Status: {click.style(final_state.status.value, fg=status_color)}")
    if final_state.stop_reason:
        click.echo(f"Stop reason: {final_state.stop_reason.value}")
    click.echo(f"Iterations: {final_state.used.iterations}")

    if final_state.violations:
        click.echo(f"\nViolations ({len(final_state.violations)}):")
        for v in final_state.violations:
            click.echo(f"  [{v['invariant_id']}] {v['message']}")


# =============================================================================
# Telemetry (Deferred 4, B2)
# =============================================================================


@cli.group("telemetry")
@click.pass_context
def telemetry_group(ctx: click.Context) -> None:
    """Structured telemetry: logging, analysis, export."""
    pass


@telemetry_group.command("enable")
@click.option("--logging/--no-logging", default=True, help="Enable/disable JSONL logging")
@click.option("--retention-days", type=int, default=None, help="Log retention in days")
@click.option("--redact-prompts/--no-redact-prompts", default=None, help="Redact prompts in logs")
@click.option("--redact-contents/--no-redact-contents", default=None, help="Redact file contents")
@click.pass_context
def telemetry_enable(
    ctx: click.Context,
    logging: bool,
    retention_days: int | None,
    redact_prompts: bool | None,
    redact_contents: bool | None,
) -> None:
    """Enable telemetry and configure settings."""
    from .telemetry import TelemetryConfig

    gov_dir = ensure_initialized(ctx)
    config = TelemetryConfig.load(gov_dir)

    config.logging_enabled = logging
    if retention_days is not None:
        config.log_retention_days = retention_days
    if redact_prompts is not None:
        config.redact_prompts = redact_prompts
    if redact_contents is not None:
        config.redact_file_contents = redact_contents

    config.save(gov_dir)

    # Ensure logs directory exists
    log_dir = gov_dir / config.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    click.echo("Telemetry enabled.")
    click.echo(f"  Logging: {config.logging_enabled}")
    click.echo(f"  Log dir: {log_dir}")
    click.echo(f"  Retention: {config.log_retention_days} days")
    click.echo(f"  Redact prompts: {config.redact_prompts}")
    click.echo(f"  Redact contents: {config.redact_file_contents}")


@telemetry_group.command("disable")
@click.pass_context
def telemetry_disable(ctx: click.Context) -> None:
    """Disable telemetry logging (preserves existing logs)."""
    from .telemetry import TelemetryConfig

    gov_dir = ensure_initialized(ctx)
    config = TelemetryConfig.load(gov_dir)
    config.logging_enabled = False
    config.save(gov_dir)
    click.echo("Telemetry logging disabled. Existing logs preserved.")


@telemetry_group.command("status")
@click.pass_context
def telemetry_status(ctx: click.Context) -> None:
    """Show telemetry configuration and log statistics."""
    from .telemetry import TelemetryConfig, get_logger

    gov_dir = ensure_initialized(ctx)
    config = TelemetryConfig.load(gov_dir)

    click.echo("Telemetry Configuration:")
    click.echo(f"  Logging: {config.logging_enabled}")
    click.echo(f"  Log dir: {config.log_dir}")
    click.echo(f"  Retention: {config.log_retention_days} days")
    click.echo(f"  Max size: {config.log_max_size_mb} MB")
    click.echo(f"  Min level: {config.min_level}")
    click.echo(f"  Redact prompts: {config.redact_prompts}")
    click.echo(f"  Redact contents: {config.redact_file_contents}")

    log_dir = gov_dir / config.log_dir
    if log_dir.exists():
        logger = get_logger(gov_dir)
        stats = logger.stats()
        click.echo("\nLog Statistics:")
        click.echo(f"  Total events: {stats.total_events}")
        click.echo(f"  Log files: {len(stats.log_files)}")
        click.echo(f"  Total size: {stats.total_size_bytes:,} bytes")
        if stats.oldest:
            click.echo(f"  Oldest: {stats.oldest}")
        if stats.newest:
            click.echo(f"  Newest: {stats.newest}")
        if stats.by_type:
            click.echo("  By type:")
            for t, c in sorted(stats.by_type.items()):
                click.echo(f"    {t}: {c}")
        if stats.by_level:
            click.echo("  By level:")
            for lv, c in sorted(stats.by_level.items()):
                click.echo(f"    {lv}: {c}")
    else:
        click.echo("\nNo logs directory found.")


@telemetry_group.command("logs")
@click.option("--last", "last_n", type=int, default=None, help="Show last N events")
@click.option("--type", "event_type", type=str, default=None, help="Filter by event type")
@click.option("--level", "level", type=str, default=None, help="Filter by minimum level")
@click.option("--since", type=str, default=None, help="Filter events since timestamp (ISO)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def telemetry_logs(
    ctx: click.Context,
    last_n: int | None,
    event_type: str | None,
    level: str | None,
    since: str | None,
    as_json: bool,
) -> None:
    """Query telemetry events."""
    from .telemetry import TelemetryEventType, TelemetryLevel, LEVEL_ORDER, get_logger

    gov_dir = ensure_initialized(ctx)
    logger = get_logger(gov_dir)

    et = None
    if event_type:
        try:
            et = TelemetryEventType(event_type)
        except ValueError:
            click.echo(f"Unknown event type: {event_type}", err=True)
            click.echo(f"Valid types: {', '.join(t.value for t in TelemetryEventType)}", err=True)
            ctx.exit(1)
            return

    events = logger.read_events(last_n=last_n, event_type=et, since=since)

    # Apply level filter
    if level:
        try:
            min_lv = TelemetryLevel(level)
        except ValueError:
            click.echo(f"Unknown level: {level}", err=True)
            ctx.exit(1)
            return
        min_order = LEVEL_ORDER.get(min_lv, 0)
        events = [e for e in events if LEVEL_ORDER.get(e.level, 0) >= min_order]

    if not events:
        click.echo("No events found.")
        return

    if as_json:
        click.echo(json.dumps([e.to_dict() for e in events], indent=2))
    else:
        for ev in events:
            ts = ev.timestamp[:19] if len(ev.timestamp) > 19 else ev.timestamp
            lv = ev.level.value if hasattr(ev.level, "value") else ev.level
            et_val = ev.event_type.value if hasattr(ev.event_type, "value") else ev.event_type
            line = f"[{ts}] {lv.upper():5s} {et_val}"
            if ev.duration_ms is not None:
                line += f" ({ev.duration_ms:.0f}ms)"
            # Show key fields
            f = ev.fields
            if "proposal_id" in f:
                line += f" proposal={f['proposal_id']}"
            if "outcome" in f:
                line += f" outcome={f['outcome']}"
            if "model" in f:
                line += f" model={f['model']}"
            if "cost_usd" in f and f["cost_usd"]:
                line += f" cost=${f['cost_usd']:.4f}"
            if "success" in f:
                line += f" success={f['success']}"
            if "error_type" in f and f["error_type"]:
                line += f" error={f['error_type']}"
            if "message" in f and f["message"]:
                line += f" msg={f['message'][:60]}"
            click.echo(line)


@telemetry_group.command("analyze")
@click.argument("report_type", type=click.Choice(["costs", "performance", "convergence"]))
@click.option("--since", type=str, default=None, help="Analyze events since timestamp (ISO)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def telemetry_analyze(
    ctx: click.Context,
    report_type: str,
    since: str | None,
    as_json: bool,
) -> None:
    """Analyze telemetry data (costs, performance, or convergence)."""
    from .telemetry import analyze_costs, analyze_convergence, analyze_performance, get_logger

    gov_dir = ensure_initialized(ctx)
    logger = get_logger(gov_dir)
    events = logger.read_events(since=since)

    if report_type == "costs":
        report = analyze_costs(events, since=since)
        if as_json:
            click.echo(json.dumps(report.to_dict(), indent=2))
        else:
            click.echo("Cost Analysis:")
            click.echo(f"  Total cost: ${report.total_cost_usd:.4f}")
            click.echo(f"  Total calls: {report.total_calls}")
            click.echo(f"  Input tokens: {report.total_input_tokens:,}")
            click.echo(f"  Output tokens: {report.total_output_tokens:,}")
            if report.by_model:
                click.echo("  By model:")
                for m, c in sorted(report.by_model.items(), key=lambda x: -x[1]):
                    click.echo(f"    {m}: ${c:.4f}")
            if report.by_operation:
                click.echo("  By operation:")
                for op, c in sorted(report.by_operation.items(), key=lambda x: -x[1]):
                    click.echo(f"    {op}: ${c:.4f}")
            if report.period:
                click.echo(f"  Period: {report.period}")
    elif report_type == "performance":
        report = analyze_performance(events)
        if as_json:
            click.echo(json.dumps(report.to_dict(), indent=2))
        else:
            click.echo("Performance Analysis:")
            click.echo(f"  Verification latency p50: {report.verification_latency_p50:.1f}ms")
            click.echo(f"  Verification latency p95: {report.verification_latency_p95:.1f}ms")
            click.echo(f"  Verification latency p99: {report.verification_latency_p99:.1f}ms")
            click.echo(f"  Approval rate: {report.approval_rate:.1%}")
            click.echo(f"  Total proposals: {report.total_proposals}")
            click.echo(f"  Verified: {report.total_verified}")
            click.echo(f"  Rejected: {report.total_rejected}")
            click.echo(f"  Avg claims/proposal: {report.avg_claims_per_proposal:.1f}")
    else:
        conv_report = analyze_convergence(events, since=since)
        if as_json:
            click.echo(json.dumps(conv_report.to_dict(), indent=2))
        else:
            click.echo("Convergence Analysis:")
            click.echo(f"  Total runs: {conv_report.total_runs}")
            click.echo(f"  Accepted: {conv_report.accepted}")
            click.echo(f"  Refused: {conv_report.refused}")
            click.echo(f"  Escalated: {conv_report.escalated}")
            click.echo(f"  Acceptance rate: {conv_report.acceptance_rate:.1%}")
            click.echo(f"  Avg attempts/run: {conv_report.avg_attempts:.1f}")
            click.echo(f"  Avg tokens/run: {conv_report.avg_tokens_per_run:.0f}")
            click.echo(f"  Avg latency/run: {conv_report.avg_latency_per_run_ms:.1f}ms")
            click.echo(f"  Efficiency (tokens/error_reduction): {conv_report.efficiency:.1f}")
            click.echo(f"  Monotone rate: {conv_report.monotone_rate:.1%}")
            click.echo(f"  Oscillation rate: {conv_report.oscillation_rate:.1%}")
            click.echo(f"  Windup count: {conv_report.windup_count}")
            if conv_report.anchor_stats:
                click.echo("  Per-anchor stats:")
                for aid, stats in sorted(conv_report.anchor_stats.items()):
                    click.echo(f"    {aid}: violations={stats.violation_count}, runs={stats.run_count}, deadzones={stats.deadzone_count}")
                    if stats.action_success_rates:
                        for act, rate in stats.action_success_rates.items():
                            click.echo(f"      {act}: {rate:.1%} success")
            if conv_report.interference_graph:
                click.echo("  Interference edges:")
                for edge, count in sorted(conv_report.interference_graph.items(), key=lambda x: -x[1]):
                    click.echo(f"    {edge}: {count}x")


@telemetry_group.command("export")
@click.option("--format", "fmt", type=click.Choice(["csv", "json"]), default="json", help="Export format")
@click.option("--output", "output_path", type=click.Path(), required=True, help="Output file path")
@click.option("--since", type=str, default=None, help="Export events since timestamp")
@click.option("--type", "event_type", type=str, default=None, help="Filter by event type")
@click.pass_context
def telemetry_export(
    ctx: click.Context,
    fmt: str,
    output_path: str,
    since: str | None,
    event_type: str | None,
) -> None:
    """Export telemetry events to a file."""
    from .telemetry import TelemetryEventType, export_events, get_logger

    gov_dir = ensure_initialized(ctx)
    logger = get_logger(gov_dir)

    et = None
    if event_type:
        try:
            et = TelemetryEventType(event_type)
        except ValueError:
            click.echo(f"Unknown event type: {event_type}", err=True)
            ctx.exit(1)
            return

    events = logger.read_events(event_type=et, since=since)
    count = export_events(events, Path(output_path), fmt=fmt)
    click.echo(f"Exported {count} events to {output_path} ({fmt})")


@telemetry_group.command("rotate-logs")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
@click.pass_context
def telemetry_rotate(ctx: click.Context, dry_run: bool) -> None:
    """Delete log files older than retention period."""
    from .telemetry import TelemetryConfig, get_logger

    gov_dir = ensure_initialized(ctx)
    config = TelemetryConfig.load(gov_dir)
    logger = get_logger(gov_dir)

    if dry_run:
        from datetime import timedelta
        cutoff = datetime.now(timezone.utc) - timedelta(days=config.log_retention_days)
        cutoff_str = cutoff.strftime("%Y%m%d")
        click.echo(f"Retention: {config.log_retention_days} days (cutoff: {cutoff_str})")
        for f in logger.list_log_files():
            name = f.stem
            parts = name.split("-", 1)
            if len(parts) >= 2:
                date_part = parts[1].split(".")[0]
                if len(date_part) == 8 and date_part.isdigit() and date_part < cutoff_str:
                    click.echo(f"  Would delete: {f.name}")
        return

    deleted = logger.rotate_logs()
    click.echo(f"Deleted {deleted} old log file(s).")


# =============================================================================
# Dashboard (Real-time Visualization)
# =============================================================================


@cli.group("dashboard")
@click.pass_context
def dashboard_group(ctx: click.Context) -> None:
    """Real-time telemetry dashboard and trace replay."""
    pass


@dashboard_group.command("live")
@click.option("--refresh", type=float, default=2.0, help="Refresh interval in seconds")
@click.pass_context
def dashboard_live(ctx: click.Context, refresh: float) -> None:
    """Run live dashboard (reads from telemetry logs)."""
    from .dashboard import run_live_dashboard, RICH_AVAILABLE

    if not RICH_AVAILABLE:
        click.echo("Error: Rich library required. Install with: pip install rich")
        raise SystemExit(1)

    gov_dir = ensure_initialized(ctx)
    log_dir = gov_dir / "logs"

    if not log_dir.exists():
        click.echo(f"Warning: No logs directory at {log_dir}")
        click.echo("Enable telemetry first: governor telemetry enable")

    run_live_dashboard(log_dir, refresh_interval=refresh)


@dashboard_group.command("replay")
@click.argument("trace_path", type=click.Path(exists=True))
@click.option("--speed", type=float, default=1.0, help="Playback speed multiplier")
def dashboard_replay(trace_path: str, speed: float) -> None:
    """Replay a trace file through the dashboard."""
    from .dashboard import run_replay, RICH_AVAILABLE

    if not RICH_AVAILABLE:
        click.echo("Error: Rich library required. Install with: pip install rich")
        raise SystemExit(1)

    run_replay(Path(trace_path), speed=speed)


@dashboard_group.command("demo")
@click.option("--speed", type=float, default=1.0, help="Playback speed multiplier")
def dashboard_demo(speed: float) -> None:
    """Generate and play a demo trace."""
    from .dashboard import generate_demo_trace, run_replay, RICH_AVAILABLE

    if not RICH_AVAILABLE:
        click.echo("Error: Rich library required. Install with: pip install rich")
        raise SystemExit(1)

    trace_path = generate_demo_trace(Path("demo_trace.jsonl"))
    run_replay(trace_path, speed=speed)


@dashboard_group.command("stats")
@click.argument("trace_path", type=click.Path(exists=True))
def dashboard_stats(trace_path: str) -> None:
    """Print statistics about a trace file."""
    from .dashboard import print_trace_stats

    print_trace_stats(Path(trace_path))


# =============================================================================
# Prometheus Metrics
# =============================================================================


@cli.group("prometheus")
@click.pass_context
def prometheus_group(ctx: click.Context) -> None:
    """Prometheus metrics export for monitoring."""
    pass


@prometheus_group.command("enable")
@click.option("--port", type=int, default=9090, help="Port for /metrics endpoint")
@click.pass_context
def prometheus_enable(ctx: click.Context, port: int) -> None:
    """Enable Prometheus metrics and start server."""
    from .prometheus import (
        PROMETHEUS_AVAILABLE,
        PrometheusConfig,
        get_metrics,
        get_server,
    )

    if not PROMETHEUS_AVAILABLE:
        click.echo("Error: prometheus_client library not installed.")
        click.echo("Install with: pip install prometheus-client")
        raise SystemExit(1)

    gov_dir = ensure_initialized(ctx)

    config = PrometheusConfig(enabled=True, port=port)
    config.save(gov_dir)

    metrics = get_metrics()
    server = get_server(config)

    if server.start():
        click.echo("Prometheus metrics enabled")
        click.echo(f"  Endpoint: http://localhost:{port}/metrics")
        click.echo(f"  Config saved to: {gov_dir / 'prometheus.json'}")
    else:
        click.echo("Failed to start metrics server")
        raise SystemExit(1)


@prometheus_group.command("disable")
@click.pass_context
def prometheus_disable(ctx: click.Context) -> None:
    """Disable Prometheus metrics server."""
    from .prometheus import PrometheusConfig, get_server

    gov_dir = ensure_initialized(ctx)

    config = PrometheusConfig.load(gov_dir)
    config.enabled = False
    config.save(gov_dir)

    server = get_server()
    server.stop()

    click.echo("Prometheus metrics disabled")


@prometheus_group.command("status")
@click.pass_context
def prometheus_status(ctx: click.Context) -> None:
    """Show Prometheus configuration and status."""
    from .prometheus import PROMETHEUS_AVAILABLE, PrometheusConfig, get_server

    gov_dir = ensure_initialized(ctx)
    config = PrometheusConfig.load(gov_dir)

    click.echo("Prometheus Metrics Status")
    click.echo(f"  Library installed: {PROMETHEUS_AVAILABLE}")
    click.echo(f"  Enabled: {config.enabled}")
    click.echo(f"  Port: {config.port}")
    click.echo(f"  Host: {config.host}")

    if PROMETHEUS_AVAILABLE and config.enabled:
        server = get_server(config)
        click.echo(f"  Server running: {server.running}")
        if server.running:
            click.echo(f"  Endpoint: http://{config.host}:{config.port}/metrics")


@prometheus_group.command("metrics")
@click.pass_context
def prometheus_metrics(ctx: click.Context) -> None:
    """Show current metrics in Prometheus text format."""
    from .prometheus import PROMETHEUS_AVAILABLE, get_server, PrometheusConfig

    if not PROMETHEUS_AVAILABLE:
        click.echo("# prometheus_client not installed")
        return

    gov_dir = ensure_initialized(ctx)
    config = PrometheusConfig.load(gov_dir)
    server = get_server(config)

    click.echo(server.get_metrics_text())


# =============================================================================
# Continuity Enforcement
# =============================================================================


@cli.group("continuity")
@click.pass_context
def continuity_group(ctx: click.Context) -> None:
    """
    Continuity enforcement: closed-loop generation control.

    Anchors define semantic constraints (setpoints). Checker measures
    deviation. Correction ladder applies escalating interventions.
    """
    pass


@continuity_group.command("status")
@click.pass_context
def continuity_status(ctx: click.Context) -> None:
    """Show continuity registry status and anchor counts by type."""
    from .continuity import AnchorRegistry, AnchorType, create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    click.echo("Continuity Enforcement Status")
    click.echo(f"  Total anchors: {len(registry)}")
    for atype in AnchorType:
        anchors = registry.get_by_type(atype)
        if anchors:
            click.echo(f"  {atype.value}: {len(anchors)}")

    if len(registry) == 0:
        click.echo("  (no anchors registered)")


@continuity_group.group("anchor")
def continuity_anchor() -> None:
    """Manage continuity anchors."""
    pass


@continuity_anchor.command("add")
@click.option("--id", "anchor_id", required=True, help="Anchor identifier")
@click.option(
    "--type", "anchor_type",
    type=click.Choice(["definition", "canon", "style", "prohibition", "requirement", "persona"]),
    required=True,
    help="Anchor type",
)
@click.option("--description", "-d", required=True, help="Anchor description")
@click.option("--required", "-r", multiple=True, help="Required pattern (repeatable)")
@click.option("--forbidden", "-f", multiple=True, help="Forbidden pattern (repeatable)")
@click.option(
    "--severity", "-s",
    type=click.Choice(["warn", "correct", "reject"]),
    default="correct",
    help="Violation severity",
)
@click.option(
    "--class", "constraint_class",
    type=click.Choice(["invariant", "preference"]),
    default="preference",
    help="Constraint class: invariant (cannot be disabled by profile) or preference (profile controls)",
)
@click.pass_context
def continuity_anchor_add(
    ctx: click.Context,
    anchor_id: str,
    anchor_type: str,
    description: str,
    required: tuple[str, ...],
    forbidden: tuple[str, ...],
    severity: str,
    constraint_class: str,
) -> None:
    """Add a continuity anchor."""
    from .continuity import Anchor, AnchorType, Severity, ConstraintClass, create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    anchor = Anchor(
        id=anchor_id,
        anchor_type=AnchorType(anchor_type),
        description=description,
        required_patterns=list(required),
        forbidden_patterns=list(forbidden),
        severity=Severity(severity),
        constraint_class=ConstraintClass(constraint_class),
    )
    registry.register(anchor)

    path = gov_dir / "continuity" / "anchors.json"
    registry.save(path)
    click.echo(f"Registered anchor: {anchor_id} ({anchor_type}, {severity}, {constraint_class})")


@continuity_anchor.command("list")
@click.pass_context
def continuity_anchor_list(ctx: click.Context) -> None:
    """List all continuity anchors."""
    from .continuity import create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    anchors = registry.all()
    if not anchors:
        click.echo("No anchors registered.")
        return

    for a in anchors:
        class_marker = "[I]" if a.constraint_class.value == "invariant" else "[P]"
        click.echo(f"  {a.id} {class_marker} [{a.anchor_type.value}] ({a.severity.value}): {a.description}")


@continuity_anchor.command("show")
@click.argument("anchor_id")
@click.pass_context
def continuity_anchor_show(ctx: click.Context, anchor_id: str) -> None:
    """Show full details of a continuity anchor."""
    from .continuity import create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    anchor = registry.get(anchor_id)
    if anchor is None:
        click.echo(f"Anchor not found: {anchor_id}", err=True)
        ctx.exit(1)
        return

    click.echo(json.dumps(anchor.to_dict(), indent=2))


@continuity_anchor.command("remove")
@click.argument("anchor_id")
@click.pass_context
def continuity_anchor_remove(ctx: click.Context, anchor_id: str) -> None:
    """Remove a continuity anchor."""
    from .continuity import create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    removed = registry.unregister(anchor_id)
    if removed is None:
        click.echo(f"Anchor not found: {anchor_id}", err=True)
        ctx.exit(1)
        return

    path = gov_dir / "continuity" / "anchors.json"
    registry.save(path)
    click.echo(f"Removed anchor: {anchor_id}")


@continuity_anchor.command("upgrade")
@click.argument("anchor_id")
@click.option(
    "--class", "constraint_class",
    type=click.Choice(["invariant", "preference"]),
    required=True,
    help="New constraint class",
)
@click.pass_context
def continuity_anchor_upgrade(ctx: click.Context, anchor_id: str, constraint_class: str) -> None:
    """Upgrade anchor constraint class."""
    from .continuity import ConstraintClass, create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    anchor = registry.get(anchor_id)
    if anchor is None:
        click.echo(f"Anchor not found: {anchor_id}", err=True)
        ctx.exit(1)
        return

    old_class = anchor.constraint_class.value
    anchor.constraint_class = ConstraintClass(constraint_class)
    registry.register(anchor)  # Re-register to update

    path = gov_dir / "continuity" / "anchors.json"
    registry.save(path)
    click.echo(f"Upgraded anchor {anchor_id}: {old_class} -> {constraint_class}")


@continuity_group.command("check")
@click.argument("text")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def continuity_check(ctx: click.Context, text: str, as_json: bool) -> None:
    """Check text against all registered anchors."""
    from .continuity import ContinuityChecker, create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    anchors = registry.all()
    if not anchors:
        click.echo("No anchors registered.")
        return

    checker = ContinuityChecker()
    report = checker.check(text, anchors)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        click.echo(report.summary())
        if report.violations:
            for v in report.violations:
                click.echo(f"  {v}")


@continuity_group.command("import")
@click.argument("path", type=click.Path(exists=True))
@click.pass_context
def continuity_import(ctx: click.Context, path: str) -> None:
    """Import anchors from a JSON file."""
    from .continuity import AnchorRegistry, create_registry

    gov_dir = ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    import_data = json.loads(Path(path).read_text())
    imported = AnchorRegistry.from_dict(import_data)

    for anchor in imported.all():
        registry.register(anchor)

    save_path = gov_dir / "continuity" / "anchors.json"
    registry.save(save_path)
    click.echo(f"Imported {len(imported)} anchor(s).")


# =============================================================================
# Maude Lite (Evidence-Gated Coding Harness)
# =============================================================================


@cli.group("gate")
@click.pass_context
def gate_cmd(ctx):
    """Evidence Gate — evidence-gated coding harness.

    Kernel-only surface: claims need evidence, contradictions persist, failures are loud.

    \b
    Examples:
        governor gate check "text"
        governor gate score "text"
    """
    pass


@gate_cmd.command("check")
@click.argument("text", required=False)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option("--file", "-f", type=click.Path(exists=True), help="Read content from file")
@click.option("--task", "-t", default="", help="Task description for context")
@click.option("--strict/--permissive", default=True, help="Strict mode (fail-closed) or permissive (warn only)")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def lite_check(ctx, text, use_stdin, file, task, strict, fmt):
    """Check agent output against kernel constraints.

    \b
    Examples:
        governor lite check "This improves performance by 10x"
        maude lite check --stdin < output.txt
        maude lite check --file output.txt --format json
    """
    from .evidence_gate import MaudeLite, MaudeLiteConfig

    # Get content to check
    if use_stdin:
        content = click.get_text_stream("stdin").read()
    elif file:
        content = Path(file).read_text()
    elif text:
        content = text
    else:
        click.echo("Error: Provide text, --stdin, or --file.", err=True)
        ctx.exit(1)
        return

    config = MaudeLiteConfig(strict=strict)
    lite = MaudeLite(config=config)
    result = lite.check(task=task, context="", output=content)

    if fmt == "json":
        click.echo(result.to_json())
    else:
        click.echo(lite.format_status(result))


@gate_cmd.command("validate")
@click.argument("path", type=click.Path(exists=True))
@click.option("--task", "-t", default="validate file", help="Task description")
@click.option("--strict/--permissive", default=True, help="Strict mode or permissive")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def maude_lite_validate(ctx, path, task, strict, fmt):
    """Validate a file's contents against kernel constraints."""
    from .evidence_gate import MaudeLite, MaudeLiteConfig

    content = Path(path).read_text()
    config = MaudeLiteConfig(strict=strict)
    lite = MaudeLite(config=config)
    result = lite.check(task=task, context=str(path), output=content)

    if fmt == "json":
        click.echo(result.to_json())
    else:
        click.echo(f"File: {path}")
        click.echo(lite.format_status(result))
        if result.claims:
            click.echo(f"\nClaims extracted: {len(result.claims)}")
            for claim in result.claims[:5]:  # Show first 5
                level = claim.level.value
                evidence = "✓" if claim.evidence else "✗"
                click.echo(f"  [{level}] {claim.text[:50]}... (evidence: {evidence})")
            if len(result.claims) > 5:
                click.echo(f"  ... and {len(result.claims) - 5} more")


@gate_cmd.command("config")
@click.pass_context
def maude_lite_config(ctx):
    """Show Maude Lite configuration."""
    from .evidence_gate import MaudeLiteConfig, CUSTODY_THRESHOLD

    config = MaudeLiteConfig()

    click.echo("Maude Lite Configuration")
    click.echo("========================")
    click.echo(f"Mode: {'strict' if config.strict else 'permissive'}")
    click.echo(f"Custody threshold: {config.custody_threshold}")
    click.echo(f"Evidence required for HARD claims: {config.evidence_required_for_hard}")
    click.echo(f"Contradiction action: {config.contradiction_action}")
    click.echo("\nKernel constraints (non-negotiable):")
    for constraint in config._kernel_constraints:
        click.echo(f"  - {constraint}")
    click.echo("\nDisabled features (surface):")
    for feature in ["puppet_mode", "persona", "tone_modulation", "regime_detection", "ticketing", "journal"]:
        click.echo(f"  - {feature}")


@gate_cmd.command("score")
@click.argument("text", required=False)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option("--file", "-f", type=click.Path(exists=True), help="Read content from file")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def maude_lite_score(ctx, text, use_stdin, file, fmt):
    """Score custody metrics (Ap, Ip, Fp) for content."""
    from .evidence_gate import score_custody

    # Get content to check
    if use_stdin:
        content = click.get_text_stream("stdin").read()
    elif file:
        content = Path(file).read_text()
    elif text:
        content = text
    else:
        click.echo("Error: Provide text, --stdin, or --file.", err=True)
        ctx.exit(1)
        return

    custody = score_custody(content)

    if fmt == "json":
        click.echo(json.dumps(custody.to_dict(), indent=2))
    else:
        click.echo("Custody Score")
        click.echo("=============")
        click.echo(f"Accountability (Ap): {custody.ap:.2f}")
        click.echo(f"Invariant coupling (Ip): {custody.ip:.2f}")
        click.echo(f"Failure explicitness (Fp): {custody.fp:.2f}")
        click.echo(f"Total: {custody.total:.2f}")
        click.echo(f"Status: {'PASS' if custody.passed else 'FAIL'}")
        if not custody.passed:
            click.echo("\nIssues:")
            for reason in custody.blocking_reasons:
                click.echo(f"  - {reason}")


@gate_cmd.command("extract")
@click.argument("text", required=False)
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin")
@click.option("--file", "-f", type=click.Path(exists=True), help="Read content from file")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.pass_context
def maude_lite_extract(ctx, text, use_stdin, file, fmt):
    """Extract claims from content."""
    from .evidence_gate import extract_claims, check_evidence, link_evidence_to_claims

    # Get content to check
    if use_stdin:
        content = click.get_text_stream("stdin").read()
    elif file:
        content = Path(file).read_text()
    elif text:
        content = text
    else:
        click.echo("Error: Provide text, --stdin, or --file.", err=True)
        ctx.exit(1)
        return

    claims = extract_claims(content)
    evidence = check_evidence(content)
    claims = link_evidence_to_claims(claims, evidence, content)

    if fmt == "json":
        click.echo(json.dumps({
            "claims": [c.to_dict() for c in claims],
            "evidence_indicators": evidence,
        }, indent=2))
    else:
        click.echo(f"Claims extracted: {len(claims)}")
        click.echo(f"Evidence indicators: {len(evidence)}")
        if evidence:
            click.echo(f"  {', '.join(evidence[:3])}{'...' if len(evidence) > 3 else ''}")
        click.echo()
        for claim in claims:
            level = claim.level.value
            evidence_status = f"✓ {claim.evidence}" if claim.evidence else "✗ no evidence"
            click.echo(f"[{level}] \"{claim.text}\"")
            click.echo(f"       ID: {claim.id}, Evidence: {evidence_status}")


@gate_cmd.command("pending")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def maude_lite_pending(ctx, fmt):
    """Show pending violation requiring resolution."""
    from .violation_resolver import ViolationResolver, format_violation_prompt

    gov_dir = ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)
    pending = resolver.get_pending()

    if not pending:
        if fmt == "json":
            click.echo(json.dumps({"pending": None}))
        else:
            click.echo("No pending violation.")
        return

    if fmt == "json":
        click.echo(json.dumps({"pending": pending.to_dict()}, indent=2))
    else:
        click.echo(format_violation_prompt(pending.violations, pending.mode))


@gate_cmd.command("fix")
@click.pass_context
def maude_lite_fix(ctx):
    """Resolve pending violation by fixing the response.

    Regenerates the blocked response to comply with violated constraints.
    This command requires an LLM backend (use --backend or environment vars).
    """
    from .violation_resolver import ViolationResolver, ResolutionAction

    gov_dir = ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)
    pending = resolver.get_pending()

    if not pending:
        click.echo("No pending violation to resolve.")
        return

    # For CLI, we can't easily call async backend — note this limitation
    click.echo("[Governor] Fix action requires the web API with an LLM backend.")
    click.echo("Use the web UI or reply '1' / 'gate fix' in chat.")
    click.echo()
    click.echo("Pending violation:")
    for v in pending.violations:
        desc = v.get("description", str(v))
        click.echo(f"  - {desc}")


@gate_cmd.command("revise")
@click.pass_context
def maude_lite_revise(ctx):
    """Resolve pending violation by updating the anchor.

    Updates the constraint/anchor that caused the violation, making the
    original response now permitted.
    """
    from .violation_resolver import ViolationResolver

    gov_dir = ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)
    pending = resolver.get_pending()

    if not pending:
        click.echo("No pending violation to resolve.")
        return

    result = resolver.resolve_revise(pending)

    if result.success:
        click.echo(f"[Governor] {result.message}")
        if result.anchor_update:
            for anchor_id in result.anchor_update.get("revised_anchors", []):
                click.echo(f"  Updated: {anchor_id}")
    else:
        click.echo(f"[Governor] Revision failed: {result.message}", err=True)


@gate_cmd.command("proceed")
@click.option("--scope", type=click.Choice(["single_instance", "session", "project"]), default="single_instance", help="Exception scope")
@click.option("--expiry", default=None, help="Exception expiry (ISO timestamp, or omit for permanent)")
@click.pass_context
def maude_lite_proceed(ctx, scope, expiry):
    """Resolve pending violation by logging an exception.

    Records the violation as an intentional deviation with specified scope
    and optional expiry.
    """
    from .violation_resolver import ViolationResolver

    gov_dir = ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)
    pending = resolver.get_pending()

    if not pending:
        click.echo("No pending violation to resolve.")
        return

    result = resolver.resolve_proceed(pending, scope=scope, expiry=expiry)

    if result.success:
        click.echo(f"[Governor] {result.message}")
        click.echo(f"  Scope: {scope}")
        if expiry:
            click.echo(f"  Expiry: {expiry}")
    else:
        click.echo(f"[Governor] Exception logging failed: {result.message}", err=True)


@gate_cmd.command("exceptions")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text")
@click.pass_context
def maude_lite_exceptions(ctx, fmt):
    """List logged exceptions (violations proceeded past)."""
    from .violation_resolver import ViolationResolver

    gov_dir = ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)
    exceptions = resolver.list_exceptions()

    if fmt == "json":
        click.echo(json.dumps([e.to_dict() for e in exceptions], indent=2))
    else:
        if not exceptions:
            click.echo("No exceptions logged.")
            return

        click.echo(f"Exceptions: {len(exceptions)}")
        click.echo()
        for exc in exceptions:
            click.echo(f"  {exc.id} [{exc.scope}]")
            click.echo(f"    Created: {exc.created_at}")
            click.echo(f"    Mode: {exc.mode}")
            if exc.expiry:
                click.echo(f"    Expiry: {exc.expiry}")
            for v in exc.violations[:2]:
                desc = v.get("description", str(v))[:60]
                click.echo(f"    - {desc}...")
            if len(exc.violations) > 2:
                click.echo(f"    ... and {len(exc.violations) - 2} more violations")
            click.echo()


# =============================================================================
# Docket Commands (Adjudicator UX)
# =============================================================================


@cli.group()
@click.pass_context
def docket(ctx: click.Context) -> None:
    """View and manage pending cases on the docket."""
    pass


@docket.command("list")
@click.option("--style", type=click.Choice(["full", "compact", "legacy"]), default="full", help="Display style")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def docket_list(ctx: click.Context, style: str, json_output: bool) -> None:
    """List all pending cases on the docket."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector, StalenessConfig
    from .epistemic import EpistemicLedger

    # Create components
    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    cases = docket_mgr.get_docket()

    if json_output:
        click.echo(json.dumps([c.to_dict() for c in cases], indent=2))
        return

    if not cases:
        click.echo("No pending cases on the docket.")
        return

    click.echo(f"DOCKET: {len(cases)} pending case(s)")
    click.echo("=" * 50)
    for case in cases:
        click.echo()
        click.echo(docket_mgr.format_case(case, style=style))


@docket.command("show")
@click.argument("case_number", type=int)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def docket_show(ctx: click.Context, case_number: int, json_output: bool) -> None:
    """Show details of a specific case."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    case = docket_mgr.get_case(case_number)
    if case is None:
        click.echo(f"Case #{case_number} not found.", err=True)
        ctx.exit(1)
        return

    if json_output:
        click.echo(json.dumps(case.to_dict(), indent=2))
    else:
        click.echo(docket_mgr.format_case(case, style="full"))


# =============================================================================
# Rule Commands (Issue Rulings)
# =============================================================================


@cli.group()
@click.pass_context
def rule(ctx: click.Context) -> None:
    """Issue rulings on docket cases."""
    pass


@rule.command("sustain")
@click.argument("case_number", type=int)
@click.option("--rationale", "-r", default="", help="Rationale for ruling")
@click.pass_context
def rule_sustain(ctx: click.Context, case_number: int, rationale: str) -> None:
    """Sustain the constraint - regenerate compliant output."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager, CaseType
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    try:
        precedent = docket_mgr.rule_sustain(case_number, rationale)
        click.echo(f"[Ruling] Case #{case_number}: SUSTAINED")
        click.echo(f"  Precedent logged: {precedent.id}")
        click.echo("  Constraint upheld. Regeneration required.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@rule.command("amend")
@click.argument("case_number", type=int)
@click.option("--rationale", "-r", default="", help="Rationale for ruling")
@click.pass_context
def rule_amend(ctx: click.Context, case_number: int, rationale: str) -> None:
    """Amend the anchor to permit the output."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    try:
        precedent = docket_mgr.rule_amend(case_number, rationale)
        click.echo(f"[Ruling] Case #{case_number}: AMENDED")
        click.echo(f"  Precedent logged: {precedent.id}")
        click.echo("  Anchor updated. Output now permitted.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@rule.command("except")
@click.argument("case_number", type=int)
@click.option("--scope", type=click.Choice(["single_instance", "session", "project"]), default="single_instance", help="Exception scope")
@click.option("--rationale", "-r", default="", help="Rationale for ruling")
@click.pass_context
def rule_except(ctx: click.Context, case_number: int, scope: str, rationale: str) -> None:
    """Grant exception - log as precedent."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    try:
        precedent = docket_mgr.rule_grant_exception(case_number, scope, rationale)
        click.echo(f"[Ruling] Case #{case_number}: EXCEPTION GRANTED")
        click.echo(f"  Precedent logged: {precedent.id}")
        click.echo(f"  Scope: {scope}")
        click.echo("  Output permitted as intentional deviation.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@rule.command("reverify")
@click.argument("case_number", type=int)
@click.option("--rationale", "-r", default="", help="Rationale for ruling")
@click.pass_context
def rule_reverify(ctx: click.Context, case_number: int, rationale: str) -> None:
    """Re-run verification on a stale claim."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    try:
        precedent = docket_mgr.rule_reverify(case_number, rationale)
        click.echo(f"[Ruling] Case #{case_number}: REVERIFY")
        click.echo(f"  Precedent logged: {precedent.id}")
        click.echo("  Claim scheduled for reverification.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


@rule.command("dismiss")
@click.argument("case_number", type=int)
@click.option("--rationale", "-r", default="", help="Rationale for ruling")
@click.pass_context
def rule_dismiss(ctx: click.Context, case_number: int, rationale: str) -> None:
    """Dismiss a stale claim - accept current state."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    try:
        precedent = docket_mgr.rule_dismiss(case_number, rationale)
        click.echo(f"[Ruling] Case #{case_number}: DISMISSED")
        click.echo(f"  Precedent logged: {precedent.id}")
        click.echo("  Stale claim accepted as-is.")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)


# =============================================================================
# Precedent Commands (View Past Rulings)
# =============================================================================


@cli.group()
@click.pass_context
def precedent(ctx: click.Context) -> None:
    """View past rulings (precedent record)."""
    pass


@precedent.command("list")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def precedent_list(ctx: click.Context, json_output: bool) -> None:
    """List all precedents."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    precedents = docket_mgr.get_precedents()

    if json_output:
        click.echo(json.dumps([p.to_dict() for p in precedents], indent=2))
        return

    if not precedents:
        click.echo("No precedents recorded.")
        return

    click.echo(f"PRECEDENT RECORD: {len(precedents)} ruling(s)")
    click.echo("=" * 50)
    for p in precedents:
        click.echo()
        click.echo(f"[{p.id}] Case #{p.case_number}")
        click.echo(f"  Ruling: {p.ruling.value.upper()}")
        click.echo(f"  Claim: {p.claim_id}")
        if p.anchor_id:
            click.echo(f"  Anchor: {p.anchor_id}")
        click.echo(f"  Scope: {p.scope}")
        if p.rationale:
            click.echo(f"  Rationale: {p.rationale}")
        click.echo(f"  Date: {p.created_at.isoformat()}")


@precedent.command("search")
@click.argument("query")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def precedent_search(ctx: click.Context, query: str, json_output: bool) -> None:
    """Search precedents by query string."""
    gov_dir = ensure_initialized(ctx)

    from .docket import create_docket_manager
    from .staleness import create_staleness_detector
    from .epistemic import EpistemicLedger

    ledger = EpistemicLedger()
    staleness = create_staleness_detector(ledger)
    docket_mgr = create_docket_manager(staleness=staleness, governor_dir=gov_dir)

    results = docket_mgr.search_precedents(query)

    if json_output:
        click.echo(json.dumps([p.to_dict() for p in results], indent=2))
        return

    if not results:
        click.echo(f"No precedents matching '{query}'.")
        return

    click.echo(f"Search results for '{query}': {len(results)} match(es)")
    click.echo("=" * 50)
    for p in results:
        click.echo()
        click.echo(f"[{p.id}] Case #{p.case_number} - {p.ruling.value.upper()}")
        click.echo(f"  {p.rationale or '(no rationale)'}")


# =============================================================================
# Claim Commands (View Claim Details)
# =============================================================================


@cli.group("claim")
@click.pass_context
def claim_cmd(ctx: click.Context) -> None:
    """View claim details and status."""
    pass


@claim_cmd.command("show")
@click.argument("claim_id")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def claim_show(ctx: click.Context, claim_id: str, json_output: bool) -> None:
    """Show detailed claim status."""
    gov_dir = ensure_initialized(ctx)

    from .epistemic import EpistemicLedger
    from .claim_status import create_claim_status_dashboard

    ledger = EpistemicLedger()
    dashboard = create_claim_status_dashboard(ledger)

    detail = dashboard.get_detail(claim_id)
    if detail is None:
        click.echo(f"Claim not found: {claim_id}", err=True)
        ctx.exit(1)
        return

    if json_output:
        click.echo(json.dumps(detail.to_dict(), indent=2))
    else:
        click.echo(dashboard.format_detail(detail))


# =============================================================================
# Unified Check Command (VS Code extension integration)
# =============================================================================


@cli.command("check")
@click.argument("path", required=False, type=click.Path())
@click.option("--stdin", "use_stdin", is_flag=True, help="Read content from stdin (JSON or plain text)")
@click.option("--format", "fmt", type=click.Choice(["text", "json"]), default="text", help="Output format")
@click.option("--no-security", "skip_security", is_flag=True, help="Skip security scanning")
@click.option("--no-continuity", "skip_continuity", is_flag=True, help="Skip continuity checking")
@click.option("--interactive", "-i", is_flag=True, help="Interactive mode: offer fix/revise/proceed on errors")
@click.option("--mode", "check_mode", type=click.Choice(["code", "fiction", "nonfiction"]), default="code", help="Context mode for interactive resolution")
@click.pass_context
def check(ctx: click.Context, path: str | None, use_stdin: bool, fmt: str, skip_security: bool, skip_continuity: bool, interactive: bool, check_mode: str) -> None:
    """Check a file for security and continuity issues.

    Aggregates findings from security scanning and continuity checking into
    a unified format suitable for editor diagnostics.

    With --interactive, blocking errors (REJECT severity) trigger the violation
    resolution flow, presenting fix/revise/proceed options.

    \b
    Examples:
        governor check src/main.py --format json
        echo '{"content":"...","filepath":"f.py"}' | governor check --stdin --format json
        governor check src/main.py --no-continuity
        governor check response.txt --interactive --mode fiction
    """
    from .check import run_check

    # Determine content and filepath
    if use_stdin:
        raw = click.get_text_stream("stdin").read()
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict) and "content" in payload:
                content = payload["content"]
                file_path = payload.get("filepath", "<stdin>")
            else:
                content = raw
                file_path = "<stdin>"
        except (json.JSONDecodeError, ValueError):
            content = raw
            file_path = "<stdin>"
    elif path is not None:
        p = Path(path)
        if not p.exists():
            click.echo(f"Error: File not found: {path}", err=True)
            ctx.exit(1)
            return
        content = p.read_text()
        file_path = str(p)
    else:
        click.echo("Error: Provide a file path or use --stdin.", err=True)
        ctx.exit(1)
        return

    # Resolve governor dir (may not exist — that's OK)
    gov_dir = get_governor_dir(ctx)
    if not gov_dir.exists():
        gov_dir_resolved = None
    else:
        gov_dir_resolved = gov_dir

    result = run_check(
        content,
        file_path,
        run_security=not skip_security,
        run_continuity=not skip_continuity,
        governor_dir=gov_dir_resolved,
    )

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        # Human-readable output
        if result.status == "pass":
            click.echo(f"✓ {result.summary}")
        else:
            status_sym = "✗" if result.status == "error" else "⚠"
            click.echo(f"{status_sym} {result.summary}")
            for f in result.findings:
                sev_color = {"error": "red", "warning": "yellow", "info": "blue"}.get(f.severity, "white")
                loc = f"{file_path}:{f.range.start.line + 1}:{f.range.start.character + 1}"
                click.echo(click.style(f"  [{f.severity.upper()}]", fg=sev_color) + f" {loc} {f.code}: {f.message}")
                if f.suggestion:
                    click.echo(f"    → {f.suggestion}")

    # Interactive mode: offer resolution for blocking errors
    if interactive and result.status == "error" and gov_dir_resolved:
        _handle_interactive_check_resolution(ctx, result, content, file_path, gov_dir_resolved, check_mode)


def _handle_interactive_check_resolution(
    ctx: click.Context,
    result: "CheckResult",  # type: ignore[name-defined]
    content: str,
    file_path: str,
    gov_dir: Path,
    mode: str,
) -> None:
    """Handle interactive resolution for check command errors."""
    from .violation_resolver import (
        ViolationResolver,
        ResolutionAction,
        format_violation_prompt,
        get_mode_choices,
    )

    # Filter to error-severity findings (REJECT)
    blocking_findings = [f for f in result.findings if f.severity == "error"]
    if not blocking_findings:
        return

    # Convert findings to violation-like dicts for the resolver
    violations = []
    for f in blocking_findings:
        violations.append({
            "anchor_id": f.code,
            "description": f.message,
            "severity": "reject",
            "evidence": [f.suggestion] if f.suggestion else [],
        })

    # Create resolver and pending violation
    resolver = ViolationResolver(gov_dir, mode=mode, context_id="cli_check")
    run_id = f"check_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    pending = resolver.create_pending(violations, content, run_id)

    click.echo()
    click.echo(format_violation_prompt(violations, mode))
    click.echo()

    # Interactive resolution loop
    while True:
        try:
            user_input = click.prompt("Choice", default="", show_default=False)
        except click.exceptions.Abort:
            click.echo("\nAborted. Pending violation saved.")
            click.echo("Resume with: governor lite pending")
            ctx.exit(1)
            return

        action = resolver.is_resolution_command(user_input)
        if action is None:
            click.echo()
            click.echo("Invalid choice. Please enter 1, 2, 3 or: fix | revise | proceed")
            click.echo()
            for choice in get_mode_choices(mode):
                click.echo(f"  {choice}")
            click.echo()
            continue

        # Execute resolution
        if action == ResolutionAction.FIX:
            click.echo()
            click.echo("[Governor] Fix requires a chat backend. Use:")
            click.echo("  - WebUI for interactive fix")
            click.echo("  - governor lite fix (with backend configured)")
            click.echo()
            click.echo("Alternatively, manually edit the content and re-run check.")
            resolver.clear_pending()
            ctx.exit(1)
            return

        elif action == ResolutionAction.REVISE:
            result_obj = resolver.resolve_revise(pending)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            if result_obj.anchor_update:
                for anchor_id in result_obj.anchor_update.get("revised_anchors", []):
                    click.echo(f"  - Revised: {anchor_id}")
            click.echo()
            click.echo("Re-run check to verify.")
            return

        elif action == ResolutionAction.PROCEED:
            scope = click.prompt("Exception scope", default="single_instance",
                               type=click.Choice(["single_instance", "session", "project"]))
            result_obj = resolver.resolve_proceed(pending, scope=scope)
            click.echo()
            click.echo(f"[Governor] {result_obj.message}")
            click.echo(f"  Exception ID: {result_obj.exception_id}")
            return


# =============================================================================
# Friendly CLI Commands (layered by persona)
# =============================================================================
# Intent Management (Code Autopilot)
# =============================================================================


@cli.group("intent")
def intent_group() -> None:
    """Manage session intent (Code Autopilot).

    Intent controls how Governor behaves for this session.
    Set a profile, scope, timebox, and reason.

    \b
    Examples:
      governor intent show                  # Show resolved intent
      governor intent set --profile hotfix --scope "src/**" --timebox 90
      governor intent clear                 # Clear session intent
    """
    pass


@intent_group.command("show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def intent_show(ctx: click.Context, as_json: bool) -> None:
    """Show resolved intent with provenance."""
    from .intent import resolve_intent, format_provenance

    gov_dir = ensure_initialized(ctx)
    intent, provenance = resolve_intent(gov_dir)

    if as_json:
        output = {
            "intent": intent.to_dict(),
            "provenance": [p.to_dict() for p in provenance],
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo()
        click.echo(f"  Intent: {intent.to_status_string()}")
        if intent.reason:
            click.echo(f"  Reason: {intent.reason}")
        click.echo(f"  Source: {intent.source}")
        click.echo()
        click.echo(format_provenance(provenance))
        click.echo()


@intent_group.command("set")
@click.option("--profile", "-p", required=True, help="Profile name (greenfield/established/production/hotfix/refactor)")
@click.option("--scope", "-s", multiple=True, help="Allowed path patterns (repeatable)")
@click.option("--deny", "-d", multiple=True, help="Denied path patterns (repeatable)")
@click.option("--timebox", "-t", type=int, help="Timebox in minutes")
@click.option("--because", "reason", help="Reason for this intent")
@click.pass_context
def intent_set(
    ctx: click.Context,
    profile: str,
    scope: tuple[str, ...],
    deny: tuple[str, ...],
    timebox: int | None,
    reason: str | None,
) -> None:
    """Set session intent."""
    from .intent import Intent, set_intent
    from .autopilot import get_autopilot_profile, apply_autopilot_profile

    gov_dir = ensure_initialized(ctx)

    # Validate profile exists
    profile_config = get_autopilot_profile(profile)
    if not profile_config:
        valid_profiles = ["greenfield", "established", "production", "hotfix", "refactor"]
        click.echo(f"Unknown profile: {profile}", err=True)
        click.echo(f"Valid profiles: {', '.join(valid_profiles)}", err=True)
        ctx.exit(1)
        return

    intent = Intent(
        profile=profile,
        scope=list(scope) if scope else None,
        deny=list(deny) if deny else None,
        timebox_minutes=timebox,
        reason=reason,
        source="cli",
    )

    set_intent(gov_dir, intent)

    # Apply the autopilot profile settings
    applied = apply_autopilot_profile(gov_dir, profile_config)

    click.echo()
    click.echo(f"  Intent set: {intent.to_status_string()}")
    if reason:
        click.echo(f"  Reason: {reason}")
    click.echo()
    click.echo("  Applied settings:")
    for key, value in applied.items():
        click.echo(f"    {key}: {value}")
    click.echo()


@intent_group.command("clear")
@click.pass_context
def intent_clear(ctx: click.Context) -> None:
    """Clear session intent."""
    from .intent import clear_intent

    gov_dir = ensure_initialized(ctx)
    cleared = clear_intent(gov_dir)

    if cleared:
        click.echo("Session intent cleared.")
    else:
        click.echo("No session intent was set.")


# =============================================================================
# Override Management (Code Autopilot)
# =============================================================================


@cli.group("override")
def override_group() -> None:
    """Manage constraint overrides (Code Autopilot).

    Create scoped, expiring exceptions to invariant constraints.
    Overrides allow emergency bypasses while maintaining audit trail.

    \b
    Examples:
      governor override create --anchor no-sql --because "legacy" --scope "migrations/**" --expires 2h
      governor override list
      governor override revoke <id> --because "fixed"
    """
    pass


@override_group.command("create")
@click.option("--anchor", "-a", required=True, help="Anchor ID to override")
@click.option("--because", "-b", required=True, help="Reason for override")
@click.option("--scope", "-s", multiple=True, required=True, help="Path patterns covered (repeatable)")
@click.option("--expires", "-e", required=True, help="Duration like '2h', '90m', '1d'")
@click.pass_context
def override_create(
    ctx: click.Context,
    anchor: str,
    because: str,
    scope: tuple[str, ...],
    expires: str,
) -> None:
    """Create scoped override for invariant constraint."""
    from .overrides import OverrideManager
    from .continuity import create_registry, ConstraintClass
    import os

    gov_dir = ensure_initialized(ctx)

    # Check that anchor exists and is invariant
    registry = create_registry(gov_dir)
    anchor_obj = registry.get(anchor)
    if anchor_obj is None:
        click.echo(f"Anchor not found: {anchor}", err=True)
        ctx.exit(1)
        return

    if anchor_obj.constraint_class != ConstraintClass.INVARIANT:
        click.echo(f"Anchor '{anchor}' is not an invariant. Use profile settings for preferences.", err=True)
        ctx.exit(1)
        return

    manager = OverrideManager(gov_dir=gov_dir)
    operator = os.environ.get("USER", os.environ.get("USERNAME", "unknown"))

    receipt = manager.create(
        anchor_id=anchor,
        reason=because,
        operator=operator,
        scope=list(scope),
        expires_duration=expires,
    )

    click.echo()
    click.echo(f"  Override created: {receipt.id}")
    click.echo(f"  Anchor: {anchor}")
    click.echo(f"  Scope: {', '.join(scope)}")
    click.echo(f"  Expires: {receipt.remaining_minutes} minutes")
    click.echo(f"  Reason: {because}")
    click.echo()


@override_group.command("list")
@click.option("--all", "show_all", is_flag=True, help="Include expired/revoked overrides")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def override_list(ctx: click.Context, show_all: bool, as_json: bool) -> None:
    """List active overrides."""
    from .overrides import OverrideManager

    gov_dir = ensure_initialized(ctx)
    manager = OverrideManager(gov_dir=gov_dir)

    overrides = manager.list_all() if show_all else manager.list_active()

    if as_json:
        click.echo(json.dumps([o.to_dict() for o in overrides], indent=2))
        return

    if not overrides:
        click.echo("No active overrides.")
        return

    click.echo()
    click.echo("  Active Overrides:")
    for o in overrides:
        click.echo(f"    {o.to_status_string()}")
        click.echo(f"      Reason: {o.reason}")
    click.echo()


@override_group.command("show")
@click.argument("override_id")
@click.pass_context
def override_show(ctx: click.Context, override_id: str) -> None:
    """Show override details."""
    from .overrides import OverrideManager

    gov_dir = ensure_initialized(ctx)
    manager = OverrideManager(gov_dir=gov_dir)

    override = manager.get(override_id)
    if override is None:
        click.echo(f"Override not found: {override_id}", err=True)
        ctx.exit(1)
        return

    click.echo(json.dumps(override.to_dict(), indent=2))


@override_group.command("revoke")
@click.argument("override_id")
@click.option("--because", "-b", required=True, help="Reason for revocation")
@click.pass_context
def override_revoke(ctx: click.Context, override_id: str, because: str) -> None:
    """Revoke an override early."""
    from .overrides import OverrideManager

    gov_dir = ensure_initialized(ctx)
    manager = OverrideManager(gov_dir=gov_dir)

    success = manager.revoke(override_id, because)
    if not success:
        click.echo(f"Override not found: {override_id}", err=True)
        ctx.exit(1)
        return

    click.echo(f"Override revoked: {override_id}")


@override_group.command("cleanup")
@click.pass_context
def override_cleanup(ctx: click.Context) -> None:
    """Remove expired override files."""
    from .overrides import OverrideManager

    gov_dir = ensure_initialized(ctx)
    manager = OverrideManager(gov_dir=gov_dir)

    count = manager.cleanup_expired()
    click.echo(f"Cleaned up {count} expired override(s).")


# =============================================================================
# Interferometry (multi-model claim comparison)
# =============================================================================


@cli.group("interferometry")
@click.pass_context
def interferometry_cmd(ctx: click.Context) -> None:
    """Interferometry — multi-model claim comparison (parallel + serial)."""
    pass


@interferometry_cmd.command("run")
@click.argument("prompt")
@click.option("--backends", "-b", required=True,
              help="Comma-separated backend:model pairs, e.g. ollama:llama3,anthropic:claude-3-haiku")
@click.option("--mode", "-m", type=click.Choice(["parallel", "serial"]), default="parallel",
              help="Execution mode: parallel (default) or serial deliberation chain.")
@click.option("--rounds", "-n", type=int, default=1,
              help="Number of deliberation rounds for serial mode (default: 1).")
@click.option("--threshold", "-t", type=float, default=0.65,
              help="Jaccard threshold for claim matching (default: 0.65).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def interferometry_run(ctx: click.Context, prompt: str, backends: str,
                       mode: str, rounds: int, threshold: float, as_json: bool) -> None:
    """Run interferometry on a prompt across multiple backends."""
    import asyncio
    from .interferometry import (
        InterferometryStore, RunMode, run_ensemble,
    )

    gov_dir = ensure_initialized(ctx)

    # Parse backend:model pairs
    backend_configs = []
    for pair in backends.split(","):
        pair = pair.strip()
        if ":" not in pair:
            click.echo(f"Error: invalid backend:model pair: {pair}", err=True)
            raise SystemExit(1)
        bt, model = pair.split(":", 1)
        config: dict = {"backend_type": bt, "model": model}
        # Add default kwargs based on type
        import os
        if bt == "anthropic":
            config["api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
        elif bt == "ollama":
            config["host"] = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
        elif bt == "claude-code":
            config["claude_path"] = os.environ.get("CLAUDE_PATH", "claude")
        elif bt == "codex":
            config["codex_path"] = os.environ.get("CODEX_PATH", "codex")
        backend_configs.append(config)

    run_mode = RunMode(mode)
    result = asyncio.run(run_ensemble(prompt, backend_configs, run_mode, rounds, threshold))

    # Save
    store = InterferometryStore(gov_dir)
    store.save(result)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Interferometry run {result.id} ({result.mode.value})")
        click.echo(f"  Models: {', '.join(r.model_id for r in result.runs)}")
        if result.mode == RunMode.SERIAL:
            click.echo(f"  Rounds: {result.rounds}")
        click.echo(f"  Shared claims:      {result.signals.shared_count}")
        click.echo(f"  Unique claims:      {result.signals.unique_count}")
        click.echo(f"  Conflicting claims: {result.signals.conflict_count}")
        click.echo(f"  Disagreement rate:  {result.signals.disagreement_rate:.1%}")
        if result.signals.specifics_conflict_count > 0:
            click.echo(f"  Specifics conflicts: {result.signals.specifics_conflict_count}")


@interferometry_cmd.command("results")
@click.option("--last", "show_last", is_flag=True, help="Show the most recent run.")
@click.option("--id", "run_id", default=None, help="Show a specific run by ID.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def interferometry_results(ctx: click.Context, show_last: bool, run_id: str | None, as_json: bool) -> None:
    """Show interferometry run results."""
    from .interferometry import InterferometryStore

    gov_dir = ensure_initialized(ctx)
    store = InterferometryStore(gov_dir)

    if run_id:
        run = store.load(run_id)
        if run is None:
            click.echo(f"Run not found: {run_id}", err=True)
            raise SystemExit(1)
        if as_json:
            click.echo(json.dumps(run.to_dict(), indent=2))
        else:
            _print_run_summary(run)
    elif show_last:
        run = store.last()
        if run is None:
            click.echo("No runs found.", err=True)
            raise SystemExit(1)
        if as_json:
            click.echo(json.dumps(run.to_dict(), indent=2))
        else:
            _print_run_summary(run)
    else:
        runs = store.list_runs()
        if not runs:
            click.echo("No interferometry runs found.")
            return
        if as_json:
            click.echo(json.dumps(runs, indent=2))
        else:
            for r in runs:
                sig = r.get("signals", {})
                mode_str = r.get("mode", "parallel")
                click.echo(
                    f"  {r['id']}  {mode_str:8s}  "
                    f"shared={sig.get('shared_count', 0)}  "
                    f"unique={sig.get('unique_count', 0)}  "
                    f"conflicts={sig.get('conflict_count', 0)}  "
                    f"{r.get('prompt', '')[:40]}"
                )


@interferometry_cmd.command("divergence")
@click.option("--last", "show_last", is_flag=True, default=True, help="Show last run divergence.")
@click.option("--id", "run_id", default=None, help="Show divergence for a specific run.")
@click.pass_context
def interferometry_divergence(ctx: click.Context, show_last: bool, run_id: str | None) -> None:
    """Show signal divergence summary."""
    from .interferometry import InterferometryStore

    gov_dir = ensure_initialized(ctx)
    store = InterferometryStore(gov_dir)

    run = store.load(run_id) if run_id else store.last()
    if run is None:
        click.echo("No run found.", err=True)
        raise SystemExit(1)

    s = run.signals
    click.echo(f"Run {run.id} ({run.mode.value}, {len(run.runs)} models)")
    click.echo(f"  Total claims:         {s.total_claims}")
    click.echo(f"  Shared:               {s.shared_count}")
    click.echo(f"  Unique:               {s.unique_count}")
    click.echo(f"  Conflicting:          {s.conflict_count}")
    click.echo(f"  Disagreement rate:    {s.disagreement_rate:.1%}")
    click.echo(f"  Specifics conflicts:  {s.specifics_conflict_count}")

    if run.conflicts:
        click.echo("\nConflicting claims:")
        for c in run.conflicts:
            click.echo(f"  - [{c.category}] {c.claim_text} (sources: {', '.join(c.sources)})")


@interferometry_cmd.command("accept")
@click.option("--shared", "shared_only", is_flag=True, default=True,
              help="Promote only shared claims (default).")
@click.option("--all", "promote_all", is_flag=True, help="Also promote unique claims at low confidence.")
@click.option("--id", "run_id", default=None, help="Run ID to promote from.")
@click.pass_context
def interferometry_accept(ctx: click.Context, shared_only: bool, promote_all: bool, run_id: str | None) -> None:
    """Promote claims from an interferometry run to the epistemic ledger."""
    from .interferometry import InterferometryStore, promote_to_ledger
    from .epistemic import EpistemicLedger

    gov_dir = ensure_initialized(ctx)
    store = InterferometryStore(gov_dir)

    run = store.load(run_id) if run_id else store.last()
    if run is None:
        click.echo("No run found.", err=True)
        raise SystemExit(1)

    ledger = EpistemicLedger(gov_dir)
    ids = promote_to_ledger(run, ledger, shared_only=not promote_all)
    click.echo(f"Promoted {len(ids)} claim(s) to epistemic ledger.")
    for cid in ids:
        click.echo(f"  {cid}")


def _print_run_summary(run: Any) -> None:
    """Print a human-readable summary of an interferometry run."""
    click.echo(f"Run: {run.id} ({run.mode.value})")
    click.echo(f"Prompt: {run.prompt[:80]}")
    if run.mode.value == "serial":
        click.echo(f"Rounds: {run.rounds}")
    click.echo(f"Created: {run.created_at}")
    click.echo()

    for r in run.runs:
        round_label = f" (round {r.round_number})" if run.mode.value == "serial" else ""
        click.echo(f"  [{r.backend_type}:{r.model_id}{round_label}] {r.latency_ms:.0f}ms")
        if r.extraction:
            click.echo(f"    Claims: {r.extraction.total_signals}, Assertiveness: {r.extraction.assertiveness_score:.2f}")
        click.echo(f"    Response: {r.response[:100]}...")
        click.echo()

    s = run.signals
    click.echo(f"Signals: shared={s.shared_count} unique={s.unique_count} conflicts={s.conflict_count}")
    click.echo(f"Disagreement rate: {s.disagreement_rate:.1%}")

    if run.shared:
        click.echo("\nShared claims:")
        for c in run.shared:
            click.echo(f"  + {c.claim_text} (confidence: {c.confidence:.0%})")
    if run.conflicts:
        click.echo("\nConflicting claims:")
        for c in run.conflicts:
            click.echo(f"  ! {c.claim_text} (sources: {', '.join(c.sources)})")
    if run.unique:
        click.echo("\nUnique claims:")
        for c in run.unique:
            click.echo(f"  ? {c.claim_text} (from: {', '.join(c.sources)})")


@interferometry_cmd.command("compare")
@click.argument("prompt", required=False)
@click.option("--backends", "-b", default=None,
              help="Comma-separated backend:model pairs, e.g. ollama:llama3,anthropic:claude-3-haiku")
@click.option("--last", "show_last", is_flag=True, help="Analyze the most recent interferometry run.")
@click.option("--id", "run_id", default=None, help="Analyze a specific run by ID.")
@click.option("--markers", "show_markers", is_flag=True, help="Show only risk markers (union lens).")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def interferometry_compare(ctx: click.Context, prompt: str | None, backends: str | None,
                           show_last: bool, run_id: str | None, show_markers: bool,
                           as_json: bool) -> None:
    """Code-specific interferometry compare — risk markers, anchor conflicts, tier."""
    import asyncio
    from .interferometry import InterferometryStore, RunMode, run_ensemble
    from .code_interferometry import compute_code_divergence, format_tier1_banner
    from .continuity import create_registry

    gov_dir = ensure_initialized(ctx)
    store = InterferometryStore(gov_dir)

    # Resolve or create the interferometry run
    if run_id:
        irun = store.load(run_id)
        if irun is None:
            click.echo(f"Run not found: {run_id}", err=True)
            raise SystemExit(1)
    elif show_last:
        irun = store.last()
        if irun is None:
            click.echo("No interferometry runs found.", err=True)
            raise SystemExit(1)
    elif prompt and backends:
        # Run ensemble first
        backend_configs = []
        for pair in backends.split(","):
            pair = pair.strip()
            if ":" not in pair:
                click.echo(f"Error: invalid backend:model pair: {pair}", err=True)
                raise SystemExit(1)
            bt, model = pair.split(":", 1)
            config: dict = {"backend_type": bt, "model": model}
            import os
            if bt == "anthropic":
                config["api_key"] = os.environ.get("ANTHROPIC_API_KEY", "")
            elif bt == "ollama":
                config["host"] = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
            elif bt == "claude-code":
                config["claude_path"] = os.environ.get("CLAUDE_PATH", "claude")
            elif bt == "codex":
                config["codex_path"] = os.environ.get("CODEX_PATH", "codex")
            backend_configs.append(config)
        irun = asyncio.run(run_ensemble(prompt, backend_configs))
        store.save(irun)
    else:
        click.echo("Provide a prompt + --backends, or use --last / --id.", err=True)
        raise SystemExit(1)

    # Load anchors for compatibility checking
    try:
        registry = create_registry(gov_dir)
        anchors = registry.all()
    except Exception:
        anchors = []

    report = compute_code_divergence(irun, anchors)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    # Human-readable output
    click.echo(f"Code Compare — Run {irun.id} (tier {report.tier})")
    click.echo(f"  Models: {', '.join(r.model_id for r in irun.runs)}")

    if report.tier >= 1:
        banner = format_tier1_banner(report)
        click.echo(f"\n  ⚠️  {banner}")

    if report.risk_marker_union:
        click.echo(f"\nRisk markers (union lens — {len(report.risk_marker_union)} total):")
        for m in report.risk_marker_union:
            icon = "🔴" if m.category.value == "security" else "🟡"
            click.echo(f"  {icon} [{m.category.value}] {m.marker_type.value}: {m.message}")
            click.echo(f"     from {m.model_id} at {m.file_path}:{m.line_number}")

    if not show_markers and report.anchor_conflicts:
        click.echo(f"\nAnchor conflicts ({len(report.anchor_conflicts)}):")
        for c in report.anchor_conflicts:
            icon = "⛔" if c.conflict_type.value == "hard" else "⚠️"
            click.echo(f"  {icon} [{c.conflict_type.value}] {c.anchor_id}: {c.description}")

    if not report.risk_marker_union and not report.anchor_conflicts:
        click.echo("\n  No risk markers or anchor conflicts detected.")

    # Per-model unique markers
    if report.risk_marker_unique and not show_markers:
        click.echo("\nPer-model unique markers:")
        for model_id, markers in report.risk_marker_unique.items():
            click.echo(f"  {model_id}: {len(markers)} unique marker(s)")


# =============================================================================
# External Constraint Attachment
# =============================================================================


@cli.group("external")
def external_cmd() -> None:
    """External constraint attachment — bind claims to external substrates.

    Attach claims to external data sources (Wikidata, Wikipedia, Scholar)
    to create structural constraint bindings. This is NOT fact verification —
    it logs what external sources reported at specific moments.

    \b
    Substrates (query order):
      wikidata   Structured knowledge graph (most reliable)
      wikipedia  Human-readable articles (dynamic)
      scholar    Academic papers via CrossRef (DOI resolution)
    """
    pass


@external_cmd.command("query")
@click.argument("substrate_id", type=click.Choice(["wikidata", "wikipedia", "scholar"]))
@click.argument("query")
@click.option("--affordance", "-a", help="Query affordance (entity/search/article/doi)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def external_query(
    substrate_id: str,
    query: str,
    affordance: str | None,
    as_json: bool,
) -> None:
    """Query an external substrate directly.

    This is for exploration — it queries the substrate and shows
    the response without binding to any claim.

    \b
    Examples:
      governor external query wikidata Q42
      governor external query wikidata "Douglas Adams" --affordance search
      governor external query wikipedia "Douglas Adams"
      governor external query scholar "10.1000/xyz123" --affordance doi
    """
    from .external import get_substrate

    substrate = get_substrate(substrate_id)
    if not substrate:
        click.echo(f"Unknown substrate: {substrate_id}", err=True)
        raise SystemExit(1)

    snapshot = substrate.query(query, affordance)

    if as_json:
        click.echo(json.dumps(snapshot.to_dict(), indent=2))
    else:
        click.echo(f"Substrate: {snapshot.substrate_id}")
        click.echo(f"Query: {snapshot.query}")
        click.echo(f"Affordance: {snapshot.affordance_used}")
        click.echo(f"Queried at: {snapshot.queried_at.isoformat()}")
        click.echo(f"Response hash: {snapshot.response_hash[:16]}...")
        click.echo("\n--- Response ---")
        # Truncate response for display
        response = snapshot.response
        if len(response) > 2000:
            response = response[:2000] + "\n... (truncated)"
        click.echo(response)


@external_cmd.command("attach")
@click.argument("claim_id")
@click.option("--substrate", "-s", required=True, type=click.Choice(["wikidata", "wikipedia", "scholar"]))
@click.option("--query", "-q", required=True, help="Query string for the substrate")
@click.option("--affordance", "-a", help="Query affordance")
@click.option("--claim-value", "-v", help="Claim value for discrepancy tracking")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def external_attach(
    claim_id: str,
    substrate: str,
    query: str,
    affordance: str | None,
    claim_value: str | None,
    as_json: bool,
) -> None:
    """Attach external constraint to a claim.

    Queries the substrate and binds the result to the specified claim.
    If binding type is CONTRADICTS and claim_value is provided,
    a discrepancy record is created.

    \b
    Examples:
      governor external attach claim_123 --substrate wikidata --query Q42
      governor external attach claim_123 -s wikipedia -q "Douglas Adams" -v "Adams wrote in 1978"
    """
    from .external import ConstraintManager
    from datetime import datetime

    manager = ConstraintManager()

    # In a real integration, we'd look up the claim's creation time
    # For now, use current time minus a small delta
    claim_created_at = datetime.utcnow()

    try:
        snapshot, binding = manager.attach_constraint(
            claim_id=claim_id,
            claim_created_at=claim_created_at,
            claim_value=claim_value or "",
            substrate_id=substrate,
            query=query,
            affordance=affordance,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps({
            "snapshot": snapshot.to_dict(),
            "binding": binding.to_dict(),
        }, indent=2))
    else:
        click.echo(f"Binding created: {binding.binding_id}")
        click.echo(f"  Claim: {claim_id}")
        click.echo(f"  Snapshot: {snapshot.snapshot_id}")
        click.echo(f"  Type: {binding.binding_type.value}")
        click.echo(f"  Δt: {binding.delta_t}")

        discrepancies = manager.get_discrepancies()
        if discrepancies:
            click.echo(f"\nDiscrepancy created: {discrepancies[0].discrepancy_id}")


@external_cmd.command("bindings")
@click.argument("claim_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def external_bindings(claim_id: str, as_json: bool) -> None:
    """List external bindings for a claim.

    Shows all external constraint bindings attached to the specified claim.
    """
    from .external import get_manager

    manager = get_manager()
    bindings = manager.get_bindings(claim_id)

    if as_json:
        click.echo(json.dumps([b.to_dict() for b in bindings], indent=2))
    elif not bindings:
        click.echo(f"No bindings for claim: {claim_id}")
    else:
        click.echo(f"Bindings for {claim_id}:\n")
        for binding in bindings:
            snapshot = manager.get_snapshot(binding.snapshot_id)
            click.echo(f"  {binding.binding_id}")
            click.echo(f"    Type: {binding.binding_type.value}")
            click.echo(f"    Substrate: {snapshot.substrate_id if snapshot else 'unknown'}")
            click.echo(f"    Δt: {binding.delta_t}")
            if binding.notes:
                click.echo(f"    Notes: {binding.notes}")
            click.echo()


@external_cmd.command("discrepancies")
@click.option("--pending", is_flag=True, help="Show only pending discrepancies")
@click.option("--contradicts", is_flag=True, help="Alias for --pending")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def external_discrepancies(pending: bool, contradicts: bool, as_json: bool) -> None:
    """Show discrepancies between claims and external substrates.

    Discrepancies are created when a binding type is CONTRADICTS.
    They must be resolved by human action.
    """
    from .external import get_manager, Resolution

    manager = get_manager()
    status = Resolution.PENDING if (pending or contradicts) else None
    discrepancies = manager.get_discrepancies(status=status)

    if as_json:
        click.echo(json.dumps([d.to_dict() for d in discrepancies], indent=2))
    elif not discrepancies:
        click.echo("No discrepancies found.")
    else:
        for disc in discrepancies:
            click.echo(f"{disc.discrepancy_id}")
            click.echo(f"  Claim: {disc.claim_id}")
            click.echo(f"  Claim value: {disc.claim_value[:60]}..." if len(disc.claim_value) > 60 else f"  Claim value: {disc.claim_value}")
            click.echo(f"  Substrate value: {disc.substrate_value[:60]}..." if len(disc.substrate_value) > 60 else f"  Substrate value: {disc.substrate_value}")
            click.echo(f"  Resolution: {disc.resolution.value}")
            if disc.resolution_reason:
                click.echo(f"  Reason: {disc.resolution_reason}")
            click.echo()


@external_cmd.command("resolve")
@click.argument("discrepancy_id")
@click.option("--resolution", "-r", required=True,
              type=click.Choice(["claim_updated", "claim_retained", "substrate_stale", "context_differs"]))
@click.option("--reason", required=True, help="Reason for resolution")
def external_resolve(discrepancy_id: str, resolution: str, reason: str) -> None:
    """Resolve a discrepancy (human action).

    The governor NEVER auto-resolves discrepancies. This command
    records the human decision about how to handle the contradiction.

    \b
    Resolution types:
      claim_updated    Claim was revised based on external info
      claim_retained   Claim kept despite contradiction
      substrate_stale  External source was out of date
      context_differs  Different contexts, both valid
    """
    from .external import get_manager, Resolution

    manager = get_manager()

    try:
        resolved = manager.resolve_discrepancy(
            discrepancy_id=discrepancy_id,
            resolution=Resolution(resolution),
            reason=reason,
        )
        click.echo(f"Resolved: {resolved.discrepancy_id}")
        click.echo(f"  Resolution: {resolved.resolution.value}")
        click.echo(f"  Reason: {resolved.resolution_reason}")
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
        raise SystemExit(1)


@external_cmd.command("substrates")
def external_substrates() -> None:
    """List available external substrates."""
    from .external import list_substrates, TRUST_PROFILES

    click.echo("Available substrates:\n")
    for substrate_id in list_substrates():
        profile = TRUST_PROFILES.get(substrate_id)
        if profile:
            click.echo(f"  {substrate_id}")
            click.echo(f"    Volatility: {profile.volatility.value}")
            click.echo(f"    Authority: {profile.authority_type.value}")
            click.echo(f"    TTL: {profile.snapshot_ttl}")
            click.echo()


# =============================================================================
# Session Continuity
# =============================================================================


@cli.group("session")
@click.pass_context
def session_group(ctx: click.Context) -> None:
    """Session continuity: capsule-based session management.

    Resume intent + constraints + authority, NOT chat replay.

    \b
    Usage:
        governor session create <name>          Create a new session
        governor session list                   List sessions
        governor session resume <id>            Resume a session
        governor session fork <name>            Fork current session
        governor session checkpoint <name>      Create checkpoint
        governor session promote <id>           Promote fork to mainline
    """
    pass


@session_group.command("create")
@click.argument("name")
@click.option("--mode", "-m", type=click.Choice(["fiction", "code", "nonfiction"]), default="fiction",
              help="Session mode")
@click.pass_context
def session_create(ctx: click.Context, name: str, mode: str) -> None:
    """Create a new session."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    capsule = manager.create(name, mode)
    click.echo(f"Created session: {capsule.metadata.session_id}")
    click.echo(f"  Name: {name}")
    click.echo(f"  Mode: {mode}")
    click.echo(f"  Mainline: {capsule.metadata.is_mainline}")


@session_group.command("list")
@click.option("--mode", "-m", type=click.Choice(["fiction", "code", "nonfiction"]), help="Filter by mode")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def session_capsule_list(ctx: click.Context, mode: str | None, as_json: bool) -> None:
    """List all sessions."""
    from .session_continuity import SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    sessions = store.list_sessions(mode)

    if as_json:
        click.echo(json.dumps(sessions, indent=2))
        return

    if not sessions:
        click.echo("No sessions found.")
        return

    mainline_id = store.get_mainline(mode)
    for s in sessions:
        marker = " [mainline]" if s["session_id"] == mainline_id else ""
        fork_marker = f" (fork of {s['parent_id'][:12]}...)" if s.get("parent_id") else ""
        click.echo(f"  {s['session_id'][:16]}... {s['name']}{marker}{fork_marker}")


@session_group.command("resume")
@click.argument("session_id", required=False)
@click.option("--last", is_flag=True, help="Resume most recent session")
@click.pass_context
def session_resume(ctx: click.Context, session_id: str | None, last: bool) -> None:
    """Resume a session by ID or --last."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    if last:
        capsule = manager.resume_last()
    elif session_id:
        capsule = manager.resume(session_id)
    else:
        click.echo("Error: Provide session ID or --last", err=True)
        ctx.exit(1)
        return

    if capsule is None:
        click.echo("Error: Session not found", err=True)
        ctx.exit(1)
        return

    click.echo(f"Resumed session: {capsule.metadata.session_id}")
    click.echo(f"  Name: {capsule.metadata.name}")
    click.echo(f"  Mode: {capsule.metadata.mode}")
    click.echo(f"  Intent: {capsule.ledger.intent or '(none)'}")
    click.echo(f"  Anchors: {len(capsule.ledger.anchors)}")
    click.echo(f"  Decisions: {len(capsule.ledger.decisions)}")


@session_group.command("show")
@click.argument("session_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def session_show(ctx: click.Context, session_id: str, as_json: bool) -> None:
    """Show session details."""
    from .session_continuity import SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    capsule = store.load_session(session_id)

    if capsule is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(capsule.to_dict(), indent=2, default=str))
    else:
        click.echo(f"Session: {capsule.metadata.session_id}")
        click.echo(f"  Name: {capsule.metadata.name}")
        click.echo(f"  Mode: {capsule.metadata.mode}")
        click.echo(f"  State: {capsule.metadata.state.value}")
        click.echo(f"  Mainline: {capsule.metadata.is_mainline}")
        click.echo(f"  Created: {capsule.metadata.created_at}")
        click.echo(f"  Last Active: {capsule.metadata.last_active}")
        if capsule.metadata.parent_id:
            click.echo(f"  Parent: {capsule.metadata.parent_id}")
        click.echo("Ledger:")
        click.echo(f"  Intent: {capsule.ledger.intent or '(none)'}")
        click.echo(f"  Anchors: {len(capsule.ledger.anchors)}")
        click.echo(f"  Decisions: {len(capsule.ledger.decisions)}")
        click.echo(f"  Constraints: {len(capsule.ledger.constraints)}")
        click.echo(f"  Canon Events: {len(capsule.ledger.canon_events)}")
        click.echo("Workspace:")
        click.echo(f"  Current Section: {capsule.workspace.current_section or '(none)'}")
        click.echo(f"  Active Threads: {len(capsule.workspace.active_thread_ids)}")


@session_group.command("fork")
@click.argument("name", required=False)
@click.option("--from", "from_session", help="Session ID to fork from (default: most recent)")
@click.pass_context
def session_fork(ctx: click.Context, name: str | None, from_session: str | None) -> None:
    """Fork a session to experiment with alternatives."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    # Resume the session to fork
    if from_session:
        capsule = manager.resume(from_session)
    else:
        capsule = manager.resume_last()

    if capsule is None:
        click.echo("Error: No session to fork", err=True)
        ctx.exit(1)
        return

    fork = manager.fork(name)
    if fork is None:
        click.echo("Error: Failed to create fork", err=True)
        ctx.exit(1)
        return

    click.echo(f"Created fork: {fork.metadata.session_id}")
    click.echo(f"  Name: {fork.metadata.name}")
    click.echo(f"  Parent: {fork.metadata.parent_id}")


@session_group.command("checkpoint")
@click.argument("name", required=False)
@click.option("--session", "-s", help="Session ID (default: most recent)")
@click.pass_context
def session_checkpoint(ctx: click.Context, name: str | None, session: str | None) -> None:
    """Create a checkpoint to save current state."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    # Resume the session
    if session:
        capsule = manager.resume(session)
    else:
        capsule = manager.resume_last()

    if capsule is None:
        click.echo("Error: No active session", err=True)
        ctx.exit(1)
        return

    checkpoint = manager.checkpoint(name)
    if checkpoint is None:
        click.echo("Error: Failed to create checkpoint", err=True)
        ctx.exit(1)
        return

    click.echo(f"Created checkpoint: {checkpoint.checkpoint_id}")
    click.echo(f"  Name: {checkpoint.name}")
    click.echo(f"  Ledger hash: {checkpoint.ledger_hash}")


@session_group.command("checkpoints")
@click.option("--session", "-s", help="Session ID (default: most recent)")
@click.pass_context
def session_checkpoints(ctx: click.Context, session: str | None) -> None:
    """List checkpoints for a session."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    # Resume the session
    if session:
        manager.resume(session)
    else:
        manager.resume_last()

    if manager.active is None:
        click.echo("Error: No active session", err=True)
        ctx.exit(1)
        return

    checkpoints = manager.get_checkpoints()
    if not checkpoints:
        click.echo("No checkpoints found.")
        return

    for cp in checkpoints:
        click.echo(f"  {cp['checkpoint_id'][:16]}... {cp['name']} ({cp['created_at']})")


@session_group.command("promote")
@click.argument("session_id")
@click.option("--confirm", is_flag=True, help="Confirm promotion")
@click.pass_context
def session_promote(ctx: click.Context, session_id: str, confirm: bool) -> None:
    """Promote a fork to mainline."""
    from .session_continuity import SessionManager, SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")
    manager = SessionManager(store)

    # Load the session to promote
    capsule = store.load_session(session_id)
    if capsule is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    if capsule.metadata.is_mainline:
        click.echo("Session is already mainline.")
        return

    if not confirm:
        click.echo(f"WARNING: This will make '{capsule.metadata.name}' the new mainline.")
        click.echo("  Current mainline will be archived.")
        click.echo("  Use --confirm to proceed.")
        return

    success = manager.promote(session_id)
    if success:
        click.echo(f"Promoted session: {session_id}")
        click.echo(f"  {capsule.metadata.name} is now mainline.")
    else:
        click.echo("Error: Promotion failed", err=True)
        ctx.exit(1)


@session_group.command("delete")
@click.argument("session_id")
@click.option("--confirm", is_flag=True, help="Confirm deletion")
@click.pass_context
def session_delete(ctx: click.Context, session_id: str, confirm: bool) -> None:
    """Delete a session."""
    from .session_continuity import SessionStore

    gov_dir = ensure_initialized(ctx)
    store = SessionStore(gov_dir / "sessions")

    capsule = store.load_session(session_id)
    if capsule is None:
        click.echo(f"Error: Session not found: {session_id}", err=True)
        ctx.exit(1)
        return

    if not confirm:
        click.echo(f"WARNING: This will delete session '{capsule.metadata.name}'.")
        click.echo("  Use --confirm to proceed.")
        return

    success = store.delete_session(session_id)
    if success:
        click.echo(f"Deleted session: {session_id}")
    else:
        click.echo("Error: Deletion failed", err=True)
        ctx.exit(1)


# =============================================================================
# Context Compact CLI
# =============================================================================


@cli.group("context")
def context_cmd() -> None:
    """Context management — loss-aware compaction with receipts.

    Governed compaction that emits receipts, respects anchors,
    and never silently drops governance state.

    \b
    Core principle:
      If you compact without knowing what you lost, you've created a lie.
    """
    pass


@context_cmd.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def context_status(ctx: click.Context, as_json: bool) -> None:
    """Show context compaction status and configuration."""
    from .context_compact import CompactionConfig
    from pathlib import Path

    gov_dir = Path(".governor")
    config_path = gov_dir / "compaction.yaml"
    config = CompactionConfig.load(config_path)

    status = {
        "config_exists": config_path.exists(),
        "context_threshold": config.context_threshold,
        "min_turns_before_compact": config.min_turns_before_compact,
        "recent_turns_to_keep": config.recent_turns_to_keep,
        "always_keep_decisions": config.always_keep_decisions,
        "always_keep_anchors": config.always_keep_anchors,
        "store_dropped_content": config.store_dropped_content,
    }

    if as_json:
        click.echo(json.dumps(status, indent=2))
    else:
        click.echo("Context Compaction Configuration:")
        click.echo(f"  Threshold: {config.context_threshold * 100}%")
        click.echo(f"  Min turns before compact: {config.min_turns_before_compact}")
        click.echo(f"  Recent turns to keep: {config.recent_turns_to_keep}")
        click.echo(f"  Keep decisions: {config.always_keep_decisions}")
        click.echo(f"  Keep anchors: {config.always_keep_anchors}")
        click.echo(f"  Store dropped content: {config.store_dropped_content}")


@context_cmd.command("config")
@click.option("--threshold", type=float, help="Context threshold (0.0-1.0)")
@click.option("--min-turns", type=int, help="Min turns before compaction")
@click.option("--keep-turns", type=int, help="Recent turns to keep")
@click.option("--show", is_flag=True, help="Show current config")
@click.pass_context
def context_config(
    ctx: click.Context,
    threshold: float | None,
    min_turns: int | None,
    keep_turns: int | None,
    show: bool,
) -> None:
    """Configure context compaction settings."""
    from .context_compact import CompactionConfig
    from pathlib import Path

    gov_dir = Path(".governor")
    gov_dir.mkdir(exist_ok=True)
    config_path = gov_dir / "compaction.yaml"
    config = CompactionConfig.load(config_path)

    if show or (threshold is None and min_turns is None and keep_turns is None):
        click.echo(json.dumps(config.to_dict(), indent=2))
        return

    if threshold is not None:
        config.context_threshold = threshold
    if min_turns is not None:
        config.min_turns_before_compact = min_turns
    if keep_turns is not None:
        config.recent_turns_to_keep = keep_turns

    config.save(config_path)
    click.echo("Configuration updated.")


@context_cmd.command("receipts")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--last", "show_last", is_flag=True, help="Show latest receipt")
@click.option("--id", "receipt_id", help="Show specific receipt by ID")
@click.pass_context
def context_receipts(ctx: click.Context, as_json: bool, show_last: bool, receipt_id: str | None) -> None:
    """List or show compaction receipts."""
    from .context_compact import ReceiptStore
    from pathlib import Path

    gov_dir = Path(".governor")
    if not gov_dir.exists():
        click.echo("No .governor directory found.")
        return

    store = ReceiptStore(gov_dir / "receipts")
    receipts = store.list_all()

    if show_last:
        receipt = store.get_latest()
        if receipt is None:
            click.echo("No receipts found.")
            return
        if as_json:
            click.echo(json.dumps(receipt.to_dict(), indent=2))
        else:
            click.echo(f"Receipt: {receipt.receipt_id}")
            click.echo(f"  Compacted at: {receipt.compacted_at}")
            click.echo(f"  Preserved turns: {receipt.preserved_turns_count}")
            click.echo(f"  Dropped items: {len(receipt.dropped_items)}")
            click.echo(f"  Dropped tokens: {receipt.total_dropped_tokens}")
            click.echo(f"  Decisions preserved: {len(receipt.preserved_decisions)}")
            click.echo(f"  Anchors preserved: {len(receipt.preserved_anchors)}")
        return

    if receipt_id:
        receipt = store.load(receipt_id)
        if receipt is None:
            click.echo(f"Receipt not found: {receipt_id}", err=True)
            ctx.exit(1)
            return
        if as_json:
            click.echo(json.dumps(receipt.to_dict(), indent=2))
        else:
            click.echo(f"Receipt: {receipt.receipt_id}")
            click.echo(f"  Compacted at: {receipt.compacted_at}")
            click.echo(f"  Preserved intent: {receipt.preserved_intent}")
            click.echo(f"  Summary hash: {receipt.compressed_hash[:16]}...")
            click.echo(f"\nDropped items ({len(receipt.dropped_items)}):")
            for item in receipt.dropped_items[:10]:
                click.echo(f"  [{item.item_type.value}] {item.description}")
            if len(receipt.dropped_items) > 10:
                click.echo(f"  ... and {len(receipt.dropped_items) - 10} more")
        return

    # List all receipts
    if not receipts:
        click.echo("No receipts found.")
        return

    if as_json:
        click.echo(json.dumps(receipts, indent=2))
    else:
        click.echo(f"Compaction receipts ({len(receipts)}):")
        for rid in receipts:
            receipt = store.load(rid)
            if receipt:
                click.echo(f"  {rid} - {receipt.compacted_at.strftime('%Y-%m-%d %H:%M')}")


@context_cmd.command("recover")
@click.argument("receipt_id")
@click.argument("content_hash")
@click.pass_context
def context_recover(ctx: click.Context, receipt_id: str, content_hash: str) -> None:
    """Recover dropped content by hash."""
    from .context_compact import RecoveryStore
    from pathlib import Path

    gov_dir = Path(".governor")
    if not gov_dir.exists():
        click.echo("No .governor directory found.", err=True)
        ctx.exit(1)
        return

    store = RecoveryStore(gov_dir / "recovery")
    content = store.recover(receipt_id, content_hash)

    if content is None:
        click.echo(f"Content not found for hash: {content_hash}", err=True)
        ctx.exit(1)
        return

    click.echo(content)


@context_cmd.command("cleanup")
@click.option("--max-age", type=int, default=24, help="Max age in hours (default: 24)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted")
@click.pass_context
def context_cleanup(ctx: click.Context, max_age: int, dry_run: bool) -> None:
    """Clean up old recovery stores."""
    from .context_compact import RecoveryStore
    from pathlib import Path

    gov_dir = Path(".governor")
    if not gov_dir.exists():
        click.echo("No .governor directory found.")
        return

    store = RecoveryStore(gov_dir / "recovery")

    if dry_run:
        click.echo(f"Would clean up recovery stores older than {max_age} hours.")
        # List what would be deleted
        from datetime import timedelta
        from governor.context_compact import _utcnow
        cutoff = _utcnow() - timedelta(hours=max_age)
        for store_dir in store.base_path.iterdir():
            if store_dir.is_dir():
                from datetime import datetime
                mtime = datetime.fromtimestamp(store_dir.stat().st_mtime)
                if mtime < cutoff:
                    click.echo(f"  Would delete: {store_dir.name}")
        return

    removed = store.cleanup_old(max_age)
    click.echo(f"Cleaned up {removed} old recovery store(s).")


# =============================================================================
# Perforce Governance CLI
# =============================================================================


@cli.group("p4")
def p4_cmd() -> None:
    """Perforce governance — integrity invariants on explicit authority.

    Applies the same integrity invariants as Git governance, but on a substrate
    that already admits authority exists.

    \b
    Checks:
      changelist_integrity  Metadata claims must match files in CL
      lock_semantics        Locked files are authoritative state
      immutable_release     Tagged release CLs cannot be modified
      doi_mapping           DOI corresponds to depot path + changelist
    """
    pass


@p4_cmd.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def p4_status(ctx: click.Context, as_json: bool) -> None:
    """Show P4 governance status and configuration."""
    from .perforce import P4Governor

    gov = P4Governor()

    if as_json:
        output = {
            "available": gov.is_available(),
            "config": gov.config.to_dict(),
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"P4 available: {gov.is_available()}")
        click.echo(f"Governance enabled: {gov.config.enabled}")
        if gov.config.connection.port:
            click.echo(f"P4 port: {gov.config.connection.port}")
        click.echo("\nCheck status:")
        click.echo(f"  Changelist integrity: {'enabled' if gov.config.changelist_integrity.enabled else 'disabled'}")
        click.echo(f"  Lock semantics: {'enabled' if gov.config.lock_semantics.enabled else 'disabled'}")
        click.echo(f"  Immutable releases: {'enabled' if gov.config.immutable_releases.enabled else 'disabled'}")
        click.echo(f"  DOI mapping: {'enabled' if gov.config.doi_mapping.enabled else 'disabled'}")


@p4_cmd.command("check")
@click.argument("changelist", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def p4_check(ctx: click.Context, changelist: int, as_json: bool) -> None:
    """Run pre-submit checks on a changelist."""
    from .perforce import P4Governor

    gov = P4Governor()

    if not gov.is_available():
        click.echo("Warning: P4 not available, checks limited", err=True)

    violations = gov.pre_submit_check(changelist)
    should_block, blocking = gov.should_block(changelist)

    if as_json:
        output = {
            "changelist": changelist,
            "violations": [v.to_dict() for v in violations],
            "should_block": should_block,
            "blocking_count": len(blocking),
        }
        click.echo(json.dumps(output, indent=2))
    else:
        if not violations:
            click.echo(f"CL {changelist}: PASSED")
        else:
            click.echo(f"CL {changelist}: {len(violations)} violation(s)")
            for v in violations:
                severity_mark = "!" if v.severity.value == "block" else "~"
                click.echo(f"  [{severity_mark}] {v.message}")

        if should_block:
            click.echo(f"\nBLOCKED: {len(blocking)} blocking violation(s)")
            ctx.exit(1)


@p4_cmd.command("pre-submit")
@click.argument("changelist", type=int)
@click.pass_context
def p4_pre_submit(ctx: click.Context, changelist: int) -> None:
    """Pre-submit hook for P4 triggers.

    Returns exit code 0 if OK, 1 if blocked.
    """
    from .perforce import P4Governor

    gov = P4Governor()
    should_block, violations = gov.should_block(changelist)

    if should_block:
        for v in violations:
            click.echo(f"VIOLATION: {v.message}", err=True)
        ctx.exit(1)


@p4_cmd.command("locks")
@click.argument("file_path", required=False)
@click.option("--agent", help="Agent ID for lock check")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def p4_locks(ctx: click.Context, file_path: str | None, agent: str | None, as_json: bool) -> None:
    """Check lock status for a file."""
    from .perforce import P4Governor

    if not file_path:
        click.echo("Usage: governor p4 locks <file_path>")
        return

    gov = P4Governor()
    result = gov.check_lock(file_path, agent_id=agent)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            click.echo(f"Lock check PASSED for: {file_path}")
        else:
            click.echo(f"Lock check FAILED for: {file_path}")
            for v in result.violations:
                click.echo(f"  - {v.message}")


@p4_cmd.group("release")
def p4_release() -> None:
    """Manage immutable releases."""
    pass


@p4_release.command("tag")
@click.argument("changelist", type=int)
@click.argument("tag")
@click.pass_context
def p4_release_tag(ctx: click.Context, changelist: int, tag: str) -> None:
    """Mark a changelist as an immutable release."""
    from .perforce import P4Governor

    gov = P4Governor()

    if gov.mark_release(changelist, tag):
        click.echo(f"Marked CL {changelist} as immutable with tag: {tag}")
    else:
        click.echo(f"Error: '{tag}' is not a valid release tag", err=True)
        click.echo(f"Valid tags: {', '.join(gov.config.immutable_releases.tags)}")
        ctx.exit(1)


@p4_release.command("check")
@click.argument("changelist", type=int)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def p4_release_check(ctx: click.Context, changelist: int, as_json: bool) -> None:
    """Check if a changelist is immutable."""
    from .perforce import P4Governor

    gov = P4Governor()
    result = gov.check_immutable(changelist)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            click.echo(f"CL {changelist} is NOT immutable (modifications allowed)")
        else:
            click.echo(f"CL {changelist} is IMMUTABLE (modifications blocked)")


@p4_cmd.group("doi")
def p4_doi() -> None:
    """Manage DOI↔depot mappings."""
    pass


@p4_doi.command("map")
@click.argument("doi")
@click.argument("depot_path")
@click.argument("changelist", type=int)
@click.pass_context
def p4_doi_map(ctx: click.Context, doi: str, depot_path: str, changelist: int) -> None:
    """Create a DOI to depot path mapping."""
    from .perforce import P4Governor

    gov = P4Governor()
    mapping = gov.add_doi_mapping(doi, depot_path, changelist)

    click.echo(f"Mapped DOI: {doi}")
    click.echo(f"  Depot path: {depot_path}")
    click.echo(f"  Changelist: {changelist}")


@p4_doi.command("verify")
@click.argument("doi")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def p4_doi_verify(ctx: click.Context, doi: str, as_json: bool) -> None:
    """Verify a DOI mapping."""
    from .perforce import P4Governor

    gov = P4Governor()
    result = gov.verify_doi(doi)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            click.echo(f"DOI mapping verified: {doi}")
        else:
            click.echo(f"DOI mapping INVALID: {doi}")
            for v in result.violations:
                click.echo(f"  - {v.message}")
            ctx.exit(1)


@p4_doi.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def p4_doi_list(as_json: bool) -> None:
    """List all DOI mappings."""
    from .perforce import P4Governor

    gov = P4Governor()
    mappings = gov.doi_checker.list_mappings()

    if as_json:
        click.echo(json.dumps([m.to_dict() for m in mappings], indent=2))
    else:
        if not mappings:
            click.echo("No DOI mappings found.")
        else:
            click.echo(f"DOI Mappings ({len(mappings)}):")
            for m in mappings:
                click.echo(f"  {m.doi} -> {m.depot_path} @ CL{m.changelist}")


# =============================================================================
# Git Governance CLI
# =============================================================================


@cli.group("git-gov")
def git_gov_cmd() -> None:
    """Git governance — integrity invariants at commit boundaries.

    Enforces artifact integrity, cross-index validation, and tagging discipline
    while leaving workflow preferences to agents and humans.

    \b
    Profiles (controls severity, not whether checks run):
      greenfield   All checks warn (new projects)
      established  Cross-index and pre-commit block (default)
      production   All checks block (release-ready)
      hotfix       Tagging deferred, critical checks block
    """
    pass


@git_gov_cmd.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_status(ctx: click.Context, as_json: bool) -> None:
    """Show git governance configuration and status."""
    from .git_governance import GitGovernor

    gov = GitGovernor()

    if as_json:
        click.echo(json.dumps(gov.config.to_dict(), indent=2))
    else:
        click.echo(f"Profile: {gov.config.profile.value}")
        click.echo("\nSeverity by check type:")
        for ct in ["artifact_integrity", "cross_index", "tagging", "pre_commit"]:
            from .git_governance import CheckType
            sev = gov.config.get_severity(CheckType(ct))
            click.echo(f"  {ct}: {sev.value}")

        if gov.config.severity_overrides:
            click.echo("\nSeverity overrides:")
            for k, v in gov.config.severity_overrides.items():
                click.echo(f"  {k}: {v}")


@git_gov_cmd.command("check")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_check(ctx: click.Context, as_json: bool) -> None:
    """Run all git governance checks.

    Checks artifacts, cross-index references, and pre-commit conditions.
    Returns exit code 1 if any blocking violations are found.
    """
    from .git_governance import GitGovernor

    gov = GitGovernor()
    results = gov.check_all()
    should_block, blocking = gov.should_block()

    if as_json:
        output = {
            "checks": {k: v.to_dict() for k, v in results.items()},
            "should_block": should_block,
            "blocking_count": len(blocking),
        }
        click.echo(json.dumps(output, indent=2))
    else:
        all_violations = []
        for name, result in results.items():
            click.echo(f"\n{name.upper()}: {'PASS' if result.passed else 'FAIL'}")
            for v in result.violations:
                all_violations.append(v)
                severity_mark = "!" if v.severity.value == "block" else "~"
                click.echo(f"  [{severity_mark}] {v.message}")
                if v.suggestion:
                    click.echo(f"      Suggestion: {v.suggestion}")

        click.echo(f"\n{'='*40}")
        if should_block:
            click.echo(f"BLOCKED: {len(blocking)} blocking violation(s)")
            ctx.exit(1)
        elif all_violations:
            click.echo(f"WARNINGS: {len(all_violations)} violation(s), none blocking")
        else:
            click.echo("PASSED: No violations")


@git_gov_cmd.command("artifacts")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_artifacts(ctx: click.Context, as_json: bool) -> None:
    """Check artifact integrity for staged files."""
    from .git_governance import GitGovernor

    gov = GitGovernor()
    result = gov.check_artifacts()

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Artifact check: {'PASS' if result.passed else 'FAIL'}")
        for v in result.violations:
            click.echo(f"  - {v.message}")
            if v.suggestion:
                click.echo(f"    Suggestion: {v.suggestion}")

    if not result.passed:
        blocking = [v for v in result.violations if v.severity.value == "block"]
        if blocking:
            ctx.exit(1)


@git_gov_cmd.command("cross-index")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_cross_index(ctx: click.Context, as_json: bool) -> None:
    """Check cross-index references (DOI, version tags, etc.)."""
    from .git_governance import GitGovernor

    gov = GitGovernor()
    result = gov.check_cross_index()

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Cross-index check: {'PASS' if result.passed else 'FAIL'}")
        for v in result.violations:
            click.echo(f"  - {v.message}")
            if v.suggestion:
                click.echo(f"    Suggestion: {v.suggestion}")

    if not result.passed:
        blocking = [v for v in result.violations if v.severity.value == "block"]
        if blocking:
            ctx.exit(1)


@git_gov_cmd.command("pre-commit")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_pre_commit(ctx: click.Context, as_json: bool) -> None:
    """Run pre-commit checks (metadata, secrets)."""
    from .git_governance import GitGovernor

    gov = GitGovernor()
    result = gov.check_pre_commit()

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Pre-commit check: {'PASS' if result.passed else 'FAIL'}")
        for v in result.violations:
            click.echo(f"  - {v.message}")
            if v.suggestion:
                click.echo(f"    Suggestion: {v.suggestion}")

    if not result.passed:
        blocking = [v for v in result.violations if v.severity.value == "block"]
        if blocking:
            ctx.exit(1)


@git_gov_cmd.command("verify-tag")
@click.argument("tag")
@click.option("--type", "tag_type", help="Tag type (paper, release)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def git_gov_verify_tag(ctx: click.Context, tag: str, tag_type: str | None, as_json: bool) -> None:
    """Verify conditions for a tag.

    Checks that tag requirements are met before tagging.
    For example, release tags may require updated changelog and passing tests.
    """
    from .git_governance import GitGovernor

    gov = GitGovernor()
    result = gov.verify_tag(tag, tag_type)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Tag '{tag}' verification: {'PASS' if result.passed else 'FAIL'}")
        for v in result.violations:
            click.echo(f"  - {v.message}")

    if not result.passed:
        blocking = [v for v in result.violations if v.severity.value == "block"]
        if blocking:
            ctx.exit(1)


@git_gov_cmd.command("set-profile")
@click.argument("profile", type=click.Choice(["greenfield", "established", "production", "hotfix"]))
@click.pass_context
def git_gov_set_profile(ctx: click.Context, profile: str) -> None:
    """Set the git governance profile.

    \b
    Profiles:
      greenfield   All checks warn (new projects)
      established  Cross-index and pre-commit block (default)
      production   All checks block (release-ready)
      hotfix       Tagging deferred, critical checks block
    """
    from .git_governance import GitPolicyConfig, Profile
    from pathlib import Path

    config_path = Path(".governor/git_policy.yaml")

    # Load existing config or create new
    config = GitPolicyConfig.load(config_path)
    config.profile = Profile(profile)
    config.save(config_path)

    click.echo(f"Profile set to: {profile}")


@git_gov_cmd.command("allowlist")
@click.argument("action", type=click.Choice(["add", "remove", "list"]))
@click.argument("path", required=False)
@click.pass_context
def git_gov_allowlist(ctx: click.Context, action: str, path: str | None) -> None:
    """Manage artifact allowlist.

    \b
    Actions:
      add <path>     Add path to allowlist
      remove <path>  Remove path from allowlist
      list           Show current allowlist
    """
    from .git_governance import GitPolicyConfig
    from pathlib import Path as PathLib

    config_path = PathLib(".governor/git_policy.yaml")
    config = GitPolicyConfig.load(config_path)

    if action == "list":
        if config.artifact_rules.allowlist:
            click.echo("Allowlisted artifacts:")
            for p in config.artifact_rules.allowlist:
                click.echo(f"  - {p}")
        else:
            click.echo("No artifacts in allowlist")
    elif action == "add":
        if not path:
            click.echo("Error: path required for 'add'", err=True)
            ctx.exit(1)
        if path not in config.artifact_rules.allowlist:
            config.artifact_rules.allowlist.append(path)
            config.save(config_path)
            click.echo(f"Added to allowlist: {path}")
        else:
            click.echo(f"Already in allowlist: {path}")
    elif action == "remove":
        if not path:
            click.echo("Error: path required for 'remove'", err=True)
            ctx.exit(1)
        if path in config.artifact_rules.allowlist:
            config.artifact_rules.allowlist.remove(path)
            config.save(config_path)
            click.echo(f"Removed from allowlist: {path}")
        else:
            click.echo(f"Not in allowlist: {path}")


# =============================================================================
# Friendly CLI Commands (layered by persona)
# =============================================================================

# Import and register friendly command groups
from .cli_friendly import fiction, code, resolve

cli.add_command(fiction)
cli.add_command(code)
cli.add_command(resolve)


# ---------------------------------------------------------------------------
# Risk controller (control theory: R_t = PD/E)
# ---------------------------------------------------------------------------

RISK_STATE_FILE = "risk_controller.json"


def get_risk_controller(gov_dir: Path):
    """Get or create the risk controller."""
    from .control_theory import RiskController

    state_path = gov_dir / RISK_STATE_FILE
    if state_path.exists():
        data = json.loads(state_path.read_text())
        return RiskController.from_dict(data)
    return RiskController()


def save_risk_controller(gov_dir: Path, controller) -> None:
    """Save the risk controller state to disk."""
    state_path = gov_dir / RISK_STATE_FILE
    state_path.write_text(json.dumps(controller.to_dict(), indent=2))


@cli.group()
@click.pass_context
def risk(ctx: click.Context) -> None:
    """
    Risk index: R_t = (P * D) / E (control theory foundation).

    Computes the Agent Risk Index — a dimensionless ratio like the
    Reynolds number that classifies agent operation regime:
    - SAFE (R̄ < 0.1): Full autonomy
    - ELASTIC (0.1-0.4): Normal checks
    - DANGEROUS (0.4-0.8): Heightened scrutiny
    - RUNAWAY (≥ 0.8): Halt
    """
    pass


@risk.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def risk_status(ctx: click.Context, as_json: bool) -> None:
    """Show current R_t, R-bar, regime, and tier."""
    gov_dir = ensure_initialized(ctx)
    ctrl = get_risk_controller(gov_dir)
    state = ctrl.get_state()

    if as_json:
        click.echo(json.dumps(state, indent=2))
        return

    regime_val = state["current_regime"]
    regime_colors = {
        "safe": "green",
        "elastic": "blue",
        "dangerous": "yellow",
        "runaway": "bright_red",
    }
    color = regime_colors.get(regime_val, "white")

    click.echo(f"Regime:    {click.style(regime_val.upper(), fg=color, bold=True)}")
    click.echo(f"R̄ (EMA):   {state['r_bar_ema']:.4f}")
    click.echo(f"R̄ (SMA):   {state['r_bar_sma']:.4f}")
    click.echo(f"R̄ (worst): {state['r_bar_worst']:.4f}")
    click.echo(f"Power:     {state['current_power']:.4f}")
    click.echo(f"Delay:     {state['current_delay']:.4f}")
    click.echo(f"Evidence:  {state['current_evidence']:.4f}")
    click.echo(f"Window:    {state['window_size']} samples")
    click.echo(f"Episode:   {state['episode_steps']} steps")

    ol = state["open_loop"]
    if ol["is_open_loop"]:
        click.echo(click.style(f"\n⚠ OPEN LOOP: Γ={ol['gamma']:.2f}, backlog={ol['backlog']}", fg="red"))


@risk.command("check")
@click.argument("tool_class")
@click.option("-e", "--evidence", type=float, default=None, help="Evidence score (0-1)")
@click.option("-d", "--delay", type=float, default=None, help="Feedback delay")
@click.option("-p", "--power", type=float, default=None, help="Power (override tool default)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def risk_check(
    ctx: click.Context,
    tool_class: str,
    evidence: float | None,
    delay: float | None,
    power: float | None,
    as_json: bool,
) -> None:
    """Check if a tool action is allowed given current state."""
    gov_dir = ensure_initialized(ctx)
    ctrl = get_risk_controller(gov_dir)

    result = ctrl.check(tool_class, p_req=power, d_t=delay, e_t=evidence)
    save_risk_controller(gov_dir, ctrl)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    decision_colors = {
        "allow": "green",
        "deny": "red",
        "demote": "yellow",
        "halt": "bright_red",
    }
    color = decision_colors.get(result.decision.value, "white")
    click.echo(f"Decision: {click.style(result.decision.value.upper(), fg=color, bold=True)}")
    click.echo(f"Risk:     {result.risk:.4f}")
    click.echo(f"Regime:   {result.regime.value.upper()}")
    click.echo(f"Reason:   {result.reason}")
    if result.demoted_tier:
        click.echo(f"Demoted to tier {result.demoted_tier.level} (P≤{result.demoted_tier.p_threshold})")


@risk.command("history")
@click.option("--limit", "-n", default=10, help="Number of entries to show")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def risk_history(ctx: click.Context, limit: int, as_json: bool) -> None:
    """Show recent risk calculations."""
    gov_dir = ensure_initialized(ctx)
    ctrl = get_risk_controller(gov_dir)

    entries = ctrl.history[-limit:]

    if as_json:
        click.echo(json.dumps([e.to_dict() for e in entries], indent=2))
        return

    if not entries:
        click.echo("No risk history recorded.")
        return

    click.echo(f"Risk History (last {limit}):\n")
    for calc in entries:
        regime_val = calc.regime.value
        click.echo(f"  R={calc.risk:.4f}  P={calc.power:.3f}  D={calc.delay:.3f}  E={calc.evidence:.3f}  [{regime_val.upper()}]")


@risk.command("sensitivity")
@click.option("-p", "--power", type=float, required=True, help="Power value")
@click.option("-d", "--delay", type=float, required=True, help="Delay value")
@click.option("-e", "--evidence", type=float, required=True, help="Evidence value")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def risk_sensitivity(
    ctx: click.Context,
    power: float,
    delay: float,
    evidence: float,
    as_json: bool,
) -> None:
    """Compute sensitivity analysis (glass cannon detection)."""
    from .control_theory import compute_sensitivity

    s = compute_sensitivity(power, delay, evidence)

    if as_json:
        click.echo(json.dumps(s, indent=2))
        return

    click.echo(f"R_t:    {s['risk']:.4f}")
    click.echo(f"∂R/∂D:  {s['dr_dd']:.4f}  (delay sensitivity)")
    click.echo(f"∂R/∂E:  {s['dr_de']:.4f}  (evidence sensitivity)")

    if abs(s["dr_dd"]) > 0.5 or abs(s["dr_de"]) > 0.5:
        click.echo(click.style("\n⚠ Glass cannon region: small changes in D or E produce large R changes", fg="yellow"))


@risk.command("trajectory")
@click.option("--mode", type=click.Choice(["additive", "discounted", "worst_step"]), default="additive")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def risk_trajectory(ctx: click.Context, mode: str, as_json: bool) -> None:
    """Show episode risk trajectory."""
    gov_dir = ensure_initialized(ctx)
    ctrl = get_risk_controller(gov_dir)

    metrics = ctrl.get_episode_risk()

    if as_json:
        click.echo(json.dumps(metrics.to_dict(), indent=2))
        return

    click.echo(f"Episode Risk ({metrics.step_count} steps):\n")
    click.echo(f"  J_additive:   {metrics.j_additive:.4f}")
    click.echo(f"  J_discounted: {metrics.j_discounted:.4f}")
    click.echo(f"  J_worst:      {metrics.j_worst:.4f}")


# =============================================================================
# Instrument (AG2 Instrumented Execution)
# =============================================================================


@cli.group("instrument")
@click.pass_context
def instrument_cmd(ctx):
    """Instrumented execution — content-addressed runs, claims, and reports."""
    pass


@instrument_cmd.command("run")
@click.option("--actor", type=click.Choice(["human", "agent", "pipeline"]), default="human")
@click.option("--task", default="", help="Task description or ID")
@click.option("--profile", type=click.Choice(["greenfield", "strict", "forensic"]), default="greenfield")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_run(ctx, actor, task, profile, as_json):
    """Start a new instrumented run."""
    from .instrument import InstrumentSystem, Actor, ActorKind, InstrumentProfile

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)

    actor_obj = Actor(kind=ActorKind(actor), id=actor, name=actor)
    manifest, _ = system.start_run(
        actor=actor_obj,
        profile=InstrumentProfile(profile),
        task_id=task,
    )

    if as_json:
        click.echo(json.dumps(manifest.to_dict(), indent=2))
    else:
        click.echo(f"Run started: {manifest.run_id}")
        click.echo(f"Profile: {profile}")
        if task:
            click.echo(f"Task: {task}")


@instrument_cmd.command("status")
@click.option("--run-id", default=None, help="Specific run ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_status(ctx, run_id, as_json):
    """Show instrument status or run details."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    status = system.status(run_id)

    if as_json:
        click.echo(json.dumps(status, indent=2))
        return

    if "error" in status:
        click.echo(f"Error: {status['error']}", err=True)
        ctx.exit(1)
        return

    if run_id:
        click.echo(f"Run: {status['run_id']}")
        click.echo(f"Created: {status['created_at']}")
        finished = status.get('finished_at', '')
        click.echo(f"Finished: {finished or '(in progress)'}")
        click.echo(f"Profile: {status['profile']}")
        click.echo(f"Events: {status['event_count']}")
        click.echo(f"Receipts: {status['receipt_count']}")
        click.echo(f"Claims: {status['claim_count']}")
        integrity = click.style("PASS", fg="green") if status["integrity"] == "pass" else click.style("FAIL", fg="red")
        click.echo(f"Integrity: {integrity}")
        if status.get("issues"):
            for issue in status["issues"]:
                click.echo(f"  - {issue}")
    else:
        click.echo(f"Instrument system: {status['instrument_dir']}")
        click.echo(f"Profile: {status['profile']}")
        click.echo(f"Total runs: {status['total_runs']}")
        if status.get("runs"):
            click.echo("Runs:")
            for rid in status["runs"][-10:]:
                click.echo(f"  {rid}")


@instrument_cmd.command("verify")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_verify(ctx, run_id, as_json):
    """Verify run integrity."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    ok, issues = system.verify_run(run_id)

    if as_json:
        click.echo(json.dumps({"ok": ok, "issues": issues}, indent=2))
    else:
        if ok:
            click.echo(click.style("PASS", fg="green") + f" — run {run_id} integrity verified")
        else:
            click.echo(click.style("FAIL", fg="red") + f" — run {run_id} has issues:")
            for issue in issues:
                click.echo(f"  - {issue}")
            ctx.exit(1)


@instrument_cmd.command("extract-claims")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_extract_claims(ctx, run_id, as_json):
    """Extract claims from a run's events."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    claims = system.extract_claims(run_id)

    if as_json:
        click.echo(json.dumps([c.to_dict() for c in claims], indent=2))
    else:
        click.echo(f"Extracted {len(claims)} claims from run {run_id}:")
        for c in claims:
            click.echo(f"  [{c.modality.value}] {c.type.value}: {c.subject} — {c.predicate}")


@instrument_cmd.command("diff")
@click.option("--left", required=True, help="Left run ID")
@click.option("--right", required=True, help="Right run ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_diff(ctx, left, right, as_json):
    """Cross-run claim diff."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    results = system.diff_runs(left, right)

    if as_json:
        click.echo(json.dumps([r.to_dict() for r in results], indent=2))
    else:
        if not results:
            click.echo("No differences found.")
        else:
            click.echo(f"{len(results)} finding(s):")
            for r in results:
                click.echo(f"  [{r.finding.value}] {r.match_key}: {r.details}")


@instrument_cmd.command("report")
@click.argument("run_id")
@click.option("--diff-with", default=None, help="Run ID to diff against")
@click.option("--json", "as_json", is_flag=True, help="Output JSON (default: markdown)")
@click.pass_context
def instrument_report(ctx, run_id, diff_with, as_json):
    """Generate report for a run."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    report = system.generate_report([run_id], diff_with=diff_with)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        click.echo(report.to_markdown())


@instrument_cmd.command("list")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_list(ctx, as_json):
    """List all runs."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)
    runs = system.run_store.list_runs()

    if as_json:
        items = []
        for rid in runs:
            m = system.run_store.load_manifest(rid)
            if m:
                items.append(m.to_dict())
        click.echo(json.dumps(items, indent=2))
    else:
        if not runs:
            click.echo("No runs found.")
        else:
            click.echo(f"{len(runs)} run(s):")
            for rid in runs:
                m = system.run_store.load_manifest(rid)
                status = "finished" if m and m.finished_at else "in progress"
                profile = m.config.profile.value if m else "?"
                click.echo(f"  {rid}  [{profile}]  {status}")


@instrument_cmd.command("event")
@click.argument("run_id")
@click.argument("kind")
@click.option("--payload", default="{}", help="JSON payload")
@click.pass_context
def instrument_event(ctx, run_id, kind, payload):
    """Append an event to a run (for testing/scripting)."""
    from .instrument import (
        InstrumentSystem, Event, EventKind, Actor, ActorKind, _now_iso,
    )
    import uuid as _uuid

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)

    try:
        event_kind = EventKind(kind)
    except ValueError:
        valid = ", ".join(k.value for k in EventKind)
        click.echo(f"Invalid event kind: {kind}. Valid: {valid}", err=True)
        ctx.exit(1)
        return

    try:
        payload_dict = json.loads(payload)
    except json.JSONDecodeError as e:
        click.echo(f"Invalid JSON payload: {e}", err=True)
        ctx.exit(1)
        return

    run_dir = system.instrument_dir / "runs" / run_id
    if not run_dir.exists():
        click.echo(f"Run not found: {run_id}", err=True)
        ctx.exit(1)
        return

    from .instrument import EventWriter
    writer = EventWriter(
        run_dir, system.artifact_store, system.config.artifact_size_threshold
    )
    event = Event(
        event_id=_uuid.uuid4().hex[:12],
        ts=_now_iso(),
        run_id=run_id,
        kind=event_kind,
        actor=Actor(ActorKind.HUMAN, "cli"),
        payload=payload_dict,
    )
    writer.append_event(event)
    click.echo(f"Event {event.event_id} appended to run {run_id}")


@instrument_cmd.command("store")
@click.argument("file_path", type=click.Path(exists=True))
@click.pass_context
def instrument_store(ctx, file_path):
    """Store a file as a content-addressed artifact."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)

    data = Path(file_path).read_bytes()
    receipt = system.artifact_store.store(data)
    click.echo(f"Stored: {receipt.artifact_hash} ({receipt.size_bytes} bytes)")


@instrument_cmd.command("waiver-create")
@click.option("--rule", required=True, help="Rule ID to waive")
@click.option("--scope", required=True, help="Glob pattern for scope")
@click.option("--reason", required=True, help="Reason for waiver")
@click.option("--expires", default="", help="Expiry duration (e.g. 2h, 1d)")
@click.option("--created-by", default="", help="Who created the waiver")
@click.pass_context
def instrument_waiver_create(ctx, rule, scope, reason, expires, created_by):
    """Create a waiver for a rule."""
    from .instrument import InstrumentSystem, Waiver, _now_iso
    import uuid as _uuid

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)

    expires_iso = ""
    if expires:
        try:
            from .overrides import parse_duration
            delta = parse_duration(expires)
            expires_iso = (datetime.now(timezone.utc) + delta).isoformat()
        except Exception:
            # Try parsing as hours/days manually
            if expires.endswith("h"):
                hours = int(expires[:-1])
                expires_iso = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
            elif expires.endswith("d"):
                days = int(expires[:-1])
                expires_iso = (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()
            else:
                click.echo(f"Invalid expires format: {expires}. Use '2h' or '1d'.", err=True)
                ctx.exit(1)
                return

    waiver = Waiver(
        waiver_id=_uuid.uuid4().hex[:12],
        rule_id=rule,
        scope=scope,
        reason=reason,
        expires=expires_iso,
        created_by=created_by,
    )
    system.waiver_store.create(waiver)
    click.echo(f"Waiver created: {waiver.waiver_id}")
    click.echo(f"  Rule: {rule}")
    click.echo(f"  Scope: {scope}")
    if expires_iso:
        click.echo(f"  Expires: {expires_iso}")


@instrument_cmd.command("waiver-list")
@click.option("--all", "show_all", is_flag=True, help="Show expired waivers too")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def instrument_waiver_list(ctx, show_all, as_json):
    """List waivers."""
    from .instrument import InstrumentSystem

    gov_dir = ensure_initialized(ctx)
    system = InstrumentSystem(gov_dir)

    waivers = system.waiver_store.list_all() if show_all else system.waiver_store.list_active()

    if as_json:
        click.echo(json.dumps([w.to_dict() for w in waivers], indent=2))
    else:
        if not waivers:
            click.echo("No waivers found.")
        else:
            for w in waivers:
                expired = " (EXPIRED)" if w.is_expired else ""
                click.echo(f"  {w.waiver_id}  rule={w.rule_id}  scope={w.scope}{expired}")
                click.echo(f"    Reason: {w.reason}")


# =============================================================================
# Slim Mode (Single-developer governance)
# =============================================================================


@cli.command("decide")
@click.argument("text")
@click.option("--topic", "-t", default=None, help="Decision topic for grouping")
@click.option("--retract", is_flag=True, help="Retract a previous decision")
@click.option("--force", is_flag=True, help="Override contradiction check")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def decide_cmd(ctx, text, topic, retract, force, as_json):
    """Record or retract an architectural decision.

    \b
    Examples:
      governor decide "Authentication uses JWT"
      governor decide "No ORM — raw SQL" --topic database
      governor decide --retract "Authentication uses JWT"
    """
    from .slim_mode import SlimMode, ContradictionError

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)

    if retract:
        result = slim.retract(text, topic)
        if result:
            if as_json:
                click.echo(json.dumps(result.to_dict(), indent=2))
            else:
                click.echo(f"Retracted: {text}")
        else:
            click.echo(f"No matching decision found to retract.", err=True)
            ctx.exit(1)
        return

    try:
        result = slim.decide(text, topic, force=force)
    except ContradictionError as e:
        click.echo(f"ERROR: {e}", err=True)
        click.echo("\nUse --retract to retract the prior decision first, or --force to override.", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        topic_display = f" [topic: {result.topic}]" if result.topic else ""
        click.echo(f"Decided: {result.choice}{topic_display}")


@cli.command("anchor")
@click.argument("description", required=False)
@click.option("--type", "anchor_type", default="canon",
              type=click.Choice(["canon", "prohibition", "requirement", "definition", "style", "persona"]))
@click.option("--severity", default="reject", type=click.Choice(["warn", "correct", "reject"]))
@click.option("--scope", default="", help="File glob pattern for scope")
@click.option("--remove", "remove_id", default=None, help="Remove anchor by ID")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def anchor_cmd(ctx, description, anchor_type, severity, scope, remove_id, as_json):
    """Create or remove a continuity anchor.

    \b
    Examples:
      governor anchor "Elena has green eyes" --type canon
      governor anchor "No eval() calls" --type prohibition --scope "src/**"
      governor anchor --remove elena-has-green-eyes
    """
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)

    if remove_id:
        removed = slim.remove_anchor(remove_id)
        if removed:
            click.echo(f"Removed anchor: {remove_id}")
        else:
            click.echo(f"Anchor not found: {remove_id}", err=True)
            ctx.exit(1)
        return

    if not description:
        # List anchors
        anchors = slim.list_anchors()
        if as_json:
            items = []
            for a in anchors:
                items.append({
                    "id": a.id,
                    "type": a.anchor_type.value,
                    "severity": a.severity.value,
                    "description": a.description,
                })
            click.echo(json.dumps(items, indent=2))
        else:
            if not anchors:
                click.echo("No anchors registered.")
            else:
                for a in anchors:
                    click.echo(f"  [{a.severity.value}] {a.id}: {a.description} (type: {a.anchor_type.value})")
        return

    anchor = slim.add_anchor(description, anchor_type, severity, scope)
    if as_json:
        click.echo(json.dumps({
            "id": anchor.id,
            "type": anchor.anchor_type.value,
            "severity": anchor.severity.value,
            "description": anchor.description,
        }, indent=2))
    else:
        click.echo(f"Anchor created: {anchor.id}")
        click.echo(f"  [{anchor.severity.value}] {anchor.description}")


@cli.command("lock")
@click.argument("path")
@click.option("--description", "-d", default="", help="Lock description")
@click.option("--forbid", multiple=True, help="Forbidden file patterns")
@click.pass_context
def lock_cmd(ctx, path, description, forbid):
    """Lock a directory structure via spine.

    \b
    Examples:
      governor lock src/governor/
      governor lock src/ --forbid "*.secret" --forbid "credentials/*"
    """
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)
    spine = slim.lock(path, description, list(forbid) if forbid else None)
    click.echo(f"Locked: {path} (spine: {spine.id})")


@cli.command("unlock")
@click.argument("path")
@click.option("--confirm", is_flag=True, required=True, help="Confirm unlock")
@click.pass_context
def unlock_cmd(ctx, path, confirm):
    """Unlock a directory structure.

    \b
    Example:
      governor unlock src/governor/ --confirm
    """
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)
    if slim.unlock(path):
        click.echo(f"Unlocked: {path}")
    else:
        click.echo(f"No lock found for: {path}", err=True)
        ctx.exit(1)


@cli.command("must-pass")
@click.argument("command")
@click.pass_context
def must_pass_cmd(ctx, command):
    """Register a test command that must pass.

    \b
    Example:
      governor must-pass "python3 -m pytest tests/ -x"
    """
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)
    spec = slim.must_pass(command)
    click.echo(f"Invariant registered: {spec.id}")
    click.echo(f"  [test] {command}")


@cli.command("must-exist")
@click.argument("filepath")
@click.pass_context
def must_exist_cmd(ctx, filepath):
    """Register a file that must exist.

    \b
    Example:
      governor must-exist src/governor/__init__.py
    """
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)
    spec = slim.must_exist(filepath)
    click.echo(f"Invariant registered: {spec.id}")
    click.echo(f"  [file-exists] {filepath}")


@cli.group("slim")
@click.pass_context
def slim_cmd(ctx):
    """Slim mode — single-developer governance."""
    pass


@slim_cmd.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--oneliner", is_flag=True, help="Compact one-liner for system prompts")
@click.pass_context
def slim_status(ctx, as_json, oneliner):
    """Show slim mode status (one-screen view)."""
    from .slim_mode import SlimMode

    gov_dir = ensure_initialized(ctx)
    slim = SlimMode(gov_dir)
    status = slim.status()

    if as_json:
        click.echo(json.dumps(status.to_dict(), indent=2))
        return

    if oneliner:
        click.echo(status.to_oneliner())
        return

    # Full one-screen view
    click.echo(f"Envelope: {status.envelope} (single-developer)\n")

    if status.decisions:
        click.echo(f"Decisions ({len(status.decisions)}):")
        for d in status.decisions:
            topic_str = f" [topic: {d['topic']}]" if d.get("topic") else ""
            click.echo(f"  * {d['choice']}{topic_str}")
    else:
        click.echo("Decisions: (none)")

    click.echo()

    if status.anchors:
        click.echo(f"Anchors ({len(status.anchors)}):")
        for a in status.anchors:
            click.echo(f"  * [{a['severity']}] {a['description']} (type: {a['type']})")
    else:
        click.echo("Anchors: (none)")

    click.echo()

    if status.invariants:
        click.echo(f"Invariants ({len(status.invariants)}):")
        for i in status.invariants:
            param_str = i.get("params", {}).get("command") or i.get("params", {}).get("path", "")
            click.echo(f"  * [{i['kind']}] {param_str}")
    else:
        click.echo("Invariants: (none)")

    click.echo()

    if status.spine_locked:
        click.echo(f"Spine: {', '.join(status.spine_locked)} (locked)")
    else:
        click.echo("Spine: (no locks)")

    if status.last_check:
        click.echo(f"\nLast check: {status.last_check}")


# ---------------------------------------------------------------------------
# Constraint Compiler (AG2 Layer 1, Item #3)
# ---------------------------------------------------------------------------


@cli.group("constraints")
def constraints_group() -> None:
    """Pre-execution constraint projection.

    Resolve all applicable constraints for intent + scope into a portable
    block that any executor LLM can consume as a prompt prefix.
    """


@constraints_group.command("resolve")
@click.option("--intent", "-i", default=None, help="User-declared intent (production, hotfix, etc.)")
@click.option("--scope", "-s", default=None, help="File/directory scope (glob pattern)")
@click.option("--mode", "-m", default=None, help="Domain mode (code, fiction, nonfiction, ops)")
@click.option("--format", "fmt", type=click.Choice(["prompt", "json", "summary"]), default="prompt", help="Output format")
@click.option("--no-cache", is_flag=True, help="Skip the in-memory cache")
@click.pass_context
def constraints_resolve(ctx: click.Context, intent: str | None, scope: str | None, mode: str | None, fmt: str, no_cache: bool) -> None:
    """Resolve all constraints for intent + scope."""
    from .constraint_compiler import compile_constraints
    import json as _json

    gov_dir = ctx.obj["gov_dir"]
    block = compile_constraints(
        intent=intent,
        scope=scope,
        mode=mode,
        governor_dir=gov_dir,
        use_cache=not no_cache,
    )

    if fmt == "json":
        click.echo(_json.dumps(block.to_dict(), indent=2, default=str))
    elif fmt == "summary":
        click.echo(block.to_summary())
    else:
        click.echo(block.prompt_prefix)


@constraints_group.command("diff")
@click.option("--scope", "-s", default=None, help="File/directory scope (glob pattern)")
@click.option("--intent", "-i", default=None, help="User-declared intent")
@click.option("--mode", "-m", default=None, help="Domain mode")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def constraints_diff(ctx: click.Context, scope: str | None, intent: str | None, mode: str | None, as_json: bool) -> None:
    """Diff current constraints against last cached compilation."""
    from .constraint_compiler import compile_constraints, diff_constraints, get_cache
    import json as _json

    gov_dir = ctx.obj["gov_dir"]

    # Get cached version (if any)
    old_block = None
    cache = get_cache()
    # Compile fresh
    new_block = compile_constraints(
        intent=intent, scope=scope, mode=mode,
        governor_dir=gov_dir, use_cache=False,
    )

    if old_block is None:
        # No previous compilation — show current as "all new"
        if as_json:
            click.echo(_json.dumps({
                "status": "no_previous",
                "current": new_block.to_dict(),
            }, indent=2, default=str))
        else:
            click.echo("No previous compilation found. Current constraints:")
            click.echo(new_block.to_summary())
        return

    diff = diff_constraints(old_block, new_block)

    if as_json:
        click.echo(_json.dumps(diff.to_dict(), indent=2, default=str))
    else:
        if not diff.has_changes:
            click.echo("No changes since last compilation.")
        else:
            if diff.added:
                click.echo(f"Added ({len(diff.added)}):")
                for c in diff.added:
                    click.echo(f"  + [{c.severity.value}] {c.description}")
            if diff.removed:
                click.echo(f"Removed ({len(diff.removed)}):")
                for c in diff.removed:
                    click.echo(f"  - [{c.severity.value}] {c.description}")
            if diff.changed:
                click.echo(f"Changed ({len(diff.changed)}):")
                for before, after in diff.changed:
                    click.echo(f"  ~ {before.description}: {before.severity.value} → {after.severity.value}")


# ---------------------------------------------------------------------------
# Detector Integration (AG2 Layer 1, Item #4)
# ---------------------------------------------------------------------------


@cli.group("detector")
def detector_group() -> None:
    """Temporal coherence detector integration.

    Sensor/controller boundary for external hallucination detector signals.
    Collapses 19 raw dimensions into 5 control signals, maps to governor actions.
    """


@detector_group.command("evaluate")
@click.argument("signal_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def detector_evaluate(ctx: click.Context, signal_file: str, as_json: bool) -> None:
    """Evaluate a detector signal file and show recommended actions."""
    from .detector_integration import DetectorIntegration
    import json as _json

    di = DetectorIntegration()
    result = di.process_file(Path(signal_file))

    if as_json:
        click.echo(_json.dumps(result.to_dict(), indent=2, default=str))
    else:
        click.echo(f"Signal quality: {result.signal_quality.value}")
        click.echo(f"Actions: {', '.join(a.value for a in result.actions)}")
        if result.confidence_cap is not None:
            click.echo(f"Confidence cap: {result.confidence_cap}")
        if result.evidence_tier:
            click.echo(f"Evidence tier: {result.evidence_tier}")
        click.echo(f"Reason: {result.reason}")


@detector_group.command("collapse")
@click.argument("signal_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def detector_collapse(signal_file: str, as_json: bool) -> None:
    """Collapse raw signal to 5 control dimensions."""
    from .detector_integration import DetectorIntegration
    import json as _json

    di = DetectorIntegration()
    collapsed, key, file_hash = di.load_and_collapse(Path(signal_file))

    if as_json:
        click.echo(_json.dumps({
            "collapsed": collapsed.to_dict(),
            "key": key.to_dict(),
            "file_hash": file_hash,
            "quality": collapsed.quality.value,
        }, indent=2, default=str))
    else:
        click.echo(f"Quality: {collapsed.quality.value}")
        click.echo(f"Coherence score: {collapsed.coherence_score}")
        click.echo(f"Instability spikes: {collapsed.instability_spikes}")
        click.echo(f"Perturbation fragility: {collapsed.perturbation_fragility}")
        click.echo(f"Overconfidence signature: {collapsed.overconfidence_signature}")
        click.echo(f"Phase flag: {collapsed.phase_flag.value}")


@detector_group.command("constraints")
@click.argument("signal_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def detector_constraints(signal_file: str, as_json: bool) -> None:
    """Show constraints produced by a detector signal."""
    from .detector_integration import DetectorIntegration
    import json as _json

    di = DetectorIntegration()
    collapsed, _, _ = di.load_and_collapse(Path(signal_file))
    constraints = di.get_constraints(collapsed)

    if as_json:
        click.echo(_json.dumps(constraints, indent=2, default=str))
    else:
        if not constraints:
            click.echo("No constraints (signal is clean).")
        else:
            for c in constraints:
                click.echo(f"  [{c['severity']}] {c['description']}")


@detector_group.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def detector_status(as_json: bool) -> None:
    """Show detector integration status and policy."""
    from .detector_integration import DetectorIntegration
    import json as _json

    di = DetectorIntegration()
    status = di.status()

    if as_json:
        click.echo(_json.dumps(status, indent=2, default=str))
    else:
        click.echo("Detector Integration Status")
        p = status["policy"]
        click.echo(f"  Coherence threshold: {p['coherence_threshold']}")
        click.echo(f"  Spike threshold: {p['spike_threshold']}")
        click.echo(f"  Fragility threshold: {p['fragility_threshold']}")
        click.echo(f"  Overconfidence threshold: {p['overconfidence_threshold']}")
        click.echo(f"  Confab blocks writes: {p['confab_blocks_writes']}")
        click.echo(f"  Unavailable penalty: {p['unavailable_penalty']}")
        fs = status["failure_safe_signal"]
        click.echo(f"  Failure-safe quality: {fs['quality']}")


@detector_group.command("failure-safe")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def detector_failure_safe(as_json: bool) -> None:
    """Show what happens when the detector is unavailable."""
    from .detector_integration import DetectorIntegration
    import json as _json

    di = DetectorIntegration()
    safe = di.failure_safe()
    result = di.evaluate(safe)

    if as_json:
        click.echo(_json.dumps({
            "signal": safe.to_dict(),
            "quality": safe.quality.value,
            "actions": result.to_dict(),
        }, indent=2, default=str))
    else:
        click.echo("Failure-safe signal (detector unavailable):")
        click.echo(f"  Coherence score: {safe.coherence_score}")
        click.echo(f"  Overconfidence: {safe.overconfidence_signature}")
        click.echo(f"  Quality: {safe.quality.value}")
        click.echo(f"  Actions: {', '.join(a.value for a in result.actions)}")


# ---------------------------------------------------------------------------
# Commitment Transport (AG2 Layer 2, Item #5)
# ---------------------------------------------------------------------------


@cli.group("transport")
def transport_group() -> None:
    """Commitment transport validation.

    Checks that obligations (MUST/SHOULD/MAY/MUST_NOT) survive lossy transforms
    like compaction, summarization, and bridge compilation.
    """


@transport_group.command("check")
@click.option("--before", "-b", "before_file", required=True, type=click.Path(exists=True), help="File with original text")
@click.option("--after", "-a", "after_file", required=True, type=click.Path(exists=True), help="File with transformed text")
@click.option("--type", "transform_type", default="", help="Transform type label")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def transport_check(ctx: click.Context, before_file: str, after_file: str, transform_type: str, as_json: bool) -> None:
    """Check commitment transport between two text files."""
    from .commitment_transport import check_transport, TransportHistory
    import json as _json

    before_text = Path(before_file).read_text()
    after_text = Path(after_file).read_text()
    report = check_transport(before_text, after_text, transform_type)

    gov_dir = ctx.obj.get("gov_dir")
    if gov_dir:
        history = TransportHistory(gov_dir)
        history.save_report(report)

    if as_json:
        click.echo(_json.dumps(report.to_dict(), indent=2, default=str))
    else:
        click.echo(report.to_summary())


@transport_group.command("extract")
@click.argument("text_file", type=click.Path(exists=True))
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def transport_extract(text_file: str, as_json: bool) -> None:
    """Extract commitments from a text file."""
    from .commitment_transport import extract_commitments
    import json as _json

    text = Path(text_file).read_text()
    commitments = extract_commitments(text)

    if as_json:
        click.echo(_json.dumps([c.to_dict() for c in commitments], indent=2, default=str))
    else:
        if not commitments:
            click.echo("No commitments found.")
        else:
            click.echo(f"Found {len(commitments)} commitments:")
            for c in commitments:
                click.echo(f"  [{c.modality.value}] [{c.kind.value}] {c.text[:80]}")
                if c.scope:
                    click.echo(f"    scope: {c.scope}")


@transport_group.command("history")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def transport_history(ctx: click.Context, as_json: bool) -> None:
    """Show transport validation history."""
    from .commitment_transport import TransportHistory
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    if not gov_dir:
        click.echo("No governor directory found.")
        return

    history = TransportHistory(gov_dir)
    reports = history.list_reports()

    if as_json:
        click.echo(_json.dumps(reports, indent=2, default=str))
    else:
        if not reports:
            click.echo("No transport reports.")
        else:
            for r in reports:
                blocking = " BLOCKING" if r["blocking"] else ""
                click.echo(
                    f"  {r['report_id']}  shear={r['shear_score']:.4f}  "
                    f"type={r['transform_type']}{blocking}"
                )


@transport_group.command("stats")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def transport_stats(ctx: click.Context, as_json: bool) -> None:
    """Show aggregate shear statistics."""
    from .commitment_transport import TransportHistory
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    if not gov_dir:
        click.echo("No governor directory found.")
        return

    history = TransportHistory(gov_dir)
    stats = history.stats()

    if as_json:
        click.echo(_json.dumps(stats, indent=2, default=str))
    else:
        click.echo(f"Total reports: {stats['total_reports']}")
        click.echo(f"Average shear: {stats['avg_shear']:.4f}")
        click.echo(f"Max shear: {stats['max_shear']:.4f}")
        click.echo(f"Blocking count: {stats['blocking_count']}")


# ---------------------------------------------------------------------------
# Spectral Stability (AG2 Layer 2, Item #6)
# ---------------------------------------------------------------------------


@cli.group("stability")
def stability_group() -> None:
    """Spectral stability gate for governance topology.

    Computes ρ(M) from the governance hierarchy's coupling matrix.
    Hard blocks when ρ(M) ≥ 1 — unstable by construction, no override.
    """


@stability_group.command("check")
@click.option("--profile", "-p", default=None, help="Governance profile to check")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def stability_check(ctx: click.Context, profile: str | None, as_json: bool) -> None:
    """Preflight stability check on governance topology."""
    from .spectral_stability import StabilityGate
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    gate = StabilityGate(profile=profile, governor_dir=gov_dir)
    report = gate.check()

    if as_json:
        click.echo(_json.dumps(report.to_dict(), indent=2, default=str))
    else:
        click.echo(report.to_summary())


@stability_group.command("matrix")
@click.option("--profile", "-p", default=None, help="Governance profile")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stability_matrix(profile: str | None, as_json: bool) -> None:
    """Show the coupling matrix details."""
    from .spectral_stability import compute_stability
    import json as _json

    report = compute_stability(profile=profile)
    coupling = report.coupling

    if as_json:
        click.echo(_json.dumps(coupling.to_dict(), indent=2, default=str))
    else:
        click.echo(f"ρ(M) = {coupling.spectral_radius:.4f}")
        click.echo(f"\nLayers: {', '.join(l.name for l in coupling.layers)}")
        click.echo("\nCoupling Matrix M:")
        n = len(coupling.layers)
        header = "           " + "  ".join(f"{l.name[:8]:>8}" for l in coupling.layers)
        click.echo(header)
        for i in range(n):
            row = f"{coupling.layers[i].name[:10]:<10} " + "  ".join(
                f"{coupling.matrix[i][j]:8.4f}" for j in range(n)
            )
            click.echo(row)


@stability_group.command("hotspots")
@click.option("--profile", "-p", default=None, help="Governance profile")
@click.option("--top", "-n", "top_n", default=3, help="Number of hotspots")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stability_hotspots(profile: str | None, top_n: int, as_json: bool) -> None:
    """Show coupling hotspots and recommendations."""
    from .spectral_stability import compute_stability
    import json as _json

    report = compute_stability(profile=profile)

    if as_json:
        click.echo(_json.dumps({
            "hotspots": [h.to_dict() for h in report.hotspots[:top_n]],
            "recommendations": report.recommendations,
        }, indent=2, default=str))
    else:
        if not report.hotspots:
            click.echo("No coupling hotspots detected.")
        else:
            click.echo("Coupling Hotspots:")
            for h in report.hotspots[:top_n]:
                click.echo(f"  {h.from_layer} → {h.to_layer}")
                click.echo(f"    Strength: {h.strength:.4f}, Sensitivity: {h.sensitivity:.4f}")
                click.echo(f"    Mitigation: {h.mitigation}")
        if report.recommendations:
            click.echo("\nRecommendations:")
            for r in report.recommendations:
                click.echo(f"  - {r}")


@stability_group.command("region")
@click.option("--profile", "-p", default=None, help="Governance profile")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def stability_region(profile: str | None, as_json: bool) -> None:
    """Show kinetic region classification."""
    from .spectral_stability import compute_stability
    import json as _json

    report = compute_stability(profile=profile)

    if as_json:
        click.echo(_json.dumps({
            "region": report.region.value,
            "spectral_radius": report.spectral_radius,
            "margin": report.margin,
            "verdict": report.verdict.value,
            "stable": report.stable,
        }, indent=2, default=str))
    else:
        click.echo(f"Region: {report.region.value}")
        click.echo(f"ρ(M) = {report.spectral_radius:.4f}")
        click.echo(f"Margin: {report.margin:.4f}")
        click.echo(f"Verdict: {report.verdict.value}")
        click.echo(f"Stable: {report.stable}")


# ---------------------------------------------------------------------------
# Scalar Collapse Detection (AG2 Layer 2, Item #7)
# ---------------------------------------------------------------------------


@cli.group("collapse")
def collapse_group() -> None:
    """Scalar collapse detection.

    Monitors the effective dimensionality of the governance decision space.
    Detects eigenstructure evaporation where metrics converge to scalar behavior.
    """


@collapse_group.command("status")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def collapse_status(ctx: click.Context, as_json: bool) -> None:
    """Show current collapse detection status."""
    from .scalar_collapse import CollapseDetector
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    detector = CollapseDetector(governor_dir=gov_dir)
    status = detector.status()

    if as_json:
        click.echo(_json.dumps(status, indent=2, default=str))
    else:
        click.echo(f"Sample count: {status['sample_count']}")
        click.echo(f"Min samples needed: {status['min_samples']}")
        click.echo(f"Sufficient data: {status['has_sufficient_data']}")
        click.echo(f"Tracked metrics: {', '.join(status['metric_names'])}")
        if "last_risk_score" in status:
            click.echo(f"Last risk score: {status['last_risk_score']:.4f}")
            click.echo(f"Last risk level: {status['last_risk_level']}")


@collapse_group.command("analyze")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def collapse_analyze(ctx: click.Context, as_json: bool) -> None:
    """Analyze governance metrics for collapse risk (requires telemetry data)."""
    from .scalar_collapse import detect_collapse, MetricSample
    import json as _json

    # Check for telemetry data
    gov_dir = ctx.obj.get("gov_dir")
    report = detect_collapse([])  # No live data without telemetry

    if as_json:
        click.echo(_json.dumps(report.to_dict(), indent=2, default=str))
    else:
        click.echo(report.to_summary())


@collapse_group.command("history")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def collapse_history(ctx: click.Context, as_json: bool) -> None:
    """Show collapse detection history."""
    from .scalar_collapse import CollapseHistory
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    if not gov_dir:
        click.echo("No governor directory found.")
        return

    history = CollapseHistory(gov_dir)
    reports = history.list_reports()

    if as_json:
        click.echo(_json.dumps(reports, indent=2, default=str))
    else:
        if not reports:
            click.echo("No collapse reports.")
        else:
            for r in reports:
                irr = " IRREVERSIBLE" if r.get("irreversible") else ""
                click.echo(
                    f"  {r['report_id']}  risk={r['risk_score']:.4f}  "
                    f"level={r['risk_level']}  action={r['action']}{irr}"
                )


@collapse_group.command("modes")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def collapse_modes(ctx: click.Context, as_json: bool) -> None:
    """Show suppressed modes from last collapse check."""
    from .scalar_collapse import CollapseHistory
    import json as _json

    gov_dir = ctx.obj.get("gov_dir")
    if not gov_dir:
        click.echo("No governor directory found.")
        return

    history = CollapseHistory(gov_dir)
    reports = history.list_reports()
    if not reports:
        click.echo("No collapse reports. Run 'governor collapse analyze' first.")
        return

    latest = history.load_report(reports[0]["report_id"])
    if latest is None:
        click.echo("Could not load latest report.")
        return

    if as_json:
        click.echo(_json.dumps({
            "dominant_metric": latest.dominant_metric,
            "suppressed_modes": latest.suppressed_modes,
            "effective_dimension": latest.signals.effective_dimension,
            "max_dimension": latest.signals.max_dimension,
        }, indent=2, default=str))
    else:
        if latest.dominant_metric:
            click.echo(f"Dominant metric: {latest.dominant_metric}")
        else:
            click.echo("No dominant metric detected.")
        if latest.suppressed_modes:
            click.echo(f"Suppressed modes: {', '.join(latest.suppressed_modes)}")
        else:
            click.echo("No suppressed modes detected.")
        click.echo(f"Effective dimension: {latest.signals.effective_dimension:.1f}/{latest.signals.max_dimension}")


# ---------------------------------------------------------------------------
# Dashboard UX (AG2 Layer 4, Item #11)
# ---------------------------------------------------------------------------


@cli.group("dashboard-ux")
def dashboard_ux_group() -> None:
    """Run-centric governance dashboard backend."""
    pass


@dashboard_ux_group.command("summary")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def dashboard_ux_summary(ctx: click.Context, as_json: bool) -> None:
    """Show aggregate dashboard statistics."""
    from .dashboard_ux import DashboardStore

    store = DashboardStore()
    summary = store.dashboard_summary()

    if as_json:
        click.echo(json.dumps(summary.to_dict(), indent=2))
    else:
        click.echo(f"Total runs: {summary.total_runs}")
        click.echo(f"  Passed: {summary.passed}")
        click.echo(f"  Failed: {summary.failed}")
        click.echo(f"  Cancelled: {summary.cancelled}")
        click.echo(f"  Pass rate: {summary.pass_rate:.1%}")
        click.echo(f"  Total claims: {summary.total_claims}")
        click.echo(f"  Total violations: {summary.total_violations}")


@dashboard_ux_group.command("runs")
@click.option("--profile", default="", help="Filter by profile")
@click.option("--verdict", default="", help="Filter by verdict")
@click.option("--limit", default=20, help="Max runs to show")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def dashboard_ux_runs(ctx: click.Context, profile: str, verdict: str, limit: int, as_json: bool) -> None:
    """List run summaries."""
    from .dashboard_ux import DashboardStore

    store = DashboardStore()
    runs = store.list_runs(profile=profile, verdict=verdict, limit=limit)

    if as_json:
        click.echo(json.dumps([r.to_dict() for r in runs], indent=2))
    else:
        if not runs:
            click.echo("No runs recorded.")
            return
        for r in runs:
            click.echo(f"  {r.run_id:<14} {r.created_at[:10]:<12} "
                        f"{r.model:<16} {r.profile:<12} "
                        f"{r.verdict.value.upper():<10} "
                        f"{r.claim_count} claims  {r.violation_count} violations")


@dashboard_ux_group.command("report")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output (default: markdown)")
@click.pass_context
def dashboard_ux_report(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Generate report for a run."""
    from .dashboard_ux import DashboardStore, generate_report

    store = DashboardStore()
    run = store.get_run(run_id)
    if not run:
        click.echo(f"Run not found: {run_id}", err=True)
        ctx.exit(1)
        return

    report = generate_report(
        run_id,
        manifest={"profile": run.profile, "model": run.model},
    )
    store.save_report(report)

    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        click.echo(report.to_markdown())


@dashboard_ux_group.command("templates")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def dashboard_ux_templates(ctx: click.Context, as_json: bool) -> None:
    """List available run templates."""
    from .dashboard_ux import BUILTIN_TEMPLATES

    if as_json:
        click.echo(json.dumps([t.to_dict() for t in BUILTIN_TEMPLATES], indent=2))
    else:
        for t in BUILTIN_TEMPLATES:
            click.echo(f"  {t.name:<20} {t.description}")
            click.echo(f"    Task: {t.example_task}")
            click.echo(f"    Expected: {t.expected_outcome}")
            click.echo()


@dashboard_ux_group.command("schema")
@click.pass_context
def dashboard_ux_schema(ctx: click.Context) -> None:
    """Show controls schema (JSON Schema + render hints)."""
    from .dashboard_ux import build_controls_schema

    click.echo(json.dumps(build_controls_schema(), indent=2))


# ---------------------------------------------------------------------------
# Document Governance (AG2 Layer 4, Item #10)
# ---------------------------------------------------------------------------


@cli.group("doc")
def doc_group() -> None:
    """Document governance — docs as governed artifacts."""
    pass


@doc_group.command("register")
@click.argument("path")
@click.option("--scope", required=True, type=click.Choice(["descriptive", "procedural", "authoritative"]))
@click.option("--link", "-l", multiple=True, help="Link as kind:target (e.g., code:src/auth/)")
@click.option("--ttl", type=int, default=None, help="TTL in days")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_register(ctx: click.Context, path: str, scope: str, link: tuple, ttl: int | None, as_json: bool) -> None:
    """Register a document for governance."""
    from .doc_governance import DocGovernor, DocLink, LinkKind

    links = []
    for l_spec in link:
        if ":" in l_spec:
            kind_str, target = l_spec.split(":", 1)
            try:
                kind = LinkKind(kind_str)
            except ValueError:
                click.echo(f"Unknown link kind: {kind_str}. Valid: {[k.value for k in LinkKind]}", err=True)
                ctx.exit(1)
                return
            links.append(DocLink(kind=kind, target=target))

    gov = DocGovernor()
    doc = gov.register(path, scope, links=links, ttl_days=ttl)

    if as_json:
        click.echo(json.dumps(doc.to_dict(), indent=2))
    else:
        click.echo(f"Registered: {path} [{scope}] (id: {doc.doc_id})")
        if links:
            click.echo(f"  Links: {len(links)}")
        if ttl:
            click.echo(f"  TTL: {ttl}d")


@doc_group.command("unregister")
@click.argument("path")
@click.pass_context
def doc_unregister(ctx: click.Context, path: str) -> None:
    """Unregister a document from governance."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    if gov.unregister(path):
        click.echo(f"Unregistered: {path}")
    else:
        click.echo(f"Not found: {path}", err=True)
        ctx.exit(1)


@doc_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_list(ctx: click.Context, as_json: bool) -> None:
    """List registered governed documents."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    docs = gov.list_docs()

    if as_json:
        click.echo(json.dumps([d.to_dict() for d in docs], indent=2))
    else:
        if not docs:
            click.echo("No governed documents registered.")
            return
        for doc in docs:
            status = doc.status.value.upper()
            click.echo(f"  {doc.path:<40} [{doc.scope.value}] {status}")


@doc_group.command("check")
@click.argument("path", required=False)
@click.option("--all", "check_all", is_flag=True, help="Check all registered docs")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_check(ctx: click.Context, path: str | None, check_all: bool, as_json: bool) -> None:
    """Check a document against governance rules."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()

    if check_all:
        results = gov.check_all()
        if as_json:
            click.echo(json.dumps([r.to_dict() for r in results], indent=2))
        else:
            for r in results:
                status = "PASS" if r.passed else "FAIL"
                click.echo(f"  {r.path:<40} [{r.scope}] {status} ({len(r.findings)} findings)")
        return

    if not path:
        click.echo("Provide a path or use --all.", err=True)
        ctx.exit(1)
        return

    result = gov.check(path)
    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        status = "PASS" if result.passed else "FAIL"
        click.echo(f"{result.path} [{result.scope}]: {status}")
        for f in result.findings:
            line = f"L{f.line_number} " if f.line_number else ""
            click.echo(f"  [{f.severity.value}] {line}{f.message}")
        if not result.findings:
            click.echo("  No issues found.")


@doc_group.command("status")
@click.argument("path", required=False)
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_status(ctx: click.Context, path: str | None, as_json: bool) -> None:
    """Show governance status for documents."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()

    if path:
        result = gov.check(path)
        if as_json:
            click.echo(json.dumps(result.to_dict(), indent=2))
        else:
            click.echo(f"{result.path} [{result.scope}]: {result.status}")
            click.echo(f"  Authority claims: {result.authority_claims} "
                        f"(grounded: {result.grounded_claims}, ungrounded: {result.ungrounded_claims})")
            click.echo(f"  Links: {result.links_valid} valid, {result.links_broken} broken")
        return

    report = gov.status()
    if as_json:
        click.echo(json.dumps(report.to_dict(), indent=2))
    else:
        click.echo(f"Governed documents: {report.total}")
        click.echo(f"  Current: {report.current}")
        click.echo(f"  Stale: {report.stale}")
        click.echo(f"  Historical: {report.historical}")
        click.echo(f"  Unsafe: {report.unsafe}")


@doc_group.command("stale")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_stale(ctx: click.Context, as_json: bool) -> None:
    """List stale and unsafe documents."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    stale = gov.stale_docs()

    if as_json:
        click.echo(json.dumps([d.to_dict() for d in stale], indent=2))
    else:
        if not stale:
            click.echo("No stale or unsafe documents.")
            return
        for doc in stale:
            click.echo(f"  {doc.path:<40} [{doc.status.value}] TTL: {doc.ttl_days or 'none'}d")


@doc_group.command("verify")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_verify(ctx: click.Context, path: str, as_json: bool) -> None:
    """Verify a document and produce a receipt."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    receipt = gov.verify(path)

    if not receipt:
        click.echo(f"Not found: {path}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(receipt.to_dict(), indent=2))
    else:
        click.echo(f"Verified: {path}")
        click.echo(f"  Status: {receipt.status}")
        click.echo(f"  Authority claims: {receipt.authority_claims}")
        click.echo(f"  Links: {receipt.links_valid} valid, {receipt.links_broken} broken")
        click.echo(f"  Hash: {receipt.content_hash}")


@doc_group.command("demote")
@click.argument("path")
@click.pass_context
def doc_demote(ctx: click.Context, path: str) -> None:
    """Demote a document to HISTORICAL status."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    if gov.demote(path):
        click.echo(f"Demoted: {path} → HISTORICAL")
    else:
        click.echo(f"Not found: {path}", err=True)
        ctx.exit(1)


@doc_group.command("promote")
@click.argument("path")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def doc_promote(ctx: click.Context, path: str, as_json: bool) -> None:
    """Promote a HISTORICAL document back to CURRENT (requires re-check)."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    result = gov.promote(path)

    if not result:
        click.echo(f"Not found: {path}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        if result.passed:
            click.echo(f"Promoted: {path} → CURRENT")
        else:
            click.echo(f"Cannot promote: {path} has {len(result.findings)} issues")
            for f in result.findings[:3]:
                click.echo(f"  [{f.severity.value}] {f.message}")


@doc_group.command("export")
@click.argument("path")
@click.option("--format", "fmt", default="obsidian", type=click.Choice(["obsidian", "json"]))
@click.pass_context
def doc_export(ctx: click.Context, path: str, fmt: str) -> None:
    """Export governance metadata for a document."""
    from .doc_governance import DocGovernor

    gov = DocGovernor()
    result = gov.export_doc(path, fmt)

    if not result:
        click.echo(f"Not found: {path}", err=True)
        ctx.exit(1)
        return

    click.echo(result)


# ---------------------------------------------------------------------------
# CLI Chat (AG2 Layer 3, Item #8)
# ---------------------------------------------------------------------------


@cli.group("backend")
def backend_group() -> None:
    """Backend management for governed chat."""
    pass


@backend_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def backend_list(ctx: click.Context, as_json: bool) -> None:
    """List available backends and their status."""
    from .cli_chat import probe_backends

    backends = probe_backends()
    if as_json:
        click.echo(json.dumps([b.to_dict() for b in backends], indent=2))
    else:
        for b in backends:
            status = "available" if b.available else "not available"
            reason = f" ({b.reason})" if b.reason else ""
            models = f", {len(b.models)} models" if b.models else ""
            click.echo(f"  {b.name:<14} {status}{reason}{models}")


@backend_group.command("switch")
@click.argument("name")
@click.option("--model", default="", help="Default model for this backend")
@click.pass_context
def backend_switch(ctx: click.Context, name: str, model: str) -> None:
    """Switch active backend."""
    from .cli_chat import ChatConfig, KNOWN_BACKENDS, probe_backend

    if name not in KNOWN_BACKENDS:
        click.echo(f"Unknown backend: {name}. Known: {', '.join(KNOWN_BACKENDS)}", err=True)
        ctx.exit(1)
        return

    info = probe_backend(name)
    if not info.available:
        click.echo(f"Warning: {name} is not available ({info.reason})", err=True)

    config = ChatConfig.load()
    config.active_backend = name
    if model:
        config.active_model = model
    config.save()
    click.echo(f"Active backend: {name}" + (f" ({model})" if model else ""))


@backend_group.command("status")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def backend_status(ctx: click.Context, as_json: bool) -> None:
    """Show active backend."""
    from .cli_chat import ChatConfig, probe_backend

    config = ChatConfig.load()
    info = probe_backend(config.active_backend)

    if as_json:
        click.echo(json.dumps({
            "active_backend": config.active_backend,
            "active_model": config.active_model,
            "available": info.available,
            "reason": info.reason,
        }, indent=2))
    else:
        status = "available" if info.available else "NOT available"
        model_str = config.active_model or info.default_model or "(default)"
        click.echo(f"Active: {config.active_backend} ({model_str}) — {status}")


@backend_group.command("models")
@click.pass_context
def backend_models(ctx: click.Context) -> None:
    """List models for active backend."""
    from .cli_chat import ChatConfig, probe_backend

    config = ChatConfig.load()
    info = probe_backend(config.active_backend)
    if not info.available:
        click.echo(f"{config.active_backend} is not available: {info.reason}", err=True)
        ctx.exit(1)
        return

    if info.models:
        for m in info.models:
            click.echo(f"  {m}")
    else:
        click.echo(f"  (model discovery not supported for {config.active_backend})")
        if info.default_model:
            click.echo(f"  Default: {info.default_model}")


@cli.command("chat")
@click.argument("prompt", required=False, default="")
@click.option("--backend", default="", help="Backend to use (overrides config)")
@click.option("--model", default="", help="Model to use (overrides config)")
@click.option("--scope", default="", help="File scope for constraint projection")
@click.option("--mode", default="code", help="Governor mode (code/fiction/nonfiction/general)")
@click.option("--stdin", "use_stdin", is_flag=True, help="Read prompt from stdin")
@click.option("--no-hooks", is_flag=True, help="Disable governor hooks")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json"]))
@click.option("--compare", default="", help="Compare backends (e.g., ollama:llama3,anthropic:claude-3)")
@click.pass_context
def chat_command(
    ctx: click.Context, prompt: str, backend: str, model: str,
    scope: str, mode: str, use_stdin: bool, no_hooks: bool,
    fmt: str, compare: str,
) -> None:
    """Governed single-turn chat with active backend.

    \b
    Examples:
      governor chat "Refactor the auth module"
      governor chat "Explain this" --backend ollama --model llama3
      echo "What does this do?" | governor chat --stdin
      governor chat "Add validation" --compare ollama:llama3,anthropic:claude-3
    """
    import sys as _sys

    from .cli_chat import (
        format_compare,
        format_response,
        parse_backend_list as parse_bl,
        run_chat,
        run_compare,
    )

    # Resolve prompt
    if use_stdin:
        prompt = _sys.stdin.read().strip()
    if not prompt:
        click.echo("No prompt provided. Use an argument or --stdin.", err=True)
        ctx.exit(1)
        return

    # Compare mode
    if compare:
        backends = parse_bl(compare)
        if len(backends) < 2:
            click.echo("--compare requires at least 2 backends.", err=True)
            ctx.exit(1)
            return
        try:
            result = run_compare(prompt, backends, scope=scope, mode=mode)
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            ctx.exit(1)
            return

        if fmt == "json":
            click.echo(json.dumps(result.to_dict(), indent=2))
        else:
            click.echo(format_compare(result))
        return

    # Single backend chat
    try:
        result = run_chat(
            prompt, backend=backend, model=model,
            scope=scope, mode=mode, use_hooks=not no_hooks,
        )
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        ctx.exit(1)
        return

    if fmt == "json":
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(format_response(result))

    if not result.passed:
        ctx.exit(1)


# Advanced command group - pointer to existing commands
@cli.group(invoke_without_command=True)
@click.pass_context
def advanced(ctx: click.Context) -> None:
    """Power user commands (50+).

    These are the full set of governor commands for advanced use cases.
    Most users won't need them - they're also available at the top level.

    \b
    Categories:
      Continuity:    continuity, lite, docket, rule, precedent, claim
      Epistemic:     epistemic, regime, jurisdiction, drift, signals
      Multi-agent:   agent, task, quorum, independence
      Automation:    hook, mcp, wrap, autonomous, spine, invariant
      Monitoring:    adapt, audit, strict, telemetry, dashboard, prometheus
      Modes:         profile, puppet, boil
      Security:      security, scar, taint
      Tuning:        tune, semvar
      Other:         graph, routing, watch, claude-hooks, issue
    """
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


# ---------------------------------------------------------------------------
# Measurement Integrity (AG2 Layer 2.1-B)
# ---------------------------------------------------------------------------


@cli.group("measure")
def measure_group() -> None:
    """Measurement integrity — tidepool defense for tool outputs."""
    pass


@measure_group.command("status")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def measure_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show measurement integrity status for a run."""
    from .measurement_integrity import MeasurementStore

    gov_dir = Path(ctx.obj or ".governor")
    store = MeasurementStore(governor_dir=gov_dir)
    state = store.load(run_id)

    if not state:
        click.echo(f"No measurement data for run {run_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(state.to_dict(), indent=2))
    else:
        click.echo(f"Run: {run_id}")
        click.echo(f"Risk: {state.risk_score:.3f}")
        click.echo(f"Trusted: {state.trusted_count} | Untrusted: {state.untrusted_count} | Quarantined: {state.quarantined_count}")
        if state.frozen_tools:
            click.echo(f"Frozen tools: {', '.join(sorted(state.frozen_tools))}")
        click.echo(f"Alerts: {len(state.alerts)}")


@measure_group.command("scan")
@click.argument("text")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def measure_scan(ctx: click.Context, text: str, as_json: bool) -> None:
    """Scan text for instruction masquerade patterns."""
    from .measurement_integrity import detect_instruction_masquerade

    matches = detect_instruction_masquerade(text)
    if as_json:
        click.echo(json.dumps({"patterns_matched": matches, "is_suspicious": len(matches) > 0}))
    else:
        if matches:
            click.echo(f"Suspicious patterns ({len(matches)}):")
            for m in matches:
                click.echo(f"  ! {m}")
        else:
            click.echo("No suspicious patterns detected.")


@measure_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def measure_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with measurement data."""
    from .measurement_integrity import MeasurementStore

    gov_dir = Path(ctx.obj or ".governor")
    store = MeasurementStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            s = store.load(r)
            results.append({"run_id": r, "risk_score": s.risk_score if s else None})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No measurement runs found.")
        for r in runs:
            s = store.load(r)
            if s:
                click.echo(f"  {r}: risk={s.risk_score:.3f} frozen={len(s.frozen_tools)}")


# ---------------------------------------------------------------------------
# Phase Control (AG2 Layer 2.1-A)
# ---------------------------------------------------------------------------


@cli.group("phase")
def phase_group() -> None:
    """Phase control — run phases with budget locks."""
    pass


@phase_group.command("status")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def phase_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show phase control status for a run."""
    from .phase_control import PhaseStore

    gov_dir = Path(ctx.obj or ".governor")
    store = PhaseStore(governor_dir=gov_dir)
    controller = store.load(run_id)

    if not controller:
        click.echo(f"No phase data for run {run_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(controller.to_dict(), indent=2))
    else:
        click.echo(f"Run: {run_id}")
        click.echo(f"Phase: {controller.phase.name}")
        br = controller.budget_remaining
        click.echo(f"Budget: explore={br['explore']} draft={br['draft']} verify={br['verify']}")
        click.echo(f"Confidence cap: {controller.confidence_cap:.2f}")
        if controller.novelty.total > 0:
            click.echo(f"Novelty debt: {controller.novelty.total:.2f}")


@phase_group.command("advance")
@click.argument("run_id")
@click.option("--force", is_flag=True, help="Force transition")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def phase_advance(ctx: click.Context, run_id: str, force: bool, as_json: bool) -> None:
    """Advance to next phase."""
    from .phase_control import PhaseStore

    gov_dir = Path(ctx.obj or ".governor")
    store = PhaseStore(governor_dir=gov_dir)
    controller = store.load(run_id)

    if not controller:
        click.echo(f"No phase data for run {run_id}", err=True)
        ctx.exit(1)
        return

    if force:
        evt = controller.force_advance("manual force")
    else:
        evt = controller.advance()

    store.save(controller)

    if as_json:
        click.echo(json.dumps(evt.to_dict(), indent=2))
    else:
        click.echo(f"{evt.from_phase.name} → {evt.to_phase.name}: {evt.result.value}")
        click.echo(f"Reason: {evt.reason}")


@phase_group.command("init")
@click.argument("run_id")
@click.option("--explore", type=int, default=None, help="Explore budget")
@click.option("--draft", type=int, default=None, help="Draft budget")
@click.option("--verify", type=int, default=None, help="Verify budget")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def phase_init(ctx: click.Context, run_id: str, explore: int | None,
               draft: int | None, verify: int | None, as_json: bool) -> None:
    """Initialize phase control for a run."""
    from .phase_control import PhaseController, PhaseBudget, PhaseStore

    gov_dir = Path(ctx.obj or ".governor")
    store = PhaseStore(governor_dir=gov_dir)

    budget_kwargs: dict[str, int] = {}
    if explore is not None:
        budget_kwargs["explore"] = explore
    if draft is not None:
        budget_kwargs["draft"] = draft
    if verify is not None:
        budget_kwargs["verify"] = verify

    controller = PhaseController(
        run_id=run_id,
        budget=PhaseBudget(**budget_kwargs) if budget_kwargs else PhaseBudget(),
    )
    store.save(controller)

    if as_json:
        click.echo(json.dumps(controller.to_dict(), indent=2))
    else:
        click.echo(f"Phase control initialized for run {run_id}")
        click.echo(f"Budget: explore={controller.budget.explore} draft={controller.budget.draft} verify={controller.budget.verify}")


@phase_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def phase_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with phase control."""
    from .phase_control import PhaseStore

    gov_dir = Path(ctx.obj or ".governor")
    store = PhaseStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            c = store.load(r)
            results.append({"run_id": r, "phase": c.phase.name if c else None})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No phase-controlled runs found.")
        for r in runs:
            c = store.load(r)
            if c:
                click.echo(f"  {r}: {c.phase.name}")


# ---------------------------------------------------------------------------
# Coverage Metrics (AG2 Layer 2.1-A)
# ---------------------------------------------------------------------------


@cli.group("metrics")
def metrics_group() -> None:
    """Coverage and efficiency metrics — severity-weighted verification."""
    pass


@metrics_group.command("status")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def metrics_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show coverage metrics for a run."""
    from .metrics import MetricsStore

    gov_dir = Path(ctx.obj or ".governor")
    store = MetricsStore(governor_dir=gov_dir)
    tracker = store.load_tracker(run_id)

    if not tracker:
        click.echo(f"No metrics found for run {run_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(tracker.to_dict(), indent=2))
    else:
        cc = tracker.claim_coverage
        click.echo(f"Run: {run_id}")
        click.echo(f"Claims: {cc.total_claims}")
        click.echo(cc.summary())
        if tracker.snapshots:
            click.echo(f"Snapshots: {len(tracker.snapshots)}")
            click.echo(f"Efficiency: {tracker.latest_efficiency():.4f}")


@metrics_group.command("claims")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def metrics_claims(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """List claims tracked for a run."""
    from .metrics import MetricsStore

    gov_dir = Path(ctx.obj or ".governor")
    store = MetricsStore(governor_dir=gov_dir)
    tracker = store.load_tracker(run_id)

    if not tracker:
        click.echo(f"No metrics found for run {run_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps([c.to_dict() for c in tracker.claims], indent=2))
    else:
        for c in tracker.claims:
            icon = {"verified": "+", "waived": "~", "refuted": "!", "pending": "?", "unknown": " "}.get(c.status.value, " ")
            click.echo(f"  [{icon}] {c.claim_id} ({c.severity.value}): {c.description}")


@metrics_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def metrics_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with metrics."""
    from .metrics import MetricsStore

    gov_dir = Path(ctx.obj or ".governor")
    store = MetricsStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            t = store.load_tracker(r)
            results.append({"run_id": r, "coverage": t.coverage if t else None,
                           "claims": len(t.claims) if t else 0})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No metrics runs found.")
        for r in runs:
            t = store.load_tracker(r)
            if t:
                click.echo(f"  {r}: coverage={t.coverage:.1%} claims={len(t.claims)}")


# ---------------------------------------------------------------------------
# Admissibility Gate (AG2 Layer 2.1-A)
# ---------------------------------------------------------------------------


@cli.group("admit")
def admit_group() -> None:
    """Admissibility gate — push-back system for underspecified tasks."""
    pass


@admit_group.command("assess")
@click.option("--setpoint", type=float, required=True, help="Setpoint score (0-1)")
@click.option("--constraints", type=float, required=True, help="Constraint score (0-1)")
@click.option("--observability", type=float, required=True, help="Observability score (0-1)")
@click.option("--run-id", default="", help="Run ID to persist assessment")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def admit_assess(ctx: click.Context, setpoint: float, constraints: float,
                 observability: float, run_id: str, as_json: bool) -> None:
    """Assess task admissibility."""
    from .admissibility import assess_task, AdmissibilityStore

    gov_dir = Path(ctx.obj or ".governor")
    assessment = assess_task(setpoint, constraints, observability)

    if run_id:
        store = AdmissibilityStore(governor_dir=gov_dir)
        store.save_assessment(run_id, assessment)

    if as_json:
        click.echo(json.dumps(assessment.to_dict(), indent=2))
    else:
        click.echo(f"Score: {assessment.score:.3f}")
        click.echo(f"Mode: {assessment.mode.value}")


@admit_group.command("status")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def admit_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show admissibility status for a run."""
    from .admissibility import AdmissibilityStore

    gov_dir = Path(ctx.obj or ".governor")
    store = AdmissibilityStore(governor_dir=gov_dir)
    assessment = store.load_assessment(run_id)

    if not assessment:
        click.echo(f"No assessment found for run {run_id}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(assessment.to_dict(), indent=2))
    else:
        click.echo(f"Run: {run_id}")
        click.echo(f"Score: {assessment.score:.3f}")
        click.echo(f"Mode: {assessment.mode.value}")
        click.echo(f"Unknowns: {len(assessment.unknowns)}")


@admit_group.command("unknowns")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def admit_unknowns(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """List unknowns for a run."""
    from .admissibility import AdmissibilityStore

    gov_dir = Path(ctx.obj or ".governor")
    store = AdmissibilityStore(governor_dir=gov_dir)
    unknowns = store.load_unknowns(run_id)

    if as_json:
        click.echo(json.dumps([u.to_dict() for u in unknowns], indent=2))
    else:
        if not unknowns:
            click.echo("No unknowns recorded.")
        for u in unknowns:
            click.echo(f"  [{u.severity.value}] {u.id}: {u.description} ({u.category.value})")


@admit_group.command("check")
@click.argument("run_id")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def admit_check(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Check Invariant F (no hidden assumptions) for a run."""
    from .admissibility import AdmissibilityStore, check_invariant_f

    gov_dir = Path(ctx.obj or ".governor")
    store = AdmissibilityStore(governor_dir=gov_dir)
    unknowns = store.load_unknowns(run_id)
    assumptions = store.load_assumptions(run_id)
    violations = check_invariant_f(assumptions, unknowns)

    if as_json:
        click.echo(json.dumps({"violations": violations, "compliant": len(violations) == 0}, indent=2))
    else:
        if violations:
            click.echo(f"Invariant F violations ({len(violations)}):")
            for v in violations:
                click.echo(f"  ! {v}")
            ctx.exit(1)
        else:
            click.echo("Invariant F: compliant")


@admit_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def admit_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with admissibility assessments."""
    from .admissibility import AdmissibilityStore

    gov_dir = Path(ctx.obj or ".governor")
    store = AdmissibilityStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            a = store.load_assessment(r)
            results.append({"run_id": r, "score": a.score if a else None,
                           "mode": a.mode.value if a else None})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No admissibility assessments found.")
        for r in runs:
            a = store.load_assessment(r)
            if a:
                click.echo(f"  {r}: score={a.score:.3f} mode={a.mode.value}")


# ---------------------------------------------------------------------------
# Mode Detection (AG2 Layer 2.1-C)
# ---------------------------------------------------------------------------


@cli.group("mode")
def mode_group() -> None:
    """Mode detection — Bayesian domain mode posterior."""
    pass


@mode_group.command("status")
@click.option("--run-id", default="current", help="Run ID")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def mode_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show mode detection state."""
    from .mode_detection import ModeDetectionStore

    gov_dir = Path(ctx.obj or ".governor")
    store = ModeDetectionStore(governor_dir=gov_dir)
    state = store.load(run_id)

    if state is None:
        if as_json:
            click.echo(json.dumps({"run_id": run_id, "status": "no data"}))
        else:
            click.echo(f"No mode data for run '{run_id}'.")
        return

    if as_json:
        click.echo(json.dumps(state.to_dict(), indent=2))
    else:
        click.echo(f"Run:       {state.run_id}")
        click.echo(f"Mode:      {state.current_posterior.dominant_mode.value}")
        click.echo(f"Conf:      {state.current_posterior.confidence:.2f}")
        click.echo(f"Profile:   {state.active_profile}")
        click.echo(f"Obs count: {state.observation_count}")
        click.echo(f"Alerts:    {len(state.alerts)}")


@mode_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def mode_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with mode data."""
    from .mode_detection import ModeDetectionStore

    gov_dir = Path(ctx.obj or ".governor")
    store = ModeDetectionStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        click.echo(json.dumps(runs))
    else:
        if not runs:
            click.echo("No mode detection runs found.")
        for r in runs:
            s = store.load(r)
            if s:
                click.echo(f"  {r}: {s.current_posterior.dominant_mode.value} "
                           f"(conf={s.current_posterior.confidence:.2f})")


# ---------------------------------------------------------------------------
# Coherence Budget (AG2 Layer 2.1-C)
# ---------------------------------------------------------------------------


@cli.group("cbi")
def cbi_group() -> None:
    """Coherence Budget Index — governor health metric."""
    pass


@cbi_group.command("status")
@click.option("--run-id", default="current", help="Run ID")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def cbi_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show CBI for a run."""
    from .coherence_budget import CoherenceBudgetStore

    gov_dir = Path(ctx.obj or ".governor")
    store = CoherenceBudgetStore(governor_dir=gov_dir)
    result = store.load(run_id)

    if result is None:
        if as_json:
            click.echo(json.dumps({"run_id": run_id, "status": "no data"}))
        else:
            click.echo(f"No CBI data for run '{run_id}'.")
        return

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"CBI:    {result.cbi:.1f}/100")
        click.echo(f"Status: {result.status.value}")
        click.echo(f"P_inv:  {result.p_inv:.4f}")
        click.echo(f"S_soft: {result.s_soft:.4f}")
        click.echo(f"D (Δt): {result.D:.2f}")


@cbi_group.command("compute")
@click.option("--d", "dt", type=float, default=0.0, help="Δt squeeze ratio")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
def cbi_compute(dt: float, as_json: bool) -> None:
    """Compute CBI with default healthy metrics (diagnostic)."""
    from .coherence_budget import compute_cbi

    violations = {f"S{i}": 0.0 for i in range(1, 8)}
    metrics = {f"M{i}": 1.0 for i in range(1, 9)}
    result = compute_cbi(violations, metrics, D=dt)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"CBI:    {result.cbi:.1f}/100")
        click.echo(f"Status: {result.status.value}")


@cbi_group.command("closure")
@click.option("--run-id", default="current", help="Run ID")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def cbi_closure(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show closure gate result for a run."""
    from .coherence_budget import CoherenceBudgetStore

    gov_dir = Path(ctx.obj or ".governor")
    store = CoherenceBudgetStore(governor_dir=gov_dir)
    result = store.load_closure(run_id)

    if result is None:
        click.echo(f"No closure gate data for run '{run_id}'.")
        return

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        click.echo(f"Decision:    {result.decision.value}")
        click.echo(f"Uncertainty: {result.uncertainty:.2f} (threshold: {result.threshold})")
        click.echo(f"Unverified:  {result.unverified_claims}")
        click.echo(f"Open unkn:   {result.open_unknowns}")


@cbi_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def cbi_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with CBI data."""
    from .coherence_budget import CoherenceBudgetStore

    gov_dir = Path(ctx.obj or ".governor")
    store = CoherenceBudgetStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            s = store.load(r)
            results.append({"run_id": r, "cbi": round(s.cbi, 1) if s else None,
                            "status": s.status.value if s else None})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No CBI runs found.")
        for r in runs:
            s = store.load(r)
            if s:
                click.echo(f"  {r}: CBI={s.cbi:.1f} [{s.status.value}]")


# ---------------------------------------------------------------------------
# Risk Function (AG2 Layer 2.1-B)
# ---------------------------------------------------------------------------


@cli.group("risk")
def risk_group() -> None:
    """Risk potential function — scalar risk V from signals."""
    pass


@risk_group.command("status")
@click.option("--run-id", default="current", help="Run ID")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def risk_status(ctx: click.Context, run_id: str, as_json: bool) -> None:
    """Show risk state for a run."""
    from .risk_function import RiskStore

    gov_dir = Path(ctx.obj or ".governor")
    store = RiskStore(governor_dir=gov_dir)
    state = store.load(run_id)

    if state is None:
        if as_json:
            click.echo(json.dumps({"run_id": run_id, "status": "no data"}))
        else:
            click.echo(f"No risk data for run '{run_id}'.")
        return

    if as_json:
        click.echo(json.dumps(state.to_dict(), indent=2))
    else:
        click.echo(f"Run:     {state.run_id}")
        click.echo(f"Level:   {state.current_level.value}")
        click.echo(f"Risk:    {state.current_risk:.4f}")
        click.echo(f"Peak:    {state.peak_risk:.4f}")
        click.echo(f"Profile: {state.active_profile}")
        click.echo(f"Frozen:  {sorted(state.frozen_tools) or 'none'}")
        click.echo(f"Ev mult: {state.evidence_multiplier}")


@risk_group.command("assess")
@click.option("--run-id", default="current", help="Run ID")
@click.option("--untrusted", type=float, default=0.0, help="Untrusted blob signal [0-1]")
@click.option("--scope", type=float, default=0.0, help="Scope size signal [0-1]")
@click.option("--irrev", type=float, default=0.0, help="Irreversibility signal [0-1]")
@click.option("--gap", type=float, default=0.0, help="Evidence gap signal [0-1]")
@click.option("--anomaly", type=float, default=0.0, help="Anomaly signal [0-1]")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def risk_assess(ctx: click.Context, run_id: str, untrusted: float,
                scope: float, irrev: float, gap: float, anomaly: float,
                as_json: bool) -> None:
    """Assess risk from signal values."""
    from .risk_function import RiskComponents, assess_risk

    components = RiskComponents(
        untrusted_blob_use=untrusted,
        scope_size=scope,
        irreversibility_intent=irrev,
        evidence_gap=gap,
        anomaly_score=anomaly,
    )
    assessment = assess_risk(run_id, components)

    if as_json:
        click.echo(json.dumps(assessment.to_dict(), indent=2))
    else:
        click.echo(f"Risk:    {assessment.risk_value:.4f}")
        click.echo(f"Level:   {assessment.level.value}")
        click.echo(f"Actions: {[a.value for a in assessment.actions_taken]}")
        if assessment.frozen_tools:
            click.echo(f"Frozen:  {sorted(assessment.frozen_tools)}")
        if assessment.demoted_to:
            click.echo(f"Demoted: {assessment.demoted_to}")


@risk_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def risk_list(ctx: click.Context, as_json: bool) -> None:
    """List runs with risk data."""
    from .risk_function import RiskStore

    gov_dir = Path(ctx.obj or ".governor")
    store = RiskStore(governor_dir=gov_dir)
    runs = store.list_runs()

    if as_json:
        results = []
        for r in runs:
            s = store.load(r)
            results.append({"run_id": r, "level": s.current_level.value if s else None})
        click.echo(json.dumps(results, indent=2))
    else:
        if not runs:
            click.echo("No risk runs found.")
        for r in runs:
            s = store.load(r)
            if s:
                click.echo(f"  {r}: {s.current_level.value} risk={s.current_risk:.4f}")


# ---------------------------------------------------------------------------
# Deployment Profiles (AG2 Layer 2.1-B)
# ---------------------------------------------------------------------------


@cli.group("deploy")
def deploy_group() -> None:
    """Deployment profiles — authority classes + capability tokens."""
    pass


@deploy_group.command("status")
@click.option("--name", default="operator", help="Profile name")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def deploy_status(ctx: click.Context, name: str, as_json: bool) -> None:
    """Show deployment profile details."""
    from .deployment_profiles import DeploymentStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DeploymentStore(governor_dir=gov_dir)
    profile = store.load_profile(name)

    if profile is None:
        click.echo(f"Profile '{name}' not found.")
        raise SystemExit(1)

    if as_json:
        click.echo(json.dumps(profile.to_dict(), indent=2))
    else:
        click.echo(f"Profile: {name}")
        click.echo(f"  Authority: {profile.authority_class.value}")
        click.echo(f"  Audit:     {profile.audit_level.value}")
        click.echo(f"  Whitelist: {sorted(profile.tool_whitelist)}")
        click.echo(f"  Blacklist: {sorted(profile.tool_blacklist)}")
        click.echo(f"  Two-phase: {sorted(profile.requires_two_phase)}")
        click.echo(f"  Evidence:  {profile.evidence_threshold}")


@deploy_group.command("check")
@click.argument("tool_id")
@click.option("--name", default="operator", help="Profile name")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def deploy_check(ctx: click.Context, tool_id: str, name: str, as_json: bool) -> None:
    """Check if a tool is allowed under a profile."""
    from .deployment_profiles import DeploymentStore, check_tool_access

    gov_dir = Path(ctx.obj or ".governor")
    store = DeploymentStore(governor_dir=gov_dir)
    profile = store.load_profile(name)

    if profile is None:
        click.echo(f"Profile '{name}' not found.")
        raise SystemExit(1)

    allowed, reason = check_tool_access(profile, tool_id)

    if as_json:
        click.echo(json.dumps({"tool": tool_id, "allowed": allowed, "reason": reason}))
    else:
        status = "ALLOWED" if allowed else "DENIED"
        click.echo(f"{status}: {tool_id} ({reason})")


@deploy_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def deploy_list(ctx: click.Context, as_json: bool) -> None:
    """List available deployment profiles."""
    from .deployment_profiles import DeploymentStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DeploymentStore(governor_dir=gov_dir)
    names = store.list_profiles()

    if as_json:
        click.echo(json.dumps(names))
    else:
        click.echo("Deployment profiles:")
        for n in names:
            p = store.load_profile(n)
            if p:
                click.echo(f"  {n}: {p.authority_class.value} audit={p.audit_level.value}")


@deploy_group.command("proposals")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def deploy_proposals(ctx: click.Context, as_json: bool) -> None:
    """List action proposals."""
    from .deployment_profiles import DeploymentStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DeploymentStore(governor_dir=gov_dir)
    ids = store.list_proposals()

    if as_json:
        results = []
        for pid in ids:
            p = store.load_proposal(pid)
            results.append(p.to_dict() if p else {"proposal_id": pid, "error": "load failed"})
        click.echo(json.dumps(results, indent=2))
    else:
        if not ids:
            click.echo("No proposals found.")
        for pid in ids:
            p = store.load_proposal(pid)
            if p:
                click.echo(f"  {pid}: {p.action} [{p.status.value}] severity={p.severity}")


# ---------------------------------------------------------------------------
# WebUI Demo (AG2 Layer 4, Item #12)
# ---------------------------------------------------------------------------


@cli.group("demo")
def demo_group() -> None:
    """WebUI demo management — scripted, reproducible screenshots."""
    pass


@demo_group.command("list")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def demo_list(ctx: click.Context, as_json: bool) -> None:
    """List all demo scenarios (built-in + custom)."""
    from .webui_demo import DemoStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DemoStore(governor_dir=gov_dir)
    scenarios = store.list_scenarios()

    if as_json:
        click.echo(json.dumps([s.to_dict() for s in scenarios], indent=2))
    else:
        for s in scenarios:
            shots = len(s.screenshot_paths)
            tags = ", ".join(s.tags) if s.tags else "none"
            click.echo(f"  {s.name} ({s.surface.value}) — {shots} screenshots, tags: {tags}")


@demo_group.command("check")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def demo_check(ctx: click.Context, as_json: bool) -> None:
    """Check freshness of all demo screenshots."""
    from .webui_demo import DemoStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DemoStore(governor_dir=gov_dir)
    results = store.check_freshness()

    if as_json:
        click.echo(json.dumps(results, indent=2))
    else:
        for r in results:
            status = r["status"]
            icon = {"fresh": "+", "stale": "~", "missing": "?", "error": "!"}.get(status, " ")
            click.echo(f"  [{icon}] {r['name']}: {status} ({len(r['screenshots'])} screenshots)")


@demo_group.command("spec")
@click.argument("name")
@click.option("--output", "-o", default=None, help="Write to file")
@click.pass_context
def demo_spec(ctx: click.Context, name: str, output: str | None) -> None:
    """Generate Playwright spec for a demo scenario."""
    from .webui_demo import DemoStore, generate_playwright_spec

    gov_dir = Path(ctx.obj or ".governor")
    store = DemoStore(governor_dir=gov_dir)
    scenarios = store.list_scenarios()
    scenario = next((s for s in scenarios if s.name == name), None)

    if not scenario:
        click.echo(f"Unknown scenario: {name}", err=True)
        ctx.exit(1)
        return

    spec = generate_playwright_spec(scenario)
    if output:
        Path(output).write_text(spec)
        click.echo(f"Wrote Playwright spec to {output}")
    else:
        click.echo(spec)


@demo_group.command("show")
@click.argument("name")
@click.option("--json", "as_json", is_flag=True, help="JSON output")
@click.pass_context
def demo_show(ctx: click.Context, name: str, as_json: bool) -> None:
    """Show details of a demo scenario."""
    from .webui_demo import DemoStore

    gov_dir = Path(ctx.obj or ".governor")
    store = DemoStore(governor_dir=gov_dir)
    scenarios = store.list_scenarios()
    scenario = next((s for s in scenarios if s.name == name), None)

    if not scenario:
        click.echo(f"Unknown scenario: {name}", err=True)
        ctx.exit(1)
        return

    if as_json:
        click.echo(json.dumps(scenario.to_dict(), indent=2))
    else:
        click.echo(f"Name: {scenario.name}")
        click.echo(f"Description: {scenario.description}")
        click.echo(f"Surface: {scenario.surface.value}")
        click.echo(f"Steps: {len(scenario.steps)}")
        click.echo(f"Screenshots: {len(scenario.screenshot_paths)}")
        if scenario.prerequisites:
            click.echo(f"Prerequisites:")
            for p in scenario.prerequisites:
                click.echo(f"  - {p}")
        if scenario.tags:
            click.echo(f"Tags: {', '.join(scenario.tags)}")
        click.echo(f"Content hash: {scenario.content_hash()}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
