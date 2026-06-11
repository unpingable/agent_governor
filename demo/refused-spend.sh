#!/usr/bin/env bash
# Agent Governor — the refused-spend demo (Act 1: a stale yes).
#
# One command. Reproduces, end to end, the refusal that ordinary auth stacks
# don't make: two actions run the IDENTICAL gauntlet (same standing, observed at
# t=40, horizon t=50, admitting wicket) and differ only in WHEN the spend is
# attempted —
#
#   * the legitimate twin (t=45, within horizon) spends cleanly;
#   * the impostor (t=51, one second past the horizon) is refused, the receipt
#     showing both clocks and the gap. The credential was valid; the standing
#     was checked; it lapsed in the gap. Good-looking is not admissible.
#
# Custody is the only layer that sees the difference. Columbo, not Jobs.
#
# Requires: an editable install of this repo (`pip install -e .`) so `governor`
# and `python3 -m governor.*` are importable. No network, no clock, no LLM.
#
# Exit code is the demo's: 0 iff the integrity tripwire holds (the impostor
# refused for the RIGHT reason — the temporal lapse, spending no capacity — not
# a hidden short-circuit). A demo that passes for the wrong reason fails loudly.

set -euo pipefail

# Repo root = parent of this script's dir (so the demo runs from anywhere).
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# Receipts land in a fresh dir and are LEFT in place so you can inspect them
# afterward (Act 2 is querying the receipts — the custody chain is in the
# evidence, not in logs). The path is printed at the end.
ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ag-refused-spend.XXXXXX")"

cd "${REPO_ROOT}"
python3 -m governor.demo_refused_spend --root "${ROOT}" --format text
status=$?

echo "Receipts written under: ${ROOT}"
echo "Inspect them with:       governor receipts   (point GOVERNOR_DIR at a run subdir)"
echo "                         or: python3 -m governor.demo_refused_spend --root ${ROOT} --format json"

exit "${status}"
