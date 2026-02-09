"""Tests for GovernorContextManager and GovernorContext."""

import json
import pytest
from pathlib import Path

from governor.context_manager import (
    GovernorContext,
    GovernorContextManager,
    VALID_MODES,
    CONTEXT_META_FILE,
    GOVERNOR_DIR,
    FICTION_GOV_DIR,
    PROPOSALS_FILE,
    _validate_context_id,
)


# ============================================================================
# TestGovernorContext
# ============================================================================


class TestGovernorContext:
    """Tests for GovernorContext dataclass."""

    def test_creation(self, tmp_path: Path) -> None:
        ctx = GovernorContext(
            context_id="test-ctx",
            mode="general",
            root=tmp_path / "test-ctx",
            governor_dir=tmp_path / "test-ctx" / ".governor",
            created_at="2025-01-01T00:00:00+00:00",
        )
        assert ctx.context_id == "test-ctx"
        assert ctx.mode == "general"
        assert ctx.metadata == {}

    def test_to_dict(self, tmp_path: Path) -> None:
        ctx = GovernorContext(
            context_id="test-ctx",
            mode="fiction",
            root=tmp_path / "test-ctx",
            governor_dir=tmp_path / "test-ctx" / ".governor",
            created_at="2025-01-01T00:00:00+00:00",
            metadata={"author": "erin"},
        )
        d = ctx.to_dict()
        assert d["context_id"] == "test-ctx"
        assert d["mode"] == "fiction"
        assert d["metadata"]["author"] == "erin"
        assert "root" in d
        assert "governor_dir" in d

    def test_from_dict(self, tmp_path: Path) -> None:
        data = {
            "context_id": "test-ctx",
            "mode": "code",
            "root": str(tmp_path / "test-ctx"),
            "governor_dir": str(tmp_path / "test-ctx" / ".governor"),
            "created_at": "2025-01-01T00:00:00+00:00",
            "metadata": {"project": "agent-gov"},
        }
        ctx = GovernorContext.from_dict(data)
        assert ctx.context_id == "test-ctx"
        assert ctx.mode == "code"
        assert ctx.root == tmp_path / "test-ctx"
        assert ctx.metadata["project"] == "agent-gov"

    def test_roundtrip(self, tmp_path: Path) -> None:
        original = GovernorContext(
            context_id="round-trip",
            mode="nonfiction",
            root=tmp_path / "round-trip",
            governor_dir=tmp_path / "round-trip" / ".governor",
            created_at="2025-06-15T12:00:00+00:00",
            metadata={"key": "value"},
        )
        restored = GovernorContext.from_dict(original.to_dict())
        assert restored.context_id == original.context_id
        assert restored.mode == original.mode
        assert restored.root == original.root
        assert restored.governor_dir == original.governor_dir
        assert restored.created_at == original.created_at
        assert restored.metadata == original.metadata

    def test_defaults(self, tmp_path: Path) -> None:
        ctx = GovernorContext(
            context_id="minimal",
            mode="general",
            root=tmp_path,
            governor_dir=tmp_path / ".governor",
            created_at="",
        )
        assert ctx.metadata == {}
        assert ctx.created_at == ""

    def test_from_dict_defaults(self) -> None:
        """from_dict handles missing optional fields."""
        data = {
            "context_id": "minimal",
            "root": "/tmp/minimal",
            "governor_dir": "/tmp/minimal/.governor",
        }
        ctx = GovernorContext.from_dict(data)
        assert ctx.mode == "general"
        assert ctx.created_at == ""
        assert ctx.metadata == {}


# ============================================================================
# TestValidation
# ============================================================================


class TestValidation:
    """Tests for context ID validation."""

    def test_valid_ids(self) -> None:
        for cid in ["test", "my-project", "erin_novel_1", "a.b.c", "A123"]:
            _validate_context_id(cid)  # should not raise

    def test_empty_id(self) -> None:
        with pytest.raises(ValueError, match="cannot be empty"):
            _validate_context_id("")

    def test_invalid_start_char(self) -> None:
        with pytest.raises(ValueError, match="Invalid context ID"):
            _validate_context_id("-starts-with-dash")

    def test_invalid_characters(self) -> None:
        with pytest.raises(ValueError, match="Invalid context ID"):
            _validate_context_id("has spaces")

    def test_too_long(self) -> None:
        with pytest.raises(ValueError, match="too long"):
            _validate_context_id("a" * 129)


# ============================================================================
# TestGovernorContextManager
# ============================================================================


