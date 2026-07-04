# SPDX-License-Identifier: Apache-2.0
"""Make the top-level `harness/` package importable for in-process cage tests.

The project's pytest `pythonpath` is `["src"]` only (the harness is deliberately NOT
an installed package — it lives outside AG). The H1 contract tests treat the harness
as a black-box subprocess; the cage tests need to import `harness.cage` in-process to
exercise the contract directly. This conftest adds the repo root to `sys.path` for the
`tests/harness/` tree only — no global config change, no governor coupling."""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
