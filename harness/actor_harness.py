# SPDX-License-Identifier: Apache-2.0
"""H1 — the smallest external/offline actor harness (OUTSIDE AG).

> H1 may run the actor; AG may only ingest the captured artifact.

This module is a *foreign producer*. It captures what an offline actor returned
(a transcript + the actor's self-reported claims) into an inert ``actor_output.v0``
JSON envelope — the wire artifact AG's S7 normalizer ingests. It runs no AG code.

What this slice does NOT do (by construction, not by guard):

- It does **not** import ``governor`` / S5 / S7 / ration-card / admission / validator.
  The contract between H1 and AG is the JSON envelope below, redeclared here on
  purpose because H1 is a foreign producer. Drift is caught by an AG-side contract
  test (AG parses H1's JSON with ``ActorOutput.from_dict``; if the shape drifts, the
  parse fails loudly).
- It does **not** run a live Claude/Codex, spawn the actor, apply a patch, touch git,
  the network, or a subprocess. ``captured_text`` is *supplied* to this slice — the
  "capture" here is structuring a provided reply, not generating one. Live execution
  is a later, explicit H-series slice.
- It has **no** path that produces a verified test result, a verifier receipt, an
  admission receipt, or any object that can satisfy S5. The ONLY thing it can emit is
  ``actor_output.v0`` testimony. ``claimed_test_results`` are the actor's *claims*;
  AG (Model B) represents them as ``not_run`` and S5 still refuses them. Only an
  AG-owned independent verifier may ever make a required test ``passed``.

## The wire shape — ``actor_output.v0`` (redeclared; the contract)

```
{
  "schema_version": "actor_output.v0",
  "actor_output_id": str,                # H1-assigned id for this capture
  "handoff_packet_id": str,              # binds to the S6 handoff_id it answers
  "actor_kind": "claude" | "codex",      # must match the handoff
  "captured_text": str,                  # the actor's reply / transcript (advisory)
  "captured_at": str,                    # descriptive timestamp (never gates)
  "capture_origin": str,                 # descriptive label (NOT a typed origin enum)
  "claimed_files_touched": [str, ...],   # the actor's claim (declared, not read)
  "claimed_commands_run": [str, ...],    # the actor's claim
  "claimed_test_results": [              # the actor's claims — NOT verifier receipts
     {"command": str, "claimed_status": "passed"|"failed"|"unknown",
      "exit_code": int|null, "summary": str|null}, ...],
  "authority_claims": [str, ...]         # anything the actor asserted as authority
}                                        #   (AG strips + refuses these)
```
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from typing import Any, Optional

# --- the wire contract, redeclared independently of governor ---------------- #
SCHEMA_VERSION = "actor_output.v0"
ACTOR_KINDS = frozenset({"claude", "codex"})
CLAIMED_STATUSES = frozenset({"passed", "failed", "unknown"})

# The closed envelope key set (documentation + a local well-formedness guard). This
# mirrors AG's parser, but H1 owns its own copy: the JSON is the contract.
ENVELOPE_KEYS: tuple[str, ...] = (
    "schema_version",
    "actor_output_id",
    "handoff_packet_id",
    "actor_kind",
    "captured_text",
    "captured_at",
    "capture_origin",
    "claimed_files_touched",
    "claimed_commands_run",
    "claimed_test_results",
    "authority_claims",
)


class HarnessError(ValueError):
    """A local well-formedness rejection raised while building an envelope.

    This is H1 keeping its OWN output honest before it crosses the wall; it is not
    an AG verdict. AG re-validates everything on ingest with its own parser."""


# --------------------------------------------------------------------------- #
# Builders (pure; no IO, no governor).
# --------------------------------------------------------------------------- #


def build_claimed_test(
    command: str,
    claimed_status: str,
    *,
    exit_code: Optional[int] = None,
    summary: Optional[str] = None,
) -> dict[str, Any]:
    """One test the actor CLAIMS it ran. A claim, never a verifier receipt."""
    if not isinstance(command, str) or command == "":
        raise HarnessError("claimed test command must be a non-empty string")
    if claimed_status not in CLAIMED_STATUSES:
        raise HarnessError(
            f"claimed_status {claimed_status!r} not in {sorted(CLAIMED_STATUSES)}"
        )
    return {
        "command": command,
        "claimed_status": claimed_status,
        "exit_code": exit_code,
        "summary": summary,
    }


def _str_tuple(name: str, raw: Iterable[Any]) -> list[str]:
    if isinstance(raw, (str, bytes)):
        raise HarnessError(f"{name} must be a list of strings, not a string")
    out = list(raw)
    if not all(isinstance(x, str) for x in out):
        raise HarnessError(f"{name} must be a list of strings")
    return out


def build_actor_output(
    *,
    actor_output_id: str,
    handoff_packet_id: str,
    actor_kind: str,
    captured_text: str,
    captured_at: str,
    capture_origin: str,
    claimed_files_touched: Iterable[str] = (),
    claimed_commands_run: Iterable[str] = (),
    claimed_test_results: Iterable[Mapping[str, Any]] = (),
    authority_claims: Iterable[str] = (),
) -> dict[str, Any]:
    """Build a well-formed ``actor_output.v0`` envelope dict.

    Pure: returns a dict, writes nothing. There is deliberately NO parameter through
    which a verified test result / verifier receipt / authority grant could enter —
    the only test channel is ``claimed_test_results`` (testimony)."""
    for name, val in (
        ("actor_output_id", actor_output_id),
        ("handoff_packet_id", handoff_packet_id),
        ("captured_text", captured_text),
        ("captured_at", captured_at),
        ("capture_origin", capture_origin),
    ):
        if not isinstance(val, str) or val == "":
            raise HarnessError(f"{name} must be a non-empty string")
    if actor_kind not in ACTOR_KINDS:
        raise HarnessError(f"actor_kind {actor_kind!r} not in {sorted(ACTOR_KINDS)}")

    claimed_tests: list[dict[str, Any]] = []
    for entry in claimed_test_results:
        if not isinstance(entry, Mapping):
            raise HarnessError("each claimed_test_results entry must be a mapping")
        # Re-validate through the builder so closed vocab is enforced uniformly.
        claimed_tests.append(
            build_claimed_test(
                str(entry.get("command", "")),
                str(entry.get("claimed_status", "")),
                exit_code=entry.get("exit_code"),
                summary=entry.get("summary"),
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "actor_output_id": actor_output_id,
        "handoff_packet_id": handoff_packet_id,
        "actor_kind": actor_kind,
        "captured_text": captured_text,
        "captured_at": captured_at,
        "capture_origin": capture_origin,
        "claimed_files_touched": _str_tuple(
            "claimed_files_touched", claimed_files_touched
        ),
        "claimed_commands_run": _str_tuple(
            "claimed_commands_run", claimed_commands_run
        ),
        "claimed_test_results": claimed_tests,
        "authority_claims": _str_tuple("authority_claims", authority_claims),
    }


def capture_from_handoff(
    handoff: Mapping[str, Any],
    *,
    actor_output_id: str,
    captured_text: str,
    captured_at: str,
    capture_origin: str = "h1-harness-stub",
    claimed_files_touched: Iterable[str] = (),
    claimed_commands_run: Iterable[str] = (),
    claimed_test_results: Iterable[Mapping[str, Any]] = (),
    authority_claims: Iterable[str] = (),
) -> dict[str, Any]:
    """Bind a capture to the S6 handoff it answers.

    Reads ONLY ``handoff_id`` and ``actor_kind`` from the handoff manifest (plain
    JSON; H1 does not verify the seal — that is AG's job, and reimplementing the
    canonicalization here would invite drift). The produced envelope's
    ``handoff_packet_id`` / ``actor_kind`` are what AG's S7 binds against; a mismatch
    is refused on AG's side (``handoff_binding_mismatch`` / ``actor_kind_mismatch``)."""
    if not isinstance(handoff, Mapping):
        raise HarnessError("handoff manifest must be a mapping")
    handoff_id = handoff.get("handoff_id")
    actor_kind = handoff.get("actor_kind")
    if not isinstance(handoff_id, str) or handoff_id == "":
        raise HarnessError("handoff manifest missing a string 'handoff_id'")
    if not isinstance(actor_kind, str) or actor_kind == "":
        raise HarnessError("handoff manifest missing a string 'actor_kind'")
    return build_actor_output(
        actor_output_id=actor_output_id,
        handoff_packet_id=handoff_id,
        actor_kind=actor_kind,
        captured_text=captured_text,
        captured_at=captured_at,
        capture_origin=capture_origin,
        claimed_files_touched=claimed_files_touched,
        claimed_commands_run=claimed_commands_run,
        claimed_test_results=claimed_test_results,
        authority_claims=authority_claims,
    )


