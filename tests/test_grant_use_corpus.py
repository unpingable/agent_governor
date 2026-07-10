# SPDX-License-Identifier: Apache-2.0
"""S5b — synthetic-ops disposition corpus. Ops-shaped workflows driven through
the REAL grant-use seam; each call's disposition is pinned. This is the
operating model (not the unit-test model) captured as regression. Extends
outward to adversarial cases (S5c); revocation/expiry/multi-actor need grant
lifecycle machinery not yet built (noted in the campaign STATUS).
"""

from __future__ import annotations

import pytest

from tests.grant_seam_harness import OpsScenario, run_ops_scenario

# The standard local-dev grant: write the crate subtrees; run cargo test/build.
_WRITE = ["/work/crates/**"]
_CMDS = [{"program": "cargo", "argv_prefix": ["test"]},
         {"program": "cargo", "argv_prefix": ["build"]}]

CORPUS = [
    OpsScenario(
        name="repeated_read_and_diagnostic",
        write_paths=_WRITE, commands=_CMDS,
        calls=[
            ("a", "Read", {"file_path": "/work/crates/x.rs"}),
            ("b", "Grep", {"pattern": "fn main"}),
            ("c", "Read", {"file_path": "/work/crates/x.rs"}),
            ("d", "Bash", {"command": "cargo test --lib"}),
            ("e", "Bash", {"command": "cargo build"}),
        ],
        expect={"a": "auto", "b": "auto", "c": "auto", "d": "accepted", "e": "accepted"},
    ),
    OpsScenario(
        name="observe_then_mutate_in_scope",
        write_paths=_WRITE, commands=_CMDS,
        calls=[
            ("r", "Read", {"file_path": "/work/crates/cfg.rs"}),
            ("w", "Edit", {"file_path": "/work/crates/cfg.rs"}),
        ],
        expect={"r": "auto", "w": "accepted"},
    ),
    OpsScenario(
        name="mutate_out_of_scope_widens",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("w", "Edit", {"file_path": "/etc/nginx/nginx.conf"})],
        expect={"w": "widens:write_path"},
    ),
    OpsScenario(
        name="network_expansion_widens",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("n", "Bash", {"command": "curl https://x.example/pull"})],
        expect={"n": "widens:network"},
    ),
    OpsScenario(
        name="git_expansion_widens",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("g", "Bash", {"command": "git push origin main"})],
        # git is program-classified to the git axis (locked) before any network
        # check — git being denied is the operative refusal (corpus caught the
        # assumption that it would read as network).
        expect={"g": "widens:git"},
    ),
    OpsScenario(
        name="opaque_shell_fails_closed",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("o", "Bash", {"command": "cargo test && rm -rf /"})],
        expect={"o": "unverifiable:opaque_shell"},
    ),
    OpsScenario(
        name="effect_escaping_flag_fails_closed",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("f", "Bash", {"command": "cargo test --target-dir=/etc/cron.d"})],
        expect={"f": "unverifiable:effect_escaping_flag"},
    ),
    OpsScenario(
        name="unknown_tool_fails_closed",
        write_paths=_WRITE, commands=_CMDS,
        calls=[("u", "NovelTool", {"x": 1})],
        expect={"u": "unverifiable:unknown_tool"},
    ),
    OpsScenario(
        name="mixed_ops_session",
        write_paths=_WRITE, commands=_CMDS,
        calls=[
            ("1", "Read", {"file_path": "/work/crates/a.rs"}),
            ("2", "Edit", {"file_path": "/work/crates/a.rs"}),
            ("3", "Bash", {"command": "cargo test"}),
            ("4", "Edit", {"file_path": "/work/../secrets/leak"}),
            ("5", "Bash", {"command": "cargo publish"}),
        ],
        expect={"1": "auto", "2": "accepted", "3": "accepted",
                "4": "widens:write_path", "5": "widens:shell"},
    ),
]


@pytest.mark.parametrize("scenario", CORPUS, ids=lambda s: s.name)
@pytest.mark.asyncio
async def test_ops_disposition_corpus(tmp_path, scenario):
    observed = await run_ops_scenario(tmp_path, scenario)
    assert observed == scenario.expect
