"""Governor verifier wrapper — mechanical guard against masked exit codes.

> A verifier result is admissible only when the verifier's own exit status is
> observed. Everything else is theater with scrollback.

The failure class this exists to refuse (scar, agent_gov/NQ 2026-06-12): a
migration shipped with three red tests because verification ran through
``cargo test | tail`` — a pipeline returns the *last* command's exit code, so
the tested command's failure was laundered into a green-looking 0.

This module wraps the (already exit-safe) CI-lane runner :func:`ci_wrap` with a
pre-flight command-safety analysis. ``ci_wrap`` runs the child via
``subprocess.run`` with output to temp files (no pipe, no shell), so the child's
exit code is captured directly. The only way to mask an exit through this path
is to ask the wrapper to run a *shell pipeline* (``bash -c "cargo test | tail"``)
where the shell's own exit is the downstream filter's, not the verifier's. This
module detects exactly that and refuses it unless the pipeline preserves the
exit source (``set -o pipefail`` / ``PIPESTATUS``).

Receipts carry three provenance fields so a downstream audit can refuse
masked-risk evidence mechanically:

- ``verifier_exit_observed``: bool — did we actually observe the tested
  command's exit (vs. refuse before running)?
- ``verifier_exit_source``: ``child_exit`` | ``pipefail_preserved`` | ``unknown``
- ``masked_exit_risk``: bool — true if a pipe without pipefail was present.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .ci import CiReceiptBundle, _write_bundle, ci_wrap
from .gate_receipt import canonical_json, create_receipt

VERIFY_GATE = "verifier"
VERIFY_SUBJECT_KIND = "verifier"

# verifier_exit_source values
EXIT_CHILD = "child_exit"
EXIT_PIPEFAIL = "pipefail_preserved"
EXIT_UNKNOWN = "unknown"

# Exit code the wrapper returns when it refuses to run a masked-risk command.
REFUSAL_EXIT = 2

_SHELLS = frozenset({"sh", "bash", "zsh", "dash", "ksh"})
_DEFAULT_RECEIPT_DIR = Path(".governor/verify_receipts")


@dataclass(frozen=True)
class CommandSafety:
    """The exit-code-masking analysis of a command argv."""

    shell_used: bool
    has_pipe: bool
    has_pipefail: bool
    masked_exit_risk: bool
    exit_source: str
    reason: str


@dataclass(frozen=True)
class VerifyResult:
    refused: bool
    exit_code: int
    receipt: object | None  # GateReceipt | None (avoid import cycle in annotation)
    receipt_path: Path | None
    safety: CommandSafety


def _basename(arg: str) -> str:
    return os.path.basename(arg)


# Receipt-filename label length cap. The label is cosmetic (it names the file on
# disk), so a generous-but-bounded slug keeps the trail readable without
# unbounded filenames.
_LABEL_MAXLEN = 40


def _slugify(text: str) -> str:
    """Conservative filename-safe slug: lowercased, non-alphanumerics → ``_``,
    stripped, truncated. Sanitizes both operator labels (so a label can never
    traverse paths or carry unsafe chars) and the command-basename fallback."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:_LABEL_MAXLEN]


def _command_label(command: list[str]) -> str:
    """Fallback receipt label when the operator supplies none: a slug of the
    command's program name only — ``basename(argv[0])``. This is NOT a shell
    parser; ``["lake", "build"]`` → ``"lake"``, ``["cargo", "test"]`` →
    ``"cargo"``. Returns ``""`` for an empty command (caller then falls back to
    the ``ci_wrap_{ci_kind}`` name)."""
    if not command:
        return ""
    return _slugify(_basename(command[0]))


def _contains_pipe(script: str) -> bool:
    """True if *script* contains a pipe operator (``|``) that is not a logical
    OR (``||``).

    Deliberately conservative: a ``|`` inside quotes or a regex over-flags as a
    pipe, but over-flagging is safe here — it only demands that the author make
    the exit source explicit (``set -o pipefail``). Under-flagging would let a
    real masking pipe through, which is the failure we are refusing.
    """
    return "|" in script.replace("||", "")