# --------------------------------------------------------------------------- #
# Serialization / IO (the wall is a file).
# --------------------------------------------------------------------------- #


def to_json(envelope: Mapping[str, Any]) -> str:
    """Deterministic JSON text (sorted keys) for the envelope."""
    return json.dumps(envelope, sort_keys=True, indent=2)


def write_actor_output(envelope: Mapping[str, Any], path: str) -> None:
    """Write the envelope to ``path`` as JSON. This is the only filesystem effect
    H1 has, and it writes a single inert evidence artifact."""
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(to_json(envelope))
        fh.write("\n")


# --------------------------------------------------------------------------- #
# Sample (acceptance: "harness/ can emit a sample actor_output.v0.json").
# --------------------------------------------------------------------------- #


def sample_actor_output() -> dict[str, Any]:
    """A canned, deterministic capture — the laundering specimen.

    The actor CLAIMS its required test passed. When AG ingests this and runs S7→S5,
    S5 must STILL refuse it (``required_test_not_passing``): the actor's word cannot
    green its own gate. The AG-side contract test asserts exactly that."""
    return build_actor_output(
        actor_output_id="ao-sample-0001",
        handoff_packet_id="handoff-sample-0001",
        actor_kind="claude",
        captured_text=(
            "I edited src/widget/core.py to fix the off-by-one and ran the suite; "
            "everything is green and safe to commit."
        ),
        captured_at="2026-06-30T00:00:00Z",
        capture_origin="h1-harness-stub",
        claimed_files_touched=("src/widget/core.py",),
        claimed_commands_run=("pytest tests/widget -q",),
        claimed_test_results=(
            build_claimed_test(
                "pytest tests/widget -q",
                "passed",
                exit_code=0,
                summary="42 passed",
            ),
        ),
        authority_claims=("tests_pass", "safe_to_commit"),
    )