class TestGovernorContextManager:
    """Tests for GovernorContextManager."""

    def test_create(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("test-project")
        assert ctx.context_id == "test-project"
        assert ctx.mode == "general"
        assert ctx.root.exists()
        assert ctx.governor_dir.exists()

    def test_create_with_mode(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("fiction-ctx", mode="fiction")
        assert ctx.mode == "fiction"

    def test_create_invalid_mode(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        with pytest.raises(ValueError, match="Invalid mode"):
            mgr.create("bad-mode", mode="invalid")

    def test_create_duplicate_raises(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        mgr.create("dup")
        with pytest.raises(ValueError, match="already exists"):
            mgr.create("dup")

    def test_get(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        mgr.create("my-ctx", metadata={"key": "val"})
        ctx = mgr.get("my-ctx")
        assert ctx is not None
        assert ctx.context_id == "my-ctx"
        assert ctx.metadata["key"] == "val"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        assert mgr.get("no-such-ctx") is None

    def test_get_or_create_existing(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx1 = mgr.create("existing", mode="fiction")
        ctx2 = mgr.get_or_create("existing", mode="code")  # mode ignored for existing
        assert ctx2.mode == "fiction"
        assert ctx2.context_id == ctx1.context_id

    def test_get_or_create_new(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.get_or_create("new-ctx", mode="code")
        assert ctx.context_id == "new-ctx"
        assert ctx.mode == "code"

    def test_get_or_create_repairs_missing_metadata(self, tmp_path: Path) -> None:
        """If directory exists but metadata is missing, get_or_create repairs it."""
        mgr = GovernorContextManager(base_dir=tmp_path)
        # Simulate: directory exists (e.g., from session store) but no _context.json
        ctx_dir = tmp_path / "orphan-ctx"
        ctx_dir.mkdir(parents=True)
        assert not (ctx_dir / CONTEXT_META_FILE).exists()

        # get_or_create should repair instead of crashing
        ctx = mgr.get_or_create("orphan-ctx", mode="fiction")
        assert ctx.context_id == "orphan-ctx"
        assert ctx.mode == "fiction"
        assert (ctx_dir / CONTEXT_META_FILE).exists()
        assert (ctx.governor_dir).exists()

    def test_get_or_create_repair_is_idempotent(self, tmp_path: Path) -> None:
        """Calling get_or_create twice on a repaired context works."""
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx_dir = tmp_path / "repair-twice"
        ctx_dir.mkdir(parents=True)

        ctx1 = mgr.get_or_create("repair-twice", mode="code")
        ctx2 = mgr.get_or_create("repair-twice", mode="fiction")  # mode ignored
        assert ctx2.mode == "code"  # first call's mode sticks
        assert ctx1.context_id == ctx2.context_id

    def test_list_contexts(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        mgr.create("alpha")
        mgr.create("beta")
        mgr.create("gamma")
        contexts = mgr.list_contexts()
        ids = [c.context_id for c in contexts]
        assert "alpha" in ids
        assert "beta" in ids
        assert "gamma" in ids
        assert len(contexts) == 3

    def test_list_empty(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        assert mgr.list_contexts() == []

    def test_delete(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        mgr.create("to-delete")
        assert mgr.get("to-delete") is not None
        result = mgr.delete("to-delete")
        assert result is True
        assert mgr.get("to-delete") is None

    def test_delete_nonexistent(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        assert mgr.delete("no-such") is False

    def test_fiction_mode_creates_fiction_gov(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("fiction-project", mode="fiction")
        fiction_dir = ctx.root / FICTION_GOV_DIR
        assert fiction_dir.exists()

    def test_code_mode_skips_fiction_gov(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("code-project", mode="code")
        fiction_dir = ctx.root / FICTION_GOV_DIR
        assert not fiction_dir.exists()

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        """New manager instance reads existing contexts from disk."""
        mgr1 = GovernorContextManager(base_dir=tmp_path)
        mgr1.create("persisted", mode="fiction", metadata={"author": "erin"})

        mgr2 = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr2.get("persisted")
        assert ctx is not None
        assert ctx.mode == "fiction"
        assert ctx.metadata["author"] == "erin"

    def test_context_isolation(self, tmp_path: Path) -> None:
        """Two contexts don't share state."""
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx1 = mgr.create("ctx-a", mode="fiction")
        ctx2 = mgr.create("ctx-b", mode="code")
        assert ctx1.root != ctx2.root
        assert ctx1.governor_dir != ctx2.governor_dir

    def test_meta_file_format(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("meta-test")
        meta_path = ctx.root / CONTEXT_META_FILE
        assert meta_path.exists()
        data = json.loads(meta_path.read_text())
        assert data["context_id"] == "meta-test"
        assert "created_at" in data


# ============================================================================
# TestEnsureGovernorInit
# ============================================================================


class TestEnsureGovernorInit:
    """Tests for _ensure_governor_init directory structure."""

    def test_creates_governor_dir(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("init-test")
        assert ctx.governor_dir.exists()

    def test_creates_facts_dir(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("init-test")
        assert (ctx.governor_dir / "facts").is_dir()
        assert (ctx.governor_dir / "facts" / "receipts").is_dir()

    def test_creates_decisions_dir(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("init-test")
        assert (ctx.governor_dir / "decisions").is_dir()

    def test_creates_proposals_file(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("init-test")
        proposals = ctx.governor_dir / PROPOSALS_FILE
        assert proposals.exists()
        assert json.loads(proposals.read_text()) == {}

    def test_creates_index_files(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("init-test")
        facts_idx = ctx.governor_dir / "facts" / "index.json"
        dec_idx = ctx.governor_dir / "decisions" / "index.json"
        assert json.loads(facts_idx.read_text()) == []
        assert json.loads(dec_idx.read_text()) == []

    def test_fiction_mode_creates_fiction_gov(self, tmp_path: Path) -> None:
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("fiction-init", mode="fiction")
        assert (ctx.root / FICTION_GOV_DIR).is_dir()

    def test_idempotent(self, tmp_path: Path) -> None:
        """Running init twice doesn't break anything."""
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("idempotent-test")
        # Manually call again
        mgr._ensure_governor_init(ctx)
        assert ctx.governor_dir.exists()
        assert json.loads(
            (ctx.governor_dir / "facts" / "index.json").read_text()
        ) == []

    def test_doesnt_clobber_existing_data(self, tmp_path: Path) -> None:
        """Init doesn't overwrite existing data."""
        mgr = GovernorContextManager(base_dir=tmp_path)
        ctx = mgr.create("clobber-test")
        # Write something to facts index
        facts_idx = ctx.governor_dir / "facts" / "index.json"
        facts_idx.write_text('[{"id": "test-fact"}]')
        # Re-init should not clobber
        mgr._ensure_governor_init(ctx)
        data = json.loads(facts_idx.read_text())
        assert data == [{"id": "test-fact"}]
