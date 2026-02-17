# SPDX-License-Identifier: Apache-2.0
"""
Performance and scale tests.

These tests verify that key subsystems handle realistic load without
O(n^2) regressions. Bounds are generous (5-10x expected) — they only
catch catastrophic performance regressions, not normal variance.

Run:
    python3 -m pytest tests/test_scale.py -v

Marker:
    @pytest.mark.scale
"""

import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.scale


# ── Receipt store at scale ───────────────────────────────────────────────


class TestReceiptStoreScale:
    """Receipt store with 10,000 receipts."""

    def _make_receipt(self, i: int):
        from governor.gate_receipt import GateReceipt
        return GateReceipt(
            receipt_id=f"r_{i:06d}",
            schema_version="receipt_v1",
            timestamp=datetime.now(timezone.utc).isoformat(),
            gate="evidence_gate" if i % 2 == 0 else "pre_commit",
            verdict="pass" if i % 3 != 0 else "block",
            subject_hash=f"sha256:{i:064x}",
            evidence_hash=f"sha256:{(i * 7):064x}",
            policy_hash=f"sha256:{(i * 13):064x}",
        )

    def test_write_10k_receipts(self, tmp_path):
        """Writing 10,000 receipts completes in < 10s."""
        from governor.gate_receipt import ReceiptStore

        store = ReceiptStore(tmp_path)
        start = time.monotonic()

        for i in range(10_000):
            store.append(self._make_receipt(i))

        elapsed = time.monotonic() - start
        assert elapsed < 10, f"Writing 10k receipts took {elapsed:.1f}s (limit: 10s)"

    def test_read_10k_receipts(self, tmp_path):
        """Reading 10,000 receipts completes in < 10s."""
        from governor.gate_receipt import ReceiptStore

        store = ReceiptStore(tmp_path)
        for i in range(10_000):
            store.append(self._make_receipt(i))

        start = time.monotonic()
        all_receipts = store.all()
        elapsed = time.monotonic() - start

        assert len(all_receipts) == 10_000
        assert elapsed < 10, f"Reading 10k receipts took {elapsed:.1f}s (limit: 10s)"

    def test_filter_10k_receipts(self, tmp_path):
        """Filtering 10,000 receipts by gate completes in < 10s."""
        from governor.gate_receipt import ReceiptStore

        store = ReceiptStore(tmp_path)
        for i in range(10_000):
            store.append(self._make_receipt(i))

        start = time.monotonic()
        filtered = store.query(gate="evidence_gate")
        elapsed = time.monotonic() - start

        assert len(filtered) == 5_000  # Every other receipt
        assert elapsed < 10, f"Filtering 10k receipts took {elapsed:.1f}s (limit: 10s)"


# ── Epistemic ledger at scale ────────────────────────────────────────────


class TestEpistemicLedgerScale:
    """Epistemic ledger with 1,000 claims."""

    def test_1k_claims_in_memory(self):
        """Creating 1,000 claims in-memory completes in < 5s."""
        from governor.epistemic import EpistemicLedger, Provenance

        ledger = EpistemicLedger()
        start = time.monotonic()

        for i in range(1_000):
            ledger.new_claim(
                content=f"Claim number {i} about topic {i % 10}",
                provenance=Provenance.ASSUMED,
                confidence=0.5,
                source_agent_id=f"agent_{i % 5}",
            )

        elapsed = time.monotonic() - start
        assert len(ledger.active_claims()) == 1_000
        assert elapsed < 5, f"Creating 1k claims took {elapsed:.1f}s (limit: 5s)"

    def test_1k_claims_query_performance(self):
        """Querying 1,000 claims by provenance completes in < 2s."""
        from governor.epistemic import EpistemicLedger, Provenance

        ledger = EpistemicLedger()
        for i in range(1_000):
            prov = Provenance.ASSUMED if i % 2 == 0 else Provenance.OBSERVED
            ledger.new_claim(
                content=f"Claim {i}",
                provenance=prov,
                confidence=0.5,
            )

        start = time.monotonic()
        assumed = ledger.claims_by_provenance(Provenance.ASSUMED)
        elapsed = time.monotonic() - start

        assert len(assumed) == 500
        assert elapsed < 2, f"Querying 1k claims took {elapsed:.1f}s (limit: 2s)"


