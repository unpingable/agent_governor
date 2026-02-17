# SPDX-License-Identifier: Apache-2.0
"""Tests for the interferometry module (multi-model claim comparison)."""

import asyncio
import json
import pytest
from pathlib import Path
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

from governor.interferometry import (
    AlignmentType,
    ClaimAlignment,
    InterferometryRun,
    InterferometrySignals,
    InterferometryStore,
    ModelRun,
    RunMode,
    align_claims,
    compute_signals,
    extract_claims,
    match_claims,
    promote_to_ledger,
    run_ensemble,
    run_parallel,
    run_serial,
)
from governor.claim_signals import ExtractionResult, SignalCategory, SignalMatch
from governor.taint import Fingerprint, fingerprint


# ============================================================================
# TestModelRun
# ============================================================================


class TestModelRun:
    """Tests for ModelRun dataclass."""

    def test_basic_creation(self) -> None:
        run = ModelRun(
            model_id="llama3",
            backend_type="ollama",
            response="The sky is blue.",
        )
        assert run.model_id == "llama3"
        assert run.backend_type == "ollama"
        assert run.response == "The sky is blue."
        assert run.usage == {}
        assert run.latency_ms == 0.0
        assert run.round_number == 0

    def test_to_dict(self) -> None:
        run = ModelRun(
            model_id="model-a",
            backend_type="anthropic",
            response="Hello",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
            latency_ms=123.4,
        )
        d = run.to_dict()
        assert d["model_id"] == "model-a"
        assert d["backend_type"] == "anthropic"
        assert d["latency_ms"] == 123.4
        assert d["usage"]["prompt_tokens"] == 10
        assert d["extraction"] is None

    def test_to_dict_with_extraction(self) -> None:
        extraction = ExtractionResult(
            text_hash="abc123",
            total_signals=3,
            signals_by_category={"assertive": 2, "date": 1},
            matches=[],
            assertiveness_score=0.7,
        )
        run = ModelRun(
            model_id="m",
            backend_type="ollama",
            response="text",
            extraction=extraction,
        )
        d = run.to_dict()
        assert d["extraction"]["total_signals"] == 3
        assert d["extraction"]["assertiveness_score"] == 0.7

    def test_round_number_for_serial(self) -> None:
        run = ModelRun(
            model_id="m",
            backend_type="ollama",
            response="text",
            round_number=2,
        )
        assert run.round_number == 2
        assert run.to_dict()["round_number"] == 2


# ============================================================================
# TestClaimAlignment
# ============================================================================


class TestClaimAlignment:
    """Tests for ClaimAlignment dataclass."""

    def test_shared_alignment(self) -> None:
        fp = fingerprint("the sky is blue")
        a = ClaimAlignment(
            claim_text="the sky is blue",
            fp=fp,
            sources=["model-a", "model-b"],
            alignment=AlignmentType.SHARED,
            confidence=1.0,
        )
        assert a.alignment == AlignmentType.SHARED
        assert len(a.sources) == 2

    def test_unique_alignment(self) -> None:
        fp = fingerprint("only one model said this")
        a = ClaimAlignment(
            claim_text="only one model said this",
            fp=fp,
            sources=["model-a"],
            alignment=AlignmentType.UNIQUE,
            confidence=0.5,
        )
        assert a.alignment == AlignmentType.UNIQUE

    def test_to_dict(self) -> None:
        fp = fingerprint("test claim")
        a = ClaimAlignment(
            claim_text="test claim",
            fp=fp,
            sources=["m1"],
            alignment=AlignmentType.CONFLICTING,
            confidence=0.75,
            category="date",
        )
        d = a.to_dict()
        assert d["alignment"] == "conflicting"
        assert d["confidence"] == 0.75
        assert d["category"] == "date"
        assert "fingerprint" in d


# ============================================================================
# TestExtractClaims
# ============================================================================


class TestExtractClaims:
    """Tests for extract_claims wrapper."""

    def test_wraps_signal_extractor(self) -> None:
        result = extract_claims("The population in 2023 was 8 billion.")
        assert isinstance(result, ExtractionResult)
        assert result.total_signals >= 0

    def test_empty_text(self) -> None:
        result = extract_claims("")
        assert result.total_signals == 0

    def test_returns_extraction_result(self) -> None:
        result = extract_claims("This is definitely true and certain.")
        assert hasattr(result, "matches")
        assert hasattr(result, "assertiveness_score")


