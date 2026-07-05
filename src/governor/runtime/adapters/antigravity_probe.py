# SPDX-License-Identifier: Apache-2.0
"""Antigravity capability probe — Slice 5 / AGY-0 (recognition, not admission).

DRAFT / CANDIDATE substrate. The **boring, fenced** first step of the Antigravity
spike: *what beast is in the room?* It records the surface of the ``agy`` CLI —
version, which flags exist, whether a read-only/plan mode exists — **without running
an agentic task**. No model invocation, no writes, no network task, no live agent.

This is a **recognizer**, and its output is **compatibility evidence, never live
testimony** (``evidence_kind = "probe_compatibility"``, enforced). It says "this
binary declares these capabilities," not "Antigravity did X" and certainly not
"Antigravity is trusted." The integration law is unchanged and absolute:

    Antigravity plan        != authorized plan
    Antigravity permission  != Gov standing
    Antigravity artifact    != receipt
    Antigravity success     != admissible completion
    Antigravity sandbox     != Gov cage

Antigravity can *testify*; AG decides whether the testimony is admissible. A probe
result is not even testimony about a run — it is recognition of the tool's shape.

Design mirrors ``playbooks/ration_card.py``: the subprocess is an **injected runner**
so the probe LOGIC is deterministic and testable against fixtures (including the
negative ones that matter most — absent binary, empty stdout, unknown flags). The
live probe just injects :func:`subprocess_runner`.

Fail-closed: an absent/unrunnable binary is ``not_supported`` (never a crash), and
anything not positively observed is ``unknown`` — never assumed present.

**AGY-0 stops here.** The live behavioural probes (headless model call, write probe,
network probe) belong to **AGY-1**, and only behind the outer cage (bwrap/porter/
disposable worktree) — never on Antigravity's own ``--sandbox`` promise. They appear
here as fields fixed to ``skipped`` so the shape is named, not silently missing.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Optional

ADAPTER_ID = "antigravity_cli"
BINARY = "agy"

# Closed vocabularies (fail-closed; "unknown" is a first-class honest value).
AVAILABILITY = frozenset({"not_supported", "available", "auth_required", "unknown"})
_TRI = frozenset({"yes", "no", "unknown"})
AUTH_STATES = frozenset({"available", "missing", "expired", "unknown"})
_STDOUT_PROBE = frozenset({"pass", "fail", "skipped"})
_WRITE_PROBE = frozenset({"blocked", "wrote", "inconclusive", "skipped"})
_NETWORK_PROBE = frozenset({"blocked", "reachable", "inconclusive", "skipped"})

#: The one evidence class a probe may carry. A probe is NEVER live testimony.
EVIDENCE_KIND = "probe_compatibility"


@dataclass(frozen=True)
class ProbeExec:
    """One injected command execution. ``ran`` is False when the binary was absent or
    not executable — the fail-closed signal, distinct from a nonzero exit."""

    ran: bool
    exit_code: Optional[int]
    stdout: str = ""
    stderr: str = ""


#: A runner executes one argv and returns a :class:`ProbeExec`. Injected for testing.
ProbeRunner = Callable[[Sequence[str]], ProbeExec]


@dataclass(frozen=True)
class AntigravityProbeResult:
    """What the probe recognized about the ``agy`` binary. Compatibility evidence —
    a description of the tool's declared surface, not a claim about any run."""

    availability: str
    agy_version: Optional[str] = None
    supports_print_mode: str = "unknown"
    supports_sandbox_flag: str = "unknown"
    supports_model_flag: str = "unknown"
    supports_plan_mode: str = "unknown"  # a read-only / plan / approval-mode flag
    supports_mcp: str = "unknown"
    auth_state: str = "unknown"
    # AGY-1 behavioural probes — named here, run only behind the outer cage.
    headless_stdout_probe: str = "skipped"
    write_probe_result: str = "skipped"
    network_probe_result: str = "skipped"
    adapter: str = ADAPTER_ID
    binary: str = BINARY
    evidence_kind: str = EVIDENCE_KIND
    notes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        checks = (
            ("availability", self.availability, AVAILABILITY),
            ("supports_print_mode", self.supports_print_mode, _TRI),
            ("supports_sandbox_flag", self.supports_sandbox_flag, _TRI),
            ("supports_model_flag", self.supports_model_flag, _TRI),
            ("supports_plan_mode", self.supports_plan_mode, _TRI),
            ("supports_mcp", self.supports_mcp, _TRI),
            ("auth_state", self.auth_state, AUTH_STATES),
            ("headless_stdout_probe", self.headless_stdout_probe, _STDOUT_PROBE),
            ("write_probe_result", self.write_probe_result, _WRITE_PROBE),
            ("network_probe_result", self.network_probe_result, _NETWORK_PROBE),
        )
        for name, value, allowed in checks:
            if value not in allowed:
                raise ValueError(f"{name}={value!r} not in {sorted(allowed)}")
        # The load-bearing honesty invariant: a probe is compatibility evidence,
        # never live testimony. This field cannot be anything else.
        if self.evidence_kind != EVIDENCE_KIND:
            raise ValueError(
                f"evidence_kind must be {EVIDENCE_KIND!r} (a probe is not live testimony)"
            )

    def as_dict(self) -> dict[str, object]:
        return {
            "adapter": self.adapter,
            "binary": self.binary,
            "availability": self.availability,
            "agy_version": self.agy_version,
            "supports_print_mode": self.supports_print_mode,
            "supports_sandbox_flag": self.supports_sandbox_flag,
            "supports_model_flag": self.supports_model_flag,
            "supports_plan_mode": self.supports_plan_mode,
            "supports_mcp": self.supports_mcp,
            "auth_state": self.auth_state,
            "headless_stdout_probe": self.headless_stdout_probe,
            "write_probe_result": self.write_probe_result,
            "network_probe_result": self.network_probe_result,
            "evidence_kind": self.evidence_kind,
            "notes": list(self.notes),
        }


