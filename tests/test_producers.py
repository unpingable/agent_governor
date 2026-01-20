"""Tests for receipt producers."""

import hashlib
import tempfile
from pathlib import Path

import pytest

from governor.producers import (
    produce_file_snapshot,
    produce_cmd_run,
    produce_diff_receipt,
    _parse_diff_paths,
    _count_diff_lines,
)
from governor.receipts import FileSnapshot, CmdRun, DiffReceipt


class TestProduceFileSnapshot:
    """Test produce_file_snapshot function."""

    def test_creates_valid_snapshot(self, tmp_path):
        """Produces a valid FileSnapshot from a real file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("hello world")

        snapshot = produce_file_snapshot(test_file)

        assert isinstance(snapshot, FileSnapshot)
        assert snapshot.path == str(test_file)
        assert snapshot.size_bytes == 11
        assert snapshot.blob_hash == hashlib.sha256(b"hello world").hexdigest()
        assert snapshot.timestamp is not None

    def test_with_base_path(self, tmp_path):
        """Stores relative path when base_path is provided."""
        test_file = tmp_path / "src" / "main.py"
        test_file.parent.mkdir()
        test_file.write_text("print('hi')")

        snapshot = produce_file_snapshot("src/main.py", base_path=tmp_path)

        assert snapshot.path == "src/main.py"
        assert snapshot.size_bytes == 11

    def test_with_excerpt_spans(self, tmp_path):
        """Passes through excerpt_spans."""
        test_file = tmp_path / "code.py"
        test_file.write_text("line1\nline2\nline3\n")

        snapshot = produce_file_snapshot(
            test_file,
            excerpt_spans=[(1, 2), (3, 3)],
        )

        assert snapshot.excerpt_spans == [(1, 2), (3, 3)]

    def test_file_not_found(self, tmp_path):
        """Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            produce_file_snapshot(tmp_path / "nonexistent.txt")

    def test_directory_rejected(self, tmp_path):
        """Raises IsADirectoryError for directories."""
        with pytest.raises(IsADirectoryError):
            produce_file_snapshot(tmp_path)

    def test_binary_file(self, tmp_path):
        """Handles binary files correctly."""
        binary_file = tmp_path / "data.bin"
        binary_content = bytes(range(256))
        binary_file.write_bytes(binary_content)

        snapshot = produce_file_snapshot(binary_file)

        assert snapshot.size_bytes == 256
        assert snapshot.blob_hash == hashlib.sha256(binary_content).hexdigest()

    def test_empty_file(self, tmp_path):
        """Handles empty files."""
        empty_file = tmp_path / "empty.txt"
        empty_file.write_text("")

        snapshot = produce_file_snapshot(empty_file)

        assert snapshot.size_bytes == 0
        assert snapshot.blob_hash == hashlib.sha256(b"").hexdigest()

    def test_hash_changes_with_content(self, tmp_path):
        """Different content produces different hashes."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content A")
        file2.write_text("content B")

        snap1 = produce_file_snapshot(file1)
        snap2 = produce_file_snapshot(file2)

        assert snap1.blob_hash != snap2.blob_hash


class TestProduceCmdRun:
    """Test produce_cmd_run function."""

    def test_successful_command(self):
        """Produces receipt for successful command."""
        receipt = produce_cmd_run(["echo", "hello"])

        assert isinstance(receipt, CmdRun)
        assert receipt.command == ("echo", "hello")
        assert receipt.exit_code == 0
        assert receipt.duration_ms >= 0
        assert receipt.timestamp is not None

    def test_failing_command(self):
        """Produces receipt for failing command."""
        receipt = produce_cmd_run(["false"])

        assert receipt.exit_code != 0

    def test_captures_stdout_hash(self):
        """Hashes stdout correctly."""
        receipt = produce_cmd_run(["echo", "test output"])

        expected_hash = hashlib.sha256(b"test output\n").hexdigest()
        assert receipt.stdout_hash == expected_hash

    def test_captures_stderr_hash(self):
        """Hashes stderr correctly."""
        # Use sh -c to write to stderr
        receipt = produce_cmd_run(["sh", "-c", "echo error >&2"])

        expected_hash = hashlib.sha256(b"error\n").hexdigest()
        assert receipt.stderr_hash == expected_hash

    def test_cwd_is_recorded(self, tmp_path):
        """Records the working directory."""
        receipt = produce_cmd_run(["pwd"], cwd=tmp_path)

        assert receipt.cwd == str(tmp_path.resolve())

    def test_cwd_defaults_to_current(self):
        """Uses current directory if cwd not specified."""
        receipt = produce_cmd_run(["pwd"])

        assert receipt.cwd == str(Path.cwd().resolve())

    def test_command_not_found(self):
        """Raises FileNotFoundError for missing command."""
        with pytest.raises(FileNotFoundError):
            produce_cmd_run(["nonexistent_command_xyz"])

    def test_timeout(self):
        """Raises TimeoutExpired for slow command."""
        with pytest.raises(Exception):  # subprocess.TimeoutExpired
            produce_cmd_run(["sleep", "10"], timeout=1)

    def test_tuple_command_accepted(self):
        """Accepts tuple for command."""
        receipt = produce_cmd_run(("echo", "tuple"))

        assert receipt.command == ("echo", "tuple")


class TestProduceDiffReceipt:
    """Test produce_diff_receipt function."""

    SIMPLE_DIFF = """\
