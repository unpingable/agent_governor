# SPDX-License-Identifier: Apache-2.0
"""Tests for the direction tracking module."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path

from governor.direction import (
    # Enums
    CommitmentType,
    AnchorType,
    RelationType,
    ViolationSeverity,
    # Data classes
    Commitment,
    Anchor,
    Relation,
    Trajectory,
    DeltaT,
    Violation,
    Triangle,
    # Classes
    BeliefGraph,
    DirectionLedger,
    # Convenience functions
    create_direction_ledger,
    create_fiction_anchors,
    create_nonfiction_anchors,
    create_thesis_commitment,
    create_chekhov_commitment,
)


class TestCommitmentType:
    """Tests for CommitmentType enum."""

    def test_all_types_exist(self):
        """Test that all commitment types are defined."""
        assert CommitmentType.PROMISE
        assert CommitmentType.PREDICTION
        assert CommitmentType.THESIS
        assert CommitmentType.FORESHADOWING
        assert CommitmentType.DEADLINE
        assert CommitmentType.CHEKHOV
        assert CommitmentType.SETUP


class TestAnchorType:
    """Tests for AnchorType enum."""

    def test_all_types_exist(self):
        """Test that all anchor types are defined."""
        assert AnchorType.WORLD_RULE
        assert AnchorType.CANON_FACT
        assert AnchorType.CITATION
        assert AnchorType.AXIOM
        assert AnchorType.ORACLE
        assert AnchorType.DEFINITION
        assert AnchorType.CONSTRAINT


class TestRelationType:
    """Tests for RelationType enum."""

    def test_all_types_exist(self):
        """Test that all relation types are defined."""
        assert RelationType.IMPLIES
        assert RelationType.CONTRADICTS
        assert RelationType.REQUIRES
        assert RelationType.ENABLES
        assert RelationType.BLOCKS
        assert RelationType.SUPPORTS
        assert RelationType.UNDERMINES
        assert RelationType.PRECEDES
        assert RelationType.FOLLOWS


class TestCommitment:
    """Tests for Commitment dataclass."""

    def test_create_commitment(self):
        """Test creating a commitment."""
        commitment = Commitment(
            id="test_1",
            commitment_type=CommitmentType.PROMISE,
            content="The hero will return",
            created_at=datetime.now(timezone.utc),
            deadline=10,
            deadline_type="chapter",
        )

        assert commitment.id == "test_1"
        assert commitment.commitment_type == CommitmentType.PROMISE
        assert commitment.fulfilled is False
        assert commitment.deadline == 10

    def test_serialization(self):
        """Test commitment serialization."""
        commitment = Commitment(
            id="test_1",
            commitment_type=CommitmentType.CHEKHOV,
            content="Gun on the wall",
            created_at=datetime.now(timezone.utc),
            deadline=5,
            predictions=["The gun will fire"],
        )

        data = commitment.to_dict()
        restored = Commitment.from_dict(data)

        assert restored.id == commitment.id
        assert restored.commitment_type == commitment.commitment_type
        assert restored.content == commitment.content
        assert restored.predictions == commitment.predictions


class TestAnchor:
    """Tests for Anchor dataclass."""

    def test_create_anchor(self):
        """Test creating an anchor."""
        anchor = Anchor(
            id="anchor_1",
            anchor_type=AnchorType.WORLD_RULE,
            content="Magic requires verbal incantation",
            created_at=datetime.now(timezone.utc),
            confidence=1.0,
        )

        assert anchor.id == "anchor_1"
        assert anchor.anchor_type == AnchorType.WORLD_RULE
        assert anchor.confidence == 1.0

    def test_serialization(self):
        """Test anchor serialization."""
        anchor = Anchor(
            id="anchor_1",
            anchor_type=AnchorType.CITATION,
            content="Smith (2020) argues X",
            created_at=datetime.now(timezone.utc),
            source="doi:10.1234/example",
        )

        data = anchor.to_dict()
        restored = Anchor.from_dict(data)

        assert restored.id == anchor.id
        assert restored.anchor_type == anchor.anchor_type
        assert restored.source == anchor.source


class TestRelation:
    """Tests for Relation dataclass."""

    def test_create_relation(self):
        """Test creating a relation."""
        relation = Relation(
            source_id="a",
            target_id="b",
            relation_type=RelationType.IMPLIES,
            strength=0.9,
        )

        assert relation.source_id == "a"
        assert relation.target_id == "b"
        assert relation.relation_type == RelationType.IMPLIES
        assert relation.strength == 0.9

    def test_serialization(self):
        """Test relation serialization."""
        relation = Relation(
            source_id="a",
            target_id="b",
            relation_type=RelationType.CONTRADICTS,
            context="In chapter 3",
        )

        data = relation.to_dict()
        restored = Relation.from_dict(data)

        assert restored.source_id == relation.source_id
        assert restored.relation_type == relation.relation_type
        assert restored.context == relation.context


class TestTrajectory:
    """Tests for Trajectory dataclass."""

    def test_create_trajectory(self):
        """Test creating a trajectory."""
        trajectory = Trajectory(
            current_position="Introduction",
            destination="Conclusion",
            waypoints=["Method", "Results", "Discussion"],
            heading="Building argument for X",
        )

        assert trajectory.current_position == "Introduction"
        assert trajectory.destination == "Conclusion"
        assert len(trajectory.waypoints) == 3
        assert trajectory.drift == 0.0

    def test_serialization(self):
        """Test trajectory serialization."""
        trajectory = Trajectory(
            current_position="Chapter 5",
            destination="Chapter 12",
            waypoints=["Chapter 8", "Chapter 10"],
            completed_waypoints=["Chapter 3"],
            drift=0.2,
        )

        data = trajectory.to_dict()
        restored = Trajectory.from_dict(data)

        assert restored.current_position == trajectory.current_position
        assert restored.waypoints == trajectory.waypoints
        assert restored.drift == trajectory.drift


class TestDeltaT:
    """Tests for DeltaT dataclass."""

    def test_create_delta_t(self):
        """Test creating a DeltaT measurement."""
        delta = DeltaT(
            commitment_id="commit_1",
            predicted="The villain escapes",
            actual="The villain is captured",
            delta=0.8,
        )

        assert delta.commitment_id == "commit_1"
        assert delta.delta == 0.8

    def test_serialization(self):
        """Test DeltaT serialization."""
        delta = DeltaT(
            commitment_id="commit_1",
            predicted="X happens",
            actual="Y happens",
            delta=0.6,
            notes="Partial match",
        )

        data = delta.to_dict()
        restored = DeltaT.from_dict(data)

        assert restored.commitment_id == delta.commitment_id
        assert restored.delta == delta.delta
        assert restored.notes == delta.notes


class TestViolation:
    """Tests for Violation dataclass."""

    def test_create_violation(self):
        """Test creating a violation."""
        violation = Violation(
            anchor_id="anchor_1",
            violating_content="Magic happens silently",
            violation_type="direct_negation",
            severity=ViolationSeverity.HIGH,
            location="Chapter 7, page 42",
        )

        assert violation.anchor_id == "anchor_1"
        assert violation.severity == ViolationSeverity.HIGH
        assert violation.resolved is False

    def test_serialization(self):
        """Test violation serialization."""
        violation = Violation(
            anchor_id="anchor_1",
            violating_content="Contradicting content",
            violation_type="impossibility",
            severity=ViolationSeverity.CRITICAL,
        )

        data = violation.to_dict()
        restored = Violation.from_dict(data)

        assert restored.anchor_id == violation.anchor_id
        assert restored.severity == violation.severity


class TestBeliefGraph:
    """Tests for BeliefGraph."""

    def test_add_node(self):
        """Test adding nodes to the graph."""
        graph = BeliefGraph()
        graph.add_node("a", "Fact A", "fact")
        graph.add_node("b", "Fact B", "fact")

        assert graph.get_node("a") is not None
        assert graph.get_node("a")["content"] == "Fact A"

    def test_add_relation(self):
        """Test adding relations to the graph."""
        graph = BeliefGraph()
        graph.add_node("a", "Fact A", "fact")
        graph.add_node("b", "Fact B", "fact")

        relation = Relation("a", "b", RelationType.IMPLIES)
        graph.add_relation(relation)

        relations_from_a = graph.get_relations_from("a")
        assert len(relations_from_a) == 1
        assert relations_from_a[0].target_id == "b"

    def test_find_path(self):
        """Test finding paths in the graph."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")
        graph.add_node("c", "C", "fact")

        graph.add_relation(Relation("a", "b", RelationType.IMPLIES))
        graph.add_relation(Relation("b", "c", RelationType.IMPLIES))

        path = graph.find_path("a", "c")
        assert path == ["a", "b", "c"]

    def test_find_path_no_connection(self):
        """Test finding paths when no connection exists."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")

        path = graph.find_path("a", "b")
        assert path is None

    def test_detect_cycles(self):
        """Test cycle detection."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")
        graph.add_node("c", "C", "fact")

        graph.add_relation(Relation("a", "b", RelationType.IMPLIES))
        graph.add_relation(Relation("b", "c", RelationType.IMPLIES))
        graph.add_relation(Relation("c", "a", RelationType.IMPLIES))

        cycles = graph.detect_cycles()
        assert len(cycles) >= 1

    def test_detect_contradictions(self):
        """Test contradiction detection."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")

        graph.add_relation(Relation("a", "b", RelationType.CONTRADICTS))

        contradictions = graph.detect_contradictions()
        assert len(contradictions) == 1
        assert contradictions[0][0] == "a"
        assert contradictions[0][1] == "b"

    def test_detect_triangles(self):
        """Test impossible triangle detection."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")
        graph.add_node("c", "C", "fact")

        # A implies B, B implies C, but A contradicts C
        graph.add_relation(Relation("a", "b", RelationType.IMPLIES))
        graph.add_relation(Relation("b", "c", RelationType.IMPLIES))
        graph.add_relation(Relation("a", "c", RelationType.CONTRADICTS))

        triangles = graph.detect_triangles()
        assert len(triangles) == 1
        assert set(triangles[0].nodes) == {"a", "b", "c"}

    def test_get_implications(self):
        """Test getting transitive implications."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")
        graph.add_node("c", "C", "fact")
        graph.add_node("d", "D", "fact")

        graph.add_relation(Relation("a", "b", RelationType.IMPLIES))
        graph.add_relation(Relation("b", "c", RelationType.IMPLIES))
        graph.add_relation(Relation("a", "d", RelationType.IMPLIES))

        implications = graph.get_implications("a")
        assert set(implications) == {"b", "c", "d"}

    def test_serialization(self):
        """Test graph serialization."""
        graph = BeliefGraph()
        graph.add_node("a", "A", "fact")
        graph.add_node("b", "B", "fact")
        graph.add_relation(Relation("a", "b", RelationType.IMPLIES))

        data = graph.to_dict()
        restored = BeliefGraph.from_dict(data)

        assert restored.get_node("a") is not None
        assert len(restored.get_relations_from("a")) == 1


class TestDirectionLedger:
    """Tests for DirectionLedger."""

    def test_add_commitment(self):
        """Test adding a commitment."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "The mystery will be solved",
            CommitmentType.PROMISE,
            deadline=12,
        )

        assert commit_id is not None
        commitment = ledger.get_commitment(commit_id)
        assert commitment is not None
        assert commitment.content == "The mystery will be solved"

    def test_fulfill_commitment(self):
        """Test fulfilling a commitment."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "Setup for payoff",
            CommitmentType.SETUP,
        )

        ledger.fulfill_commitment(commit_id, "Payoff in chapter 10")

        commitment = ledger.get_commitment(commit_id)
        assert commitment.fulfilled is True
        assert commitment.fulfilled_how == "Payoff in chapter 10"

    def test_fulfill_with_prediction_computes_delta_t(self):
        """Test that fulfilling with predictions computes Δt."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "The hero escapes",
            CommitmentType.PREDICTION,
            predictions=["hero escapes prison through tunnel"],
        )

        delta_t = ledger.fulfill_commitment(
            commit_id,
            "Chapter 8 escape sequence",
            actual_outcome="hero escapes prison through window",
        )

        assert delta_t is not None
        assert 0.0 <= delta_t.delta <= 1.0

    def test_abandon_commitment(self):
        """Test abandoning a commitment."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "Subplot that goes nowhere",
            CommitmentType.SETUP,
        )

        ledger.abandon_commitment(commit_id, "Decided to cut this subplot")

        commitment = ledger.get_commitment(commit_id)
        assert commitment.abandoned is True
        assert commitment.abandoned_reason == "Decided to cut this subplot"

    def test_check_deadlines(self):
        """Test checking for overdue commitments."""
        ledger = DirectionLedger()

        # Overdue commitment
        ledger.add_commitment(
            "Should have happened by chapter 5",
            CommitmentType.DEADLINE,
            deadline=5,
        )

        # Not yet due
        ledger.add_commitment(
            "Due in chapter 20",
            CommitmentType.DEADLINE,
            deadline=20,
        )

        overdue = ledger.check_deadlines(current_position=10)
        assert len(overdue) == 1
        assert "chapter 5" in overdue[0].content

    def test_get_unfulfilled(self):
        """Test getting unfulfilled commitments."""
        ledger = DirectionLedger()

        commit1 = ledger.add_commitment("Unfulfilled 1", CommitmentType.PROMISE)
        commit2 = ledger.add_commitment("Unfulfilled 2", CommitmentType.PROMISE)
        commit3 = ledger.add_commitment("Fulfilled", CommitmentType.PROMISE)

        ledger.fulfill_commitment(commit3, "Done")

        unfulfilled = ledger.get_unfulfilled()
        assert len(unfulfilled) == 2

    def test_add_anchor(self):
        """Test adding an anchor."""
        ledger = DirectionLedger()
        anchor_id = ledger.add_anchor(
            "Magic requires line of sight",
            AnchorType.WORLD_RULE,
            source="Chapter 1 exposition",
        )

        anchor = ledger.get_anchor(anchor_id)
        assert anchor is not None
        assert anchor.anchor_type == AnchorType.WORLD_RULE

    def test_check_against_anchors_no_violation(self):
        """Test checking content that doesn't violate anchors."""
        ledger = DirectionLedger()
        ledger.add_anchor("Magic requires words", AnchorType.WORLD_RULE)

        violations = ledger.check_against_anchors("The wizard spoke the spell")
        assert len(violations) == 0

    def test_check_against_anchors_with_violation(self):
        """Test checking content that violates an anchor."""
        ledger = DirectionLedger()
        ledger.add_anchor("Magic requires words", AnchorType.WORLD_RULE)

        violations = ledger.check_against_anchors("Magic never requires words")
        assert len(violations) == 1
        assert violations[0].violation_type == "direct_negation"

    def test_set_trajectory(self):
        """Test setting a trajectory."""
        ledger = DirectionLedger()
        ledger.set_trajectory(
            current_position="Act 1",
            destination="Act 3 Resolution",
            waypoints=["Act 2 Confrontation", "Climax"],
            heading="Building toward final battle",
        )

        trajectory = ledger.get_trajectory()
        assert trajectory is not None
        assert trajectory.current_position == "Act 1"
        assert len(trajectory.waypoints) == 2

    def test_update_position(self):
        """Test updating position along trajectory."""
        ledger = DirectionLedger()
        ledger.set_trajectory(
            current_position="Start",
            destination="End",
            waypoints=["Middle"],
        )

        drift = ledger.update_position("Middle")
        trajectory = ledger.get_trajectory()

        assert "Middle" in trajectory.completed_waypoints
        assert "Middle" not in trajectory.waypoints

    def test_add_relation(self):
        """Test adding relations to belief graph."""
        ledger = DirectionLedger()

        anchor1 = ledger.add_anchor("Fact A", AnchorType.AXIOM)
        anchor2 = ledger.add_anchor("Fact B", AnchorType.AXIOM)

        ledger.add_relation(anchor1, anchor2, RelationType.IMPLIES)

        graph = ledger.get_belief_graph()
        relations = graph.get_relations_from(anchor1)
        assert len(relations) == 1

    def test_check_consistency_clean(self):
        """Test consistency check with no issues."""
        ledger = DirectionLedger()
        ledger.add_anchor("Fact A", AnchorType.AXIOM)
        ledger.add_anchor("Fact B", AnchorType.AXIOM)

        triangles, contradictions = ledger.check_consistency()
        assert len(triangles) == 0
        assert len(contradictions) == 0

    def test_check_consistency_with_contradiction(self):
        """Test consistency check with contradiction."""
        ledger = DirectionLedger()

        a = ledger.add_anchor("Fact A", AnchorType.AXIOM)
        b = ledger.add_anchor("Fact B", AnchorType.AXIOM)

        ledger.add_relation(a, b, RelationType.CONTRADICTS)

        triangles, contradictions = ledger.check_consistency()
        assert len(contradictions) == 1

    def test_record_and_verify_prediction(self):
        """Test recording and verifying predictions."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "Something will happen",
            CommitmentType.PREDICTION,
        )

        ledger.record_prediction(commit_id, "The hero wins the battle")
        delta_t = ledger.verify_prediction(commit_id, "The hero loses the battle")

        # Jaccard: intersection={the,hero,battle}/union={the,hero,wins,loses,battle} = 3/5 = 0.6
        # Delta = 1 - 0.6 = 0.4
        assert delta_t.delta > 0.3  # Should show some mismatch
        assert delta_t.delta < 0.7  # But not complete (shares words)

    def test_get_delta_t_history(self):
        """Test getting Δt history."""
        ledger = DirectionLedger()
        commit_id = ledger.add_commitment(
            "Prediction",
            CommitmentType.PREDICTION,
            predictions=["outcome X"],
        )

        ledger.fulfill_commitment(commit_id, "Done", actual_outcome="outcome Y")

        history = ledger.get_delta_t_history()
        assert len(history) == 1

    def test_get_aggregate_delta_t(self):
        """Test aggregate Δt calculation."""
        ledger = DirectionLedger()

        # Create multiple predictions with different outcomes
        for i in range(3):
            commit_id = ledger.add_commitment(
                f"Prediction {i}",
                CommitmentType.PREDICTION,
                predictions=[f"outcome {i}"],
            )
            ledger.fulfill_commitment(
                commit_id,
                f"Done {i}",
                actual_outcome=f"different outcome {i}",
            )

        aggregate = ledger.get_aggregate_delta_t()
        assert 0.0 <= aggregate <= 1.0

    def test_get_violations(self):
        """Test getting violations."""
        ledger = DirectionLedger()
        ledger.add_anchor("Magic requires words", AnchorType.WORLD_RULE)

        # This should trigger a violation (negates the rule)
        ledger.check_against_anchors("Magic does not require words")

        violations = ledger.get_violations()
        assert len(violations) == 1

        unresolved = ledger.get_violations(resolved=False)
        assert len(unresolved) == 1

    def test_resolve_violation(self):
        """Test resolving a violation."""
        ledger = DirectionLedger()
        ledger.add_anchor("Rule X", AnchorType.WORLD_RULE)
        ledger.check_against_anchors("Never Rule X")

        ledger.resolve_violation(0, "Fixed in revision")

        resolved = ledger.get_violations(resolved=True)
        assert len(resolved) == 1
        assert resolved[0].resolution == "Fixed in revision"

    def test_get_direction_summary(self):
        """Test getting direction summary."""
        ledger = DirectionLedger()

        ledger.add_commitment("Promise 1", CommitmentType.PROMISE)
        ledger.add_commitment("Promise 2", CommitmentType.PROMISE)
        ledger.add_anchor("Rule 1", AnchorType.WORLD_RULE)
        ledger.set_trajectory("Start", "End", ["Middle"])

        summary = ledger.get_direction_summary()

        assert summary["commitments"]["total"] == 2
        assert summary["commitments"]["pending"] == 2
        assert summary["anchors"]["total"] == 1
        assert summary["trajectory"] is not None

    def test_get_coherence_score(self):
        """Test coherence score calculation."""
        ledger = DirectionLedger()

        # Clean ledger should have high coherence
        ledger.add_commitment("Promise", CommitmentType.PROMISE)
        ledger.add_anchor("Rule", AnchorType.WORLD_RULE)

        score = ledger.get_coherence_score()
        assert score > 0.8

    def test_coherence_degrades_with_issues(self):
        """Test that coherence degrades with issues."""
        ledger = DirectionLedger()

        a = ledger.add_anchor("Fact A", AnchorType.AXIOM)
        b = ledger.add_anchor("Fact B", AnchorType.AXIOM)

        # Add a contradiction
        ledger.add_relation(a, b, RelationType.CONTRADICTS)

        score = ledger.get_coherence_score()
        assert score < 0.9  # Should be penalized

    def test_persistence(self, tmp_path):
        """Test persistence to disk."""
        storage_dir = tmp_path / ".governor"

        # Create and populate ledger
        ledger = DirectionLedger(storage_dir)
        commit_id = ledger.add_commitment("Promise", CommitmentType.PROMISE)
        anchor_id = ledger.add_anchor("Rule", AnchorType.WORLD_RULE)
        ledger.set_trajectory("Start", "End")

        # Create new ledger from same storage
        ledger2 = DirectionLedger(storage_dir)

        assert ledger2.get_commitment(commit_id) is not None
        assert ledger2.get_anchor(anchor_id) is not None
        assert ledger2.get_trajectory() is not None


class TestConvenienceFunctions:
    """Tests for convenience functions."""

    def test_create_direction_ledger(self):
        """Test creating a direction ledger."""
        ledger = create_direction_ledger()
        assert ledger is not None

    def test_create_fiction_anchors(self):
        """Test creating fiction anchors from world rules."""
        ledger = DirectionLedger()
        rules = [
            "Magic requires verbal incantation",
            "Vampires cannot enter without invitation",
            "Time travel creates paradoxes",
        ]

        anchor_ids = create_fiction_anchors(ledger, rules)

        assert len(anchor_ids) == 3
        for anchor_id in anchor_ids:
            anchor = ledger.get_anchor(anchor_id)
            assert anchor.anchor_type == AnchorType.WORLD_RULE

    def test_create_nonfiction_anchors(self):
        """Test creating non-fiction anchors from citations."""
        ledger = DirectionLedger()
        citations = [
            ("Smith argues X", "Smith (2020)"),
            ("Jones found Y", "Jones et al. (2021)"),
        ]

        anchor_ids = create_nonfiction_anchors(ledger, citations)

        assert len(anchor_ids) == 2
        for anchor_id in anchor_ids:
            anchor = ledger.get_anchor(anchor_id)
            assert anchor.anchor_type == AnchorType.CITATION
            assert anchor.source is not None

    def test_create_thesis_commitment(self):
        """Test creating a thesis commitment."""
        ledger = DirectionLedger()
        commit_id = create_thesis_commitment(
            ledger,
            "This paper argues that X leads to Y",
            deadline=5,
        )

        commitment = ledger.get_commitment(commit_id)
        assert commitment.commitment_type == CommitmentType.THESIS
        assert commitment.deadline_type == "section"

    def test_create_chekhov_commitment(self):
        """Test creating a Chekhov's gun commitment."""
        ledger = DirectionLedger()
        commit_id = create_chekhov_commitment(
            ledger,
            "The gun on the mantelpiece",
            payoff_deadline=10,
        )

        commitment = ledger.get_commitment(commit_id)
        assert commitment.commitment_type == CommitmentType.CHEKHOV
        assert commitment.deadline == 10
        assert commitment.deadline_type == "chapter"


