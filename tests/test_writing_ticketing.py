# SPDX-License-Identifier: Apache-2.0
"""Tests for writing_ticketing.py — Making Failures First-Class Citizens."""

import time

import pytest

from governor.writing_ticketing import (
    ALLOWED_TRANSITIONS,
    AUTO_FIX_TYPES,
    DEFAULT_TICKETING_CONFIG,
    DEFAULT_TICKETING_LAYER,
    ESCALATE_TYPES,
    SEVERITY_ORDER,
    CodeTicketType,
    CorrectionResult,
    LearningSignal,
    ProseTicketType,
    RetentionPolicy,
    RoutingAction,
    RoutingActionType,
    Ticket,
    TicketDomain,
    TicketingConfig,
    TicketingLayer,
    TicketingLayerInput,
    TicketingLayerOutput,
    TicketingMetrics,
    TicketSeverity,
    TicketStatus,
    TicketStore,
    TicketTransition,
    TicketType,
    ViolationDetection,
    calculate_similarity,
    compute_metrics,
    create_ticketing_layer,
    extract_learning_signals,
    find_similar_tickets,
    get_auto_fix,
    has_auto_fix,
    is_valid_transition,
    jaccard_similarity,
    map_severity,
    parse_ticket_type,
    severity_level,
    should_escalate,
    tokenize,
)


# =============================================================================
# ProseTicketType Tests
# =============================================================================


class TestProseTicketType:
    def test_all_values(self):
        assert ProseTicketType.GOV_VISIBILITY_LEAK.value == "GOV_VISIBILITY_LEAK"
        assert ProseTicketType.REGIME_COLLISION.value == "REGIME_COLLISION"
        assert ProseTicketType.PREMATURE_CLOSURE.value == "PREMATURE_CLOSURE"
        assert ProseTicketType.TONE_GOVERNANCE_LEAK.value == "TONE_GOVERNANCE_LEAK"
        assert ProseTicketType.COMMITMENT_VIOLATION.value == "COMMITMENT_VIOLATION"
        assert ProseTicketType.AUDIENCE_MISMATCH.value == "AUDIENCE_MISMATCH"
        assert ProseTicketType.EXIT_SHAPE_VIOLATION.value == "EXIT_SHAPE_VIOLATION"
        assert ProseTicketType.PHASE_LOCK_FAILURE.value == "PHASE_LOCK_FAILURE"
        assert ProseTicketType.UNJUSTIFIED_NORMATIVITY.value == "UNJUSTIFIED_NORMATIVITY"
        assert ProseTicketType.TYPE_ERROR.value == "TYPE_ERROR"
        assert ProseTicketType.AUTHORITY_MISMATCH.value == "AUTHORITY_MISMATCH"
        assert ProseTicketType.REPETITION_VIOLATION.value == "REPETITION_VIOLATION"
        assert ProseTicketType.LEGIBILITY_OVERRUN.value == "LEGIBILITY_OVERRUN"
        assert ProseTicketType.META_INVARIANT_VIOLATION.value == "META_INVARIANT_VIOLATION"

    def test_count(self):
        assert len(ProseTicketType) == 14


class TestCodeTicketType:
    def test_all_values(self):
        assert CodeTicketType.UNOWNED_LIABILITY.value == "UNOWNED_LIABILITY"
        assert CodeTicketType.MISSING_INVARIANT.value == "MISSING_INVARIANT"
        assert CodeTicketType.HIDDEN_GOVERNANCE.value == "HIDDEN_GOVERNANCE"
        assert CodeTicketType.FAILURE_SURFACE_HIDDEN.value == "FAILURE_SURFACE_HIDDEN"
        assert CodeTicketType.PREMATURE_ABSTRACTION.value == "PREMATURE_ABSTRACTION"
        assert CodeTicketType.MAGIC_BEHAVIOR.value == "MAGIC_BEHAVIOR"
        assert CodeTicketType.EXCEPTION_SMEAR.value == "EXCEPTION_SMEAR"
        assert CodeTicketType.SCOPE_VIOLATION.value == "SCOPE_VIOLATION"
        assert CodeTicketType.ROLLBACK_GAP.value == "ROLLBACK_GAP"
        assert CodeTicketType.OBSERVABILITY_GAP.value == "OBSERVABILITY_GAP"
        assert CodeTicketType.PHASE_LOCK_FAILURE.value == "PHASE_LOCK_FAILURE"

    def test_count(self):
        assert len(CodeTicketType) == 11


