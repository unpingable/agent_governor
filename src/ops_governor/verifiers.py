# SPDX-License-Identifier: Apache-2.0
"""
Specialized verifiers for SRE/Ops.

These go beyond basic proof collection to enforce operational policies:
- Runbook compliance
- Change windows / time-based enforcement
- Blast radius limits
- Precondition chains
"""

import hashlib
import json
import re
from datetime import datetime, timezone, time
from pathlib import Path
from typing import Any

from .types import (
    ProofType,
    ProofRequirement,
    ProofEvidence,
    ClaimDefinition,
    PolicyPack,
)


class RunbookVerifier:
    """
    Verify actions comply with documented runbooks.

    A runbook is a structured document (YAML/JSON/Markdown) that defines:
    - Steps to perform
    - Preconditions for each step
    - Expected outcomes
    - Rollback procedures
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.runbooks_dir = project_dir / ".ops-gov" / "runbooks"
        self.runbooks_dir.mkdir(parents=True, exist_ok=True)

    def load_runbook(self, name: str) -> dict[str, Any] | None:
        """Load a runbook by name."""
        # Try JSON first
        json_path = self.runbooks_dir / f"{name}.json"
        if json_path.exists():
            return json.loads(json_path.read_text())

        # Try YAML
        yaml_path = self.runbooks_dir / f"{name}.yaml"
        if yaml_path.exists():
            try:
                import yaml
                return yaml.safe_load(yaml_path.read_text())
            except ImportError:
                # No yaml support, skip
                pass

        return None

    def save_runbook(self, name: str, runbook: dict[str, Any]) -> None:
        """Save a runbook."""
        json_path = self.runbooks_dir / f"{name}.json"
        json_path.write_text(json.dumps(runbook, indent=2))

    def create_runbook(
        self,
        name: str,
        description: str,
        steps: list[dict[str, Any]],
        rollback_steps: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a new runbook."""
        runbook = {
            "name": name,
            "description": description,
            "version": "1.0",
            "steps": steps,
            "rollback_steps": rollback_steps or [],
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self.save_runbook(name, runbook)
        return runbook

    def verify_step(
        self,
        runbook_name: str,
        step_index: int,
        evidence: dict[str, Any],
    ) -> tuple[bool, str]:
        """
        Verify a runbook step was completed correctly.

        Returns (success, message).
        """
        runbook = self.load_runbook(runbook_name)
        if not runbook:
            return False, f"Runbook not found: {runbook_name}"

        if step_index >= len(runbook.get("steps", [])):
            return False, f"Step {step_index} not found in runbook"

        step = runbook["steps"][step_index]

        # Check preconditions
        if step.get("preconditions"):
            for precond in step["preconditions"]:
                if precond.get("type") == "previous_step":
                    # Check that previous step was completed
                    prev_idx = precond.get("step_index", step_index - 1)
                    if prev_idx >= 0 and not evidence.get(f"step_{prev_idx}_complete"):
                        return False, f"Precondition failed: step {prev_idx} not complete"

        # Check expected evidence
        if step.get("expected_evidence"):
            for exp in step["expected_evidence"]:
                exp_type = exp.get("type")
                if exp_type == "command_exit_code":
                    if evidence.get("exit_code") != exp.get("value", 0):
                        return False, f"Expected exit code {exp.get('value', 0)}, got {evidence.get('exit_code')}"
                elif exp_type == "output_contains":
                    if exp.get("pattern") not in evidence.get("output", ""):
                        return False, "Output doesn't contain expected pattern"

        return True, f"Step {step_index} verified"

    def verify_runbook_execution(
        self,
        runbook_name: str,
        execution_log: list[dict[str, Any]],
    ) -> tuple[bool, list[str]]:
        """
        Verify an entire runbook execution.

        execution_log is a list of step results with evidence.
        Returns (all_passed, list_of_messages).
        """
        runbook = self.load_runbook(runbook_name)
        if not runbook:
            return False, [f"Runbook not found: {runbook_name}"]

        messages = []
        all_passed = True
        completed_steps = set()

        for entry in execution_log:
            step_idx = entry.get("step_index")
            evidence = entry.get("evidence", {})

            # Mark as potentially complete for precondition checking
            evidence[f"step_{step_idx}_complete"] = True
            for prev_idx in completed_steps:
                evidence[f"step_{prev_idx}_complete"] = True

            success, msg = self.verify_step(runbook_name, step_idx, evidence)
            messages.append(f"Step {step_idx}: {msg}")

            if success:
                completed_steps.add(step_idx)
            else:
                all_passed = False

        # Check all required steps were completed
        required_steps = set(range(len(runbook.get("steps", []))))
        missing = required_steps - completed_steps
        if missing:
            all_passed = False
            messages.append(f"Missing steps: {sorted(missing)}")

        return all_passed, messages

    def generate_claim_requirements(self, runbook_name: str) -> list[ProofRequirement]:
        """
        Generate claim requirements from a runbook.

        Each runbook step becomes a proof requirement.
        """
        runbook = self.load_runbook(runbook_name)
        if not runbook:
            return []

        requirements = []
        for i, step in enumerate(runbook.get("steps", [])):
            # Convert step to proof requirement
            if step.get("command"):
                req = ProofRequirement(
                    proof_type=ProofType.COMMAND_OUTPUT,
                    description=step.get("description", f"Runbook step {i}"),
                    command=step["command"],
                    expected_exit_code=step.get("expected_exit_code", 0),
                    expected_pattern=step.get("expected_pattern"),
                )
                requirements.append(req)
            elif step.get("file_check"):
                req = ProofRequirement(
                    proof_type=ProofType.FILE_EXISTS,
                    description=step.get("description", f"Runbook step {i}"),
                    file_path=step["file_check"],
                )
                requirements.append(req)
            elif step.get("approval_required"):
                req = ProofRequirement(
                    proof_type=ProofType.APPROVAL,
                    description=step.get("description", f"Runbook step {i}"),
                    approver_role=step.get("approver_role"),
                )
                requirements.append(req)

        return requirements


class TimeWindowVerifier:
    """
    Verify actions occur within allowed time windows.

    Supports:
    - Fixed time ranges (e.g., 09:00-17:00 UTC)
    - Day-of-week restrictions
    - Blackout periods (no changes during certain times)
    - Emergency overrides
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.windows_file = project_dir / ".ops-gov" / "time_windows.json"
        self._windows: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load time windows from disk."""
        if self.windows_file.exists():
            self._windows = json.loads(self.windows_file.read_text())

    def _save(self) -> None:
        """Save time windows to disk."""
        self.windows_file.parent.mkdir(parents=True, exist_ok=True)
        self.windows_file.write_text(json.dumps(self._windows, indent=2))

    def define_window(
        self,
        name: str,
        start_time: str,
        end_time: str,
        days: list[str] | None = None,
        timezone_str: str = "UTC",
        description: str = "",
    ) -> None:
        """
        Define a change window.

        Args:
            name: Window identifier (e.g., 'business_hours', 'maintenance_window')
            start_time: Start time in HH:MM format
            end_time: End time in HH:MM format
            days: List of allowed days (e.g., ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'])
            timezone_str: Timezone name
            description: Human description
        """
        self._windows[name] = {
            "start_time": start_time,
            "end_time": end_time,
            "days": days or ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
            "timezone": timezone_str,
            "description": description,
        }
        self._save()

    def define_blackout(
        self,
        name: str,
        start: datetime,
        end: datetime,
        reason: str,
    ) -> None:
        """Define a blackout period where no changes are allowed."""
        self._windows[f"blackout:{name}"] = {
            "type": "blackout",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "reason": reason,
        }
        self._save()

    def is_within_window(
        self,
        window_name: str,
        at_time: datetime | None = None,
    ) -> tuple[bool, str]:
        """
        Check if a time is within a change window.

        Returns (allowed, reason).
        """
        if at_time is None:
            at_time = datetime.now(timezone.utc)

        window = self._windows.get(window_name)
        if not window:
            return False, f"Window not defined: {window_name}"

        if window.get("type") == "blackout":
            # Blackout periods are inverse - return False if within
            start = datetime.fromisoformat(window["start"])
            end = datetime.fromisoformat(window["end"])
            if start <= at_time <= end:
                return False, f"Within blackout period: {window['reason']}"
            return True, "Outside blackout period"

        # Check day of week
        day_name = at_time.strftime("%A").lower()
        if day_name not in [d.lower() for d in window.get("days", [])]:
            return False, f"Day {day_name} not in allowed days"

        # Check time range
        start_parts = window["start_time"].split(":")
        end_parts = window["end_time"].split(":")
        start_time = time(int(start_parts[0]), int(start_parts[1]))
        end_time = time(int(end_parts[0]), int(end_parts[1]))
        current_time = at_time.time()

        if start_time <= current_time <= end_time:
            return True, f"Within window {window_name}"
        else:
            return False, f"Outside window hours ({window['start_time']}-{window['end_time']})"

    def check_blackouts(self, at_time: datetime | None = None) -> tuple[bool, str | None]:
        """
        Check if any blackout periods are active.

        Returns (allowed, active_blackout_name_or_none).
        """
        if at_time is None:
            at_time = datetime.now(timezone.utc)

        for name, window in self._windows.items():
            if window.get("type") == "blackout":
                start = datetime.fromisoformat(window["start"])
                end = datetime.fromisoformat(window["end"])
                if start <= at_time <= end:
                    return False, name

        return True, None

    def create_requirement(self, window_name: str) -> ProofRequirement:
        """Create a proof requirement for a time window."""
        return ProofRequirement(
            proof_type=ProofType.TIME_WINDOW,
            description=f"Must be within {window_name} change window",
            time_window_start=self._windows.get(window_name, {}).get("start_time"),
            time_window_end=self._windows.get(window_name, {}).get("end_time"),
        )


class BlastRadiusVerifier:
    """
    Verify changes don't exceed allowed blast radius.

    Blast radius is defined as the scope of potential impact:
    - Number of services affected
    - Percentage of traffic affected
    - Geographic regions affected
    - User segments affected
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.limits_file = project_dir / ".ops-gov" / "blast_limits.json"
        self._limits: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load blast radius limits from disk."""
        if self.limits_file.exists():
            self._limits = json.loads(self.limits_file.read_text())

    def _save(self) -> None:
        """Save blast radius limits to disk."""
        self.limits_file.parent.mkdir(parents=True, exist_ok=True)
        self.limits_file.write_text(json.dumps(self._limits, indent=2))

    def define_limit(
        self,
        name: str,
        max_services: int | None = None,
        max_traffic_percent: float | None = None,
        max_regions: int | None = None,
        allowed_regions: list[str] | None = None,
        requires_approval_above: dict[str, Any] | None = None,
    ) -> None:
        """Define blast radius limits."""
        self._limits[name] = {
            "max_services": max_services,
            "max_traffic_percent": max_traffic_percent,
            "max_regions": max_regions,
            "allowed_regions": allowed_regions,
            "requires_approval_above": requires_approval_above,
        }
        self._save()

    def check_blast_radius(
        self,
        limit_name: str,
        affected_services: list[str] | None = None,
        traffic_percent: float | None = None,
        regions: list[str] | None = None,
    ) -> tuple[bool, list[str], bool]:
        """
        Check if a change exceeds blast radius limits.

        Returns (within_limits, violations, requires_approval).
        """
        limit = self._limits.get(limit_name)
        if not limit:
            return True, [], False  # No limits defined, allow

        violations = []
        requires_approval = False

        # Check services
        if limit.get("max_services") and affected_services:
            if len(affected_services) > limit["max_services"]:
                violations.append(f"Affects {len(affected_services)} services (max: {limit['max_services']})")

        # Check traffic percentage
        if limit.get("max_traffic_percent") and traffic_percent:
            if traffic_percent > limit["max_traffic_percent"]:
                violations.append(f"Affects {traffic_percent}% traffic (max: {limit['max_traffic_percent']}%)")

        # Check regions
        if limit.get("max_regions") and regions:
            if len(regions) > limit["max_regions"]:
                violations.append(f"Affects {len(regions)} regions (max: {limit['max_regions']})")

        if limit.get("allowed_regions") and regions:
            disallowed = set(regions) - set(limit["allowed_regions"])
            if disallowed:
                violations.append(f"Affects disallowed regions: {disallowed}")

        # Check if approval required
        approval_thresholds = limit.get("requires_approval_above", {})
        if approval_thresholds:
            if traffic_percent and traffic_percent > approval_thresholds.get("traffic_percent", 100):
                requires_approval = True
            if affected_services and len(affected_services) > approval_thresholds.get("services", 999):
                requires_approval = True

        return len(violations) == 0, violations, requires_approval


class PreconditionChainVerifier:
    """
    Verify precondition chains are satisfied.

    Some claims require other claims to be satisfied first.
    This verifier tracks the chain and ensures order.
    """

    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.chains_file = project_dir / ".ops-gov" / "precondition_chains.json"
        self._chains: dict[str, list[str]] = {}
        self._satisfied: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        """Load precondition chains from disk."""
        if self.chains_file.exists():
            data = json.loads(self.chains_file.read_text())
            self._chains = data.get("chains", {})
            self._satisfied = data.get("satisfied", {})

    def _save(self) -> None:
        """Save to disk."""
        self.chains_file.parent.mkdir(parents=True, exist_ok=True)
        self.chains_file.write_text(json.dumps({
            "chains": self._chains,
            "satisfied": self._satisfied,
        }, indent=2))

    def define_chain(self, final_claim: str, prerequisites: list[str]) -> None:
        """
        Define a precondition chain.

        Example: define_chain("deploy_complete", ["tests_pass", "deploy_approved", "deploy_started"])
        """
        self._chains[final_claim] = prerequisites
        self._save()

    def mark_satisfied(
        self,
        claim: str,
        context_id: str,
        evidence: dict[str, Any],
    ) -> None:
        """Mark a claim as satisfied in a context (e.g., a deployment ID)."""
        if context_id not in self._satisfied:
            self._satisfied[context_id] = {}

        self._satisfied[context_id][claim] = {
            "satisfied_at": datetime.now(timezone.utc).isoformat(),
            "evidence": evidence,
        }
        self._save()

    def check_prerequisites(
        self,
        claim: str,
        context_id: str,
    ) -> tuple[bool, list[str]]:
        """
        Check if prerequisites for a claim are satisfied.

        Returns (all_satisfied, missing_prerequisites).
        """
        prerequisites = self._chains.get(claim, [])
        if not prerequisites:
            return True, []

        context_satisfied = self._satisfied.get(context_id, {})
        missing = [p for p in prerequisites if p not in context_satisfied]

        return len(missing) == 0, missing

    def get_chain_status(self, claim: str, context_id: str) -> dict[str, Any]:
        """Get the status of all prerequisites in a chain."""
        prerequisites = self._chains.get(claim, [])
        context_satisfied = self._satisfied.get(context_id, {})

        status = {}
        for prereq in prerequisites:
            if prereq in context_satisfied:
                status[prereq] = {
                    "satisfied": True,
                    "satisfied_at": context_satisfied[prereq]["satisfied_at"],
                }
            else:
                status[prereq] = {"satisfied": False}

        return status
