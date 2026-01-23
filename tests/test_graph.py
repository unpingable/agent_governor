"""Tests for audit graph system."""

import json
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from governor.graph import (
    Node,
    Edge,
    NodeType,
    EdgeType,
    AuditGraph,
    StableSummary,
)


@pytest.fixture
def empty_graph():
    """Create an empty graph."""
    return AuditGraph()


@pytest.fixture
def sample_graph():
    """Create a sample graph with various nodes and edges."""
    graph = AuditGraph()

    # Add proposals
    graph.add_node(Node(
        id="proposal:1",
        type=NodeType.PROPOSAL,
        label="Proposal 1",
        properties={"state": "applied"},
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
    ))

    graph.add_node(Node(
        id="proposal:2",
        type=NodeType.PROPOSAL,
        label="Proposal 2",
        properties={"state": "rejected"},
        timestamp=datetime.now(timezone.utc) - timedelta(days=1),
    ))

    # Add claims
    graph.add_node(Node(
        id="claim:1:0",
        type=NodeType.CLAIM,
        label="File exists",
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
    ))

    graph.add_node(Node(
        id="claim:2:0",
        type=NodeType.CLAIM,
        label="Tests pass",
        timestamp=datetime.now(timezone.utc) - timedelta(days=1),
    ))

    # Add receipts
    graph.add_node(Node(
        id="receipt:1:0",
        type=NodeType.RECEIPT,
        label="FileSnapshot",
    ))

    # Add decisions
    graph.add_node(Node(
        id="decision:1",
        type=NodeType.DECISION,
        label="framework: react",
        properties={"topic": "framework", "choice": "react"},
        timestamp=datetime.now(timezone.utc) - timedelta(days=3),
    ))

    graph.add_node(Node(
        id="decision:2",
        type=NodeType.DECISION,
        label="framework: vue",
        properties={"topic": "framework", "choice": "vue"},
        timestamp=datetime.now(timezone.utc) - timedelta(days=1),
    ))

    # Add sessions
    graph.add_node(Node(
        id="session:1",
        type=NodeType.SESSION,
        label="Session 1",
        timestamp=datetime.now(timezone.utc) - timedelta(days=2),
    ))

    graph.add_node(Node(
        id="session:2",
        type=NodeType.SESSION,
        label="Session 2",
        timestamp=datetime.now(timezone.utc) - timedelta(days=1),
    ))

    # Add rejection
    graph.add_node(Node(
        id="rejection:1",
        type=NodeType.REJECTION,
        label="File not found",
        properties={"reason": "File not found: test.py"},
    ))

    # Add agent
    graph.add_node(Node(
        id="agent:worker-1",
        type=NodeType.AGENT,
        label="worker-1",
    ))

    # Add edges
    graph.add_edge(Edge(
        source="proposal:1",
        target="claim:1:0",
        type=EdgeType.CONTAINS,
    ))

    graph.add_edge(Edge(
        source="proposal:2",
        target="claim:2:0",
        type=EdgeType.CONTAINS,
    ))

    graph.add_edge(Edge(
        source="receipt:1:0",
        target="claim:1:0",
        type=EdgeType.SUPPORTS,
    ))

    graph.add_edge(Edge(
        source="decision:2",
        target="decision:1",
        type=EdgeType.SUPERSEDES,
    ))

    graph.add_edge(Edge(
        source="proposal:2",
        target="rejection:1",
        type=EdgeType.REJECTED_BY,
    ))

    graph.add_edge(Edge(
        source="proposal:1",
        target="agent:worker-1",
        type=EdgeType.PROPOSED_BY,
    ))

    return graph