def _flag_present(help_text: str, *tokens: str) -> str:
    """TRI: 'yes' if any token appears in the help text, else 'no'."""
    low = help_text.lower()
    return "yes" if any(t.lower() in low for t in tokens) else "no"


def probe(runner: ProbeRunner) -> AntigravityProbeResult:
    """Recognize the ``agy`` CLI surface via an injected runner. AGY-0 only:
    ``agy --version`` + ``agy --help``. No task execution, no model call.

    Fail-closed:
    - binary absent/unrunnable → ``not_supported`` (never raises).
    - ``--help`` unreadable → flag capabilities stay ``unknown`` (never assumed yes).
    """
    version_exec = runner([BINARY, "--version"])
    if not version_exec.ran:
        return AntigravityProbeResult(
            availability="not_supported",
            notes=("agy binary absent or not executable (fail-closed)",),
        )
    if version_exec.exit_code not in (0, None):
        return AntigravityProbeResult(
            availability="unknown",
            notes=(f"agy --version exited {version_exec.exit_code}; surface unknown",),
        )

    agy_version = (version_exec.stdout.strip().splitlines() or [""])[0].strip() or None

    help_exec = runner([BINARY, "--help"])
    notes: list[str] = []
    # Usage text may land on stdout OR stderr (agy, like most Go flag CLIs, prints
    # usage to stderr) — read both before declaring the help surface unreadable.
    help_text = f"{help_exec.stdout}\n{help_exec.stderr}".strip()
    if not help_exec.ran or help_exec.exit_code not in (0, None) or not help_text:
        notes.append("agy --help unreadable; flag capabilities left unknown")
        return AntigravityProbeResult(
            availability="available",
            agy_version=agy_version,
            notes=tuple(notes),
        )

    supports_print = _flag_present(help_text, "--print", "-p ", "--prompt")
    supports_sandbox = _flag_present(help_text, "--sandbox")
    supports_model = _flag_present(help_text, "--model")
    supports_plan = _flag_present(
        help_text, "--approval-mode", "plan-mode", "--plan", "read-only", "readonly"
    )
    supports_mcp = "yes" if "mcp" in help_text.lower() else "unknown"

    if supports_plan == "no":
        # The known automation gap (antigravity-cli issue #45): non-interactive `-p`
        # has no read-only/plan-mode equivalent — writes are fenced by the OUTER cage
        # at AGY-1, never by an agy flag. Recorded, not worked around.
        notes.append(
            "no read-only/plan-mode flag observed — headless writes must be fenced "
            "by the outer cage (bwrap/porter), not by agy (see antigravity-cli #45)"
        )

    return AntigravityProbeResult(
        availability="available",
        agy_version=agy_version,
        supports_print_mode=supports_print,
        supports_sandbox_flag=supports_sandbox,
        supports_model_flag=supports_model,
        supports_plan_mode=supports_plan,
        supports_mcp=supports_mcp,
        auth_state="unknown",  # AGY-0 does not probe auth (would hit Google)
        notes=tuple(notes),
    )


def subprocess_runner(timeout_s: float = 20.0) -> ProbeRunner:
    """A real runner over ``subprocess``. Safe for AGY-0 use (version/help only):
    closes stdin, bounds time, and reports an absent binary as ``ran=False`` rather
    than raising. NOT for behavioural probes — those need the outer cage (AGY-1)."""
    import subprocess

    def _run(argv: Sequence[str]) -> ProbeExec:
        try:
            proc = subprocess.run(
                list(argv),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=timeout_s,
            )
        except FileNotFoundError:
            return ProbeExec(ran=False, exit_code=None)
        except subprocess.TimeoutExpired:
            return ProbeExec(ran=True, exit_code=None, stderr="timeout")
        return ProbeExec(
            ran=True, exit_code=proc.returncode, stdout=proc.stdout, stderr=proc.stderr
        )

    return _run


__all__ = [
    "ADAPTER_ID",
    "BINARY",
    "AVAILABILITY",
    "AUTH_STATES",
    "EVIDENCE_KIND",
    "ProbeExec",
    "ProbeRunner",
    "AntigravityProbeResult",
    "probe",
    "subprocess_runner",
]
