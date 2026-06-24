# SPDX-License-Identifier: Apache-2.0
"""Standing grant-use client — the real cross-repo spend-trigger seam (Slice 1b).

Status: real cross-repo client. Graduates AG's Standing consumption from the
``standing_client.py`` VERIFY-stub (which checks a receipt id) to a real
subprocess client that TRIGGERS a spend at the mint boundary — **for this seam
only**. The transition-kernel-pickup campaign, D010 (Model X).

Doctrine this module is built to honour (do not weaken):

* **AG inherits; it does not adjudicate (D010 Model X).** AG invokes
  ``standing grant use`` and consumes the ``standing.grant_use.v1`` witness
  packet. AG performs **no** local scope / expiry / spend / replay / subject
  adjudication. The returned ``refusal_class`` is Standing's verdict, recorded
  verbatim as inherited cause — never synthesized here.

* **Trigger, not verify (operator, 2026-06-23).** AG triggers Standing's spend
  (``grant use`` consumes the grant on success). There is no ``verify-use``
  surface in Standing; building one would expand Standing, not this slice.

* **Spendful op → invoke ONCE, never retry.** ``grant use`` has no idempotency
  key. If the subprocess dies *after dispatch* but before a parseable result,
  the grant **may already be spent** — that is **unknown custody**, not a
  transient error. AG refuses the mint and records ``standing_unknown_custody``;
  it MUST NOT re-invoke (a retry would double-spend, or a wrong-target retry
  becomes a DoS primitive). Same shape as the playbooks ``InterruptedUnknownEffect``
  poison: unknown custody is terminal unless reconciled, never "try again".

* **Transport failure is NOT a Standing refusal.** A binary that won't launch, a
  killed process, unparseable stdout, an unknown schema/class, a ``used`` packet
  with no digest, or a packet that doesn't match this request → ``NoVerifiedResult``.
  AG may refuse to mint because it *cannot verify* Standing, but it must never
  claim Standing *refused the grant* unless Standing emitted a typed refusal.
  (Otherwise: laundering in a JSON raincoat.)

The three outcomes are distinct TYPES, not one type with a flag — only
``GrantUsed`` carries a mintable ``receipt_digest`` (the ``standing_basis``).
Misuse (minting from a refusal or a no-result) is unrepresentable, the same
type-split discipline as ``OperationalConsumed`` / ``DemonstratedConsumed``.

This module does NOT emit receipts or touch ``activation.py`` — it returns a
verdict. The Office-2 rewire (next slice-step) records ``standing_basis`` from a
``GrantUsed``. The gate returns; the orchestrator composes.

Contract pinned against ``~/git/standing`` ``crates/standing-cli/src/main.rs``
at commit ``f101c55`` (``standing.grant_use.v1``).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Optional, Protocol

# --------------------------------------------------------------------------
# Contract constants — pinned to standing.grant_use.v1 (standing@f101c55).
# --------------------------------------------------------------------------

SCHEMA_GRANT_USE_V1 = "standing.grant_use.v1"

# Closed refusal_class set AG RECOGNIZES. This mirrors the REAL
# ``grant_use_refusal_class`` mapping in standing-cli (5 classes). NOTE: D010c's
# prose also lists ``replay``, but ``grant use`` does not emit it — so it is NOT
# here. An unrecognized class is treated as ``standing_output_unparseable`` (a
# no-verified-result), never silently accepted as a refusal.
RECOGNIZED_REFUSAL_CLASSES = frozenset(
    {
        "scope_mismatch",
        "expired",
        "already_spent",
        "subject_mismatch",
        "not_found",
    }
)

# no_verified_result reasons — the transport ≠ refusal vocabulary. Closed set.
REASON_BINARY_UNRESOLVED = "standing_binary_unresolved"
REASON_TRANSPORT_FAILED = "standing_transport_failed"
REASON_UNKNOWN_CUSTODY = "standing_unknown_custody"
REASON_OUTPUT_UNPARSEABLE = "standing_output_unparseable"
REASON_SCHEMA_UNKNOWN = "standing_schema_unknown"
REASON_RECEIPT_MISSING = "standing_receipt_missing"
REASON_REQUEST_MISMATCH = "standing_request_mismatch"

NO_VERIFIED_RESULT_REASONS = frozenset(
    {
        REASON_BINARY_UNRESOLVED,
        REASON_TRANSPORT_FAILED,
        REASON_UNKNOWN_CUSTODY,
        REASON_OUTPUT_UNPARSEABLE,
        REASON_SCHEMA_UNKNOWN,
        REASON_RECEIPT_MISSING,
        REASON_REQUEST_MISMATCH,
    }
)

# Default binary command name (the [[bin]] is "standing", not "standing-cli").
DEFAULT_STANDING_COMMAND = "standing"
# Env override (preferred resolution path — explicit, no PATH séance).
ENV_STANDING_BIN = "STANDING_BIN"
# Optional explicit DB path for Standing's own store (AG passes it to Standing's
# binary; AG never opens the DB itself).
ENV_STANDING_DB = "STANDING_DB"


# --------------------------------------------------------------------------
# Typed three-way result. Only GrantUsed is mintable.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class GrantUsed:
    """Standing spent the grant for THIS request. The only mintable outcome.

    ``receipt_digest`` is the real ``standing_basis`` activation may carry — it
    witnesses the ``Active → Used`` transition (the success path mints a real
    ``GrantUsed`` receipt; D010c asymmetric custody).
    """

    grant_id: str
    receipt_digest: str
    action: str
    target: str
    subject: Optional[str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class GrantRefused:
    """Standing refused the grant with a typed, recognized class. AG mints
    nothing; the class is recorded as inherited cause (never synthesized here)."""

    grant_id: Optional[str]
    refusal_class: str
    detail: Optional[str]
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class NoVerifiedResult:
    """AG could not obtain a verified Standing verdict. NOT a Standing refusal.

    ``reason`` is a closed ``REASON_*`` value. ``may_have_spent`` is True only
    for ``standing_unknown_custody`` — dispatched-then-died, where the grant may
    already be ``Used``. A retry is forbidden in that case (double-spend / DoS).
    """

    reason: str
    detail: Optional[str] = None
    raw: Optional[Mapping[str, Any]] = None

    @property
    def may_have_spent(self) -> bool:
        return self.reason == REASON_UNKNOWN_CUSTODY


GrantUseResult = GrantUsed | GrantRefused | NoVerifiedResult


# --------------------------------------------------------------------------
# Binary resolution — configured path preferred; never the DB.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResolvedBinary:
    """A located ``standing`` binary plus how it was found (recorded in receipts
    by the caller). ``source`` ∈ {configured, path, cargo_lab}."""

    path: str
    source: str


def resolve_standing_binary(
    env: Optional[Mapping[str, str]] = None,
    *,
    command: str = DEFAULT_STANDING_COMMAND,
) -> Optional[ResolvedBinary]:
    """Locate the ``standing`` binary. Resolution order (TRANSPORT.md step 1):

    1. ``STANDING_BIN`` explicit path — **preferred** (tests + deployment, no
       PATH séance).
    2. ``PATH`` lookup by command name — dev-acceptable.
    3. Repo-relative cargo artifact (``~/git/standing/target/{debug,release}``)
       — local lab only, not durable.
    4. Direct DB / shared store — **never** (that makes AG a Standing organ).

    Returns ``None`` when unresolved; the caller maps that to
    ``standing_binary_unresolved`` (a no-verified-result, NOT dispatched, so the
    grant is untouched).
    """
    env = os.environ if env is None else env

    explicit = env.get(ENV_STANDING_BIN)
    if explicit:
        p = Path(explicit)
        if p.is_file() and os.access(p, os.X_OK):
            return ResolvedBinary(path=str(p), source="configured")
        # An explicit-but-bad path is a configuration error worth surfacing as
        # unresolved (not silently falling through to PATH, which would mask it).
        return None

    on_path = shutil.which(command)
    if on_path:
        return ResolvedBinary(path=on_path, source="path")

    home = env.get("HOME")
    if home:
        for profile in ("debug", "release"):
            cand = Path(home) / "git" / "standing" / "target" / profile / command
            if cand.is_file() and os.access(cand, os.X_OK):
                return ResolvedBinary(path=str(cand), source="cargo_lab")

    return None


# --------------------------------------------------------------------------
# Injectable subprocess runner. Tests inject a fake; prod uses the default.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RunOutcome:
    """Result of a single subprocess invocation.

    ``dispatched`` distinguishes "never launched" (binary missing / OSError
    before exec → grant untouched → transport_failed) from "launched but no
    clean result" (``exit_code is None`` → killed/timeout → unknown custody, the
    grant may already be spent).
    """

    dispatched: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str


class SubprocessRunner(Protocol):
    def run(self, argv: list[str], *, timeout: Optional[float]) -> RunOutcome: ...


class DefaultSubprocessRunner:
    """Real runner over ``subprocess.run``. Invokes exactly once; never retries."""

    def run(self, argv: list[str], *, timeout: Optional[float]) -> RunOutcome:
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError:
            # Never launched — the grant was not touched. Safe transport failure.
            return RunOutcome(dispatched=False, exit_code=None, stdout="", stderr="binary not found")
        except subprocess.TimeoutExpired as e:
            # Launched, then we gave up waiting — the spend MAY have happened in
            # the store before we killed it. Unknown custody (exit_code=None).
            out = e.stdout or ""
            err = e.stderr or ""
            so = out.decode() if isinstance(out, bytes) else out
            se = err.decode() if isinstance(err, bytes) else err
            return RunOutcome(dispatched=True, exit_code=None, stdout=so, stderr=se)
        except OSError as e:
            # Failed to launch (permissions, etc.) — not dispatched, grant untouched.
            return RunOutcome(dispatched=False, exit_code=None, stdout="", stderr=str(e))
        return RunOutcome(
            dispatched=True,
            exit_code=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
        )


# --------------------------------------------------------------------------
# The client.
# --------------------------------------------------------------------------


class StandingGrantUseClient:
    """Triggers a Standing grant-use spend and returns Standing's verdict.

    Construct with an injected ``runner`` (tests pass a fake returning canned
    ``standing.grant_use.v1`` stdout; prod uses ``DefaultSubprocessRunner``).
    The client builds argv, invokes ONCE, parses the witness packet, and triages
    into the typed three-way result. It does no adjudication and no retry.
    """

    def __init__(
        self,
        runner: Optional[SubprocessRunner] = None,
        *,
        binary: Optional[ResolvedBinary] = None,
        env: Optional[Mapping[str, str]] = None,
        db_path: Optional[str] = None,
        timeout: Optional[float] = 30.0,
    ):
        self._runner = runner if runner is not None else DefaultSubprocessRunner()
        self._env = os.environ if env is None else env
        # Allow an explicitly-injected binary (tests / pinned deployment); else
        # resolve lazily at use() time so a fake runner never needs a real binary.
        self._binary = binary
        self._db_path = db_path if db_path is not None else self._env.get(ENV_STANDING_DB)
        self._timeout = timeout

    # -- argv construction (pinned to the real CLI signature) ----------------

    def _build_argv(
        self,
        binary_path: str,
        *,
        grant_id: str,
        identity_path: str,
        secret: str,
        action: str,
        target: str,
        evidence: str,
    ) -> list[str]:
        argv = [binary_path]
        if self._db_path:
            argv += ["--db-path", self._db_path]
        argv += [
            "grant",
            "use",
            "--id",
            grant_id,
            "--identity",
            identity_path,
            "--secret",
            secret,
            "--action",
            action,
            "--target",
            target,
            "--evidence",
            evidence,
            "--json",
        ]
        return argv

    # -- the seam -------------------------------------------------------------

    def use(
        self,
        *,
        grant_id: str,
        action: str,
        target: str,
        identity_path: str,
        secret: str,
        evidence: str = "{}",
    ) -> GrantUseResult:
        """Invoke ``standing grant use … --json`` ONCE and triage the verdict.

        Returns one of ``GrantUsed`` / ``GrantRefused`` / ``NoVerifiedResult``.
        Never retries; on a dispatched-then-died invocation returns
        ``NoVerifiedResult(standing_unknown_custody)`` (the grant may be spent).
        """
        binary = self._binary or resolve_standing_binary(self._env)
        if binary is None:
            return NoVerifiedResult(
                reason=REASON_BINARY_UNRESOLVED,
                detail="standing binary not resolved (STANDING_BIN / PATH / cargo lab)",
            )

        argv = self._build_argv(
            binary.path,
            grant_id=grant_id,
            identity_path=identity_path,
            secret=secret,
            action=action,
            target=target,
            evidence=evidence,
        )
        outcome = self._runner.run(argv, timeout=self._timeout)
        return self._triage(outcome, grant_id=grant_id, action=action, target=target)

    def _triage(
        self,
        outcome: RunOutcome,
        *,
        grant_id: str,
        action: str,
        target: str,
    ) -> GrantUseResult:
        # Never launched → the grant was not touched. Safe transport failure.
        if not outcome.dispatched:
            return NoVerifiedResult(
                reason=REASON_TRANSPORT_FAILED,
                detail=outcome.stderr or "subprocess not dispatched",
            )

        packet = _try_parse_packet(outcome.stdout)

        if packet is None:
            # Dispatched but no parseable witness on stdout.
            if outcome.exit_code is None:
                # Killed / timed out mid-flight — the spend may have committed in
                # Standing's store before stdout reached us. UNKNOWN CUSTODY.
                return NoVerifiedResult(
                    reason=REASON_UNKNOWN_CUSTODY,
                    detail="dispatched then died with no parseable result; grant may be spent — do not retry",
                )
            # Clean exit, prose-only (Standing's None branch: internal/transport
            # error surfaced as prose, NOT a typed grant refusal). "Cannot verify."
            return NoVerifiedResult(
                reason=REASON_TRANSPORT_FAILED,
                detail=(outcome.stderr or outcome.stdout or "no JSON witness on stdout").strip()[:500],
            )

        if packet.get("schema") != SCHEMA_GRANT_USE_V1:
            return NoVerifiedResult(
                reason=REASON_SCHEMA_UNKNOWN,
                detail=f"unexpected schema: {packet.get('schema')!r}",
                raw=packet,
            )

        result = packet.get("result")

        if result == "used":
            digest = packet.get("receipt_digest")
            if not isinstance(digest, str) or not digest:
                # used without a real digest is not a mintable basis (D010c).
                return NoVerifiedResult(
                    reason=REASON_RECEIPT_MISSING,
                    detail="result=used but receipt_digest absent/empty",
                    raw=packet,
                )
            # Witness-integrity (NOT scope adjudication): the packet must be about
            # THIS request. Standing already decided scope; this only confirms the
            # witness corresponds to what we asked, defeating stale/confused packets.
            attempted = packet.get("attempted") or {}
            if attempted.get("action") != action or attempted.get("target") != target:
                return NoVerifiedResult(
                    reason=REASON_REQUEST_MISMATCH,
                    detail=(
                        f"used packet attempted={attempted!r} does not match "
                        f"request action={action!r} target={target!r}"
                    ),
                    raw=packet,
                )
            return GrantUsed(
                grant_id=str(packet.get("grant_id") or grant_id),
                receipt_digest=digest,
                action=action,
                target=target,
                subject=packet.get("subject"),
                raw=packet,
            )

        if result == "refused":
            klass = packet.get("refusal_class")
            if isinstance(klass, str) and klass in RECOGNIZED_REFUSAL_CLASSES:
                return GrantRefused(
                    grant_id=packet.get("grant_id"),
                    refusal_class=klass,
                    detail=packet.get("detail"),
                    raw=packet,
                )
            # result=refused but the class is unknown/missing — Standing refused,
            # but AG cannot faithfully record WHY. Don't invent a class; record
            # no-verified-result. (Mint outcome is identical: REFUSED_NO_STANDING.)
            return NoVerifiedResult(
                reason=REASON_OUTPUT_UNPARSEABLE,
                detail=f"refused with unrecognized refusal_class: {klass!r}",
                raw=packet,
            )

        # Unknown ``result`` value entirely.
        return NoVerifiedResult(
            reason=REASON_OUTPUT_UNPARSEABLE,
            detail=f"unknown result value: {result!r}",
            raw=packet,
        )


def _try_parse_packet(stdout: str) -> Optional[dict[str, Any]]:
    """Parse the last non-empty stdout line as a JSON object, or None.

    Standing prints the witness packet as a single JSON line; we tolerate
    leading prose/log lines by scanning from the end for the first line that
    parses to a JSON object.
    """
    if not stdout:
        return None
    for line in reversed(stdout.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            return obj
    return None
