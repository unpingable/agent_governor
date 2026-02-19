# SPDX-License-Identifier: Apache-2.0
"""Tests for mcp_governor.framing."""

import io

import pytest

from mcp_governor.framing import read_message, write_message


class TestReadMessage:
    def test_simple_object(self):
        stream = io.StringIO('{"jsonrpc":"2.0","id":1,"method":"test"}\n')
        msg = read_message(stream)
        assert msg == {"jsonrpc": "2.0", "id": 1, "method": "test"}

    def test_eof_returns_none(self):
        stream = io.StringIO("")
        assert read_message(stream) is None

    def test_empty_line_returns_none(self):
        stream = io.StringIO("\n")
        assert read_message(stream) is None

    def test_invalid_json_raises(self):
        stream = io.StringIO("not json\n")
        with pytest.raises(ValueError, match="Invalid JSON-RPC"):
            read_message(stream)

    def test_non_object_raises(self):
        stream = io.StringIO("[1,2,3]\n")
        with pytest.raises(ValueError, match="must be an object"):
            read_message(stream)

    def test_multiple_messages(self):
        stream = io.StringIO('{"id":1}\n{"id":2}\n')
        assert read_message(stream) == {"id": 1}
        assert read_message(stream) == {"id": 2}
        assert read_message(stream) is None


class TestWriteMessage:
    def test_simple_write(self):
        stream = io.StringIO()
        write_message(stream, {"jsonrpc": "2.0", "id": 1})
        output = stream.getvalue()
        assert output.endswith("\n")
        assert "\n" not in output[:-1]  # no embedded newlines

    def test_roundtrip(self):
        original = {"jsonrpc": "2.0", "id": "abc", "method": "tools/call", "params": {"name": "echo"}}
        buf = io.StringIO()
        write_message(buf, original)
        buf.seek(0)
        recovered = read_message(buf)
        assert recovered == original

    def test_no_embedded_newlines_in_string_values(self):
        """String values with newlines are escaped, not literal."""
        stream = io.StringIO()
        write_message(stream, {"text": "line1\nline2"})
        raw = stream.getvalue()
        # Only one newline: the terminator
        assert raw.count("\n") == 1

    def test_compact_separators(self):
        stream = io.StringIO()
        write_message(stream, {"a": 1, "b": 2})
        raw = stream.getvalue().strip()
        assert " " not in raw  # compact, no spaces
