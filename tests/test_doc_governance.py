# SPDX-License-Identifier: Apache-2.0
"""Tests for doc_governance.py — Document Governance."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest

from governor.doc_governance import (
    AuthorityClaim,
    CheckSeverity,
    DocCheckResult,
    DocFinding,
    DocGovernor,
    DocLink,
    DocReceipt,
    DocScope,
    DocStatus,
    DocStore,
    ExportConfig,
    GovDoc,
    LinkKind,
    StalenessReport,
    check_adjacency,
    check_authority,
    check_doc,
    check_links,
    check_staleness,
    extract_authority_claims,
    generate_frontmatter,
    generate_sidecar,
    make_doc_event,
)


# ===========================================================================
# Enum tests
# ===========================================================================

class TestEnums:
    """Tests for all enums."""

    def test_doc_scope_values(self):
        assert DocScope.DESCRIPTIVE.value == "descriptive"
        assert DocScope.PROCEDURAL.value == "procedural"
        assert DocScope.AUTHORITATIVE.value == "authoritative"
        assert len(DocScope) == 3

    def test_doc_status_values(self):
        assert DocStatus.CURRENT.value == "current"
        assert DocStatus.STALE.value == "stale"
        assert DocStatus.HISTORICAL.value == "historical"
        assert DocStatus.UNSAFE.value == "unsafe"
        assert len(DocStatus) == 4

    def test_link_kind_values(self):
        assert LinkKind.CODE.value == "code"
        assert LinkKind.SCRIPT.value == "script"
        assert LinkKind.TEST.value == "test"
        assert LinkKind.PANEL.value == "panel"
        assert LinkKind.DECISION.value == "decision"
        assert LinkKind.ANCHOR.value == "anchor"
        assert LinkKind.RUNBOOK.value == "runbook"
        assert len(LinkKind) == 7

    def test_check_severity_values(self):
        assert CheckSeverity.ERROR.value == "error"
        assert CheckSeverity.WARN.value == "warn"
        assert CheckSeverity.INFO.value == "info"
        assert len(CheckSeverity) == 3

    def test_str_enum_behavior(self):
        assert str(DocScope.DESCRIPTIVE) == "DocScope.DESCRIPTIVE"
        assert DocScope("descriptive") == DocScope.DESCRIPTIVE


# ===========================================================================
# DocLink tests
# ===========================================================================

class TestDocLink:
    """Tests for DocLink dataclass."""

    def test_creation(self):
        link = DocLink(kind=LinkKind.CODE, target="src/auth/")
        assert link.kind == LinkKind.CODE
        assert link.target == "src/auth/"
        assert link.description == ""

    def test_to_dict(self):
        link = DocLink(kind=LinkKind.SCRIPT, target="deploy.sh", description="Deploy script")
        d = link.to_dict()
        assert d["kind"] == "script"
        assert d["target"] == "deploy.sh"
        assert d["description"] == "Deploy script"

    def test_from_dict(self):
        d = {"kind": "test", "target": "tests/test_auth.py", "description": "Auth tests"}
        link = DocLink.from_dict(d)
        assert link.kind == LinkKind.TEST
        assert link.target == "tests/test_auth.py"

    def test_roundtrip(self):
        link = DocLink(kind=LinkKind.PANEL, target="grafana/deploy", description="Deploy dash")
        d = link.to_dict()
        restored = DocLink.from_dict(d)
        assert restored.kind == link.kind
        assert restored.target == link.target
        assert restored.description == link.description

    def test_exists_for_file(self, tmp_path: Path):
        f = tmp_path / "test.py"
        f.write_text("pass")
        link = DocLink(kind=LinkKind.CODE, target=str(f))
        assert link.exists() is True

    def test_exists_for_missing_file(self):
        link = DocLink(kind=LinkKind.CODE, target="/nonexistent/path.py")
        assert link.exists() is False

    def test_exists_for_non_filesystem_link(self):
        link = DocLink(kind=LinkKind.PANEL, target="grafana/deploy")
        assert link.exists() is True  # Non-filesystem links always return True

    def test_exists_for_decision(self):
        link = DocLink(kind=LinkKind.DECISION, target="auth:jwt")
        assert link.exists() is True


# ===========================================================================
# GovDoc tests
# ===========================================================================

class TestGovDoc:
    """Tests for GovDoc dataclass."""

    def test_creation(self):
        doc = GovDoc(doc_id="", path="README.md", scope=DocScope.DESCRIPTIVE)
        assert doc.doc_id  # Auto-generated
        assert doc.path == "README.md"
        assert doc.scope == DocScope.DESCRIPTIVE
        assert doc.status == DocStatus.CURRENT
        assert doc.registered_at  # Auto-set

    def test_explicit_id(self):
        doc = GovDoc(doc_id="abc123", path="test.md", scope=DocScope.DESCRIPTIVE)
        assert doc.doc_id == "abc123"

    def test_to_dict(self):
        doc = GovDoc(
            doc_id="test", path="docs/arch.md",
            scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.DECISION, target="auth:jwt")],
            ttl_days=180,
        )
        d = doc.to_dict()
        assert d["doc_id"] == "test"
        assert d["scope"] == "authoritative"
        assert len(d["links"]) == 1
        assert d["ttl_days"] == 180

    def test_from_dict(self):
        d = {
            "doc_id": "test",
            "path": "runbook.md",
            "scope": "procedural",
            "links": [{"kind": "code", "target": "src/", "description": ""}],
            "ttl_days": 90,
            "registered_at": "2025-01-01T00:00:00+00:00",
            "last_verified": "2025-01-01T00:00:00+00:00",
            "status": "current",
            "content_hash": "abc123",
        }
        doc = GovDoc.from_dict(d)
        assert doc.scope == DocScope.PROCEDURAL
        assert len(doc.links) == 1
        assert doc.ttl_days == 90

    def test_roundtrip(self):
        doc = GovDoc(
            doc_id="rt", path="test.md",
            scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.ANCHOR, target="safety-anchor")],
            ttl_days=30,
        )
        restored = GovDoc.from_dict(doc.to_dict())
        assert restored.doc_id == doc.doc_id
        assert restored.scope == doc.scope
        assert len(restored.links) == 1

    def test_ttl_property(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE, ttl_days=90)
        assert doc.ttl == timedelta(days=90)

    def test_ttl_none(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        assert doc.ttl is None

    def test_ttl_not_expired(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            ttl_days=90,
            last_verified=datetime.now(timezone.utc).isoformat(),
        )
        assert doc.is_ttl_expired() is False

    def test_ttl_expired(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            ttl_days=90,
            last_verified=old_date,
        )
        assert doc.is_ttl_expired() is True

    def test_ttl_no_ttl_never_expires(self):
        old_date = (datetime.now(timezone.utc) - timedelta(days=1000)).isoformat()
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            last_verified=old_date,
        )
        assert doc.is_ttl_expired() is False

    def test_compute_content_hash(self, tmp_path: Path):
        f = tmp_path / "test.md"
        f.write_text("# Hello World\n")
        doc = GovDoc(doc_id="t", path=str(f), scope=DocScope.DESCRIPTIVE)
        h = doc.compute_content_hash()
        assert len(h) == 16
        # Deterministic
        assert doc.compute_content_hash() == h

    def test_compute_content_hash_missing(self):
        doc = GovDoc(doc_id="t", path="/nonexistent.md", scope=DocScope.DESCRIPTIVE)
        assert doc.compute_content_hash() == ""


# ===========================================================================
# Authority language detection tests
# ===========================================================================

class TestExtractAuthorityClaims:
    """Tests for authority language extraction."""

    def test_must(self):
        claims = extract_authority_claims("You MUST validate inputs.")
        assert len(claims) == 1
        assert claims[0].pattern == r'\bMUST\b'

    def test_must_not(self):
        claims = extract_authority_claims("You MUST NOT skip validation.")
        assert len(claims) >= 1

    def test_shall(self):
        claims = extract_authority_claims("The system SHALL log all requests.")
        assert len(claims) == 1

    def test_never(self):
        claims = extract_authority_claims("NEVER expose the database directly.")
        assert len(claims) == 1

    def test_required(self):
        claims = extract_authority_claims("Authentication is REQUIRED.")
        assert len(claims) == 1

    def test_mandatory(self):
        claims = extract_authority_claims("Code review is MANDATORY.")
        assert len(claims) == 1

    def test_forbidden(self):
        claims = extract_authority_claims("Direct database access is FORBIDDEN.")
        assert len(claims) == 1

    def test_no_authority_in_lowercase(self):
        claims = extract_authority_claims("You must validate inputs.")
        assert len(claims) == 0

    def test_code_blocks_excluded(self):
        text = "Normal text.\n```\nYou MUST do this in code.\n```\nMore text."
        claims = extract_authority_claims(text)
        assert len(claims) == 0

    def test_frontmatter_excluded(self):
        text = "---\nstatus: MUST fix\n---\nBody text."
        claims = extract_authority_claims(text)
        assert len(claims) == 0

    def test_multiple_claims(self):
        text = "You MUST validate.\nYou SHALL log.\nNEVER skip."
        claims = extract_authority_claims(text)
        assert len(claims) == 3

    def test_one_per_line(self):
        text = "You MUST and SHALL validate."
        claims = extract_authority_claims(text)
        assert len(claims) == 1  # One match per line

    def test_empty_text(self):
        claims = extract_authority_claims("")
        assert len(claims) == 0

    def test_claim_structure(self):
        claims = extract_authority_claims("Line 1\nYou MUST test.\nLine 3")
        assert claims[0].line_number == 2
        assert "MUST" in claims[0].text


# ===========================================================================
# Check authority tests
# ===========================================================================

class TestCheckAuthority:
    """Tests for authority scope checking."""

    def test_authority_in_authoritative_doc(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE)
        findings = check_authority(doc, "You MUST validate inputs.")
        # Authoritative docs are allowed to use authority language
        assert len(findings) == 0

    def test_authority_in_descriptive_doc(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        findings = check_authority(doc, "You MUST validate inputs.")
        assert len(findings) == 1
        assert findings[0].severity == CheckSeverity.WARN
        assert findings[0].category == "authority"

    def test_authority_in_procedural_doc(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.PROCEDURAL)
        findings = check_authority(doc, "You MUST restart the service.")
        assert len(findings) == 1
        assert findings[0].severity == CheckSeverity.WARN

    def test_no_authority_no_findings(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        findings = check_authority(doc, "The system validates inputs.")
        assert len(findings) == 0


# ===========================================================================
# Check adjacency tests
# ===========================================================================

class TestCheckAdjacency:
    """Tests for execution adjacency rules."""

    def test_procedural_with_code_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[DocLink(kind=LinkKind.CODE, target="src/")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 0

    def test_procedural_with_script_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[DocLink(kind=LinkKind.SCRIPT, target="deploy.sh")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 0

    def test_procedural_with_test_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[DocLink(kind=LinkKind.TEST, target="tests/")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 0

    def test_procedural_without_exec_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[DocLink(kind=LinkKind.PANEL, target="grafana/")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 1
        assert findings[0].severity == CheckSeverity.ERROR
        assert "PROCEDURAL" in findings[0].message or "procedural" in findings[0].message.lower()

    def test_procedural_no_links(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.PROCEDURAL)
        findings = check_adjacency(doc)
        assert len(findings) == 1

    def test_authoritative_with_decision_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.DECISION, target="auth:jwt")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 0

    def test_authoritative_with_anchor_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.ANCHOR, target="safety")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 0

    def test_authoritative_without_auth_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.CODE, target="src/")],
        )
        findings = check_adjacency(doc)
        assert len(findings) == 1
        assert findings[0].severity == CheckSeverity.ERROR

    def test_descriptive_no_links_ok(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        findings = check_adjacency(doc)
        assert len(findings) == 0


# ===========================================================================
# Check links tests
# ===========================================================================

class TestCheckLinks:
    """Tests for link validation."""

    def test_valid_link(self, tmp_path: Path):
        f = tmp_path / "code.py"
        f.write_text("pass")
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            links=[DocLink(kind=LinkKind.CODE, target=str(f))],
        )
        valid, broken, findings = check_links(doc)
        assert valid == 1
        assert broken == 0
        assert len(findings) == 0

    def test_broken_link(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            links=[DocLink(kind=LinkKind.CODE, target="/nonexistent/file.py")],
        )
        valid, broken, findings = check_links(doc)
        assert valid == 0
        assert broken == 1
        assert len(findings) == 1
        assert findings[0].severity == CheckSeverity.ERROR

    def test_no_links(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        valid, broken, findings = check_links(doc)
        assert valid == 0
        assert broken == 0

    def test_mixed_links(self, tmp_path: Path):
        f = tmp_path / "exists.py"
        f.write_text("pass")
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            links=[
                DocLink(kind=LinkKind.CODE, target=str(f)),
                DocLink(kind=LinkKind.CODE, target="/nope.py"),
            ],
        )
        valid, broken, findings = check_links(doc)
        assert valid == 1
        assert broken == 1


# ===========================================================================
# Check staleness tests
# ===========================================================================

class TestCheckStaleness:
    """Tests for staleness detection."""

    def test_not_stale(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            ttl_days=90,
            last_verified=datetime.now(timezone.utc).isoformat(),
        )
        findings = check_staleness(doc)
        assert len(findings) == 0

    def test_stale_ttl(self):
        old = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE,
            ttl_days=90,
            last_verified=old,
        )
        findings = check_staleness(doc)
        assert any(f.category == "staleness" and f.severity == CheckSeverity.WARN
                    for f in findings)

    def test_content_changed(self, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("Original content")

        doc = GovDoc(
            doc_id="t", path=str(f), scope=DocScope.DESCRIPTIVE,
            content_hash="different_hash",
        )
        findings = check_staleness(doc)
        assert any(f.category == "staleness" and f.severity == CheckSeverity.INFO
                    for f in findings)


# ===========================================================================
# check_doc integration tests
# ===========================================================================

class TestCheckDoc:
    """Integration tests for check_doc."""

    def test_clean_descriptive_doc(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        result = check_doc(doc, "This is a simple description.")
        assert result.passed is True
        assert result.status == "current"

    def test_authority_in_wrong_scope(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        result = check_doc(doc, "You MUST validate inputs.")
        # Authority language in descriptive doc is a warning, not an error
        assert result.passed is True  # Warnings don't fail
        assert result.authority_claims == 1
        assert result.ungrounded_claims == 1

    def test_procedural_without_links(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.PROCEDURAL)
        result = check_doc(doc, "Follow these steps.")
        assert result.passed is False  # Missing required links

    def test_authoritative_with_links(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.DECISION, target="auth:jwt")],
        )
        result = check_doc(doc, "You MUST use JWT.")
        assert result.passed is True
        assert result.authority_claims == 1
        assert result.grounded_claims == 1

    def test_authoritative_unsafe(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.CODE, target="/nonexistent.py")],
        )
        result = check_doc(doc, "You MUST validate.")
        assert result.status == "unsafe"
        assert result.passed is False


# ===========================================================================
# DocReceipt tests
# ===========================================================================

class TestDocReceipt:
    """Tests for verification receipts."""

    def test_from_check_result(self):
        result = DocCheckResult(
            doc_id="test", path="x.md", scope="descriptive", status="current",
            authority_claims=2, grounded_claims=1, ungrounded_claims=1,
            links_valid=3, links_broken=0,
        )
        receipt = DocReceipt.from_check_result(result, "abc123")
        assert receipt.doc_id == "test"
        assert receipt.content_hash == "abc123"
        assert receipt.authority_claims == 2
        assert receipt.links_valid == 3

    def test_to_dict(self):
        receipt = DocReceipt(
            doc_id="t", verified_at="2025-01-01", status="current",
            commitments_extracted=5, links_valid=3, links_broken=1,
            authority_claims=5, grounded_claims=3, ungrounded_claims=2,
            content_hash="abc",
        )
        d = receipt.to_dict()
        assert d["doc_id"] == "t"
        assert d["links_broken"] == 1


# ===========================================================================
# StalenessReport tests
# ===========================================================================

class TestStalenessReport:
    """Tests for staleness report."""

    def test_creation(self):
        report = StalenessReport(total=10, current=7, stale=2, historical=1)
        assert report.total == 10
        assert report.unsafe == 0

    def test_to_dict(self):
        report = StalenessReport(total=5, current=3, stale=1, historical=1)
        d = report.to_dict()
        assert d["total"] == 5
        assert d["current"] == 3


# ===========================================================================
# DocStore tests
# ===========================================================================

class TestDocStore:
    """Tests for DocStore persistence."""

    def test_register(self, tmp_path: Path):
        store = DocStore(tmp_path)
        doc = GovDoc(doc_id="t1", path="test.md", scope=DocScope.DESCRIPTIVE)
        result = store.register(doc)
        assert result.doc_id == "t1"
        assert store.registry_path.exists()

    def test_get(self, tmp_path: Path):
        store = DocStore(tmp_path)
        doc = GovDoc(doc_id="t1", path="test.md", scope=DocScope.DESCRIPTIVE)
        store.register(doc)
        loaded = store.get("t1")
        assert loaded is not None
        assert loaded.doc_id == "t1"

    def test_get_missing(self, tmp_path: Path):
        store = DocStore(tmp_path)
        assert store.get("nope") is None

    def test_get_by_path(self, tmp_path: Path):
        store = DocStore(tmp_path)
        doc = GovDoc(doc_id="t1", path="docs/arch.md", scope=DocScope.AUTHORITATIVE)
        store.register(doc)
        loaded = store.get_by_path("docs/arch.md")
        assert loaded is not None
        assert loaded.scope == DocScope.AUTHORITATIVE

    def test_list_docs(self, tmp_path: Path):
        store = DocStore(tmp_path)
        store.register(GovDoc(doc_id="t1", path="a.md", scope=DocScope.DESCRIPTIVE))
        store.register(GovDoc(doc_id="t2", path="b.md", scope=DocScope.PROCEDURAL))
        docs = store.list_docs()
        assert len(docs) == 2

    def test_unregister(self, tmp_path: Path):
        store = DocStore(tmp_path)
        store.register(GovDoc(doc_id="t1", path="a.md", scope=DocScope.DESCRIPTIVE))
        assert store.unregister("t1") is True
        assert store.get("t1") is None

    def test_unregister_missing(self, tmp_path: Path):
        store = DocStore(tmp_path)
        assert store.unregister("nope") is False

    def test_update(self, tmp_path: Path):
        store = DocStore(tmp_path)
        doc = GovDoc(doc_id="t1", path="a.md", scope=DocScope.DESCRIPTIVE)
        store.register(doc)
        doc.status = DocStatus.STALE
        store.update(doc)
        loaded = store.get("t1")
        assert loaded is not None
        assert loaded.status == DocStatus.STALE

    def test_save_and_load_receipt(self, tmp_path: Path):
        store = DocStore(tmp_path)
        receipt = DocReceipt(
            doc_id="t1", verified_at="2025-01-01", status="current",
            commitments_extracted=5, links_valid=3, links_broken=0,
            authority_claims=5, grounded_claims=4, ungrounded_claims=1,
            content_hash="abc",
        )
        store.save_receipt(receipt)
        loaded = store.load_receipt("t1")
        assert loaded is not None
        assert loaded.doc_id == "t1"
        assert loaded.authority_claims == 5

    def test_load_receipt_missing(self, tmp_path: Path):
        store = DocStore(tmp_path)
        assert store.load_receipt("nope") is None

    def test_staleness_report(self, tmp_path: Path):
        store = DocStore(tmp_path)
        store.register(GovDoc(doc_id="t1", path="a.md", scope=DocScope.DESCRIPTIVE))
        report = store.staleness_report()
        assert report.total == 1
        assert report.current == 1


# ===========================================================================
# DocGovernor facade tests
# ===========================================================================

class TestDocGovernor:
    """Tests for the DocGovernor facade."""

    def test_register(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        doc = gov.register("test.md", DocScope.DESCRIPTIVE)
        assert doc.doc_id
        assert doc.scope == DocScope.DESCRIPTIVE

    def test_register_with_string_scope(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        doc = gov.register("test.md", "procedural")
        assert doc.scope == DocScope.PROCEDURAL

    def test_register_with_links(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        doc = gov.register(
            "arch.md", DocScope.AUTHORITATIVE,
            links=[DocLink(kind=LinkKind.DECISION, target="auth:jwt")],
            ttl_days=180,
        )
        assert len(doc.links) == 1
        assert doc.ttl_days == 180

    def test_unregister(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("test.md", DocScope.DESCRIPTIVE)
        assert gov.unregister("test.md") is True

    def test_unregister_missing(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        assert gov.unregister("nope.md") is False

    def test_check(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("test.md", DocScope.DESCRIPTIVE)
        result = gov.check("test.md")
        assert result.doc_id
        assert result.scope == "descriptive"

    def test_check_unregistered(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        result = gov.check("unregistered.md")
        assert result.passed is False
        assert "not registered" in result.findings[0].message

    def test_check_all(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("a.md", DocScope.DESCRIPTIVE)
        gov.register("b.md", DocScope.DESCRIPTIVE)
        results = gov.check_all()
        assert len(results) == 2

    def test_verify(self, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("Simple doc.")
        gov = DocGovernor(tmp_path)
        gov.register(str(f), DocScope.DESCRIPTIVE)
        receipt = gov.verify(str(f))
        assert receipt is not None
        assert receipt.status == "current"

    def test_verify_unregistered(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        assert gov.verify("nope.md") is None

    def test_demote(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("test.md", DocScope.DESCRIPTIVE)
        assert gov.demote("test.md") is True
        docs = gov.list_docs()
        assert docs[0].status == DocStatus.HISTORICAL

    def test_demote_missing(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        assert gov.demote("nope.md") is False

    def test_promote(self, tmp_path: Path):
        f = tmp_path / "doc.md"
        f.write_text("Doc content.")
        gov = DocGovernor(tmp_path)
        gov.register(str(f), DocScope.DESCRIPTIVE)
        gov.demote(str(f))
        result = gov.promote(str(f))
        assert result is not None
        assert result.passed is True

    def test_promote_missing(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        assert gov.promote("nope.md") is None

    def test_status(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("a.md", DocScope.DESCRIPTIVE)
        report = gov.status()
        assert report.total == 1

    def test_stale_docs(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("a.md", DocScope.DESCRIPTIVE)
        stale = gov.stale_docs()
        assert len(stale) == 0  # Fresh doc is not stale

    def test_list_docs(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("a.md", DocScope.DESCRIPTIVE)
        gov.register("b.md", DocScope.PROCEDURAL)
        docs = gov.list_docs()
        assert len(docs) == 2


# ===========================================================================
# Export tests
# ===========================================================================

class TestExport:
    """Tests for doc export functionality."""

    def test_frontmatter(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.AUTHORITATIVE,
            ttl_days=180,
            links=[DocLink(kind=LinkKind.DECISION, target="auth:jwt")],
            content_hash="abc123",
        )
        fm = generate_frontmatter(doc)
        assert fm.startswith("---")
        assert fm.endswith("---")
        assert "gov_scope: authoritative" in fm
        assert "gov_ttl: 180d" in fm
        assert "decision: auth:jwt" in fm
        assert "gov_hash: abc123" in fm

    def test_frontmatter_no_ttl(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        fm = generate_frontmatter(doc)
        assert "gov_ttl" not in fm

    def test_sidecar(self):
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[DocLink(kind=LinkKind.CODE, target="src/")],
        )
        sc = generate_sidecar(doc)
        assert sc["scope"] == "procedural"
        assert len(sc["links"]) == 1

    def test_export_via_governor(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("test.md", DocScope.AUTHORITATIVE,
                      links=[DocLink(kind=LinkKind.ANCHOR, target="safety")])
        result = gov.export_doc("test.md", "obsidian")
        assert "gov_scope: authoritative" in result

    def test_export_json(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        gov.register("test.md", DocScope.DESCRIPTIVE)
        result = gov.export_doc("test.md", "json")
        d = json.loads(result)
        assert d["scope"] == "descriptive"

    def test_export_missing(self, tmp_path: Path):
        gov = DocGovernor(tmp_path)
        result = gov.export_doc("nope.md")
        assert result == ""


# ===========================================================================
# Telemetry event tests
# ===========================================================================

class TestMakeDocEvent:
    """Tests for telemetry event creation."""

    def test_basic_event(self):
        result = DocCheckResult(
            doc_id="t", path="x.md", scope="descriptive", status="current",
            authority_claims=2, grounded_claims=1, ungrounded_claims=1,
            links_valid=3, links_broken=0,
        )
        e = make_doc_event(result)
        assert e["type"] == "doc_governance_check"
        assert e["doc_id"] == "t"
        assert e["passed"] is True

    def test_failed_event(self):
        result = DocCheckResult(
            doc_id="t", path="x.md", scope="authoritative", status="unsafe",
            passed=False, links_broken=2,
        )
        e = make_doc_event(result)
        assert e["passed"] is False
        assert e["status"] == "unsafe"


# ===========================================================================
# DocFinding tests
# ===========================================================================

class TestDocFinding:
    """Tests for DocFinding dataclass."""

    def test_to_dict(self):
        f = DocFinding(
            severity=CheckSeverity.ERROR,
            category="link",
            message="Broken link",
            line_number=42,
            details={"target": "x.py"},
        )
        d = f.to_dict()
        assert d["severity"] == "error"
        assert d["line_number"] == 42
        assert d["details"]["target"] == "x.py"

    def test_to_dict_no_line(self):
        f = DocFinding(severity=CheckSeverity.INFO, category="staleness", message="TTL expired")
        d = f.to_dict()
        assert "line_number" not in d

    def test_to_dict_no_details(self):
        f = DocFinding(severity=CheckSeverity.WARN, category="authority", message="Wrong scope")
        d = f.to_dict()
        assert "details" not in d


# ===========================================================================
# Golden-file schema tests
# ===========================================================================

class TestGoldenSchemas:
    """Tests that serialized schemas remain stable."""

    def test_gov_doc_schema(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        d = doc.to_dict()
        expected = {"doc_id", "path", "scope", "links", "ttl_days",
                     "registered_at", "last_verified", "status", "content_hash"}
        assert set(d.keys()) == expected

    def test_doc_link_schema(self):
        link = DocLink(kind=LinkKind.CODE, target="x")
        d = link.to_dict()
        assert set(d.keys()) == {"kind", "target", "description"}

    def test_doc_check_result_schema(self):
        r = DocCheckResult(doc_id="t", path="x", scope="d", status="c")
        d = r.to_dict()
        expected = {"doc_id", "path", "scope", "status", "findings",
                     "authority_claims", "grounded_claims", "ungrounded_claims",
                     "links_valid", "links_broken", "passed"}
        assert set(d.keys()) == expected

    def test_doc_receipt_schema(self):
        r = DocReceipt(
            doc_id="t", verified_at="x", status="c",
            commitments_extracted=0, links_valid=0, links_broken=0,
            authority_claims=0, grounded_claims=0, ungrounded_claims=0,
            content_hash="",
        )
        d = r.to_dict()
        expected = {"doc_id", "verified_at", "status", "commitments_extracted",
                     "links_valid", "links_broken", "authority_claims",
                     "grounded_claims", "ungrounded_claims", "content_hash"}
        assert set(d.keys()) == expected

    def test_staleness_report_schema(self):
        r = StalenessReport()
        d = r.to_dict()
        assert set(d.keys()) == {"total", "current", "stale", "historical", "unsafe", "docs"}

    def test_doc_event_schema(self):
        r = DocCheckResult(doc_id="t", path="x", scope="d", status="c")
        e = make_doc_event(r)
        expected = {"type", "doc_id", "path", "scope", "status", "findings",
                     "authority_claims", "grounded_claims", "ungrounded_claims",
                     "links_valid", "links_broken", "passed"}
        assert set(e.keys()) == expected


# ===========================================================================
# Edge case tests
# ===========================================================================

class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_content(self):
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        result = check_doc(doc, "")
        assert result.passed is True

    def test_all_code_blocks(self):
        content = "```\nYou MUST do this\n```"
        doc = GovDoc(doc_id="t", path="x.md", scope=DocScope.DESCRIPTIVE)
        result = check_doc(doc, content)
        # Authority in code blocks should be ignored
        assert result.authority_claims == 0

    def test_multiple_links_mixed_validity(self, tmp_path: Path):
        f = tmp_path / "real.py"
        f.write_text("pass")
        doc = GovDoc(
            doc_id="t", path="x.md", scope=DocScope.PROCEDURAL,
            links=[
                DocLink(kind=LinkKind.CODE, target=str(f)),
                DocLink(kind=LinkKind.CODE, target="/nonexistent.py"),
            ],
        )
        result = check_doc(doc, "Steps to follow.")
        assert result.links_valid == 1
        assert result.links_broken == 1

    def test_doc_id_deterministic(self):
        doc1 = GovDoc(doc_id="", path="same_path.md", scope=DocScope.DESCRIPTIVE)
        doc2 = GovDoc(doc_id="", path="same_path.md", scope=DocScope.DESCRIPTIVE)
        assert doc1.doc_id == doc2.doc_id

    def test_export_config(self):
        ec = ExportConfig(format="json", output_dir="/tmp/out")
        d = ec.to_dict()
        assert d["format"] == "json"
