# SPDX-License-Identifier: Apache-2.0
"""Cargo/rustc failure-triage driver (Slice 0).

Pure pieces (diagnostic splitting, orchestration) under deterministic fakes — no
cargo, no model, no network. run_cargo (the subprocess seam) is exercised live, not
here.
"""

from __future__ import annotations

import json

from governor.cargo_triage import (
    CargoRunResult,
    CargoTriageReport,
    split_diagnostics,
    triage_cargo_result,
)
from governor.local_candidate import CANDIDATE_OBSERVED

_MODEL = "qwen2.5-coder:7b"

_GOOD = json.dumps(
    {
        "failure_kind": "borrow_of_moved_value",
        "likely_files": ["src/main.rs"],
        "next_action": "clone the value or borrow instead of moving",
        "confidence": "high",
        "authority_claims": [],
    }
)

_TWO_ERRORS = """\
   Compiling demo v0.1.0 (/x/demo)
error[E0382]: borrow of moved value: `s`
 --> src/main.rs:4:20
  |
3 |     let _s2 = s;
  |               - value moved here
4 |     println!("{}", s);
  |                    ^ value borrowed here after move

error[E0308]: mismatched types
 --> src/main.rs:8:18
  |
8 |     let _x: i32 = "nope";
  |             ---   ^^^^^^ expected `i32`, found `&str`

error: aborting due to 2 previous errors
"""

_TEST_FAILURE = """\
running 1 test
test t_math ... FAILED
failures:
---- t_math stdout ----
thread 't_math' panicked at 'assertion failed: `(left == right)`
  left: `4`, right: `5`', src/lib.rs:2:14
"""


class _FixedClient:
    def __init__(self, out=_GOOD):
        self.calls = 0
        self._out = out

    def complete(self, prompt: str) -> str:
        self.calls += 1
        return self._out


def _cargo(exit_code: int, transcript: str) -> CargoRunResult:
    return CargoRunResult(
        command=("cargo", "check"),
        cwd="/x/demo",
        rustc_version="rustc 1.94.0",
        cargo_version="cargo 1.94.0",
        target_triple="aarch64-apple-darwin",
        exit_code=exit_code,
        transcript=transcript,
    )


# --------------------------------------------------------------------------- #
# split_diagnostics.
# --------------------------------------------------------------------------- #


class TestSplit:
    def test_splits_per_error(self):
        chunks = split_diagnostics(_TWO_ERRORS)
        # two error[Exxxx] + the trailing "error: aborting" = 3 boundaries.
        assert len(chunks) == 3
        assert chunks[0].startswith("error[E0382]")
        assert chunks[1].startswith("error[E0308]")
        assert all(c.strip() for c in chunks)

    def test_no_boundary_is_single_chunk(self):
        chunks = split_diagnostics(_TEST_FAILURE)
        assert len(chunks) == 1
        assert "panicked" in chunks[0]

    def test_empty_is_no_chunks(self):
        assert split_diagnostics("   ") == []

    def test_chunk_count_bounded(self):
        big = "\n".join(f"error[E0001]: e{i}\n detail" for i in range(50))
        assert len(split_diagnostics(big, max_diagnostics=5)) == 5


# --------------------------------------------------------------------------- #
# triage_cargo_result orchestration.
# --------------------------------------------------------------------------- #


class TestOrchestration:
    def test_clean_run_yields_no_triage(self):
        client = _FixedClient()
        report = triage_cargo_result(_cargo(0, ""), model=_MODEL, client=client)
        assert report.diagnostics_found == 0
        assert report.receipts == ()
        assert client.calls == 0  # nothing to triage on a green run

    def test_each_diagnostic_triaged(self):
        client = _FixedClient()
        report = triage_cargo_result(_cargo(101, _TWO_ERRORS), model=_MODEL, client=client)
        # 3 diagnostics (2 errors + aborting line) each get a candidate.
        assert report.diagnostics_found == 3
        assert len(report.receipts) == 3
        assert report.observed == 3
        assert all(r.verdict == CANDIDATE_OBSERVED for r in report.receipts)

    def test_truncation_flagged(self):
        client = _FixedClient()
        report = triage_cargo_result(
            _cargo(101, _TWO_ERRORS), model=_MODEL, client=client, max_diagnostics=1
        )
        assert report.diagnostics_found == 3
        assert len(report.receipts) == 1
        assert report.truncated is True

    def test_authority_claim_in_diagnostic_still_refused(self):
        bad = json.dumps(
            {
                "failure_kind": "x",
                "likely_files": [],
                "next_action": "y",
                "confidence": "low",
                "authority_claims": ["safe_to_commit"],
            }
        )
        client = _FixedClient(out=bad)
        report = triage_cargo_result(_cargo(101, _TWO_ERRORS), model=_MODEL, client=client)
        # discipline carried from the worker: every receipt is a refusal.
        assert all(r.verdict != CANDIDATE_OBSERVED for r in report.receipts)

    def test_report_is_a_report_not_an_authority(self):
        report = triage_cargo_result(_cargo(101, _TWO_ERRORS), model=_MODEL, client=_FixedClient())
        assert isinstance(report, CargoTriageReport)
        # no method that claims the build/port works, applies, or commits.
        for forbidden in ("apply", "commit", "promote", "port_works", "succeed"):
            assert not hasattr(report, forbidden)
