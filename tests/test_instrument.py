# SPDX-License-Identifier: Apache-2.0
"""
Tests for AG2 Instrumented Execution — instrument.py

~200 tests across enum validation, dataclass creation/serialization,
all service classes, tool parsers, and full lifecycle integration.
"""

import json
import time
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from governor.instrument import (
    # Enums
    EventKind,
    ClaimModality,
    AG2ClaimType,
    DiffFinding,
    ActorKind,
    FindingSeverity,
    InstrumentProfile,
    # Supporting dataclasses
    Actor,
    Environment,
    RepoState,
    ModelSpec,
    RunConfig,
    RunInputs,
    # Core dataclasses
    RunManifest,
    Event,
    ArtifactReceipt,
    ClaimSource,
    ClaimScope,
    AG2Claim,
    ClaimDiffResult,
    Waiver,
    # Report dataclasses
    ReportFinding,
    ReportProvenance,
    AG2Report,
    # Config
    InstrumentConfig,
    # Services
    ArtifactStore,
    RunStore,
    EventWriter,
    ClaimExtractor,
    AG2ClaimDiffer,
    ReportGenerator,
    RunVerifier,
    WaiverStore,
    InstrumentSystem,
    # Tool parsers
    PytestParser,
    MypyParser,
    RuffParser,
    DEFAULT_TOOL_PARSERS,
    # Helpers
    _make_run_id,
    _now_iso,
    _count_jsonl,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def tmp_gov(tmp_path):
    """Create a temporary governor directory."""
    gov_dir = tmp_path / ".governor"
    gov_dir.mkdir()
    return gov_dir


@pytest.fixture
def artifact_store(tmp_gov):
    """Create an artifact store."""
    return ArtifactStore(tmp_gov / "instrument")


@pytest.fixture
def run_store(tmp_gov):
    """Create a run store."""
    return RunStore(tmp_gov / "instrument")


@pytest.fixture
def system(tmp_gov):
    """Create an InstrumentSystem."""
    return InstrumentSystem(tmp_gov)


@pytest.fixture
def sample_actor():
    return Actor(kind=ActorKind.HUMAN, id="user1", name="Test User")


@pytest.fixture
def sample_event(sample_actor):
    return Event(
        event_id="evt001",
        ts=_now_iso(),
        run_id="run001",
        kind=EventKind.TOOL_RESULT,
        actor=sample_actor,
        payload={"tool": "pytest", "exit_code": 0, "output": "passed"},
    )


# =============================================================================
# Enum Tests
# =============================================================================


class TestEventKind:
    def test_values(self):
        assert len(EventKind) == 12

    def test_str_behavior(self):
        assert EventKind.PROMPT_SENT.value == "prompt_sent"
        assert str(EventKind.TOOL_RESULT) == "EventKind.TOOL_RESULT"

    def test_all_values_are_strings(self):
        for kind in EventKind:
            assert isinstance(kind.value, str)


class TestClaimModality:
    def test_values(self):
        assert len(ClaimModality) == 4
        assert ClaimModality.ASSERT.value == "assert"
        assert ClaimModality.HYPOTHESIS.value == "hypothesis"

    def test_str_enum(self):
        assert isinstance(ClaimModality.ASSERT.value, str)


class TestAG2ClaimType:
    def test_values(self):
        assert len(AG2ClaimType) == 8

    def test_distinct_from_governor_claim_type(self):
        # Ensure no collision with governor.claims.ClaimType
        from governor.claims import ClaimType
        ag2_values = {t.value for t in AG2ClaimType}
        gov_values = {t.value for t in ClaimType}
        assert ag2_values.isdisjoint(gov_values)


class TestDiffFinding:
    def test_values(self):
        assert len(DiffFinding) == 5
        assert DiffFinding.CONTRADICTION.value == "contradiction"
        assert DiffFinding.DRIFT.value == "drift"


class TestActorKind:
    def test_values(self):
        assert len(ActorKind) == 3
        assert ActorKind.HUMAN.value == "human"


class TestFindingSeverity:
    def test_values(self):
        assert len(FindingSeverity) == 3
        assert FindingSeverity.ERROR.value == "error"


class TestInstrumentProfile:
    def test_values(self):
        assert len(InstrumentProfile) == 3
        assert InstrumentProfile.GREENFIELD.value == "greenfield"


# =============================================================================
# Supporting Dataclass Tests
# =============================================================================


class TestActor:
    def test_creation(self):
        a = Actor(kind=ActorKind.HUMAN, id="u1", name="Alice")
        assert a.kind == ActorKind.HUMAN
        assert a.id == "u1"
        assert a.name == "Alice"

    def test_to_dict(self):
        a = Actor(kind=ActorKind.AGENT, id="a1")
        d = a.to_dict()
        assert d["kind"] == "agent"
        assert d["id"] == "a1"

    def test_from_dict(self):
        d = {"kind": "pipeline", "id": "p1", "name": "CI"}
        a = Actor.from_dict(d)
        assert a.kind == ActorKind.PIPELINE
        assert a.name == "CI"

    def test_roundtrip(self):
        a = Actor(kind=ActorKind.HUMAN, id="u1", name="Bob")
        assert Actor.from_dict(a.to_dict()) == a


class TestEnvironment:
    def test_creation(self):
        e = Environment(os_name="Linux", hostname="box", cwd="/tmp", timezone="+0000")
        assert e.os_name == "Linux"

    def test_to_dict(self):
        e = Environment(os_name="Darwin", hostname="mac", cwd="/", timezone="PST")
        d = e.to_dict()
        assert d["os"] == "Darwin"

    def test_from_dict(self):
        d = {"os": "Windows", "hostname": "pc", "cwd": "C:\\", "timezone": "EST"}
        e = Environment.from_dict(d)
        assert e.os_name == "Windows"

    def test_capture(self):
        e = Environment.capture()
        assert e.os_name  # should be non-empty
        assert e.cwd  # should be non-empty

    def test_roundtrip(self):
        e = Environment(os_name="Linux", hostname="h", cwd="/a", timezone="Z")
        assert Environment.from_dict(e.to_dict()) == e


class TestRepoState:
    def test_creation(self):
        r = RepoState(url="git@gh", git_sha="abc", branch="main", dirty=False)
        assert r.url == "git@gh"

    def test_to_dict(self):
        r = RepoState(url="", git_sha="def", branch="dev", dirty=True)
        d = r.to_dict()
        assert d["dirty"] is True

    def test_from_dict(self):
        d = {"url": "", "git_sha": "", "branch": "", "dirty": False}
        r = RepoState.from_dict(d)
        assert r.dirty is False

    def test_capture(self):
        r = RepoState.capture()
        # In a git repo, should have a sha
        assert isinstance(r.git_sha, str)

    def test_roundtrip(self):
        r = RepoState(url="u", git_sha="s", branch="b", dirty=True)
        assert RepoState.from_dict(r.to_dict()) == r


class TestModelSpec:
    def test_creation(self):
        m = ModelSpec(name="gpt-4", provider="openai")
        assert m.name == "gpt-4"

    def test_to_dict(self):
        m = ModelSpec(name="claude", provider="anthropic", version="3")
        d = m.to_dict()
        assert d["provider"] == "anthropic"

    def test_from_dict(self):
        d = {"name": "m", "provider": "p", "version": "1", "parameters_hash": "h"}
        m = ModelSpec.from_dict(d)
        assert m.parameters_hash == "h"

    def test_roundtrip(self):
        m = ModelSpec(name="n", provider="p", version="v", parameters_hash="h")
        assert ModelSpec.from_dict(m.to_dict()) == m


class TestRunConfig:
    def test_creation(self):
        c = RunConfig(profile=InstrumentProfile.STRICT)
        assert c.profile == InstrumentProfile.STRICT

    def test_to_dict(self):
        c = RunConfig(profile=InstrumentProfile.FORENSIC, anchors_hash="abc")
        d = c.to_dict()
        assert d["profile"] == "forensic"

    def test_from_dict(self):
        d = {"profile": "greenfield", "anchors_hash": "x", "toolchain_versions": {"py": "3.12"}}
        c = RunConfig.from_dict(d)
        assert c.toolchain_versions == {"py": "3.12"}

    def test_roundtrip(self):
        c = RunConfig(profile=InstrumentProfile.GREENFIELD, anchors_hash="h")
        assert RunConfig.from_dict(c.to_dict()) == c


class TestRunInputs:
    def test_creation(self):
        i = RunInputs(task_id="t1", prompt_hash="ph", seed=42)
        assert i.seed == 42

    def test_defaults(self):
        i = RunInputs()
        assert i.task_id == ""
        assert i.seed == 0

    def test_roundtrip(self):
        i = RunInputs(task_id="t", prompt_hash="p", seed=7)
        assert RunInputs.from_dict(i.to_dict()) == i


# =============================================================================
# Core Dataclass Tests
# =============================================================================


class TestRunManifest:
    def test_creation(self):
        m = RunManifest(
            run_id="abc123",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        assert m.run_id == "abc123"

    def test_to_dict(self):
        m = RunManifest(
            run_id="r1",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        d = m.to_dict()
        assert d["run_id"] == "r1"
        assert d["actor"]["kind"] == "human"

    def test_from_dict(self):
        d = {
            "run_id": "r2",
            "created_at": "2024-01-01T00:00:00Z",
            "actor": {"kind": "agent", "id": "a1", "name": ""},
            "environment": {"os": "L", "hostname": "h", "cwd": "/", "timezone": "Z"},
            "config": {"profile": "strict"},
        }
        m = RunManifest.from_dict(d)
        assert m.config.profile == InstrumentProfile.STRICT

    def test_roundtrip(self):
        m = RunManifest(
            run_id="r1",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
            models=[ModelSpec("m", "p")],
        )
        m2 = RunManifest.from_dict(m.to_dict())
        assert m2.run_id == m.run_id
        assert len(m2.models) == 1

    def test_default_counts(self):
        m = RunManifest(
            run_id="r1",
            created_at="now",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        assert m.event_count == 0
        assert m.receipt_count == 0
        assert m.claim_count == 0


class TestEvent:
    def test_creation(self, sample_actor):
        e = Event(
            event_id="e1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.PROMPT_SENT,
            actor=sample_actor,
        )
        assert e.kind == EventKind.PROMPT_SENT

    def test_to_json_line(self, sample_actor):
        e = Event(
            event_id="e1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.ERROR,
            actor=sample_actor,
            payload={"msg": "fail"},
        )
        line = e.to_json_line()
        parsed = json.loads(line)
        assert parsed["kind"] == "error"

    def test_from_dict(self):
        d = {
            "event_id": "e2",
            "ts": "2024-01-01T00:00:00Z",
            "run_id": "r1",
            "kind": "file_write",
            "actor": {"kind": "agent", "id": "a1"},
            "payload": {"path": "/tmp/x"},
        }
        e = Event.from_dict(d)
        assert e.kind == EventKind.FILE_WRITE
        assert e.payload["path"] == "/tmp/x"

    def test_roundtrip(self, sample_actor):
        e = Event(
            event_id="e1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.GIT_DIFF,
            actor=sample_actor,
            payload={"diff": "+foo"},
            receipt_refs=["hash1"],
        )
        e2 = Event.from_dict(e.to_dict())
        assert e2.event_id == e.event_id
        assert e2.receipt_refs == ["hash1"]

    def test_parent_event_id(self, sample_actor):
        e = Event(
            event_id="e2",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.TOOL_RESULT,
            actor=sample_actor,
            parent_event_id="e1",
        )
        assert e.parent_event_id == "e1"


class TestArtifactReceipt:
    def test_creation(self):
        r = ArtifactReceipt(artifact_hash="abc", size_bytes=100)
        assert r.mime_type == "application/octet-stream"

    def test_to_json_line(self):
        r = ArtifactReceipt(artifact_hash="def", size_bytes=50, mime_type="text/plain")
        parsed = json.loads(r.to_json_line())
        assert parsed["mime_type"] == "text/plain"

    def test_roundtrip(self):
        r = ArtifactReceipt(artifact_hash="h", size_bytes=10, mime_type="m", stored_at="t")
        r2 = ArtifactReceipt.from_dict(r.to_dict())
        assert r2 == r


class TestClaimSource:
    def test_creation(self):
        s = ClaimSource(kind="tool_parser", event_id="e1")
        assert s.kind == "tool_parser"

    def test_roundtrip(self):
        s = ClaimSource(kind="manual", event_id="e2", model="gpt-4")
        assert ClaimSource.from_dict(s.to_dict()) == s


class TestClaimScope:
    def test_match_key_path(self):
        s = ClaimScope(path="src/main.py")
        assert "path:src/main.py" in s.match_key

    def test_match_key_command(self):
        s = ClaimScope(command="pytest")
        assert "cmd:pytest" in s.match_key

    def test_match_key_global(self):
        s = ClaimScope()
        assert s.match_key == "global"

    def test_match_key_composite(self):
        s = ClaimScope(path="f.py", symbol="Foo")
        key = s.match_key
        assert "path:f.py" in key
        assert "sym:Foo" in key

    def test_roundtrip(self):
        s = ClaimScope(repo_sha="abc", path="p", symbol="s", command="c")
        assert ClaimScope.from_dict(s.to_dict()) == s


class TestAG2Claim:
    def test_assert_requires_evidence(self):
        with pytest.raises(ValueError, match="I5"):
            AG2Claim(
                claim_id="c1",
                ts="now",
                run_id="r1",
                source=ClaimSource(kind="manual"),
                modality=ClaimModality.ASSERT,
                type=AG2ClaimType.TEST_RESULT,
                subject="pytest",
                predicate="passed",
                evidence_refs=[],
            )

    def test_assert_with_evidence(self):
        c = AG2Claim(
            claim_id="c1",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.TEST_RESULT,
            subject="pytest",
            predicate="passed",
            evidence_refs=["e1"],
        )
        assert c.evidence_refs == ["e1"]

    def test_hypothesis_requires_notes(self):
        with pytest.raises(ValueError, match="notes"):
            AG2Claim(
                claim_id="c2",
                ts="now",
                run_id="r1",
                source=ClaimSource(kind="manual"),
                modality=ClaimModality.HYPOTHESIS,
                type=AG2ClaimType.COMPLETION_CLAIM,
                subject="maybe",
                predicate="possible",
            )

    def test_hypothesis_with_notes(self):
        c = AG2Claim(
            claim_id="c2",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.HYPOTHESIS,
            type=AG2ClaimType.COMPLETION_CLAIM,
            subject="maybe",
            predicate="possible",
            notes="Needs verification",
        )
        assert c.notes == "Needs verification"

    def test_infer_no_evidence_ok(self):
        c = AG2Claim(
            claim_id="c3",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="model_block"),
            modality=ClaimModality.INFER,
            type=AG2ClaimType.COMPLETION_CLAIM,
            subject="x",
            predicate="y",
        )
        assert c.modality == ClaimModality.INFER

    def test_plan_no_evidence_ok(self):
        c = AG2Claim(
            claim_id="c4",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.PLAN,
            type=AG2ClaimType.ACTION_PERFORMED,
            subject="deploy",
            predicate="planned",
        )
        assert c.modality == ClaimModality.PLAN

    def test_roundtrip(self):
        c = AG2Claim(
            claim_id="c1",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="tool_parser", event_id="e1"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.TEST_RESULT,
            subject="pytest",
            predicate="passed",
            scope=ClaimScope(command="pytest"),
            evidence_refs=["e1"],
            confidence=0.9,
        )
        c2 = AG2Claim.from_dict(c.to_dict())
        assert c2.claim_id == c.claim_id
        assert c2.confidence == 0.9

    def test_default_confidence(self):
        c = AG2Claim(
            claim_id="c1",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.PLAN,
            type=AG2ClaimType.COMPLETION_CLAIM,
            subject="s",
            predicate="p",
        )
        assert c.confidence == 1.0

    def test_object_field(self):
        c = AG2Claim(
            claim_id="c1",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.FILE_CHANGED,
            subject="main.py",
            predicate="contains",
            object="def foo():",
            evidence_refs=["e1"],
        )
        assert c.object == "def foo():"


class TestClaimDiffResult:
    def test_creation(self):
        r = ClaimDiffResult(
            left_run_id="l",
            right_run_id="r",
            finding=DiffFinding.CONTRADICTION,
            match_key="k",
            details="mismatch",
        )
        assert r.finding == DiffFinding.CONTRADICTION

    def test_roundtrip(self):
        claim = AG2Claim(
            claim_id="c1",
            ts="now",
            run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.TEST_RESULT,
            subject="s",
            predicate="p",
            evidence_refs=["e1"],
        )
        r = ClaimDiffResult(
            left_run_id="l",
            right_run_id="r",
            finding=DiffFinding.DRIFT,
            match_key="k",
            left_claim=claim,
            details="drifted",
        )
        r2 = ClaimDiffResult.from_dict(r.to_dict())
        assert r2.finding == DiffFinding.DRIFT
        assert r2.left_claim is not None
        assert r2.left_claim.claim_id == "c1"


class TestWaiver:
    def test_creation_requires_reason(self):
        with pytest.raises(ValueError, match="reason"):
            Waiver(waiver_id="w1", rule_id="r1", scope="*", reason="")

    def test_creation_ok(self):
        w = Waiver(waiver_id="w1", rule_id="contradiction", scope="*.py", reason="Known issue")
        assert w.rule_id == "contradiction"

    def test_is_expired_false(self):
        w = Waiver(
            waiver_id="w1",
            rule_id="r1",
            scope="*",
            reason="ok",
            expires=(datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        )
        assert not w.is_expired

    def test_is_expired_true(self):
        w = Waiver(
            waiver_id="w1",
            rule_id="r1",
            scope="*",
            reason="ok",
            expires=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        assert w.is_expired

    def test_is_expired_permanent(self):
        w = Waiver(waiver_id="w1", rule_id="r1", scope="*", reason="ok")
        assert not w.is_expired

    def test_covers_matching(self):
        w = Waiver(waiver_id="w1", rule_id="drift", scope="src/*.py", reason="ok")
        assert w.covers("drift", "src/main.py")
        assert not w.covers("drift", "tests/test.py")
        assert not w.covers("other", "src/main.py")

    def test_covers_expired(self):
        w = Waiver(
            waiver_id="w1",
            rule_id="drift",
            scope="*",
            reason="ok",
            expires=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        assert not w.covers("drift", "any.py")

    def test_roundtrip(self):
        w = Waiver(
            waiver_id="w1",
            rule_id="r1",
            scope="*.py",
            reason="test",
            created_by="admin",
        )
        w2 = Waiver.from_dict(w.to_dict())
        assert w2.waiver_id == w.waiver_id
        assert w2.reason == "test"


# =============================================================================
# Report Dataclass Tests
# =============================================================================


class TestReportFinding:
    def test_creation(self):
        f = ReportFinding(kind="I0", severity=FindingSeverity.ERROR, summary="bad")
        assert f.kind == "I0"

    def test_roundtrip(self):
        f = ReportFinding(
            kind="I5",
            severity=FindingSeverity.WARNING,
            claim_refs=["c1"],
            evidence_refs=["e1"],
            summary="orphan",
        )
        f2 = ReportFinding.from_dict(f.to_dict())
        assert f2.claim_refs == ["c1"]


class TestReportProvenance:
    def test_defaults(self):
        p = ReportProvenance()
        assert p.spec_version == "ag2_instrument_v1"

    def test_roundtrip(self):
        p = ReportProvenance(spec_version="v2", generator_version="1.0")
        assert ReportProvenance.from_dict(p.to_dict()) == p


class TestAG2Report:
    def test_creation(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1"],
            generated_at="now",
        )
        assert r.report_id == "rpt1"

    def test_to_markdown_pass(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1"],
            generated_at="2024-01-01T00:00:00Z",
            invariants_satisfied=["I0", "I5"],
        )
        md = r.to_markdown()
        assert "PASS" in md
        assert "r1" in md

    def test_to_markdown_fail(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1"],
            generated_at="now",
            findings=[
                ReportFinding(kind="I0", severity=FindingSeverity.ERROR, summary="bad"),
            ],
            invariants_violated=["I0"],
        )
        md = r.to_markdown()
        assert "FAIL" in md

    def test_to_markdown_warn(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1"],
            generated_at="now",
            findings=[
                ReportFinding(kind="drift", severity=FindingSeverity.WARNING, summary="drifted"),
            ],
        )
        md = r.to_markdown()
        assert "WARN" in md

    def test_roundtrip(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1", "r2"],
            generated_at="now",
            findings=[
                ReportFinding(kind="I5", severity=FindingSeverity.ERROR, summary="orphan"),
            ],
            invariants_satisfied=["I0"],
            invariants_violated=["I5"],
        )
        r2 = AG2Report.from_dict(r.to_dict())
        assert r2.report_id == "rpt1"
        assert len(r2.findings) == 1


# =============================================================================
# Config Tests
# =============================================================================


class TestInstrumentConfig:
    def test_defaults(self):
        c = InstrumentConfig()
        assert c.profile == InstrumentProfile.GREENFIELD
        assert c.auto_extract_claims is True
        assert c.artifact_size_threshold == 4096

    def test_save_load(self, tmp_path):
        c = InstrumentConfig(
            profile=InstrumentProfile.STRICT,
            auto_extract_claims=False,
            artifact_size_threshold=8192,
        )
        path = tmp_path / "config.json"
        c.save(path)
        c2 = InstrumentConfig.load(path)
        assert c2.profile == InstrumentProfile.STRICT
        assert c2.auto_extract_claims is False
        assert c2.artifact_size_threshold == 8192

    def test_load_missing(self, tmp_path):
        c = InstrumentConfig.load(tmp_path / "nonexistent.json")
        assert c.profile == InstrumentProfile.GREENFIELD

    def test_roundtrip(self):
        c = InstrumentConfig(profile=InstrumentProfile.FORENSIC)
        c2 = InstrumentConfig.from_dict(c.to_dict())
        assert c2.profile == c.profile


# =============================================================================
# ArtifactStore Tests
# =============================================================================


class TestArtifactStore:
    def test_store_and_retrieve(self, artifact_store):
        data = b"hello world"
        receipt = artifact_store.store(data)
        assert receipt.size_bytes == len(data)
        assert artifact_store.retrieve(receipt.artifact_hash) == data

    def test_store_idempotent(self, artifact_store):
        data = b"idempotent"
        r1 = artifact_store.store(data)
        r2 = artifact_store.store(data)
        assert r1.artifact_hash == r2.artifact_hash

    def test_store_text(self, artifact_store):
        receipt = artifact_store.store_text("hello", "text/plain")
        assert receipt.mime_type == "text/plain"
        assert artifact_store.retrieve(receipt.artifact_hash) == b"hello"

    def test_retrieve_missing(self, artifact_store):
        assert artifact_store.retrieve("nonexistent") is None

    def test_exists(self, artifact_store):
        data = b"exists"
        receipt = artifact_store.store(data)
        assert artifact_store.exists(receipt.artifact_hash)
        assert not artifact_store.exists("missing_hash")

    def test_verify_valid(self, artifact_store):
        data = b"verify me"
        receipt = artifact_store.store(data)
        assert artifact_store.verify(receipt.artifact_hash)

    def test_verify_missing(self, artifact_store):
        assert not artifact_store.verify("nonexistent")

    def test_verify_corrupt(self, artifact_store):
        data = b"corrupt me"
        receipt = artifact_store.store(data)
        # Corrupt the file
        path = artifact_store._path_for(receipt.artifact_hash)
        path.write_bytes(b"corrupted")
        assert not artifact_store.verify(receipt.artifact_hash)

    def test_path_structure(self, artifact_store):
        data = b"path test"
        receipt = artifact_store.store(data)
        sha = receipt.artifact_hash
        path = artifact_store._path_for(sha)
        assert path.parent.parent.name == sha[:2]
        assert path.parent.name == sha[2:4]

    def test_different_data_different_hash(self, artifact_store):
        r1 = artifact_store.store(b"data1")
        r2 = artifact_store.store(b"data2")
        assert r1.artifact_hash != r2.artifact_hash

    def test_empty_data(self, artifact_store):
        receipt = artifact_store.store(b"")
        assert receipt.size_bytes == 0
        assert artifact_store.retrieve(receipt.artifact_hash) == b""

    def test_large_data(self, artifact_store):
        data = b"x" * 100000
        receipt = artifact_store.store(data)
        assert artifact_store.retrieve(receipt.artifact_hash) == data


# =============================================================================
# RunStore Tests
# =============================================================================


class TestRunStore:
    def test_create_and_load(self, run_store):
        m = RunManifest(
            run_id="r1",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        run_store.create_run(m)
        loaded = run_store.load_manifest("r1")
        assert loaded is not None
        assert loaded.run_id == "r1"

    def test_load_missing(self, run_store):
        assert run_store.load_manifest("nonexistent") is None

    def test_finish_run(self, run_store):
        m = RunManifest(
            run_id="r2",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        run_store.create_run(m)
        finished = run_store.finish_run("r2")
        assert finished is not None
        assert finished.finished_at != ""

    def test_finish_missing(self, run_store):
        assert run_store.finish_run("nonexistent") is None

    def test_list_runs(self, run_store):
        for rid in ["b", "a", "c"]:
            m = RunManifest(
                run_id=rid,
                created_at="2024-01-01T00:00:00Z",
                actor=Actor(ActorKind.HUMAN, "u1"),
                environment=Environment("L", "h", "/", "Z"),
                config=RunConfig(InstrumentProfile.GREENFIELD),
            )
            run_store.create_run(m)
        runs = run_store.list_runs()
        assert runs == ["a", "b", "c"]

    def test_list_runs_empty(self, run_store):
        assert run_store.list_runs() == []

    def test_last_run(self, run_store):
        for i, rid in enumerate(["older", "newer"]):
            m = RunManifest(
                run_id=rid,
                created_at=f"2024-01-0{i+1}T00:00:00Z",
                actor=Actor(ActorKind.HUMAN, "u1"),
                environment=Environment("L", "h", "/", "Z"),
                config=RunConfig(InstrumentProfile.GREENFIELD),
            )
            run_store.create_run(m)
        assert run_store.last_run() == "newer"

    def test_last_run_empty(self, run_store):
        assert run_store.last_run() is None

    def test_roundtrip_with_models(self, run_store):
        m = RunManifest(
            run_id="r3",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.AGENT, "a1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.STRICT),
            models=[ModelSpec("claude", "anthropic")],
        )
        run_store.create_run(m)
        loaded = run_store.load_manifest("r3")
        assert len(loaded.models) == 1
        assert loaded.models[0].name == "claude"


# =============================================================================
# EventWriter Tests
# =============================================================================


class TestEventWriter:
    def test_append_and_read(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r1"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store)

        e = Event(
            event_id="e1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.PROMPT_SENT,
            actor=sample_actor,
            payload={"text": "hello"},
        )
        writer.append_event(e)

        events = writer.read_events()
        assert len(events) == 1
        assert events[0].event_id == "e1"

    def test_large_payload_offloaded(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r2"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store, threshold=50)

        large_payload = {"data": "x" * 100}
        e = Event(
            event_id="e2",
            ts="2024-01-01T00:00:00Z",
            run_id="r2",
            kind=EventKind.MODEL_OUTPUT,
            actor=sample_actor,
            payload=large_payload,
        )
        result = writer.append_event(e)

        # Payload should be replaced with artifact ref
        assert "_artifact_ref" in result.payload
        assert len(result.receipt_refs) > 0

        # Artifact should be retrievable
        sha = result.payload["_artifact_ref"]
        assert artifact_store.exists(sha)

    def test_small_payload_not_offloaded(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r3"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store, threshold=4096)

        e = Event(
            event_id="e3",
            ts="2024-01-01T00:00:00Z",
            run_id="r3",
            kind=EventKind.TOOL_RESULT,
            actor=sample_actor,
            payload={"small": True},
        )
        result = writer.append_event(e)
        assert "_artifact_ref" not in result.payload

    def test_store_artifact(self, tmp_gov, artifact_store):
        run_dir = tmp_gov / "instrument" / "runs" / "r4"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store)

        receipt = writer.store_artifact(b"artifact data")
        assert receipt.size_bytes > 0
        receipts = writer.read_receipts()
        assert len(receipts) == 1

    def test_read_events_empty(self, tmp_gov, artifact_store):
        run_dir = tmp_gov / "instrument" / "runs" / "r5"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store)
        assert writer.read_events() == []

    def test_read_receipts_empty(self, tmp_gov, artifact_store):
        run_dir = tmp_gov / "instrument" / "runs" / "r6"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store)
        assert writer.read_receipts() == []

    def test_multiple_events_ordering(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r7"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store)

        for i in range(5):
            e = Event(
                event_id=f"e{i}",
                ts=f"2024-01-01T00:0{i}:00Z",
                run_id="r7",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
            )
            writer.append_event(e)

        events = writer.read_events()
        assert len(events) == 5
        assert events[0].event_id == "e0"
        assert events[4].event_id == "e4"

    def test_append_event_with_existing_receipt_refs(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r8"
        run_dir.mkdir(parents=True)
        writer = EventWriter(run_dir, artifact_store, threshold=50)

        large_payload = {"data": "y" * 100}
        e = Event(
            event_id="e8",
            ts="2024-01-01T00:00:00Z",
            run_id="r8",
            kind=EventKind.MODEL_OUTPUT,
            actor=sample_actor,
            payload=large_payload,
            receipt_refs=["existing_ref"],
        )
        result = writer.append_event(e)
        assert "existing_ref" in result.receipt_refs
        assert len(result.receipt_refs) == 2  # existing + new artifact


# =============================================================================
# ClaimExtractor Tests
# =============================================================================


class TestClaimExtractor:
    def test_extract_pytest_pass(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r1"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e1",
                ts="now",
                run_id="r1",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "pytest", "exit_code": 0},
            )
        ]
        claims = extractor.extract_from_events(events, "r1")
        assert len(claims) == 1
        assert claims[0].type == AG2ClaimType.TEST_RESULT
        assert claims[0].predicate == "passed"

    def test_extract_pytest_fail(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r2"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e2",
                ts="now",
                run_id="r2",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "pytest", "exit_code": 1},
            )
        ]
        claims = extractor.extract_from_events(events, "r2")
        assert len(claims) == 1
        assert claims[0].predicate == "failed"

    def test_extract_file_write(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r3"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e3",
                ts="now",
                run_id="r3",
                kind=EventKind.FILE_WRITE,
                actor=sample_actor,
                payload={"path": "src/main.py"},
            )
        ]
        claims = extractor.extract_from_events(events, "r3")
        assert len(claims) == 1
        assert claims[0].type == AG2ClaimType.FILE_CHANGED
        assert claims[0].scope.path == "src/main.py"

    def test_extract_generic_tool(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r4"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e4",
                ts="now",
                run_id="r4",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "unknown_tool"},
            )
        ]
        claims = extractor.extract_from_events(events, "r4")
        assert len(claims) == 1
        assert claims[0].type == AG2ClaimType.ACTION_PERFORMED

    def test_write_and_read_claims(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r5"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e5",
                ts="now",
                run_id="r5",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "pytest", "exit_code": 0},
            )
        ]
        claims = extractor.extract_from_events(events, "r5")
        extractor.write_claims(claims)

        read_back = extractor.read_claims()
        assert len(read_back) == 1
        assert read_back[0].type == AG2ClaimType.TEST_RESULT

    def test_read_claims_empty(self, tmp_gov):
        run_dir = tmp_gov / "instrument" / "runs" / "r6"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)
        assert extractor.read_claims() == []

    def test_no_claim_from_prompt(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r7"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e7",
                ts="now",
                run_id="r7",
                kind=EventKind.PROMPT_SENT,
                actor=sample_actor,
                payload={"text": "Do something"},
            )
        ]
        claims = extractor.extract_from_events(events, "r7")
        assert len(claims) == 0

    def test_extract_multiple_events(self, tmp_gov, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r8"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e8a",
                ts="now",
                run_id="r8",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "pytest", "exit_code": 0},
            ),
            Event(
                event_id="e8b",
                ts="now",
                run_id="r8",
                kind=EventKind.FILE_WRITE,
                actor=sample_actor,
                payload={"path": "foo.py"},
            ),
        ]
        claims = extractor.extract_from_events(events, "r8")
        assert len(claims) == 2

    def test_tool_result_without_exit_code(self, tmp_gov, sample_actor):
        """Tool result with known parser but missing exit_code produces no claims."""
        run_dir = tmp_gov / "instrument" / "runs" / "r9"
        run_dir.mkdir(parents=True)
        extractor = ClaimExtractor(run_dir)

        events = [
            Event(
                event_id="e9",
                ts="now",
                run_id="r9",
                kind=EventKind.TOOL_RESULT,
                actor=sample_actor,
                payload={"tool": "pytest"},
            )
        ]
        claims = extractor.extract_from_events(events, "r9")
        # pytest parser returns [] when no exit_code
        assert len(claims) == 0


