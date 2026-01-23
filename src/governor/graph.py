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
