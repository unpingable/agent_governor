# SPDX-License-Identifier: Apache-2.0
"""Subprocess bridge to the Rust `transition-cli` (the governed-transition office).

A2 of the transition-kernel build: AG forms a real cooked context, sends it over **real transport**
(subprocess, JSON in / one JSON line out) to the Rust decision kernel, gets a decision back, and records
it as a **measurement** receipt — then STOPS. This path is deliberately *non-operational*:

- It holds no `LinearAccountantClient` and no `LabGate`; it cannot call `consume()` or confer any effect.
  "Real transport and orchestration, not live consequence."
- The decision is recorded with ``receipt_role=ROLE_MEASUREMENT`` and ``verdict="observe"`` — a witness,
  not an authority. A measurement does not mint a grant, a token, or a spend.
- Under any non-``observed`` origin (e.g. ``drill``), the Rust kernel reports ``operational: false`` and
  the receipt's evidence bundle carries that fence verbatim.

Mirrors ``la_subprocess.LASubprocess`` (same fail-closed discipline), but the wire is JSON, not TSV, and
``transition-cli`` emits no banner — the first stdout line is the response.

Contract (see ``~/git/transition-kernel/CONTRACT.md``):
  in  : {"scenario": <one of 8>, "origin_mode": "drill|observed|...", "override_origin_mode"?, ...}
  out : {"decision": "admit|refuse|escalate", "verdict": {<7 fields incl. operational>}}
  err : {"error": "...", "fail_closed": true}
"""

from __future__ import annotations

import json
import os
import select
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

DEFAULT_TRANSITION_CLI = os.path.expanduser(
    "~/git/transition-kernel/target/debug/transition-cli"
)

# transition-cli decision -> closed gate-receipt verdict (gate_receipt.VALID_VERDICTS).
# A transition decision is a *measurement* here, never authority: admit observes, it does not grant.
_VERDICT_FOR_DECISION = {
    "admit": "observe",
    "refuse": "block",
    "escalate": "warn",
}


class TransitionSubprocessError(Exception):
    """The transport could not be established (binary missing)."""


@dataclass(frozen=True)
class TransitionBoundaryIdentity:
    """What AG records at the constellation edge: exactly which transition-kernel it talked to."""

    binary_path: str
    repo_commit: Optional[str]  # `git -C <repo> rev-parse HEAD` at launch

    def to_dict(self) -> dict[str, Any]:
        return {"binary_path": self.binary_path, "repo_commit": self.repo_commit}


