#!/usr/bin/env bash
# Agent Governor — the OPA contrast (Act 2.5: the objection, pre-answered).
#
# One command. The SAME incident as Act 1 (the temporal-lapse impostor): a small
# Rego policy — correct for the world it is handed — returns `allow` over the
# input document, because the input asserts the credential is valid and nothing
# attests WHEN that was true. Custody refuses the same incident upstream: its
# premises failed preflight (the standing lapsed in the gap, on a named
# monotonic clock basis). Then OPA's verdict itself gets a receipt (policy
# hash, input provenance, decision) and enters the evidence plane.
#
#   policy engines decide over claims; custody systems decide whether those
#   claims may become premises.
#
# We're not an alternative to OPA. We're what OPA stands on.
#
# Requires: an editable install of this repo (`pip install -e .`). If the `opa`
# binary is installed, the policy is evaluated live; if not, the shim says so
# plainly and never fabricates a verdict (the 8-line policy reads by eye).
#
# Exit code: 0 iff the integrity assertions hold (custody refused for the RIGHT
# reason; OPA, when present, allowed — the contrast is real, not staged).

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

ROOT="$(mktemp -d "${TMPDIR:-/tmp}/ag-opa-contrast.XXXXXX")"

cd "${REPO_ROOT}"
python3 -m governor.demo_opa_contrast --root "${ROOT}" --format text
status=$?

echo "Custody receipts under: ${ROOT}"
exit "${status}"
