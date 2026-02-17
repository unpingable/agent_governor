# SPDX-License-Identifier: Apache-2.0
"""
Tests for Slim Mode — single-developer governance.

Tests the SlimMode facade, contradiction detection, anchor management,
structure locking, invariant registration, status views, and helpers.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import pytest

from governor.slim_mode import (
    SlimMode,
    SlimStatus,
    ContradictionError,
    create_slim_mode,
    _infer_topic,
    _make_anchor_id,
    _make_spine_id,
    _make_invariant_id,
    _extract_patterns,
)
from governor.envelopes import EnvelopeMode, EnvelopeConfig
from governor.continuity import AnchorType, Severity as AnchorSeverity, Anchor
from governor.invariant_store import InvariantSpec
from governor.spine import Spine


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def gov_dir(tmp_path):
    """Create a minimal governor directory structure."""
    gd = tmp_path / ".governor"
    gd.mkdir()
    # DecisionLedger needs decisions/index.json
    (gd / "decisions").mkdir()
    (gd / "decisions" / "index.json").write_text("[]")
    # FactLedger needs facts/ (DecisionLedger is separate but init checks)
    (gd / "facts").mkdir()
    (gd / "facts" / "index.json").write_text("[]")
    (gd / "facts" / "receipts").mkdir()
    return gd


@pytest.fixture
def slim(gov_dir):
    """Create a SlimMode instance."""
    return SlimMode(gov_dir)


# =============================================================================
# Envelope Tests
# =============================================================================


class TestEnvelopeMode:
    def test_slim_mode_exists(self):
        assert EnvelopeMode.SLIM.value == "slim"

    def test_slim_config(self):
        config = EnvelopeConfig.slim()
        assert config.mode == EnvelopeMode.SLIM
        assert config.require_receipts is False
        assert config.commit_decisions is True
        assert config.allow_conflicts is False

    def test_slim_in_all_modes(self):
        modes = [m.value for m in EnvelopeMode]
        assert "slim" in modes


# =============================================================================
# Decision Tests
# =============================================================================


class TestDecide:
    def test_basic_decision(self, slim):
        d = slim.decide("Authentication uses JWT")
        assert d.choice == "Authentication uses JWT"

    def test_decision_with_topic(self, slim):
        d = slim.decide("React", topic="framework")
        assert d.topic == "framework"
        assert d.choice == "React"

    def test_decision_inferred_topic(self, slim):
        d = slim.decide("Authentication uses JWT")
        assert d.topic == "authentication"

    def test_contradiction_detection(self, slim):
        slim.decide("React", topic="framework")
        with pytest.raises(ContradictionError) as exc_info:
            slim.decide("Vue", topic="framework")
        assert "framework" in str(exc_info.value)
        assert "React" in str(exc_info.value)

    def test_contradiction_force(self, slim):
        slim.decide("React", topic="framework")
        d = slim.decide("Vue", topic="framework", force=True)
        assert d.choice == "Vue"

    def test_retract(self, slim):
        slim.decide("JWT auth", topic="auth")
        result = slim.retract("JWT auth", topic="auth")
        assert result is not None
        assert "[RETRACTED]" in result.choice

    def test_retract_not_found(self, slim):
        result = slim.retract("nonexistent", topic="nothing")
        assert result is None

    def test_retract_then_decide(self, slim):
        slim.decide("React", topic="framework")
        slim.retract("React", topic="framework")
        # After retraction, should be able to decide on same topic
        d = slim.decide("Vue", topic="framework")
        assert d.choice == "Vue"

    def test_list_decisions(self, slim):
        slim.decide("JWT", topic="auth")
        slim.decide("React", topic="framework")
        decisions = slim.list_decisions()
        assert len(decisions) == 2

    def test_list_decisions_excludes_superseded(self, slim):
        slim.decide("JWT", topic="auth")
        slim.retract("JWT", topic="auth")
        decisions = slim.list_decisions()
        # Only the retraction is active
        active_choices = [d.choice for d in decisions]
        assert any("[RETRACTED]" in c for c in active_choices)

    def test_decision_no_topic_no_inference(self, slim):
        d = slim.decide("Something random")
        # Should succeed even without topic inference
        assert d.choice == "Something random"

    def test_multiple_different_topics(self, slim):
        slim.decide("JWT", topic="auth")
        slim.decide("React", topic="framework")
        slim.decide("PostgreSQL", topic="database")
        assert len(slim.list_decisions()) == 3

    def test_retract_by_text_match(self, slim):
        slim.decide("JWT auth", topic="auth")
        result = slim.retract("JWT auth")
        assert result is not None


class TestContradictionError:
    def test_error_message(self, slim):
        slim.decide("React", topic="framework")
        try:
            slim.decide("Vue", topic="framework")
        except ContradictionError as e:
            assert e.topic == "framework"
            assert e.new_text == "Vue"
            assert e.existing.choice == "React"


# =============================================================================
# Anchor Tests
# =============================================================================


class TestAnchor:
    def test_add_anchor(self, slim):
        a = slim.add_anchor("Elena has green eyes", "canon", "reject")
        assert a.description == "Elena has green eyes"
        assert a.anchor_type == AnchorType.CANON
        assert a.severity == AnchorSeverity.REJECT

    def test_add_prohibition(self, slim):
        a = slim.add_anchor("No eval() calls", "prohibition", "reject")
        assert a.anchor_type == AnchorType.PROHIBITION
        assert a.forbidden_patterns  # Should have extracted patterns

    def test_add_requirement(self, slim):
        a = slim.add_anchor("Must include copyright header", "requirement", "warn")
        assert a.anchor_type == AnchorType.REQUIREMENT
        assert a.required_patterns

    def test_remove_anchor(self, slim):
        a = slim.add_anchor("Test anchor", "canon", "reject")
        removed = slim.remove_anchor(a.id)
        assert removed is not None
        assert removed.id == a.id
        assert len(slim.list_anchors()) == 0

    def test_remove_nonexistent(self, slim):
        assert slim.remove_anchor("nonexistent") is None

    def test_list_anchors(self, slim):
        slim.add_anchor("Anchor 1", "canon", "reject")
        slim.add_anchor("Anchor 2", "prohibition", "warn")
        assert len(slim.list_anchors()) == 2

    def test_anchor_persistence(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.add_anchor("Persistent anchor", "canon", "reject")

        slim2 = SlimMode(gov_dir)
        anchors = slim2.list_anchors()
        assert len(anchors) == 1
        assert anchors[0].description == "Persistent anchor"

    def test_custom_id(self, slim):
        a = slim.add_anchor("Test", "canon", "reject", anchor_id="my-custom-id")
        assert a.id == "my-custom-id"

    def test_anchor_with_scope(self, slim):
        a = slim.add_anchor("No eval()", "prohibition", "reject", scope="src/**")
        assert a.description == "No eval()"

    def test_all_anchor_types(self, slim):
        for atype in ["canon", "prohibition", "requirement", "definition", "style", "persona"]:
            a = slim.add_anchor(f"Test {atype}", atype, "warn")
            assert a.anchor_type == AnchorType(atype)


# =============================================================================
# Lock/Unlock Tests
# =============================================================================


class TestLockUnlock:
    def test_lock(self, slim):
        spine = slim.lock("src/governor/")
        assert spine.id.startswith("lock-")
        assert "src/governor/" in spine.structure.get("directories", {})

    def test_unlock(self, slim):
        slim.lock("src/governor/")
        assert slim.unlock("src/governor/")

    def test_unlock_nonexistent(self, slim):
        assert not slim.unlock("nonexistent/")

    def test_lock_with_forbidden(self, slim):
        spine = slim.lock("src/", forbidden_patterns=["*.secret", "credentials/*"])
        assert "*.secret" in spine.structure.get("forbidden_paths", [])

    def test_list_locks(self, slim):
        slim.lock("src/")
        slim.lock("tests/")
        locks = slim.list_locks()
        assert len(locks) >= 2

    def test_lock_persistence(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.lock("src/governor/")

        slim2 = SlimMode(gov_dir)
        locks = slim2.list_locks()
        assert any("src/governor/" in str(s.structure) for s in locks)

    def test_lock_with_description(self, slim):
        spine = slim.lock("lib/", description="Core library locked")
        assert spine.description == "Core library locked"


# =============================================================================
# Invariant Tests (must-pass, must-exist)
# =============================================================================


class TestMustPass:
    def test_must_pass(self, slim):
        spec = slim.must_pass("python3 -m pytest tests/ -x")
        assert spec.kind == "test"
        assert spec.params["command"] == "python3 -m pytest tests/ -x"
        assert spec.on_violation == "block"

    def test_must_pass_custom_id(self, slim):
        spec = slim.must_pass("pytest", spec_id="my-test")
        assert spec.id == "my-test"

    def test_must_pass_auto_id(self, slim):
        spec = slim.must_pass("python3 -m pytest tests/ -x")
        assert spec.id.startswith("test-")

    def test_must_pass_persistence(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.must_pass("pytest tests/")

        slim2 = SlimMode(gov_dir)
        invariants = slim2.list_invariants()
        assert any(i.kind == "test" for i in invariants)


class TestMustExist:
    def test_must_exist(self, slim):
        spec = slim.must_exist("src/governor/__init__.py")
        assert spec.kind == "file-exists"
        assert spec.params["path"] == "src/governor/__init__.py"

    def test_must_exist_custom_id(self, slim):
        spec = slim.must_exist("README.md", spec_id="readme-check")
        assert spec.id == "readme-check"

    def test_must_exist_auto_id(self, slim):
        spec = slim.must_exist("src/governor/__init__.py")
        assert spec.id.startswith("file-exists-")


class TestRemoveInvariant:
    def test_remove(self, slim):
        spec = slim.must_pass("pytest", spec_id="test-1")
        assert slim.remove_invariant("test-1")
        assert len(slim.list_invariants()) == 0

    def test_remove_nonexistent(self, slim):
        assert not slim.remove_invariant("nonexistent")

    def test_list_invariants(self, slim):
        slim.must_pass("pytest tests/")
        slim.must_exist("setup.py")
        assert len(slim.list_invariants()) == 2


# =============================================================================
# Status Tests
# =============================================================================


class TestSlimStatus:
    def test_empty_status(self, slim):
        status = slim.status()
        assert status.envelope == "slim"
        assert status.decisions == []
        assert status.anchors == []
        assert status.invariants == []
        assert status.spine_locked == []

    def test_status_with_decisions(self, slim):
        slim.decide("JWT", topic="auth")
        status = slim.status()
        assert len(status.decisions) == 1
        assert status.decisions[0]["choice"] == "JWT"
        assert status.decisions[0]["topic"] == "auth"

    def test_status_with_anchors(self, slim):
        slim.add_anchor("No eval()", "prohibition", "reject")
        status = slim.status()
        assert len(status.anchors) == 1
        assert status.anchors[0]["severity"] == "reject"

    def test_status_with_invariants(self, slim):
        slim.must_pass("pytest")
        status = slim.status()
        assert len(status.invariants) == 1
        assert status.invariants[0]["kind"] == "test"

    def test_status_with_locks(self, slim):
        slim.lock("src/")
        status = slim.status()
        assert "src/" in status.spine_locked

    def test_status_to_dict(self, slim):
        slim.decide("JWT", topic="auth")
        status = slim.status()
        d = status.to_dict()
        assert d["envelope"] == "slim"
        assert len(d["decisions"]) == 1

    def test_status_to_oneliner(self, slim):
        slim.decide("JWT", topic="auth")
        slim.add_anchor("No eval()", "prohibition", "reject")
        slim.must_pass("pytest")
        status = slim.status()
        oneliner = status.to_oneliner()
        assert "DECISIONS" in oneliner
        assert "ANCHORS" in oneliner
        assert "INVARIANTS" in oneliner

    def test_status_to_oneliner_empty(self, slim):
        status = slim.status()
        assert status.to_oneliner() == "No constraints active."

    def test_status_from_dict(self):
        d = {
            "envelope": "slim",
            "decisions": [{"topic": "auth", "choice": "JWT"}],
            "anchors": [],
            "invariants": [],
            "spine_locked": [],
        }
        status = SlimStatus.from_dict(d)
        assert status.envelope == "slim"
        assert len(status.decisions) == 1

    def test_record_check(self, slim):
        slim.record_check()
        status = slim.status()
        assert status.last_check != ""

    def test_full_status(self, slim):
        slim.decide("JWT", topic="auth")
        slim.decide("React", topic="framework")
        slim.add_anchor("Elena green eyes", "canon", "reject")
        slim.add_anchor("No eval()", "prohibition", "reject")
        slim.must_pass("pytest tests/")
        slim.must_exist("setup.py")
        slim.lock("src/")
        slim.record_check()

        status = slim.status()
        assert len(status.decisions) == 2
        assert len(status.anchors) == 2
        assert len(status.invariants) == 2
        assert len(status.spine_locked) >= 1
        assert status.last_check != ""


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestInferTopic:
    def test_uses_pattern(self):
        assert _infer_topic("Authentication uses JWT") == "authentication"

    def test_use_for_pattern(self):
        assert _infer_topic("Use React for frontend") == "frontend"

    def test_no_pattern(self):
        assert _infer_topic("No ORM") == "orm"

    def test_no_pattern_with_dash(self):
        assert _infer_topic("No ORM — raw SQL") == "orm"

    def test_no_inference(self):
        assert _infer_topic("Something random") == ""

    def test_with_via(self):
        assert _infer_topic("Deployment via Docker") == "deployment"

    def test_empty_string(self):
        assert _infer_topic("") == ""


class TestMakeAnchorId:
    def test_basic(self):
        aid = _make_anchor_id("Elena has green eyes")
        assert aid == "elena-has-green-eyes"

    def test_special_chars(self):
        aid = _make_anchor_id("No eval() calls!")
        assert "eval" in aid
        assert "(" not in aid

    def test_long_description(self):
        aid = _make_anchor_id("A" * 100)
        assert len(aid) <= 40

    def test_empty(self):
        aid = _make_anchor_id("")
        assert len(aid) > 0  # Should fallback to UUID


class TestMakeSpineId:
    def test_basic(self):
        sid = _make_spine_id("src/governor/")
        assert sid.startswith("lock-")
        assert "governor" in sid

    def test_strips_slash(self):
        sid = _make_spine_id("/src/")
        assert "lock-" in sid


class TestMakeInvariantId:
    def test_test_kind(self):
        iid = _make_invariant_id("test", "pytest tests/")
        assert iid.startswith("test-")
        assert "pytest" in iid

    def test_file_exists_kind(self):
        iid = _make_invariant_id("file-exists", "setup.py")
        assert iid.startswith("file-exists-")


class TestExtractPatterns:
    def test_quoted_strings(self):
        patterns = _extract_patterns('Must contain "hello world"')
        assert "hello world" in patterns

    def test_no_prefix(self):
        patterns = _extract_patterns("No eval() calls")
        assert any("eval()" in p for p in patterns)

    def test_plain_description(self):
        patterns = _extract_patterns("Elena has green eyes")
        assert "Elena has green eyes" in patterns


# =============================================================================
# Integration Tests
# =============================================================================


class TestIntegration:
    def test_full_lifecycle(self, slim):
        """Test a complete slim-mode workflow."""
        # Record decisions
        slim.decide("JWT", topic="auth")
        slim.decide("React", topic="framework")

        # Create anchors
        slim.add_anchor("Elena has green eyes", "canon", "reject")

        # Lock structure
        slim.lock("src/")

        # Add invariants
        slim.must_pass("pytest tests/")
        slim.must_exist("setup.py")

        # Check status
        status = slim.status()
        assert len(status.decisions) == 2
        assert len(status.anchors) == 1
        assert len(status.invariants) == 2
        assert len(status.spine_locked) >= 1

        # Retract a decision
        slim.retract("JWT", topic="auth")
        assert len(slim.list_decisions()) == 2  # retraction + framework

        # Remove an anchor
        slim.remove_anchor("elena-has-green-eyes")
        assert len(slim.list_anchors()) == 0

        # Unlock
        slim.unlock("src/")

    def test_upgrade_safe(self, gov_dir):
        """State created in slim mode should be readable by strict-mode subsystems."""
        from governor.ledgers import DecisionLedger
        from governor.continuity import AnchorRegistry

        slim = SlimMode(gov_dir)
        slim.decide("JWT", topic="auth")
        slim.add_anchor("Test anchor", "canon", "reject")

        # Strict-mode subsystems can read slim state
        ledger = DecisionLedger(gov_dir)
        decisions = ledger.query()
        assert len(decisions) == 1

        path = gov_dir / "continuity" / "anchors.json"
        registry = AnchorRegistry.load(path)
        assert len(registry.all()) == 1

    def test_create_slim_mode(self, gov_dir):
        slim = create_slim_mode(gov_dir)
        assert isinstance(slim, SlimMode)

    def test_oneliner_with_all_fields(self, slim):
        slim.decide("JWT", topic="auth")
        slim.add_anchor("No eval()", "prohibition", "reject")
        slim.must_pass("pytest")
        slim.lock("src/")

        status = slim.status()
        oneliner = status.to_oneliner()
        assert "DECISIONS" in oneliner
        assert "ANCHORS" in oneliner
        assert "INVARIANTS" in oneliner
        assert "SPINE" in oneliner


# =============================================================================
# Persistence Tests
# =============================================================================


class TestPersistence:
    def test_decisions_persist(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.decide("JWT", topic="auth")

        slim2 = SlimMode(gov_dir)
        assert len(slim2.list_decisions()) == 1

    def test_anchors_persist(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.add_anchor("Test", "canon", "reject")

        slim2 = SlimMode(gov_dir)
        assert len(slim2.list_anchors()) == 1

    def test_invariants_persist(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.must_pass("pytest")

        slim2 = SlimMode(gov_dir)
        assert len(slim2.list_invariants()) == 1

    def test_locks_persist(self, gov_dir):
        slim1 = SlimMode(gov_dir)
        slim1.lock("src/")

        slim2 = SlimMode(gov_dir)
        assert len(slim2.list_locks()) >= 1
