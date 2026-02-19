#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Demo: run gateway in passthrough-warn mode, call shell_exec (allowed but tagged).
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== MCP Governor Gateway Demo: Passthrough (allow-warn) ==="
echo ""

# Clean previous receipts
rm -f receipts/demo_passthrough.jsonl

# Feed a transcript — shell_exec would be denied, but passthrough allows it
python -m mcp_governor config/demo_passthrough.toml <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"shell_exec","arguments":{"command":"ls -la"}}}
EOF

echo ""
echo "=== Receipts ==="
if [ -f receipts/demo_passthrough.jsonl ]; then
    python -m json.tool < <(head -1 receipts/demo_passthrough.jsonl)
    echo ""
    echo "Receipt shows: action=allow, reason_code=gov.passthrough"
    echo "Receipt file: receipts/demo_passthrough.jsonl"
else
    echo "ERROR: No receipt file created"
    exit 1
fi
