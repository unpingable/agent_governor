# SPDX-License-Identifier: Apache-2.0
"""Bubblewrap real-cage backend (implementation slice, OUTSIDE AG).

> Configuration is not containment. A cage that *says* it is isolated is making a claim;
> the attestation is earned by **witnessing** — running the forbidden thing and confirming
> it fails. (Real Cage Backend Review, operator pass 2026-06-30: facts **C1–C11**,
> seccomp required as C11.)

This is the real backend authorized by `docs/playbooks/real-cage-backend-review.md`. It
implements the `HarnessCage` contract (`attest()` + `admit_live()`) over bubblewrap
(`bwrap`). It **runs no actor** — the only subprocesses it ever launches are the `bwrap`
*probe commands required to test the cage itself*. There is no `run`/`spawn`/`run_once`
method, no Claude/Codex/echo invocation, no loop.

How `confirms_isolation=True` is earned (and why it usually is not):

1. **Host gate.** `assess_host` requires Linux + `bwrap` on PATH + user namespaces +
   seccomp kernel support + a *cage smoke test* (`bwrap … -- /bin/true` actually starts an
   isolated cage). Any miss → no battery, attest nothing, refuse-live.
2. **Pre-flight negative-probe battery, per run.** For each required fact C1–C11 the prober
   attempts the forbidden action inside a fresh cage and witnesses that it fails (or that
   the safe property holds). Positive config inspection is *not* a witness.
3. **Conjunctive mint.** `CageAttestation(confirms_isolation=True, scope=live)` is minted
   **only** when **every** required fact (C1–C11) is witnessed for that run. One missing,
   unknown, refused, failed, or timed-out fact → attest nothing → refuse-live.
4. **Evidence carried.** The per-fact `FactWitness` results ride in the `CageRunAttestation`
   and are persisted to the **tainted harness audit store** (`harness.cage.run_dir`,
   outside AG ingest). AG ingests only `actor_output.v0`.

**Lab/compatibility status (honest):** the live witnessing path is real-shaped but is
gated behind a host where `bwrap` can establish a cage. In a nested/restricted sandbox the
cage smoke fails, so this backend **refuses**. Additionally the v0 prober does **not** yet
compile a seccomp BPF filter, so **C11 is never witnessed by the real prober** → the real
backend refuses live admission in v0 by construction. The battery/decision/evidence logic
is exercised against an injected prober (synthetic compatibility), never live testimony.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Protocol

from .cage import (
    SCOPE_LIVE,
    SCOPE_NONE,
    CageAttestation,
    LiveAdmission,
    LiveAdmissionRequest,
    evaluate_live_admission,
    run_dir,
)

BACKEND_ID = "bwrap-cage.v0"

# The containment facts, in order (Real Cage Backend Review, C1–C11). Every one is
# REQUIRED — the admission is conjunctive.
FACT_LABELS: dict[str, str] = {
    "C1": "no network",
    "C2": "pid/ipc/uts/cgroup isolation",
    "C3": "non-root, no privilege escalation",
    "C4": "read-only input",
    "C5": "exactly one narrow writable area",
    "C6": "no host filesystem / no credentials",
    "C7": "minimal /dev, no host devices",
    "C8": "clean env allowlist",
    "C9": "resource + time limits",
    "C10": "disposable, per-run workspace",
    "C11": "syscall surface constrained (seccomp profile active)",
}
ORDERED_FACT_IDS: tuple[str, ...] = tuple(FACT_LABELS)
REQUIRED_FACT_IDS: frozenset[str] = frozenset(ORDERED_FACT_IDS)

# Witness methods (closed vocabulary).
METHOD_FORBIDDEN_BLOCKED = "forbidden_action_blocked"  # negative probe: forbidden cmd failed
METHOD_PROPERTY_HOLDS = "property_holds"  # safe property observed true inside the cage
METHOD_PROBER_GUARANTEE = "prober_guarantee"  # lifecycle/limit enforced by the prober
METHOD_UNAVAILABLE = "unavailable"  # cannot be witnessed (→ refuse)
METHOD_PROBE_ERROR = "probe_error"  # the cage itself failed to run the probe (→ refuse)
METHOD_TIMEOUT = "timeout"  # probe exceeded its deadline (→ refuse)
METHOD_HOST_UNSUPPORTED = "host_unsupported"  # host gate failed before the battery


# --------------------------------------------------------------------------- #
# Value types.
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class FactWitness:
    """One containment fact, witnessed (or not) for one run. ``witnessed=True`` means the
    forbidden action was observed to fail / the safe property was observed to hold — not
    that the cage was configured to enforce it."""

    fact_id: str
    label: str
    witnessed: bool
    method: str
    detail: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "label": self.label,
            "witnessed": self.witnessed,
            "method": self.method,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class HostSupport:
    """Whether the host can host a real cage at all. ``ok`` gates the whole battery."""

    ok: bool
    is_linux: bool
    bwrap_present: bool
    userns_ok: bool
    seccomp_supported: bool
    cage_smoke_ok: bool
    reasons: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "is_linux": self.is_linux,
            "bwrap_present": self.bwrap_present,
            "userns_ok": self.userns_ok,
            "seccomp_supported": self.seccomp_supported,
            "cage_smoke_ok": self.cage_smoke_ok,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class CageRunAttestation:
    """The backend's full attestation record for one run: host support + per-fact witnesses
    + the derived `CageAttestation` (the admission token the Protocol consumes). This is the
    evidence carried + persisted; the plain `CageAttestation` is only the boolean gate."""

    backend_id: str
    run_id: str
    host_support: HostSupport
    witnesses: tuple[FactWitness, ...]
    attestation: CageAttestation

    @property
    def confirms_isolation(self) -> bool:
        return self.attestation.confirms_isolation

    def missing_or_unwitnessed(self) -> tuple[str, ...]:
        seen = {w.fact_id for w in self.witnesses if w.witnessed}
        return tuple(f for f in ORDERED_FACT_IDS if f not in seen)

    def to_evidence_dict(self) -> dict[str, Any]:
        return {
            "backend_id": self.backend_id,
            "run_id": self.run_id,
            "confirms_isolation": self.confirms_isolation,
            "scope": self.attestation.scope,
            "host_support": self.host_support.as_dict(),
            "witnesses": [w.as_dict() for w in self.witnesses],
            "missing_or_unwitnessed": list(self.missing_or_unwitnessed()),
        }


# --------------------------------------------------------------------------- #
# Pure decision logic (the part the acceptance criteria pin; fully testable).
# --------------------------------------------------------------------------- #


def assess_host(
    *,
    is_linux: bool,
    bwrap_present: bool,
    userns_ok: bool,
    seccomp_supported: bool,
    cage_smoke_ok: bool,
) -> HostSupport:
    """Pure host verdict. ``ok`` iff EVERY requirement holds. Reasons name each failure so
    the refusal is legible (bubblewrap missing, userns/seccomp unavailable, cage won't
    start)."""
    reasons: list[str] = []
    if not is_linux:
        reasons.append("host is not Linux")
    if not bwrap_present:
        reasons.append("bubblewrap (bwrap) not found on PATH")
    if not userns_ok:
        reasons.append("unprivileged user namespaces unavailable")
    if not seccomp_supported:
        reasons.append("seccomp kernel support unavailable")
    if not cage_smoke_ok:
        reasons.append("cage smoke test failed: bwrap could not establish an isolated cage")
    ok = not reasons
    return HostSupport(
        ok=ok,
        is_linux=is_linux,
        bwrap_present=bwrap_present,
        userns_ok=userns_ok,
        seccomp_supported=seccomp_supported,
        cage_smoke_ok=cage_smoke_ok,
        reasons=tuple(reasons),
    )


def all_required_witnessed(witnesses: tuple[FactWitness, ...]) -> bool:
    """True iff every required fact (C1–C11) has a witness with ``witnessed=True``.
    Conjunctive: one missing or unwitnessed fact → False."""
    seen = {w.fact_id for w in witnesses if w.witnessed}
    return REQUIRED_FACT_IDS <= seen


# --------------------------------------------------------------------------- #
# Probe specs (real bwrap shapes) + the prober contract.
# --------------------------------------------------------------------------- #

# The cage's isolation flags (C1–C10 enforcement). The probes run inside this cage.
BWRAP_BASE_ARGS: tuple[str, ...] = (
    "--unshare-all",  # C1 net + C2 pid/ipc/uts/cgroup + C3 user
    "--die-with-parent",  # C9
    "--new-session",  # C9
    "--clearenv",  # C8
    "--uid", "65534", "--gid", "65534",  # C3 non-root (nobody)
    "--proc", "/proc",
    "--dev", "/dev",  # C7 minimal /dev
    "--tmpfs", "/tmp",  # C5 the one declared writable area
    "--ro-bind", "/usr", "/usr",  # C4 read-only system
    "--ro-bind", "/bin", "/bin",
    "--ro-bind", "/lib", "/lib",
    "--ro-bind", "/lib64", "/lib64",
    # C5 seal the container root. bwrap's root `/` is a fresh tmpfs and is WRITABLE by
    # default, so without this a probe could `echo x > /file` — a second writable area
    # besides /tmp, violating "exactly one narrow writable area". Real-substrate finding
    # (capable-vm-noble-001, 2026-07-01): FakeProber masked this; real bwrap exposed it.
    # `--remount-ro /` runs after the mounts above; /tmp is a separate mount and stays
    # writable, so exactly one writable area remains.
    "--remount-ro", "/",
    "--chdir", "/",
)

# Sentinel env var the prober sets in bwrap's parent env; --clearenv must strip it (C8).
ENV_LEAK_SENTINEL = "BWRAP_CAGE_LEAK_SENTINEL"


@dataclass(frozen=True)
class ProbeSpec:
    """A real, reviewable negative/positive probe for one inner-command fact (C1–C8).
    ``inner`` is the forbidden action (or safe-property check) run inside the cage;
    ``method`` says how the result is read."""

    fact_id: str
    inner: tuple[str, ...]
    method: str  # METHOD_FORBIDDEN_BLOCKED | METHOD_PROPERTY_HOLDS
    note: str


# C1–C8 are inner-command probes. C9/C10 are prober-lifecycle guarantees; C11 (seccomp)
# requires a compiled BPF filter the v0 prober does not produce → unavailable → refuse.
PROBE_SPECS: dict[str, ProbeSpec] = {
    "C1": ProbeSpec("C1", ("/bin/sh", "-c", "exec 3<>/dev/tcp/1.1.1.1/53"),
                    METHOD_FORBIDDEN_BLOCKED, "outbound TCP must fail (no network)"),
    "C2": ProbeSpec("C2", ("/bin/sh", "-c",
                           'test "$(ls -1 /proc 2>/dev/null | grep -cE "^[0-9]+$")" -le 5'),
                    METHOD_PROPERTY_HOLDS, "few pids visible (pid namespace isolation)"),
    "C3": ProbeSpec("C3", ("/bin/sh", "-c", 'test "$(id -u)" -ne 0 -a "$(id -g)" -ne 0'),
                    METHOD_PROPERTY_HOLDS, "uid and gid are non-root inside"),
    "C4": ProbeSpec("C4", ("/bin/sh", "-c", "echo x > /usr/__cage_probe_should_fail__"),
                    METHOD_FORBIDDEN_BLOCKED, "write to a read-only mount must fail"),
    "C5": ProbeSpec("C5", ("/bin/sh", "-c", "echo x > /__cage_probe_outside_writable__"),
                    METHOD_FORBIDDEN_BLOCKED, "write outside the one writable area must fail"),
    "C6": ProbeSpec("C6", ("/bin/sh", "-c",
                           'test -z "$(ls -A /home 2>/dev/null)" -a ! -e /root/.ssh'),
                    METHOD_PROPERTY_HOLDS, "no host homes / ssh creds visible"),
    "C7": ProbeSpec("C7", ("/bin/sh", "-c",
                           "test ! -e /dev/sda -a ! -e /dev/nvme0n1 -a ! -e /dev/vda"),
                    METHOD_PROPERTY_HOLDS, "no host block devices in /dev"),
    "C8": ProbeSpec("C8", ("/bin/sh", "-c", f'test -z "${ENV_LEAK_SENTINEL}"'),
                    METHOD_PROPERTY_HOLDS, "host env sentinel stripped by --clearenv"),
}


class Prober(Protocol):
    """The injection seam: gather host support + witness one fact. Production =
    ``BwrapProber`` (shells to bwrap); tests = a fake (synthetic compatibility)."""

    def host_support(self) -> HostSupport: ...

    def witness(self, fact_id: str) -> FactWitness: ...


# --------------------------------------------------------------------------- #
# The real prober (lab/compat-shaped; conservative — refuses on any uncertainty).
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class BwrapProber:
    """Real bwrap prober. Shells out ONLY to bwrap probe commands (never an actor).
    Conservative: any error/timeout/uncertainty → not witnessed → refuse. v0 cannot
    witness C11 (no compiled seccomp filter), so a real battery never fully passes in v0."""

    timeout_s: int = 10

    # -- host support ------------------------------------------------------- #

    def host_support(self) -> HostSupport:
        is_linux = sys.platform.startswith("linux")
        bwrap = shutil.which("bwrap")
        bwrap_present = bwrap is not None
        userns_ok = self._userns_ok()
        seccomp_supported = self._seccomp_supported()
        cage_smoke_ok = self._cage_smoke_ok(bwrap) if bwrap_present else False
        return assess_host(
            is_linux=is_linux,
            bwrap_present=bwrap_present,
            userns_ok=userns_ok,
            seccomp_supported=seccomp_supported,
            cage_smoke_ok=cage_smoke_ok,
        )

    @staticmethod
    def _userns_ok() -> bool:
        p = Path("/proc/sys/kernel/unprivileged_userns_clone")
        if p.exists():
            try:
                return p.read_text().strip() == "1"
            except OSError:
                return False
        m = Path("/proc/sys/user/max_user_namespaces")
        if m.exists():
            try:
                return int(m.read_text().strip()) > 0
            except (OSError, ValueError):
                return False
        return False

    @staticmethod
    def _seccomp_supported() -> bool:
        try:
            return "Seccomp:" in Path("/proc/self/status").read_text()
        except OSError:
            return False

    def _cage_smoke_ok(self, bwrap: Optional[str]) -> bool:
        if not bwrap:
            return False
        try:
            r = subprocess.run(
                [bwrap, *BWRAP_BASE_ARGS, "--", "/bin/true"],
                capture_output=True, timeout=self.timeout_s,
            )
            return r.returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    # -- per-fact witnessing ------------------------------------------------ #

    def witness(self, fact_id: str) -> FactWitness:
        label = FACT_LABELS.get(fact_id, fact_id)
        if fact_id == "C11":
            # No compiled seccomp BPF filter in v0 → cannot install/witness → refuse.
            return FactWitness(
                fact_id, label, witnessed=False, method=METHOD_UNAVAILABLE,
                detail="v0 prober does not compile a seccomp filter; C11 cannot be witnessed",
            )
        if fact_id in ("C9", "C10"):
            # Lifecycle/limit guarantees: witnessed iff the cage actually starts (smoke) —
            # the prober applies the timeout (C9) and a fresh per-run workspace (C10).
            ok = self._cage_smoke_ok(shutil.which("bwrap"))
            return FactWitness(
                fact_id, label, witnessed=ok, method=METHOD_PROBER_GUARANTEE,
                detail=("prober enforces timeout + disposable workspace; cage established"
                        if ok else "cage could not be established"),
            )
        spec = PROBE_SPECS.get(fact_id)
        if spec is None:
            return FactWitness(fact_id, label, witnessed=False, method=METHOD_UNAVAILABLE,
                               detail="no probe spec")
        return self._run_inner_probe(spec)

    def _run_inner_probe(self, spec: ProbeSpec) -> FactWitness:
        bwrap = shutil.which("bwrap")
        label = FACT_LABELS[spec.fact_id]
        if not bwrap:
            return FactWitness(spec.fact_id, label, witnessed=False,
                               method=METHOD_HOST_UNSUPPORTED, detail="bwrap not found")
        argv = [bwrap, *BWRAP_BASE_ARGS, "--", *spec.inner]
        env = {"PATH": "/usr/bin:/bin", ENV_LEAK_SENTINEL: "1"}
        try:
            r = subprocess.run(argv, capture_output=True, timeout=self.timeout_s, env=env)
        except subprocess.TimeoutExpired:
            return FactWitness(spec.fact_id, label, witnessed=False, method=METHOD_TIMEOUT,
                               detail=f"probe exceeded {self.timeout_s}s")
        except (OSError, subprocess.SubprocessError) as exc:
            return FactWitness(spec.fact_id, label, witnessed=False, method=METHOD_PROBE_ERROR,
                               detail=f"probe could not run: {exc}")
        # A bwrap *infrastructure* failure (could not build the cage) is NOT a witness.
        err = (r.stderr or b"").decode("utf-8", "replace")
        if err.startswith("bwrap:"):
            return FactWitness(spec.fact_id, label, witnessed=False, method=METHOD_PROBE_ERROR,
                               detail=f"cage setup failed: {err.strip()[:200]}")
        if spec.method == METHOD_FORBIDDEN_BLOCKED:
            witnessed = r.returncode != 0  # forbidden action must FAIL
        else:  # METHOD_PROPERTY_HOLDS
            witnessed = r.returncode == 0  # safe property must HOLD
        return FactWitness(spec.fact_id, label, witnessed=witnessed, method=spec.method,
                           detail=spec.note)


# --------------------------------------------------------------------------- #
# The backend.
# --------------------------------------------------------------------------- #


@dataclass
class BwrapCage:
    """The bubblewrap-backed `HarnessCage`. Runs the pre-flight battery via the injected
    prober and mints `confirms_isolation=True` ONLY on a full C1–C11 witness. Runs no
    actor — the only subprocesses are the prober's bwrap probe commands."""

    prober: Prober = field(default_factory=BwrapProber)
    backend_id: str = BACKEND_ID

    def evaluate(self, *, run_id: str = "preflight") -> CageRunAttestation:
        """Pre-flight self-test for one run: host gate → battery → conjunctive mint."""
        hs = self.prober.host_support()
        if not hs.ok:
            attestation = CageAttestation(
                backend_id=self.backend_id, confirms_isolation=False, scope=SCOPE_NONE,
                notes="host gate failed: " + "; ".join(hs.reasons),
            )
            return CageRunAttestation(self.backend_id, run_id, hs, (), attestation)

        witnesses = tuple(self.prober.witness(fid) for fid in ORDERED_FACT_IDS)
        confirmed = all_required_witnessed(witnesses)
        attestation = CageAttestation(
            backend_id=self.backend_id,
            confirms_isolation=confirmed,
            scope=SCOPE_LIVE if confirmed else SCOPE_NONE,
            notes=("all C1–C11 witnessed" if confirmed
                   else "refused: facts not witnessed: "
                        + ",".join(f for f in ORDERED_FACT_IDS
                                   if f not in {w.fact_id for w in witnesses if w.witnessed})),
        )
        return CageRunAttestation(self.backend_id, run_id, hs, witnesses, attestation)

    def attest(self) -> CageAttestation:
        """`HarnessCage` conformance: the admission token (runs a fresh pre-flight)."""
        return self.evaluate().attestation

    def admit_live(self, request: LiveAdmissionRequest) -> LiveAdmission:
        """`HarnessCage` conformance: admit a live actor iff this run's battery passed.
        Reuses `cage.evaluate_live_admission` (the pure guard) — no separate path to True."""
        return evaluate_live_admission(self.attest(), request)