# ── SQLite concurrency ──────────────────────────────────────────────────


class TestSQLiteConcurrency:
    """Concurrent access to SQLite storage."""

    def test_100_concurrent_inserts(self, tmp_path):
        """100 concurrent fact inserts complete without errors."""
        from governor.storage import Storage

        db_path = tmp_path / "governor.db"
        storage = Storage(db_path)
        errors = []

        def insert_fact(i):
            try:
                now = datetime.now(timezone.utc).isoformat()
                with storage.transaction() as cursor:
                    cursor.execute(
                        "INSERT INTO facts (id, claim_type, claim_json, receipt_json, "
                        "file_hashes_json, epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (f"f_{i}", "file_exists", "{}", "{}", "{}", i, now),
                    )
            except Exception as e:
                errors.append((i, str(e)))

        threads = [threading.Thread(target=insert_fact, args=(i,)) for i in range(100)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        elapsed = time.monotonic() - start

        assert not errors, f"Insert errors: {errors[:5]}"
        with storage.transaction() as cursor:
            cursor.execute("SELECT COUNT(*) FROM facts")
            assert cursor.fetchone()[0] == 100
        assert elapsed < 30, f"100 inserts took {elapsed:.1f}s"

    def test_50_readers_1_writer(self, tmp_path):
        """50 concurrent readers + 1 writer don't deadlock."""
        from governor.storage import Storage

        db_path = tmp_path / "governor.db"
        storage = Storage(db_path)

        # Pre-populate some data
        for i in range(10):
            now = datetime.now(timezone.utc).isoformat()
            with storage.transaction() as cursor:
                cursor.execute(
                    "INSERT INTO facts (id, claim_type, claim_json, receipt_json, "
                    "file_hashes_json, epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (f"f_{i}", "file_exists", "{}", "{}", "{}", i, now),
                )

        errors = []
        read_counts = []

        def reader(thread_id):
            try:
                conn = storage._get_connection()
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM facts")
                count = cursor.fetchone()[0]
                read_counts.append(count)
            except Exception as e:
                errors.append((f"reader_{thread_id}", str(e)))

        def writer():
            try:
                for i in range(10, 20):
                    now = datetime.now(timezone.utc).isoformat()
                    with storage.transaction() as cursor:
                        cursor.execute(
                            "INSERT INTO facts (id, claim_type, claim_json, receipt_json, "
                            "file_hashes_json, epoch, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (f"f_{i}", "file_exists", "{}", "{}", "{}", i, now),
                        )
                    time.sleep(0.01)
            except Exception as e:
                errors.append(("writer", str(e)))

        threads = [threading.Thread(target=reader, args=(i,)) for i in range(50)]
        threads.append(threading.Thread(target=writer))
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert not errors, f"Concurrency errors: {errors[:5]}"

    def test_epoch_counter_under_contention(self, tmp_path):
        """Epoch counter produces 1,000 unique values under 20-thread contention."""
        from governor.storage import Storage

        db_path = tmp_path / "governor.db"
        storage = Storage(db_path)
        epochs = []
        lock = threading.Lock()
        errors = []

        def claim_epochs(count):
            try:
                for _ in range(count):
                    epoch = storage.next_epoch()
                    with lock:
                        epochs.append(epoch)
            except Exception as e:
                errors.append(str(e))

        threads = [threading.Thread(target=claim_epochs, args=(50,)) for _ in range(20)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        elapsed = time.monotonic() - start

        assert not errors, f"Epoch errors: {errors[:5]}"
        assert len(epochs) == 1_000, f"Expected 1000 epochs, got {len(epochs)}"
        assert len(set(epochs)) == 1_000, (
            f"Expected 1000 unique epochs, got {len(set(epochs))} unique"
        )
        assert elapsed < 60, f"Epoch contention took {elapsed:.1f}s"


# ── Security scanner at scale ────────────────────────────────────────────


class TestSecurityScannerScale:
    """Security scanner on large inputs."""

    def test_1mb_file_scan(self, tmp_path):
        """Scanning a 1MB file completes in < 10s."""
        from governor.security import SecurityVerifier

        # Generate 1MB of realistic-ish code
        lines = []
        for i in range(30_000):
            lines.append(f"    result_{i} = process(data_{i}, config_{i})")
        content = "\n".join(lines)
        assert len(content) > 1_000_000, f"Generated {len(content)} bytes, need > 1MB"

        verifier = SecurityVerifier()
        start = time.monotonic()
        findings = verifier.scan_content(content, "large_file.py")
        elapsed = time.monotonic() - start

        assert elapsed < 10, f"1MB scan took {elapsed:.1f}s (limit: 10s)"

    def test_100_file_directory_scan(self, tmp_path):
        """Scanning 100 files completes in < 15s."""
        from governor.security import SecurityVerifier

        # Create 100 files
        src_dir = tmp_path / "src"
        src_dir.mkdir()
        for i in range(100):
            f = src_dir / f"module_{i}.py"
            f.write_text(f"# Module {i}\ndef func_{i}():\n    return {i}\n" * 100)

        verifier = SecurityVerifier()
        start = time.monotonic()
        findings = verifier.scan_directory(src_dir)
        elapsed = time.monotonic() - start

        assert elapsed < 15, f"100-file scan took {elapsed:.1f}s (limit: 15s)"


# ── Continuity checker at scale ──────────────────────────────────────────


class TestContinuityCheckerScale:
    """Continuity checker with many anchors and large text."""

    def test_100_anchors(self):
        """Checking against 100 anchors completes in < 5s."""
        from governor.continuity import Anchor, AnchorType, ContinuityChecker, Severity

        anchors = []
        for i in range(100):
            anchors.append(Anchor(
                id=f"a_{i}",
                anchor_type=AnchorType.REQUIREMENT,
                description=f"Must mention concept_{i}",
                required_patterns=[f"concept_{i}"],
                severity=Severity.CORRECT,
            ))

        # Text that satisfies all anchors
        text = " ".join(f"concept_{i}" for i in range(100))

        checker = ContinuityChecker()
        start = time.monotonic()
        report = checker.check(text, anchors)
        elapsed = time.monotonic() - start

        assert report.passed
        assert elapsed < 5, f"100 anchors took {elapsed:.1f}s (limit: 5s)"

    def test_large_text_50kb(self):
        """Checking 50KB text against anchors completes in < 5s."""
        from governor.continuity import Anchor, AnchorType, ContinuityChecker, Severity

        anchors = [
            Anchor(
                id="a1",
                anchor_type=AnchorType.REQUIREMENT,
                description="Must mention magic_word",
                required_patterns=["magic_word"],
                severity=Severity.CORRECT,
            ),
            Anchor(
                id="a2",
                anchor_type=AnchorType.PROHIBITION,
                description="Must not mention forbidden_term",
                forbidden_patterns=["forbidden_term"],
                severity=Severity.REJECT,
            ),
        ]

        # Generate 50KB of text
        base = "This is a paragraph of text discussing various topics. magic_word appears here. "
        text = base * (50_000 // len(base) + 1)
        assert len(text) >= 50_000

        checker = ContinuityChecker()
        start = time.monotonic()
        report = checker.check(text, anchors)
        elapsed = time.monotonic() - start

        assert report.passed
        assert elapsed < 5, f"50KB text check took {elapsed:.1f}s (limit: 5s)"
