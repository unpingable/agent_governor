# SPDX-License-Identifier: Apache-2.0
"""D0-Origin: AG consumes a genuine NQ-produced FindingSnapshot.

Slice D0-Origin replaces the drill runner's constructed
``FindingSnapshot`` fixture with the JSON written by NQ's production
evaluator pipeline against a staged WAL-bloat sandbox.

This test:

  1. Stages a real WAL-bloat condition on a sandbox SQLite DB (small
     DB + bloated WAL via direct rusqlite-style writes from Python).
  2. Invokes ``nq-monitor drill wal-bloat`` (NQ's real production
     evaluator pipeline) against the sandbox, capturing the genuine
     ``nq.finding_snapshot.v1`` JSON.
  3. Feeds the JSON to ``governor.drill_runner.load_finding_snapshot_from_json``
     and drives the cooked-context orchestrator through the four-link
     chain.
  4. Asserts every D0-Origin acceptance criterion the campaign card
     names.

Hard rule: the NQ binary must be on PATH (or at the location specified
by the ``NQ_MONITOR_BIN`` env var) and must include the ``drill
wal-bloat`` subcommand landed alongside this slice. Tests skip cleanly
if neither is available — they do NOT silently substitute the fixture
path (that would re-enact the same custody gap the slice closed).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from governor.cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    NQ_ORIGIN_MODES,
    ORIGIN_MODE_DRILL,
)
from governor.drill_runner import (
    InvalidFindingSnapshotError,
    build_json_envelope,
    load_finding_snapshot_from_json,
    run_drill_and_render,
)
from governor.gate_receipt import GateReceiptSystem


# ---------------------------------------------------------------------------
# Helpers — stage the WAL-bloat substrate from Python.
#
# Equivalent to Night Shift's ``wal_bloat_stager.rs``. Implemented in
# Python here because the test exercises the AG side; we don't want the
# AG test to spawn the Rust stager binary, just the staged-substrate
# shape it produces.
# ---------------------------------------------------------------------------


_STAGER_BASELINE_ROWS = 50
_STAGER_BLOAT_ROWS = 3000
_STAGER_ROW_BLOB_BYTES = 1024
_NQ_BIN_ENV = "NQ_MONITOR_BIN"
_NQ_BIN_DEFAULT_PATHS = (
    "/home/jbeck/git/notquery/target/debug/nq-monitor",
    "nq-monitor",
)


def _resolve_nq_bin() -> str | None:
    """Return the path to the nq-monitor binary, or None if unavailable."""
    explicit = os.environ.get(_NQ_BIN_ENV)
    if explicit and Path(explicit).exists():
        return explicit
    for candidate in _NQ_BIN_DEFAULT_PATHS:
        path = shutil.which(candidate) or candidate
        if Path(path).exists():
            return path
    return None


_STAGER_SUBPROCESS_SCRIPT = r"""
import os, sqlite3, sys
db_path = sys.argv[1]
baseline_rows = int(sys.argv[2])
bloat_rows = int(sys.argv[3])
row_bytes = int(sys.argv[4])
conn = sqlite3.connect(db_path)
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
conn.execute("PRAGMA wal_autocheckpoint=0")
conn.execute("CREATE TABLE staged_t (id INTEGER PRIMARY KEY, blob BLOB)")
baseline = b"x" * row_bytes
for _ in range(baseline_rows):
    conn.execute("INSERT INTO staged_t (blob) VALUES (?)", (baseline,))
conn.commit()
conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
bloat = b"y" * row_bytes
for _ in range(bloat_rows):
    conn.execute("INSERT INTO staged_t (blob) VALUES (?)", (bloat,))
