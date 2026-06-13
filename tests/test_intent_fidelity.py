"""Specimens for inert intent fidelity metadata (P1.4).

The contract is BORING: fidelity is optional, declared, unenforced, and its
absence preserves current semantics bit-for-bit. The default is None
("unspecified"), never a permissive class — defaulting to e.g. "heuristic" would
silently license loss. Supplying fidelity must not change any existing
receipt_hash (it is not folded into the hash payload).
"""

from __future__ import annotations

from typing import Any

import pytest

from governor.intent_compiler import (
    IntentCompilationResult,
    IntentFormResponse,
    build_form_schema,
    compile_intent,
)


def _schema_and_response(values: dict[str, Any] | None = None):
    schema = build_form_schema("session_start", mode="code")
    if values is None:
        values = {"profile": "strict", "mode": "code"}
    resp = IntentFormResponse(schema_id=schema.schema_id, values=values)
    return schema, resp


class TestDefaultBoring:
    def test_default_fidelity_is_none_not_a_class(self) -> None:
        # Rule #7: absent fidelity must NOT default to a permissive class.
        schema, resp = _schema_and_response()
        result = compile_intent(resp, schema)
        assert result.fidelity_class is None
        assert result.loss_posture is None

    def test_default_to_dict_omits_fidelity_keys(self) -> None:
        # Bit-for-bit: a no-fidelity compilation serializes exactly as before.
        schema, resp = _schema_and_response()
        d = compile_intent(resp, schema).to_dict()
        assert "fidelity_class" not in d
        assert "loss_posture" not in d

    def test_supplying_fidelity_does_not_change_receipt_hash(self) -> None:
        # Fidelity is carried but NOT folded into receipt_hash, so every
        # existing receipt is byte-identical whether or not fidelity is set.
        schema, resp = _schema_and_response()
        without = compile_intent(resp, schema)
        with_fid = compile_intent(
            resp, schema, fidelity_class="bounded", loss_posture="docs only"
        )
        assert without.receipt_hash == with_fid.receipt_hash


class TestFidelityWhenSupplied:
    def test_flows_into_result_and_to_dict(self) -> None:
        schema, resp = _schema_and_response()
        result = compile_intent(
            resp, schema, fidelity_class="exploratory", loss_posture="best effort"
        )
        assert result.fidelity_class == "exploratory"
        assert result.loss_posture == "best effort"
        d = result.to_dict()
        assert d["fidelity_class"] == "exploratory"
        assert d["loss_posture"] == "best effort"

    @pytest.mark.parametrize(
        "fid", ["exact", "bounded", "heuristic", "exploratory"]
    )
    def test_each_valid_class_accepted(self, fid: str) -> None:
        schema, resp = _schema_and_response()
        result = compile_intent(resp, schema, fidelity_class=fid)
        assert result.fidelity_class == fid

    def test_out_of_vocabulary_class_refused(self) -> None:
        schema, resp = _schema_and_response()
        with pytest.raises(ValueError, match="fidelity_class must be"):
            compile_intent(resp, schema, fidelity_class="vibes")


class TestRoundTrip:
    def test_roundtrip_with_fidelity(self) -> None:
        schema, resp = _schema_and_response()
        result = compile_intent(
            resp, schema, fidelity_class="bounded", loss_posture="scope-limited"
        )
        restored = IntentCompilationResult.from_dict(result.to_dict())
        assert restored.fidelity_class == "bounded"
        assert restored.loss_posture == "scope-limited"

    def test_from_dict_without_fidelity_keys_defaults_none(self) -> None:
        # Backward compat: an older serialized result (no fidelity keys) loads
        # with the conservative None default.
        schema, resp = _schema_and_response()
        d = compile_intent(resp, schema).to_dict()
        assert "fidelity_class" not in d
        restored = IntentCompilationResult.from_dict(d)
        assert restored.fidelity_class is None
        assert restored.loss_posture is None
