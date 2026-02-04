"""
Tests for InvariantSpec, InvariantStore, and materialization.
Deferred 1: Invariant management.
"""

import json
import pytest
from pathlib import Path

from governor.invariant_store import (
    InvariantSpec,
    InvariantStore,
    VALID_KINDS,
    _materialize_spec,
)
from governor.invariants import (
    Invariant,
    InvariantResult,
    InvariantSet,
    InvariantType,
)


# =============================================================================
# TestInvariantSpec
# =============================================================================


class TestInvariantSpec:
    def test_creation(self):
        spec = InvariantSpec(id="test_1", kind="test", params={"command": "pytest"})
        assert spec.id == "test_1"
        assert spec.kind == "test"
        assert spec.params == {"command": "pytest"}
        assert spec.on_violation == "block"
        assert spec.enabled is True

    def test_creation_with_overrides(self):
        spec = InvariantSpec(
            id="my_inv",
            kind="no-secrets",
            on_violation="warn",
            enabled=False,
        )
        assert spec.on_violation == "warn"
        assert spec.enabled is False

    def test_invalid_kind_raises(self):
        with pytest.raises(ValueError, match="Invalid kind"):
            InvariantSpec(id="bad", kind="nonexistent")

    def test_to_dict(self):
        spec = InvariantSpec(id="f1", kind="file-exists", params={"path": "README.md"})
        d = spec.to_dict()
        assert d["id"] == "f1"
        assert d["kind"] == "file-exists"
        assert d["params"] == {"path": "README.md"}
        assert d["on_violation"] == "block"
        assert d["enabled"] is True
        assert "created_at" in d

    def test_from_dict(self):
        data = {
            "id": "x",
            "kind": "no-secrets",
            "params": {},
            "on_violation": "warn",
            "enabled": False,
            "created_at": "2025-01-01T00:00:00",
        }
        spec = InvariantSpec.from_dict(data)
        assert spec.id == "x"
        assert spec.kind == "no-secrets"
        assert spec.on_violation == "warn"
        assert spec.enabled is False
        assert spec.created_at == "2025-01-01T00:00:00"

    def test_roundtrip(self):
        spec = InvariantSpec(
            id="rt",
            kind="forbidden",
            params={"pattern": "*.secret"},
            on_violation="warn",
        )
        d = spec.to_dict()
        spec2 = InvariantSpec.from_dict(d)
        assert spec2.id == spec.id
        assert spec2.kind == spec.kind
        assert spec2.params == spec.params
        assert spec2.on_violation == spec.on_violation

    def test_defaults(self):
        spec = InvariantSpec(id="d", kind="no-secrets")
        assert spec.params == {}
        assert spec.on_violation == "block"
        assert spec.enabled is True
        assert spec.created_at  # non-empty

    def test_validate_params_ok(self):
        spec = InvariantSpec(id="t", kind="test", params={"command": "pytest"})
        assert spec.validate_params() == []

    def test_validate_params_missing(self):
        spec = InvariantSpec(id="t", kind="test", params={})
        errors = spec.validate_params()
        assert len(errors) == 1
        assert "command" in errors[0]

    def test_validate_file_exists_missing_path(self):
        spec = InvariantSpec(id="f", kind="file-exists", params={})
        errors = spec.validate_params()
        assert len(errors) == 1
        assert "path" in errors[0]


# =============================================================================
# TestValidKinds
# =============================================================================


class TestValidKinds:
    def test_all_kinds_present(self):
        expected = {"test", "file-exists", "dir-exists", "forbidden", "no-secrets", "max-file-size", "chrono", "identity"}
        assert set(VALID_KINDS.keys()) == expected

    def test_each_kind_has_factory(self):
        for kind, info in VALID_KINDS.items():
            assert "factory" in info
            assert "required_params" in info
            assert "description" in info

    def test_no_secrets_no_required_params(self):
        assert VALID_KINDS["no-secrets"]["required_params"] == []

    def test_test_requires_command(self):
        assert "command" in VALID_KINDS["test"]["required_params"]


# =============================================================================
# TestInvariantStore
# =============================================================================


class TestInvariantStore:
    def test_add_and_get(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="s1", kind="no-secrets")
        store.add(spec)
        got = store.get("s1")
        assert got is not None
        assert got.id == "s1"
        assert got.kind == "no-secrets"

    def test_get_nonexistent(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        assert store.get("missing") is None

    def test_list_empty(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        assert store.list_all() == []

    def test_list_after_add(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="a", kind="no-secrets"))
        store.add(InvariantSpec(id="b", kind="max-file-size", params={"max_kb": 100}))
        specs = store.list_all()
        assert len(specs) == 2
        ids = {s.id for s in specs}
        assert ids == {"a", "b"}

    def test_remove_existing(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="rm", kind="no-secrets"))
        assert store.remove("rm") is True
        assert store.get("rm") is None

    def test_remove_nonexistent(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        assert store.remove("nope") is False

    def test_overwrite(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="ow", kind="no-secrets", on_violation="block"))
        store.add(InvariantSpec(id="ow", kind="no-secrets", on_violation="warn"))
        spec = store.get("ow")
        assert spec is not None
        assert spec.on_violation == "warn"

    def test_bad_json_skip(self, tmp_path):
        root = tmp_path
        inv_dir = root / ".governor" / "invariants"
        inv_dir.mkdir(parents=True)
        (inv_dir / "bad.json").write_text("not json{{{")
        store = InvariantStore(root)
        assert store.list_all() == []

    def test_persistence(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store1 = InvariantStore(root)
        store1.add(InvariantSpec(id="persist", kind="no-secrets"))
        # New store instance reads from disk
        store2 = InvariantStore(root)
        spec = store2.get("persist")
        assert spec is not None
        assert spec.id == "persist"

    def test_creates_invariant_dir(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="x", kind="no-secrets"))
        assert (root / ".governor" / "invariants").is_dir()

    def test_file_format(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="fmt", kind="no-secrets"))
        path = root / ".governor" / "invariants" / "fmt.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["id"] == "fmt"
        assert data["kind"] == "no-secrets"

    def test_list_sorted(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="z_last", kind="no-secrets"))
        store.add(InvariantSpec(id="a_first", kind="no-secrets"))
        specs = store.list_all()
        assert specs[0].id == "a_first"
        assert specs[1].id == "z_last"

    def test_remove_then_list(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="keep", kind="no-secrets"))
        store.add(InvariantSpec(id="drop", kind="no-secrets"))
        store.remove("drop")
        specs = store.list_all()
        assert len(specs) == 1
        assert specs[0].id == "keep"

    def test_id_sanitization(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="path/with/slashes", kind="no-secrets")
        store.add(spec)
        got = store.get("path/with/slashes")
        assert got is not None
        assert got.id == "path/with/slashes"