class TestParseTicketType:
    def test_parse_prose_type(self):
        result = parse_ticket_type("GOV_VISIBILITY_LEAK")
        assert result == ProseTicketType.GOV_VISIBILITY_LEAK

    def test_parse_code_type(self):
        result = parse_ticket_type("UNOWNED_LIABILITY")
        assert result == CodeTicketType.UNOWNED_LIABILITY


# =============================================================================
# TicketStatus Tests
# =============================================================================


class TestTicketStatus:
    def test_all_values(self):
        assert TicketStatus.OPEN.value == "open"
        assert TicketStatus.ACKNOWLEDGED.value == "acknowledged"
        assert TicketStatus.FIXED.value == "fixed"
        assert TicketStatus.WONT_FIX.value == "wont_fix"
        assert TicketStatus.DUPLICATE.value == "duplicate"


class TestTicketSeverity:
    def test_all_values(self):
        assert TicketSeverity.INFO.value == "info"
        assert TicketSeverity.WARNING.value == "warning"
        assert TicketSeverity.VIOLATION.value == "violation"
        assert TicketSeverity.CRITICAL.value == "critical"

    def test_severity_order(self):
        assert SEVERITY_ORDER[0] == TicketSeverity.INFO
        assert SEVERITY_ORDER[-1] == TicketSeverity.CRITICAL

    def test_severity_level(self):
        assert severity_level(TicketSeverity.INFO) == 0
        assert severity_level(TicketSeverity.CRITICAL) == 3


class TestMapSeverity:
    def test_info(self):
        assert map_severity(0.1) == TicketSeverity.INFO
        assert map_severity(0.24) == TicketSeverity.INFO

    def test_warning(self):
        assert map_severity(0.25) == TicketSeverity.WARNING
        assert map_severity(0.49) == TicketSeverity.WARNING

    def test_violation(self):
        assert map_severity(0.5) == TicketSeverity.VIOLATION
        assert map_severity(0.74) == TicketSeverity.VIOLATION

    def test_critical(self):
        assert map_severity(0.75) == TicketSeverity.CRITICAL
        assert map_severity(1.0) == TicketSeverity.CRITICAL


# =============================================================================
# TicketDomain Tests
# =============================================================================


class TestTicketDomain:
    def test_all_values(self):
        assert TicketDomain.PROSE.value == "prose"
        assert TicketDomain.CODE.value == "code"


# =============================================================================
# Ticket Tests
# =============================================================================


class TestTicket:
    def test_create(self):
        ticket = Ticket(
            id="TKT-123",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="governance must not leak",
            description="Governance leaked in response",
            context_slice="I'm sorry, but I cannot...",
        )
        assert ticket.id == "TKT-123"
        assert ticket.type == ProseTicketType.GOV_VISIBILITY_LEAK
        assert ticket.status == TicketStatus.OPEN

    def test_to_dict(self):
        ticket = Ticket(
            id="TKT-123",
            created_at=1000.0,
            updated_at=1000.0,
            type=CodeTicketType.UNOWNED_LIABILITY,
            regime="code",
            domain=TicketDomain.CODE,
            severity=TicketSeverity.VIOLATION,
            violated_invariant="ownership required",
            description="No owner specified",
            context_slice="def mysterious_function():",
        )
        d = ticket.to_dict()
        assert d["id"] == "TKT-123"
        assert d["type"] == "UNOWNED_LIABILITY"
        assert d["domain"] == "code"

    def test_from_dict(self):
        d = {
            "id": "TKT-456",
            "created_at": 2000.0,
            "updated_at": 2000.0,
            "type": "REGIME_COLLISION",
            "regime": "comedy",
            "domain": "prose",
            "severity": "critical",
            "violated_invariant": "no collision",
            "description": "Comedy and tragedy collided",
            "context_slice": "It was funny but sad",
        }
        ticket = Ticket.from_dict(d)
        assert ticket.id == "TKT-456"
        assert ticket.type == ProseTicketType.REGIME_COLLISION
        assert ticket.severity == TicketSeverity.CRITICAL


# =============================================================================
# TicketingConfig Tests
# =============================================================================


class TestTicketingConfig:
    def test_defaults(self):
        config = TicketingConfig()
        assert config.enabled is False
        assert config.auto_create is True
        assert config.require_ticket_for_fix is True
        assert config.link_recurring is True
        assert config.retention_policy == RetentionPolicy.SESSION

    def test_to_dict(self):
        config = TicketingConfig(enabled=True)
        d = config.to_dict()
        assert d["enabled"] is True

    def test_from_dict(self):
        d = {
            "enabled": True,
            "retention_policy": "persistent",
        }
        config = TicketingConfig.from_dict(d)
        assert config.enabled is True
        assert config.retention_policy == RetentionPolicy.PERSISTENT


