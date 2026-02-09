#!/usr/bin/env bash
# Run Maude ↔ Governor contract tests via docker compose.
#
# Usage:
#   cd integration && bash run.sh
#   MAUDE_DIR=/path/to/maude bash run.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Resolve maude repo location
MAUDE_DIR="${MAUDE_DIR:-$(cd "$SCRIPT_DIR/../../maude" 2>/dev/null && pwd)}"

if [ ! -f "$MAUDE_DIR/pyproject.toml" ]; then
    echo "ERROR: maude repo not found at $MAUDE_DIR"
    echo "Set MAUDE_DIR to the maude repo root, e.g.:"
    echo "  MAUDE_DIR=/path/to/maude bash run.sh"
    exit 1
fi

echo "=== Maude ↔ Governor contract tests ==="
echo "Governor:  $(cd "$SCRIPT_DIR/.." && pwd)"
echo "Maude:     $MAUDE_DIR"
echo ""

export MAUDE_DIR

# Resolve gov-webui repo location (for contract test governor container)
GOV_WEBUI_DIR="${GOV_WEBUI_DIR:-$(cd "$SCRIPT_DIR/../../gov-webui" 2>/dev/null && pwd)}"
if [ ! -f "$GOV_WEBUI_DIR/pyproject.toml" ]; then
    echo "ERROR: gov-webui repo not found at $GOV_WEBUI_DIR"
    echo "Set GOV_WEBUI_DIR to the gov-webui repo root, e.g.:"
    echo "  GOV_WEBUI_DIR=/path/to/gov-webui bash run.sh"
    exit 1
fi
export GOV_WEBUI_DIR
echo "Gov-WebUI: $GOV_WEBUI_DIR"
echo ""

docker compose -f docker-compose.contract.yml up \
    --build \
    --abort-on-container-exit \
    --exit-code-from contract-tests
