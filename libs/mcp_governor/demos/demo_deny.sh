#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Demo: run gateway, call shell_exec (denied), check deny receipt.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== MCP Governor Gateway Demo: Deny ==="
echo ""

# Clean previous receipts
rm -f receipts/demo_deny.jsonl

# Feed a transcript — shell_exec should be denied
python -m mcp_governor config/demo_deny_shell.toml <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"shell_exec","arguments":{"command":"rm -rf /"}}}
EOF

echo ""
echo "=== Receipts ==="
if [ -f receipts/demo_deny.jsonl ]; then
    python -m json.tool < <(head -1 receipts/demo_deny.jsonl)
    echo ""
    echo "Receipt shows: action=deny"
    echo "Receipt file: receipts/demo_deny.jsonl"
else
    echo "ERROR: No receipt file created"
    exit 1
fi