class TestDefaultTicketingConfig:
    def test_disabled_by_default(self):
        assert DEFAULT_TICKETING_CONFIG.enabled is False


# =============================================================================
# ViolationDetection Tests
# =============================================================================


class TestViolationDetection:
    def test_create(self):
        detection = ViolationDetection(
            type=ProseTicketType.PREMATURE_CLOSURE,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="no premature synthesis",
            context="And in conclusion...",
            severity=0.6,
        )
        assert detection.type == ProseTicketType.PREMATURE_CLOSURE
        assert detection.severity == 0.6

    def test_to_dict(self):
        detection = ViolationDetection(
            type=CodeTicketType.MISSING_INVARIANT,
            regime="code",
            domain=TicketDomain.CODE,
            invariant="must have tests",
            context="def foo(): pass",
        )
        d = detection.to_dict()
        assert d["type"] == "MISSING_INVARIANT"


# =============================================================================
# Routing Tests
# =============================================================================


class TestRoutingAction:
    def test_create(self):
        action = RoutingAction(
            action=RoutingActionType.ESCALATE,
            reason="critical",
            escalate_to="human",
        )
        assert action.action == RoutingActionType.ESCALATE

    def test_to_dict(self):
        action = RoutingAction(
            action=RoutingActionType.ADJUST,
            adjustment={"action": "suppress"},
        )
        d = action.to_dict()
        assert d["action"] == "adjust"


class TestAutoFix:
    def test_has_auto_fix(self):
        assert has_auto_fix(ProseTicketType.GOV_VISIBILITY_LEAK) is True
        assert has_auto_fix(ProseTicketType.REGIME_COLLISION) is True
        assert has_auto_fix(CodeTicketType.UNOWNED_LIABILITY) is False

    def test_get_auto_fix(self):
        fix = get_auto_fix(ProseTicketType.GOV_VISIBILITY_LEAK)
        assert fix is not None
        assert "action" in fix


class TestEscalateTypes:
    def test_should_escalate(self):
        assert should_escalate(CodeTicketType.UNOWNED_LIABILITY) is True
        assert should_escalate(CodeTicketType.ROLLBACK_GAP) is True
        assert should_escalate(ProseTicketType.GOV_VISIBILITY_LEAK) is False


# =============================================================================
# Ticket Transitions Tests
# =============================================================================


class TestTicketTransitions:
    def test_open_to_acknowledged(self):
        assert is_valid_transition(TicketStatus.OPEN, TicketStatus.ACKNOWLEDGED, "human")
        # Auto cannot acknowledge
        assert not is_valid_transition(TicketStatus.OPEN, TicketStatus.ACKNOWLEDGED, "auto")

    def test_open_to_fixed(self):
        assert is_valid_transition(TicketStatus.OPEN, TicketStatus.FIXED, "auto")
        assert is_valid_transition(TicketStatus.OPEN, TicketStatus.FIXED, "human")

    def test_open_to_duplicate(self):
        assert is_valid_transition(TicketStatus.OPEN, TicketStatus.DUPLICATE, "auto")

    def test_acknowledged_to_fixed(self):
        assert is_valid_transition(TicketStatus.ACKNOWLEDGED, TicketStatus.FIXED, "auto")

    def test_acknowledged_to_wont_fix(self):
        assert is_valid_transition(TicketStatus.ACKNOWLEDGED, TicketStatus.WONT_FIX, "human")
        # Auto cannot wont_fix
        assert not is_valid_transition(TicketStatus.ACKNOWLEDGED, TicketStatus.WONT_FIX, "auto")

    def test_invalid_transition(self):
        assert not is_valid_transition(TicketStatus.FIXED, TicketStatus.OPEN, "auto")
        assert not is_valid_transition(TicketStatus.WONT_FIX, TicketStatus.FIXED, "human")


# =============================================================================
# Similarity Matching Tests
# =============================================================================


class TestTokenize:
    def test_basic(self):
        tokens = tokenize("Hello World")
        assert "hello" in tokens
        assert "world" in tokens

    def test_special_chars(self):
        tokens = tokenize("foo_bar-baz.qux")
        # \w+ includes underscores, so foo_bar is one token
        assert "foo_bar" in tokens
        assert "baz" in tokens
        assert "qux" in tokens