class TestAuditGraphBasics:
    """Test basic graph operations."""

    def test_add_node(self, empty_graph):
        """Can add a node to the graph."""
        node = Node(
            id="test:1",
            type=NodeType.PROPOSAL,
            label="Test",
        )
        empty_graph.add_node(node)

        assert "test:1" in empty_graph.nodes
        assert empty_graph.nodes["test:1"].label == "Test"

    def test_add_edge(self, empty_graph):
        """Can add an edge to the graph."""
        empty_graph.add_node(Node(id="a", type=NodeType.PROPOSAL, label="A"))
        empty_graph.add_node(Node(id="b", type=NodeType.CLAIM, label="B"))

        edge = Edge(source="a", target="b", type=EdgeType.CONTAINS)
        empty_graph.add_edge(edge)

        assert len(empty_graph.edges) == 1
        assert empty_graph.edges[0].source == "a"
        assert empty_graph.edges[0].target == "b"

    def test_get_node(self, sample_graph):
        """Can retrieve a node by ID."""
        node = sample_graph.get_node("proposal:1")
        assert node is not None
        assert node.label == "Proposal 1"

    def test_get_nonexistent_node(self, sample_graph):
        """Getting nonexistent node returns None."""
        node = sample_graph.get_node("nonexistent")
        assert node is None

    def test_get_edges_from(self, sample_graph):
        """Can get edges originating from a node."""
        edges = sample_graph.get_edges_from("proposal:1")
        assert len(edges) == 2  # CONTAINS and PROPOSED_BY

    def test_get_edges_to(self, sample_graph):
        """Can get edges pointing to a node."""
        edges = sample_graph.get_edges_to("claim:1:0")
        assert len(edges) == 2  # CONTAINS from proposal and SUPPORTS from receipt

    def test_get_neighbors(self, sample_graph):
        """Can get neighboring nodes."""
        neighbors = sample_graph.get_neighbors("proposal:1")
        neighbor_ids = {n.id for n in neighbors}
        assert "claim:1:0" in neighbor_ids
        assert "agent:worker-1" in neighbor_ids


class TestGraphTransforms:
    """Test Maltego-style transforms."""

    def test_claims_without_evidence(self, sample_graph):
        """Can find claims lacking evidence."""
        unverified = sample_graph.claims_without_evidence()

        # claim:2:0 has no SUPPORTS edge
        assert len(unverified) == 1
        assert unverified[0].id == "claim:2:0"

    def test_expand_dependency_chain(self, sample_graph):
        """Can expand decision dependency chain."""
        subgraph = sample_graph.expand_dependency_chain("decision:2")

        # Should include decision:2 and decision:1 (superseded)
        assert "decision:2" in subgraph.nodes
        assert "decision:1" in subgraph.nodes
        assert len(subgraph.edges) == 1  # The supersedes edge

    def test_weak_grounding(self, sample_graph):
        """Can find proposals with weak grounding."""
        weak = sample_graph.weak_grounding(threshold=2)

        # proposal:1 has 1 receipt, proposal:2 has 0
        # Both should be weak with threshold=2
        assert len(weak) == 2

    def test_weak_grounding_high_threshold(self, sample_graph):
        """High threshold catches more proposals."""
        weak = sample_graph.weak_grounding(threshold=10)
        assert len(weak) == 2

    def test_rejection_patterns(self, sample_graph):
        """Can group rejections by pattern."""
        patterns = sample_graph.rejection_patterns()

        assert "file_not_found" in patterns
        assert len(patterns["file_not_found"]) == 1

    def test_contradictions_after_session(self, sample_graph):
        """Can find contradictions after a session."""
        # Add a contradiction edge
        sample_graph.add_edge(Edge(
            source="claim:2:0",
            target="decision:1",
            type=EdgeType.CONTRADICTS,
        ))

        # Look for contradictions after session:1
        contradictions = sample_graph.contradictions_after_session("session:1")

        # claim:2:0 was created after session:1 and contradicts decision:1
        assert len(contradictions) == 1
        claim, decision = contradictions[0]
        assert claim.id == "claim:2:0"
        assert decision.id == "decision:1"

    def test_actor_authority_map(self, sample_graph):
        """Can map actor authority."""
        authority = sample_graph.actor_authority_map()

        assert "agent:worker-1" in authority
        assert authority["agent:worker-1"]["proposals"] == 1