# =============================================================================
# AG2ClaimDiffer Tests
# =============================================================================


def _make_claim(
    subject: str = "pytest",
    predicate: str = "passed",
    modality: ClaimModality = ClaimModality.ASSERT,
    claim_type: AG2ClaimType = AG2ClaimType.TEST_RESULT,
    scope: ClaimScope | None = None,
    evidence_refs: list[str] | None = None,
    confidence: float = 1.0,
    run_id: str = "r1",
) -> AG2Claim:
    return AG2Claim(
        claim_id=uuid.uuid4().hex[:12],
        ts="now",
        run_id=run_id,
        source=ClaimSource(kind="manual"),
        modality=modality,
        type=claim_type,
        subject=subject,
        predicate=predicate,
        scope=scope or ClaimScope(command="pytest"),
        evidence_refs=evidence_refs or ["e1"],
        confidence=confidence,
    )


class TestAG2ClaimDiffer:
    def test_no_diff_identical(self):
        left = [_make_claim(run_id="l")]
        right = [_make_claim(run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        assert len(results) == 0

    def test_contradiction(self):
        left = [_make_claim(predicate="passed", run_id="l")]
        right = [_make_claim(predicate="failed", run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = [r.finding for r in results]
        assert DiffFinding.CONTRADICTION in findings

    def test_phantom_action_left_only(self):
        left = [_make_claim(subject="only_left", scope=ClaimScope(command="only_left"), run_id="l")]
        right = []
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        assert any(r.finding == DiffFinding.PHANTOM_ACTION for r in results)

    def test_phantom_action_right_only(self):
        left = []
        right = [_make_claim(subject="only_right", scope=ClaimScope(command="only_right"), run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        assert any(r.finding == DiffFinding.PHANTOM_ACTION for r in results)

    def test_unsupported_success(self):
        left = [_make_claim(predicate="failed", evidence_refs=["e1"], run_id="l")]
        right = [_make_claim(predicate="passed", evidence_refs=["e1"], run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = [r.finding for r in results]
        assert DiffFinding.UNSUPPORTED_SUCCESS in findings

    def test_supported_success(self):
        """Success with new evidence should NOT produce unsupported_success."""
        left = [_make_claim(predicate="failed", evidence_refs=["e1"], run_id="l")]
        right = [_make_claim(predicate="passed", evidence_refs=["e1", "e2"], run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = [r.finding for r in results]
        assert DiffFinding.UNSUPPORTED_SUCCESS not in findings

    def test_drift(self):
        left = [_make_claim(confidence=0.3, run_id="l")]
        right = [_make_claim(confidence=0.8, run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = [r.finding for r in results]
        assert DiffFinding.DRIFT in findings

    def test_no_drift_small_change(self):
        left = [_make_claim(confidence=0.8, run_id="l")]
        right = [_make_claim(confidence=0.9, run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = [r.finding for r in results]
        assert DiffFinding.DRIFT not in findings

    def test_waiver_suppresses(self):
        left = [_make_claim(predicate="passed", run_id="l")]
        right = [_make_claim(predicate="failed", run_id="r")]
        waiver = Waiver(
            waiver_id="w1",
            rule_id="contradiction",
            scope="*",
            reason="Known flaky test",
        )
        differ = AG2ClaimDiffer(waivers=[waiver])
        results = differ.diff(left, right, "l", "r")
        assert len(results) == 0

    def test_expired_waiver_does_not_suppress(self):
        left = [_make_claim(predicate="passed", run_id="l")]
        right = [_make_claim(predicate="failed", run_id="r")]
        waiver = Waiver(
            waiver_id="w1",
            rule_id="contradiction",
            scope="*",
            reason="Expired",
            expires=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        )
        differ = AG2ClaimDiffer(waivers=[waiver])
        results = differ.diff(left, right, "l", "r")
        assert any(r.finding == DiffFinding.CONTRADICTION for r in results)

    def test_multiple_findings_per_pair(self):
        """A pair can produce contradiction + unsupported_success."""
        left = [_make_claim(predicate="failed", evidence_refs=["e1"], confidence=0.3, run_id="l")]
        right = [_make_claim(predicate="passed", evidence_refs=["e1"], confidence=0.9, run_id="r")]
        differ = AG2ClaimDiffer()
        results = differ.diff(left, right, "l", "r")
        findings = {r.finding for r in results}
        assert DiffFinding.CONTRADICTION in findings
        assert DiffFinding.UNSUPPORTED_SUCCESS in findings
        assert DiffFinding.DRIFT in findings


# =============================================================================
# ReportGenerator Tests
# =============================================================================


class TestReportGenerator:
    def test_generate_empty(self):
        gen = ReportGenerator()
        report = gen.generate(["r1"], [], [], [])
        assert report.run_ids == ["r1"]
        assert "I5_no_orphan_claims" in report.invariants_satisfied

    def test_generate_with_monotonic_events(self, sample_actor):
        gen = ReportGenerator()
        events = [
            Event(event_id="e1", ts="2024-01-01T00:00:00Z", run_id="r1", kind=EventKind.PROMPT_SENT, actor=sample_actor),
            Event(event_id="e2", ts="2024-01-01T00:01:00Z", run_id="r1", kind=EventKind.MODEL_OUTPUT, actor=sample_actor),
        ]
        report = gen.generate(["r1"], [], events, [])
        assert "I0_append_only" in report.invariants_satisfied

    def test_generate_with_non_monotonic_events(self, sample_actor):
        gen = ReportGenerator()
        events = [
            Event(event_id="e1", ts="2024-01-01T00:01:00Z", run_id="r1", kind=EventKind.PROMPT_SENT, actor=sample_actor),
            Event(event_id="e2", ts="2024-01-01T00:00:00Z", run_id="r1", kind=EventKind.MODEL_OUTPUT, actor=sample_actor),
        ]
        report = gen.generate(["r1"], [], events, [])
        assert "I0_append_only" in report.invariants_violated

    def test_severity_greenfield(self):
        gen = ReportGenerator(InstrumentProfile.GREENFIELD)
        severity = gen._finding_severity(DiffFinding.MISSING_EVIDENCE)
        assert severity == FindingSeverity.WARNING

    def test_severity_strict_upgrade(self):
        gen = ReportGenerator(InstrumentProfile.STRICT)
        severity = gen._finding_severity(DiffFinding.MISSING_EVIDENCE)
        assert severity == FindingSeverity.ERROR

    def test_severity_forensic_upgrade(self):
        gen = ReportGenerator(InstrumentProfile.FORENSIC)
        severity = gen._finding_severity(DiffFinding.DRIFT)
        assert severity == FindingSeverity.WARNING  # info -> warning

    def test_with_diff_results(self):
        gen = ReportGenerator()
        diff = [
            ClaimDiffResult(
                left_run_id="l",
                right_run_id="r",
                finding=DiffFinding.CONTRADICTION,
                match_key="k",
                details="mismatch",
            )
        ]
        report = gen.generate(["l", "r"], [], [], [], diff)
        assert len(report.findings) > 0
        kinds = [f.kind for f in report.findings]
        assert "contradiction" in kinds

    def test_i4_profiles_dont_disable_anchors(self):
        """Even greenfield should report findings (as info/warning), never suppress."""
        gen = ReportGenerator(InstrumentProfile.GREENFIELD)
        # Contradiction is ERROR even in greenfield
        severity = gen._finding_severity(DiffFinding.CONTRADICTION)
        assert severity == FindingSeverity.ERROR


# =============================================================================
# WaiverStore Tests
# =============================================================================


class TestWaiverStore:
    def test_create_and_load(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        w = Waiver(waiver_id="w1", rule_id="r1", scope="*", reason="test")
        store.create(w)
        loaded = store.load("w1")
        assert loaded is not None
        assert loaded.reason == "test"

    def test_load_missing(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        assert store.load("nonexistent") is None

    def test_list_all(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        for i in range(3):
            store.create(Waiver(waiver_id=f"w{i}", rule_id="r1", scope="*", reason=f"reason {i}"))
        assert len(store.list_all()) == 3

    def test_list_active(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        store.create(Waiver(waiver_id="active", rule_id="r1", scope="*", reason="ok"))
        store.create(Waiver(
            waiver_id="expired",
            rule_id="r1",
            scope="*",
            reason="old",
            expires=(datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        ))
        active = store.list_active()
        assert len(active) == 1
        assert active[0].waiver_id == "active"

    def test_empty_store(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        assert store.list_all() == []
        assert store.list_active() == []

    def test_waiver_roundtrip_via_store(self, tmp_gov):
        store = WaiverStore(tmp_gov / "instrument")
        w = Waiver(
            waiver_id="w1",
            rule_id="contradiction",
            scope="src/*.py",
            reason="flaky",
            created_by="admin",
        )
        store.create(w)
        loaded = store.load("w1")
        assert loaded.scope == "src/*.py"
        assert loaded.created_by == "admin"


# =============================================================================
# RunVerifier Tests
# =============================================================================


class TestRunVerifier:
    def test_verify_valid_run(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r1"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r1",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))

        # Write monotonic events
        with open(run_dir / "events.jsonl", "w") as f:
            for i in range(3):
                e = Event(
                    event_id=f"e{i}",
                    ts=f"2024-01-01T00:0{i}:00Z",
                    run_id="r1",
                    kind=EventKind.PROMPT_SENT,
                    actor=sample_actor,
                )
                f.write(e.to_json_line() + "\n")

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert ok
        assert issues == []

    def test_verify_missing_manifest(self, tmp_gov, artifact_store):
        run_dir = tmp_gov / "instrument" / "runs" / "r2"
        run_dir.mkdir(parents=True)
        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert not ok
        assert "manifest.json missing" in issues[0]

    def test_verify_non_monotonic(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r3"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r3",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))

        with open(run_dir / "events.jsonl", "w") as f:
            e1 = Event(event_id="e1", ts="2024-01-01T00:01:00Z", run_id="r3", kind=EventKind.PROMPT_SENT, actor=sample_actor)
            e2 = Event(event_id="e2", ts="2024-01-01T00:00:00Z", run_id="r3", kind=EventKind.PROMPT_SENT, actor=sample_actor)
            f.write(e1.to_json_line() + "\n")
            f.write(e2.to_json_line() + "\n")

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert not ok
        assert any("I0" in issue for issue in issues)

    def test_verify_orphan_claim(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r4"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r4",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))

        # Write a claim that would violate I5 if deserialized
        # We manually write JSON without going through __post_init__
        claim_dict = {
            "claim_id": "c1",
            "ts": "now",
            "run_id": "r4",
            "source": {"kind": "manual"},
            "modality": "assert",
            "type": "test_result",
            "subject": "pytest",
            "predicate": "passed",
            "evidence_refs": [],
        }
        with open(run_dir / "claims.jsonl", "w") as f:
            f.write(json.dumps(claim_dict) + "\n")

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert not ok
        assert any("I5" in issue for issue in issues)

    def test_verify_missing_artifact(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r5"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r5",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))

        receipt = ArtifactReceipt(artifact_hash="nonexistent_hash", size_bytes=0)
        with open(run_dir / "receipts.jsonl", "w") as f:
            f.write(receipt.to_json_line() + "\n")

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert not ok
        assert any("I1" in issue for issue in issues)

    def test_verify_no_events(self, tmp_gov, artifact_store, sample_actor):
        """A run with just a manifest is valid."""
        run_dir = tmp_gov / "instrument" / "runs" / "r6"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r6",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert ok

    def test_verify_corrupt_events(self, tmp_gov, artifact_store, sample_actor):
        run_dir = tmp_gov / "instrument" / "runs" / "r7"
        run_dir.mkdir(parents=True)

        m = RunManifest(
            run_id="r7",
            created_at="2024-01-01T00:00:00Z",
            actor=sample_actor,
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        (run_dir / "manifest.json").write_text(json.dumps(m.to_dict(), indent=2))
        (run_dir / "events.jsonl").write_text("not json\n")

        verifier = RunVerifier(artifact_store)
        ok, issues = verifier.verify(run_dir)
        assert not ok
        assert any("parse error" in issue for issue in issues)


# =============================================================================
# Tool Parser Tests
# =============================================================================


class TestPytestParser:
    def test_pass(self, sample_actor):
        parser = PytestParser()
        event = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 0},
        )
        claims = parser.parse(event, "r1")
        assert len(claims) == 1
        assert claims[0].predicate == "passed"

    def test_fail(self, sample_actor):
        parser = PytestParser()
        event = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 1},
        )
        claims = parser.parse(event, "r1")
        assert claims[0].predicate == "failed"

    def test_no_exit_code(self, sample_actor):
        parser = PytestParser()
        event = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "pytest"},
        )
        claims = parser.parse(event, "r1")
        assert len(claims) == 0


class TestMypyParser:
    def test_pass(self, sample_actor):
        parser = MypyParser()
        event = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "mypy", "exit_code": 0},
        )
        claims = parser.parse(event, "r1")
        assert claims[0].predicate == "passed"
        assert claims[0].type == AG2ClaimType.LINTER_RESULT


class TestRuffParser:
    def test_pass(self, sample_actor):
        parser = RuffParser()
        event = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "ruff", "exit_code": 0},
        )
        claims = parser.parse(event, "r1")
        assert claims[0].predicate == "passed"
        assert claims[0].subject == "ruff"


# =============================================================================
# InstrumentSystem Integration Tests
# =============================================================================


class TestInstrumentSystem:
    def test_start_and_finish_run(self, system):
        manifest, writer = system.start_run()
        assert manifest.run_id
        assert manifest.created_at

        finished = system.finish_run(manifest.run_id)
        assert finished is not None
        assert finished.finished_at != ""

    def test_full_lifecycle(self, system, sample_actor):
        manifest, writer = system.start_run(
            actor=sample_actor,
            profile=InstrumentProfile.STRICT,
            task_id="task-1",
        )

        # Append events
        e1 = Event(
            event_id="e1",
            ts=_now_iso(),
            run_id=manifest.run_id,
            kind=EventKind.TOOL_RESULT,
            actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 0, "output": "passed"},
        )
        writer.append_event(e1)

        e2 = Event(
            event_id="e2",
            ts=_now_iso(),
            run_id=manifest.run_id,
            kind=EventKind.FILE_WRITE,
            actor=sample_actor,
            payload={"path": "main.py"},
        )
        writer.append_event(e2)

        # Finish
        system.finish_run(manifest.run_id)

        # Extract claims
        claims = system.extract_claims(manifest.run_id)
        assert len(claims) >= 2

        # Verify
        ok, issues = system.verify_run(manifest.run_id)
        assert ok, f"Verification failed: {issues}"

        # Report
        report = system.generate_report([manifest.run_id])
        assert report.report_id
        assert manifest.run_id in report.run_ids

    def test_diff_runs(self, system, sample_actor):
        # Run 1: pytest fails
        m1, w1 = system.start_run(actor=sample_actor)
        w1.append_event(Event(
            event_id="e1",
            ts=_now_iso(),
            run_id=m1.run_id,
            kind=EventKind.TOOL_RESULT,
            actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 1},
        ))
        system.finish_run(m1.run_id)
        system.extract_claims(m1.run_id)

        # Run 2: pytest passes (same evidence)
        m2, w2 = system.start_run(actor=sample_actor)
        w2.append_event(Event(
            event_id="e2",
            ts=_now_iso(),
            run_id=m2.run_id,
            kind=EventKind.TOOL_RESULT,
            actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 0},
        ))
        system.finish_run(m2.run_id)
        system.extract_claims(m2.run_id)

        # Diff
        results = system.diff_runs(m1.run_id, m2.run_id)
        findings = {r.finding for r in results}
        assert DiffFinding.CONTRADICTION in findings

    def test_status_overall(self, system, sample_actor):
        manifest, _ = system.start_run(actor=sample_actor)
        system.finish_run(manifest.run_id)

        status = system.status()
        assert status["total_runs"] >= 1

    def test_status_specific_run(self, system, sample_actor):
        manifest, _ = system.start_run(actor=sample_actor)
        system.finish_run(manifest.run_id)

        status = system.status(manifest.run_id)
        assert status["run_id"] == manifest.run_id

    def test_status_missing_run(self, system):
        status = system.status("nonexistent")
        assert "error" in status

    def test_verify_missing_run(self, system):
        ok, issues = system.verify_run("nonexistent")
        assert not ok

    def test_extract_claims_missing_run(self, system):
        claims = system.extract_claims("nonexistent")
        assert claims == []

    def test_generate_report_with_diff(self, system, sample_actor):
        m1, w1 = system.start_run(actor=sample_actor)
        w1.append_event(Event(
            event_id="e1", ts=_now_iso(), run_id=m1.run_id,
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 0},
        ))
        system.finish_run(m1.run_id)
        system.extract_claims(m1.run_id)

        m2, w2 = system.start_run(actor=sample_actor)
        w2.append_event(Event(
            event_id="e2", ts=_now_iso(), run_id=m2.run_id,
            kind=EventKind.TOOL_RESULT, actor=sample_actor,
            payload={"tool": "pytest", "exit_code": 0},
        ))
        system.finish_run(m2.run_id)
        system.extract_claims(m2.run_id)

        report = system.generate_report([m1.run_id], diff_with=m2.run_id)
        assert report.report_id

    def test_report_saved_to_disk(self, system, sample_actor):
        manifest, writer = system.start_run(actor=sample_actor)
        system.finish_run(manifest.run_id)
        system.extract_claims(manifest.run_id)

        report = system.generate_report([manifest.run_id])

        reports_dir = system.instrument_dir / "runs" / manifest.run_id / "reports"
        assert (reports_dir / "report.json").exists()
        assert (reports_dir / "report.md").exists()

    def test_start_run_with_models(self, system, sample_actor):
        models = [ModelSpec("claude", "anthropic", "3.5")]
        manifest, _ = system.start_run(actor=sample_actor, models=models)
        assert len(manifest.models) == 1
        assert manifest.models[0].name == "claude"


# =============================================================================
# Serialization Roundtrip Tests
# =============================================================================


class TestSerializationRoundtrips:
    def test_event_roundtrip(self, sample_actor):
        e = Event(
            event_id="e1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            kind=EventKind.GIT_DIFF,
            actor=sample_actor,
            parent_event_id="e0",
            payload={"diff": "+line"},
            receipt_refs=["h1", "h2"],
        )
        line = e.to_json_line()
        e2 = Event.from_dict(json.loads(line))
        assert e2.event_id == e.event_id
        assert e2.parent_event_id == "e0"
        assert e2.receipt_refs == ["h1", "h2"]

    def test_claim_roundtrip(self):
        c = AG2Claim(
            claim_id="c1",
            ts="2024-01-01T00:00:00Z",
            run_id="r1",
            source=ClaimSource(kind="tool_parser", event_id="e1", model="m1"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.BUILD_RESULT,
            subject="cargo",
            predicate="passed",
            object="release",
            scope=ClaimScope(repo_sha="abc", command="cargo build"),
            evidence_refs=["e1"],
            confidence=0.95,
            notes="Clean build",
        )
        d = c.to_dict()
        c2 = AG2Claim.from_dict(d)
        assert c2.claim_id == c.claim_id
        assert c2.object == "release"
        assert c2.scope.repo_sha == "abc"
        assert c2.notes == "Clean build"

    def test_report_roundtrip(self):
        r = AG2Report(
            report_id="rpt1",
            run_ids=["r1"],
            generated_at="2024-01-01T00:00:00Z",
            findings=[
                ReportFinding(
                    kind="I0",
                    severity=FindingSeverity.ERROR,
                    claim_refs=["c1"],
                    evidence_refs=["e1"],
                    summary="Timestamp regression",
                ),
            ],
            invariants_satisfied=["I1", "I3"],
            invariants_violated=["I0"],
            provenance=ReportProvenance(spec_version="v1", generator_version="0.1"),
        )
        d = r.to_dict()
        r2 = AG2Report.from_dict(d)
        assert r2.report_id == "rpt1"
        assert len(r2.findings) == 1
        assert r2.provenance.spec_version == "v1"

    def test_manifest_full_roundtrip(self):
        m = RunManifest(
            run_id="full",
            created_at="2024-01-01T00:00:00Z",
            finished_at="2024-01-01T01:00:00Z",
            actor=Actor(ActorKind.AGENT, "a1", "Agent One"),
            environment=Environment("Linux", "host", "/work", "+0100"),
            repo=RepoState("git@gh", "deadbeef", "feature", True),
            config=RunConfig(InstrumentProfile.FORENSIC, "anchors_h", {"py": "3.12"}),
            inputs=RunInputs("task-42", "prompt_h", 7),
            models=[ModelSpec("gpt-4", "openai", "0613", "param_h")],
            event_count=10,
            receipt_count=3,
            claim_count=5,
        )
        d = m.to_dict()
        m2 = RunManifest.from_dict(d)
        assert m2.run_id == "full"
        assert m2.actor.name == "Agent One"
        assert m2.repo.dirty is True
        assert m2.config.toolchain_versions == {"py": "3.12"}
        assert m2.inputs.seed == 7
        assert m2.event_count == 10

    def test_waiver_roundtrip(self):
        w = Waiver(
            waiver_id="w1",
            rule_id="contradiction",
            scope="src/*.py",
            reason="Flaky test",
            expires="2025-01-01T00:00:00Z",
            created_by="admin",
        )
        d = w.to_dict()
        w2 = Waiver.from_dict(d)
        assert w2.waiver_id == "w1"
        assert w2.created_by == "admin"

    def test_claim_diff_result_roundtrip(self):
        c = _make_claim()
        r = ClaimDiffResult(
            left_run_id="l",
            right_run_id="r",
            finding=DiffFinding.PHANTOM_ACTION,
            match_key="k",
            left_claim=c,
            details="orphan",
        )
        d = r.to_dict()
        r2 = ClaimDiffResult.from_dict(d)
        assert r2.finding == DiffFinding.PHANTOM_ACTION
        assert r2.left_claim is not None

    def test_config_roundtrip(self):
        c = InstrumentConfig(
            profile=InstrumentProfile.STRICT,
            auto_extract_claims=False,
            artifact_size_threshold=2048,
        )
        d = c.to_dict()
        c2 = InstrumentConfig.from_dict(d)
        assert c2.profile == InstrumentProfile.STRICT
        assert c2.artifact_size_threshold == 2048

    def test_diff_result_null_claims(self):
        r = ClaimDiffResult(
            left_run_id="l",
            right_run_id="r",
            finding=DiffFinding.DRIFT,
            match_key="k",
        )
        d = r.to_dict()
        assert d["left_claim"] is None
        r2 = ClaimDiffResult.from_dict(d)
        assert r2.left_claim is None
        assert r2.right_claim is None


# =============================================================================
# Golden-file / Schema Tests
# =============================================================================


class TestGoldenSchemas:
    def test_manifest_schema(self):
        m = RunManifest(
            run_id="test",
            created_at="2024-01-01T00:00:00Z",
            actor=Actor(ActorKind.HUMAN, "u1"),
            environment=Environment("L", "h", "/", "Z"),
            config=RunConfig(InstrumentProfile.GREENFIELD),
        )
        d = m.to_dict()
        required_keys = {"run_id", "created_at", "finished_at", "actor", "environment", "config", "inputs", "models", "event_count", "receipt_count", "claim_count"}
        assert required_keys <= set(d.keys())

    def test_event_schema(self, sample_actor):
        e = Event(
            event_id="e1", ts="now", run_id="r1",
            kind=EventKind.PROMPT_SENT, actor=sample_actor,
        )
        d = e.to_dict()
        required_keys = {"event_id", "ts", "run_id", "kind", "actor", "parent_event_id", "payload", "receipt_refs"}
        assert required_keys <= set(d.keys())

    def test_claim_schema(self):
        c = AG2Claim(
            claim_id="c1", ts="now", run_id="r1",
            source=ClaimSource(kind="manual"),
            modality=ClaimModality.ASSERT,
            type=AG2ClaimType.TEST_RESULT,
            subject="s", predicate="p",
            evidence_refs=["e1"],
        )
        d = c.to_dict()
        required_keys = {"claim_id", "ts", "run_id", "source", "modality", "type", "subject", "predicate", "object", "scope", "evidence_refs", "confidence", "notes"}
        assert required_keys <= set(d.keys())

    def test_report_schema(self):
        r = AG2Report(
            report_id="rpt1", run_ids=["r1"], generated_at="now",
        )
        d = r.to_dict()
        required_keys = {"report_id", "run_ids", "generated_at", "findings", "invariants_satisfied", "invariants_violated", "provenance"}
        assert required_keys <= set(d.keys())

    def test_artifact_receipt_schema(self):
        r = ArtifactReceipt(artifact_hash="h", size_bytes=0)
        d = r.to_dict()
        required_keys = {"artifact_hash", "size_bytes", "mime_type", "stored_at"}
        assert required_keys <= set(d.keys())


# =============================================================================
# Helper Function Tests
# =============================================================================


class TestHelpers:
    def test_make_run_id_format(self):
        rid = _make_run_id()
        assert len(rid) == 12
        assert all(c in "0123456789abcdef" for c in rid)

    def test_make_run_id_unique(self):
        ids = {_make_run_id() for _ in range(100)}
        assert len(ids) == 100

    def test_now_iso_format(self):
        ts = _now_iso()
        # Should be parseable
        dt = datetime.fromisoformat(ts)
        assert dt.tzinfo is not None

    def test_count_jsonl(self, tmp_path):
        path = tmp_path / "test.jsonl"
        path.write_text('{"a":1}\n{"b":2}\n\n{"c":3}\n')
        assert _count_jsonl(path) == 3

    def test_count_jsonl_missing(self, tmp_path):
        assert _count_jsonl(tmp_path / "nonexistent.jsonl") == 0

    def test_count_jsonl_empty(self, tmp_path):
        path = tmp_path / "empty.jsonl"
        path.write_text("")
        assert _count_jsonl(path) == 0