class TestJaccardSimilarity:
    def test_identical(self):
        assert jaccard_similarity({"a", "b"}, {"a", "b"}) == 1.0

    def test_disjoint(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial(self):
        # {a, b} ∩ {a, c} = {a}, |{a}| = 1
        # {a, b} ∪ {a, c} = {a, b, c}, |{a, b, c}| = 3
        assert jaccard_similarity({"a", "b"}, {"a", "c"}) == pytest.approx(1/3)

    def test_empty(self):
        assert jaccard_similarity(set(), set()) == 1.0
        assert jaccard_similarity({"a"}, set()) == 0.0


class TestCalculateSimilarity:
    def test_same_type_and_invariant(self):
        detection = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="no governance leak",
            context="I cannot help with that",
        )
        ticket = Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="no governance leak",
            description="test",
            context_slice="I cannot assist with that",
        )
        result = calculate_similarity(detection, ticket)
        assert result.same_type is True
        assert result.same_invariant is True
        assert result.similarity >= 0.7

    def test_different_type(self):
        detection = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="test",
            context="test",
        )
        ticket = Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.REGIME_COLLISION,
            regime="comedy",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="other",
            description="test",
            context_slice="different",
        )
        result = calculate_similarity(detection, ticket)
        assert result.same_type is False
        assert result.similarity < 0.5


class TestFindSimilarTickets:
    def test_finds_similar(self):
        detection = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="no governance leak",
            context="test context",
        )
        history = [
            Ticket(
                id="TKT-1",
                created_at=1000.0,
                updated_at=1000.0,
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                severity=TicketSeverity.WARNING,
                violated_invariant="no governance leak",
                description="test",
                context_slice="test context",
            ),
        ]
        similar = find_similar_tickets(detection, history, threshold=0.7)
        assert len(similar) == 1

    def test_excludes_fixed(self):
        detection = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="no governance leak",
            context="test context",
        )
        history = [
            Ticket(
                id="TKT-1",
                created_at=1000.0,
                updated_at=1000.0,
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                severity=TicketSeverity.WARNING,
                violated_invariant="no governance leak",
                description="test",
                context_slice="test context",
                status=TicketStatus.FIXED,
            ),
        ]
        similar = find_similar_tickets(detection, history, threshold=0.7)
        assert len(similar) == 0


# =============================================================================
# TicketStore Tests
# =============================================================================


class TestTicketStore:
    def test_add_and_get(self):
        store = TicketStore()
        ticket = Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        )
        store.add(ticket)
        retrieved = store.get("TKT-1")
        assert retrieved is not None
        assert retrieved.id == "TKT-1"

    def test_all(self):
        store = TicketStore()
        store.add(Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        ))
        store.add(Ticket(
            id="TKT-2",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.REGIME_COLLISION,
            regime="comedy",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        ))
        assert len(store.all()) == 2

    def test_open_tickets(self):
        store = TicketStore()
        store.add(Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
            status=TicketStatus.OPEN,
        ))
        store.add(Ticket(
            id="TKT-2",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.REGIME_COLLISION,
            regime="comedy",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
            status=TicketStatus.FIXED,
        ))
        assert len(store.open_tickets()) == 1

    def test_by_type(self):
        store = TicketStore()
        store.add(Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        ))
        store.add(Ticket(
            id="TKT-2",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.REGIME_COLLISION,
            regime="comedy",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        ))
        by_type = store.by_type(ProseTicketType.GOV_VISIBILITY_LEAK)
        assert len(by_type) == 1

    def test_count_recurrences(self):
        store = TicketStore()
        store.add(Ticket(
            id="TKT-1",
            created_at=1000.0,
            updated_at=1000.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
        ))
        store.add(Ticket(
            id="TKT-2",
            created_at=1001.0,
            updated_at=1001.0,
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            severity=TicketSeverity.WARNING,
            violated_invariant="test",
            description="test",
            context_slice="test",
            parent_ticket="TKT-1",
        ))
        ticket1 = store.get("TKT-1")
        assert store.count_recurrences(ticket1) == 1


# =============================================================================
# TicketingLayer Tests
# =============================================================================


class TestTicketingLayerDisabled:
    def test_process_returns_no_ticket(self):
        layer = TicketingLayer()  # disabled by default
        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        assert output.ticket_created is False


