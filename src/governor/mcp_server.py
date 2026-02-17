# SPDX-License-Identifier: Apache-2.0
"""
MCP Server for Governor.

Exposes governor functionality as MCP tools that can be called by
language models like Claude.

The server provides tools for:
- Proposing changes with claims
- Verifying proposals
- Applying verified proposals
- Querying facts and decisions
- Managing operating envelopes

Extended surface for Claude Code integration:
- Querying anchors (constraints) before generation
- Checking text against constraints during generation
- Viewing docket (pending cases) and claim status
- Recording rulings on violations
- Staleness checking and reverification

Usage:
    governor mcp serve

Or configure in Claude Desktop's MCP settings:
    {
      "mcpServers": {
        "governor": {
          "command": "governor",
          "args": ["mcp", "serve"]
        }
      }
    }
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

# MCP protocol types
# These follow the MCP specification for tool definitions

class MCPTool:
    """Definition of an MCP tool."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: dict[str, Any],
        handler: callable,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.handler = handler

    def to_dict(self) -> dict[str, Any]:
        """Convert to MCP tool definition format."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.parameters,
                "required": [
                    k for k, v in self.parameters.items()
                    if v.get("required", False)
                ],
            },
        }


class GovernorMCPServer:
    """MCP server exposing governor tools."""

    def __init__(self, root: Path):
        self.root = root
        self.gov_dir = root / ".governor"
        self.tools = self._create_tools()

    def _create_tools(self) -> dict[str, MCPTool]:
        """Create the available tools."""
        return {
            "governor_propose": MCPTool(
                name="governor_propose",
                description="Create a proposal with claims. Claims specify what you're asserting about the codebase.",
                parameters={
                    "claims": {
                        "type": "array",
                        "description": "List of claims. Each claim is an object with 'type' and type-specific fields.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["file_exists", "tests_pass", "decision", "changeset"],
                                },
                                "path": {"type": "string"},
                                "command": {"type": "string"},
                                "topic": {"type": "string"},
                                "choice": {"type": "string"},
                                "diff": {"type": "string"},
                            },
                        },
                        "required": True,
                    },
                },
                handler=self._handle_propose,
            ),
            "governor_verify": MCPTool(
                name="governor_verify",
                description="Verify a proposal by running checks and producing receipts.",
                parameters={
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the proposal to verify",
                        "required": True,
                    },
                },
                handler=self._handle_verify,
            ),
            "governor_apply": MCPTool(
                name="governor_apply",
                description="Apply a verified proposal, committing the changes.",
                parameters={
                    "proposal_id": {
                        "type": "string",
                        "description": "The ID of the proposal to apply",
                        "required": True,
                    },
                },
                handler=self._handle_apply,
            ),
            "governor_status": MCPTool(
                name="governor_status",
                description="Get the status of proposals.",
                parameters={
                    "proposal_id": {
                        "type": "string",
                        "description": "Optional specific proposal ID to check",
                        "required": False,
                    },
                },
                handler=self._handle_status,
            ),
            "governor_facts": MCPTool(
                name="governor_facts",
                description="Query recorded facts from the ledger.",
                parameters={
                    "topic": {
                        "type": "string",
                        "description": "Optional topic to filter by",
                        "required": False,
                    },
                },
                handler=self._handle_facts,
            ),
            "governor_decisions": MCPTool(
                name="governor_decisions",
                description="Query recorded decisions from the ledger.",
                parameters={
                    "topic": {
                        "type": "string",
                        "description": "Optional topic to filter by",
                        "required": False,
                    },
                },
                handler=self._handle_decisions,
            ),
            "governor_envelope": MCPTool(
                name="governor_envelope",
                description="Get or set the operating envelope (exploratory or strict mode).",
                parameters={
                    "mode": {
                        "type": "string",
                        "enum": ["exploratory", "strict"],
                        "description": "Optional mode to set. If not provided, returns current mode.",
                        "required": False,
                    },
                },
                handler=self._handle_envelope,
            ),
            # =========================================================================
            # Extended surface for Claude Code integration
            # =========================================================================
            "governor_get_anchors": MCPTool(
                name="governor_get_anchors",
                description="Get all continuity anchors (constraints) for this project. Call this BEFORE generating code to know what constraints to respect.",
                parameters={
                    "type": {
                        "type": "string",
                        "description": "Optional anchor type filter (canon, prohibition, persona, definition, requirement, style)",
                        "required": False,
                    },
                },
                handler=self._handle_get_anchors,
            ),
            "governor_get_docket": MCPTool(
                name="governor_get_docket",
                description="Get pending cases on the docket that need attention (violations awaiting ruling, stale claims).",
                parameters={
                    "case_type": {
                        "type": "string",
                        "enum": ["contested", "stale", "all"],
                        "description": "Filter by case type. Default: all",
                        "required": False,
                    },
                },
                handler=self._handle_get_docket,
            ),
            "governor_claim_status": MCPTool(
                name="governor_claim_status",
                description="Get claim health summary: what's live, degrading, stale, or contested. The 'weather report' for epistemic state.",
                parameters={},
                handler=self._handle_claim_status,
            ),
            "governor_check_text": MCPTool(
                name="governor_check_text",
                description="Check arbitrary text against all anchors. Use this to verify output BEFORE presenting to user.",
                parameters={
                    "text": {
                        "type": "string",
                        "description": "The text to check against anchors",
                        "required": True,
                    },
                },
                handler=self._handle_check_text,
            ),
            "governor_check_file": MCPTool(
                name="governor_check_file",
                description="Check a file for security and continuity violations.",
                parameters={
                    "path": {
                        "type": "string",
                        "description": "Path to the file to check",
                        "required": True,
                    },
                },
                handler=self._handle_check_file,
            ),
            "governor_record_ruling": MCPTool(
                name="governor_record_ruling",
                description="Record a ruling on a docket case (after human decision). Used when human chooses fix/revise/proceed.",
                parameters={
                    "case_number": {
                        "type": "integer",
                        "description": "The case number from the docket",
                        "required": True,
                    },
                    "ruling": {
                        "type": "string",
                        "enum": ["sustain", "amend", "except", "reverify", "dismiss"],
                        "description": "The ruling type",
                        "required": True,
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Optional rationale for the ruling",
                        "required": False,
                    },
                    "scope": {
                        "type": "string",
                        "enum": ["single_instance", "session", "project"],
                        "description": "Scope for exception rulings. Default: single_instance",
                        "required": False,
                    },
                },
                handler=self._handle_record_ruling,
            ),
            "governor_get_constraints_for_fix": MCPTool(
                name="governor_get_constraints_for_fix",
                description="Get the specific constraints that need to be respected when regenerating after a violation. Call this before attempting a fix.",
                parameters={
                    "case_number": {
                        "type": "integer",
                        "description": "The case number from the docket",
                        "required": True,
                    },
                },
                handler=self._handle_get_constraints_for_fix,
            ),
            "governor_check_staleness": MCPTool(
                name="governor_check_staleness",
                description="Check which claims are stale or decaying. Returns claims that need reverification.",
                parameters={
                    "threshold": {
                        "type": "number",
                        "description": "Confidence threshold below which claims are considered stale. Default: 0.5",
                        "required": False,
                    },
                },
                handler=self._handle_check_staleness,
            ),
            "governor_reverify": MCPTool(
                name="governor_reverify",
                description="Request reverification of a stale claim.",
                parameters={
                    "claim_id": {
                        "type": "string",
                        "description": "The claim ID to reverify",
                        "required": True,
                    },
                },
                handler=self._handle_reverify,
            ),
            # =========================================================================
            # Code Autopilot: Intent and Override Management
            # =========================================================================
            "governor_get_intent": MCPTool(
                name="governor_get_intent",
                description="Get current resolved intent with provenance. Shows active profile, scope, timebox, and how it was determined.",
                parameters={},
                handler=self._handle_get_intent,
            ),
            "governor_set_intent": MCPTool(
                name="governor_set_intent",
                description="Set session intent (profile, scope, timebox). Controls Governor enforcement level for this session.",
                parameters={
                    "profile": {
                        "type": "string",
                        "enum": ["greenfield", "established", "production", "hotfix", "refactor"],
                        "description": "Profile name",
                        "required": True,
                    },
                    "scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Allowed path patterns (glob)",
                        "required": False,
                    },
                    "deny": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Denied path patterns (glob)",
                        "required": False,
                    },
                    "timebox_minutes": {
                        "type": "number",
                        "description": "Auto-expire after this many minutes",
                        "required": False,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this intent is being set",
                        "required": False,
                    },
                },
                handler=self._handle_set_intent,
            ),
            "governor_suggest_profile": MCPTool(
                name="governor_suggest_profile",
                description="Get profile suggestion based on context (branch name, files touched).",
                parameters={
                    "branch": {
                        "type": "string",
                        "description": "Current git branch name",
                        "required": False,
                    },
                    "files_touched": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of files being modified",
                        "required": False,
                    },
                },
                handler=self._handle_suggest_profile,
            ),
            "governor_override": MCPTool(
                name="governor_override",
                description="Create scoped override for invariant constraint. Allows temporary exception with audit trail.",
                parameters={
                    "anchor_id": {
                        "type": "string",
                        "description": "ID of the anchor (invariant constraint) to override",
                        "required": True,
                    },
                    "reason": {
                        "type": "string",
                        "description": "Why this override is needed",
                        "required": True,
                    },
                    "scope": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Path patterns covered by this override",
                        "required": True,
                    },
                    "expires_hours": {
                        "type": "number",
                        "description": "Hours until override expires",
                        "required": True,
                    },
                },
                handler=self._handle_override,
            ),
            "governor_override_list": MCPTool(
                name="governor_override_list",
                description="List active overrides.",
                parameters={
                    "include_expired": {
                        "type": "boolean",
                        "description": "Include expired/revoked overrides. Default: false",
                        "required": False,
                    },
                },
                handler=self._handle_override_list,
            ),
        }

    def _ensure_initialized(self) -> tuple[bool, str]:
        """Ensure governor is initialized."""
        if not self.gov_dir.exists():
            return False, "Governor not initialized. Run 'governor init' first."
        return True, ""

    def _load_proposals(self) -> dict[str, dict]:
        """Load proposals from disk."""
        proposals_path = self.gov_dir / "proposals.json"
        if not proposals_path.exists():
            return {}
        return json.loads(proposals_path.read_text())

    def _save_proposals(self, proposals: dict[str, dict]) -> None:
        """Save proposals to disk."""
        proposals_path = self.gov_dir / "proposals.json"
        proposals_path.write_text(json.dumps(proposals, indent=2))

    def _handle_propose(self, claims: list[dict]) -> dict[str, Any]:
        """Handle propose tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .claims import file_exists, claim_tests_pass, decision, changeset, Claim
        from .fsm import create_proposal

        parsed_claims = []
        for claim_data in claims:
            claim_type = claim_data.get("type")

            if claim_type == "file_exists":
                if "path" not in claim_data:
                    return {"success": False, "error": "file_exists claim requires 'path'"}
                parsed_claims.append(file_exists(claim_data["path"]))

            elif claim_type == "tests_pass":
                if "command" not in claim_data:
                    return {"success": False, "error": "tests_pass claim requires 'command'"}
                cmd = tuple(claim_data["command"].split())
                parsed_claims.append(claim_tests_pass(cmd))

            elif claim_type == "decision":
                if "topic" not in claim_data or "choice" not in claim_data:
                    return {"success": False, "error": "decision claim requires 'topic' and 'choice'"}
                parsed_claims.append(decision(claim_data["topic"], claim_data["choice"]))

            elif claim_type == "changeset":
                if "diff" not in claim_data:
                    return {"success": False, "error": "changeset claim requires 'diff'"}
                parsed_claims.append(changeset(claim_data["diff"]))

            else:
                return {"success": False, "error": f"Unknown claim type: {claim_type}"}

        if not parsed_claims:
            return {"success": False, "error": "No claims provided"}

        # Create proposal
        fsm = create_proposal(parsed_claims)
        fsm.propose()

        # Save proposal
        proposals = self._load_proposals()
        proposals[str(fsm.proposal.id)] = fsm.proposal.to_dict()
        self._save_proposals(proposals)

        return {
            "success": True,
            "proposal_id": str(fsm.proposal.id),
            "state": fsm.state.value,
            "claims": [c.describe() for c in parsed_claims],
        }

    def _handle_verify(self, proposal_id: str) -> dict[str, Any]:
        """Handle verify tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .fsm import Proposal, ProposalFSM, ProposalState, RejectionInfo, ClaimError
        from .envelopes import get_current_envelope
        from .ledgers import DecisionLedger
        from .verifiers import create_default_verifiers
        from .claims import ClaimType

        proposals = self._load_proposals()
        if proposal_id not in proposals:
            return {"success": False, "error": f"Proposal {proposal_id} not found"}

        proposal = Proposal.from_dict(proposals[proposal_id])
        fsm = ProposalFSM(proposal)

        if fsm.state != ProposalState.PROPOSED:
            return {"success": False, "error": f"Proposal is in {fsm.state.value} state, cannot verify"}

        envelope = get_current_envelope(self.gov_dir)

        # Check for conflicts
        decision_ledger = DecisionLedger(self.gov_dir)
        conflicts = []

        if not envelope.allow_conflicts:
            for i, claim in enumerate(proposal.claims):
                if claim.type == ClaimType.DECISION:
                    conflict = decision_ledger.check_conflict(claim)
                    if conflict:
                        conflicts.append({
                            "claim_index": i,
                            "proposed": {"topic": claim.topic, "choice": claim.choice},
                            "existing": {"topic": conflict.topic, "choice": conflict.choice},
                        })

        if conflicts:
            rejection = RejectionInfo(
                reason="Decision conflicts",
                conflicting_decisions=[],
            )
            fsm.reject(rejection)
            proposals[proposal_id] = fsm.proposal.to_dict()
            self._save_proposals(proposals)

            return {
                "success": False,
                "state": "rejected",
                "conflicts": conflicts,
                "suggestion": "Use 'governor revise' to change existing decisions",
            }

        # Run verifiers
        verifier = create_default_verifiers(self.root)
        results = verifier.verify_all(proposal.claims)

        failed = []
        receipts = []
        for i, result in enumerate(results):
            if result.success:
                receipts.append(result.receipt)
            else:
                failed.append({"claim_index": i, "error": result.error})

        if failed and envelope.require_receipts:
            rejection = RejectionInfo(
                reason="Verification failed",
                failed_claims=[f["claim_index"] for f in failed],
            )
            fsm.reject(rejection)
            proposals[proposal_id] = fsm.proposal.to_dict()
            self._save_proposals(proposals)

            return {
                "success": False,
                "state": "rejected",
                "failed_claims": failed,
            }

        # Create stub receipts for exploratory mode
        if not receipts or (failed and not envelope.require_receipts):
            from .receipts import FileSnapshot
            for i in range(len(proposal.claims)):
                if i >= len(receipts):
                    receipts.append(FileSnapshot(
                        path=f"exploratory:{i}",
                        blob_hash="exploratory",
                        size_bytes=0,
                        timestamp=datetime.now(timezone.utc),
                    ))

        fsm.verify(receipts)
        proposals[proposal_id] = fsm.proposal.to_dict()
        self._save_proposals(proposals)

        return {
            "success": True,
            "state": "verified",
            "receipts_count": len(receipts),
            "envelope": envelope.mode.value,
        }

    def _handle_apply(self, proposal_id: str) -> dict[str, Any]:
        """Handle apply tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .fsm import Proposal, ProposalFSM, ProposalState
        from .envelopes import get_current_envelope
        from .ledgers import FactLedger, DecisionLedger
        from .claims import ClaimType

        proposals = self._load_proposals()
        if proposal_id not in proposals:
            return {"success": False, "error": f"Proposal {proposal_id} not found"}

        proposal = Proposal.from_dict(proposals[proposal_id])
        fsm = ProposalFSM(proposal)

        if fsm.state != ProposalState.VERIFIED:
            return {"success": False, "error": f"Proposal is in {fsm.state.value} state, must be verified"}

        envelope = get_current_envelope(self.gov_dir)
        fact_ledger = FactLedger(self.gov_dir)
        decision_ledger = DecisionLedger(self.gov_dir)

        applied_facts = []
        applied_decisions = []

        for claim, receipt in zip(proposal.claims, proposal.receipts):
            if claim.type == ClaimType.DECISION:
                if envelope.commit_decisions:
                    decision_ledger.add(claim)
                    applied_decisions.append({"topic": claim.topic, "choice": claim.choice})
            else:
                fact_ledger.add(claim, receipt)
                applied_facts.append(claim.describe())

        fsm.apply()
        proposals[proposal_id] = fsm.proposal.to_dict()
        self._save_proposals(proposals)

        return {
            "success": True,
            "state": "applied",
            "facts_added": len(applied_facts),
            "decisions_added": len(applied_decisions),
        }

    def _handle_status(self, proposal_id: str | None = None) -> dict[str, Any]:
        """Handle status tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .fsm import Proposal

        proposals = self._load_proposals()

        if proposal_id:
            if proposal_id not in proposals:
                return {"success": False, "error": f"Proposal {proposal_id} not found"}

            proposal = Proposal.from_dict(proposals[proposal_id])
            return {
                "success": True,
                "proposal": {
                    "id": str(proposal.id),
                    "state": proposal.state.value,
                    "claims": [c.describe() for c in proposal.claims],
                    "created_at": proposal.created_at.isoformat(),
                },
            }

        # Return summary of all proposals
        summary = []
        for pid, data in list(proposals.items())[-10:]:  # Last 10
            proposal = Proposal.from_dict(data)
            summary.append({
                "id": pid,
                "state": proposal.state.value,
                "claims_count": len(proposal.claims),
            })

        return {
            "success": True,
            "total": len(proposals),
            "recent": summary,
        }

    def _handle_facts(self, topic: str | None = None) -> dict[str, Any]:
        """Handle facts tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .ledgers import FactLedger

        ledger = FactLedger(self.gov_dir)
        facts = ledger.all()

        result = []
        for fact in facts:
            if topic and topic.lower() not in fact.claim.describe().lower():
                continue
            result.append({
                "id": str(fact.id),
                "claim": fact.claim.describe(),
                "created_at": fact.created_at.isoformat(),
            })

        return {
            "success": True,
            "count": len(result),
            "facts": result,
        }

    def _handle_decisions(self, topic: str | None = None) -> dict[str, Any]:
        """Handle decisions tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .ledgers import DecisionLedger

        ledger = DecisionLedger(self.gov_dir)
        decisions = ledger.query(topic)

        result = []
        for dec in decisions:
            result.append({
                "id": str(dec.id),
                "topic": dec.topic,
                "choice": dec.choice,
                "rationale": dec.rationale,
            })

        return {
            "success": True,
            "count": len(result),
            "decisions": result,
        }

    def _handle_envelope(self, mode: str | None = None) -> dict[str, Any]:
        """Handle envelope tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        from .envelopes import EnvelopeMode, get_current_envelope, set_envelope

        if mode:
            try:
                envelope_mode = EnvelopeMode(mode)
                set_envelope(self.gov_dir, envelope_mode)
                return {
                    "success": True,
                    "action": "set",
                    "mode": mode,
                }
            except ValueError:
                return {"success": False, "error": f"Unknown mode: {mode}"}

        current = get_current_envelope(self.gov_dir)
        return {
            "success": True,
            "mode": current.mode.value,
            "require_receipts": current.require_receipts,
            "commit_decisions": current.commit_decisions,
            "allow_conflicts": current.allow_conflicts,
        }

    # =========================================================================
    # Extended handlers for Claude Code integration
    # =========================================================================

    def _handle_get_anchors(self, type: str | None = None) -> dict[str, Any]:
        """Handle get_anchors tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .continuity import create_registry

            registry = create_registry(self.gov_dir)
            anchors = registry.all()

            result = []
            for anchor in anchors:
                if type and anchor.anchor_type.value != type:
                    continue
                result.append({
                    "id": anchor.id,
                    "type": anchor.anchor_type.value,
                    "description": anchor.description,
                    "severity": anchor.severity.value,
                    "forbidden_patterns": anchor.forbidden_patterns,
                    "required_patterns": anchor.required_patterns,
                })

            return {
                "success": True,
                "count": len(result),
                "anchors": result,
                "hint": "Respect these constraints when generating code/text",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_docket(self, case_type: str | None = None) -> dict[str, Any]:
        """Handle get_docket tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .docket import DocketManager, CaseType

            docket = DocketManager(governor_dir=self.gov_dir)
            cases = docket.get_docket()

            result = []
            for case in cases:
                if case_type and case_type != "all":
                    if case.case_type.value != case_type:
                        continue
                result.append({
                    "case_number": case.case_number,
                    "type": case.case_type.value,
                    "claim_id": case.claim_id,
                    "anchor_id": case.anchor_id,
                    "status": case.status.value,
                    "description": case.description,
                })

            return {
                "success": True,
                "count": len(result),
                "cases": result,
                "hint": "These cases need rulings. Use governor_record_ruling to resolve.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_claim_status(self) -> dict[str, Any]:
        """Handle claim_status tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .epistemic import EpistemicLedger
            from .claim_status import ClaimStatusDashboard
            from .docket import DocketManager

            ledger = EpistemicLedger()
            docket = DocketManager(governor_dir=self.gov_dir)
            dashboard = ClaimStatusDashboard(ledger, docket=docket)

            summary = dashboard.get_summary()

            return {
                "success": True,
                "summary": {
                    "live_count": summary.live_count,
                    "live_confidence_avg": summary.live_confidence_avg,
                    "degrading_count": summary.degrading_count,
                    "stale_count": summary.stale_count,
                    "contested_count": summary.contested_count,
                    "total_claims": summary.total_claims,
                    "health_score": summary.health_score,
                },
                "attention_needed": summary.stale_count > 0 or summary.contested_count > 0,
                "hint": "Run governor_get_docket for details on contested/stale cases",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_check_text(self, text: str) -> dict[str, Any]:
        """Handle check_text tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .continuity import create_registry, ContinuityChecker

            registry = create_registry(self.gov_dir)
            checker = ContinuityChecker()
            anchors = registry.all()
            report = checker.check(text, anchors)

            violations = []
            for v in report.violations:
                violations.append({
                    "anchor_id": v.anchor_id,
                    "description": v.description,
                    "matched_text": v.matched_text,
                    "severity": v.severity.value,
                    "action": v.recommended_action.value,
                })

            return {
                "success": True,
                "clean": len(violations) == 0,
                "violations": violations,
                "blocking": any(v["severity"] == "reject" for v in violations),
                "hint": "If blocking, use governor_get_constraints_for_fix to get constraints for regeneration" if violations else "Text passes all constraints",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_check_file(self, path: str) -> dict[str, Any]:
        """Handle check_file tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .check import run_check

            file_path = Path(path)
            if not file_path.is_absolute():
                file_path = self.root / file_path

            if not file_path.exists():
                return {"success": False, "error": f"File not found: {path}"}

            content = file_path.read_text()
            result = run_check(
                content,
                file_path=str(file_path),
                governor_dir=self.gov_dir,
                run_security=True,
                run_continuity=True,
            )

            findings = []
            for f in result.findings:
                findings.append({
                    "source": f.source,
                    "severity": f.severity,
                    "message": f.message,
                    "line": f.range.start.line if f.range else None,
                })

            return {
                "success": True,
                "path": str(file_path),
                "clean": len(findings) == 0,
                "findings": findings,
                "blocking": any(f["severity"] in ("error", "reject") for f in findings),
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_record_ruling(
        self,
        case_number: int,
        ruling: str,
        rationale: str | None = None,
        scope: str | None = None,
    ) -> dict[str, Any]:
        """Handle record_ruling tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .docket import DocketManager

            docket = DocketManager(governor_dir=self.gov_dir)

            if ruling == "sustain":
                precedent = docket.rule_sustain(case_number, rationale or "")
            elif ruling == "amend":
                precedent = docket.rule_amend(case_number, rationale or "")
            elif ruling == "except":
                precedent = docket.rule_grant_exception(
                    case_number,
                    scope=scope or "single_instance",
                    rationale=rationale or "",
                )
            elif ruling == "reverify":
                precedent = docket.rule_reverify(case_number, rationale or "")
            elif ruling == "dismiss":
                precedent = docket.rule_dismiss(case_number, rationale or "")
            else:
                return {"success": False, "error": f"Unknown ruling type: {ruling}"}

            return {
                "success": True,
                "precedent_id": precedent.id,
                "case_number": case_number,
                "ruling": ruling,
                "scope": precedent.scope,
            }
        except ValueError as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_get_constraints_for_fix(self, case_number: int) -> dict[str, Any]:
        """Handle get_constraints_for_fix tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .docket import DocketManager, CaseType
            from .continuity import create_registry

            docket = DocketManager(governor_dir=self.gov_dir)
            case = docket.get_case(case_number)

            if case is None:
                return {"success": False, "error": f"Case #{case_number} not found"}

            if case.case_type != CaseType.CONTESTED:
                return {
                    "success": False,
                    "error": f"Case #{case_number} is not a contested case (type: {case.case_type.value})",
                }

            # Get the anchor that was violated
            constraints = []
            if case.anchor_id:
                registry = create_registry(self.gov_dir)
                anchor = registry.get(case.anchor_id)
                if anchor:
                    constraints.append({
                        "anchor_id": anchor.id,
                        "description": anchor.description,
                        "forbidden_patterns": anchor.forbidden_patterns,
                        "required_patterns": anchor.required_patterns,
                        "severity": anchor.severity.value,
                    })

            # Also include evidence from the case
            evidence_hints = []
            for ev in case.evidence:
                if ev.get("description"):
                    evidence_hints.append(ev["description"])

            return {
                "success": True,
                "case_number": case_number,
                "constraints": constraints,
                "evidence_hints": evidence_hints,
                "blocked_content": case.blocked_content[:500] if case.blocked_content else None,
                "hint": "Regenerate output respecting these constraints",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_check_staleness(self, threshold: float | None = None) -> dict[str, Any]:
        """Handle check_staleness tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .epistemic import EpistemicLedger
            from .staleness import StalenessDetector, StalenessConfig

            config = StalenessConfig(
                confidence_threshold=threshold or 0.5,
            )
            ledger = EpistemicLedger()
            detector = StalenessDetector(ledger, config)

            stale_claims = detector.detect_stale_claims()

            result = []
            for freshness in stale_claims:
                result.append({
                    "claim_id": freshness.claim_id,
                    "confidence": freshness.confidence,
                    "is_live": freshness.is_live,
                    "decay_amount": freshness.decay_amount,
                    "staleness_reason": freshness.staleness_reason,
                    "violated_assumptions": freshness.violated_assumptions,
                })

            return {
                "success": True,
                "count": len(result),
                "stale_claims": result,
                "hint": "Use governor_reverify to refresh stale claims, or governor_record_ruling with 'dismiss' to accept",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_reverify(self, claim_id: str) -> dict[str, Any]:
        """Handle reverify tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .epistemic import EpistemicLedger
            from .staleness import StalenessDetector

            ledger = EpistemicLedger()
            detector = StalenessDetector(ledger)

            # Compute current freshness
            freshness = detector.compute_freshness(claim_id)

            if freshness.staleness_reason == "Claim not found":
                return {"success": False, "error": f"Claim {claim_id} not found"}

            # Get the claim and refresh its timestamp
            claim = ledger.get(claim_id)
            if claim:
                from datetime import datetime
                claim.last_updated_at = datetime.now()
                # Restore some confidence if it decayed
                if claim.confidence < 0.8:
                    claim.confidence = min(1.0, claim.confidence + 0.3)

            return {
                "success": True,
                "claim_id": claim_id,
                "old_confidence": freshness.confidence,
                "new_confidence": claim.confidence if claim else freshness.confidence,
                "hint": "Claim has been refreshed. Consider attaching new evidence.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # =========================================================================
    # Code Autopilot Handlers
    # =========================================================================

    def _handle_get_intent(self) -> dict[str, Any]:
        """Handle get_intent tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .intent import resolve_intent

            intent, provenance = resolve_intent(self.gov_dir)

            return {
                "success": True,
                "intent": intent.to_dict(),
                "status_string": intent.to_status_string(),
                "provenance": [p.to_dict() for p in provenance],
                "is_expired": intent.is_expired,
                "remaining_minutes": intent.remaining_minutes,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_set_intent(
        self,
        profile: str,
        scope: list[str] | None = None,
        deny: list[str] | None = None,
        timebox_minutes: float | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Handle set_intent tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .intent import Intent, set_intent
            from .autopilot import get_autopilot_profile, apply_autopilot_profile

            # Validate profile
            profile_config = get_autopilot_profile(profile)
            if not profile_config:
                return {
                    "success": False,
                    "error": f"Unknown profile: {profile}",
                    "valid_profiles": ["greenfield", "established", "production", "hotfix", "refactor"],
                }

            intent = Intent(
                profile=profile,
                scope=scope,
                deny=deny,
                timebox_minutes=int(timebox_minutes) if timebox_minutes else None,
                reason=reason,
                source="mcp",
            )

            set_intent(self.gov_dir, intent)
            applied = apply_autopilot_profile(self.gov_dir, profile_config)

            return {
                "success": True,
                "intent": intent.to_dict(),
                "status_string": intent.to_status_string(),
                "applied_settings": applied,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_suggest_profile(
        self,
        branch: str | None = None,
        files_touched: list[str] | None = None,
    ) -> dict[str, Any]:
        """Handle suggest_profile tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .intent import suggest_profile_for_branch, get_current_branch
            from .autopilot import get_autopilot_profile

            # Get branch if not provided
            if not branch:
                branch = get_current_branch()

            suggested, auto_apply, is_high_risk = suggest_profile_for_branch(branch)
            profile_config = get_autopilot_profile(suggested)

            return {
                "success": True,
                "branch": branch,
                "suggested_profile": suggested,
                "auto_apply": auto_apply,
                "is_high_risk": is_high_risk,
                "profile_description": profile_config.description if profile_config else "",
                "hint": f"Use governor_set_intent with profile='{suggested}' to apply" if not auto_apply else "Profile can be auto-applied for this branch type",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_override(
        self,
        anchor_id: str,
        reason: str,
        scope: list[str],
        expires_hours: float,
    ) -> dict[str, Any]:
        """Handle override tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .overrides import OverrideManager
            from .continuity import create_registry, ConstraintClass
            import os

            # Check that anchor exists and is invariant
            registry = create_registry(self.gov_dir)
            anchor = registry.get(anchor_id)
            if anchor is None:
                return {"success": False, "error": f"Anchor not found: {anchor_id}"}

            if anchor.constraint_class != ConstraintClass.INVARIANT:
                return {
                    "success": False,
                    "error": f"Anchor '{anchor_id}' is not an invariant. Use profile settings for preferences.",
                }

            manager = OverrideManager(gov_dir=self.gov_dir)
            operator = os.environ.get("USER", os.environ.get("USERNAME", "mcp"))

            receipt = manager.create(
                anchor_id=anchor_id,
                reason=reason,
                operator=operator,
                scope=scope,
                expires_hours=expires_hours,
            )

            return {
                "success": True,
                "override_id": receipt.id,
                "anchor_id": anchor_id,
                "scope": scope,
                "expires_at": receipt.expires_at,
                "remaining_minutes": receipt.remaining_minutes,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _handle_override_list(
        self,
        include_expired: bool = False,
    ) -> dict[str, Any]:
        """Handle override_list tool call."""
        ok, err = self._ensure_initialized()
        if not ok:
            return {"success": False, "error": err}

        try:
            from .overrides import OverrideManager

            manager = OverrideManager(gov_dir=self.gov_dir)
            overrides = manager.list_all() if include_expired else manager.list_active()

            return {
                "success": True,
                "count": len(overrides),
                "overrides": [o.to_dict() for o in overrides],
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_tools(self) -> list[dict[str, Any]]:
        """List available tools in MCP format."""
        return [tool.to_dict() for tool in self.tools.values()]

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call a tool by name with arguments."""
        if name not in self.tools:
            return {"success": False, "error": f"Unknown tool: {name}"}

        tool = self.tools[name]
        try:
            return tool.handler(**arguments)
        except Exception as e:
            return {"success": False, "error": str(e)}


def create_mcp_server(root: Path | None = None) -> GovernorMCPServer:
    """Create an MCP server instance."""
    if root is None:
        root = Path.cwd()
    return GovernorMCPServer(root)


# MCP JSON-RPC server implementation
def run_mcp_server(root: Path | None = None) -> None:
    """
    Run the MCP server using JSON-RPC over stdio.

    This implements the MCP protocol for communication with
    Claude Desktop and other MCP clients.
    """
    server = create_mcp_server(root)

    def send_response(response: dict) -> None:
        """Send a JSON-RPC response."""
        json_str = json.dumps(response)
        sys.stdout.write(f"Content-Length: {len(json_str)}\r\n\r\n{json_str}")
        sys.stdout.flush()

    def handle_request(request: dict) -> dict:
        """Handle a JSON-RPC request."""
        method = request.get("method", "")
        params = request.get("params", {})
        request_id = request.get("id")

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {},
                    },
                    "serverInfo": {
                        "name": "governor",
                        "version": "0.1.0",
                    },
                },
            }

        elif method == "tools/list":
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": server.list_tools(),
                },
            }

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = server.call_tool(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(result, indent=2),
                        }
                    ],
                },
            }

        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32601,
                    "message": f"Method not found: {method}",
                },
            }

    # Read requests from stdin
    import re

    while True:
        try:
            # Read headers
            headers = {}
            while True:
                line = sys.stdin.readline()
                if not line or line == "\r\n" or line == "\n":
                    break
                match = re.match(r"([^:]+):\s*(.+)", line.strip())
                if match:
                    headers[match.group(1)] = match.group(2)

            if "Content-Length" not in headers:
                continue

            # Read body
            content_length = int(headers["Content-Length"])
            body = sys.stdin.read(content_length)

            request = json.loads(body)
            response = handle_request(request)
            send_response(response)

        except EOFError:
            break
        except Exception as e:
            # Log error but continue
            sys.stderr.write(f"Error: {e}\n")
            sys.stderr.flush()
