"""Invariant: tools.trace_consistency

If claims reference tool_call_ids, the tool_trace evidence must exist
and contain matching entries. Catches "phantom tooling" structurally.
"""

from __future__ import annotations

from typing import Any

from receipt_kernel.invariants._helpers import get_run_mode, load_evidence_json
from receipt_kernel.types import InvariantResult, Reason, Verdict


class ToolTraceConsistencyInvariant:
    """Verify tool-derived claims match actual tool trace entries."""

    invariant_id = "tools.trace_consistency"

    def __init__(self, *, enforce_in_modes: tuple[str, ...] = ("factual", "mixed")):
        self._modes = enforce_in_modes

    def evaluate(self, ctx: dict[str, Any]) -> InvariantResult:
        store = ctx.get("store")
        run_id = ctx.get("run_id")
        if store is None or not run_id:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.UNKNOWN,
                reasons=[Reason(code="CONTEXT_MISSING", msg="store/run_id not provided")],
            )

        mode = get_run_mode(store, str(run_id))
        if mode is None:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.FAIL,
                reasons=[Reason(code="RUN_MODE_MISSING", msg="RUN_START.meta.mode is required")],
            )

        if mode not in self._modes:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.PASS,
                reasons=[],
                meta={"mode": mode, "skipped": True},
            )

        # Load claims_map to find tool_call_ids
        claims_doc = load_evidence_json(store, str(run_id), "claims_map")
        if claims_doc is None:
            # Let claims.evidence_binding own this failure
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.UNKNOWN,
                reasons=[Reason(code="CLAIMS_MAP_MISSING", msg="cannot verify tool refs without claims_map")],
                meta={"mode": mode},
            )

        claims = claims_doc.get("claims") or []
        required_ids: set[str] = set()
        for c in claims:
            if isinstance(c, dict):
                tids = c.get("tool_call_ids")
                if isinstance(tids, list):
                    for tid in tids:
                        if isinstance(tid, str) and tid:
                            required_ids.add(tid)

        if not required_ids:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.PASS,
                reasons=[],
                meta={"mode": mode, "tool_ids_checked": 0},
            )

        # Load tool_trace
        trace_doc = load_evidence_json(store, str(run_id), "tool_trace")
        if trace_doc is None:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.FAIL,
                reasons=[Reason(
                    code="TOOL_TRACE_MISSING",
                    msg="tool_trace required when claims reference tool_call_ids",
                )],
                meta={"mode": mode, "required_ids": sorted(required_ids)},
            )

        calls = trace_doc.get("calls")
        if not isinstance(calls, list):
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.FAIL,
                reasons=[Reason(code="TOOL_TRACE_MALFORMED", msg="tool_trace.calls must be a list")],
                meta={"mode": mode},
            )

        present_ids: set[str] = set()
        for call in calls:
            if isinstance(call, dict) and isinstance(call.get("id"), str):
                present_ids.add(call["id"])

        missing = sorted(required_ids - present_ids)
        if missing:
            return InvariantResult(
                invariant_id=self.invariant_id,
                verdict=Verdict.FAIL,
                reasons=[Reason(
                    code="TOOL_CALL_MISSING",
                    msg=f"claims reference tool_call_ids missing from trace: {missing}",
                )],
                meta={"mode": mode, "missing": missing},
            )

        return InvariantResult(
            invariant_id=self.invariant_id,
            verdict=Verdict.PASS,
            reasons=[],
            meta={"mode": mode, "tool_ids_checked": len(required_ids)},
        )