class TestGraphExport:
    """Test graph export formats."""

    def test_to_dict(self, sample_graph):
        """Can export to dictionary."""
        data = sample_graph.to_dict()

        assert "nodes" in data
        assert "edges" in data
        assert "metadata" in data
        assert data["metadata"]["node_count"] == len(sample_graph.nodes)
        assert data["metadata"]["edge_count"] == len(sample_graph.edges)

    def test_to_json(self, sample_graph):
        """Can export to JSON string."""
        json_str = sample_graph.to_json()

        # Should be valid JSON
        data = json.loads(json_str)
        assert "nodes" in data

    def test_to_cytoscape(self, sample_graph):
        """Can export to Cytoscape format."""
        cyto = sample_graph.to_cytoscape()

        assert "elements" in cyto
        # Should have both nodes and edges
        assert len(cyto["elements"]) > len(sample_graph.nodes)

    def test_to_graphviz(self, sample_graph):
        """Can export to Graphviz DOT format."""
        dot = sample_graph.to_graphviz()

        assert "digraph AuditGraph" in dot
        assert "proposal:1" in dot
        assert "->" in dot

    def test_to_obsidian_canvas(self, sample_graph):
        """Can export to Obsidian Canvas format."""
        canvas = sample_graph.to_obsidian_canvas()

        assert "nodes" in canvas
        assert "edges" in canvas