# =============================================================================
# TestMaterialize
# =============================================================================


class TestMaterialize:
    def test_materialize_no_secrets(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="ns", kind="no-secrets")
        store.add(spec)
        inv = store.materialize("ns")
        assert inv is not None
        assert inv.id == "ns"
        # Should pass with no files touched
        result = inv.check(files_touched=[])
        assert result.passed is True

    def test_materialize_file_exists_pass(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        (root / "README.md").write_text("hello")
        store = InvariantStore(root)
        spec = InvariantSpec(id="fe", kind="file-exists", params={"path": "README.md"})
        store.add(spec)
        inv = store.materialize("fe")
        assert inv is not None
        result = inv.check(root=root)
        assert result.passed is True

    def test_materialize_file_exists_fail(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="fe2", kind="file-exists", params={"path": "NOPE.md"})
        store.add(spec)
        inv = store.materialize("fe2")
        assert inv is not None
        result = inv.check(root=root)
        assert result.passed is False

    def test_materialize_dir_exists_pass(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        (root / "src").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="de", kind="dir-exists", params={"path": "src"})
        store.add(spec)
        inv = store.materialize("de")
        assert inv is not None
        result = inv.check(root=root)
        assert result.passed is True

    def test_materialize_dir_exists_fail(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="de2", kind="dir-exists", params={"path": "nope_dir"})
        store.add(spec)
        inv = store.materialize("de2")
        assert inv is not None
        result = inv.check(root=root)
        assert result.passed is False

    def test_materialize_forbidden_pass(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="fb", kind="forbidden", params={"pattern": "*.secret"})
        store.add(spec)
        inv = store.materialize("fb")
        assert inv is not None
        result = inv.check(files_touched=["safe.py"])
        assert result.passed is True

    def test_materialize_forbidden_fail(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="fb2", kind="forbidden", params={"pattern": "*.secret"})
        store.add(spec)
        inv = store.materialize("fb2")
        assert inv is not None
        result = inv.check(files_touched=["data.secret"])
        assert result.passed is False

    def test_materialize_max_file_size(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="mfs", kind="max-file-size", params={"max_kb": 1})
        store.add(spec)
        inv = store.materialize("mfs")
        assert inv is not None
        # No files touched = pass
        result = inv.check(root=root, files_touched=[])
        assert result.passed is True

    def test_materialize_test_kind(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="tk", kind="test", params={"command": "echo", "args": "ok"})
        store.add(spec)
        inv = store.materialize("tk")
        assert inv is not None
        assert inv.id == "tk"
        # echo should pass
        result = inv.check()
        assert result.passed is True

    def test_materialize_nonexistent(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        assert store.materialize("missing") is None

    def test_materialize_all(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        store.add(InvariantSpec(id="a", kind="no-secrets"))
        store.add(InvariantSpec(id="b", kind="no-secrets"))
        inv_set = store.materialize_all()
        assert isinstance(inv_set, InvariantSet)
        assert len(inv_set.invariants) == 2

    def test_materialize_all_empty(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        inv_set = store.materialize_all()
        assert len(inv_set.invariants) == 0

    def test_on_violation_propagated(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="w", kind="no-secrets", on_violation="warn")
        store.add(spec)
        inv = store.materialize("w")
        assert inv is not None
        assert inv.on_violation == "warn"

    def test_enabled_propagated(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(id="d", kind="no-secrets", enabled=False)
        store.add(spec)
        inv = store.materialize("d")
        assert inv is not None
        assert inv.enabled is False
        # Disabled invariant should pass
        result = inv.check(files_touched=["password.pem"])
        assert result.passed is True

    def test_materialize_forbidden_with_description(self, tmp_path):
        root = tmp_path
        (root / ".governor").mkdir()
        store = InvariantStore(root)
        spec = InvariantSpec(
            id="fbd",
            kind="forbidden",
            params={"pattern": "*.env", "description": "No env files"},
        )
        store.add(spec)
        inv = store.materialize("fbd")
        assert inv is not None
        assert "No env files" in inv.rule

    def test_materialize_spec_directly(self):
        spec = InvariantSpec(id="direct", kind="no-secrets")
        inv = _materialize_spec(spec)
        assert inv is not None
        assert inv.id == "direct"
