# SPDX-License-Identifier: Apache-2.0
"""Tests for the Constraint Compiler (AG2 Layer 1, Item #3)."""

import json
import hashlib
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import uuid4

import pytest

from governor.constraint_compiler import (
    ConstraintKind,
    ConstraintSeverity,
    ScarClass,
    OutputFormat,
    ResolvedConstraint,
    ConstraintSource,
    OverrideWarrant,
    QuorumUnsatisfiedReceipt,
    ConstraintBlock,
    CacheEntry,
    ConstraintCache,
    ConstraintDiff,
    classify_scar,
    required_quorum,
    check_warrant_quorum,
    make_constraint_id,
    compute_priority,
    render_prompt_prefix,
    compile_constraints,
    diff_constraints,
    clear_cache,
    get_cache,
    _scope_matches,
    _content_hash,
    _hash_items,
    _compute_cache_key,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def gov_dir(tmp_path):
    """Create a minimal .governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    (d / "decisions").mkdir()
    return d


@pytest.fixture
def project_dir(gov_dir):
    """Return the project root (parent of .governor)."""
    return gov_dir.parent


@pytest.fixture(autouse=True)
def clear_compiler_cache():
    """Clear the compiler cache before each test."""
    clear_cache()
    yield
    clear_cache()


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------


class TestConstraintKind:
    def test_values(self):
        assert ConstraintKind.ANCHOR.value == "anchor"
        assert ConstraintKind.INVARIANT.value == "invariant"
        assert ConstraintKind.SCAR.value == "scar"
        assert ConstraintKind.DECISION.value == "decision"
        assert ConstraintKind.SPINE_RULE.value == "spine_rule"
        assert ConstraintKind.SECURITY_PATTERN.value == "security_pattern"
        assert ConstraintKind.ENVELOPE.value == "envelope"
        assert ConstraintKind.PROFILE.value == "profile"
        assert ConstraintKind.OVERRIDE.value == "override"

    def test_count(self):
        assert len(ConstraintKind) == 9


class TestConstraintSeverity:
    def test_values(self):
        assert ConstraintSeverity.REJECT.value == "reject"
        assert ConstraintSeverity.WARN.value == "warn"
        assert ConstraintSeverity.INFO.value == "info"


class TestScarClass:
    def test_values(self):
        assert ScarClass.HARD.value == "hard"
        assert ScarClass.SOFT.value == "soft"
        assert ScarClass.PROCEDURAL.value == "procedural"


class TestOutputFormat:
    def test_values(self):
        assert OutputFormat.PROMPT.value == "prompt"
        assert OutputFormat.JSON.value == "json"
        assert OutputFormat.SUMMARY.value == "summary"


# ---------------------------------------------------------------------------
# Scar Classification
# ---------------------------------------------------------------------------


class TestClassifyScar:
    def test_hard(self):
        assert classify_scar(1.0) == ScarClass.HARD
        assert classify_scar(0.95) == ScarClass.HARD
        assert classify_scar(0.99) == ScarClass.HARD

    def test_soft(self):
        assert classify_scar(0.94) == ScarClass.SOFT
        assert classify_scar(0.5) == ScarClass.SOFT
        assert classify_scar(0.3) == ScarClass.SOFT

    def test_procedural(self):
        assert classify_scar(0.29) == ScarClass.PROCEDURAL
        assert classify_scar(0.1) == ScarClass.PROCEDURAL
        assert classify_scar(0.05) == ScarClass.PROCEDURAL


# ---------------------------------------------------------------------------
# Quorum Policy
# ---------------------------------------------------------------------------


class TestRequiredQuorum:
    def test_hard_never_overridable(self):
        assert required_quorum(ScarClass.HARD) == -1
        assert required_quorum(ScarClass.HARD, "production", "strict") == -1

    def test_soft_one_signer(self):
        assert required_quorum(ScarClass.SOFT) == 1
        assert required_quorum(ScarClass.SOFT, "production", "strict") == 1

    def test_procedural_default_one_signer(self):
        assert required_quorum(ScarClass.PROCEDURAL) == 1
        assert required_quorum(ScarClass.PROCEDURAL, "greenfield", "strict") == 1

    def test_procedural_production_strict_two_signers(self):
        assert required_quorum(ScarClass.PROCEDURAL, "production", "strict") == 2


class TestCheckWarrantQuorum:
    def test_hard_scar_always_fails(self):
        warrant = OverrideWarrant(
            warrant_id="w1",
            invoked_by="admin",
            reason="test",
            scope=["src/**"],
            constraints_overruled=[],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            quorum_signers=["signer1", "signer2"],
        )
        result = check_warrant_quorum(warrant, ScarClass.HARD)
        assert result is not None
        assert "never overridable" in result.reason

    def test_soft_scar_passes_with_invoker(self):
        warrant = OverrideWarrant(
            warrant_id="w1",
            invoked_by="admin",
            reason="test",
            scope=["src/**"],
            constraints_overruled=[],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        result = check_warrant_quorum(warrant, ScarClass.SOFT)
        assert result is None

    def test_procedural_production_needs_two(self):
        warrant = OverrideWarrant(
            warrant_id="w1",
            invoked_by="admin",
            reason="test",
            scope=["src/**"],
            constraints_overruled=[],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            quorum_signers=None,  # Only invoker
        )
        result = check_warrant_quorum(warrant, ScarClass.PROCEDURAL, "production", "strict")
        assert result is not None
        assert "insufficient signers" in result.reason

    def test_procedural_production_passes_with_cosigner(self):
        warrant = OverrideWarrant(
            warrant_id="w1",
            invoked_by="admin",
            reason="test",
            scope=["src/**"],
            constraints_overruled=[],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            quorum_signers=["cosigner1"],
        )
        result = check_warrant_quorum(warrant, ScarClass.PROCEDURAL, "production", "strict")
        assert result is None


# ---------------------------------------------------------------------------
# Constraint ID
# ---------------------------------------------------------------------------


class TestMakeConstraintId:
    def test_deterministic(self):
        id1 = make_constraint_id("anchor", "continuity", "src/", "*.py", "test")
        id2 = make_constraint_id("anchor", "continuity", "src/", "*.py", "test")
        assert id1 == id2

    def test_different_inputs_different_ids(self):
        id1 = make_constraint_id("anchor", "continuity", "src/", "*.py", "test1")
        id2 = make_constraint_id("anchor", "continuity", "src/", "*.py", "test2")
        assert id1 != id2

    def test_format(self):
        cid = make_constraint_id("a", "b", "c", "d", "e")
        assert len(cid) == 16
        assert all(c in "0123456789abcdef" for c in cid)


# ---------------------------------------------------------------------------
# Scope Matching
# ---------------------------------------------------------------------------


class TestScopeMatches:
    def test_none_scope_matches_everything(self):
        assert _scope_matches(None, ["src/**"])
        assert _scope_matches("src/foo.py", None)
        assert _scope_matches(None, None)

    def test_empty_scope_matches(self):
        assert _scope_matches("", ["src/**"])
        assert _scope_matches("src/foo.py", [])

    def test_glob_match(self):
        assert _scope_matches("src/auth/login.py", ["src/auth/**"])

    def test_glob_no_match(self):
        assert not _scope_matches("tests/test_foo.py", ["src/auth/**"])

    def test_reverse_match(self):
        assert _scope_matches("src/**", ["src/auth/login.py"])

    def test_exact_match(self):
        assert _scope_matches("src/main.py", ["src/main.py"])


# ---------------------------------------------------------------------------
# Priority Computation
# ---------------------------------------------------------------------------


class TestComputePriority:
    def test_reject_higher_than_warn(self):
        p_reject = compute_priority(
            ConstraintKind.ANCHOR, ConstraintSeverity.REJECT, None, None
        )
        p_warn = compute_priority(
            ConstraintKind.ANCHOR, ConstraintSeverity.WARN, None, None
        )
        assert p_reject > p_warn

    def test_in_scope_boost(self):
        p_scoped = compute_priority(
            ConstraintKind.ANCHOR, ConstraintSeverity.REJECT, "src/auth/**", ["src/auth/**"]
        )
        p_unscoped = compute_priority(
            ConstraintKind.ANCHOR, ConstraintSeverity.REJECT, None, ["src/auth/**"]
        )
        assert p_scoped > p_unscoped

    def test_scar_adjacent_boost(self):
        p_adj = compute_priority(
            ConstraintKind.SCAR, ConstraintSeverity.WARN, None, None, is_scar_adjacent=True
        )
        p_not = compute_priority(
            ConstraintKind.SCAR, ConstraintSeverity.WARN, None, None, is_scar_adjacent=False
        )
        assert p_adj > p_not

    def test_decision_boost(self):
        p_dec = compute_priority(
            ConstraintKind.DECISION, ConstraintSeverity.REJECT, None, None
        )
        p_anc = compute_priority(
            ConstraintKind.ANCHOR, ConstraintSeverity.REJECT, None, None
        )
        assert p_dec > p_anc

    def test_capped_at_one(self):
        p = compute_priority(
            ConstraintKind.DECISION, ConstraintSeverity.REJECT, "src/a/b.py", ["src/**"],
            is_scar_adjacent=True,
        )
        assert p <= 1.0


# ---------------------------------------------------------------------------
# ResolvedConstraint
# ---------------------------------------------------------------------------


class TestResolvedConstraint:
    def test_roundtrip(self):
        c = ResolvedConstraint(
            constraint_id="abc123",
            kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT,
            description="No eval()",
            pattern="eval\\(",
            scope="src/**",
            source="anchors",
            projection_priority=0.85,
        )
        d = c.to_dict()
        c2 = ResolvedConstraint.from_dict(d)
        assert c2.constraint_id == c.constraint_id
        assert c2.kind == c.kind
        assert c2.severity == c.severity
        assert c2.description == c.description
        assert c2.pattern == c.pattern
        assert c2.scope == c.scope

    def test_optional_fields_omitted(self):
        c = ResolvedConstraint(
            constraint_id="x", kind=ConstraintKind.ENVELOPE,
            severity=ConstraintSeverity.INFO, description="test",
            source="envelope",
        )
        d = c.to_dict()
        assert "pattern" not in d
        assert "scope" not in d
        assert "overruled_by" not in d

    def test_overruled_included(self):
        c = ResolvedConstraint(
            constraint_id="x", kind=ConstraintKind.SCAR,
            severity=ConstraintSeverity.WARN, description="test",
            source="scars", overruled_by="w123",
        )
        d = c.to_dict()
        assert d["overruled_by"] == "w123"


# ---------------------------------------------------------------------------
# ConstraintSource
# ---------------------------------------------------------------------------


class TestConstraintSource:
    def test_roundtrip(self):
        s = ConstraintSource(subsystem="anchors", count=5, hash="abc123")
        d = s.to_dict()
        s2 = ConstraintSource.from_dict(d)
        assert s2.subsystem == s.subsystem
        assert s2.count == s.count
        assert s2.hash == s.hash


# ---------------------------------------------------------------------------
# OverrideWarrant
# ---------------------------------------------------------------------------


class TestOverrideWarrant:
    def test_roundtrip(self):
        w = OverrideWarrant(
            warrant_id="w1",
            invoked_by="admin",
            reason="hotfix",
            scope=["src/auth/**"],
            constraints_overruled=["c1", "c2"],
            expires_at=datetime(2025, 6, 1, 14, 0, tzinfo=timezone.utc),
        )
        d = w.to_dict()
        w2 = OverrideWarrant.from_dict(d)
        assert w2.warrant_id == w.warrant_id
        assert w2.invoked_by == w.invoked_by
        assert w2.constraints_overruled == w.constraints_overruled

    def test_is_expired(self):
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        w = OverrideWarrant(
            warrant_id="w1", invoked_by="a", reason="r",
            scope=[], constraints_overruled=[], expires_at=past,
        )
        assert w.is_expired

    def test_not_expired(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        w = OverrideWarrant(
            warrant_id="w1", invoked_by="a", reason="r",
            scope=[], constraints_overruled=[], expires_at=future,
        )
        assert not w.is_expired

    def test_remaining_seconds(self):
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        w = OverrideWarrant(
            warrant_id="w1", invoked_by="a", reason="r",
            scope=[], constraints_overruled=[], expires_at=future,
        )
        assert w.remaining_seconds > 3500
        assert w.remaining_seconds <= 3600


# ---------------------------------------------------------------------------
# QuorumUnsatisfiedReceipt
# ---------------------------------------------------------------------------


class TestQuorumUnsatisfiedReceipt:
    def test_roundtrip(self):
        r = QuorumUnsatisfiedReceipt(
            warrant_id="w1",
            required_signers=2,
            verified_signers=1,
            reason="insufficient",
            constraint_id="c1",
        )
        d = r.to_dict()
        r2 = QuorumUnsatisfiedReceipt.from_dict(d)
        assert r2.warrant_id == r.warrant_id
        assert r2.required_signers == r.required_signers


# ---------------------------------------------------------------------------
# ConstraintBlock
# ---------------------------------------------------------------------------


class TestConstraintBlock:
    def _make_block(self, constraints=None):
        constraints = constraints or []
        return ConstraintBlock(
            constraints=constraints,
            sources=[],
            content_hash="abc123",
            compiled_at=datetime.now(timezone.utc),
            envelope="strict",
        )

    def test_effective_constraints(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c2", kind=ConstraintKind.SCAR,
            severity=ConstraintSeverity.WARN, description="b", source="b",
            overruled_by="w1",
        )
        block = self._make_block([c1, c2])
        assert len(block.effective_constraints) == 1
        assert block.effective_constraints[0].constraint_id == "c1"

    def test_overruled_constraints(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c2", kind=ConstraintKind.SCAR,
            severity=ConstraintSeverity.WARN, description="b", source="b",
            overruled_by="w1",
        )
        block = self._make_block([c1, c2])
        assert len(block.overruled_constraints) == 1
        assert block.overruled_constraints[0].constraint_id == "c2"

    def test_hard_constraints(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c2", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.WARN, description="b", source="a",
        )
        block = self._make_block([c1, c2])
        assert len(block.hard_constraints) == 1

    def test_soft_constraints(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.WARN, description="a", source="a",
        )
        block = self._make_block([c])
        assert len(block.soft_constraints) == 1

    def test_security_constraints(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.SECURITY_PATTERN,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        block = self._make_block([c])
        assert len(block.security_constraints) == 1

    def test_roundtrip(self):
        block = self._make_block()
        d = block.to_dict()
        block2 = ConstraintBlock.from_dict(d)
        assert block2.content_hash == block.content_hash
        assert block2.envelope == block.envelope

    def test_to_summary(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        block = self._make_block([c])
        summary = block.to_summary()
        assert "1 total" in summary
        assert "Hard (reject): 1" in summary

    def test_to_summary_exploratory(self):
        block = self._make_block()
        block.exploratory_warning = True
        summary = block.to_summary()
        assert "Exploratory" in summary

    def test_prompt_prefix(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.DECISION,
            severity=ConstraintSeverity.REJECT, description="auth uses JWT",
            source="decisions",
        )
        block = self._make_block([c])
        prefix = block.prompt_prefix
        assert "GOVERNOR CONSTRAINTS" in prefix
        assert "auth uses JWT" in prefix
        assert "HARD CONSTRAINTS" in prefix
        assert "END CONSTRAINTS" in prefix


# ---------------------------------------------------------------------------
# Prompt Prefix Rendering
# ---------------------------------------------------------------------------


class TestRenderPromptPrefix:
    def test_basic(self):
        block = ConstraintBlock(
            constraints=[],
            sources=[],
            content_hash="abc123",
            compiled_at=datetime.now(timezone.utc),
            envelope="strict",
        )
        prefix = render_prompt_prefix(block)
        assert "hash:abc123" in prefix
        assert "ENVELOPE: strict" in prefix
        assert "END CONSTRAINTS" in prefix

    def test_with_intent_scope_mode(self):
        block = ConstraintBlock(
            constraints=[],
            sources=[],
            content_hash="x",
            compiled_at=datetime.now(timezone.utc),
            intent="production",
            scope=["src/auth/**"],
            mode="code",
            envelope="strict",
        )
        prefix = render_prompt_prefix(block)
        assert "INTENT: production" in prefix
        assert "SCOPE: src/auth/**" in prefix
        assert "MODE: code" in prefix

    def test_hard_section(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.DECISION,
            severity=ConstraintSeverity.REJECT, description="use JWT",
            source="decisions",
        )
        block = ConstraintBlock(
            constraints=[c], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        prefix = render_prompt_prefix(block)
        assert "HARD CONSTRAINTS" in prefix
        assert "use JWT" in prefix

    def test_soft_section(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.WARN, description="prefer async",
            source="anchors",
        )
        block = ConstraintBlock(
            constraints=[c], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        prefix = render_prompt_prefix(block)
        assert "SOFT CONSTRAINTS" in prefix
        assert "prefer async" in prefix

    def test_security_section(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.SECURITY_PATTERN,
            severity=ConstraintSeverity.REJECT, description="No SQL injection (5 patterns)",
            source="security",
        )
        block = ConstraintBlock(
            constraints=[c], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        prefix = render_prompt_prefix(block)
        assert "SECURITY" in prefix
        assert "SQL injection" in prefix

    def test_overruled_section(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.SCAR,
            severity=ConstraintSeverity.WARN, description="no DB queries",
            source="scars", overruled_by="w1",
        )
        w = OverrideWarrant(
            warrant_id="w1", invoked_by="jbeck", reason="hotfix CVE",
            scope=["src/**"], constraints_overruled=["c1"],
            expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        )
        block = ConstraintBlock(
            constraints=[c], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
            warrants=[w],
        )
        prefix = render_prompt_prefix(block)
        assert "OVERRULED CONSTRAINTS" in prefix
        assert "jbeck" in prefix
        assert "hotfix CVE" in prefix

    def test_exploratory_warning(self):
        block = ConstraintBlock(
            constraints=[], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="exploratory",
            exploratory_warning=True,
        )
        prefix = render_prompt_prefix(block)
        assert "WARNING" in prefix
        assert "Exploratory" in prefix


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------


class TestConstraintCache:
    def test_put_and_get(self):
        cache = ConstraintCache()
        block = ConstraintBlock(
            constraints=[], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        cache.put("key1", block)
        result = cache.get("key1")
        assert result is not None
        assert result.content_hash == "x"

    def test_miss(self):
        cache = ConstraintCache()
        assert cache.get("nonexistent") is None

    def test_eviction(self):
        cache = ConstraintCache(max_size=2)
        for i in range(3):
            block = ConstraintBlock(
                constraints=[], sources=[], content_hash=f"h{i}",
                compiled_at=datetime.now(timezone.utc), envelope="strict",
            )
            cache.put(f"key{i}", block)
        assert cache.size() == 2
        # First entry should be evicted
        assert cache.get("key0") is None
        assert cache.get("key2") is not None

    def test_invalidate(self):
        cache = ConstraintCache()
        block = ConstraintBlock(
            constraints=[], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        cache.put("key1", block)
        cache.invalidate()
        assert cache.get("key1") is None
        assert cache.size() == 0

    def test_expired_warrant_invalidates(self):
        cache = ConstraintCache()
        w = OverrideWarrant(
            warrant_id="w1", invoked_by="a", reason="r",
            scope=[], constraints_overruled=[],
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        block = ConstraintBlock(
            constraints=[], sources=[], content_hash="x",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
            warrants=[w],
        )
        cache.put("key1", block)
        # Should be stale because warrant expired
        result = cache.get("key1")
        assert result is None


class TestCacheKey:
    def test_deterministic(self):
        k1 = _compute_cache_key("prod", ["src/**"], "code", "strict", Path("/x"))
        k2 = _compute_cache_key("prod", ["src/**"], "code", "strict", Path("/x"))
        assert k1 == k2

    def test_different_inputs(self):
        k1 = _compute_cache_key("prod", ["src/**"], "code", "strict", Path("/x"))
        k2 = _compute_cache_key("hotfix", ["src/**"], "code", "strict", Path("/x"))
        assert k1 != k2


# ---------------------------------------------------------------------------
# Content Hash
# ---------------------------------------------------------------------------


class TestContentHash:
    def test_deterministic(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        h1 = _content_hash([c])
        h2 = _content_hash([c])
        assert h1 == h2

    def test_order_independent(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c2", kind=ConstraintKind.DECISION,
            severity=ConstraintSeverity.WARN, description="b", source="b",
        )
        h1 = _content_hash([c1, c2])
        h2 = _content_hash([c2, c1])
        assert h1 == h2  # Sorted by constraint_id


# ---------------------------------------------------------------------------
# Compile Constraints (Integration)
# ---------------------------------------------------------------------------


class TestCompileConstraints:
    def test_basic_compilation(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        assert isinstance(block, ConstraintBlock)
        assert block.content_hash
        assert block.compiled_at

    def test_envelope_detected(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        # Default is strict
        assert block.envelope in ("strict", "exploratory", "slim")
        # Should have at least envelope constraint
        envelope_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.ENVELOPE
        ]
        assert len(envelope_constraints) >= 1

    def test_security_patterns_included(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        security = [c for c in block.constraints if c.kind == ConstraintKind.SECURITY_PATTERN]
        assert len(security) >= 1  # At least some security patterns

    def test_scope_filtering(self, gov_dir):
        block = compile_constraints(
            scope="src/auth/**",
            governor_dir=gov_dir,
            use_cache=False,
        )
        assert block.scope == ["src/auth/**"]

    def test_intent_recorded(self, gov_dir):
        block = compile_constraints(
            intent="production",
            governor_dir=gov_dir,
            use_cache=False,
        )
        assert block.intent == "production"

    def test_mode_recorded(self, gov_dir):
        block = compile_constraints(
            mode="code",
            governor_dir=gov_dir,
            use_cache=False,
        )
        assert block.mode == "code"

    def test_content_hash_stable(self, gov_dir):
        block1 = compile_constraints(governor_dir=gov_dir, use_cache=False)
        block2 = compile_constraints(governor_dir=gov_dir, use_cache=False)
        assert block1.content_hash == block2.content_hash

    def test_caching(self, gov_dir):
        block1 = compile_constraints(governor_dir=gov_dir, use_cache=True)
        assert get_cache().size() >= 1
        block2 = compile_constraints(governor_dir=gov_dir, use_cache=True)
        # Cache hit should return same hash
        assert block1.content_hash == block2.content_hash

    def test_no_cache(self, gov_dir):
        compile_constraints(governor_dir=gov_dir, use_cache=False)
        assert get_cache().size() == 0

    def test_json_output(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        d = block.to_dict()
        assert "constraints" in d
        assert "sources" in d
        assert "content_hash" in d
        # Should be JSON serializable
        json_str = json.dumps(d, default=str)
        assert json_str

    def test_prompt_output(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        prefix = block.prompt_prefix
        assert "GOVERNOR CONSTRAINTS" in prefix
        assert "END CONSTRAINTS" in prefix

    def test_summary_output(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        summary = block.to_summary()
        assert "total" in summary

    def test_scope_string_normalized(self, gov_dir):
        block = compile_constraints(
            scope="src/**",
            governor_dir=gov_dir,
            use_cache=False,
        )
        assert block.scope == ["src/**"]

    def test_scope_list(self, gov_dir):
        block = compile_constraints(
            scope=["src/**", "tests/**"],
            governor_dir=gov_dir,
            use_cache=False,
        )
        assert block.scope == ["src/**", "tests/**"]


class TestCompileWithDecisions:
    def test_decisions_included(self, gov_dir):
        """Set up a decision and verify it appears in compilation."""
        from governor.claims import decision as make_decision
        from governor.ledgers import DecisionLedger

        ledger = DecisionLedger(gov_dir)
        claim = make_decision(topic="framework", choice="react")
        ledger.add(claim, rationale="test decision")

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        decision_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.DECISION
        ]
        assert len(decision_constraints) == 1
        assert "react" in decision_constraints[0].description

    def test_retracted_decisions_excluded(self, gov_dir):
        """Retracted decisions should not appear in compilation."""
        from governor.claims import decision as make_decision
        from governor.ledgers import DecisionLedger

        ledger = DecisionLedger(gov_dir)
        claim = make_decision(topic="db", choice="postgres")
        d = ledger.add(claim, rationale="initial")

        # Retract it
        retract_claim = make_decision(topic="db", choice="[RETRACTED] postgres")
        ledger.add(retract_claim, rationale="retracted", supersedes=d.id)

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        decision_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.DECISION
        ]
        # The retracted one should be excluded, superseded one should be gone
        for c in decision_constraints:
            assert "postgres" not in c.description or "[RETRACTED]" not in c.description


class TestCompileWithAnchors:
    def test_anchors_included(self, gov_dir):
        """Set up anchors and verify they appear in compilation."""
        from governor.continuity import (
            Anchor, AnchorType, Severity, AnchorRegistry,
        )

        registry = AnchorRegistry()
        anchor = Anchor(
            id="no-eval",
            anchor_type=AnchorType.PROHIBITION,
            description="No eval() calls",
            forbidden_patterns=["eval("],
            severity=Severity.REJECT,
            source="test",
        )
        registry.register(anchor)
        path = gov_dir / "continuity" / "anchors.json"
        registry.save(path)

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        anchor_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.ANCHOR
        ]
        assert len(anchor_constraints) == 1
        assert "eval()" in anchor_constraints[0].description
        assert anchor_constraints[0].severity == ConstraintSeverity.REJECT


class TestCompileWithInvariants:
    def test_invariants_included(self, gov_dir, project_dir):
        """Set up invariants and verify they appear in compilation."""
        from governor.invariant_store import InvariantSpec, InvariantStore

        store = InvariantStore(project_dir)
        spec = InvariantSpec(
            id="test-pytest",
            kind="test",
            params={"command": "pytest tests/ -x"},
            on_violation="block",
        )
        store.add(spec)

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        inv_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.INVARIANT
        ]
        assert len(inv_constraints) == 1
        assert "pytest" in inv_constraints[0].description


class TestCompileWithSpine:
    def test_spine_included(self, gov_dir, project_dir):
        """Set up an active spine and verify it appears in compilation."""
        from governor.spine import Spine, SpineManager

        manager = SpineManager(project_dir)
        spine = Spine(
            id="main-spine",
            structure={
                "files": {"README.md": "required"},
                "directories": {"src/": "required"},
                "forbidden_paths": ["*.secret"],
            },
            description="Main project structure",
        )
        manager.lock(spine)
        manager.set_active("main-spine")

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        spine_constraints = [
            c for c in block.constraints if c.kind == ConstraintKind.SPINE_RULE
        ]
        assert len(spine_constraints) >= 1
        descriptions = " ".join(c.description for c in spine_constraints)
        assert "README.md" in descriptions or "src/" in descriptions or "secret" in descriptions


class TestCompileExploratoryWarning:
    def test_exploratory_warning(self, gov_dir):
        """Exploratory mode should set the warning flag."""
        from governor.envelopes import set_envelope, EnvelopeMode

        set_envelope(gov_dir, EnvelopeMode.EXPLORATORY)

        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        assert block.exploratory_warning
        assert block.envelope == "exploratory"


# ---------------------------------------------------------------------------
# Monotonicity
# ---------------------------------------------------------------------------


class TestMonotonicity:
    def test_more_scope_same_or_more_constraints(self, gov_dir, project_dir):
        """Adding scope should never reduce constraint count (for non-scoped constraints)."""
        from governor.invariant_store import InvariantSpec, InvariantStore

        store = InvariantStore(project_dir)
        store.add(InvariantSpec(
            id="t1", kind="test",
            params={"command": "pytest"}, on_violation="block",
        ))
        store.add(InvariantSpec(
            id="f1", kind="file-exists",
            params={"path": "src/main.py"}, on_violation="block",
        ))

        block_global = compile_constraints(governor_dir=gov_dir, use_cache=False)
        block_scoped = compile_constraints(
            scope="src/**", governor_dir=gov_dir, use_cache=False,
        )
        # Global non-scoped constraints (security, envelope) should be present in both
        global_security = len([
            c for c in block_global.constraints if c.kind == ConstraintKind.SECURITY_PATTERN
        ])
        scoped_security = len([
            c for c in block_scoped.constraints if c.kind == ConstraintKind.SECURITY_PATTERN
        ])
        assert scoped_security == global_security


# ---------------------------------------------------------------------------
# Constraint Diff
# ---------------------------------------------------------------------------


class TestConstraintDiff:
    def test_no_changes(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        block1 = ConstraintBlock(
            constraints=[c], sources=[], content_hash="h1",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        block2 = ConstraintBlock(
            constraints=[c], sources=[], content_hash="h1",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        diff = diff_constraints(block1, block2)
        assert not diff.has_changes

    def test_added(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c2", kind=ConstraintKind.DECISION,
            severity=ConstraintSeverity.REJECT, description="b", source="b",
        )
        block1 = ConstraintBlock(
            constraints=[c1], sources=[], content_hash="h1",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        block2 = ConstraintBlock(
            constraints=[c1, c2], sources=[], content_hash="h2",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        diff = diff_constraints(block1, block2)
        assert diff.has_changes
        assert len(diff.added) == 1
        assert diff.added[0].constraint_id == "c2"

    def test_removed(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        block1 = ConstraintBlock(
            constraints=[c1], sources=[], content_hash="h1",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        block2 = ConstraintBlock(
            constraints=[], sources=[], content_hash="h2",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        diff = diff_constraints(block1, block2)
        assert diff.has_changes
        assert len(diff.removed) == 1

    def test_changed_severity(self):
        c1 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.WARN, description="a", source="a",
        )
        c2 = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="a", source="a",
        )
        block1 = ConstraintBlock(
            constraints=[c1], sources=[], content_hash="h1",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        block2 = ConstraintBlock(
            constraints=[c2], sources=[], content_hash="h2",
            compiled_at=datetime.now(timezone.utc), envelope="strict",
        )
        diff = diff_constraints(block1, block2)
        assert diff.has_changes
        assert len(diff.changed) == 1

    def test_to_dict(self):
        diff = ConstraintDiff(
            added=[], removed=[], changed=[],
            left_hash="h1", right_hash="h2",
        )
        d = diff.to_dict()
        assert d["left_hash"] == "h1"
        assert d["right_hash"] == "h2"


# ---------------------------------------------------------------------------
# Serialization Golden Tests
# ---------------------------------------------------------------------------


class TestGoldenSchemas:
    def test_constraint_block_schema(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        d = block.to_dict()
        required_keys = {
            "constraints", "sources", "content_hash", "compiled_at",
            "intent", "scope", "mode", "envelope", "profile",
            "warrants", "quorum_failures", "exploratory_warning",
        }
        assert required_keys.issubset(d.keys())

    def test_resolved_constraint_schema(self):
        c = ResolvedConstraint(
            constraint_id="c1", kind=ConstraintKind.ANCHOR,
            severity=ConstraintSeverity.REJECT, description="test",
            source="anchors", projection_priority=0.8,
        )
        d = c.to_dict()
        required_keys = {
            "constraint_id", "kind", "severity", "description",
            "source", "projection_priority",
        }
        assert required_keys.issubset(d.keys())

    def test_constraint_source_schema(self):
        s = ConstraintSource(subsystem="test", count=5, hash="abc")
        d = s.to_dict()
        assert set(d.keys()) == {"subsystem", "count", "hash"}

    def test_constraint_diff_schema(self):
        diff = ConstraintDiff(
            added=[], removed=[], changed=[],
            left_hash="h1", right_hash="h2",
        )
        d = diff.to_dict()
        assert set(d.keys()) == {"added", "removed", "changed", "left_hash", "right_hash"}


# ---------------------------------------------------------------------------
# Hash Utilities
# ---------------------------------------------------------------------------


class TestHashItems:
    def test_deterministic(self):
        items = [{"a": 1}, {"b": 2}]
        h1 = _hash_items(items)
        h2 = _hash_items(items)
        assert h1 == h2

    def test_different_items(self):
        h1 = _hash_items([{"a": 1}])
        h2 = _hash_items([{"a": 2}])
        assert h1 != h2


# ---------------------------------------------------------------------------
# Integration: Full Lifecycle
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_compile_diff_cycle(self, gov_dir):
        """Compile, add constraints, compile again, diff."""
        block1 = compile_constraints(governor_dir=gov_dir, use_cache=False)

        # Add a decision
        from governor.claims import decision as make_decision
        from governor.ledgers import DecisionLedger

        ledger = DecisionLedger(gov_dir)
        claim = make_decision(topic="auth", choice="JWT")
        ledger.add(claim, rationale="test")

        block2 = compile_constraints(governor_dir=gov_dir, use_cache=False)

        diff = diff_constraints(block1, block2)
        assert diff.has_changes
        assert len(diff.added) == 1
        assert "JWT" in diff.added[0].description

    def test_compile_renders_all_formats(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)

        # Prompt format
        prefix = block.prompt_prefix
        assert isinstance(prefix, str)
        assert len(prefix) > 0

        # JSON format
        d = block.to_dict()
        json_str = json.dumps(d, default=str)
        assert isinstance(json_str, str)

        # Summary format
        summary = block.to_summary()
        assert isinstance(summary, str)

    def test_sources_tracked(self, gov_dir):
        block = compile_constraints(governor_dir=gov_dir, use_cache=False)
        # Should have at least envelope and security sources
        subsystems = {s.subsystem for s in block.sources}
        assert "envelope" in subsystems
        assert "security" in subsystems
