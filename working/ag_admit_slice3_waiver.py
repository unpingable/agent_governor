# SPDX-License-Identifier: Apache-2.0
"""
Slice 3 dogfood — run the REAL waiver-completeness packet through the ag_admit loop.

This is the first AG-on-AG slice, authorized by
``working/promotion-ag-admit-to-waiver-completeness.md`` for EXACTLY ONE packet.

It demonstrates two honest things and then stops:
  1. The packet's declared §2 path surface flows through the SAME loop (real
     DiffPathScopeGate + dumb conductor): an in-scope change ADMITs, an out-of-scope
     change (§3-forbidden file) is REJECTed on observed paths.
  2. Executing acceptance criterion 2 requires a closed-receipt-enum decision
     (VALID_NON_DISCHARGE_KINDS) — a forbidden surface — so the campaign STOPS with
     NEEDS_HUMAN. The path gate cannot adjudicate that; it is a human boundary.

Exit code: 2 = "stopped for human" (not 0=clean, not 1=error). Receipts under
working/slice3_receipts/.
"""

from __future__ import annotations

import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE))

import ag_admit_conductor  # noqa: E402
from governor.ag_admit import CandidateStep, DiffPathScopeGate, StepVerdict  # noqa: E402
from governor.gate_receipt import GateReceiptSystem  # noqa: E402

# The packet's §2 path allowlist = the grant (exact paths; no globs widen it).
WAIVER_PACKET_SCOPE: tuple[str, ...] = (
    "src/governor/overrides.py",
    "src/governor/admissibility.py",
    "src/governor/gate_receipt.py",
    "tests/test_overrides.py",
    "tests/test_admissibility.py",
    "tests/test_waiver_admission_completeness.py",
    "src/governor/constraint_compiler.py",  # the one consumer read-path candidate
)


def _diff(path: str) -> str:
    return (
        f"diff --git a/{path} b/{path}\n"
        f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-old\n+new\n"
    )


def _step(step_id: str, path: str) -> CandidateStep:
    return CandidateStep(
        step_id=step_id,
        repo="agent_gov",
        base_commit="HEAD",
        diff=_diff(path),
        declared_intent="waiver-completeness: no silent override path",
        scope="; ".join(WAIVER_PACKET_SCOPE),
        tests_to_run=(
            "pytest tests/test_overrides.py tests/test_admissibility.py "
            "tests/test_waiver_admission_completeness.py -q",
        ),
    )


def main() -> int:
    gov = _HERE / "slice3_receipts"
    system = GateReceiptSystem(gov)
    gate = DiffPathScopeGate(WAIVER_PACKET_SCOPE)

    # 1a. In-scope change → ADMIT on observed paths (real loop on a real AG path surface).
    in_scope = ag_admit_conductor.conduct(
        _step("waiver-in-scope", "src/governor/overrides.py"), gate, system
    )
    # 1b. Out-of-scope (§3-forbidden) change → REJECT on observed paths.
    out_scope = ag_admit_conductor.conduct(
        _step("waiver-out-scope", "src/governor/activation.py"), gate, system
    )

    print(f"in-scope  (overrides.py):  {in_scope.verdict.value}  [{in_scope.action}]")
    print(f"out-scope (activation.py): {out_scope.verdict.value}  [{out_scope.action}]")

    assert in_scope.verdict is StepVerdict.ADMIT, "in-scope packet path must admit"
    assert out_scope.verdict is StepVerdict.REJECT, "forbidden path must refuse"

    # 2. Post-decision (operator chose MODEL A, 2026-06-23): criterion 2 is RESOLVED
    #    inside the grant — "clean antecedents not certified" is a NonDischargeClaim of
    #    the specific existing kind the waiver bypasses (no new clean_antecedents kind,
    #    VALID_NON_DISCHARGE_KINDS untouched). Implemented in admissibility.py /
    #    overrides.py; pinned by tests/test_waiver_admission_completeness.py (criteria
    #    1, 2, 4). The remaining halt is criterion 3.
    #
    # 3. Criterion 3 (a consumer refuses a waiver-admitted receipt) has NO in-fence home:
    #    the named candidates (constraint_compiler.py, status_rollup.py) don't branch on
    #    receipt verdict; the real one (ci.py: ci_verify requires verdict=="pass") is
    #    OUTSIDE the §2 grant. Packet §8 → hand back, don't build a new consumer surface.
    finding = system.emit(
        gate="ag_packet_review",
        verdict="block",  # campaign halt; coarse wire verdict
        subject_kind="task_packet",
        subject_bytes=b"packet-waiver-completeness:criterion-3",
        evidence_bundle={
            "packet": "working/packet-waiver-completeness.md",
            "campaign_verdict": "NEEDS_HUMAN",
            "criterion_1_2_4": "RESOLVED in-grant via Model A (see test file)",
            "model_chosen": "A (reuse existing non-discharge kind; no enum change)",
            "boundary": "criterion_3_consumer_out_of_fence",
            "why": (
                "Criterion 3 needs a consumer that branches on receipt verdict. The "
                "named §2 candidates do not; the real one (ci.py ci_verify, requires "
                "verdict=='pass') is outside the §2 path grant."
            ),
            "options": (
                "(a) widen grant to include ci.py (small consumer touch); "
                "(b) defer criterion 3 to a follow-up packet."
            ),
            "in_scope_admission_receipt": in_scope.receipt_id,
            "conductor_decided": False,
        },
        gate_config={"slice": 3, "grant": list(WAIVER_PACKET_SCOPE)},
    )

    print("\nCriteria 1/2/4: RESOLVED in-grant via Model A (no enum change).")
    print(f"VERDICT: NEEDS_HUMAN on criterion 3  (finding receipt {finding.receipt_id[:16]}…)")
    print("Boundary: no in-fence verdict-branching consumer; real one (ci.py) out of §2.")
    print(f"Receipts: {gov}/receipts/gate_receipts.jsonl")
    return 2  # stopped for human (criterion 3)


if __name__ == "__main__":
    raise SystemExit(main())