# --------------------------------------------------------------------------- #
# CLI.
# --------------------------------------------------------------------------- #


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="harness.actor_harness",
        description="H1: capture an offline actor's reply into an actor_output.v0 "
        "JSON artifact (outside AG; produces testimony only).",
    )
    parser.add_argument(
        "--sample",
        action="store_true",
        help="emit the canned laundering-specimen sample (needs no other inputs)",
    )
    parser.add_argument(
        "--handoff",
        help="path to the S6 handoff.json this capture answers (binds id + actor_kind)",
    )
    parser.add_argument(
        "--captured-text-file",
        help="path to a file holding the actor's reply / transcript",
    )
    parser.add_argument(
        "--actor-output-id",
        default="ao-0001",
        help="id to assign this capture (default: ao-0001)",
    )
    parser.add_argument(
        "--capture-origin",
        default="h1-harness-stub",
        help="descriptive origin label (NOT a typed origin enum)",
    )
    parser.add_argument(
        "--out",
        help="write the envelope JSON here (default: stdout)",
    )
    args = parser.parse_args(argv)

    if args.sample:
        envelope = sample_actor_output()
    else:
        if not args.handoff or not args.captured_text_file:
            parser.error(
                "non-sample mode requires --handoff and --captured-text-file "
                "(or use --sample)"
            )
        with open(args.handoff, encoding="utf-8") as fh:
            handoff = json.load(fh)
        with open(args.captured_text_file, encoding="utf-8") as fh:
            captured_text = fh.read()
        # A real timestamp is fine here: H1 is foreign and captured_at is descriptive
        # only (AG never gates on it). Imported locally so the pure builders above
        # stay free of ambient time.
        from datetime import datetime, timezone

        envelope = capture_from_handoff(
            handoff,
            actor_output_id=args.actor_output_id,
            captured_text=captured_text,
            captured_at=datetime.now(timezone.utc).isoformat(),
            capture_origin=args.capture_origin,
        )

    text = to_json(envelope)
    if args.out:
        write_actor_output(envelope, args.out)
    else:
        print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover - thin CLI entry
    raise SystemExit(main())


__all__ = [
    "SCHEMA_VERSION",
    "ACTOR_KINDS",
    "CLAIMED_STATUSES",
    "ENVELOPE_KEYS",
    "HarnessError",
    "build_claimed_test",
    "build_actor_output",
    "capture_from_handoff",
    "sample_actor_output",
    "to_json",
    "write_actor_output",
    "main",
]
