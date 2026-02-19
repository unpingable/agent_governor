#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# Demo: run gateway with allow-all config, call echo tool, check receipt.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "=== MCP Governor Gateway Demo: Allow ==="
echo ""

# Clean previous receipts
rm -f receipts/demo_allow.jsonl

# Feed a transcript to the gateway
python -m mcp_governor config/demo_allow.toml <<'EOF'
{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"demo-client","version":"1.0"}}}
{"jsonrpc":"2.0","method":"notifications/initialized"}
{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"echo","arguments":{"text":"Hello from the gateway demo!"}}}
EOF

echo ""
echo "=== Receipts ==="
if [ -f receipts/demo_allow.jsonl ]; then
    python -m json.tool < <(head -1 receipts/demo_allow.jsonl)
    echo ""
    echo "Receipt file: receipts/demo_allow.jsonl"
else
    echo "ERROR: No receipt file created"
    exit 1
fi