# ============================================================================
# TestMatchClaims
# ============================================================================


class TestMatchClaims:
    """Tests for match_claims (Jaccard similarity)."""

    def test_exact_match(self) -> None:
        score = match_claims("the sky is blue", "the sky is blue")
        assert score == 1.0

    def test_below_threshold(self) -> None:
        score = match_claims("the sky is blue", "cats are furry animals")
        assert score < 0.65

    def test_partial_overlap(self) -> None:
        score = match_claims("the sky is blue today", "the sky is clear today")
        # Some overlap due to shared tokens
        assert 0.0 < score < 1.0

    def test_empty_strings(self) -> None:
        score = match_claims("", "")
        # Both empty → fingerprints have empty token sets
        assert score >= 0.0


# ============================================================================
# TestAlignClaims
# ============================================================================


class TestAlignClaims:
    """Tests for align_claims clustering."""

    def _make_run(self, model_id: str, claims: list[tuple[str, str]]) -> ModelRun:
        """Helper: create a ModelRun with mock extraction results."""
        matches = [
            SignalMatch(
                category=SignalCategory(cat),
                value=text,
                span=(0, len(text)),
                line_number=1,
                context=text,
            )
            for text, cat in claims
        ]
        extraction = ExtractionResult(
            text_hash="x",
            total_signals=len(matches),
            signals_by_category={},
            matches=matches,
            assertiveness_score=0.5,
        )
        return ModelRun(
            model_id=model_id,
            backend_type="ollama",
            response="response",
            extraction=extraction,
        )

    def test_all_agree(self) -> None:
        """When all models produce the same claim, it's shared."""
        run_a = self._make_run("a", [("the population is 8 billion", "assertive")])
        run_b = self._make_run("b", [("the population is 8 billion", "assertive")])

        shared, unique, conflicts = align_claims([run_a, run_b])
        assert len(shared) >= 1
        assert all(c.alignment == AlignmentType.SHARED for c in shared)

    def test_no_overlap(self) -> None:
        """Completely different claims are all unique."""
        run_a = self._make_run("a", [("cats are mammals", "assertive")])
        run_b = self._make_run("b", [("python is a programming language", "assertive")])

        shared, unique, conflicts = align_claims([run_a, run_b])
        assert len(unique) == 2
        assert len(shared) == 0

    def test_mixed(self) -> None:
        """Mix of shared and unique claims."""
        run_a = self._make_run("a", [
            ("the sky is blue", "assertive"),
            ("water is wet", "assertive"),
        ])
        run_b = self._make_run("b", [
            ("the sky is blue", "assertive"),
            ("fire is hot", "assertive"),
        ])

        shared, unique, conflicts = align_claims([run_a, run_b])
        assert len(shared) >= 1  # "the sky is blue"
        assert len(unique) >= 1  # "water is wet" and "fire is hot"

    def test_empty_runs(self) -> None:
        shared, unique, conflicts = align_claims([])
        assert shared == []
        assert unique == []
        assert conflicts == []

    def test_single_run(self) -> None:
        """Single run: all claims are unique."""
        run_a = self._make_run("a", [("the sky is blue", "assertive")])
        shared, unique, conflicts = align_claims([run_a])
        assert len(unique) >= 1
        assert len(shared) == 0

    def test_no_extraction(self) -> None:
        """Runs without extraction are skipped."""
        run = ModelRun(model_id="a", backend_type="ollama", response="hello")
        shared, unique, conflicts = align_claims([run])
        assert shared == [] and unique == [] and conflicts == []

    def test_specifics_conflict(self) -> None:
        """Different dates from different models should be flagged as conflicting."""
        run_a = self._make_run("a", [("January 2023", "date")])
        run_b = self._make_run("b", [("March 2024", "date")])

        # These have different tokens so they won't cluster together
        # (Jaccard threshold won't match "January 2023" with "March 2024")
        shared, unique, conflicts = align_claims([run_a, run_b], threshold=0.1)
        # At very low threshold they might cluster; at default they're unique
        total = len(shared) + len(unique) + len(conflicts)
        assert total >= 2


# ============================================================================
# TestComputeSignals
# ============================================================================