# --------------------------------------------------------------------------- #
# Evidence persistence (tainted audit store, OUTSIDE AG ingest).
# --------------------------------------------------------------------------- #


def persist_run_attestation(run_attestation: CageRunAttestation) -> Path:
    """Write the run's attestation evidence (host support + per-fact witnesses + decision)
    under the harness audit store (`harness.cage.run_dir`), OUTSIDE AG's ingest path. AG
    ingests only `actor_output.v0`; this evidence is referenced by run id / digest, never
    imported as authority. Returns the written path."""
    d = run_dir(run_attestation.run_id)
    d.mkdir(parents=True, exist_ok=True)
    out = d / "cage_attestation.json"
    out.write_text(json.dumps(run_attestation.to_evidence_dict(), indent=2, sort_keys=True))
    return out


__all__ = [
    "BACKEND_ID",
    "FACT_LABELS",
    "ORDERED_FACT_IDS",
    "REQUIRED_FACT_IDS",
    "METHOD_FORBIDDEN_BLOCKED",
    "METHOD_PROPERTY_HOLDS",
    "METHOD_PROBER_GUARANTEE",
    "METHOD_UNAVAILABLE",
    "METHOD_PROBE_ERROR",
    "METHOD_TIMEOUT",
    "METHOD_HOST_UNSUPPORTED",
    "FactWitness",
    "HostSupport",
    "CageRunAttestation",
    "assess_host",
    "all_required_witnessed",
    "BWRAP_BASE_ARGS",
    "ENV_LEAK_SENTINEL",
    "ProbeSpec",
    "PROBE_SPECS",
    "Prober",
    "BwrapProber",
    "BwrapCage",
    "persist_run_attestation",
]
