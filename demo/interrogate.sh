#!/usr/bin/env bash
# Agent Governor — the interrogation (Act 2: "just one more thing").
#
# Cross-examine the corpse: the receipts an Act-1 run (demo/refused-spend.sh)
# left on disk. Six questions, each a runnable query — the custody chain
# reconstructs from EVIDENCE, not logs:
#
#   Q1  what happened to the spend?        → the chain walk (why)
#   Q2  why was it refused?                → the typed reason, on the receipt
#   Q3  which predicate failed?            → gap > bound, the numbers
#   Q4  stale under WHICH clock witness?   → the named monotonic basis
#   Q5  what did the naive gate conclude?  → OPA's own verdict, receipted
#   Q6  a receipt that doesn't exist?      → honest absence, never inference
#
# Usage:
#   demo/interrogate.sh <root>   # the path refused-spend.sh printed
#   demo/interrogate.sh          # no corpse handy? runs Act 1 + 2.5 itself
#
# Exit code: 0 iff every assertion holds — an interrogation that passes for
# the wrong reason fails loudly, same discipline as the other acts.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"
python3 -m governor.demo_interrogate "$@"