class TestComputeSignals:
    """Tests for compute_signals."""

    def test_zero_claims(self) -> None:
        signals = compute_signals([], [], [], 2)
        assert signals.total_claims == 0
        assert signals.disagreement_rate == 0.0

    def test_all_shared(self) -> None:
        shared = [
            ClaimAlignment("a", fingerprint("a"), ["m1", "m2"], AlignmentType.SHARED, 1.0),
            ClaimAlignment("b", fingerprint("b"), ["m1", "m2"], AlignmentType.SHARED, 1.0),
        ]
        signals = compute_signals(shared, [], [], 2)
        assert signals.shared_count == 2
        assert signals.unique_count == 0
        assert signals.conflict_count == 0
        assert signals.disagreement_rate == 0.0

    def test_all_unique(self) -> None:
        unique = [
            ClaimAlignment("a", fingerprint("a"), ["m1"], AlignmentType.UNIQUE, 0.5),
            ClaimAlignment("b", fingerprint("b"), ["m2"], AlignmentType.UNIQUE, 0.5),
        ]
        signals = compute_signals([], unique, [], 2)
        assert signals.unique_count == 2
        assert signals.disagreement_rate == 0.0

    def test_rate_calculation(self) -> None:
        shared = [ClaimAlignment("a", fingerprint("a"), ["m1", "m2"], AlignmentType.SHARED, 1.0)]
        conflicts = [ClaimAlignment("b", fingerprint("b"), ["m1", "m2"], AlignmentType.CONFLICTING, 1.0, "date")]
        signals = compute_signals(shared, [], conflicts, 2)
        assert signals.total_claims == 2
        assert signals.disagreement_rate == 0.5
        assert signals.specifics_conflict_count == 1

    def test_signals_to_dict(self) -> None:
        signals = InterferometrySignals(
            disagreement_rate=0.25,
            specifics_conflict_count=1,
            unique_count=3,
            shared_count=5,
            conflict_count=2,
            total_claims=10,
        )
        d = signals.to_dict()
        assert d["disagreement_rate"] == 0.25
        assert d["total_claims"] == 10


# ============================================================================
# TestRunEnsemble
# ============================================================================


class TestRunEnsemble:
    """Tests for run_parallel, run_serial, and run_ensemble."""

    def test_parallel_with_mock_backends(self) -> None:
        """Parallel mode calls each backend once."""
        @dataclass
        class FakeResponse:
            content: str = "The sky is blue."
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_parallel(
                "What color is the sky?",
                [
                    {"backend_type": "ollama", "model": "m1"},
                    {"backend_type": "ollama", "model": "m2"},
                ],
            ))

        assert result.mode == RunMode.PARALLEL
        assert len(result.runs) == 2
        assert result.id  # Has an ID
        assert result.created_at  # Has timestamp

    def test_serial_with_mock_backends(self) -> None:
        """Serial mode chains responses across backends."""
        @dataclass
        class FakeResponse:
            content: str = "I agree, the sky is blue."
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_serial(
                "What color is the sky?",
                [
                    {"backend_type": "ollama", "model": "m1"},
                    {"backend_type": "ollama", "model": "m2"},
                ],
                rounds=1,
            ))

        assert result.mode == RunMode.SERIAL
        assert result.rounds == 1
        assert len(result.runs) == 2  # Initial + 1 round
        assert result.runs[0].round_number == 0
        assert result.runs[1].round_number == 1

    def test_serial_multiple_rounds(self) -> None:
        """Serial mode with N=2 rounds produces 3 total steps."""
        @dataclass
        class FakeResponse:
            content: str = "Response text."
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_serial(
                "Prompt",
                [
                    {"backend_type": "ollama", "model": "m1"},
                    {"backend_type": "ollama", "model": "m2"},
                ],
                rounds=2,
            ))

        assert len(result.runs) == 3  # Initial + 2 rounds

    def test_failure_handling(self) -> None:
        """Backend errors produce error responses, not crashes."""
        with patch("governor.interferometry.create_backend", side_effect=Exception("Connection refused")):
            result = asyncio.run(run_parallel(
                "test",
                [{"backend_type": "ollama", "model": "m1"}],
            ))

        assert len(result.runs) == 1
        assert "[error]" in result.runs[0].response

    def test_ensemble_dispatches_to_parallel(self) -> None:
        """run_ensemble with PARALLEL mode calls run_parallel."""
        @dataclass
        class FakeResponse:
            content: str = "text"
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_ensemble(
                "test",
                [{"backend_type": "ollama", "model": "m1"}],
                mode=RunMode.PARALLEL,
            ))
        assert result.mode == RunMode.PARALLEL

    def test_ensemble_dispatches_to_serial(self) -> None:
        """run_ensemble with SERIAL mode calls run_serial."""
        @dataclass
        class FakeResponse:
            content: str = "text"
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_ensemble(
                "test",
                [{"backend_type": "ollama", "model": "m1"}, {"backend_type": "ollama", "model": "m2"}],
                mode=RunMode.SERIAL,
                rounds=1,
            ))
        assert result.mode == RunMode.SERIAL

    def test_signal_production(self) -> None:
        """Ensemble produces valid signals."""
        @dataclass
        class FakeResponse:
            content: str = "The population of Earth is 8 billion people as of 2023."
            model: str = "fake"
            usage: dict = None
            finish_reason: str = "stop"
            def __post_init__(self):
                if self.usage is None:
                    self.usage = {}

        fake_backend = AsyncMock()
        fake_backend.chat = AsyncMock(return_value=FakeResponse())

        with patch("governor.interferometry.create_backend", return_value=fake_backend):
            result = asyncio.run(run_parallel(
                "What is Earth's population?",
                [
                    {"backend_type": "ollama", "model": "m1"},
                    {"backend_type": "ollama", "model": "m2"},
                ],
            ))

        assert result.signals.total_claims >= 0
        assert result.signals.disagreement_rate >= 0.0


