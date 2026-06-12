# SPDX-License-Identifier: Apache-2.0
"""Act-2 receipt interrogation — the spec's acceptance criteria, pinned.

The five questions (plus the negative sixth) run against a real Act-1 + Act-2.5
corpse built in a fixture; assertions are on fields, not bytes (byte-determinism
explicitly not required). The tamper test pins "fails loudly": an interrogation
that would pass for the wrong reason must not pass at all.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from governor.demo_interrogate import interrogate
from governor.demo_opa_contrast import run_contrast as opa_contrast
from governor.demo_refused_spend import run_contrast as act_one


@pytest.fixture(scope="module")
def corpse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("act2-corpse")
    act_one(root=root, now=0)
    opa_contrast(root=root, now=0)
    return root


def test_interrogation_holds_on_the_real_corpse(corpse: Path):
    transcript, ok = interrogate(corpse)
    assert ok is True
    # All six beats present.
    for n in range(1, 7):
        assert f"Q{n}:" in transcript


def test_transcript_carries_the_acceptance_answers(corpse: Path):
    transcript, _ = interrogate(corpse)
    # Q1: chain walk with honest terminus.
    assert "REFUSED  standing_before_spendability_not_bounded" in transcript
    assert "wicket_seam" in transcript and "standing_seam" in transcript
    assert "MISSING" in transcript
    # Q3: the predicate's numbers.
    assert "gap_ns     = 11000000000" in transcript
    assert "bound_ns   = 10000000000" in transcript
    # Q4: the named clock witness + the provenance cameo.
    assert '"kind": "monotonic"' in transcript
    assert '"epoch": "boot:demo-single-host"' in transcript
    assert '"role": "display_only"' in transcript
    assert "origin_mode visible" in transcript
    # Q5: the naive gate's verdict, provenance-labeled.
    assert "unwitnessed_self_report" in transcript
    assert "opa_rcpt_" in transcript
    # Commands are copy-pasteable.
    assert "$ governor --root" in transcript


def test_q6_honest_absence_for_fabricated_id(corpse: Path):
    transcript, ok = interrogate(corpse)
    assert ok is True
    assert "And a receipt that doesn't exist?" in transcript
    assert "honest absence — not found, never inferred" in transcript


def test_q5_skips_honestly_without_opa_receipt(tmp_path: Path):
    # An Act-1-only root: Q5's evidence is absent. The beat says so plainly
    # and skips — no assertion fabricated, the rest of the interrogation holds.
    act_one(root=tmp_path, now=0)
    transcript, ok = interrogate(tmp_path)
    assert ok is True
    assert "no OPA verdict receipt" in transcript
    assert "nothing asserted, nothing fabricated" in transcript


def test_tampered_corpse_fails_loudly(corpse: Path, tmp_path: Path):
    # Copy the corpse and tamper the refusal's evidence bundle (inflate the
    # bound so the gap looks within budget). The interrogation must FAIL —
    # it asserts the recorded facts, it does not take the store's word.
    import shutil

    root = tmp_path / "tampered"
    shutil.copytree(corpse, root)
    store = root / "impostor" / ".governor"
    for line in (store / "receipts" / "gate_receipts.jsonl").open():
        rec = json.loads(line)
        if rec["verdict"] == "block":
            ev = rec["evidence_hash"]
            ev_path = store / "evidence" / ev[:2] / f"{ev}.json"
            bundle = json.loads(ev_path.read_text())
            bundle["bound_ns"] = 99_000_000_000
            ev_path.write_text(json.dumps(bundle))
    _, ok = interrogate(root)
    assert ok is False


def test_opa_receipt_persisted_at_pinned_path(corpse: Path):
    # Act 2.5's verdict receipt lands at the spec-pinned stable filename with
    # the content-addressed id inside (render-only would make Q5 a mime).
    path = corpse / "opa_verdict_receipt.json"
    assert path.exists()
    body = json.loads(path.read_text())
    assert body["receipt_id"].startswith("opa_rcpt_")
    assert body["input_provenance"] == "unwitnessed_self_report"
