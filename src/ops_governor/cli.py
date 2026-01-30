"""
CLI for SRE/Ops Governor.

ops-gov: Mechanical verification for operational claims.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from .types import (
    ProofType,
    ProofRequirement,
    ClaimDefinition,
    PolicyPack,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)
from .policy import (
    PolicyRegistry,
    ClaimVerifier,
    BUILTIN_PACKS,
    install_builtin_pack,
)


def get_project_dir() -> Path:
    """Find project directory by looking for .ops-gov folder."""
    cwd = Path.cwd()

    if (cwd / ".ops-gov").exists():
        return cwd

    for parent in cwd.parents:
        if (parent / ".ops-gov").exists():
            return parent

    return cwd


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize an ops-gov project."""
    project_dir = Path(args.path or ".").resolve()
    ops_dir = project_dir / ".ops-gov"

    if ops_dir.exists() and not args.force:
        print(f"Project already initialized at {project_dir}")
        print("Use --force to reinitialize")
        return 1

    ops_dir.mkdir(parents=True, exist_ok=True)
    (ops_dir / "policies").mkdir(exist_ok=True)
    (ops_dir / "claims").mkdir(exist_ok=True)
    (ops_dir / "incidents").mkdir(exist_ok=True)

    meta = {
        "project_name": args.name or project_dir.name,
        "version": "1.0",
    }
    (ops_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    print(f"Initialized ops-gov project: {meta['project_name']}")
    print(f"  Directory: {project_dir}")
    print("\nNext steps:")
    print("  ops-gov policy install incident/strict")
    print("  ops-gov claim verify service_restored")

    return 0


# ============================================================================
# Policy commands
# ============================================================================


def cmd_policy_list(args: argparse.Namespace) -> int:
    """List installed policy packs."""
    registry = PolicyRegistry(get_project_dir())

    packs = registry.all_packs()
    if not packs:
        print("No policy packs installed.")
        print("\nAvailable built-in packs:")
        for name in BUILTIN_PACKS:
            print(f"  {name}")
        print("\nInstall with: ops-gov policy install <name>")
        return 0

    print("Installed policy packs:\n")
    for pack in packs:
        status = "✓" if pack.enabled else "✗"
        env = f" [{', '.join(pack.environments)}]" if pack.environments else ""
        print(f"  {status} {pack.name} v{pack.version}{env}")
        print(f"      {pack.description}")
        print(f"      Claims: {', '.join(c.name for c in pack.claims)}")
        print()

    return 0


def cmd_policy_install(args: argparse.Namespace) -> int:
    """Install a policy pack."""
    registry = PolicyRegistry(get_project_dir())

    if args.name in BUILTIN_PACKS:
        pack = install_builtin_pack(registry, args.name)
        print(f"Installed built-in pack: {pack.name}")
        print(f"  Claims: {', '.join(c.name for c in pack.claims)}")
    elif args.file:
        data = json.loads(Path(args.file).read_text())
        pack = PolicyPack.from_dict(data)
        registry.register(pack)
        print(f"Installed pack from file: {pack.name}")
    else:
        print(f"Unknown pack: {args.name}")
        print(f"Available built-in packs: {', '.join(BUILTIN_PACKS.keys())}")
        return 1

    return 0


def cmd_policy_show(args: argparse.Namespace) -> int:
    """Show details of a policy pack."""
    registry = PolicyRegistry(get_project_dir())

    pack = registry.get(args.name)
    if not pack:
        print(f"Pack not found: {args.name}")
        return 1

    print(f"# {pack.name} v{pack.version}")
    print(f"\n{pack.description}\n")

    if pack.environments:
        print(f"Environments: {', '.join(pack.environments)}")

    print(f"\n## Claims ({len(pack.claims)})\n")
    for claim in pack.claims:
        print(f"### {claim.name}")
        print(f"{claim.description}\n")
        print("Requirements:")
        for req in claim.requirements:
            opt = " (optional)" if req.optional else ""
            print(f"  - [{req.proof_type.value}] {req.description}{opt}")
            if req.command:
                print(f"      Command: {req.command}")
            if req.file_path:
                print(f"      File: {req.file_path}")
            if req.threshold is not None:
                print(f"      Threshold: {req.threshold_op} {req.threshold}")
        print()

    return 0


def cmd_policy_disable(args: argparse.Namespace) -> int:
    """Disable a policy pack."""
    registry = PolicyRegistry(get_project_dir())

    pack = registry.get(args.name)
    if not pack:
        print(f"Pack not found: {args.name}")
        return 1

    pack.enabled = False
    registry.register(pack)  # Re-save
    print(f"Disabled pack: {args.name}")

    return 0


def cmd_policy_enable(args: argparse.Namespace) -> int:
    """Enable a policy pack."""
    registry = PolicyRegistry(get_project_dir())

    pack = registry.get(args.name)
    if not pack:
        print(f"Pack not found: {args.name}")
        return 1

    pack.enabled = True
    registry.register(pack)
    print(f"Enabled pack: {args.name}")

    return 0


# ============================================================================
# Claim commands
# ============================================================================


def cmd_claim_verify(args: argparse.Namespace) -> int:
    """Verify a claim with mechanical proof."""
    verifier = ClaimVerifier(get_project_dir())

    context = {}
    if args.service:
        context["service"] = args.service
    if args.env:
        context["environment"] = args.env

    print(f"Verifying claim: {args.claim}")
    print(f"Actor: {args.actor or 'cli'}")
    if context:
        print(f"Context: {context}")
    print()

    attempt = verifier.verify_claim(
        claim_name=args.claim,
        actor=args.actor or "cli",
        environment=args.env,
        context=context,
    )

    if attempt.satisfied:
        print("✓ CLAIM SATISFIED\n")
    else:
        print("✗ CLAIM NOT SATISFIED\n")

    print("Evidence collected:")
    for evidence in attempt.evidence:
        status = "✓" if evidence.satisfied else "✗"
        print(f"  {status} [{evidence.proof_type.value}]")
        if evidence.command_executed:
            print(f"      Command: {evidence.command_executed}")
            print(f"      Exit code: {evidence.exit_code}")
        if evidence.file_path_checked:
            print(f"      File: {evidence.file_path_checked}")
            print(f"      Exists: {evidence.file_exists}")
        if evidence.output_hash:
            print(f"      Output hash: {evidence.output_hash[:16]}...")
        if evidence.failure_reason:
            print(f"      Failure: {evidence.failure_reason}")
        print()

    if attempt.missing_requirements:
        print(f"Missing requirements: {', '.join(attempt.missing_requirements)}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(attempt.to_dict(), indent=2, default=str))

    return 0 if attempt.satisfied else 1


def cmd_claim_list(args: argparse.Namespace) -> int:
    """List available claims."""
    registry = PolicyRegistry(get_project_dir())

    packs = registry.enabled_packs(environment=args.env)
    if not packs:
        print("No policy packs enabled.")
        return 0

    print("Available claims:\n")
    for pack in packs:
        print(f"## {pack.name}")
        for claim in pack.claims:
            req_count = len(claim.requirements)
            opt_count = sum(1 for r in claim.requirements if r.optional)
            print(f"  - {claim.name}: {claim.description}")
            print(f"      Requirements: {req_count} ({opt_count} optional)")
        print()

    return 0


def cmd_claim_approve(args: argparse.Namespace) -> int:
    """Add approval evidence to a pending claim."""
    # For now, just demonstrate the pattern
    print(f"Approval recorded:")
    print(f"  Claim: {args.claim}")
    print(f"  Approver: {args.approver}")
    print(f"  Role: {args.role}")
    if args.reason:
        print(f"  Reason: {args.reason}")

    # In full implementation, this would:
    # 1. Load pending claim attempt
    # 2. Add approval evidence
    # 3. Re-verify
    # 4. Save result

    return 0


def cmd_claim_waive(args: argparse.Namespace) -> int:
    """Waive a requirement with explicit reason."""
    print(f"Waiver recorded:")
    print(f"  Claim: {args.claim}")
    print(f"  Requirement: {args.requirement}")
    print(f"  Approver: {args.approver}")
    print(f"  Role: {args.role}")
    print(f"  Reason: {args.reason}")

    return 0


# ============================================================================
# Incident commands
# ============================================================================


def cmd_incident_create(args: argparse.Namespace) -> int:
    """Create a new incident."""
    severity = IncidentSeverity(args.severity.lower())

    incident = Incident(
        title=args.title,
        severity=severity,
        service=args.service or "",
        environment=args.env or "",
        commander=args.commander,
    )

    incident.add_event(
        event_type="created",
        actor=args.commander or "cli",
        description=f"Incident created: {args.title}",
    )

    # Save incident
    project_dir = get_project_dir()
    incidents_dir = project_dir / ".ops-gov" / "incidents"
    incidents_dir.mkdir(parents=True, exist_ok=True)

    incident_file = incidents_dir / f"{incident.id}.json"
    incident_file.write_text(json.dumps(incident.to_dict(), indent=2))

    print(f"Created incident: {incident.id}")
    print(f"  Title: {incident.title}")
    print(f"  Severity: {incident.severity.value}")
    print(f"  Status: {incident.status.value}")

    return 0


def cmd_incident_status(args: argparse.Namespace) -> int:
    """Update incident status."""
    project_dir = get_project_dir()
    incident_file = project_dir / ".ops-gov" / "incidents" / f"{args.id}.json"

    if not incident_file.exists():
        print(f"Incident not found: {args.id}")
        return 1

    incident = Incident.from_dict(json.loads(incident_file.read_text()))
    new_status = IncidentStatus(args.status.lower())

    event = incident.change_status(new_status, actor=args.actor or "cli")

    incident_file.write_text(json.dumps(incident.to_dict(), indent=2))

    print(f"Updated incident {args.id}:")
    print(f"  {event.old_status.value} → {event.new_status.value}")

    return 0


def cmd_incident_show(args: argparse.Namespace) -> int:
    """Show incident details."""
    project_dir = get_project_dir()
    incident_file = project_dir / ".ops-gov" / "incidents" / f"{args.id}.json"

    if not incident_file.exists():
        print(f"Incident not found: {args.id}")
        return 1

    incident = Incident.from_dict(json.loads(incident_file.read_text()))

    print(f"# Incident: {incident.title}")
    print(f"\nID: {incident.id}")
    print(f"Severity: {incident.severity.value}")
    print(f"Status: {incident.status.value}")
    print(f"Service: {incident.service or 'N/A'}")
    print(f"Environment: {incident.environment or 'N/A'}")
    print(f"Commander: {incident.commander or 'N/A'}")
    print(f"Detected: {incident.detected_at}")
    if incident.resolved_at:
        print(f"Resolved: {incident.resolved_at}")

    print(f"\n## Timeline ({len(incident.timeline)} events)\n")
    for event in incident.timeline:
        print(f"  [{event.timestamp.strftime('%H:%M:%S')}] {event.event_type}: {event.description}")
        print(f"      Actor: {event.actor}")

    return 0


def cmd_incident_list(args: argparse.Namespace) -> int:
    """List incidents."""
    project_dir = get_project_dir()
    incidents_dir = project_dir / ".ops-gov" / "incidents"

    if not incidents_dir.exists():
        print("No incidents recorded.")
        return 0

    incidents = []
    for f in incidents_dir.glob("*.json"):
        try:
            incident = Incident.from_dict(json.loads(f.read_text()))
            incidents.append(incident)
        except:
            pass

    if not incidents:
        print("No incidents recorded.")
        return 0

    # Filter by status
    if args.status:
        target_status = IncidentStatus(args.status.lower())
        incidents = [i for i in incidents if i.status == target_status]

    # Sort by detected time
    incidents.sort(key=lambda i: i.detected_at, reverse=True)

    print(f"Incidents ({len(incidents)}):\n")
    for incident in incidents[:20]:  # Limit to 20
        sev = incident.severity.value.upper()
        status = incident.status.value
        print(f"  [{sev}] {incident.id}")
        print(f"      {incident.title}")
        print(f"      Status: {status} | Service: {incident.service or 'N/A'}")
        print()

    return 0


def cmd_incident_claim(args: argparse.Namespace) -> int:
    """Make a claim within an incident context."""
    project_dir = get_project_dir()
    incident_file = project_dir / ".ops-gov" / "incidents" / f"{args.incident_id}.json"

    if not incident_file.exists():
        print(f"Incident not found: {args.incident_id}")
        return 1

    incident = Incident.from_dict(json.loads(incident_file.read_text()))

    # Verify the claim
    verifier = ClaimVerifier(project_dir)
    attempt = verifier.verify_claim(
        claim_name=args.claim,
        actor=args.actor or "cli",
        context={"incident_id": str(incident.id)},
    )

    # Add to incident
    incident.claims.append(attempt)
    incident.add_event(
        event_type="claim",
        actor=args.actor or "cli",
        description=f"Claim '{args.claim}': {'satisfied' if attempt.satisfied else 'not satisfied'}",
        claim_attempt_id=attempt.id,
    )

    incident_file.write_text(json.dumps(incident.to_dict(), indent=2))

    if attempt.satisfied:
        print(f"✓ Claim '{args.claim}' satisfied for incident {args.incident_id}")
    else:
        print(f"✗ Claim '{args.claim}' not satisfied")
        print(f"  Missing: {', '.join(attempt.missing_requirements)}")

    return 0 if attempt.satisfied else 1


# ============================================================================
# Main
# ============================================================================


# ============================================================================
# Runbook commands
# ============================================================================


def cmd_runbook_create(args: argparse.Namespace) -> int:
    """Create a new runbook."""
    from .verifiers import RunbookVerifier

    verifier = RunbookVerifier(get_project_dir())

    # Parse steps from JSON or interactively
    steps = []
    if args.steps:
        try:
            steps = json.loads(args.steps)
        except json.JSONDecodeError:
            print("Error: --steps must be valid JSON")
            return 1
    elif args.from_file:
        file_path = Path(args.from_file)
        if not file_path.exists():
            print(f"File not found: {args.from_file}")
            return 1
        try:
            steps = json.loads(file_path.read_text())
            if isinstance(steps, dict) and "steps" in steps:
                steps = steps["steps"]
        except json.JSONDecodeError:
            print("Error: file must contain valid JSON")
            return 1
    else:
        # Create minimal runbook
        steps = [
            {
                "description": "Step 1 - Update this runbook",
                "command": "echo 'TODO: Add actual commands'",
                "expected_exit_code": 0,
            }
        ]

    rollback_steps = []
    if args.rollback:
        try:
            rollback_steps = json.loads(args.rollback)
        except json.JSONDecodeError:
            print("Error: --rollback must be valid JSON")
            return 1

    runbook = verifier.create_runbook(
        name=args.name,
        description=args.description or f"Runbook: {args.name}",
        steps=steps,
        rollback_steps=rollback_steps,
    )

    print(f"Created runbook: {args.name}")
    print(f"  Steps: {len(runbook['steps'])}")
    print(f"  Rollback steps: {len(runbook.get('rollback_steps', []))}")
    print(f"\nEdit with: ops-gov runbook show {args.name}")

    return 0


def cmd_runbook_list(args: argparse.Namespace) -> int:
    """List available runbooks."""
    from .verifiers import RunbookVerifier

    verifier = RunbookVerifier(get_project_dir())
    runbooks_dir = verifier.runbooks_dir

    if not runbooks_dir.exists():
        print("No runbooks directory. Create one with: ops-gov runbook create <name>")
        return 0

    runbooks = list(runbooks_dir.glob("*.json"))
    if not runbooks:
        print("No runbooks found. Create one with: ops-gov runbook create <name>")
        return 0

    print(f"Runbooks ({len(runbooks)}):\n")
    for rb_file in sorted(runbooks):
        try:
            data = json.loads(rb_file.read_text())
            name = data.get("name", rb_file.stem)
            desc = data.get("description", "")
            steps = len(data.get("steps", []))
            version = data.get("version", "1.0")

            print(f"  {name} (v{version})")
            print(f"    {desc}")
            print(f"    Steps: {steps}")
            print()
        except json.JSONDecodeError:
            print(f"  {rb_file.stem} (invalid JSON)")

    return 0


def cmd_runbook_show(args: argparse.Namespace) -> int:
    """Show runbook details."""
    from .verifiers import RunbookVerifier

    verifier = RunbookVerifier(get_project_dir())
    runbook = verifier.load_runbook(args.name)

    if not runbook:
        print(f"Runbook not found: {args.name}")
        return 1

    print(f"Runbook: {runbook['name']}")
    print(f"Version: {runbook.get('version', '1.0')}")
    print(f"Description: {runbook.get('description', '')}")
    print(f"Created: {runbook.get('created_at', 'unknown')}")

    print("\nSteps:")
    for i, step in enumerate(runbook.get("steps", [])):
        print(f"\n  [{i}] {step.get('description', f'Step {i}')}")
        if step.get("command"):
            print(f"      Command: {step['command']}")
        if step.get("expected_exit_code") is not None:
            print(f"      Expected exit: {step['expected_exit_code']}")
        if step.get("expected_pattern"):
            print(f"      Expected pattern: {step['expected_pattern']}")
        if step.get("preconditions"):
            print(f"      Preconditions: {step['preconditions']}")

    if runbook.get("rollback_steps"):
        print("\nRollback Steps:")
        for i, step in enumerate(runbook["rollback_steps"]):
            print(f"  [{i}] {step.get('description', f'Rollback {i}')}")
            if step.get("command"):
                print(f"      Command: {step['command']}")

    if args.json:
        print("\n--- JSON ---")
        print(json.dumps(runbook, indent=2))

    return 0


def cmd_runbook_verify(args: argparse.Namespace) -> int:
    """Verify runbook execution."""
    from .verifiers import RunbookVerifier

    verifier = RunbookVerifier(get_project_dir())
    runbook = verifier.load_runbook(args.name)

    if not runbook:
        print(f"Runbook not found: {args.name}")
        return 1

    # Build execution log from provided evidence
    execution_log = []

    if args.log_file:
        try:
            execution_log = json.loads(Path(args.log_file).read_text())
        except (json.JSONDecodeError, FileNotFoundError) as e:
            print(f"Error reading log file: {e}")
            return 1
    elif args.step is not None:
        # Verify a single step
        evidence = {}
        if args.exit_code is not None:
            evidence["exit_code"] = args.exit_code
        if args.output:
            evidence["output"] = args.output

        success, msg = verifier.verify_step(args.name, args.step, evidence)
        print(f"Step {args.step}: {'PASS' if success else 'FAIL'}")
        print(f"  {msg}")
        return 0 if success else 1
    else:
        print("Error: Provide --log-file with execution log or --step to verify a single step")
        return 1

    # Verify full execution
    success, messages = verifier.verify_runbook_execution(args.name, execution_log)

    print(f"Runbook verification: {'PASS' if success else 'FAIL'}")
    print()
    for msg in messages:
        print(f"  {msg}")

    return 0 if success else 1


def cmd_runbook_generate_claims(args: argparse.Namespace) -> int:
    """Generate claim requirements from a runbook."""
    from .verifiers import RunbookVerifier

    verifier = RunbookVerifier(get_project_dir())
    runbook = verifier.load_runbook(args.name)

    if not runbook:
        print(f"Runbook not found: {args.name}")
        return 1

    requirements = verifier.generate_claim_requirements(args.name)

    if not requirements:
        print("No requirements generated (runbook may be empty)")
        return 0

    print(f"Generated {len(requirements)} claim requirements from runbook '{args.name}':\n")

    for i, req in enumerate(requirements):
        print(f"  [{i}] {req.description}")
        print(f"      Type: {req.proof_type.value}")
        if req.command:
            print(f"      Command: {req.command}")
        if req.expected_exit_code is not None:
            print(f"      Expected exit: {req.expected_exit_code}")
        print()

    if args.create_claim:
        # Create a claim definition from the runbook
        claim_name = f"runbook:{args.name}"
        claim_def = ClaimDefinition(
            name=claim_name,
            description=f"Complete runbook: {runbook.get('description', args.name)}",
            requirements=requirements,
        )

        # Create a policy pack for this runbook
        pack = PolicyPack(
            name=f"runbook/{args.name}",
            description=f"Auto-generated from runbook: {args.name}",
            claims=[claim_def],
        )

        registry = PolicyRegistry(get_project_dir())
        registry.register(pack)

        print(f"\nCreated policy pack: runbook/{args.name}")
        print(f"  Claim: {claim_name}")
        print(f"  Verify with: ops-gov claim verify {claim_name}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="ops-gov",
        description="SRE/Ops Governor: Mechanical verification for operational claims.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize ops-gov project")
    init_parser.add_argument("--name", help="Project name")
    init_parser.add_argument("--path", help="Project path")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialize")
    init_parser.set_defaults(func=cmd_init)

    # policy
    policy_parser = subparsers.add_parser("policy", help="Manage policy packs")
    policy_subs = policy_parser.add_subparsers(dest="policy_cmd")

    policy_list = policy_subs.add_parser("list", help="List installed packs")
    policy_list.set_defaults(func=cmd_policy_list)

    policy_install = policy_subs.add_parser("install", help="Install a policy pack")
    policy_install.add_argument("name", help="Pack name or 'file' for custom")
    policy_install.add_argument("--file", "-f", help="Custom policy file")
    policy_install.set_defaults(func=cmd_policy_install)

    policy_show = policy_subs.add_parser("show", help="Show pack details")
    policy_show.add_argument("name", help="Pack name")
    policy_show.set_defaults(func=cmd_policy_show)

    policy_enable = policy_subs.add_parser("enable", help="Enable a pack")
    policy_enable.add_argument("name", help="Pack name")
    policy_enable.set_defaults(func=cmd_policy_enable)

    policy_disable = policy_subs.add_parser("disable", help="Disable a pack")
    policy_disable.add_argument("name", help="Pack name")
    policy_disable.set_defaults(func=cmd_policy_disable)

    # claim
    claim_parser = subparsers.add_parser("claim", help="Verify claims")
    claim_subs = claim_parser.add_subparsers(dest="claim_cmd")

    claim_verify = claim_subs.add_parser("verify", help="Verify a claim")
    claim_verify.add_argument("claim", help="Claim name")
    claim_verify.add_argument("--actor", "-a", help="Who is making the claim")
    claim_verify.add_argument("--env", "-e", help="Environment")
    claim_verify.add_argument("--service", "-s", help="Service name")
    claim_verify.add_argument("--json", action="store_true", help="JSON output")
    claim_verify.set_defaults(func=cmd_claim_verify)

    claim_list = claim_subs.add_parser("list", help="List available claims")
    claim_list.add_argument("--env", "-e", help="Filter by environment")
    claim_list.set_defaults(func=cmd_claim_list)

    claim_approve = claim_subs.add_parser("approve", help="Add approval")
    claim_approve.add_argument("claim", help="Claim name")
    claim_approve.add_argument("--approver", "-a", required=True, help="Approver ID")
    claim_approve.add_argument("--role", "-r", required=True, help="Approver role")
    claim_approve.add_argument("--reason", help="Approval reason")
    claim_approve.set_defaults(func=cmd_claim_approve)

    claim_waive = claim_subs.add_parser("waive", help="Waive a requirement")
    claim_waive.add_argument("claim", help="Claim name")
    claim_waive.add_argument("requirement", help="Requirement ID")
    claim_waive.add_argument("--approver", "-a", required=True, help="Approver ID")
    claim_waive.add_argument("--role", "-r", required=True, help="Approver role")
    claim_waive.add_argument("--reason", required=True, help="Waiver reason")
    claim_waive.set_defaults(func=cmd_claim_waive)

    # incident
    incident_parser = subparsers.add_parser("incident", help="Manage incidents")
    incident_subs = incident_parser.add_subparsers(dest="incident_cmd")

    incident_create = incident_subs.add_parser("create", help="Create incident")
    incident_create.add_argument("title", help="Incident title")
    incident_create.add_argument("--severity", "-s", required=True,
                                  choices=["sev1", "sev2", "sev3", "sev4"])
    incident_create.add_argument("--service", help="Affected service")
    incident_create.add_argument("--env", "-e", help="Environment")
    incident_create.add_argument("--commander", "-c", help="Incident commander")
    incident_create.set_defaults(func=cmd_incident_create)

    incident_status = incident_subs.add_parser("status", help="Update status")
    incident_status.add_argument("id", help="Incident ID")
    incident_status.add_argument("status", choices=[s.value for s in IncidentStatus])
    incident_status.add_argument("--actor", "-a", help="Who is updating")
    incident_status.set_defaults(func=cmd_incident_status)

    incident_show = incident_subs.add_parser("show", help="Show incident")
    incident_show.add_argument("id", help="Incident ID")
    incident_show.set_defaults(func=cmd_incident_show)

    incident_list = incident_subs.add_parser("list", help="List incidents")
    incident_list.add_argument("--status", "-s", help="Filter by status")
    incident_list.set_defaults(func=cmd_incident_list)

    incident_claim = incident_subs.add_parser("claim", help="Make claim in incident")
    incident_claim.add_argument("incident_id", help="Incident ID")
    incident_claim.add_argument("claim", help="Claim name")
    incident_claim.add_argument("--actor", "-a", help="Who is claiming")
    incident_claim.set_defaults(func=cmd_incident_claim)

    # runbook
    runbook_parser = subparsers.add_parser("runbook", help="Manage runbooks")
    runbook_subs = runbook_parser.add_subparsers(dest="runbook_cmd")

    runbook_create = runbook_subs.add_parser("create", help="Create a runbook")
    runbook_create.add_argument("name", help="Runbook name")
    runbook_create.add_argument("--description", "-d", help="Runbook description")
    runbook_create.add_argument("--steps", help="Steps as JSON array")
    runbook_create.add_argument("--from-file", "-f", help="Load steps from JSON file")
    runbook_create.add_argument("--rollback", help="Rollback steps as JSON array")
    runbook_create.set_defaults(func=cmd_runbook_create)

    runbook_list = runbook_subs.add_parser("list", help="List runbooks")
    runbook_list.set_defaults(func=cmd_runbook_list)

    runbook_show = runbook_subs.add_parser("show", help="Show runbook details")
    runbook_show.add_argument("name", help="Runbook name")
    runbook_show.add_argument("--json", action="store_true", help="Output as JSON")
    runbook_show.set_defaults(func=cmd_runbook_show)

    runbook_verify = runbook_subs.add_parser("verify", help="Verify runbook execution")
    runbook_verify.add_argument("name", help="Runbook name")
    runbook_verify.add_argument("--log-file", "-l", help="Execution log file (JSON)")
    runbook_verify.add_argument("--step", "-s", type=int, help="Verify single step")
    runbook_verify.add_argument("--exit-code", type=int, help="Exit code for step verification")
    runbook_verify.add_argument("--output", "-o", help="Output for step verification")
    runbook_verify.set_defaults(func=cmd_runbook_verify)

    runbook_gen = runbook_subs.add_parser("generate-claims", help="Generate claims from runbook")
    runbook_gen.add_argument("name", help="Runbook name")
    runbook_gen.add_argument("--create-claim", "-c", action="store_true",
                              help="Create policy pack from runbook")
    runbook_gen.set_defaults(func=cmd_runbook_generate_claims)

    # Parse and dispatch
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
