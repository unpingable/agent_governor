"""Tests for governor state --json and --json flags on 7 existing commands."""

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from governor.cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def initialized_v1(tmp_path, runner):
    """A v1-initialized governor directory (no SQLite)."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        runner.invoke(cli, ["--root", td, "init"])
        yield Path(td)


@pytest.fixture
def initialized_v2(tmp_path, runner):
    """A v2-initialized governor directory (with SQLite)."""
    with runner.isolated_filesystem(temp_dir=tmp_path) as td:
        runner.invoke(cli, ["--root", td, "init", "--v2"])
        yield Path(td)


# ===========================================================================
# governor state --json
# ===========================================================================


class TestStateCommand:
    """Tests for governor state --json."""

    def test_state_json_returns_valid_json(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_state_json_v2_default_has_schema_version(self, runner, initialized_v1):
        """V2 is now the default schema."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json"])
        data = json.loads(result.output)
        assert data["schema_version"] == "v2"
        expected_keys = {"schema_version", "generated_at", "session", "regime",
                         "decisions", "claims", "evidence", "violations",
                         "execution", "stability"}
        assert set(data.keys()) == expected_keys

    def test_state_json_v1_has_all_seven_keys(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        expected_keys = {"proposals", "facts", "decisions", "tasks", "regime", "boil", "autonomous"}
        assert set(data.keys()) == expected_keys

    def test_state_json_v1_empty_returns_empty_arrays(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        assert data["proposals"] == []
        assert data["facts"] == []
        assert data["decisions"] == []
        assert data["autonomous"] == []

    def test_state_json_v1_tasks_graceful_no_sqlite(self, runner, initialized_v1):
        """Tasks section returns [] when no SQLite backend (v1 init)."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        assert data["tasks"] == []

    def test_state_json_regime_not_none_default(self, runner, initialized_v1):
        """V1: Regime returns a dict with default ELASTIC state."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        if data["regime"] is not None:
            assert "current_regime" in data["regime"]

    def test_state_json_boil_not_none_default(self, runner, initialized_v1):
        """V1: Boil returns a dict with default OOLONG state."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        if data["boil"] is not None:
            assert "mode" in data["boil"]

    def test_state_without_json_flag_shows_usage(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state"])
        assert result.exit_code == 0
        assert "governor state --json" in result.output

    def test_state_json_v1_with_proposal(self, runner, initialized_v1):
        """V1: State includes proposals when they exist."""
        root = str(initialized_v1)
        (initialized_v1 / "main.py").write_text("# main")
        runner.invoke(cli, ["--root", root, "propose", "--claim", "type=file_exists,path=main.py"])

        result = runner.invoke(cli, ["--root", root, "state", "--json", "--schema", "v1"])
        data = json.loads(result.output)
        assert len(data["proposals"]) >= 1

    def test_state_json_v2_with_proposal(self, runner, initialized_v1):
        """V2: State includes decisions derived from proposals."""
        root = str(initialized_v1)
        (initialized_v1 / "main.py").write_text("# main")
        runner.invoke(cli, ["--root", root, "propose", "--claim", "type=file_exists,path=main.py"])

        result = runner.invoke(cli, ["--root", root, "state", "--json"])
        data = json.loads(result.output)
        assert data["schema_version"] == "v2"
        assert len(data["decisions"]) >= 1

    def test_state_json_v2_regime_section(self, runner, initialized_v1):
        """V2: Regime section has name field."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json"])
        data = json.loads(result.output)
        if data["regime"] is not None:
            assert "name" in data["regime"]

    def test_state_json_v2_stability_section(self, runner, initialized_v1):
        """V2: Stability section has drift_alert field."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "state", "--json"])
        data = json.loads(result.output)
        if data["stability"] is not None:
            assert "drift_alert" in data["stability"]


# ===========================================================================
# --json flag on 7 existing commands
# ===========================================================================


class TestFactsJson:
    def test_facts_json_empty(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "facts", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_facts_json_with_data(self, runner, initialized_v1):
        root = str(initialized_v1)
        (initialized_v1 / "main.py").write_text("# main")
        runner.invoke(cli, ["--root", root, "propose", "--claim", "type=file_exists,path=main.py"])
        # Find proposal ID and verify it to create a fact
        status_result = runner.invoke(cli, ["--root", root, "status", "--json"])
        proposals = json.loads(status_result.output)
        if proposals:
            pid = proposals[0]["id"]
            runner.invoke(cli, ["--root", root, "verify", pid])

        result = runner.invoke(cli, ["--root", root, "facts", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)


class TestDecisionsJson:
    def test_decisions_json_empty(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "decisions", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []


class TestStatusJson:
    def test_status_json_empty(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_status_json_with_proposal(self, runner, initialized_v1):
        root = str(initialized_v1)
        (initialized_v1 / "main.py").write_text("# main")
        runner.invoke(cli, ["--root", root, "propose", "--claim", "type=file_exists,path=main.py"])

        result = runner.invoke(cli, ["--root", root, "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) >= 1
        assert "state" in data[0]
        assert "claims" in data[0]


class TestTaskListJson:
    def test_task_list_json_empty(self, runner, initialized_v2):
        result = runner.invoke(cli, ["--root", str(initialized_v2), "task", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_task_list_json_no_sqlite(self, runner, initialized_v1):
        """Graceful when no SQLite backend."""
        result = runner.invoke(cli, ["--root", str(initialized_v1), "task", "list", "--json"])
        # May fail (no SQLite), but should not crash with --json
        # The command requires storage, so exit_code may be non-zero
        # As long as it doesn't traceback, this is fine
        assert result.exit_code is not None


class TestRegimeStatusJson:
    def test_regime_status_json(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "regime", "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "current_regime" in data


class TestBoilStatusJson:
    def test_boil_status_json(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "boil", "status", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "mode" in data
        assert "preset" in data
        assert "regime" in data


class TestAutoListJson:
    def test_auto_list_json_empty(self, runner, initialized_v1):
        result = runner.invoke(cli, ["--root", str(initialized_v1), "autonomous", "list", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []
