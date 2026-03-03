# SPDX-License-Identifier: Apache-2.0
"""Tests for HashRef — cross-module hash comparison helper."""

import pytest

from governor.hash_ref import HashRef


# ── Parsing ──────────────────────────────────────────────────────────────────


class TestParse:
    def test_prefixed_sha256(self):
        h = HashRef.parse("sha256:9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
        assert h.alg == "sha256"
        assert h.digest == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        assert h.prefixed is True

    def test_raw_hex(self):
        h = HashRef.parse("9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08")
        assert h.alg == "sha256"  # default
        assert h.digest == "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08"
        assert h.prefixed is False

    def test_custom_default_alg(self):
        h = HashRef.parse("abcdef01", default_alg="sha384")
        assert h.alg == "sha384"

    def test_prefixed_overrides_default_alg(self):
        h = HashRef.parse("sha384:abcdef01", default_alg="sha256")
        assert h.alg == "sha384"

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="Empty"):
            HashRef.parse("")

    def test_non_hex_raises(self):
        with pytest.raises(ValueError, match="Not a valid hex"):
            HashRef.parse("not-a-hash")

    def test_whitespace_stripped(self):
        h = HashRef.parse("  sha256:abcdef01  ")
        assert h.digest == "abcdef01"

    def test_uppercase_hex_lowered(self):
        h = HashRef.parse("ABCDEF01")
        assert h.digest == "abcdef01"

    def test_truncated_hex(self):
        """Short hex digests (e.g., [:16]) are valid."""
        h = HashRef.parse("9f86d081884c7d65")
        assert h.digest == "9f86d081884c7d65"


# ── Comparison ───────────────────────────────────────────────────────────────


class TestComparison:
    def test_prefixed_equals_raw(self):
        """The whole point: same digest compares equal regardless of format."""
        prefixed = HashRef.parse("sha256:abcdef01")
        raw = HashRef.parse("abcdef01")
        assert prefixed == raw
        assert prefixed.matches(raw)

    def test_different_digest_not_equal(self):
        a = HashRef.parse("sha256:aaaa")
        b = HashRef.parse("sha256:bbbb")
        assert a != b
        assert not a.matches(b)

    def test_different_alg_not_equal(self):
        a = HashRef.parse("sha256:abcdef01")
        b = HashRef.parse("sha384:abcdef01")
        assert a != b

    def test_hash_set_membership(self):
        """Can use HashRef in sets for dedup across formats."""
        s = {HashRef.parse("sha256:abcdef01")}
        assert HashRef.parse("abcdef01") in s

    def test_hash_dict_key(self):
        """Can use HashRef as dict key."""
        d = {HashRef.parse("sha256:abcdef01"): "found"}
        assert d[HashRef.parse("abcdef01")] == "found"

    def test_not_equal_to_string(self):
        h = HashRef.parse("sha256:abcdef01")
        assert h != "sha256:abcdef01"


# ── Output ───────────────────────────────────────────────────────────────────


class TestOutput:
    def test_canonical_always_prefixed(self):
        h = HashRef.parse("abcdef01")
        assert h.canonical() == "sha256:abcdef01"

    def test_hex_always_raw(self):
        h = HashRef.parse("sha256:abcdef01")
        assert h.hex() == "abcdef01"

    def test_str_is_canonical(self):
        h = HashRef.parse("abcdef01")
        assert str(h) == "sha256:abcdef01"

    def test_repr(self):
        h = HashRef.parse("sha256:abcdef01")
        assert repr(h) == "HashRef('sha256:abcdef01')"


# ── Cross-module comparison ─────────────────────────────────────────────────


class TestCrossModule:
    """Verify HashRef bridges the gate_receipt / signals divergence."""

    def test_gate_receipt_vs_signal_envelope(self):
        """gate_receipt.content_hash() returns raw hex,
        signals.content_hash() returns sha256:<hex>.
        HashRef makes them comparable.
        """
        import hashlib
        data = b"test payload"
        digest = hashlib.sha256(data).hexdigest()

        # Simulate gate_receipt.content_hash()
        gate_hash = HashRef.parse(digest)

        # Simulate signals.content_hash()
        signal_hash = HashRef.parse(f"sha256:{digest}")

        assert gate_hash == signal_hash
        assert gate_hash.matches(signal_hash)

    def test_gate_receipt_style(self):
        """Raw hex from gate_receipt normalizes to prefixed."""
        from governor.gate_receipt import content_hash as gate_content_hash
        h = gate_content_hash(b"hello")
        ref = HashRef.parse(h)
        assert ref.prefixed is False
        assert ref.canonical().startswith("sha256:")

    def test_signal_envelope_style(self):
        """Prefixed hash from signals parses correctly."""
        from governor.signals.envelope import content_hash as signal_content_hash
        h = signal_content_hash(b"hello")
        ref = HashRef.parse(h)
        assert ref.prefixed is True

    def test_same_data_matches_across_modules(self):
        """Same bytes → same HashRef regardless of module."""
        from governor.gate_receipt import content_hash as gate_ch
        from governor.signals.envelope import content_hash as signal_ch

        data = b"identical payload"
        gate_ref = HashRef.parse(gate_ch(data))
        signal_ref = HashRef.parse(signal_ch(data))
        assert gate_ref == signal_ref


# ── Frozen / slots ──────────────────────────────────────────────────────────


class TestImmutability:
    def test_frozen(self):
        h = HashRef.parse("sha256:abcdef01")
        with pytest.raises(AttributeError):
            h.alg = "md5"  # type: ignore[misc]

    def test_frozen_digest(self):
        h = HashRef.parse("sha256:abcdef01")
        with pytest.raises(AttributeError):
            h.digest = "00000000"  # type: ignore[misc]