class TestTicketingLayerEnabled:
    def test_process_creates_ticket(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)
        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test context",
                severity=0.5,
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        assert output.ticket_created is True
        assert output.ticket is not None
        assert output.ticket.type == ProseTicketType.GOV_VISIBILITY_LEAK

    def test_process_with_no_violation(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)
        input = TicketingLayerInput(
            violation=None,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        assert output.ticket_created is False

    def test_process_detects_recurrence(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # First violation
        input1 = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="no governance leak",
                context="same context",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        layer.process(input1)

        # Second similar violation
        input2 = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="no governance leak",
                context="same context",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output2 = layer.process(input2)
        assert output2.recurrence_detected is True
        assert len(output2.similar_tickets) > 0


class TestTicketingLayerAttemptCorrection:
    def test_correction_with_ticket(self):
        config = TicketingConfig(enabled=True, require_ticket_for_fix=True)
        layer = TicketingLayer(config)

        violation = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="test",
            context="test",
        )
        result = layer.attempt_correction(violation)
        assert result.corrected is True
        assert result.ticket is not None

    def test_correction_without_ticket_when_disabled(self):
        config = TicketingConfig(enabled=False)
        layer = TicketingLayer(config)

        violation = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="test",
            context="test",
        )
        result = layer.attempt_correction(violation)
        assert result.corrected is True
        assert result.ticket is None


