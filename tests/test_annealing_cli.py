"""CLI specimens for `governor annealing` (P2.3; read-only, no apply).

The slice is propose/list/show over candidate deltas. The load-bearing fences:
the group exposes NO apply/activate verb, and `propose` writes only a
proposed-delta RECORD under .governor/annealing_deltas/ — never config, never an
effect.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import annealing_cmd, cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def gov(tmp_path, runner):
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        result = runner.invoke(cli, ["--root", td, "init"])
        assert result.exit_code == 0, result.output
        yield td


_PROPOSE = [
    "annealing", "propose",
    "--surface", "retry_posture",
    "--target", "retry_budget",
    "--change-summary", "lower default retry budget",
    "--baseline-id", "cb_abc",
    "--expiry", "2026-06-20T00:00:00Z",
    "--rollback-trigger", "refusal_rate>0.2",
]


class TestNoApplyVerb:
    def test_group_has_no_apply_or_activate_command(self) -> None:
        names = set(annealing_cmd.commands)
        assert names == {"propose", "list", "show"}
        for forbidden in ("apply", "activate", "rollback", "promote"):
            assert forbidden not in names

    def test_cli_group_source_for_annealing_has_no_apply(self) -> None:
        # Grep-fence over the annealing modules + store: no apply/activate path,
        # no config write. (The store writes only delta records.)
        import governor.annealing as an
        import governor.annealing_store as ast

        for mod in (an, ast):
            src = Path(mod.__file__).read_text()
            for needle in ("def apply", "def activate", "def rollback", "config_write"):
                assert needle not in src, (mod.__file__, needle)


class TestProposeListShow:
    def test_propose_records_and_lists(self, runner, gov) -> None:
        gov_root = Path(gov) / ".governor"
        before = {p for p in gov_root.rglob("*") if p.is_file()}

        r = runner.invoke(cli, ["--root", gov, *_PROPOSE])
        assert r.exit_code == 0, r.output
        assert "proposed" in r.output

        after = {p for p in gov_root.rglob("*") if p.is_file()}
        new_files = after - before
        # Every new file landed under annealing_deltas/ — nothing written to
        # config or anywhere else in .governor.
        assert new_files, "propose recorded nothing"
        for p in new_files:
            assert p.parent == gov_root / "annealing_deltas", p
        assert len(list((gov_root / "annealing_deltas").glob("*.json"))) == 1

        rl = runner.invoke(cli, ["--root", gov, "annealing", "list"])
        assert rl.exit_code == 0
        assert "retry_posture/retry_budget" in rl.output

    def test_show_round_trips(self, runner, gov) -> None:
        runner.invoke(cli, ["--root", gov, *_PROPOSE])
        ids = runner.invoke(cli, ["--root", gov, "annealing", "list", "--json"])
        import json
        delta_id = json.loads(ids.output)["deltas"][0]
        rs = runner.invoke(cli, ["--root", gov, "annealing", "show", delta_id])
        assert rs.exit_code == 0
        shown = json.loads(rs.output)
        assert shown["surface"] == "retry_posture"
        assert shown["delta_id"] == delta_id

    def test_off_allowlist_surface_refused_nonzero(self, runner, gov) -> None:
        args = list(_PROPOSE)
        args[args.index("retry_posture")] = "not_a_surface"
        r = runner.invoke(cli, ["--root", gov, *args])
        assert r.exit_code == 1
        assert "REFUSED" in r.output
        assert "target_off_allowlist" in r.output

    def test_genesis_target_refused_nonzero(self, runner, gov) -> None:
        args = list(_PROPOSE)
        args[args.index("retry_budget")] = "standing_route"
        r = runner.invoke(cli, ["--root", gov, *args])
        assert r.exit_code == 1
        assert "genesis_class_target" in r.output

    def test_la_dependent_without_ref_refused(self, runner, gov) -> None:
        r = runner.invoke(cli, ["--root", gov, *_PROPOSE, "--la-dependent"])
        assert r.exit_code == 1
        assert "requires_la_custody" in r.output

    def test_refused_proposal_writes_no_record(self, runner, gov) -> None:
        args = list(_PROPOSE)
        args[args.index("retry_posture")] = "not_a_surface"
        runner.invoke(cli, ["--root", gov, *args])
        deltas_dir = Path(gov) / ".governor" / "annealing_deltas"
        # A refusal records nothing.
        assert not deltas_dir.exists() or not list(deltas_dir.glob("*.json"))

    def test_list_empty(self, runner, gov) -> None:
        r = runner.invoke(cli, ["--root", gov, "annealing", "list"])
        assert r.exit_code == 0
        assert "No proposed deltas" in r.output


class TestStoreReadFence:
    def test_get_rejects_path_traversal_and_non_id(self, tmp_path) -> None:
        from governor.annealing_store import AnnealingDeltaStore

        store = AnnealingDeltaStore(tmp_path)
        assert store.get("../etc/passwd") is None
        assert store.get("not-a-hex-id") is None

    def test_get_rejects_content_id_mismatch(self, tmp_path) -> None:
        # A record stored under a filename that doesn't match its content id is
        # not returned — delta_id is content, never trusted from the filename.
        import json

        from governor.annealing import AnnealingDelta, propose_delta
        from governor.annealing_store import AnnealingDeltaStore

        store = AnnealingDeltaStore(tmp_path)
        store.directory.mkdir(parents=True)
        delta = propose_delta(
            surface="routing", target="lane_weights", change_summary="x",
            baseline_id="cb", expiry="e", rollback_trigger="t",
        )
        assert isinstance(delta, AnnealingDelta)
        wrong_id = "0" * 64
        (store.directory / f"{wrong_id}.json").write_text(
            json.dumps(delta.to_dict())
        )
        assert store.get(wrong_id) is None  # filename id != content id
        assert store.get(delta.delta_id) is None  # no file under the real id