class TransitionSubprocess:
    """One `transition-cli` process; session-lived. Stateless across calls (each decide spawns one
    exchange), but we keep a persistent process for transport realism + boundary identity."""

    def __init__(
        self,
        binary_path: str | None = None,
        *,
        repo_dir: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.binary_path = binary_path or os.environ.get(
            "GOVERNOR_TRANSITION_CLI", DEFAULT_TRANSITION_CLI
        )
        self.repo_dir = repo_dir
        self.timeout = timeout
        self.identity: TransitionBoundaryIdentity | None = None

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> TransitionBoundaryIdentity:
        if not Path(self.binary_path).exists():
            raise TransitionSubprocessError(
                f"transition-cli not found at {self.binary_path} (cargo build the transition-kernel)"
            )
        # No banner to read: transition-cli reads one JSON object and emits one JSON line per process.
        self.identity = TransitionBoundaryIdentity(
            binary_path=self.binary_path,
            repo_commit=self._repo_commit(),
        )
        return self.identity

    def __enter__(self) -> "TransitionSubprocess":
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    # -- transport ---------------------------------------------------------- #

    def decide_live(self, office_outputs: dict[str, Any]) -> dict[str, Any] | None:
        """Decide on a live office-outputs probe (the supervisor hot path). Non-operational by
        construction: the kernel mints a candidate, never an authority."""
        return self.decide({"office_outputs": office_outputs})

    def decide_gated(
        self, memory_claim: dict[str, Any], operation: dict[str, Any]
    ) -> dict[str, Any] | None:
        """GAP-3b: derive Standing through memory custody, then decide. Unpromoted memory cannot stamp
        standing, so the transition refuses for want of standing. Non-operational."""
        return self.decide({
            "memory_gated_transition": {"memory_claim": memory_claim, "operation": operation}
        })

    def _send_raw(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """Send one JSON object; return the parsed response dict, or None (fail-closed) on any transport
        failure / malformed line / `fail_closed` error. The caller validates the response shape."""
        if self.identity is None:
            return None
        try:
            proc = subprocess.Popen(
                [self.binary_path],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
            )
        except OSError:
            return None
        try:
            try:
                out, _ = proc.communicate(json.dumps(payload), timeout=self.timeout)
            except subprocess.TimeoutExpired:
                proc.kill()
                return None
            lines = (out or "").strip().splitlines()
            if not lines:
                return None
            obj = json.loads(lines[-1])
        except (json.JSONDecodeError, ValueError):
            return None
        finally:
            if proc.poll() is None:
                proc.kill()
        if not isinstance(obj, dict) or obj.get("fail_closed"):
            return None
        return obj

    def decide(self, probe: dict[str, Any]) -> dict[str, Any] | None:
        """Send one cooked-context probe; return {"decision","verdict"} or None (fail-closed)."""
        obj = self._send_raw(probe)
        if obj is None or "decision" not in obj or "verdict" not in obj:
            return None
        return obj

    def correspondence_check(self, chain_inner: dict[str, Any]) -> dict[str, Any] | None:
        """3b1: validate up to receiver correspondence (no burn); return the LA consume params or a
        refusal. None (fail-closed) on transport failure — the enforce path must then refuse, never
        observe."""
        obj = self._send_raw({"correspondence_check": chain_inner})
        if obj is None or "result" not in obj:
            return None
        return obj

    def decide_continuation(
        self, request: dict[str, Any], policy: dict[str, Any]
    ) -> dict[str, Any] | None:
        """GAP-2 C2: ask the continuation OFFICE whether a proposed next step may continue from the prior
        governed step's terminal chain. Returns the decision dict (`{"decision": grant|refuse|escalate,
        ...}`) or None (fail-closed). Runs the office only — no consumer, no burn, no effect."""
        obj = self._send_raw({"continuation": {"request": request, "policy": policy}})
        if obj is None or "decision" not in obj:
            return None
        return obj

    def _repo_commit(self) -> Optional[str]:
        repo = self.repo_dir
        if repo is None and "target" in self.binary_path:
            repo = str(Path(self.binary_path).resolve().parents[2])
        if not repo:
            return None
        try:
            out = subprocess.run(
                ["git", "-C", repo, "rev-parse", "HEAD"],
                capture_output=True, text=True, timeout=3.0,
            )
            return out.stdout.strip() if out.returncode == 0 else None
        except Exception:
            return None


def record_transition_decision(
    system: Any,  # GateReceiptSystem
    *,
    probe: dict[str, Any],
    decision: dict[str, Any],
    binary_path: str,
) -> Any:  # GateReceipt
    """Record a transition decision as a non-authority MEASUREMENT receipt and STOP.

    Mints no LA grant/token, calls no `consume`, confers no effect. The receipt is a witness: role
    MEASUREMENT, verdict in {observe, block, warn}. The `operational` flag from the Rust kernel is
    carried verbatim so the existing operational fence sees it.
    """
    from governor.gate_receipt import ROLE_MEASUREMENT

    verdict_field = decision["verdict"]
    gate_verdict = _VERDICT_FOR_DECISION.get(decision["decision"], "observe")
    origin_mode = probe.get("override_origin_mode") or probe.get("origin_mode") or "drill"

    evidence_bundle = {
        "decision": decision["decision"],
        "verdict": verdict_field,
        "origin_mode": origin_mode,
        "operational": verdict_field.get("operational"),
        "transition_cli_binary": binary_path,
        "probe": probe,
    }
    subject_bytes = json.dumps(probe, sort_keys=True, separators=(",", ":")).encode("utf-8")

    return system.emit(
        gate="transition_kernel_seam",
        verdict=gate_verdict,
        subject_kind="transition_cooked_context",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence_bundle,
        gate_config={"scenario": probe.get("scenario"), "seam": "transition_kernel"},
        receipt_role=ROLE_MEASUREMENT,
    )


def default_office_context(
    tool_name: str, tool_input: dict[str, Any], scope: str, target: str
) -> dict[str, Any]:
    """The production posture: a session admitted this far has verified standing and an admitted,
    consumable request. Tests inject a different builder to construct hostile (refusing) postures."""
    return {
        "standing": "verified",
        "standing_receipt_ref": "d" * 64,
        "spendability": "not_applicable",
        "la_admission": "admitted",
        "la_consume": "consumed",
        "scope": scope or "lab",
        "target": target or tool_name,
    }


# transition-probe modes. `enforce` is deliberately absent: no mode here lets a candidate participate in
# minting an AuthorizedTransition. That word is reserved for the later slice.
PROBE_DISABLED = "disabled"  # no kernel call; behavior byte-identical to baseline
PROBE_OBSERVE = "observe"    # decide + receipt; governed path continues; loud divergence receipt
PROBE_HOLD = "hold"          # decide + receipt; then STOP before LA/effect (no consume)
PROBE_ENFORCE = "enforce"    # full chain: consume + bounded effect; legacy route unreachable
PROBE_MODES = frozenset({PROBE_DISABLED, PROBE_OBSERVE, PROBE_HOLD, PROBE_ENFORCE})


@dataclass
class TransitionProbe:
    """Flag-gated, additive transition-kernel probe for the supervisor hot path.

    `disabled` (default) makes the probe a no-op so baseline behavior is byte-identical. `observe`
    records the kernel decision and a loud divergence receipt when the kernel would refuse while the
    governed path continues — never silently treating a Rust refusal as advisory success. `hold` records
    the decision and STOPS before any LA consume or effect. No `enforce` mode exists.
    """

    transport: TransitionSubprocess
    mode: str = PROBE_DISABLED
    receipt_system: Any = None  # GateReceiptSystem | None
    build_office_context: Callable[..., dict[str, Any]] = field(default=default_office_context)
    # GAP-3b: when set, the session's Standing input is DERIVED through memory custody. The builder
    # returns the inner memory claim ({artifact, promotion_receipt?, presentation}) for this operation,
    # or None to fall back to the plain office-context path.
    memory_context_builder: Callable[..., dict[str, Any] | None] | None = None
    # 3b2 enforce: config for the live consequence chain (LA handle, token, sandbox, durable sink, ...).
    enforce_config: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.mode not in PROBE_MODES:
            raise ValueError(f"transition probe mode {self.mode!r} not in {sorted(PROBE_MODES)}")

    def evaluate(
        self, *, tool_name: str, tool_input: dict[str, Any], scope: str, target: str
    ) -> dict[str, Any] | None:
        """Decide via the kernel (real transport), record a measurement receipt. Returns the decision
        dict or None (fail-closed). When a memory_context_builder is configured, Standing is derived
        THROUGH memory custody (GAP-3b); otherwise the plain office-context path is used."""
        mem = None
        if self.memory_context_builder is not None:
            mem = self.memory_context_builder(tool_name, tool_input, scope, target)
        if mem is not None:
            operation = {"scope": scope or "lab", "target": target or tool_name}
            decision = self.transport.decide_gated(mem, operation)
            probe = {"memory_gated_transition": {"memory_claim": mem, "operation": operation}}
        else:
            office = self.build_office_context(tool_name, tool_input, scope, target)
            decision = self.transport.decide_live(office)
            probe = {"office_outputs": office}
        if decision is not None and self.receipt_system is not None:
            record_transition_decision(
                self.receipt_system, probe=probe, decision=decision,
                binary_path=self.transport.binary_path,
            )
        return decision

    def enforce(
        self, *, tool_name: str, tool_input: dict[str, Any], tool_call_id: str
    ) -> dict[str, Any]:
        """3b2: run the full live consequence chain for this operation — consume + one bounded marker
        effect. Returns the terminal result. Fail-closed; the caller denies on anything but success."""
        from governor.runtime.transition_enforce import MarkerActuator, enforce_chain

        cfg = self.enforce_config or {}
        sandbox_root = cfg["sandbox_root"]
        content = cfg.get("marker_content", b"create_marker_v1:fixed-bytes")
        actuator = MarkerActuator(sandbox_root, tool_call_id, content)
        return enforce_chain(
            self.transport, cfg["la"],
            token_handle=cfg["token_handle"], scope=cfg.get("scope", "lab"), target=tool_name,
            effect_class="create_marker_v1", operation_hash=tool_call_id, consumer=cfg.get("consumer", "ag:main"),
            eligibility_reference=cfg["eligibility_reference"], capability_id=tool_call_id,
            valid_until=cfg.get("valid_until", 1000), now=cfg.get("now", 10),
            durable_path=cfg["durable_path"], actuator=actuator,
        )

    def record_divergence(
        self, *, kernel_decision: dict[str, Any] | None, tool_name: str, tool_call_id: str,
        governed_path: str,
    ) -> Any:
        """Emit a LOUD classified divergence receipt: the kernel refused while the governed path
        continued. A warning-role measurement — it records the disagreement, it does not act on it."""
        if self.receipt_system is None:
            return None
        from governor.gate_receipt import ROLE_MEASUREMENT

        bundle = {
            "classification": "kernel_refuse_vs_governed_continue",
            "kernel_decision": kernel_decision or {"decision": "fail_closed"},
            "governed_path": governed_path,
            "tool_name": tool_name,
            "mode": self.mode,
        }
        return self.receipt_system.emit(
            gate="transition_kernel_divergence",
            verdict="warn",
            subject_kind="transition_divergence",
            subject_bytes=(tool_call_id or "").encode("utf-8"),
            evidence_bundle=bundle,
            gate_config={"seam": "transition_kernel"},
            receipt_role=ROLE_MEASUREMENT,
        )


# --- GAP-2 C2: the continuation office in the live artery (observe/hold; no burn) -------------------- #

CONT_DISABLED = "disabled"  # no continuation call; behavior byte-identical to baseline
CONT_OBSERVE = "observe"    # decide + receipt; legacy loop continues; loud divergence on refuse/escalate
CONT_HOLD = "hold"          # decide + receipt; then STOP before the next agent step
CONT_ENFORCE = "enforce"    # C3: a grant must be presented + durably BURNED before the next step reaches
                            # the transition gate; no grant -> no next step (legacy unreachable)
CONT_MODES = frozenset({CONT_DISABLED, CONT_OBSERVE, CONT_HOLD, CONT_ENFORCE})

# continuation decision -> closed gate-receipt verdict. A grant here is a MEASUREMENT ("the office would
# grant"), never authority: C2 records, it never burns. The burn/enforce point is C3.
_VERDICT_FOR_CONTINUATION = {"grant": "observe", "refuse": "block", "escalate": "warn"}


def default_next_step(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Project a proposed tool call into the next step it represents: its class, the scope it requests,
    and the clock. Tests drive hostile next steps (scope expansion, unknown class) via tool_input."""
    return {
        "next_step_class": tool_input.get("next_step_class", tool_name),
        "scope": tool_input.get("scope"),
        "now": tool_input.get("now", 0),
    }


def record_continuation_decision(
    system: Any, *, request: dict[str, Any], decision: dict[str, Any], binary_path: str
) -> Any:
    """Record a continuation decision as a non-authority MEASUREMENT receipt. Mints no grant, burns
    nothing, confers no effect — it witnesses what the office would decide about the *next step*."""
    from governor.gate_receipt import ROLE_MEASUREMENT

    gate_verdict = _VERDICT_FOR_CONTINUATION.get(decision.get("decision"), "observe")
    evidence_bundle = {
        "decision": decision.get("decision"),
        "kind": decision.get("kind"),
        "required_authority": decision.get("required_authority"),
        "prior_chain_tip": request.get("prior_chain_tip"),
        "terminal_outcome": request.get("terminal_outcome"),
        "requested_next_step": request.get("requested_next_step"),
        "scope": request.get("scope"),
        "transition_cli_binary": binary_path,
        # The grant, if any, is DESCRIBED (its binds) — not consumed. No burn happens by recording it.
        "grant": decision.get("grant"),
    }
    subject_bytes = json.dumps(request, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return system.emit(
        gate="continuation_seam",
        verdict=gate_verdict,
        subject_kind="continuation_request",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence_bundle,
        gate_config={"seam": "continuation_kernel"},
        receipt_role=ROLE_MEASUREMENT,
    )


@dataclass
class ContinuationProbe:
    """GAP-2 C2: the continuation office spliced into the live AG artery, observe/hold only.

    Given a prior governed step's terminal Stage 3c chain and a proposed next step, it asks the Rust
    continuation OFFICE whether the agent earns one more step, and records the decision/divergence. It
    holds no consumer and burns no grant — `observe` records and lets the legacy loop continue, `hold`
    records and stops before the next step, `disabled` is a no-op (byte-identical baseline). The
    present/burn enforce point is C3, not here: minting-and-burning authority for a path the kernel does
    not yet control would be accounting cosplay.
    """

    transport: TransitionSubprocess
    mode: str = CONT_DISABLED
    receipt_system: Any = None
    # The prior governed step's terminal chain (a Stage 3c result): prior_snapshot (dict|None),
    # terminal_outcome, prior_chain_tip, session_id, actor_id, policy_version, kernel_version, scope,
    # remaining_capacity_ref.
    prior_terminal: dict[str, Any] = field(default_factory=dict)
    # Continuation policy: admissible_next_step_classes, current_policy_version, grant_ttl.
    policy: dict[str, Any] = field(default_factory=dict)
    next_step_builder: Callable[..., dict[str, Any]] = field(default=default_next_step)
    # C3 enforce: the durable continuation ledger. The single-use burn lives here, not in memory.
    enforce_ledger_path: Any = None  # Path | None

    def __post_init__(self) -> None:
        if self.mode not in CONT_MODES:
            raise ValueError(f"continuation probe mode {self.mode!r} not in {sorted(CONT_MODES)}")
        if self.mode == CONT_ENFORCE and self.enforce_ledger_path is None:
            raise ValueError("continuation enforce mode requires enforce_ledger_path (durable burn)")

    def build_request(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        nxt = self.next_step_builder(tool_name, tool_input)
        p = self.prior_terminal
        return {
            "prior_snapshot": p.get("prior_snapshot"),
            "terminal_outcome": p.get("terminal_outcome", "consumed_outcome_unknown"),
            "prior_chain_tip": p.get("prior_chain_tip", ""),
            "session_id": p.get("session_id", ""),
            "actor_id": p.get("actor_id", "ag:main"),
            "requested_next_step": nxt["next_step_class"],
            "scope": nxt.get("scope") or p.get("scope", "lab"),
            "remaining_capacity_ref": p.get("remaining_capacity_ref", ""),
            "policy_version": p.get("policy_version", ""),
            "kernel_version": p.get("kernel_version", ""),
            "now": nxt.get("now", 0),
        }

    def evaluate(self, *, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        """Decide via the kernel continuation office and record a measurement receipt. Returns the
        decision dict (or None, fail-closed). No grant is burned."""
        request = self.build_request(tool_name, tool_input)
        decision = self.transport.decide_continuation(request, self.policy)
        if decision is not None and self.receipt_system is not None:
            record_continuation_decision(
                self.receipt_system, request=request, decision=decision,
                binary_path=self.transport.binary_path,
            )
        return decision

    def record_divergence(
        self, *, decision: dict[str, Any] | None, tool_name: str, tool_call_id: str, governed_path: str
    ) -> Any:
        """Emit a LOUD classified divergence receipt: the kernel would NOT grant continuation while the
        legacy loop would continue. A warning-role measurement — it records the disagreement, it does not
        act on it (and burns nothing)."""
        if self.receipt_system is None:
            return None
        from governor.gate_receipt import ROLE_MEASUREMENT

        bundle = {
            "classification": "kernel_refuse_continuation_vs_legacy_continue",
            "continuation_decision": decision or {"decision": "fail_closed"},
            "governed_path": governed_path,
            "tool_name": tool_name,
            "mode": self.mode,
        }
        return self.receipt_system.emit(
            gate="continuation_divergence",
            verdict="warn",
            subject_kind="continuation_divergence",
            subject_bytes=(tool_call_id or "").encode("utf-8"),
            evidence_bundle=bundle,
            gate_config={"seam": "continuation_kernel"},
            receipt_role=ROLE_MEASUREMENT,
        )

    # --- C3 enforce: durable present/burn (the single-use authority lives in the ledger) ----------- #

    def present(self, *, grant: dict[str, Any], tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        """Present the issued grant for the proposed next step and durably BURN it (before the transition
        gate). The presentation is built from the grant's own binds (the grant was issued for exactly this
        step), so correspondence holds on the happy path; the burn record is fsynced before this returns
        admitted. Returns the present_continuation result."""
        from governor.runtime.continuation_enforce import present_continuation

        now = self.next_step_builder(tool_name, tool_input).get("now", 0)
        presentation = {
            "session_id": grant.get("session_id"), "actor_id": grant.get("actor_id"),
            "chain_tip": grant.get("chain_tip"), "scope": grant.get("scope"),
            "next_step_class": grant.get("next_step_class"), "now": now,
        }
        return present_continuation(self.enforce_ledger_path, grant, presentation, now)

    def finalize(self, grant_id: str) -> None:
        """Record that the burned next step reached the transition gate."""
        from governor.runtime.continuation_enforce import finalize_continuation

        finalize_continuation(self.enforce_ledger_path, grant_id)

    def record_refusal(self, *, grant_id: str | None, reason: str) -> None:
        """Durably record a non-burning refusal (no grant / refuse / escalate / fail-closed) so a denied
        continuation is never fail-silent."""
        from governor.runtime.continuation_enforce import record_continuation_refusal

        if self.enforce_ledger_path is not None:
            record_continuation_refusal(self.enforce_ledger_path, grant_id=grant_id, reason=reason)
