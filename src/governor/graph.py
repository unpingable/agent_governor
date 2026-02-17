# SPDX-License-Identifier: Apache-2.0
"""
Audit graph for Agent Governor.

Maltego-style graph representation of governor state for:
- Claims → Evidence edges (provenance)
- Actions → Preconditions (what had to be true)
- Sessions → Handoffs → Drift (state changes, contradictions)
- Actors → Authority scope (who can assert what)
- Failure events → Root patterns (invariants violated)

Transforms are graph queries:
- "Show me all claims lacking evidence"
- "Expand dependency chain for this decision"
- "Highlight contradictions introduced after session N"
- "Find all actions taken under weak grounding"
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


class NodeType(Enum):
    """Types of nodes in the audit graph."""
    # Core governor objects
    PROPOSAL = "proposal"
    CLAIM = "claim"
    RECEIPT = "receipt"
    FACT = "fact"
    DECISION = "decision"

    # Task management
    TASK = "task"
    SESSION = "session"
    MILESTONE = "milestone"

    # Actors
    AGENT = "agent"

    # External references
    FILE = "file"
    COMMAND = "command"

    # Meta
    REJECTION = "rejection"
    SUMMARY = "summary"  # Collapsed stable summary object


class EdgeType(Enum):
    """Types of edges in the audit graph."""
    # Provenance
    SUPPORTS = "supports"           # receipt → claim
    EVIDENCES = "evidences"         # file/command → receipt
    CONTAINS = "contains"           # proposal → claim

    # Decisions
    SUPERSEDES = "supersedes"       # decision → decision
    CONTRADICTS = "contradicts"     # claim → decision
    DECIDED_BY = "decided_by"       # decision → proposal

    # Tasks
    SUBTASK_OF = "subtask_of"       # task → task
    BLOCKS = "blocks"               # task → task
    RELATED_TO = "related_to"       # task → task
    PART_OF = "part_of"             # task → milestone
    WORKED_ON = "worked_on"         # session → task

    # Actors
    PROPOSED_BY = "proposed_by"     # proposal → agent
    OWNED_BY = "owned_by"           # task → agent

    # Failures
    REJECTED_BY = "rejected_by"     # proposal → rejection
    CAUSED_BY = "caused_by"         # rejection → claim

    # Files
    REFERENCES = "references"       # claim/fact → file
    MODIFIES = "modifies"           # proposal → file

    # Summaries
    SUMMARIZES = "summarizes"       # summary → node (collapsed into summary)


@dataclass
class Node:
    """A node in the audit graph."""
    id: str
    type: NodeType
    label: str
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "label": self.label,
            "properties": self.properties,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class Edge:
    """An edge in the audit graph."""
    source: str  # Node ID
    target: str  # Node ID
    type: EdgeType
    properties: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "type": self.type.value,
            "properties": self.properties,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


@dataclass
class StableSummary:
    """
    A collapsed summary of a subgraph - a reusable insight object.

    Captures:
    - What was decided/claimed
    - What evidence supported it
    - What contradictions were resolved
    - What the lineage looks like
    - Key invariants established

    This is not just a compression - it's a stable artifact that can be
    referenced, cited, and built upon without needing to traverse the
    full subgraph.
    """
    id: str
    title: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # What this summary covers
    node_ids: list[str] = field(default_factory=list)  # Original nodes collapsed
    time_range: tuple[datetime | None, datetime | None] = (None, None)

    # Key content extracted
    decisions: list[dict[str, Any]] = field(default_factory=list)  # topic -> choice
    claims_verified: list[str] = field(default_factory=list)  # Verified claims
    claims_unverified: list[str] = field(default_factory=list)  # Claims lacking evidence
    contradictions_resolved: list[dict[str, Any]] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)

    # Lineage
    agents_involved: list[str] = field(default_factory=list)
    files_touched: list[str] = field(default_factory=list)
    sessions_spanned: list[str] = field(default_factory=list)

    # Invariants / insights
    invariants: list[str] = field(default_factory=list)  # Extracted stable truths
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "node_ids": self.node_ids,
            "time_range": [
                self.time_range[0].isoformat() if self.time_range[0] else None,
                self.time_range[1].isoformat() if self.time_range[1] else None,
            ],
            "decisions": self.decisions,
            "claims_verified": self.claims_verified,
            "claims_unverified": self.claims_unverified,
            "contradictions_resolved": self.contradictions_resolved,
            "rejections": self.rejections,
            "agents_involved": self.agents_involved,
            "files_touched": self.files_touched,
            "sessions_spanned": self.sessions_spanned,
            "invariants": self.invariants,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StableSummary":
        time_range = data.get("time_range", [None, None])
        return cls(
            id=data["id"],
            title=data["title"],
            created_at=datetime.fromisoformat(data["created_at"]),
            node_ids=data.get("node_ids", []),
            time_range=(
                datetime.fromisoformat(time_range[0]) if time_range[0] else None,
                datetime.fromisoformat(time_range[1]) if time_range[1] else None,
            ),
            decisions=data.get("decisions", []),
            claims_verified=data.get("claims_verified", []),
            claims_unverified=data.get("claims_unverified", []),
            contradictions_resolved=data.get("contradictions_resolved", []),
            rejections=data.get("rejections", []),
            agents_involved=data.get("agents_involved", []),
            files_touched=data.get("files_touched", []),
            sessions_spanned=data.get("sessions_spanned", []),
            invariants=data.get("invariants", []),
            notes=data.get("notes", ""),
        )

    def to_markdown(self) -> str:
        """Export summary as markdown document."""
        lines = [
            f"# {self.title}",
            "",
            f"*Summary ID: {self.id}*",
            f"*Created: {self.created_at.isoformat()}*",
            "",
        ]

        if self.time_range[0] or self.time_range[1]:
            start = self.time_range[0].isoformat() if self.time_range[0] else "?"
            end = self.time_range[1].isoformat() if self.time_range[1] else "?"
            lines.append(f"**Time span:** {start} → {end}")
            lines.append("")

        if self.decisions:
            lines.append("## Decisions")
            for dec in self.decisions:
                lines.append(f"- **{dec.get('topic', '?')}**: {dec.get('choice', '?')}")
            lines.append("")

        if self.claims_verified:
            lines.append("## Verified Claims")
            for claim in self.claims_verified:
                lines.append(f"- ✓ {claim}")
            lines.append("")

        if self.claims_unverified:
            lines.append("## Unverified Claims")
            for claim in self.claims_unverified:
                lines.append(f"- ⚠ {claim}")
            lines.append("")

        if self.contradictions_resolved:
            lines.append("## Contradictions Resolved")
            for c in self.contradictions_resolved:
                lines.append(f"- {c.get('old', '?')} → {c.get('new', '?')}")
            lines.append("")

        if self.rejections:
            lines.append("## Rejections")
            for r in self.rejections:
                lines.append(f"- {r.get('reason', '?')}")
            lines.append("")

        if self.invariants:
            lines.append("## Invariants Established")
            for inv in self.invariants:
                lines.append(f"- {inv}")
            lines.append("")

        if self.agents_involved:
            lines.append(f"**Agents:** {', '.join(self.agents_involved)}")
        if self.files_touched:
            lines.append(f"**Files:** {', '.join(self.files_touched[:10])}")
            if len(self.files_touched) > 10:
                lines.append(f"  *(and {len(self.files_touched) - 10} more)*")
        if self.sessions_spanned:
            lines.append(f"**Sessions:** {len(self.sessions_spanned)}")

        if self.notes:
            lines.extend(["", "## Notes", self.notes])

        lines.extend(["", "---", f"*Collapsed from {len(self.node_ids)} nodes*"])

        return "\n".join(lines)

    def to_node(self) -> Node:
        """Convert this summary to a graph node."""
        return Node(
            id=f"summary:{self.id}",
            type=NodeType.SUMMARY,
            label=self.title,
            properties=self.to_dict(),
            timestamp=self.created_at,
        )


@dataclass
class AuditGraph:
    """
    The complete audit graph.

    Supports transforms (queries) and export to various formats.
    """
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: Node) -> None:
        """Add a node to the graph."""
        self.nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph."""
        self.edges.append(edge)

    def get_node(self, node_id: str) -> Node | None:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_edges_from(self, node_id: str) -> list[Edge]:
        """Get all edges originating from a node."""
        return [e for e in self.edges if e.source == node_id]

    def get_edges_to(self, node_id: str) -> list[Edge]:
        """Get all edges pointing to a node."""
        return [e for e in self.edges if e.target == node_id]

    def get_neighbors(self, node_id: str) -> list[Node]:
        """Get all nodes connected to a node."""
        neighbor_ids = set()
        for edge in self.edges:
            if edge.source == node_id:
                neighbor_ids.add(edge.target)
            elif edge.target == node_id:
                neighbor_ids.add(edge.source)
        return [self.nodes[nid] for nid in neighbor_ids if nid in self.nodes]

    # =========================================================================
    # Transforms (Maltego-style queries)
    # =========================================================================

    def claims_without_evidence(self) -> list[Node]:
        """
        Transform: Show all claims lacking evidence.

        Returns claims that have no SUPPORTS edges pointing to them.
        """
        supported_claims = {
            e.target for e in self.edges
            if e.type == EdgeType.SUPPORTS
        }
        return [
            node for node in self.nodes.values()
            if node.type == NodeType.CLAIM and node.id not in supported_claims
        ]

    def expand_dependency_chain(self, decision_id: str) -> "AuditGraph":
        """
        Transform: Expand dependency chain for a decision.

        Returns a subgraph containing the decision and all decisions
        it supersedes (recursively).
        """
        subgraph = AuditGraph()
        visited = set()
        to_visit = [decision_id]

        while to_visit:
            current_id = to_visit.pop()
            if current_id in visited:
                continue
            visited.add(current_id)

            node = self.get_node(current_id)
            if node:
                subgraph.add_node(node)

                # Find supersedes edges
                for edge in self.get_edges_from(current_id):
                    if edge.type == EdgeType.SUPERSEDES:
                        subgraph.add_edge(edge)
                        to_visit.append(edge.target)

        return subgraph

    def contradictions_after_session(self, session_id: str) -> list[tuple[Node, Node]]:
        """
        Transform: Highlight contradictions introduced after session N.

        Returns pairs of (new_claim, contradicted_decision).
        """
        session_node = self.get_node(session_id)
        if not session_node or not session_node.timestamp:
            return []

        session_time = session_node.timestamp
        contradictions = []

        for edge in self.edges:
            if edge.type == EdgeType.CONTRADICTS:
                claim_node = self.get_node(edge.source)
                decision_node = self.get_node(edge.target)

                if claim_node and decision_node:
                    if claim_node.timestamp and claim_node.timestamp > session_time:
                        contradictions.append((claim_node, decision_node))

        return contradictions

    def weak_grounding(self, threshold: int = 1) -> list[Node]:
        """
        Transform: Find all actions taken under 'weak' grounding.

        Returns proposals with fewer than `threshold` supporting receipts.
        """
        weak = []

        for node in self.nodes.values():
            if node.type == NodeType.PROPOSAL:
                # Count receipts supporting claims in this proposal
                claims_in_proposal = [
                    e.target for e in self.get_edges_from(node.id)
                    if e.type == EdgeType.CONTAINS
                ]

                receipt_count = 0
                for claim_id in claims_in_proposal:
                    receipts = [
                        e for e in self.get_edges_to(claim_id)
                        if e.type == EdgeType.SUPPORTS
                    ]
                    receipt_count += len(receipts)

                if receipt_count < threshold:
                    weak.append(node)

        return weak

    def rejection_patterns(self) -> dict[str, list[Node]]:
        """
        Transform: Group rejections by their root cause patterns.

        Returns dict mapping rejection reasons to rejected proposals.
        """
        patterns: dict[str, list[Node]] = {}

        for node in self.nodes.values():
            if node.type == NodeType.REJECTION:
                reason = node.properties.get("reason", "unknown")
                # Normalize reason to pattern
                pattern = self._normalize_rejection_pattern(reason)

                if pattern not in patterns:
                    patterns[pattern] = []

                # Find the proposal that was rejected
                for edge in self.get_edges_to(node.id):
                    if edge.type == EdgeType.REJECTED_BY:
                        proposal = self.get_node(edge.source)
                        if proposal:
                            patterns[pattern].append(proposal)

        return patterns

    def _normalize_rejection_pattern(self, reason: str) -> str:
        """Normalize rejection reason to a pattern category."""
        reason_lower = reason.lower()

        if "file" in reason_lower and "not found" in reason_lower:
            return "file_not_found"
        elif "conflict" in reason_lower or "contradict" in reason_lower:
            return "decision_conflict"
        elif "test" in reason_lower and "fail" in reason_lower:
            return "test_failure"
        elif "permission" in reason_lower or "not allowed" in reason_lower:
            return "permission_denied"
        elif "evidence" in reason_lower or "receipt" in reason_lower:
            return "missing_evidence"
        else:
            return "other"

    def subgraph_for_task(self, task_id: str) -> "AuditGraph":
        """
        Transform: Get subgraph for a specific task.

        Includes the task, its subtasks, related proposals, sessions, etc.
        """
        subgraph = AuditGraph()
        visited = set()
        to_visit = [task_id]

        while to_visit:
            current_id = to_visit.pop()
            if current_id in visited:
                continue
            visited.add(current_id)

            node = self.get_node(current_id)
            if node:
                subgraph.add_node(node)

                # Add all edges from/to this node
                for edge in self.get_edges_from(current_id):
                    subgraph.add_edge(edge)
                    # Expand subtasks and related
                    if edge.type in (EdgeType.SUBTASK_OF, EdgeType.RELATED_TO, EdgeType.BLOCKS):
                        to_visit.append(edge.target)

                for edge in self.get_edges_to(current_id):
                    subgraph.add_edge(edge)
                    if edge.type == EdgeType.SUBTASK_OF:
                        to_visit.append(edge.source)

        return subgraph

    def actor_authority_map(self) -> dict[str, dict[str, int]]:
        """
        Transform: Map actors to their authority scope.

        Returns dict mapping agent_id to counts of actions by type.
        """
        authority: dict[str, dict[str, int]] = {}

        for node in self.nodes.values():
            if node.type == NodeType.AGENT:
                agent_id = node.id
                authority[agent_id] = {
                    "proposals": 0,
                    "decisions": 0,
                    "tasks": 0,
                    "sessions": 0,
                }

                # Count proposals by this agent
                for edge in self.get_edges_to(node.id):
                    if edge.type == EdgeType.PROPOSED_BY:
                        authority[agent_id]["proposals"] += 1
                    elif edge.type == EdgeType.OWNED_BY:
                        source_node = self.get_node(edge.source)
                        if source_node:
                            if source_node.type == NodeType.TASK:
                                authority[agent_id]["tasks"] += 1
                            elif source_node.type == NodeType.SESSION:
                                authority[agent_id]["sessions"] += 1

        return authority

    def session_drift(self) -> list[dict[str, Any]]:
        """
        Transform: Analyze drift across sessions.

        Returns list of drift events (forgotten items, contradictions).
        """
        drift_events = []
        sessions = sorted(
            [n for n in self.nodes.values() if n.type == NodeType.SESSION],
            key=lambda n: n.timestamp or datetime.min.replace(tzinfo=timezone.utc)
        )

        for i, session in enumerate(sessions[1:], 1):
            prev_session = sessions[i - 1]

            # Find decisions made before this session that were contradicted
            contradictions = self.contradictions_after_session(prev_session.id)

            if contradictions:
                drift_events.append({
                    "type": "contradiction",
                    "session": session.id,
                    "previous_session": prev_session.id,
                    "count": len(contradictions),
                    "details": [
                        {"claim": c.label, "decision": d.label}
                        for c, d in contradictions
                    ],
                })

        return drift_events

    # =========================================================================
    # Collapse (stable summary objects)
    # =========================================================================

    def collapse(
        self,
        subgraph: "AuditGraph | None" = None,
        title: str = "Summary",
        notes: str = "",
        extract_invariants: bool = True,
    ) -> StableSummary:
        """
        Transform: Collapse a subgraph into a stable summary object.

        A summary is not just compression - it's a reusable insight artifact that
        captures:
        - What was decided
        - What evidence supported it
        - What contradictions were resolved
        - What the lineage looks like
        - Key invariants established

        Args:
            subgraph: The subgraph to collapse (defaults to entire graph)
            title: Title for the summary
            notes: Additional notes to include
            extract_invariants: Whether to extract invariants from decisions

        Returns:
            A StableSummary object that can be stored, referenced, and built upon.
        """
        from uuid import uuid4

        target = subgraph or self

        summary = StableSummary(
            id=str(uuid4()),
            title=title,
            notes=notes,
        )

        # Collect node IDs
        summary.node_ids = list(target.nodes.keys())

        # Determine time range
        timestamps = [
            n.timestamp for n in target.nodes.values()
            if n.timestamp is not None
        ]
        if timestamps:
            summary.time_range = (min(timestamps), max(timestamps))

        # Extract decisions
        for node in target.nodes.values():
            if node.type == NodeType.DECISION:
                summary.decisions.append({
                    "topic": node.properties.get("topic", ""),
                    "choice": node.properties.get("choice", ""),
                    "rationale": node.properties.get("rationale", ""),
                    "id": node.id,
                })

                # Extract invariants from decisions if requested
                if extract_invariants:
                    topic = node.properties.get("topic", "")
                    choice = node.properties.get("choice", "")
                    if topic and choice:
                        summary.invariants.append(f"{topic} = {choice}")

        # Classify claims as verified or unverified
        supported_claims = {
            e.target for e in target.edges
            if e.type == EdgeType.SUPPORTS
        }

        for node in target.nodes.values():
            if node.type == NodeType.CLAIM:
                if node.id in supported_claims:
                    summary.claims_verified.append(node.label)
                else:
                    summary.claims_unverified.append(node.label)

        # Find contradictions that were resolved (superseded decisions)
        for edge in target.edges:
            if edge.type == EdgeType.SUPERSEDES:
                old_node = target.get_node(edge.target)
                new_node = target.get_node(edge.source)
                if old_node and new_node:
                    summary.contradictions_resolved.append({
                        "old": old_node.label,
                        "new": new_node.label,
                        "old_id": old_node.id,
                        "new_id": new_node.id,
                    })

        # Collect rejections
        for node in target.nodes.values():
            if node.type == NodeType.REJECTION:
                summary.rejections.append({
                    "reason": node.properties.get("reason", ""),
                    "suggestion": node.properties.get("suggestion", ""),
                    "id": node.id,
                })

        # Collect agents involved
        for node in target.nodes.values():
            if node.type == NodeType.AGENT:
                # Extract agent name from ID (e.g., "agent:worker-1" -> "worker-1")
                agent_name = node.id.split(":", 1)[-1] if ":" in node.id else node.id
                summary.agents_involved.append(agent_name)

        # Collect files touched
        for node in target.nodes.values():
            if node.type == NodeType.FILE:
                file_path = node.id.split(":", 1)[-1] if ":" in node.id else node.label
                summary.files_touched.append(file_path)

        # Collect sessions spanned
        for node in target.nodes.values():
            if node.type == NodeType.SESSION:
                summary.sessions_spanned.append(node.id)

        return summary

    def collapse_and_add(
        self,
        subgraph: "AuditGraph | None" = None,
        title: str = "Summary",
        notes: str = "",
    ) -> Node:
        """
        Collapse a subgraph and add the summary as a node in this graph.

        Creates SUMMARIZES edges from the summary node to all nodes it collapsed.

        Returns the summary node.
        """
        summary = self.collapse(subgraph, title, notes)
        summary_node = summary.to_node()

        self.add_node(summary_node)

        # Add edges to collapsed nodes
        target = subgraph or self
        for node_id in summary.node_ids:
            if node_id != summary_node.id:  # Don't link to self
                self.add_edge(Edge(
                    source=summary_node.id,
                    target=node_id,
                    type=EdgeType.SUMMARIZES,
                ))

        return summary_node

    # =========================================================================
    # Export
    # =========================================================================

    def to_dict(self) -> dict[str, Any]:
        """Export graph to dictionary format."""
        return {
            "nodes": [node.to_dict() for node in self.nodes.values()],
            "edges": [edge.to_dict() for edge in self.edges],
            "metadata": {
                "node_count": len(self.nodes),
                "edge_count": len(self.edges),
                "exported_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def to_json(self, indent: int = 2) -> str:
        """Export graph to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_cytoscape(self) -> dict[str, Any]:
        """
        Export to Cytoscape.js format.

        Compatible with Cytoscape.js web viewer.
        """
        elements = []

        for node in self.nodes.values():
            elements.append({
                "data": {
                    "id": node.id,
                    "label": node.label,
                    "type": node.type.value,
                    **node.properties,
                },
                "classes": node.type.value,
            })

        for edge in self.edges:
            elements.append({
                "data": {
                    "id": f"{edge.source}-{edge.type.value}-{edge.target}",
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.type.value,
                    **edge.properties,
                },
                "classes": edge.type.value,
            })

        return {"elements": elements}

    def to_graphviz(self) -> str:
        """
        Export to Graphviz DOT format.

        Can be rendered with `dot -Tpng graph.dot -o graph.png`
        """
        lines = ["digraph AuditGraph {"]
        lines.append("  rankdir=LR;")
        lines.append("  node [shape=box];")
        lines.append("")

        # Define node styles by type
        type_styles = {
            NodeType.PROPOSAL: 'shape=box,style=filled,fillcolor="#e3f2fd"',
            NodeType.CLAIM: 'shape=ellipse,style=filled,fillcolor="#fff3e0"',
            NodeType.RECEIPT: 'shape=note,style=filled,fillcolor="#e8f5e9"',
            NodeType.DECISION: 'shape=diamond,style=filled,fillcolor="#fce4ec"',
            NodeType.TASK: 'shape=box,style=filled,fillcolor="#f3e5f5"',
            NodeType.SESSION: 'shape=box,style=rounded,fillcolor="#e0f7fa"',
            NodeType.AGENT: 'shape=octagon,style=filled,fillcolor="#fff8e1"',
            NodeType.REJECTION: 'shape=box,style=filled,fillcolor="#ffebee"',
        }

        # Add nodes
        for node in self.nodes.values():
            style = type_styles.get(node.type, "")
            label = node.label.replace('"', '\\"')[:40]
            lines.append(f'  "{node.id}" [label="{label}",{style}];')

        lines.append("")

        # Add edges
        edge_styles = {
            EdgeType.SUPPORTS: 'color="green"',
            EdgeType.CONTRADICTS: 'color="red",style=dashed',
            EdgeType.SUPERSEDES: 'color="blue",style=dotted',
            EdgeType.BLOCKS: 'color="orange"',
        }

        for edge in self.edges:
            style = edge_styles.get(edge.type, "")
            lines.append(f'  "{edge.source}" -> "{edge.target}" [{style}];')

        lines.append("}")
        return "\n".join(lines)

    def to_obsidian_canvas(self) -> dict[str, Any]:
        """
        Export to Obsidian Canvas format (.canvas JSON).

        Creates a visual canvas that can be opened in Obsidian.
        """
        nodes = []
        edges = []

        # Position nodes in a grid
        cols = max(1, int(len(self.nodes) ** 0.5))

        for i, node in enumerate(self.nodes.values()):
            x = (i % cols) * 300
            y = (i // cols) * 200

            # Color by type
            colors = {
                NodeType.PROPOSAL: "1",  # Red
                NodeType.DECISION: "4",  # Green
                NodeType.TASK: "5",      # Purple
                NodeType.SESSION: "6",   # Cyan
            }

            nodes.append({
                "id": node.id,
                "type": "text",
                "x": x,
                "y": y,
                "width": 250,
                "height": 100,
                "text": f"**{node.type.value}**\n{node.label}",
                "color": colors.get(node.type, "0"),
            })

        for edge in self.edges:
            edges.append({
                "id": f"{edge.source}-{edge.target}",
                "fromNode": edge.source,
                "toNode": edge.target,
                "label": edge.type.value,
            })

        return {"nodes": nodes, "edges": edges}


class GraphBuilder:
    """
    Builds an AuditGraph from governor state.

    Pulls data from storage and constructs the full graph.
    """

    def __init__(self, governor_dir: Path):
        self.governor_dir = governor_dir

    def build(self) -> AuditGraph:
        """Build the complete audit graph from governor state."""
        from .storage import get_storage
        from .tasks import get_task_manager

        graph = AuditGraph()
        storage = get_storage(self.governor_dir)

        # Add proposals and their claims
        self._add_proposals(graph, storage)

        # Add facts and decisions
        self._add_facts(graph, storage)
        self._add_decisions(graph, storage)

        # Add agents
        self._add_agents(graph, storage)

        # Add rejections
        self._add_rejections(graph, storage)

        # Add tasks and sessions
        try:
            tm = get_task_manager(self.governor_dir)
            self._add_tasks(graph, tm)
            self._add_sessions(graph, tm)
            self._add_milestones(graph, tm)
        except Exception:
            # Task tables might not exist yet
            pass

        return graph

    def _add_proposals(self, graph: AuditGraph, storage) -> None:
        """Add proposal nodes and their claims."""
        rows = storage.query("proposals", order_by="created_at DESC")

        for row in rows:
            proposal_id = row["id"]

            # Add proposal node
            graph.add_node(Node(
                id=f"proposal:{proposal_id}",
                type=NodeType.PROPOSAL,
                label=f"Proposal {proposal_id[:8]}",
                properties={
                    "state": row["state"],
                    "agent_id": row["agent_id"],
                },
                timestamp=datetime.fromisoformat(row["created_at"]),
            ))

            # Add claims
            claims = json.loads(row["claims_json"])
            for i, claim in enumerate(claims):
                claim_id = f"claim:{proposal_id}:{i}"
                graph.add_node(Node(
                    id=claim_id,
                    type=NodeType.CLAIM,
                    label=claim.get("description", f"Claim {i}"),
                    properties=claim,
                    timestamp=datetime.fromisoformat(row["created_at"]),
                ))

                # Edge: proposal contains claim
                graph.add_edge(Edge(
                    source=f"proposal:{proposal_id}",
                    target=claim_id,
                    type=EdgeType.CONTAINS,
                ))

                # If claim references a file, add file node and edge
                if claim.get("path"):
                    file_id = f"file:{claim['path']}"
                    if file_id not in graph.nodes:
                        graph.add_node(Node(
                            id=file_id,
                            type=NodeType.FILE,
                            label=claim["path"],
                        ))
                    graph.add_edge(Edge(
                        source=claim_id,
                        target=file_id,
                        type=EdgeType.REFERENCES,
                    ))

            # Add receipts
            receipts = json.loads(row["receipts_json"])
            for i, receipt in enumerate(receipts):
                receipt_id = f"receipt:{proposal_id}:{i}"
                graph.add_node(Node(
                    id=receipt_id,
                    type=NodeType.RECEIPT,
                    label=receipt.get("type", f"Receipt {i}"),
                    properties=receipt,
                ))

                # Edge: receipt supports claim
                if i < len(claims):
                    graph.add_edge(Edge(
                        source=receipt_id,
                        target=f"claim:{proposal_id}:{i}",
                        type=EdgeType.SUPPORTS,
                    ))

            # Edge: proposal by agent
            if row["agent_id"]:
                agent_id = f"agent:{row['agent_id']}"
                graph.add_edge(Edge(
                    source=f"proposal:{proposal_id}",
                    target=agent_id,
                    type=EdgeType.PROPOSED_BY,
                ))

    def _add_facts(self, graph: AuditGraph, storage) -> None:
        """Add fact nodes."""
        rows = storage.query("facts", order_by="created_at DESC")

        for row in rows:
            fact_id = row["id"]
            claim = json.loads(row["claim_json"])

            graph.add_node(Node(
                id=f"fact:{fact_id}",
                type=NodeType.FACT,
                label=claim.get("description", f"Fact {fact_id[:8]}"),
                properties={
                    "claim_type": row["claim_type"],
                    "invalidated": row["invalidated_at"] is not None,
                },
                timestamp=datetime.fromisoformat(row["created_at"]),
            ))

    def _add_decisions(self, graph: AuditGraph, storage) -> None:
        """Add decision nodes and supersedes edges."""
        rows = storage.query("decisions", order_by="created_at DESC")

        for row in rows:
            decision_id = row["id"]

            graph.add_node(Node(
                id=f"decision:{decision_id}",
                type=NodeType.DECISION,
                label=f"{row['topic']}: {row['choice']}",
                properties={
                    "topic": row["topic"],
                    "choice": row["choice"],
                    "rationale": row["rationale"],
                },
                timestamp=datetime.fromisoformat(row["created_at"]),
            ))

            # Supersedes edge
            if row["supersedes_id"]:
                graph.add_edge(Edge(
                    source=f"decision:{decision_id}",
                    target=f"decision:{row['supersedes_id']}",
                    type=EdgeType.SUPERSEDES,
                ))

    def _add_agents(self, graph: AuditGraph, storage) -> None:
        """Add agent nodes."""
        rows = storage.query("agents")

        for row in rows:
            graph.add_node(Node(
                id=f"agent:{row['id']}",
                type=NodeType.AGENT,
                label=row["id"],
                properties={
                    "class": row["agent_class"],
                    "capabilities": json.loads(row["capabilities_json"]),
                },
                timestamp=datetime.fromisoformat(row["registered_at"]),
            ))

    def _add_rejections(self, graph: AuditGraph, storage) -> None:
        """Add rejection nodes."""
        rows = storage.query("rejections", order_by="created_at DESC")

        for row in rows:
            rejection_id = row["id"]

            graph.add_node(Node(
                id=f"rejection:{rejection_id}",
                type=NodeType.REJECTION,
                label=row["reason"][:50],
                properties={
                    "reason": row["reason"],
                    "suggestion": row["suggestion"],
                },
                timestamp=datetime.fromisoformat(row["created_at"]),
            ))

            # Edge: proposal rejected
            if row["proposal_id"]:
                graph.add_edge(Edge(
                    source=f"proposal:{row['proposal_id']}",
                    target=f"rejection:{rejection_id}",
                    type=EdgeType.REJECTED_BY,
                ))

    def _add_tasks(self, graph: AuditGraph, tm) -> None:
        """Add task nodes and relationships."""
        tasks = tm.list_tasks(include_archived=True)

        for task in tasks:
            graph.add_node(Node(
                id=f"task:{task.id}",
                type=NodeType.TASK,
                label=task.title,
                properties={
                    "status": task.status.value,
                    "priority": task.priority.value,
                },
                timestamp=task.created_at,
            ))

            # Subtask edge
            if task.parent_id:
                graph.add_edge(Edge(
                    source=f"task:{task.id}",
                    target=f"task:{task.parent_id}",
                    type=EdgeType.SUBTASK_OF,
                ))

            # Blocking edges
            for dep_id in task.depends_on:
                graph.add_edge(Edge(
                    source=f"task:{dep_id}",
                    target=f"task:{task.id}",
                    type=EdgeType.BLOCKS,
                ))

            # Related edges
            for rel_id in task.related_to:
                # Only add one direction to avoid duplicates
                if str(task.id) < str(rel_id):
                    graph.add_edge(Edge(
                        source=f"task:{task.id}",
                        target=f"task:{rel_id}",
                        type=EdgeType.RELATED_TO,
                    ))

            # Milestone edge
            if task.milestone_id:
                graph.add_edge(Edge(
                    source=f"task:{task.id}",
                    target=f"milestone:{task.milestone_id}",
                    type=EdgeType.PART_OF,
                ))

            # Agent edge
            if task.agent_id:
                graph.add_edge(Edge(
                    source=f"task:{task.id}",
                    target=f"agent:{task.agent_id}",
                    type=EdgeType.OWNED_BY,
                ))

    def _add_sessions(self, graph: AuditGraph, tm) -> None:
        """Add session nodes."""
        sessions = tm.list_sessions(limit=100)

        for session in sessions:
            graph.add_node(Node(
                id=f"session:{session.id}",
                type=NodeType.SESSION,
                label=session.summary[:40] if session.summary else f"Session {str(session.id)[:8]}",
                properties={
                    "active": session.is_active,
                    "duration_minutes": session.duration.total_seconds() / 60,
                    "next_steps": session.next_steps,
                    "blockers": session.blockers,
                },
                timestamp=session.started_at,
            ))

            # Tasks worked on
            for task_id in session.task_ids:
                graph.add_edge(Edge(
                    source=f"session:{session.id}",
                    target=f"task:{task_id}",
                    type=EdgeType.WORKED_ON,
                ))

    def _add_milestones(self, graph: AuditGraph, tm) -> None:
        """Add milestone nodes."""
        milestones = tm.list_milestones(include_closed=True)

        for milestone in milestones:
            progress = tm.get_milestone_progress(milestone.id)

            graph.add_node(Node(
                id=f"milestone:{milestone.id}",
                type=NodeType.MILESTONE,
                label=milestone.name,
                properties={
                    "closed": milestone.is_closed,
                    "due_date": milestone.due_date.isoformat() if milestone.due_date else None,
                    "progress_percent": progress["percent_complete"],
                },
                timestamp=milestone.created_at,
            ))


def build_graph(governor_dir: Path) -> AuditGraph:
    """Convenience function to build audit graph."""
    builder = GraphBuilder(governor_dir)
    return builder.build()
