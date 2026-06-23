# SPDX-License-Identifier: Apache-2.0
"""Receipt interrogation — the demo's Act 2 ("just one more thing").

Per GOV_GAP_ACT_TWO_RECEIPT_INTERROGATION_001 (ratified 2026-06-12). The beat
between Act 1 (the refusal) and Act 3 (the proof seam): interrogate the SAME
incident's receipts and reconstruct the custody chain from evidence, not logs.
Without this, the hero specimen reads as "AG said no because AG says no"; with
it, "AG shows you the exact premise that failed, from the receipts, with
provenance intact."

Five questions, each a runnable query against the corpse the Act-1 demo left on
disk — the transcript shows the exact ``governor`` command (copy-pasteable),
the relevant output, and a field assertion. A sixth beat asks about a receipt
that doesn't exist (honest absence — the chain never infers). Exit nonzero if
any answer is wrong: an interrogation that passes for the wrong reason fails
loudly, same tripwire discipline as Acts 1 and 2.5.

Scope (anti-dashboard, pinned): a sequence of EXISTING CLI invocations plus
these assertions. No TUI, no query language, no new long-lived surface.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

# Q5 reads Act 2.5's persisted verdict receipt (stable name, pinned by spec).
OPA_RECEIPT_FILENAME = "opa_verdict_receipt.json"

_GOVERNOR_ARGV0: list[str] = (
    ["governor"] if shutil.which("governor") else [sys.executable, "-m", "governor.cli"]
)


def _run_cli(args: list[str]) -> str:
    proc = subprocess.run(
        _GOVERNOR_ARGV0 + args, capture_output=True, text=True, timeout=60
    )
    return proc.stdout + proc.stderr


def _find_refusal(impostor_store: Path) -> dict[str, Any]:
    for line in (impostor_store / "receipts" / "gate_receipts.jsonl").open():
        rec = json.loads(line)
        if rec["verdict"] == "block":
            return rec
    raise SystemExit(f"no refusal receipt in {impostor_store} — not an Act-1 root?")


def _load_evidence(store: Path, evidence_hash: str) -> dict[str, Any]:
    path = store / "evidence" / evidence_hash[:2] / f"{evidence_hash}.json"
    return json.loads(path.read_text())


class _Transcript:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.assertions: list[tuple[str, bool, str]] = []

    def say(self, text: str = "") -> None:
        self.lines.append(text)

    def beat(self, n: int | str, question: str, command: str, output: str) -> None:
        self.say("─" * 70)
        self.say(f"  Q{n}: {question}")
        self.say(f"  $ {command}")
        for ln in output.rstrip().splitlines():
            self.say(f"    {ln}")

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.assertions.append((label, ok, detail))
        self.say(f"  {'✓' if ok else '✗'} {label}")
        if not ok and detail:
            self.say(f"      detail: {detail}")

    def note(self, label: str) -> None:
        self.say(f"  ○ {label}")


def interrogate(root: Path) -> tuple[str, bool]:
    """Cross-examine the corpse at ``root`` (an Act-1 run dir). Returns the
    transcript and whether every assertion held."""
    t = _Transcript()
    impostor_root = root / "impostor"
    store = impostor_root / ".governor"
    receipts = store / "receipts" / "gate_receipts.jsonl"
    if not receipts.exists():
        raise SystemExit(
            f"interrogate: no Act-1 corpse at {root} (expected {receipts}) — pass the "
            f"run ROOT Act 1 printed (the dir that contains 'impostor/'), not the "
            f"impostor subdir."
        )
    refusal = _find_refusal(store)
    rid = refusal["receipt_id"]
    evidence = _load_evidence(store, refusal["evidence_hash"])

    t.say("═" * 70)
    t.say("  Agent Governor — Just One More Thing (Act 2: the interrogation)")
    t.say("  Same incident. The custody chain reconstructs from the receipts —")
    t.say("  evidence, not logs.")
    t.say("═" * 70)

    # Q1 — what happened? The chain walk.
    cmd = f"governor --root {impostor_root} why {rid}"
    out = _run_cli(["--root", str(impostor_root), "why", rid])
    t.beat(1, "What happened to the spend?", cmd, out)
    t.check(
        "refused at the spendability seam, for the temporal-lapse kind",
        "REFUSED" in out
        and "standing_before_spendability_not_bounded" in out
        and "standing_spendability_seam" in out,
    )
    t.check(
        "chain walks refusal → wicket → standing → honest MISSING terminus",
        "wicket_seam" in out and "standing_seam" in out and "MISSING" in out,
        "the refusal is not an orphan; the terminus is absence, not inference",
    )

    # Q2 — why refused? The receipt's own reason.
    cmd = f"governor --root {impostor_root} receipts --id {rid} --evidence"
    out = _run_cli(["--root", str(impostor_root), "receipts", "--id", rid, "--evidence"])
    t.beat(2, "Why was it refused?", cmd, "\n".join(out.splitlines()[:8]) + "\n    …")
    t.check(
        "the receipt names the reason, typed",
        evidence.get("refusal_kind") == "standing_before_spendability_not_bounded"
        and evidence.get("lapse_coverage") == "exceeded_horizon",
        f"refusal_kind={evidence.get('refusal_kind')} lapse={evidence.get('lapse_coverage')}",
    )

    # Q3 — which predicate failed? The numbers.
    t.beat(
        3,
        "Which predicate failed?",
        "(same evidence bundle)",
        f"gap_ns     = {evidence.get('gap_ns')}\n"
        f"bound_ns   = {evidence.get('bound_ns')}\n"
        f"overage_ns = {evidence.get('overage_ns')}",
    )
    t.check(
        "gap exceeded bound by exactly the lapse",
        evidence.get("gap_ns") == 11_000_000_000
        and evidence.get("bound_ns") == 10_000_000_000
        and evidence.get("overage_ns") == 1_000_000_000,
        f"gap={evidence.get('gap_ns')} bound={evidence.get('bound_ns')}",
    )

    # Q4 — stale under WHICH clock witness? The basis, named.
    gb = evidence.get("gap_basis") or {}
    wall = evidence.get("wall") or {}
    t.beat(
        4,
        "Which evidence was stale — under which clock witness?",
        "(same evidence bundle)",
        json.dumps({"gap_basis": gb, "wall": wall}, indent=2, sort_keys=True),
    )
    t.check(
        "the gap ran on a named monotonic basis; wall is display-only",
        gb.get("kind") == "monotonic"
        and gb.get("source") == "process_monotonic"
        and gb.get("epoch") == "boot:demo-single-host"
        and wall.get("role") == "display_only",
        "a gap is a difference between compatible clock witnesses, not numbers",
    )
    t.check(
        "even the demo's own evidence is typed: origin_mode visible, fenced",
        evidence.get("origin_mode") == "drill",
        f"origin_mode={evidence.get('origin_mode')} (drill receipts cannot confer effect)",
    )

    # Q5 — what did the naive gate conclude? (Act 2.5's receipt, if present.)
    opa_path = root / OPA_RECEIPT_FILENAME
    if opa_path.exists():
        opa = json.loads(opa_path.read_text())
        t.beat(
            5,
            "What did the naive gate conclude about the same incident?",
            f"cat {opa_path}",
            json.dumps(opa, indent=2, sort_keys=True),
        )
        t.check(
            "the policy engine's verdict sits in the evidence plane, provenance-labeled",
            opa.get("input_provenance") == "unwitnessed_self_report"
            and str(opa.get("policy_hash", "")).startswith("sha256:")
            and str(opa.get("receipt_id", "")).startswith("opa_rcpt_"),
            f"decision={opa.get('decision')} engine={opa.get('engine')}",
        )
    else:
        t.say("─" * 70)
        t.say("  Q5: What did the naive gate conclude about the same incident?")
        t.note(
            f"no OPA verdict receipt at {opa_path} — run demo/opa-contrast.sh, "
            "or run interrogate.sh with no argument for the full transcript "
            "(honest absence; nothing asserted, nothing fabricated)"
        )

    # Q6 — the negative: ask about a receipt that doesn't exist.
    bogus = "0" * 64
    cmd = f"governor --root {impostor_root} why {bogus}"
    out = _run_cli(["--root", str(impostor_root), "why", bogus])
    t.beat(6, "And a receipt that doesn't exist?", cmd, out)
    t.check(
        "honest absence — not found, never inferred",
        "not found" in out.lower(),
    )

    # Integrity block (the tripwire).
    t.say("")
    t.say("─" * 70)
    t.say("  Integrity (the interrogation answered for the right reasons)")
    t.say("─" * 70)
    ok = all(a for _, a, _ in t.assertions)
    t.say(f"  {len(t.assertions)} assertions, {'all hold' if ok else 'FAILURES PRESENT'}")
    t.say("")
    return "\n".join(t.lines) + "\n", ok


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m governor.demo_interrogate",
        description="Act 2 — interrogate an Act-1 run's receipts.",
    )
    parser.add_argument(
        "root", nargs="?", type=Path, default=None,
        help="An Act-1 run root (from demo/refused-spend.sh). "
             "Omitted: runs Act 1 (and Act 2.5) itself first, and says so.",
    )
    args = parser.parse_args(argv)

    root = args.root
    if root is None:
        import tempfile

        from governor.demo_opa_contrast import run_contrast as opa_contrast
        from governor.demo_refused_spend import run_contrast as act_one

        root = Path(tempfile.mkdtemp(prefix="ag-interrogate."))
        print(f"(no root given — running Act 1 + Act 2.5 fresh under {root})")
        act_one(root=root, now=0)
        opa_contrast(root=root, now=0)
        # Act 2.5 writes its custody run under the same root; the OPA receipt
        # lands at <root>/opa_verdict_receipt.json — Q5's evidence.

    transcript, ok = interrogate(root)
    sys.stdout.write(transcript)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(_main())
