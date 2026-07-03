# SPDX-License-Identifier: Apache-2.0
"""ag_shell_client protocol + model tests. Pure, no daemon required."""

from __future__ import annotations

import io
import json

import pytest

from ag_shell_client import (
    AUTH_ERROR_CODE,
    DaemonAuthError,
    DecisionItem,
    RPCError,
    decisions_from_response,
    default_socket_path,
    encode_message,
    make_request,
    parse_response,
    read_message,
)


def _reader(data: bytes):
    buf = io.BytesIO(data)
    return buf.readline, buf.read


def test_framing_roundtrip():
    msg = {"jsonrpc": "2.0", "method": "governor.hello", "params": {}, "id": 1}
    wire = encode_message(msg)
    assert wire.startswith(b"Content-Length: ")
    readline, readexactly = _reader(wire)
    assert read_message(readline, readexactly) == msg


def test_read_message_eof_and_no_length():
    assert read_message(*_reader(b"")) is None
    # headers with no Content-Length -> None (not a hang, not a guess)
    assert read_message(*_reader(b"X-Foo: bar\r\n\r\n")) is None


def test_socket_path_matches_daemon_derivation(tmp_path, monkeypatch):
    # The whole point of de-triplication: identical to the daemon's helper.
    monkeypatch.setenv("XDG_RUNTIME_DIR", str(tmp_path))
    from governor.daemon import default_socket_path as daemon_path

    gov = tmp_path / ".governor"
    gov.mkdir()
    assert default_socket_path(gov) == daemon_path(gov)


def test_socket_path_falls_back_to_tmp(monkeypatch, tmp_path):
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    p = default_socket_path(tmp_path)
    assert str(p).startswith("/tmp/governor-") and p.suffix == ".sock"


def test_make_request_shape():
    r = make_request("operator.decisions.list", {"kinds": ["intervention"]}, request_id=7)
    assert r == {"jsonrpc": "2.0", "method": "operator.decisions.list",
                 "params": {"kinds": ["intervention"]}, "id": 7}
    assert make_request("governor.now", request_id=1)["params"] == {}


def test_parse_response_result_and_errors():
    assert parse_response({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}) == {"ok": True}
    with pytest.raises(DaemonAuthError) as ei:
        parse_response({"error": {"code": AUTH_ERROR_CODE, "message": "not logged in"}})
    assert ei.value.code == AUTH_ERROR_CODE
    with pytest.raises(RPCError) as ei2:
        parse_response({"error": {"code": -32601, "message": "method not found"}})
    assert ei2.value.code == -32601
    assert not isinstance(ei2.value, DaemonAuthError)


def test_decision_item_from_dict_safe_defaults_and_required():
    d = {"decision_id": "dec_1", "kind": "intervention", "created_at": "t",
         "urgency": "blocking", "summary": "s",
         "options": [{"key": "y", "label": "approve", "action": "approve"}],
         "extra_unknown_field": "ignored"}
    it = DecisionItem.from_dict(d)
    assert it.decision_id == "dec_1" and it.is_known_kind and it.is_interrupt
    assert it.options[0].key == "y"
    # missing identity is refused
    with pytest.raises(ValueError):
        DecisionItem.from_dict({"kind": "intervention"})
    with pytest.raises(ValueError):
        DecisionItem.from_dict({"decision_id": "x"})


def test_unknown_kind_preserved_and_flagged():
    it = DecisionItem.from_dict({"decision_id": "d", "kind": "future_kind",
                                 "created_at": "t", "urgency": "normal", "summary": "s"})
    assert it.kind == "future_kind"  # preserved, not dropped
    assert it.is_known_kind is False  # flagged
    assert it.is_interrupt is False   # normal urgency accumulates


def test_unknown_urgency_conservatively_interrupts():
    it = DecisionItem.from_dict({"decision_id": "d", "kind": "intervention",
                                 "created_at": "t", "urgency": "weird", "summary": "s"})
    assert it.is_interrupt is True  # over-surface an unrecognized urgency


def test_from_dict_tolerates_malformed_nonmapping_fields():
    # Safe-defaults: a daemon that sends a truthy non-mapping for a dict field
    # (or a non-dict option) must degrade, not crash the reading shell.
    it = DecisionItem.from_dict(
        {"decision_id": "d", "kind": "intervention", "created_at": "t",
         "urgency": "normal", "summary": "s",
         "detail": "not-a-dict", "source": [1, 2],
         "options": ["garbage", {"key": "y", "label": "L", "action": "approve"}]}
    )
    assert it.detail == {} and it.source == {}
    assert [o.key for o in it.options] == ["y"]  # non-dict option dropped


def test_parse_response_tolerates_nonmapping_error():
    # A JSON-RPC-violating error (not an object) is still an error, not a result.
    with pytest.raises(RPCError):
        parse_response({"jsonrpc": "2.0", "id": 1, "error": "boom"})


def test_decisions_from_response():
    result = {"items": [
        {"decision_id": "d1", "kind": "intervention", "created_at": "t",
         "urgency": "blocking", "summary": "a"},
        {"decision_id": "d2", "kind": "promotion", "created_at": "t",
         "urgency": "normal", "summary": "b"},
    ], "count": 2}
    items = decisions_from_response(result)
    assert [i.decision_id for i in items] == ["d1", "d2"]


def test_encode_produces_valid_json_body():
    wire = encode_message({"a": 1})
    _, _, body = wire.partition(b"\r\n\r\n")
    assert json.loads(body) == {"a": 1}
