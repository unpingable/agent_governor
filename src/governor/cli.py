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


@click.group()
@click.option(
    "--root", "-r",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Project root directory",
)
@click.pass_context
def cli(ctx: click.Context, root: str) -> None:
    """Agent Governor - Gate for file mutations."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


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
        click.echo(f"  Backup exists: yes")


@hook.command("pre-commit")
@click.option("--bypass", is_flag=True, help="Bypass the check")
@click.pass_context
def hook_pre_commit(ctx: click.Context, bypass: bool) -> None:
    """
    Run the pre-commit check.

    This is called by the git pre-commit hook script.
    Not typically called directly by users.
    """
    from .hooks import run_pre_commit_check, get_git_root

    root = Path(ctx.obj["root"])
    git_root = get_git_root(root)

    success, message = run_pre_commit_check(git_root, bypass=bypass)

    click.echo(message)

    if not success:
        ctx.exit(1)


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
@click.pass_context
def wrap(ctx: click.Context, command: tuple[str, ...], auto_approve: bool) -> None:
    """
    Wrap an agent command with governor enforcement.

    Monitors file changes made by the agent and ensures they go
    through the governor approval workflow.

    Examples:
        governor wrap -- python script.py
        governor wrap --auto-approve -- claude-code
        governor wrap -- npm run build
    """
    from .wrapper import wrap_agent

    root = Path(ctx.obj["root"])

    exit_code, message = wrap_agent(
        list(command),
        root=root,
        auto_approve=auto_approve,
    )

    click.echo(message)
    ctx.exit(exit_code)


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
            click.echo(f"Error: Scope conflict with existing reservation", err=True)
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

    click.echo(f"Task heartbeat recorded")
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
@click.pass_context
def task_list(ctx: click.Context, agent_id: str | None, active_only: bool) -> None:
    """List tasks/reservations."""
    gov_dir = ensure_initialized(ctx)
    storage = get_storage(gov_dir)

    where = {"agent_id": agent_id} if agent_id else None
    reservations = storage.query("reservations", where=where, order_by="started_at DESC")

    if not reservations:
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
        click.echo("No active tasks found")
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
        click.echo(f"\n  Next steps:")
        for step in next_steps:
            click.echo(f"    - {step}")
    if blocker:
        click.echo(f"\n  Blockers:")
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

    click.echo(f"Audit Graph Statistics\n")
    click.echo(f"Total nodes: {len(graph.nodes)}")
    click.echo(f"Total edges: {len(graph.edges)}")

    if node_counts:
        click.echo(f"\nNodes by type:")
        for type_name, count in sorted(node_counts.items()):
            click.echo(f"  {type_name}: {count}")

    if edge_counts:
        click.echo(f"\nEdges by type:")
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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