conn.commit()
# os._exit bypasses Python's connection finalizer that would otherwise
# trigger a passive checkpoint and truncate the WAL we just bloated.
os._exit(0)
"""


def _stage_wal_bloat(sandbox_dir: Path) -> Path:
    """Stage a sandbox SQLite DB with a bloated WAL.

    Runs the staging in a subprocess that exits via ``os._exit(0)`` so
    Python's connection finalizer does not get a chance to checkpoint
    and truncate the WAL. This mirrors Night Shift's Rust stager
    behavior (which holds the WAL open via the OS-level connection
    lifetime, not via Python's GC semantics).
    """
    sandbox_dir.mkdir(parents=True, exist_ok=True)
    db_path = sandbox_dir / "staged.sqlite"
    # Clear any prior staging artifacts.
    for suffix in ("", "-wal", "-shm"):
        target = sandbox_dir / f"staged.sqlite{suffix}"
        if target.exists():
            target.unlink()
    proc = subprocess.run(
        [
            "python3",
            "-c",
            _STAGER_SUBPROCESS_SCRIPT,
            str(db_path),
            str(_STAGER_BASELINE_ROWS),
            str(_STAGER_BLOAT_ROWS),
            str(_STAGER_ROW_BLOB_BYTES),
        ],
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0, (
        f"WAL stager subprocess failed: "
        f"stderr={proc.stderr.decode(errors='replace')!r}"
    )
    # Confirm we actually staged the condition.
    db_size = db_path.stat().st_size
    wal_path = db_path.parent / "staged.sqlite-wal"
    wal_size = wal_path.stat().st_size if wal_path.exists() else 0
    wal_pct = 100.0 * wal_size / db_size if db_size else 0.0
    # The detector requires wal_pct > 5.0 OR (db_size_mb < 5120 AND
    # wal_size_mb > 256). We aim for the relative threshold.
    if not (wal_pct > 5.0):
        pytest.fail(
            f"WAL staging failed to produce detector-triggering substrate: "
            f"db_size={db_size}, wal_size={wal_size}, wal_pct={wal_pct:.2f}%"
        )
    return db_path


def _invoke_nq_drill(
    *, nq_bin: str, sandbox_db: Path, nq_db: Path, origin_mode: str = "drill"
) -> dict:
    """Invoke `nq-monitor drill wal-bloat` and return the parsed snapshot."""
    proc = subprocess.run(
        [
            nq_bin,
            "drill",
            "wal-bloat",
            "--sandbox-db",
            str(sandbox_db),
            "--db",
            str(nq_db),
            "--origin-mode",
            origin_mode,
            "--format",
            "json",
        ],
        capture_output=True,
        env={**os.environ, "RUST_LOG": "warn"},
        check=False,
    )
    assert proc.returncode == 0, (
        f"nq-monitor drill wal-bloat failed: rc={proc.returncode} "
        f"stderr={proc.stderr.decode(errors='replace')!r}"
    )
    raw = json.loads(proc.stdout)
    # `--format json` produces an array of snapshots; the sandbox has
    # exactly one DB so the array has exactly one element.
    assert isinstance(raw, list), f"expected array, got {type(raw).__name__}"
    assert len(raw) == 1, f"expected one snapshot, got {len(raw)}"
    return raw[0]


# ---------------------------------------------------------------------------
# Fixture: stage substrate + invoke NQ + write JSON to disk.
# ---------------------------------------------------------------------------


@pytest.fixture
def genuine_nq_finding(tmp_path: Path) -> tuple[Path, dict]:
    """Stage WAL bloat, invoke real NQ, return (json_path, parsed_dict)."""
    nq_bin = _resolve_nq_bin()
    if nq_bin is None:
        pytest.skip(
            f"nq-monitor binary not found. Set {_NQ_BIN_ENV} env var or "
            f"build NQ via `cargo build -p nq-monitor` in ~/git/notquery."
        )
    sandbox_dir = tmp_path / "sandbox"
    sandbox_db = _stage_wal_bloat(sandbox_dir)
    nq_db = tmp_path / "nq.db"
    snapshot = _invoke_nq_drill(
        nq_bin=nq_bin, sandbox_db=sandbox_db, nq_db=nq_db
    )
    finding_json_path = tmp_path / "nq_finding.json"
    finding_json_path.write_text(json.dumps(snapshot))
    return finding_json_path, snapshot


# ---------------------------------------------------------------------------
# Acceptance tests — one per criterion from the D0-Origin spec.
# ---------------------------------------------------------------------------


def test_acceptance_1_wal_bloat_condition_is_staged(
    genuine_nq_finding: tuple[Path, dict],
) -> None:
    """Acceptance 1: WAL-bloat condition staged in sandbox target."""
    _, snapshot = genuine_nq_finding
    assert snapshot["identity"]["detector"] == "wal_bloat"
    # NQ's diagnosis carries the WAL bloat synopsis.
    diagnosis = snapshot.get("diagnosis")
    assert diagnosis is not None, "WAL bloat detection should produce diagnosis"
    assert "WAL" in diagnosis["synopsis"]


def test_acceptance_2_nq_observed_through_real_evaluator(
    genuine_nq_finding: tuple[Path, dict],
) -> None:
    """Acceptance 2: NQ evaluator observed the condition via real path."""
    _, snapshot = genuine_nq_finding
    # The schema literal proves the snapshot came off the real
    # `export_findings_from_conn` path, not a hand-crafted dict.
    assert snapshot["schema"] == "nq.finding_snapshot.v1"
    # `lifecycle.first_seen_gen` is set by `update_warning_state_inner`
    # — the production lifecycle path. Its presence is structural
    # evidence of the real evaluator pipeline running.
    assert snapshot["lifecycle"]["first_seen_gen"] >= 1
    # The observation row underneath the snapshot also exists.
    assert snapshot["observations"]["total_count"] >= 1


def test_acceptance_3_finding_carries_origin_mode_drill(
    genuine_nq_finding: tuple[Path, dict],
) -> None:
    """Acceptance 3: produced finding carries origin_mode=drill."""
    _, snapshot = genuine_nq_finding
    assert snapshot["origin_mode"] == ORIGIN_MODE_DRILL
    assert snapshot["origin_mode"] in NQ_ORIGIN_MODES


def test_acceptance_4_drill_finding_distinguishable_from_observed(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """Acceptance 4: drill ≠ observed at row + DTO level.

    Done by staging the same substrate against TWO fresh NQ DBs and
    asking for ``observed`` vs ``drill`` — the DTO origin_mode field
    must differ, and the two JSONs must not be byte-identical.
    """
    nq_bin = _resolve_nq_bin()
    assert nq_bin is not None
    finding_json_drill, snapshot_drill = genuine_nq_finding
    # Build a second NQ DB observing the same sandbox under
    # `origin_mode=observed`.
    sandbox_db = tmp_path / "sandbox" / "staged.sqlite"
    nq_db_observed = tmp_path / "nq_observed.db"
    snapshot_observed = _invoke_nq_drill(
        nq_bin=nq_bin,
        sandbox_db=sandbox_db,
        nq_db=nq_db_observed,
        origin_mode="observed",
    )
    assert snapshot_drill["origin_mode"] == "drill"
    assert snapshot_observed["origin_mode"] == "observed"
    # Wire DTOs must differ on at least the origin_mode field.
    drill_bytes = json.dumps(snapshot_drill, sort_keys=True)
    observed_bytes = json.dumps(snapshot_observed, sort_keys=True)
    assert drill_bytes != observed_bytes


def test_acceptance_5_ag_consumes_genuine_finding_not_fixture(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """Acceptance 5: AG drives the chain from the genuine wire DTO."""
    finding_json_path, snapshot = genuine_nq_finding
    loaded = load_finding_snapshot_from_json(finding_json_path)
    # The loaded shape carries provenance fields the fixture path does not.
    assert loaded["_source"] == "nq_drill_finding_json"
    assert loaded["_nq_snapshot"]["schema"] == "nq.finding_snapshot.v1"
    # The finding_id used to thread the chain is the NQ-side
    # finding_key — not a hardcoded fixture value.
    assert loaded["finding_id"] == snapshot["finding_key"]
    assert loaded["finding_id"].startswith("local/")
    # Drive the chain.
    receipt_root = tmp_path / "receipts"
    result, _transcript = run_drill_and_render(
        gov_dir=receipt_root, finding=loaded
    )
    # Four receipts: standing/wicket/grant/consume.
    assert len(result.receipt_ids) == 4


def test_acceptance_6_all_four_receipts_inherit_origin_mode_drill(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """Acceptance 6: every chain receipt carries origin_mode=drill."""
    finding_json_path, _ = genuine_nq_finding
    loaded = load_finding_snapshot_from_json(finding_json_path)
    receipt_root = tmp_path / "receipts"
    result, _ = run_drill_and_render(gov_dir=receipt_root, finding=loaded)
    system = GateReceiptSystem(receipt_root)
    for rid in result.receipt_ids:
        receipt = system.receipt_store.get_by_id(rid)
        assert receipt is not None, f"receipt {rid} should be retrievable"
        bundle = system.evidence_store.get(receipt.evidence_hash)
        assert bundle is not None, f"evidence bundle for {rid} should exist"
        assert (
            bundle.get(EVIDENCE_KEY_ORIGIN_MODE) == ORIGIN_MODE_DRILL
        ), f"receipt {rid} evidence_bundle.origin_mode missing or wrong"


def test_acceptance_7_why_renders_drill_first(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """Acceptance 7: governor why on final receipt renders DRILL first."""
    finding_json_path, _ = genuine_nq_finding
    loaded = load_finding_snapshot_from_json(finding_json_path)
    receipt_root = tmp_path / "receipts"
    _, transcript = run_drill_and_render(gov_dir=receipt_root, finding=loaded)
    # The transcript embeds the walk under "why <id>:". DRILL must
    # appear BEFORE any chain link rendering.
    walk_section = transcript.split("why <rcpt:4>:")[1]
    drill_idx = walk_section.find("DRILL")
    first_rcpt_idx = walk_section.find("verdict=")
    assert drill_idx > 0, "DRILL marker should appear in walk section"
    assert first_rcpt_idx > 0, "Chain link rendering should appear in walk"
    assert drill_idx < first_rcpt_idx, (
        "DRILL must render BEFORE the first chain link in the walk; "
        "found DRILL at offset {} and first verdict= at offset {}".format(
            drill_idx, first_rcpt_idx
        )
    )


def test_acceptance_8_transcript_deterministic_after_normalization(
    tmp_path: Path,
) -> None:
    """Acceptance 8: two runs against fresh sandboxes produce byte-identical normalized transcripts."""
    nq_bin = _resolve_nq_bin()
    if nq_bin is None:
        pytest.skip(f"nq-monitor binary not found ({_NQ_BIN_ENV})")
    transcripts = []
    for run in range(2):
        sandbox_dir = tmp_path / f"sandbox_{run}"
        sandbox_db = _stage_wal_bloat(sandbox_dir)
        nq_db = tmp_path / f"nq_{run}.db"
        snapshot = _invoke_nq_drill(
            nq_bin=nq_bin, sandbox_db=sandbox_db, nq_db=nq_db
        )
        finding_json_path = tmp_path / f"nq_finding_{run}.json"
        finding_json_path.write_text(json.dumps(snapshot))
        loaded = load_finding_snapshot_from_json(finding_json_path)
        receipt_root = tmp_path / f"receipts_{run}"
        _, transcript = run_drill_and_render(
            gov_dir=receipt_root, finding=loaded
        )
        transcripts.append(transcript)
    assert transcripts[0] == transcripts[1], (
        "Normalized transcripts should be byte-identical across two runs "
        "against fresh sandbox dirs. Diff:\n"
        + "\n".join(
            __import__("difflib").unified_diff(
                transcripts[0].splitlines(),
                transcripts[1].splitlines(),
                lineterm="",
            )
        )
    )


# ---------------------------------------------------------------------------
# Bridge contract negative tests — refuse malformed input.
# ---------------------------------------------------------------------------


def test_bridge_refuses_wrong_schema(tmp_path: Path) -> None:
    """Snapshot with wrong schema string is refused at load time."""
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "schema": "some.other.schema.v1",
                "finding_key": "x",
                "identity": {"host": "h", "detector": "wal_bloat"},
                "origin_mode": "drill",
            }
        )
    )
    with pytest.raises(InvalidFindingSnapshotError, match="schema"):
        load_finding_snapshot_from_json(p)


def test_bridge_refuses_unknown_origin_mode(tmp_path: Path) -> None:
    """Snapshot with origin_mode outside the closed vocabulary is refused."""
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "schema": "nq.finding_snapshot.v1",
                "finding_key": "x",
                "identity": {"host": "h", "detector": "wal_bloat"},
                "origin_mode": "not_in_vocab",
            }
        )
    )
    with pytest.raises(InvalidFindingSnapshotError, match="origin_mode"):
        load_finding_snapshot_from_json(p)


def test_bridge_refuses_wrong_detector(tmp_path: Path) -> None:
    """Snapshot with a detector other than wal_bloat refused in D0-Origin all-green."""
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            {
                "schema": "nq.finding_snapshot.v1",
                "finding_key": "x",
                "identity": {"host": "h", "detector": "stale_host"},
                "origin_mode": "drill",
            }
        )
    )
    with pytest.raises(InvalidFindingSnapshotError, match="wal_bloat"):
        load_finding_snapshot_from_json(p)


def test_bridge_refuses_multiple_snapshots_in_array(tmp_path: Path) -> None:
    """Array of multiple snapshots is refused — drill must produce exactly one."""
    p = tmp_path / "bad.json"
    p.write_text(
        json.dumps(
            [
                {
                    "schema": "nq.finding_snapshot.v1",
                    "finding_key": "a",
                    "identity": {"host": "h", "detector": "wal_bloat"},
                    "origin_mode": "drill",
                },
                {
                    "schema": "nq.finding_snapshot.v1",
                    "finding_key": "b",
                    "identity": {"host": "h", "detector": "wal_bloat"},
                    "origin_mode": "drill",
                },
            ]
        )
    )
    with pytest.raises(InvalidFindingSnapshotError, match="exactly one"):
        load_finding_snapshot_from_json(p)


# ---------------------------------------------------------------------------
# Module entry-point smoke test (mirrors the Night Shift subprocess
# invocation shape).
# ---------------------------------------------------------------------------


def test_module_entry_consumes_finding_json(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """`python3 -m governor.drill_runner --finding-json ...` works end-to-end."""
    finding_json_path, _ = genuine_nq_finding
    receipt_root = tmp_path / "receipts"
    proc = subprocess.run(
        [
            "python3",
            "-m",
            "governor.drill_runner",
            "--scenario",
            "all-green",
            "--root",
            str(receipt_root),
            "--finding-json",
            str(finding_json_path),
        ],
        capture_output=True,
        env={
            **os.environ,
            "PYTHONPATH": str(Path(__file__).resolve().parent.parent / "src"),
        },
        check=False,
    )
    assert proc.returncode == 0, (
        f"drill_runner --finding-json failed: "
        f"stderr={proc.stderr.decode(errors='replace')!r}"
    )
    envelope = json.loads(proc.stdout)
    assert envelope["origin_mode"] == "drill"
    assert envelope["scenario"] == "all-green"
    assert len(envelope["receipt_ids"]) == 4
    assert envelope["leaf_receipt_id"] == envelope["receipt_ids"][-1]


# ---------------------------------------------------------------------------
# Envelope round-trip smoke (not D0-Origin specific but proves the
# build_json_envelope path still handles the genuine-finding shape).
# ---------------------------------------------------------------------------


def test_build_json_envelope_preserves_finding(
    genuine_nq_finding: tuple[Path, dict], tmp_path: Path
) -> None:
    """JSON envelope carries the genuine NQ finding verbatim."""
    finding_json_path, snapshot = genuine_nq_finding
    loaded = load_finding_snapshot_from_json(finding_json_path)
    receipt_root = tmp_path / "receipts"
    result, transcript = run_drill_and_render(
        gov_dir=receipt_root, finding=loaded
    )
    envelope = build_json_envelope(result, transcript)
    # The genuine snapshot is carried through under
    # `finding._nq_snapshot`. The wire-side `finding_key` is preserved.
    assert (
        envelope["finding"]["_nq_snapshot"]["finding_key"]
        == snapshot["finding_key"]
    )
    assert envelope["finding"]["origin_mode"] == "drill"