class TestFictionScenarios:
    """Integration tests for fiction scenarios."""

    def test_novel_direction_tracking(self):
        """Test tracking direction for a novel."""
        ledger = DirectionLedger()

        # Set up world rules
        create_fiction_anchors(ledger, [
            "Magic requires sacrifice",
            "The dead cannot return",
        ])

        # Set up trajectory
        ledger.set_trajectory(
            current_position="Chapter 1: Introduction",
            destination="Chapter 20: Resolution",
            waypoints=[
                "Chapter 5: First confrontation",
                "Chapter 10: Midpoint reversal",
                "Chapter 15: All is lost",
            ],
        )

        # Add Chekhov's gun
        gun_id = create_chekhov_commitment(
            ledger,
            "The mysterious letter in the desk",
            payoff_deadline=15,
        )

        # Progress through story
        ledger.update_position("Chapter 5: First confrontation")
        ledger.complete_waypoint("Chapter 5: First confrontation")

        # Check status at chapter 10
        overdue = ledger.check_deadlines(10)
        assert len(overdue) == 0  # Gun not yet overdue

        # Fulfill the gun
        ledger.fulfill_commitment(gun_id, "Letter revealed in chapter 12")

        summary = ledger.get_direction_summary()
        assert summary["commitments"]["fulfilled"] == 1

    def test_detect_world_rule_violation(self):
        """Test detecting when story violates world rules."""
        ledger = DirectionLedger()

        # Establish rule
        ledger.add_anchor(
            "Magic requires sacrifice",
            AnchorType.WORLD_RULE,
            source="Chapter 2 exposition",
        )

        # This should not violate (doesn't negate)
        violations = ledger.check_against_anchors(
            "The wizard made a great sacrifice to cast the spell"
        )
        assert len(violations) == 0

        # This should violate (negates the rule)
        violations = ledger.check_against_anchors(
            "Magic does not require sacrifice in this world"
        )
        assert len(violations) == 1
        assert violations[0].violation_type == "direct_negation"

    def test_custom_violation_checker(self):
        """Test using a custom violation checker."""
        ledger = DirectionLedger()

        ledger.add_anchor(
            "The dead cannot return",
            AnchorType.WORLD_RULE,
        )

        # Custom checker that looks for semantic contradiction
        def semantic_checker(anchor: str, content: str) -> tuple[bool, str]:
            anchor_l = anchor.lower()
            content_l = content.lower()
            # Check if content claims the opposite
            if "dead" in anchor_l and "return" in anchor_l:
                if "dead" in content_l and "return" in content_l:
                    if "can return" in content_l or "returned" in content_l:
                        return True, "semantic_contradiction"
            return False, ""

        # Test with custom checker
        violations = ledger.check_against_anchors(
            "The dead hero returned to life",
            checker=semantic_checker,
        )
        assert len(violations) == 1
        assert violations[0].violation_type == "semantic_contradiction"


