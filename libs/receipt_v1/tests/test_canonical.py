# SPDX-License-Identifier: Apache-2.0
"""Tests for Receipt Canonicalization v1."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from receipt_v1.canonical import args_hash, canonical_json, domain_hash, receipt_hash, result_hash, uuid7

VECTORS_PATH = Path(__file__).parent / "data" / "canonical_vectors.json"


def _load_vectors():
    with open(VECTORS_PATH) as f:
        return json.load(f)


class TestCanonicalJson:
    """Deterministic JSON canonicalization."""

    def test_sorted_keys(self):
        result = canonical_json({"z": 1, "a": 2, "m": 3})
        assert result == b'{"a":2,"m":3,"z":1}'

    def test_compact_separators(self):
        result = canonical_json({"key": "value"})
        # No spaces after : or ,
        assert b" " not in result

    def test_ensure_ascii(self):
        result = canonical_json({"emoji": "\u2603"})
        assert b"\\u2603" in result

    def test_no_floats_raises(self):
        import pytest
        with pytest.raises(ValueError, match="Float values are forbidden"):
            canonical_json({"val": 3.14})

    def test_no_floats_nested(self):
        import pytest
        with pytest.raises(ValueError, match="Float values are forbidden"):
            canonical_json({"outer": {"inner": 1.0}})

    def test_no_floats_in_array(self):
        import pytest
        with pytest.raises(ValueError, match="Float values are forbidden"):
            canonical_json({"items": [1, 2.0, 3]})

    def test_check_floats_disabled(self):
        # Should not raise when check_floats=False
        result = canonical_json({"val": 3.14}, check_floats=False)
        assert b"3.14" in result

    def test_golden_vectors(self):
        """All golden vectors must produce exact canonical bytes and hash."""
        data = _load_vectors()
        for vec in data["vectors"]:
            actual_bytes = canonical_json(vec["input"])
            actual_str = actual_bytes.decode("utf-8")
            assert actual_str == vec["canonical_utf8"], (
                f"Vector {vec['name']}: expected {vec['canonical_utf8']!r}, got {actual_str!r}"
            )
            actual_hash = hashlib.sha256(actual_bytes).hexdigest()
            assert actual_hash == vec["sha256"], (
                f"Vector {vec['name']}: hash mismatch"
            )


class TestDomainHash:
    """Domain-separated SHA-256."""

    def test_domain_separation(self):
        """Same data with different domains produces different hashes."""
        h1 = domain_hash("domain-a", b"data")
        h2 = domain_hash("domain-b", b"data")
        assert h1 != h2

    def test_golden_args_vector(self):
        data = _load_vectors()
        vec = data["domain_hash_vectors"][0]
        actual = args_hash(vec["tool_id"], vec["args"])
        assert actual == vec["expected"]

    def test_hex_format(self):
        h = domain_hash("test", b"data")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_result_hash_differs_from_args(self):
        """result_hash uses different domain than args_hash."""
        data = {"path": "/etc/config"}
        ah = args_hash("fs.read", data)
        rh = result_hash("fs.read", data)
        assert ah != rh  # different domain prefixes

    def test_receipt_hash_excludes_self(self):
        """receipt_hash ignores receipt_hash and signature fields."""
        d = {
            "receipt_id": "test",
            "receipt_hash": "should-be-ignored",
            "provenance": {
                "deployment_id": "dep",
                "instance_id": "inst",
                "governor_version": "1.0",
                "signature": "should-be-ignored",
                "signature_alg": "should-be-ignored",
                "signature_encoding": "should-be-ignored",
                "signing_key_id": "should-be-ignored",
            },
        }
        h1 = receipt_hash(d)

        d2 = {
            "receipt_id": "test",
            "receipt_hash": "totally-different-value",
            "provenance": {
                "deployment_id": "dep",
                "instance_id": "inst",
                "governor_version": "1.0",
                "signature": "different-sig",
                "signature_alg": "different-alg",
                "signature_encoding": "different-enc",
                "signing_key_id": "different-key",
            },
        }
        h2 = receipt_hash(d2)
        assert h1 == h2


class TestUuid7:
    """UUIDv7 generation (RFC 9562)."""

    def test_format(self):
        u = uuid7()
        parts = u.split("-")
        assert len(parts) == 5
        assert [len(p) for p in parts] == [8, 4, 4, 4, 12]

    def test_version_nibble(self):
        """Version nibble (bits 48-51) must be 7."""
        u = uuid7()
        hex_str = u.replace("-", "")
        version_nibble = int(hex_str[12], 16)
        assert version_nibble == 7

    def test_variant_bits(self):
        """Variant bits (bits 64-65) must be 10."""
        u = uuid7()
        hex_str = u.replace("-", "")
        variant_byte = int(hex_str[16:18], 16)
        assert (variant_byte >> 6) == 0b10

    def test_uniqueness(self):
        ids = {uuid7() for _ in range(100)}
        assert len(ids) == 100

    def test_time_sortable(self):
        """UUIDs generated in sequence should be roughly time-sortable."""
        import time
        u1 = uuid7()
        time.sleep(0.002)
        u2 = uuid7()
        # First 12 hex chars encode millisecond timestamp
        ts1 = u1.replace("-", "")[:12]
        ts2 = u2.replace("-", "")[:12]
        assert ts1 <= ts2
