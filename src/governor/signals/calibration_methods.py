# SPDX-License-Identifier: Apache-2.0
"""
Calibration transform functions — Phase C2 apply-only methods.

Three transforms that normalize raw signal values to [0,1]:
  - identity_clip:  pass-through with clamping
  - linear_minmax:  linear rescaling from observed range
  - log_minmax:     log-space rescaling (requires explicit epsilon_shift)

All methods raise CalibrationMismatchError on bad inputs — never emit
degraded output silently.

Design authority: specs/gaps/V2_4C_SPINE.md §3
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Callable


# ── Exception ────────────────────────────────────────────────────────────────


class CalibrationMismatchError(Exception):
    """Raised when a param set doesn't match the source signal.

    Never emit degraded output — caller gets exception, not garbage.
    """

    def __init__(
        self,
        reason: str,
        *,
        param_set_id: str = "",
        signal_id: str = "",
    ):
        self.reason = reason
        self.param_set_id = param_set_id
        self.signal_id = signal_id
        super().__init__(reason)


# ── Bound helpers ────────────────────────────────────────────────────────────


def _validate_unit_bounds(lo: float, hi: float, label_lo: str, label_hi: str) -> None:
    """Enforce clip/identity bounds are in [0,1] and ordered."""
    if hi < lo:
        raise CalibrationMismatchError(
            f"inverted bounds: {label_hi}={hi} < {label_lo}={lo}"
        )
    if lo < 0.0 or hi > 1.0:
        raise CalibrationMismatchError(
            f"bounds outside [0,1]: {label_lo}={lo}, {label_hi}={hi}"
        )


# ── Transform functions ──────────────────────────────────────────────────────


def identity_clip(value: float, params: Mapping[str, Any]) -> float:
    """Pass-through with clamping to [min, max].

    Params: {"min": float, "max": float}
    Bounds must satisfy 0.0 <= min <= max <= 1.0.
    """
    lo, hi = params["min"], params["max"]
    _validate_unit_bounds(lo, hi, "min", "max")
    return max(lo, min(hi, value))


def linear_minmax(value: float, params: Mapping[str, Any]) -> float:
    """Linear rescaling from observed range to [clip_min, clip_max].

    Params: {"observed_min": float, "observed_max": float,
             "clip_min": float, "clip_max": float}
    Clip bounds must satisfy 0.0 <= clip_min <= clip_max <= 1.0.
    Observed bounds must satisfy observed_min <= observed_max.
    """
    obs_min, obs_max = params["observed_min"], params["observed_max"]
    clip_lo, clip_hi = params["clip_min"], params["clip_max"]

    if obs_max < obs_min:
        raise CalibrationMismatchError(
            f"inverted bounds: observed_max={obs_max} < observed_min={obs_min}"
        )
    _validate_unit_bounds(clip_lo, clip_hi, "clip_min", "clip_max")

    if obs_max == obs_min:
        return 0.5  # degenerate

    normalized = (value - obs_min) / (obs_max - obs_min)
    return max(clip_lo, min(clip_hi, normalized))


def log_minmax(value: float, params: Mapping[str, Any]) -> float:
    """Log-space rescaling from observed range to [clip_min, clip_max].

    Requires explicit epsilon_shift in param set (user-pinned policy).
    Refuses if value + epsilon_shift <= 0.

    Params: {"observed_min": float, "observed_max": float,
             "log_base": float, "epsilon_shift": float,
             "clip_min": float, "clip_max": float}
    Clip bounds must satisfy 0.0 <= clip_min <= clip_max <= 1.0.

    Two error categories (both CalibrationMismatchError):
      - Param-set errors: inverted bounds, epsilon_shift <= 0,
        bounds + epsilon_shift <= 0, bad log_base, inverted clip bounds
      - Runtime input error: value + epsilon_shift <= 0
    """
    base = params["log_base"]
    epsilon_shift = params["epsilon_shift"]
    obs_min = params["observed_min"]
    obs_max = params["observed_max"]
    clip_lo, clip_hi = params["clip_min"], params["clip_max"]

    # Param-set domain guards
    if base <= 0 or base == 1:
        raise CalibrationMismatchError(
            f"invalid log_base={base} (must be positive and != 1)"
        )
    if epsilon_shift <= 0:
        raise CalibrationMismatchError(
            f"epsilon_shift={epsilon_shift} must be > 0"
        )
    if obs_min + epsilon_shift <= 0:
        raise CalibrationMismatchError(
            f"observed_min + epsilon_shift = {obs_min + epsilon_shift} <= 0"
        )
    if obs_max + epsilon_shift <= 0:
        raise CalibrationMismatchError(
            f"observed_max + epsilon_shift = {obs_max + epsilon_shift} <= 0"
        )
    if obs_max < obs_min:
        raise CalibrationMismatchError(
            f"inverted bounds: observed_max={obs_max} < observed_min={obs_min}"
        )
    _validate_unit_bounds(clip_lo, clip_hi, "clip_min", "clip_max")

    # Runtime value guard (user-pinned)
    shifted = value + epsilon_shift
    if shifted <= 0:
        raise CalibrationMismatchError(
            f"value + epsilon_shift = {shifted} <= 0 (domain error)"
        )

    log_val = math.log(shifted) / math.log(base)
    log_min = math.log(obs_min + epsilon_shift) / math.log(base)
    log_max = math.log(obs_max + epsilon_shift) / math.log(base)

    if log_max == log_min:
        return 0.5  # degenerate — valid output, not mismatch

    normalized = (log_val - log_min) / (log_max - log_min)
    return max(clip_lo, min(clip_hi, normalized))


# ── Registry ─────────────────────────────────────────────────────────────────


CALIBRATION_METHODS: dict[str, Callable[[float, Mapping[str, Any]], float]] = {
    "identity_clip": identity_clip,
    "linear_minmax": linear_minmax,
    "log_minmax": log_minmax,
}

REQUIRED_PARAMS: dict[str, frozenset[str]] = {
    "identity_clip": frozenset({"min", "max"}),
    "linear_minmax": frozenset({"observed_min", "observed_max", "clip_min", "clip_max"}),
    "log_minmax": frozenset({
        "observed_min", "observed_max", "log_base",
        "epsilon_shift", "clip_min", "clip_max",
    }),
}
