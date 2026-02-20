# SPDX-License-Identifier: Apache-2.0
"""SimAPI — thin adapter between the sim runner and governor internals.

One import surface. When governor refactors, fix this file only.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any


class SimAPI:
    """Adapter that delegates to governor modules via their public APIs.

    Parameters
    ----------
    gov_dir:
        Path to an initialised ``.governor/`` directory.
    params:
        Optional overrides for thresholds / config used by the heartbeat
        and evidence gate subsystems.  Supported keys:
        ``heartbeat_interval``, ``heartbeat_grace``, ``heartbeat_threshold``,
        ``evidence_gate_strict``.
    """

    def __init__(self, gov_dir: Path, params: dict[str, Any] | None = None) -> None:
        self.gov_dir = gov_dir
        self.params = params or {}
        self._receipt_system: Any | None = None
        self._evidence_gate: Any | None = None

    # -- lazy helpers --------------------------------------------------------

    def _get_receipt_system(self) -> Any:
        if self._receipt_system is None:
            from governor.gate_receipt import GateReceiptSystem
            self._receipt_system = GateReceiptSystem(self.gov_dir)
        return self._receipt_system

    def _get_evidence_gate(self) -> Any:
        if self._evidence_gate is None:
            from governor.evidence_gate import EvidenceGate, EvidenceGateConfig
            strict = self.params.get("evidence_gate_strict", True)
            cfg = EvidenceGateConfig(strict=strict)
            self._evidence_gate = EvidenceGate(
                config=cfg,
                receipt_system=self._get_receipt_system(),
            )
        return self._evidence_gate

    def _heartbeat_config(self) -> Any:
        from governor.gate_heartbeat import HeartbeatConfig
        kwargs: dict[str, Any] = {}
        if "heartbeat_interval" in self.params:
            kwargs["expected_interval_seconds"] = float(self.params["heartbeat_interval"])
        if "heartbeat_grace" in self.params:
            kwargs["grace_period_seconds"] = float(self.params["heartbeat_grace"])
        if "heartbeat_threshold" in self.params:
            kwargs["stale_after_missed"] = int(self.params["heartbeat_threshold"])
        return HeartbeatConfig(**kwargs)

    # -- public API ----------------------------------------------------------

    def gate_check(self, output: str, task: str = "", context: str = ".") -> dict[str, Any]:
        """Call EvidenceGate.check() and return result as dict."""
        gate = self._get_evidence_gate()
        result = gate.check(task=task, context=context, output=output)
        return {
            "status": result.status.value,
            "blocking_reasons": list(result.blocking_reasons),
            "warnings": list(result.warnings),
            "claim_count": len(result.claims),
        }

    def gate_heartbeat(self, now: datetime, session_active: bool = True) -> dict[str, Any]:
        """Call gate_heartbeat() and return HeartbeatStatus as dict."""
        from governor.gate_heartbeat import gate_heartbeat
        status = gate_heartbeat(
            self.gov_dir,
            config=self._heartbeat_config(),
            now=now,
            session_active=session_active,
        )
        return status.to_dict()

    def emit_receipt(
        self, receipt_data: dict[str, Any], *, timestamp: str | None = None,
    ) -> None:
        """Write a receipt through GateReceiptSystem (not raw file write).

        If *timestamp* is provided it overrides wall-clock (sim time injection).
        """
        system = self._get_receipt_system()
        raw = receipt_data.get("subject_bytes", b"sim")
        if isinstance(raw, str):
            subject_bytes = raw.encode("utf-8")
        elif isinstance(raw, bytes):
            subject_bytes = raw
        else:
            raise TypeError(
                f"subject_bytes must be str (UTF-8 encoded) or bytes, got {type(raw).__name__}"
            )
        system.emit(
            gate=receipt_data.get("gate", "sim"),
            verdict=receipt_data.get("verdict", "pass"),
            subject_kind=receipt_data.get("subject_kind", "sim_event"),
            subject_bytes=subject_bytes,
            evidence_bundle=receipt_data.get("evidence_bundle", {}),
            gate_config=receipt_data.get("gate_config", {}),
            timestamp=timestamp,
        )

    def receipt_count(self) -> int:
        """Count receipts via ReceiptStore.all()."""
        system = self._get_receipt_system()
        return len(system.receipt_store.all())

    def get_heartbeat_status(self, now: datetime, session_active: bool = True) -> dict[str, Any]:
        """Read heartbeat status (alias for gate_heartbeat)."""
        return self.gate_heartbeat(now=now, session_active=session_active)