diff --git a/file.txt b/file.txt
index 1234567..abcdefg 100644
--- a/file.txt
+++ b/file.txt
@@ -1,3 +1,4 @@
 line1
+added line
 line2
-removed line
 line3
"""

    def test_creates_valid_receipt(self):
        """Produces a valid DiffReceipt."""
        receipt = produce_diff_receipt(self.SIMPLE_DIFF)

        assert isinstance(receipt, DiffReceipt)
        assert receipt.timestamp is not None
        assert receipt.unified_diff_hash == hashlib.sha256(
            self.SIMPLE_DIFF.encode()
        ).hexdigest()

    def test_extracts_paths(self):
        """Extracts touched file paths."""
        receipt = produce_diff_receipt(self.SIMPLE_DIFF)

        assert "file.txt" in receipt.paths_touched

    def test_counts_additions(self):
        """Counts added lines."""
        receipt = produce_diff_receipt(self.SIMPLE_DIFF)

        assert receipt.additions == 1

    def test_counts_deletions(self):
        """Counts deleted lines."""
        receipt = produce_diff_receipt(self.SIMPLE_DIFF)

        assert receipt.deletions == 1

    def test_multiple_files(self):
        """Handles diffs with multiple files."""
        multi_diff = """\
diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1 +1,2 @@
 existing
+new in a
diff --git a/b.py b/b.py
--- a/b.py
+++ b/b.py
@@ -1 +1,2 @@
 existing
+new in b
"""
        receipt = produce_diff_receipt(multi_diff)

        assert set(receipt.paths_touched) == {"a.py", "b.py"}
        assert receipt.additions == 2

    def test_new_file(self):
        """Handles new file creation."""
        new_file_diff = """\
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+line1
+line2
+line3
"""
        receipt = produce_diff_receipt(new_file_diff)

        assert "new.py" in receipt.paths_touched
        assert receipt.additions == 3
        assert receipt.deletions == 0

    def test_deleted_file(self):
        """Handles file deletion."""
        delete_diff = """\
diff --git a/old.py b/old.py
deleted file mode 100644
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-line1
-line2
"""
        receipt = produce_diff_receipt(delete_diff)

        # Deleted files show /dev/null in +++, so path comes from ---
        # Our implementation tracks +++ paths, so deleted files won't appear
        # This is acceptable - we're tracking what will exist after the patch
        assert receipt.deletions == 2

    def test_empty_diff(self):
        """Handles empty diff."""
        receipt = produce_diff_receipt("")

        assert receipt.paths_touched == ()
        assert receipt.additions == 0
        assert receipt.deletions == 0

    def test_base_tree_hash_without_git(self, tmp_path):
        """Returns empty tree hash when not in git repo."""
        receipt = produce_diff_receipt(self.SIMPLE_DIFF, repo_root=tmp_path)

        assert receipt.base_tree_hash == ""


class TestParseDiffPaths:
    """Test _parse_diff_paths helper."""

    def test_git_format(self):
        """Parses git diff format with a/ b/ prefixes."""
        diff = "+++ b/src/main.py"
        assert _parse_diff_paths(diff) == ["src/main.py"]

    def test_plain_format(self):
        """Parses plain diff format without prefixes."""
        diff = "+++ src/main.py"
        assert _parse_diff_paths(diff) == ["src/main.py"]

    def test_skips_dev_null(self):
        """Skips /dev/null entries."""
        diff = "+++ /dev/null"
        assert _parse_diff_paths(diff) == []


class TestCountDiffLines:
    """Test _count_diff_lines helper."""

    def test_counts_correctly(self):
        """Counts additions and deletions in hunk."""
        diff = """\
@@ -1,3 +1,4 @@
 context
+added
-removed
+also added
"""
        adds, dels = _count_diff_lines(diff)
        assert adds == 2
        assert dels == 1

    def test_ignores_header_lines(self):
        """Doesn't count +++ and --- as changes."""
        diff = """\
--- a/file.txt
+++ b/file.txt
@@ -1 +1 @@
-old
+new
"""
        adds, dels = _count_diff_lines(diff)
        assert adds == 1
        assert dels == 1

    def test_empty_diff(self):
        """Returns zeros for empty diff."""
        adds, dels = _count_diff_lines("")
        assert adds == 0
        assert dels == 0