class TestTicketingLayerManualTicket:
    def test_create_manual_ticket(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        ticket = layer.create_manual_ticket(
            ticket_type=ProseTicketType.TYPE_ERROR,
            description="User reported type error",
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            tags=["user_report"],
        )
        assert ticket is not None
        assert ticket.source == "manual"
        assert ticket.severity == TicketSeverity.WARNING

    def test_create_manual_ticket_disabled(self):
        config = TicketingConfig(enabled=False)
        layer = TicketingLayer(config)

        ticket = layer.create_manual_ticket(
            ticket_type=ProseTicketType.TYPE_ERROR,
            description="test",
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        assert ticket is None


class TestTicketingLayerStatusTransitions:
    def test_acknowledge(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        ticket_id = output.ticket.id

        result = layer.acknowledge(ticket_id)
        assert result is True
        ticket = layer.get_ticket(ticket_id)
        assert ticket.status == TicketStatus.ACKNOWLEDGED

    def test_fix(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        ticket_id = output.ticket.id

        result = layer.fix(ticket_id, "Fixed by removing governance markers")
        assert result is True
        ticket = layer.get_ticket(ticket_id)
        assert ticket.status == TicketStatus.FIXED
        assert ticket.closed_at is not None

    def test_wont_fix(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        ticket_id = output.ticket.id

        # Must acknowledge first
        layer.acknowledge(ticket_id)
        result = layer.wont_fix(ticket_id, "Intentional behavior")
        assert result is True

    def test_mark_duplicate(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # Create two tickets
        input1 = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output1 = layer.process(input1)

        input2 = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test2",
                context="test2",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output2 = layer.process(input2)

        result = layer.mark_duplicate(output2.ticket.id, output1.ticket.id)
        assert result is True


class TestTicketingLayerRouting:
    def test_critical_escalates(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
                severity=0.9,  # Critical
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        assert output.routing.action == RoutingActionType.ESCALATE

    def test_auto_fix_adjusts(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
                severity=0.3,  # Not critical
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        assert output.routing.action == RoutingActionType.ADJUST

    def test_scope_violation_suppresses(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=CodeTicketType.SCOPE_VIOLATION,
                regime="code",
                domain=TicketDomain.CODE,
                invariant="test",
                context="test",
                severity=0.3,
            ),
            regime="code",
            domain=TicketDomain.CODE,
        )
        output = layer.process(input)
        assert output.routing.action == RoutingActionType.SUPPRESS


# =============================================================================
# Learning Signals Tests
# =============================================================================


class TestLearningSignal:
    def test_to_dict(self):
        signal = LearningSignal(
            ticket_type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            resolution="Removed markers",
            recurrence_count=2,
            time_to_fix=3600.0,
            effective=True,
        )
        d = signal.to_dict()
        assert d["ticket_type"] == "GOV_VISIBILITY_LEAK"
        assert d["effective"] is True


class TestExtractLearningSignals:
    def test_extracts_from_fixed_tickets(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # Create and fix a ticket
        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="test",
                context="test",
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )
        output = layer.process(input)
        layer.fix(output.ticket.id, "fixed")

        signals = extract_learning_signals(layer)
        assert len(signals) == 1
        assert signals[0].ticket_type == ProseTicketType.GOV_VISIBILITY_LEAK


# =============================================================================
# Metrics Tests
# =============================================================================


class TestTicketingMetrics:
    def test_to_dict(self):
        metrics = TicketingMetrics(
            tickets_created=10,
            tickets_fixed=5,
            tickets_open=3,
            recurrence_rate=0.2,
            mean_time_to_fix=1800.0,
            escalation_rate=0.1,
            top_violation_types=[("GOV_VISIBILITY_LEAK", 4)],
        )
        d = metrics.to_dict()
        assert d["tickets_created"] == 10


class TestComputeMetrics:
    def test_empty_layer(self):
        layer = TicketingLayer(TicketingConfig(enabled=True))
        metrics = compute_metrics(layer)
        assert metrics.tickets_created == 0

    def test_with_tickets(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # Create tickets
        for i in range(3):
            input = TicketingLayerInput(
                violation=ViolationDetection(
                    type=ProseTicketType.GOV_VISIBILITY_LEAK,
                    regime="nonfiction",
                    domain=TicketDomain.PROSE,
                    invariant="test",
                    context="test",
                ),
                regime="nonfiction",
                domain=TicketDomain.PROSE,
            )
            output = layer.process(input)
            if i == 0:
                layer.fix(output.ticket.id, "fixed")

        metrics = compute_metrics(layer)
        assert metrics.tickets_created == 3
        assert metrics.tickets_fixed == 1
        assert metrics.tickets_open == 2


# =============================================================================
# Integration Tests
# =============================================================================


class TestCreateTicketingLayer:
    def test_factory(self):
        layer = create_ticketing_layer(
            enabled=True,
            require_ticket_for_fix=False,
            retention_policy="persistent",
        )
        assert layer.config.enabled is True
        assert layer.config.require_ticket_for_fix is False


class TestDefaultTicketingLayer:
    def test_exists(self):
        assert DEFAULT_TICKETING_LAYER is not None
        assert DEFAULT_TICKETING_LAYER.config.enabled is False


class TestTicketingIntegration:
    def test_full_lifecycle(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # 1. Violation detected
        input = TicketingLayerInput(
            violation=ViolationDetection(
                type=ProseTicketType.GOV_VISIBILITY_LEAK,
                regime="nonfiction",
                domain=TicketDomain.PROSE,
                invariant="governance must not leak",
                context="I'm sorry, but I cannot help with that.",
                severity=0.6,
            ),
            regime="nonfiction",
            domain=TicketDomain.PROSE,
        )

        # 2. Process creates ticket
        output = layer.process(input)
        assert output.ticket_created is True
        ticket_id = output.ticket.id

        # 3. Human acknowledges
        layer.acknowledge(ticket_id)
        ticket = layer.get_ticket(ticket_id)
        assert ticket.status == TicketStatus.ACKNOWLEDGED

        # 4. System fixes
        layer.fix(ticket_id, "Removed apology and governance markers")
        ticket = layer.get_ticket(ticket_id)
        assert ticket.status == TicketStatus.FIXED

        # 5. Learning signals extracted
        signals = extract_learning_signals(layer)
        assert len(signals) == 1
        assert signals[0].resolution == "Removed apology and governance markers"

    def test_recurrence_tracking(self):
        config = TicketingConfig(enabled=True)
        layer = TicketingLayer(config)

        # Create multiple similar violations
        for i in range(4):
            input = TicketingLayerInput(
                violation=ViolationDetection(
                    type=ProseTicketType.GOV_VISIBILITY_LEAK,
                    regime="nonfiction",
                    domain=TicketDomain.PROSE,
                    invariant="governance must not leak",
                    context="I'm sorry, but I cannot help.",
                ),
                regime="nonfiction",
                domain=TicketDomain.PROSE,
            )
            layer.process(input)

        # Check recurrence count
        tickets = layer.get_all_tickets()
        first_ticket = tickets[0]
        recurrences = layer.count_recurrences(first_ticket.id)
        # First ticket is parent, others are recurrences
        assert recurrences >= 2

    def test_no_correction_without_ticket(self):
        """The key invariant: no correction without a ticket."""
        config = TicketingConfig(enabled=True, require_ticket_for_fix=True)
        layer = TicketingLayer(config)

        violation = ViolationDetection(
            type=ProseTicketType.GOV_VISIBILITY_LEAK,
            regime="nonfiction",
            domain=TicketDomain.PROSE,
            invariant="test",
            context="test",
        )

        # Correction creates ticket
        result = layer.attempt_correction(violation)
        assert result.corrected is True
        assert result.ticket is not None
        assert "correction_with_ticket" in result.reason
