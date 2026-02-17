# SPDX-License-Identifier: Apache-2.0
"""
Tests for Phase A1: Spine (locked project structure).
"""

import json
import pytest
from pathlib import Path

from governor.spine import (
    Spine,
    SpineViolation,
    SpineCheckResult,
    SpineManager,
    _glob_to_regex,
)


class TestSpine:
    def test_basic_creation(self):
        s = Spine(id="test", description="Test spine")
        assert s.id == "test"
        assert s.description == "Test spine"
        assert s.locked_by == "human"
        assert s.unlock_requires == "explicit_confirmation"

    def test_with_structure(self):
        s = Spine(
            id="project",
            structure={
                "files": {"src/main.py": "required", "README.md": "required"},
                "directories": {"src/": "required", "tests/": "required"},
                "forbidden_paths": ["*.secret"],
            },
        )
        assert s.structure["files"]["src/main.py"] == "required"
        assert len(s.structure["forbidden_paths"]) == 1

    def test_to_dict(self):
        s = Spine(id="test", description="desc")
        d = s.to_dict()
        assert d["id"] == "test"
        assert d["description"] == "desc"
        assert "locked_at" in d

    def test_from_dict(self):
        d = {
            "id": "loaded",
            "structure": {"files": {"a.py": "required"}},
            "description": "Loaded spine",
        }
        s = Spine.from_dict(d)
        assert s.id == "loaded"
        assert s.structure["files"]["a.py"] == "required"

    def test_roundtrip(self):
        s = Spine(
            id="rt",
            structure={"files": {"x.py": "required"}, "forbidden_paths": ["*.key"]},
            description="Roundtrip",
        )
        s2 = Spine.from_dict(s.to_dict())
        assert s2.id == s.id
        assert s2.structure == s.structure
        assert s2.description == s.description

    def test_save_and_load(self, tmp_path):
        s = Spine(id="saved", structure={"files": {"a.py": "required"}})
        path = tmp_path / "spine.json"
        s.save(path)
        assert path.exists()

        loaded = Spine.load(path)
        assert loaded.id == "saved"
        assert loaded.structure["files"]["a.py"] == "required"


class TestSpineVerifyProposal:
    def test_no_violations(self):
        s = Spine(id="test", structure={"files": {"src/main.py": "required"}})
        result = s.verify_proposal({"files_modified": ["src/other.py"]})
        assert result.valid is True
        assert len(result.violations) == 0

    def test_delete_required_file(self):
        s = Spine(id="test", structure={"files": {"src/main.py": "required"}})
        result = s.verify_proposal({"files_deleted": ["src/main.py"]})
        assert result.valid is False
        assert len(result.violations) == 1
        assert "required file" in result.violations[0].message.lower()

    def test_delete_non_required_file(self):
        s = Spine(id="test", structure={"files": {"src/main.py": "required"}})
        result = s.verify_proposal({"files_deleted": ["src/other.py"]})
        assert result.valid is True

    def test_touch_forbidden_path(self):
        s = Spine(id="test", structure={"forbidden_paths": ["*.secret", "credentials/*"]})
        result = s.verify_proposal({"files_created": ["db.secret"]})
        assert result.valid is False
        assert any("forbidden" in v.message.lower() for v in result.violations)

    def test_touch_forbidden_wildcard(self):
        s = Spine(id="test", structure={"forbidden_paths": ["credentials/*"]})
        result = s.verify_proposal({"files_modified": ["credentials/api.key"]})
        assert result.valid is False

    def test_no_forbidden_match(self):
        s = Spine(id="test", structure={"forbidden_paths": ["*.secret"]})
        result = s.verify_proposal({"files_created": ["src/main.py"]})
        assert result.valid is True

    def test_delete_from_required_directory(self):
        s = Spine(id="test", structure={"directories": {"src/": "required"}})
        result = s.verify_proposal({"files_deleted": ["src/main.py"]})
        assert result.valid is False
        assert any("required directory" in v.message.lower() for v in result.violations)

    def test_empty_proposal(self):
        s = Spine(id="test", structure={
            "files": {"src/main.py": "required"},
            "forbidden_paths": ["*.secret"],
        })
        result = s.verify_proposal({})
        assert result.valid is True

    def test_multiple_violations(self):
        s = Spine(id="test", structure={
            "files": {"src/main.py": "required", "README.md": "required"},
            "forbidden_paths": ["*.secret"],
        })
        result = s.verify_proposal({
            "files_deleted": ["src/main.py", "README.md"],
            "files_created": ["creds.secret"],
        })
        assert result.valid is False
        assert len(result.violations) >= 3

    def test_result_to_dict(self):
        s = Spine(id="test", structure={"files": {"a.py": "required"}})
        result = s.verify_proposal({"files_deleted": ["a.py"]})
        d = result.to_dict()
        assert d["valid"] is False
        assert len(d["violations"]) == 1
        assert "path" in d["violations"][0]


