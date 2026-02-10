"""Tests for the selfcheck module — automated deployment health verification."""

import json
import pytest
from pathlib import Path

from governor.selfcheck import CheckItem, run_selfcheck


@pytest.fixture
def gov_dir(tmp_path):
    """Create a well-formed governor directory."""
    d = tmp_path / ".governor"
    d.mkdir()
    (d / "gate_receipts").mkdir()
    (d / "evidence").mkdir()
    (d / "exceptions").mkdir()
    return d


class TestCheckItem:

    def test_to_dict(self):
        item = CheckItem("test", "ok", "All good")
        d = item.to_dict()
        assert d == {"name": "test", "status": "ok", "detail": "All good"}

    def test_fields(self):
        item = CheckItem("name", "warn", "Some issue")
        assert item.name == "name"
        assert item.status == "warn"
        assert item.detail == "Some issue"


class TestDirStructure:

    def test_healthy_dir(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        dir_check = next(i for i in items if i.name == "dir_structure")
        assert dir_check.status == "ok"

    def test_missing_governor_dir(self, tmp_path):
        missing = tmp_path / ".governor"
        items = run_selfcheck(missing, scope="fast")
        dir_check = next(i for i in items if i.name == "dir_structure")
        assert dir_check.status == "fail"

    def test_missing_subdirs(self, tmp_path):
        d = tmp_path / ".governor"
        d.mkdir()
        # No gate_receipts or evidence
        items = run_selfcheck(d, scope="fast")
        dir_check = next(i for i in items if i.name == "dir_structure")
        assert dir_check.status == "warn"
        assert "gate_receipts" in dir_check.detail


class TestReceiptStore:

    def test_healthy_receipts(self, gov_dir):
        # Write valid JSONL
        jsonl = gov_dir / "gate_receipts" / "receipts.jsonl"
        lines = [
            json.dumps({"receipt_id": "r1", "gate": "test", "verdict": "pass"}),
            json.dumps({"receipt_id": "r2", "gate": "test", "verdict": "block"}),
        ]
        jsonl.write_text("\n".join(lines))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "receipt_store")
        assert check.status == "ok"
        assert "2 receipt(s)" in check.detail

    def test_corrupt_jsonl(self, gov_dir):
        jsonl = gov_dir / "gate_receipts" / "receipts.jsonl"
        jsonl.write_text('{"valid": true}\nnot json at all\n{"also": "valid"}\n')

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "receipt_store")
        assert check.status == "warn"
        assert "1 parse error" in check.detail

    def test_empty_receipt_store(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "receipt_store")
        assert check.status == "ok"
        assert "0 receipt(s)" in check.detail


class TestExceptionRecords:

    def test_healthy_exceptions(self, gov_dir):
        exc = {"id": "exc_test", "violations": [{"a": 1}], "scope": "single_instance"}
        (gov_dir / "exceptions" / "exc_test.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "exception_records")
        assert check.status == "ok"
        assert "1 exception(s)" in check.detail

    def test_corrupt_exception(self, gov_dir):
        (gov_dir / "exceptions" / "exc_bad.json").write_text("not json")

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "exception_records")
        assert check.status == "warn"

    def test_missing_fields(self, gov_dir):
        # Valid JSON but missing required fields
        (gov_dir / "exceptions" / "exc_bad.json").write_text('{"foo": "bar"}')

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "exception_records")
        assert check.status == "warn"

    def test_no_exceptions_dir(self, tmp_path):
        d = tmp_path / ".governor"
        d.mkdir()
        (d / "gate_receipts").mkdir()
        (d / "evidence").mkdir()

        items = run_selfcheck(d, scope="fast")
        check = next(i for i in items if i.name == "exception_records")
        assert check.status == "ok"


class TestPendingViolation:

    def test_no_pending(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "pending_violation")
        assert check.status == "ok"

    def test_stale_pending(self, gov_dir):
        pending = {
            "id": "pend_abc",
            "status": "pending",
            "violations": [{"a": 1}],
        }
        (gov_dir / "pending_violations.json").write_text(json.dumps(pending))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "pending_violation")
        assert check.status == "warn"
        assert "pend_abc" in check.detail

    def test_resolved_pending(self, gov_dir):
        pending = {"id": "pend_abc", "status": "proceeded"}
        (gov_dir / "pending_violations.json").write_text(json.dumps(pending))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "pending_violation")
        assert check.status == "ok"

    def test_corrupt_pending(self, gov_dir):
        (gov_dir / "pending_violations.json").write_text("not json")

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "pending_violation")
        assert check.status == "warn"
        assert "corrupt" in check.detail.lower()


