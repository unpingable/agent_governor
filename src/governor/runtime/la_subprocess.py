# SPDX-License-Identifier: Apache-2.0
"""Subprocess bridge to the real Linear Accountant `la_cli` transport.

Replaces the injected contract-faithful seam on the bootstrap-lab path with the
**real** spendability authority: AG spawns one `la_cli` process per supervised
session (the session's in-memory accountant), seeds its allocation, and routes
capacity decisions to it. The Rust accountant — not AG — decides spendability;
AG only carries the request and records the decision (atlas spine:
spendability(LA) → execution(AG) → receipt).

Boundary record: the banner is parsed into :class:`LABoundaryIdentity`
(la/version/commit/protocol + binary path + the LA repo HEAD) so AG's durable
event chain pins the exact LA version/commit at the constellation edge.

Fail-closed everywhere (operator requirement #3): a dead process, a read
timeout, malformed JSON, or a `fail_closed` error line all map to a decision the
``LinearAccountantClient`` treats as a refusal — never a silent allow. The two
public callables match the injected-callable signature the client expects, so
the client + LabGate are reused unchanged (only the seam becomes real).

Protocol: see ``~/git/linearaccountant/docs/LA_CLI_PROTOCOL.md``.
"""

from __future__ import annotations

import json
import os
import select
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

DEFAULT_LA_CLI = os.path.expanduser("~/git/linearaccountant/target/debug/la_cli")


class LASubprocessError(Exception):
    """The transport could not be established (binary missing / no banner)."""


@dataclass(frozen=True)
class LABoundaryIdentity:
    """What AG records at the constellation edge: exactly which LA it talked to."""

    la: str
    version: str
    commit: str          # build-time LA_GIT_COMMIT, or "unknown"
    protocol: str
    binary_path: str
    repo_commit: Optional[str]  # `git -C <la repo> rev-parse HEAD` at launch

    def to_dict(self) -> dict[str, Any]:
        return {
            "la": self.la,
            "version": self.version,
            "commit": self.commit,
            "protocol": self.protocol,
            "binary_path": self.binary_path,
            "repo_commit": self.repo_commit,
        }


def _tsv(cmd: str, fields: dict[str, Any]) -> str:
    """Build one TAB-separated key=value command line. Values may not contain a
    TAB/newline (the wire framing) — reject if they do (fail-closed at the edge)."""
    parts = [f"cmd={cmd}"]
    for k, v in fields.items():
        if v is None:
            continue
        s = str(v)
        if "\t" in s or "\n" in s:
            raise LASubprocessError(f"field {k!r} contains a wire separator")
        parts.append(f"{k}={s}")
    return "\t".join(parts)


class LASubprocess:
    """One `la_cli` process; session-lived. Construct, :meth:`start`, use the
    callables, :meth:`close` at session end."""

    def __init__(
        self,
        binary_path: str | None = None,
        *,
        repo_dir: str | None = None,
        timeout: float = 5.0,
    ) -> None:
        self.binary_path = binary_path or os.environ.get("GOVERNOR_LA_CLI", DEFAULT_LA_CLI)
        self.repo_dir = repo_dir
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self.identity: LABoundaryIdentity | None = None

    # -- lifecycle ---------------------------------------------------------- #

    def start(self) -> LABoundaryIdentity:
        if not Path(self.binary_path).exists():
            raise LASubprocessError(f"la_cli not found at {self.binary_path}")
        self._proc = subprocess.Popen(
            [self.binary_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        banner = self._read_line()
        if banner is None:
            self.close()
            raise LASubprocessError("la_cli produced no banner")
        try:
            b = json.loads(banner)
        except json.JSONDecodeError as e:
            self.close()
            raise LASubprocessError(f"la_cli banner not JSON: {banner!r}") from e
        self.identity = LABoundaryIdentity(
            la=b.get("la", ""),
            version=b.get("version", ""),
            commit=b.get("commit", "unknown"),
            protocol=b.get("protocol", ""),
            binary_path=self.binary_path,
            repo_commit=self._repo_commit(),
        )
        return self.identity

    def close(self) -> None:
        if self._proc is None:
            return
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.terminate()
            try:
                self._proc.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        except Exception:
            pass
        finally:
            self._proc = None

    def __enter__(self) -> LASubprocess:
        self.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    # -- transport ---------------------------------------------------------- #

    def _read_line(self) -> str | None:
        """Read one response line within the timeout, else None (fail-closed)."""
        if self._proc is None or self._proc.stdout is None:
            return None
        r, _, _ = select.select([self._proc.stdout], [], [], self.timeout)
        if not r:
            return None  # timeout
        line = self._proc.stdout.readline()
        if not line:
            return None  # EOF / process died
        return line.strip()

    def _exchange(self, cmd: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        """Send one command, return the parsed JSON response, or None on any
        transport failure (dead process / timeout / malformed / fail_closed)."""
        if self._proc is None or self._proc.stdin is None or self._proc.poll() is not None:
            return None
        try:
            line = _tsv(cmd, fields)
        except LASubprocessError:
            return None
        try:
            self._proc.stdin.write(line + "\n")
            self._proc.stdin.flush()
        except (BrokenPipeError, ValueError, OSError):
            return None
        resp = self._read_line()
        if resp is None:
            return None
        try:
            obj = json.loads(resp)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict) or obj.get("fail_closed"):
            return None
        return obj

    # -- operations --------------------------------------------------------- #

    def deposit(self, scope: str, amount: int, *, now: int = 0) -> dict[str, Any] | None:
        """Seed the session's bounded allocation. Recorded in LA's ledger."""
        return self._exchange("deposit", {"scope": scope, "amount": amount})

    def request_capacity(self, la_request: dict[str, Any], now: int) -> dict[str, Any]:
        """Injected-callable shape. Fail-closed → Denied (→ capacity refusal)."""
        resp = self._exchange("request_capacity", {
            "request_id": la_request.get("request_id"),
            "actor": la_request.get("actor"),
            "action": la_request.get("action"),
            "target": la_request.get("target"),
            "scope": la_request.get("scope"),
            "requested_capacity": la_request.get("requested_capacity"),
            "eligibility_reference": la_request.get("eligibility_reference"),
            "eligibility_valid_until": la_request.get("eligibility_valid_until"),
            "expires_after": la_request.get("expires_after"),
            "idempotency_key": la_request.get("idempotency_key"),
            "tick": now,
        })
        if resp is None:
            return {"decision": "Denied", "denial_reason": "la_transport_failure", "receipt": "none"}
        return resp

    def consume(self, la_request: dict[str, Any], now: int) -> dict[str, Any]:
        """Injected-callable shape. Fail-closed → a decision-less dict the client
        maps to a capacity refusal (closed-set invariant preserved)."""
        resp = self._exchange("consume", {
            "consumption_event_id": la_request.get("consumption_event_id"),
            "token_id": la_request.get("token_id"),
            "actor": la_request.get("actor"),
            "action": la_request.get("action"),
            "target": la_request.get("target"),
            "amount": la_request.get("amount"),
            "scope": la_request.get("scope"),
            "tick": now,
        })
        if resp is None:
            return {"decision": "TransportFailure", "detail": "la_transport_failure"}
        return resp

    def _repo_commit(self) -> Optional[str]:
        repo = self.repo_dir or str(Path(self.binary_path).resolve().parents[2]) \
            if "target" in self.binary_path else self.repo_dir
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