class TestGlobToRegex:
    def test_exact_match(self):
        r = _glob_to_regex("foo.py")
        assert r.match("foo.py")
        assert not r.match("bar.py")

    def test_star_wildcard(self):
        r = _glob_to_regex("*.py")
        assert r.match("foo.py")
        assert r.match("bar.py")
        assert not r.match("foo.js")

    def test_path_wildcard(self):
        r = _glob_to_regex("src/*")
        assert r.match("src/main.py")
        assert r.match("src/foo/bar.py")
        assert not r.match("tests/main.py")

    def test_question_mark(self):
        r = _glob_to_regex("test?.py")
        assert r.match("test1.py")
        assert r.match("testA.py")
        assert not r.match("test12.py")


class TestSpineManager:
    def test_no_spines_initially(self, tmp_path):
        manager = SpineManager(tmp_path)
        assert manager.list_spines() == []
        assert manager.active_spine() is None

    def test_lock_and_get(self, tmp_path):
        manager = SpineManager(tmp_path)
        spine = Spine(id="project", structure={"files": {"main.py": "required"}})
        manager.lock(spine)

        loaded = manager.get("project")
        assert loaded is not None
        assert loaded.id == "project"
        assert loaded.structure["files"]["main.py"] == "required"

    def test_list_spines(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(id="alpha"))
        manager.lock(Spine(id="beta"))

        spines = manager.list_spines()
        assert len(spines) == 2
        ids = {s.id for s in spines}
        assert "alpha" in ids
        assert "beta" in ids

    def test_unlock(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(id="to_remove"))
        assert manager.unlock("to_remove") is True
        assert manager.get("to_remove") is None

    def test_unlock_nonexistent(self, tmp_path):
        manager = SpineManager(tmp_path)
        assert manager.unlock("nope") is False

    def test_set_active(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(id="active_one"))
        assert manager.set_active("active_one") is True

        active = manager.active_spine()
        assert active is not None
        assert active.id == "active_one"

    def test_set_active_nonexistent(self, tmp_path):
        manager = SpineManager(tmp_path)
        assert manager.set_active("nope") is False

    def test_deactivate(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(id="s1"))
        manager.set_active("s1")
        manager.deactivate()
        assert manager.active_spine() is None

    def test_unlock_active_spine_deactivates(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(id="s1"))
        manager.set_active("s1")
        manager.unlock("s1")
        assert manager.active_spine() is None

    def test_verify_proposal_with_active_spine(self, tmp_path):
        manager = SpineManager(tmp_path)
        manager.lock(Spine(
            id="s1",
            structure={"files": {"main.py": "required"}},
        ))
        manager.set_active("s1")

        result = manager.verify_proposal({"files_deleted": ["main.py"]})
        assert result.valid is False

    def test_verify_proposal_without_spine(self, tmp_path):
        manager = SpineManager(tmp_path)
        result = manager.verify_proposal({"files_deleted": ["main.py"]})
        assert result.valid is True  # No spine = no constraints

    def test_persistence(self, tmp_path):
        m1 = SpineManager(tmp_path)
        m1.lock(Spine(id="persisted", description="test"))
        m1.set_active("persisted")

        m2 = SpineManager(tmp_path)
        assert len(m2.list_spines()) == 1
        assert m2.active_spine().id == "persisted"