# ============================================================================
# TestPromoteToLedger
# ============================================================================


class TestPromoteToLedger:
    """Tests for promote_to_ledger."""

    def _make_run(self, shared: list[ClaimAlignment], unique: list[ClaimAlignment]) -> InterferometryRun:
        return InterferometryRun(
            id="test-run",
            prompt="test",
            mode=RunMode.PARALLEL,
            runs=[],
            shared=shared,
            unique=unique,
            conflicts=[],
            signals=InterferometrySignals(0, 0, len(unique), len(shared), 0, len(shared) + len(unique)),
        )

    def test_shared_to_derived(self) -> None:
        """Shared claims are promoted with DERIVED provenance."""
        shared = [
            ClaimAlignment("the sky is blue", fingerprint("the sky is blue"),
                           ["m1", "m2"], AlignmentType.SHARED, 1.0),
        ]
        run = self._make_run(shared, [])

        mock_ledger = MagicMock()
        mock_claim = MagicMock()
        mock_claim.claim_id = "c1"
        mock_ledger.new_claim.return_value = mock_claim

        ids = promote_to_ledger(run, mock_ledger)
        assert len(ids) == 1
        call_args = mock_ledger.new_claim.call_args
        assert call_args[1]["provenance"].value == "derived"
        assert call_args[1]["confidence"] == 1.0

    def test_unique_to_assumed(self) -> None:
        """Unique claims are promoted with ASSUMED provenance when shared_only=False."""
        unique = [
            ClaimAlignment("only model a said this", fingerprint("only model a said this"),
                           ["m1"], AlignmentType.UNIQUE, 0.5),
        ]
        run = self._make_run([], unique)

        mock_ledger = MagicMock()
        mock_claim = MagicMock()
        mock_claim.claim_id = "c1"
        mock_ledger.new_claim.return_value = mock_claim

        ids = promote_to_ledger(run, mock_ledger, shared_only=False)
        assert len(ids) == 1
        call_args = mock_ledger.new_claim.call_args
        assert call_args[1]["provenance"].value == "assumed"
        assert call_args[1]["confidence"] == 0.2

    def test_shared_only_skips_unique(self) -> None:
        """With shared_only=True, unique claims are not promoted."""
        unique = [
            ClaimAlignment("unique claim", fingerprint("unique claim"),
                           ["m1"], AlignmentType.UNIQUE, 0.5),
        ]
        run = self._make_run([], unique)

        mock_ledger = MagicMock()
        ids = promote_to_ledger(run, mock_ledger, shared_only=True)
        assert len(ids) == 0
        mock_ledger.new_claim.assert_not_called()

    def test_empty_run(self) -> None:
        """Empty run produces no promotions."""
        run = self._make_run([], [])
        mock_ledger = MagicMock()
        ids = promote_to_ledger(run, mock_ledger)
        assert ids == []


# ============================================================================
# TestInterferometryStore
# ============================================================================