class TestNonfictionScenarios:
    """Integration tests for non-fiction scenarios."""

    def test_paper_direction_tracking(self):
        """Test tracking direction for an academic paper."""
        ledger = DirectionLedger()

        # Set up citations as anchors
        create_nonfiction_anchors(ledger, [
            ("Prior work shows X", "Smith 2020"),
            ("Method Y is validated", "Jones 2021"),
        ])

        # Thesis commitment
        thesis_id = create_thesis_commitment(
            ledger,
            "We argue that combining X with Y produces Z",
            deadline=5,  # By section 5
        )

        # Trajectory
        ledger.set_trajectory(
            current_position="Introduction",
            destination="Conclusion",
            waypoints=["Literature Review", "Method", "Results", "Discussion"],
            heading="Building evidence for thesis",
        )

        # Progress
        ledger.update_position("Literature Review")
        ledger.complete_waypoint("Literature Review")

        # Add supporting relations
        ledger.add_relation(
            list(ledger._anchors.keys())[0],  # Smith citation
            thesis_id,
            RelationType.SUPPORTS,
        )

        summary = ledger.get_direction_summary()
        assert summary["trajectory"]["completed_waypoints"] == ["Literature Review"]

    def test_argument_consistency(self):
        """Test checking argument consistency."""
        ledger = DirectionLedger()

        # Build an argument
        claim_a = ledger.add_anchor("Claim A is true", AnchorType.AXIOM)
        claim_b = ledger.add_anchor("Claim B is true", AnchorType.AXIOM)
        claim_c = ledger.add_anchor("Claim C is true", AnchorType.AXIOM)

        # A implies B
        ledger.add_relation(claim_a, claim_b, RelationType.IMPLIES)
        # B implies C
        ledger.add_relation(claim_b, claim_c, RelationType.IMPLIES)

        # Check consistency (should be fine)
        triangles, contradictions = ledger.check_consistency()
        assert len(triangles) == 0
        assert len(contradictions) == 0

        # Now add a contradiction
        ledger.add_relation(claim_a, claim_c, RelationType.CONTRADICTS)

        # Should detect the triangle
        triangles, contradictions = ledger.check_consistency()
        assert len(triangles) == 1 or len(contradictions) == 1