class TestUnlinkedExceptions:

    def test_all_linked(self, gov_dir):
        """All exceptions have receipt_id — ok."""
        exc = {
            "id": "exc_1",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "expiry": None,
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
            "receipt_id": "rcpt_abc",
        }
        (gov_dir / "exceptions" / "exc_1.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "unlinked_exceptions")
        assert check.status == "ok"
        assert "all linked" in check.detail

    def test_unlinked_warns(self, gov_dir):
        """Exception with receipt_id=None triggers warn."""
        exc = {
            "id": "exc_1",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "expiry": None,
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
            # No receipt_id — this is the canary
        }
        (gov_dir / "exceptions" / "exc_1.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "unlinked_exceptions")
        assert check.status == "warn"
        assert "1/1" in check.detail
        assert "receipt_id" in check.detail

    def test_mixed_linked_and_unlinked(self, gov_dir):
        """Mix of linked and unlinked — warns with count."""
        for i, rid in enumerate([None, "rcpt_a", None, "rcpt_b"]):
            exc = {"id": f"exc_{i}", "violations": [], "mode": "code"}
            if rid:
                exc["receipt_id"] = rid
            (gov_dir / "exceptions" / f"exc_{i}.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "unlinked_exceptions")
        assert check.status == "warn"
        assert "2/4" in check.detail

    def test_no_exceptions(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        check = next(i for i in items if i.name == "unlinked_exceptions")
        assert check.status == "ok"

    def test_included_in_fast_scope(self, gov_dir):
        """unlinked_exceptions runs in fast scope (it's a cheap canary)."""
        items = run_selfcheck(gov_dir, scope="fast")
        names = [i.name for i in items]
        assert "unlinked_exceptions" in names


class TestEvidenceBlobs:

    def test_all_evidence_present(self, gov_dir):
        # Create a receipt with evidence_hash
        eh = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        receipt = {"receipt_id": "r1", "evidence_hash": eh}
        (gov_dir / "gate_receipts" / "receipts.jsonl").write_text(
            json.dumps(receipt) + "\n"
        )
        # Create matching evidence blob
        shard = gov_dir / "evidence" / eh[:2]
        shard.mkdir(parents=True)
        (shard / f"{eh}.json").write_text('{"data": "test"}')

        items = run_selfcheck(gov_dir, scope="full")
        check = next(i for i in items if i.name == "evidence_blobs")
        assert check.status == "ok"

    def test_missing_evidence(self, gov_dir):
        eh = "abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        receipt = {"receipt_id": "r1", "evidence_hash": eh}
        (gov_dir / "gate_receipts" / "receipts.jsonl").write_text(
            json.dumps(receipt) + "\n"
        )
        # No evidence blob created

        items = run_selfcheck(gov_dir, scope="full")
        check = next(i for i in items if i.name == "evidence_blobs")
        assert check.status == "warn"
        assert "1 missing" in check.detail

    def test_not_included_in_fast(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        names = [i.name for i in items]
        assert "evidence_blobs" not in names


class TestReceiptExceptionXrefs:

    def test_valid_xrefs(self, gov_dir):
        # Receipt store
        receipt = {"receipt_id": "r1", "gate": "test"}
        (gov_dir / "gate_receipts" / "receipts.jsonl").write_text(
            json.dumps(receipt) + "\n"
        )
        # Exception with matching receipt_id
        exc = {
            "id": "exc_1",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "expiry": None,
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
            "receipt_id": "r1",
        }
        (gov_dir / "exceptions" / "exc_1.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="full")
        check = next(i for i in items if i.name == "receipt_exception_xrefs")
        assert check.status == "ok"
        assert "1 linked" in check.detail

    def test_orphan_xref(self, gov_dir):
        # No receipts
        # Exception pointing to nonexistent receipt
        exc = {
            "id": "exc_1",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "expiry": None,
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
            "receipt_id": "nonexistent_receipt",
        }
        (gov_dir / "exceptions" / "exc_1.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="full")
        check = next(i for i in items if i.name == "receipt_exception_xrefs")
        assert check.status == "warn"
        assert "1 orphan" in check.detail

    def test_no_linked_exceptions(self, gov_dir):
        # Exception without receipt_id (old format)
        exc = {
            "id": "exc_1",
            "violations": [],
            "blocked_response_preview": "test",
            "scope": "single_instance",
            "created_at": "2025-01-01T00:00:00Z",
            "mode": "code",
        }
        (gov_dir / "exceptions" / "exc_1.json").write_text(json.dumps(exc))

        items = run_selfcheck(gov_dir, scope="full")
        check = next(i for i in items if i.name == "receipt_exception_xrefs")
        assert check.status == "ok"
        assert "No linked" in check.detail

    def test_not_included_in_fast(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        names = [i.name for i in items]
        assert "receipt_exception_xrefs" not in names


class TestRunSelfcheckScopes:

    def test_fast_returns_5_items(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="fast")
        assert len(items) == 5

    def test_full_returns_7_items(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="full")
        assert len(items) == 7

    def test_healthy_store_all_ok(self, gov_dir):
        items = run_selfcheck(gov_dir, scope="full")
        assert all(i.status == "ok" for i in items)
