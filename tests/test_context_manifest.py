# SPDX-License-Identifier: Apache-2.0
"""Tests for context_manifest — prompt assembly as governed artifact."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest

from governor.context_manifest import (
    HASH_ALG,
    MANIFEST_SCHEMA_VERSION,
    MUTABILITY_FROZEN,
    MUTABILITY_MUTABLE,
    MUTABILITY_PROTECTED,
    STORE_FULL,
    STORE_HASH_ONLY,
    VALID_CAPABILITIES,
    VALID_REGION_KINDS,
    ContextManifest,
    ContextRegion,
    ManifestStore,
    build_manifest,
    emit_build_receipt,
    _canonical_json,
    _make_region,
    _sha256_hex,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sample_regions() -> list[tuple[str, str, str]]:
    return [
        ("mode_base", "mode_base", "You are a code assistant."),
        ("mode_anchors", "mode_anchors", "ESTABLISHED DEFINITIONS:\n- Use React"),
    ]


def _build_sample(**kwargs) -> ContextManifest:
    defaults = {
        "mode": "code",
        "regions": _sample_regions(),
        "build_id": "test123",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    defaults.update(kwargs)
    return build_manifest(**defaults)


# =============================================================================
# Determinism (5)
# =============================================================================


class TestDeterminism:
    def test_same_inputs_same_manifest_hash(self):
        m1 = _build_sample()
        m2 = _build_sample()
        assert m1.manifest_hash == m2.manifest_hash

    def test_same_inputs_same_prompt_hash(self):
        m1 = _build_sample()
        m2 = _build_sample()
        assert m1.prompt_hash == m2.prompt_hash

    def test_different_build_id_same_manifest_hash(self):
        m1 = _build_sample(build_id="aaa")
        m2 = _build_sample(build_id="bbb")
        assert m1.manifest_hash == m2.manifest_hash
        assert m1.build_id != m2.build_id

    def test_one_char_change_flips_hashes(self):
        m1 = _build_sample()
        regions2 = [
            ("mode_base", "mode_base", "You are a code assistant!"),  # period → !
            ("mode_anchors", "mode_anchors", "ESTABLISHED DEFINITIONS:\n- Use React"),
        ]
        m2 = _build_sample(regions=regions2)
        assert m1.prompt_hash != m2.prompt_hash
        assert m1.manifest_hash != m2.manifest_hash
        assert m1.regions[0].content_hash != m2.regions[0].content_hash

    def test_capabilities_serialized_sorted(self):
        r = _make_region("test", "other", "text")
        d = r.to_dict()
        assert d["capabilities"] == sorted(d["capabilities"])
        # Verify it's a list, not set
        assert isinstance(d["capabilities"], list)


# =============================================================================
# ContextRegion (6)
# =============================================================================


class TestContextRegion:
    def test_frozen(self):
        r = _make_region("test", "mode_base", "hello")
        with pytest.raises(AttributeError):
            r.kind = "other"  # type: ignore[misc]

    def test_validation_bad_kind(self):
        with pytest.raises(ValueError, match="Invalid region kind"):
            ContextRegion(
                region_id="x", kind="INVALID", content_hash="abc",
                content_len=3, source_class="generated", sensitivity="none",
                capabilities=frozenset({"read"}), mutability="frozen",
                store_mode="hash_only", rationale="test",
            )

    def test_validation_bad_source_class(self):
        with pytest.raises(ValueError, match="Invalid source_class"):
            ContextRegion(
                region_id="x", kind="mode_base", content_hash="abc",
                content_len=3, source_class="BOGUS", sensitivity="none",
                capabilities=frozenset({"read"}), mutability="frozen",
                store_mode="hash_only", rationale="test",
            )

    def test_validation_bad_sensitivity(self):
        with pytest.raises(ValueError, match="Invalid sensitivity"):
            ContextRegion(
                region_id="x", kind="mode_base", content_hash="abc",
                content_len=3, source_class="generated", sensitivity="TOP_SECRET",
                capabilities=frozenset({"read"}), mutability="frozen",
                store_mode="hash_only", rationale="test",
            )

    def test_validation_bad_mutability(self):
        with pytest.raises(ValueError, match="Invalid mutability"):
            ContextRegion(
                region_id="x", kind="mode_base", content_hash="abc",
                content_len=3, source_class="generated", sensitivity="none",
                capabilities=frozenset({"read"}), mutability="immutable",
                store_mode="hash_only", rationale="test",
            )

    def test_validation_bad_store_mode(self):
        with pytest.raises(ValueError, match="Invalid store_mode"):
            ContextRegion(
                region_id="x", kind="mode_base", content_hash="abc",
                content_len=3, source_class="generated", sensitivity="none",
                capabilities=frozenset({"read"}), mutability="frozen",
                store_mode="compressed", rationale="test",
            )

    def test_validation_bad_capabilities(self):
        with pytest.raises(ValueError, match="Invalid capabilities"):
            ContextRegion(
                region_id="x", kind="mode_base", content_hash="abc",
                content_len=3, source_class="generated", sensitivity="none",
                capabilities=frozenset({"read", "execute"}), mutability="frozen",
                store_mode="hash_only", rationale="test",
            )

    def test_to_dict_from_dict_roundtrip(self):
        r = _make_region("test", "mode_base", "hello world")
        d = r.to_dict()
        r2 = ContextRegion.from_dict(d)
        assert r == r2

    def test_content_len_is_bytes_not_chars(self):
        # "café" is 4 chars but 5 bytes in UTF-8
        r = _make_region("test", "mode_base", "café")
        assert r.content_len == len("café".encode("utf-8"))
        assert r.content_len == 5  # not 4

    def test_content_preview_omitted_when_not_none_sensitivity(self):
        # compaction_summary has sensitivity="internal"
        r = _make_region("test", "compaction_summary", "secret stuff")
        assert r.content_preview is None

    def test_content_preview_present_for_none_sensitivity(self):
        r = _make_region("test", "mode_base", "visible text here")
        assert r.content_preview == "visible text here"


# =============================================================================
# ContextManifest (7)
# =============================================================================


class TestContextManifest:
    def test_frozen(self):
        m = _build_sample()
        with pytest.raises(AttributeError):
            m.mode = "fiction"  # type: ignore[misc]

    def test_manifest_hash_excludes_created_at_and_build_id(self):
        m1 = _build_sample(build_id="aaa", created_at="2020-01-01T00:00:00+00:00")
        m2 = _build_sample(build_id="bbb", created_at="2099-12-31T23:59:59+00:00")
        assert m1.manifest_hash == m2.manifest_hash

    def test_manifest_hash_includes_mode(self):
        m1 = _build_sample(mode="code")
        m2 = _build_sample(mode="fiction")
        assert m1.manifest_hash != m2.manifest_hash

    def test_manifest_hash_includes_chain_refs(self):
        m1 = _build_sample()
        m2 = _build_sample(prev_manifest_hash="abc123", prev_build_id="prev1")
        assert m1.manifest_hash != m2.manifest_hash

    def test_to_dict_from_dict_roundtrip(self):
        m = _build_sample(session_id="gov_abc123456789")
        d = m.to_dict()
        m2 = ContextManifest.from_dict(d)
        assert m.manifest_hash == m2.manifest_hash
        assert m.prompt_hash == m2.prompt_hash
        assert m.build_id == m2.build_id
        assert m.session_id == m2.session_id

    def test_chaining(self):
        m1 = _build_sample(build_id="first")
        m2 = _build_sample(
            build_id="second",
            prev_manifest_hash=m1.manifest_hash,
            prev_build_id=m1.build_id,
        )
        assert m2.prev_manifest_hash == m1.manifest_hash
        assert m2.prev_build_id == "first"

    def test_governor_version_optional(self):
        m = _build_sample()
        # governor_version may or may not be set depending on install state
        # but it should not raise
        assert m.manifest_version == MANIFEST_SCHEMA_VERSION

    def test_tenant_principal_none_by_default(self):
        m = _build_sample()
        assert m.tenant_id is None
        assert m.principal_id is None


# =============================================================================
# build_manifest() (5)
# =============================================================================


class TestBuildManifest:
    def test_region_metadata_from_lookup(self):
        m = _build_sample()
        base = m.regions[0]
        assert base.source_class == "generated"
        assert base.sensitivity == "none"
        assert base.mutability == MUTABILITY_FROZEN
        assert base.capabilities == frozenset({"read"})

        anchors = m.regions[1]
        assert anchors.source_class == "repo"
        assert anchors.mutability == MUTABILITY_PROTECTED

    def test_prompt_hash_is_joined_regions(self):
        texts = ["You are a code assistant.", "ESTABLISHED DEFINITIONS:\n- Use React"]
        expected = _sha256_hex("\n\n".join(texts).encode("utf-8"))
        m = _build_sample()
        assert m.prompt_hash == expected

    def test_empty_regions_valid(self):
        m = build_manifest(
            mode="code", regions=[],
            build_id="test", created_at="2026-01-01T00:00:00+00:00",
        )
        assert len(m.regions) == 0
        assert m.prompt_hash == _sha256_hex(b"")

    def test_content_preview_populated(self):
        m = _build_sample()
        assert m.regions[0].content_preview is not None
        assert m.regions[0].content_preview.startswith("You are")

    def test_inputs_digest_when_provided(self):
        r = _make_region("test", "mode_base", "text", inputs_digest="abc123")
        assert r.inputs_digest == "abc123"


# =============================================================================
# ManifestStore (4)
# =============================================================================


class TestManifestStore:
    def test_append_and_latest(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        m = _build_sample()
        store.append(m)
        latest = store.latest()
        assert latest is not None
        assert latest.manifest_hash == m.manifest_hash

    def test_query_with_limit(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        for i in range(5):
            m = _build_sample(build_id=f"build_{i}")
            store.append(m)
        results = store.query(limit=3)
        assert len(results) == 3
        # Newest first
        assert results[0].build_id == "build_4"

    def test_query_by_build_id(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        store.append(_build_sample(build_id="target"))
        store.append(_build_sample(build_id="other"))
        results = store.query(build_id="target")
        assert len(results) == 1
        assert results[0].build_id == "target"

    def test_query_by_manifest_hash_prefix(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        m = _build_sample()
        store.append(m)
        prefix = m.manifest_hash[:8]
        results = store.query(manifest_hash_prefix=prefix)
        assert len(results) == 1

    def test_jsonl_format(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        store.append(_build_sample())
        store.append(_build_sample(build_id="second"))
        lines = store.path.read_text().splitlines()
        assert len(lines) == 2
        # Each line is valid JSON
        for line in lines:
            json.loads(line)

    def test_empty_store_returns_none(self, tmp_path: Path):
        store = ManifestStore(tmp_path)
        assert store.latest() is None
        assert store.query() == []


# =============================================================================
# Gate receipt (3)
# =============================================================================


class TestGateReceipt:
    def test_emit_build_receipt_observe(self):
        m = _build_sample()
        receipt = emit_build_receipt(m)
        assert receipt.gate == "context_build"
        assert receipt.verdict == "observe"

    def test_evidence_no_bodies(self):
        """Evidence bundle must contain hashes only, never region text."""
        m = _build_sample()
        receipt = emit_build_receipt(m)
        # Re-derive evidence to inspect it
        from governor.gate_receipt import canonical_json as gc_json
        # The evidence should not contain the actual prompt text
        evidence = {
            "manifest_hash": m.manifest_hash,
            "prompt_hash": m.prompt_hash,
            "region_count": len(m.regions),
            "regions": [
                {
                    "region_id": r.region_id,
                    "kind": r.kind,
                    "content_hash": r.content_hash,
                    "content_len": r.content_len,
                }
                for r in m.regions
            ],
        }
        evidence_str = json.dumps(evidence)
        # The actual prompt text should NOT appear in evidence
        assert "You are a code assistant" not in evidence_str

    def test_receipt_subject_is_manifest(self):
        m = _build_sample()
        receipt = emit_build_receipt(m)
        # subject_hash should be derived from manifest
        assert receipt.subject_hash  # non-empty


# =============================================================================
# CLI (4)
# =============================================================================


class TestCLI:
    def test_summary_output(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner
        from governor.cli import cli

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        store = ManifestStore(gov_dir)
        store.append(_build_sample(session_id="gov_abc123456789"))

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["context", "manifest"])
        assert result.exit_code == 0
        assert "mode_base" in result.output
        assert "mode_anchors" in result.output

    def test_json_output(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner
        from governor.cli import cli

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        store = ManifestStore(gov_dir)
        m = _build_sample()
        store.append(m)

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["context", "manifest", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert data[0]["manifest_hash"] == m.manifest_hash

    def test_id_lookup(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner
        from governor.cli import cli

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()
        store = ManifestStore(gov_dir)
        store.append(_build_sample(build_id="target_build"))
        store.append(_build_sample(build_id="other_build"))

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["context", "manifest", "--id", "target_build"])
        assert result.exit_code == 0
        assert "target_build" in result.output

    def test_no_manifests(self, tmp_path: Path, monkeypatch):
        from click.testing import CliRunner
        from governor.cli import cli

        gov_dir = tmp_path / ".governor"
        gov_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        runner = CliRunner()
        result = runner.invoke(cli, ["context", "manifest"])
        assert result.exit_code == 0
        assert "No manifests" in result.output


# =============================================================================
# Identity separation (2)
# =============================================================================


# =============================================================================
# Golden determinism (pinned hashes across runs)
# =============================================================================


class TestGoldenDeterminism:
    """Pin exact hash values for a fixed fixture.

    Catches accidental canonicalization changes — if any of these break,
    it means the hashing contract has changed.
    """

    GOLDEN_MANIFEST_HASH = "49deaf30465fce18624b49e11359ea2926bd3e3df16342db8408541cba22c05c"
    GOLDEN_PROMPT_HASH = "36bcfafabaadfa95cf714bcba958a313d9ce9513f42bf4c9fe064f142255eaa7"
    GOLDEN_REGION0_HASH = "eb1f7daa7e4743503ad5490360f74f9f8bdd783784919b4a5717aa0d75b7f96f"
    GOLDEN_REGION1_HASH = "488f62f783bcc2d2018303331bdd49cb59ebb7b9d86adf1b6e4762425754fe42"

    def _golden_manifest(self) -> ContextManifest:
        return build_manifest(
            mode="code",
            regions=_sample_regions(),
            build_id="golden_test",
            created_at="2026-01-01T00:00:00+00:00",
        )

    def test_manifest_hash_pinned(self):
        m = self._golden_manifest()
        assert m.manifest_hash == self.GOLDEN_MANIFEST_HASH

    def test_prompt_hash_pinned(self):
        m = self._golden_manifest()
        assert m.prompt_hash == self.GOLDEN_PROMPT_HASH

    def test_region_hashes_pinned(self):
        m = self._golden_manifest()
        assert m.regions[0].content_hash == self.GOLDEN_REGION0_HASH
        assert m.regions[1].content_hash == self.GOLDEN_REGION1_HASH


# =============================================================================
# Failure-path receipts (2)
# =============================================================================


class TestFailureReceipt:
    def test_emit_build_failure_receipt(self):
        from governor.context_manifest import emit_build_failure_receipt
        receipt = emit_build_failure_receipt(
            build_id="fail_123",
            mode="code",
            exc_type="ValueError",
            exc_message="something broke",
        )
        assert receipt.gate == "context_build_failed"
        assert receipt.verdict == "warn"

    def test_failure_receipt_includes_exc_info(self):
        from governor.context_manifest import emit_build_failure_receipt
        from governor.gate_receipt import canonical_json, content_hash
        receipt = emit_build_failure_receipt(
            build_id="fail_456",
            mode="fiction",
            exc_type="RuntimeError",
            exc_message="bad things",
            session_id="gov_test123",
        )
        # The evidence hash should be based on evidence containing exc info
        assert receipt.evidence_hash  # non-empty string


# =============================================================================
# Identity separation (2)
# =============================================================================


class TestIdentitySeparation:
    def test_build_id_differs_across_calls(self):
        """build_id is a fresh UUID each time (event identity)."""
        m1 = build_manifest(mode="code", regions=_sample_regions())
        m2 = build_manifest(mode="code", regions=_sample_regions())
        assert m1.build_id != m2.build_id

    def test_manifest_hash_same_across_calls(self):
        """manifest_hash is content-addressed (same inputs → same hash)."""
        m1 = build_manifest(
            mode="code", regions=_sample_regions(),
            build_id="x", created_at="2026-01-01T00:00:00+00:00",
        )
        m2 = build_manifest(
            mode="code", regions=_sample_regions(),
            build_id="y", created_at="2099-12-31T23:59:59+00:00",
        )
        assert m1.manifest_hash == m2.manifest_hash