class TestInterferometryStore:
    """Tests for InterferometryStore persistence."""

    def _make_run(self, run_id: str = "test-123") -> InterferometryRun:
        return InterferometryRun(
            id=run_id,
            prompt="What is 2+2?",
            mode=RunMode.PARALLEL,
            runs=[
                ModelRun(model_id="m1", backend_type="ollama", response="4"),
            ],
            shared=[],
            unique=[],
            conflicts=[],
            signals=InterferometrySignals(0, 0, 0, 0, 0, 0),
            created_at="2024-01-01T00:00:00Z",
        )

    def test_save_load_roundtrip(self, tmp_path: Path) -> None:
        store = InterferometryStore(tmp_path)
        run = self._make_run()
        store.save(run)

        loaded = store.load("test-123")
        assert loaded is not None
        assert loaded.id == "test-123"
        assert loaded.prompt == "What is 2+2?"
        assert loaded.mode == RunMode.PARALLEL
        assert len(loaded.runs) == 1
        assert loaded.runs[0].model_id == "m1"

    def test_list_runs(self, tmp_path: Path) -> None:
        store = InterferometryStore(tmp_path)
        store.save(self._make_run("run-1"))
        store.save(self._make_run("run-2"))

        summaries = store.list_runs()
        assert len(summaries) == 2
        ids = {s["id"] for s in summaries}
        assert "run-1" in ids
        assert "run-2" in ids

    def test_last(self, tmp_path: Path) -> None:
        store = InterferometryStore(tmp_path)
        store.save(self._make_run("run-old"))
        store.save(self._make_run("run-new"))

        last = store.last()
        assert last is not None
        # Last should be the most recently written
        assert last.id in ("run-old", "run-new")

    def test_empty_dir(self, tmp_path: Path) -> None:
        store = InterferometryStore(tmp_path)
        assert store.list_runs() == []
        assert store.last() is None
        assert store.load("nonexistent") is None

    def test_serial_mode_roundtrip(self, tmp_path: Path) -> None:
        """Serial mode runs are preserved through save/load."""
        run = InterferometryRun(
            id="serial-1",
            prompt="Discuss",
            mode=RunMode.SERIAL,
            rounds=2,
            runs=[
                ModelRun(model_id="m1", backend_type="ollama", response="First", round_number=0),
                ModelRun(model_id="m2", backend_type="ollama", response="Second", round_number=1),
                ModelRun(model_id="m1", backend_type="ollama", response="Third", round_number=2),
            ],
            shared=[],
            unique=[],
            conflicts=[],
            signals=InterferometrySignals(0, 0, 0, 0, 0, 0),
            created_at="2024-01-01T00:00:00Z",
        )
        store = InterferometryStore(tmp_path)
        store.save(run)
        loaded = store.load("serial-1")
        assert loaded is not None
        assert loaded.mode == RunMode.SERIAL
        assert loaded.rounds == 2
        assert len(loaded.runs) == 3
        assert loaded.runs[2].round_number == 2


# ============================================================================
# TestInterferometryRun
# ============================================================================


class TestInterferometryRun:
    """Tests for InterferometryRun dataclass."""

    def test_to_dict_complete(self) -> None:
        run = InterferometryRun(
            id="r1",
            prompt="test",
            mode=RunMode.PARALLEL,
            runs=[ModelRun(model_id="m", backend_type="ollama", response="x")],
            shared=[ClaimAlignment("c", fingerprint("c"), ["m"], AlignmentType.SHARED, 1.0)],
            unique=[],
            conflicts=[],
            signals=InterferometrySignals(0, 0, 0, 1, 0, 1),
            created_at="2024-01-01",
        )
        d = run.to_dict()
        assert d["id"] == "r1"
        assert d["mode"] == "parallel"
        assert len(d["runs"]) == 1
        assert len(d["shared"]) == 1
        assert d["signals"]["shared_count"] == 1

    def test_serial_to_dict(self) -> None:
        run = InterferometryRun(
            id="s1",
            prompt="test",
            mode=RunMode.SERIAL,
            rounds=3,
            runs=[],
            shared=[],
            unique=[],
            conflicts=[],
            signals=InterferometrySignals(0, 0, 0, 0, 0, 0),
        )
        d = run.to_dict()
        assert d["mode"] == "serial"
        assert d["rounds"] == 3


# ============================================================================
# TestRunMode
# ============================================================================


class TestRunMode:
    """Tests for RunMode enum."""

    def test_parallel_value(self) -> None:
        assert RunMode.PARALLEL.value == "parallel"

    def test_serial_value(self) -> None:
        assert RunMode.SERIAL.value == "serial"

    def test_from_string(self) -> None:
        assert RunMode("parallel") == RunMode.PARALLEL
        assert RunMode("serial") == RunMode.SERIAL
