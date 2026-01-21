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

Usage:
    governor mcp serve

Or configure in Claude Desktop's MCP settings.
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