class TestNodeSerialization:
    """Test node to_dict method."""

    def test_node_to_dict(self):
        """Node can serialize to dict."""
        node = Node(
            id="test:1",
            type=NodeType.PROPOSAL,
            label="Test",
            properties={"key": "value"},
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        data = node.to_dict()

        assert data["id"] == "test:1"
        assert data["type"] == "proposal"
        assert data["label"] == "Test"
        assert data["properties"]["key"] == "value"
        assert "2024-01-15" in data["timestamp"]

    def test_node_without_timestamp(self):
        """Node without timestamp serializes correctly."""
        node = Node(id="test:1", type=NodeType.CLAIM, label="Test")
        data = node.to_dict()

        assert data["timestamp"] is None


class TestEdgeSerialization:
    """Test edge to_dict method."""

    def test_edge_to_dict(self):
        """Edge can serialize to dict."""
        edge = Edge(
            source="a",
            target="b",
            type=EdgeType.SUPPORTS,
            properties={"weight": 1},
            timestamp=datetime(2024, 1, 15, tzinfo=timezone.utc),
        )

        data = edge.to_dict()

        assert data["source"] == "a"
        assert data["target"] == "b"
        assert data["type"] == "supports"
        assert data["properties"]["weight"] == 1


class TestSubgraphForTask:
    """Test task subgraph extraction."""

    def test_subgraph_for_task(self):
        """Can extract subgraph for a task."""
        graph = AuditGraph()

        # Add parent task
        graph.add_node(Node(id="task:parent", type=NodeType.TASK, label="Parent"))

        # Add subtasks
        graph.add_node(Node(id="task:child1", type=NodeType.TASK, label="Child 1"))
        graph.add_node(Node(id="task:child2", type=NodeType.TASK, label="Child 2"))

        # Add edges
        graph.add_edge(Edge(
            source="task:child1",
            target="task:parent",
            type=EdgeType.SUBTASK_OF,
        ))
        graph.add_edge(Edge(
            source="task:child2",
            target="task:parent",
            type=EdgeType.SUBTASK_OF,
        ))

        # Extract subgraph
        subgraph = graph.subgraph_for_task("task:parent")

        assert "task:parent" in subgraph.nodes
        assert "task:child1" in subgraph.nodes
        assert "task:child2" in subgraph.nodes


class TestSessionDrift:
    """Test session drift analysis."""

    def test_no_drift_when_no_sessions(self, empty_graph):
        """No drift when there are no sessions."""
        drift = empty_graph.session_drift()
        assert len(drift) == 0

    def test_no_drift_when_no_contradictions(self, sample_graph):
        """No drift when no contradictions occur."""
        drift = sample_graph.session_drift()
        assert len(drift) == 0

    def test_detects_drift_with_contradictions(self, sample_graph):
        """Detects drift when contradictions occur."""
        # Add contradiction after session:1
        sample_graph.add_edge(Edge(
            source="claim:2:0",
            target="decision:1",
            type=EdgeType.CONTRADICTS,
        ))

        drift = sample_graph.session_drift()

        # Should detect contradiction introduced after session:1
        assert len(drift) >= 1
        assert drift[0]["type"] == "contradiction"


class TestRejectionPatternNormalization:
    """Test rejection pattern normalization."""

    def test_file_not_found_pattern(self, empty_graph):
        """Recognizes file not found pattern."""
        pattern = empty_graph._normalize_rejection_pattern("File not found: test.py")
        assert pattern == "file_not_found"

    def test_decision_conflict_pattern(self, empty_graph):
        """Recognizes decision conflict pattern."""
        pattern = empty_graph._normalize_rejection_pattern("Conflicts with existing decision")
        assert pattern == "decision_conflict"

    def test_test_failure_pattern(self, empty_graph):
        """Recognizes test failure pattern."""
        pattern = empty_graph._normalize_rejection_pattern("Tests failed with exit code 1")
        assert pattern == "test_failure"

    def test_permission_denied_pattern(self, empty_graph):
        """Recognizes permission denied pattern."""
        pattern = empty_graph._normalize_rejection_pattern("Agent not allowed to modify file")
        assert pattern == "permission_denied"

    def test_missing_evidence_pattern(self, empty_graph):
        """Recognizes missing evidence pattern."""
        pattern = empty_graph._normalize_rejection_pattern("No receipt provided")
        assert pattern == "missing_evidence"

    def test_unknown_pattern(self, empty_graph):
        """Unknown patterns become 'other'."""
        pattern = empty_graph._normalize_rejection_pattern("Something else happened")
        assert pattern == "other"


class TestStableSummary:
    """Test StableSummary dataclass."""

    def test_create_summary(self):
        """Can create a summary."""
        summary = StableSummary(
            id="test-id",
            title="Test Summary",
        )

        assert summary.id == "test-id"
        assert summary.title == "Test Summary"

    def test_summary_to_dict(self):
        """Summary can serialize to dict."""
        summary = StableSummary(
            id="test-id",
            title="Test",
            decisions=[{"topic": "framework", "choice": "react"}],
            invariants=["framework = react"],
        )

        data = summary.to_dict()

        assert data["id"] == "test-id"
        assert len(data["decisions"]) == 1
        assert len(data["invariants"]) == 1

    def test_summary_from_dict(self):
        """Summary can deserialize from dict."""
        data = {
            "id": "test-id",
            "title": "Test",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "decisions": [{"topic": "api", "choice": "rest"}],
            "invariants": ["api = rest"],
        }

        summary = StableSummary.from_dict(data)

        assert summary.id == "test-id"
        assert len(summary.decisions) == 1

    def test_summary_to_markdown(self):
        """Summary can export to markdown."""
        summary = StableSummary(
            id="test-id",
            title="Test Summary",
            decisions=[{"topic": "framework", "choice": "react"}],
            claims_verified=["File exists"],
            claims_unverified=["Tests pass"],
            invariants=["framework = react"],
        )

        md = summary.to_markdown()

        assert "# Test Summary" in md
        assert "## Decisions" in md
        assert "framework" in md
        assert "## Verified Claims" in md
        assert "## Unverified Claims" in md

    def test_summary_to_node(self):
        """Summary can convert to graph node."""
        summary = StableSummary(
            id="test-id",
            title="Test Summary",
        )

        node = summary.to_node()

        assert node.id == "summary:test-id"
        assert node.type == NodeType.SUMMARY
        assert node.label == "Test Summary"


class TestGraphCollapse:
    """Test collapse transform."""

    def test_collapse_entire_graph(self, sample_graph):
        """Can collapse entire graph into summary."""
        summary = sample_graph.collapse(title="Full Graph Summary")

        assert summary.title == "Full Graph Summary"
        assert len(summary.node_ids) == len(sample_graph.nodes)
        assert len(summary.decisions) > 0

    def test_collapse_extracts_decisions(self, sample_graph):
        """Collapse extracts decisions."""
        summary = sample_graph.collapse()

        # sample_graph has 2 decisions
        assert len(summary.decisions) == 2
        topics = {d["topic"] for d in summary.decisions}
        assert "framework" in topics

    def test_collapse_extracts_invariants(self, sample_graph):
        """Collapse extracts invariants from decisions."""
        summary = sample_graph.collapse(extract_invariants=True)

        # Should have invariant for each decision
        assert len(summary.invariants) == 2
        assert any("framework" in inv for inv in summary.invariants)

    def test_collapse_classifies_claims(self, sample_graph):
        """Collapse classifies claims as verified/unverified."""
        summary = sample_graph.collapse()

        # claim:1:0 has receipt, claim:2:0 does not
        assert "File exists" in summary.claims_verified
        assert "Tests pass" in summary.claims_unverified

    def test_collapse_captures_rejections(self, sample_graph):
        """Collapse captures rejections."""
        summary = sample_graph.collapse()

        assert len(summary.rejections) == 1
        assert "File not found" in summary.rejections[0]["reason"]

    def test_collapse_tracks_agents(self, sample_graph):
        """Collapse tracks agents involved."""
        summary = sample_graph.collapse()

        assert "worker-1" in summary.agents_involved

    def test_collapse_with_notes(self, sample_graph):
        """Collapse can include notes."""
        summary = sample_graph.collapse(notes="Additional context here")

        assert summary.notes == "Additional context here"
        assert "Additional context here" in summary.to_markdown()

    def test_collapse_subgraph(self, sample_graph):
        """Can collapse a subgraph."""
        # Create a subgraph with just the decisions
        subgraph = sample_graph.expand_dependency_chain("decision:2")

        summary = sample_graph.collapse(subgraph, title="Decision Chain")

        assert summary.title == "Decision Chain"
        assert len(summary.node_ids) == 2  # Just the two decisions

    def test_collapse_and_add(self, sample_graph):
        """Collapse and add creates summary node in graph."""
        initial_count = len(sample_graph.nodes)

        summary_node = sample_graph.collapse_and_add(title="Added Summary")

        assert len(sample_graph.nodes) == initial_count + 1
        assert summary_node.id in sample_graph.nodes
        assert summary_node.type == NodeType.SUMMARY

        # Should have SUMMARIZES edges
        summarizes_edges = [
            e for e in sample_graph.edges
            if e.type == EdgeType.SUMMARIZES
        ]
        assert len(summarizes_edges) > 0

    def test_collapse_time_range(self, sample_graph):
        """Collapse captures time range."""
        summary = sample_graph.collapse()

        assert summary.time_range[0] is not None
        assert summary.time_range[1] is not None
        assert summary.time_range[0] <= summary.time_range[1]

    def test_collapse_contradictions_resolved(self):
        """Collapse captures resolved contradictions (supersedes)."""
        graph = AuditGraph()

        # Add decisions with supersedes relationship
        graph.add_node(Node(
            id="decision:old",
            type=NodeType.DECISION,
            label="framework: angular",
            properties={"topic": "framework", "choice": "angular"},
        ))
        graph.add_node(Node(
            id="decision:new",
            type=NodeType.DECISION,
            label="framework: react",
            properties={"topic": "framework", "choice": "react"},
        ))
        graph.add_edge(Edge(
            source="decision:new",
            target="decision:old",
            type=EdgeType.SUPERSEDES,
        ))

        summary = graph.collapse()

        assert len(summary.contradictions_resolved) == 1
        assert summary.contradictions_resolved[0]["old"] == "framework: angular"
        assert summary.contradictions_resolved[0]["new"] == "framework: react"