def analyze_command(argv: list[str]) -> CommandSafety:
    """Classify how *argv*'s exit code will reach us.

    - Direct exec (``["cargo", "test"]``): ``subprocess.run`` runs the binary
      directly; its exit is the binary's. Safe — ``child_exit``.
    - Shell ``-c`` with a pipe and no pipefail: the shell exits with the last
      pipeline stage's code, masking the verifier. ``masked_exit_risk``.
    - Shell ``-c`` with a pipe and ``pipefail``/``PIPESTATUS``: the exit source
      is preserved. ``pipefail_preserved``.
    - Shell ``-c`` without a pipe: the shell's exit honestly reflects the
      script. ``child_exit``.
    """
    if not argv:
        return CommandSafety(
            shell_used=False,
            has_pipe=False,
            has_pipefail=False,
            masked_exit_risk=False,
            exit_source=EXIT_UNKNOWN,
            reason="empty command",
        )

    shell_used = _basename(argv[0]) in _SHELLS and "-c" in argv
    if not shell_used:
        return CommandSafety(
            shell_used=False,
            has_pipe=False,
            has_pipefail=False,
            masked_exit_risk=False,
            exit_source=EXIT_CHILD,
            reason="direct exec (no shell); child exit observed directly",
        )

    # The script is the token immediately after -c.
    try:
        script = argv[argv.index("-c") + 1]
    except (ValueError, IndexError):
        script = ""

    has_pipe = _contains_pipe(script)
    has_pipefail = "pipefail" in script or "PIPESTATUS" in script

    if has_pipe and not has_pipefail:
        return CommandSafety(
            shell_used=True,
            has_pipe=True,
            has_pipefail=False,
            masked_exit_risk=True,
            exit_source=EXIT_UNKNOWN,
            reason=(
                "shell pipeline without `set -o pipefail` / PIPESTATUS: the "
                "shell exits with the last stage's code, masking the verifier's"
            ),
        )
    if has_pipe and has_pipefail:
        return CommandSafety(
            shell_used=True,
            has_pipe=True,
            has_pipefail=True,
            masked_exit_risk=False,
            exit_source=EXIT_PIPEFAIL,
            reason="shell pipeline with pipefail/PIPESTATUS; exit source preserved",
        )
    return CommandSafety(
        shell_used=True,
        has_pipe=False,
        has_pipefail=has_pipefail,
        masked_exit_risk=False,
        exit_source=EXIT_CHILD,
        reason="shell script without a pipe; exit observed directly",
    )


def _emit_refusal_receipt(
    command: list[str],
    ci_kind: str,
    safety: CommandSafety,
    receipt_out: Path,
    timestamp: str | None,
    label: str | None = None,
):
    """Mint a block receipt recording that a masked-risk command was refused
    *before* running it (so no green can ever be claimed from it)."""
    evidence = {
        "verifier_exit_observed": False,
        "verifier_exit_source": EXIT_UNKNOWN,
        "masked_exit_risk": True,
        "shell_used": safety.shell_used,
        "command": command,
        "ci_kind": ci_kind,
        "refused": True,
        "safety_reason": safety.reason,
    }
    subject_bytes = canonical_json(
        {"command": command, "ci_kind": ci_kind, "refused": True}
    )
    receipt = create_receipt(
        gate=VERIFY_GATE,
        verdict="block",
        subject_kind=VERIFY_SUBJECT_KIND,
        subject_bytes=subject_bytes,
        evidence_bundle=evidence,
        gate_config={"ci_kind": ci_kind, "policy": "refuse_masked_exit"},
        timestamp=timestamp,
    )
    bundle = CiReceiptBundle(receipt=receipt, evidence=evidence)
    path = _write_bundle(bundle, receipt_out, label=label)
    return receipt, path


def verify_run(
    command: list[str],
    ci_kind: str = "unit_tests",
    receipt_out: Path | None = None,
    *,
    allow_masked: bool = False,
    cwd: Path | None = None,
    timestamp: str | None = None,
    label: str | None = None,
) -> VerifyResult:
    """Run *command* as a verifier and emit a receipt whose verdict is backed by
    the command's own exit code.

    ``label`` names the on-disk receipt file. When given it is sanitized and
    preferred; when omitted it falls back to a slug of the command's program name
    (``basename(argv[0])``) so a ``lake build`` receipt is named ``lake_*`` rather
    than mislabeled by ``ci_kind``. The label is cosmetic — it affects ONLY the
    filename, never ``receipt_id`` / subject bytes / hashed evidence (the command
    is already recorded in evidence as ``command_display``). Both the success and
    the masked-exit-refusal paths use it.

    Refuses (does not run; verdict=block, ``verifier_exit_observed=False``) when
    the command is a shell pipeline that would mask the verifier's exit, unless
    ``allow_masked`` is set *and* the pipeline preserves the exit source. There
    is no way to get ``verifier_exit_observed=True`` from a masked pipeline.
    """
    out = receipt_out or _DEFAULT_RECEIPT_DIR
    if out == _DEFAULT_RECEIPT_DIR:
        out.mkdir(parents=True, exist_ok=True)

    # Operator label preferred; else a conservative basename(argv[0]) slug. Used
    # identically on the success and masked-exit-refusal paths; filename-only.
    effective_label = _slugify(label) if label else _command_label(command)
    effective_label = effective_label or None

    safety = analyze_command(command)

    if safety.masked_exit_risk and not allow_masked:
        receipt, path = _emit_refusal_receipt(
            command, ci_kind, safety, out, timestamp, label=effective_label
        )
        return VerifyResult(
            refused=True,
            exit_code=REFUSAL_EXIT,
            receipt=receipt,
            receipt_path=path,
            safety=safety,
        )

    extra = {
        "verifier_exit_observed": True,
        "verifier_exit_source": safety.exit_source,
        "masked_exit_risk": safety.masked_exit_risk,
        "shell_used": safety.shell_used,
        "cwd": str(Path(cwd).resolve()) if cwd else os.getcwd(),
        "safety_reason": safety.reason,
    }
    result = ci_wrap(
        command,
        ci_kind,
        out,
        cwd=cwd,
        timestamp=timestamp,
        extra_evidence=extra,
        gate=VERIFY_GATE,
        subject_kind=VERIFY_SUBJECT_KIND,
        label=effective_label,
    )
    return VerifyResult(
        refused=False,
        exit_code=result.exit_code,
        receipt=result.receipt,
        receipt_path=result.receipt_path,
        safety=safety,
    )
