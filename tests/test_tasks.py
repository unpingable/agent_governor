# SPDX-License-Identifier: Apache-2.0
"""Tests for task management system."""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from governor.storage import Storage
from governor.tasks import (
    Task,
    TaskStatus,
    Priority,
    Label,
    Milestone,
    TimeEntry,
    Session,
    TaskManager,
)


@pytest.fixture
def storage():
    """Create a temporary storage for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        yield Storage(db_path)


@pytest.fixture
def task_manager(storage):
    """Create a task manager for testing."""
    return TaskManager(storage)


class TestTaskBasics:
    """Test basic task CRUD operations."""

    def test_create_task(self, task_manager):
        """Can create a task."""
        task = task_manager.create_task(
            title="Test task",
            description="A test task",
            priority=Priority.HIGH,
        )

        assert task.id is not None
        assert task.title == "Test task"
        assert task.description == "A test task"
        assert task.priority == Priority.HIGH
        assert task.status == TaskStatus.OPEN

    def test_get_task(self, task_manager):
        """Can retrieve a task by ID."""
        task = task_manager.create_task("Test task")
        retrieved = task_manager.get_task(task.id)

        assert retrieved is not None
        assert retrieved.id == task.id
        assert retrieved.title == task.title

    def test_update_task(self, task_manager):
        """Can update task fields."""
        task = task_manager.create_task("Original title")
        task.title = "Updated title"
        task.priority = Priority.CRITICAL

        task_manager.update_task(task)

        retrieved = task_manager.get_task(task.id)
        assert retrieved.title == "Updated title"
        assert retrieved.priority == Priority.CRITICAL

    def test_delete_task(self, task_manager):
        """Can delete a task."""
        task = task_manager.create_task("To delete")
        task_manager.delete_task(task.id)

        retrieved = task_manager.get_task(task.id)
        assert retrieved is None

    def test_list_tasks(self, task_manager):
        """Can list all tasks."""
        task_manager.create_task("Task 1")
        task_manager.create_task("Task 2")
        task_manager.create_task("Task 3")

        tasks = task_manager.list_tasks()
        assert len(tasks) == 3

    def test_list_tasks_by_status(self, task_manager):
        """Can filter tasks by status."""
        t1 = task_manager.create_task("Open task")
        t2 = task_manager.create_task("Done task")
        task_manager.complete_task(t2.id)

        open_tasks = task_manager.list_tasks(status=TaskStatus.OPEN)
        done_tasks = task_manager.list_tasks(status=TaskStatus.DONE)

        assert len(open_tasks) == 1
        assert len(done_tasks) == 1
        assert open_tasks[0].id == t1.id
        assert done_tasks[0].id == t2.id


class TestTaskStatusChanges:
    """Test task status transitions."""

    def test_start_task(self, task_manager):
        """Starting a task changes status to in_progress."""
        task = task_manager.create_task("Task")
        task_manager.start_task(task.id)

        task = task_manager.get_task(task.id)
        assert task.status == TaskStatus.IN_PROGRESS

    def test_complete_task(self, task_manager):
        """Completing a task changes status to done."""
        task = task_manager.create_task("Task")
        task_manager.complete_task(task.id)

        task = task_manager.get_task(task.id)
        assert task.status == TaskStatus.DONE
        assert task.closed_at is not None

    def test_archive_task(self, task_manager):
        """Can archive a completed task."""
        task = task_manager.create_task("Task")
        task_manager.complete_task(task.id)
        task_manager.archive_task(task.id)

        task = task_manager.get_task(task.id)
        assert task.status == TaskStatus.ARCHIVED
        assert task.archived_at is not None

    def test_reopen_task(self, task_manager):
        """Can reopen a closed task."""
        task = task_manager.create_task("Task")
        task_manager.complete_task(task.id)
        task_manager.reopen_task(task.id)

        task = task_manager.get_task(task.id)
        assert task.status == TaskStatus.OPEN
        assert task.closed_at is None


class TestSubtasks:
    """Test subtask functionality."""

    def test_create_subtask(self, task_manager):
        """Can create a subtask."""
        parent = task_manager.create_task("Parent task")
        child = task_manager.create_task("Subtask", parent_id=parent.id)

        assert child.parent_id == parent.id
        assert child.is_subtask

    def test_get_subtasks(self, task_manager):
        """Can retrieve subtasks of a parent."""
        parent = task_manager.create_task("Parent")
        child1 = task_manager.create_task("Child 1", parent_id=parent.id)
        child2 = task_manager.create_task("Child 2", parent_id=parent.id)
        task_manager.create_task("Unrelated")

        subtasks = task_manager.get_subtasks(parent.id)
        assert len(subtasks) == 2
        assert {s.id for s in subtasks} == {child1.id, child2.id}


class TestDependencies:
    """Test blocking dependency functionality."""

    def test_add_dependency(self, task_manager):
        """Can add a blocking dependency."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")

        success = task_manager.add_dependency(task2.id, task1.id)
        assert success

        task2 = task_manager.get_task(task2.id)
        assert task1.id in task2.depends_on

    def test_remove_dependency(self, task_manager):
        """Can remove a blocking dependency."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")

        task_manager.add_dependency(task2.id, task1.id)
        task_manager.remove_dependency(task2.id, task1.id)

        task2 = task_manager.get_task(task2.id)
        assert task1.id not in task2.depends_on

    def test_blocked_task_status(self, task_manager):
        """Starting a blocked task sets status to blocked."""
        task1 = task_manager.create_task("Blocker")
        task2 = task_manager.create_task("Blocked")

        task_manager.add_dependency(task2.id, task1.id)
        task_manager.start_task(task2.id)

        task2 = task_manager.get_task(task2.id)
        assert task2.status == TaskStatus.BLOCKED

    def test_completing_unblocks_dependent(self, task_manager):
        """Completing a blocker unblocks dependent tasks."""
        task1 = task_manager.create_task("Blocker")
        task2 = task_manager.create_task("Blocked")

        task_manager.add_dependency(task2.id, task1.id)
        task_manager.start_task(task2.id)
        assert task_manager.get_task(task2.id).status == TaskStatus.BLOCKED

        task_manager.complete_task(task1.id)
        task2 = task_manager.get_task(task2.id)
        assert task2.status == TaskStatus.OPEN

    def test_prevent_circular_dependency(self, task_manager):
        """Cannot create circular dependencies."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")
        task3 = task_manager.create_task("Task 3")

        task_manager.add_dependency(task2.id, task1.id)  # task2 depends on task1
        task_manager.add_dependency(task3.id, task2.id)  # task3 depends on task2

        # Try to make task1 depend on task3 (would create cycle)
        success = task_manager.add_dependency(task1.id, task3.id)
        assert not success

    def test_get_blocking_tasks(self, task_manager):
        """Can get list of blocking tasks."""
        blocker1 = task_manager.create_task("Blocker 1")
        blocker2 = task_manager.create_task("Blocker 2")
        blocked = task_manager.create_task("Blocked")

        task_manager.add_dependency(blocked.id, blocker1.id)
        task_manager.add_dependency(blocked.id, blocker2.id)

        blocking = task_manager.get_blocking_tasks(blocked.id)
        assert len(blocking) == 2
        assert {b.id for b in blocking} == {blocker1.id, blocker2.id}

    def test_get_dependent_tasks(self, task_manager):
        """Can get tasks that depend on this one."""
        blocker = task_manager.create_task("Blocker")
        dependent1 = task_manager.create_task("Dependent 1")
        dependent2 = task_manager.create_task("Dependent 2")

        task_manager.add_dependency(dependent1.id, blocker.id)
        task_manager.add_dependency(dependent2.id, blocker.id)

        dependents = task_manager.get_dependent_tasks(blocker.id)
        assert len(dependents) == 2


class TestRelatedTasks:
    """Test related task linking."""

    def test_link_tasks(self, task_manager):
        """Can link two tasks as related."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")

        success = task_manager.link_tasks(task1.id, task2.id)
        assert success

        # Check bidirectional link
        task1 = task_manager.get_task(task1.id)
        task2 = task_manager.get_task(task2.id)
        assert task2.id in task1.related_to
        assert task1.id in task2.related_to

    def test_unlink_tasks(self, task_manager):
        """Can remove a related task link."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")

        task_manager.link_tasks(task1.id, task2.id)
        task_manager.unlink_tasks(task1.id, task2.id)

        task1 = task_manager.get_task(task1.id)
        task2 = task_manager.get_task(task2.id)
        assert task2.id not in task1.related_to
        assert task1.id not in task2.related_to

    def test_get_related_tasks(self, task_manager):
        """Can get all related tasks."""
        task1 = task_manager.create_task("Task 1")
        task2 = task_manager.create_task("Task 2")
        task3 = task_manager.create_task("Task 3")

        task_manager.link_tasks(task1.id, task2.id)
        task_manager.link_tasks(task1.id, task3.id)

        related = task_manager.get_related_tasks(task1.id)
        assert len(related) == 2
        assert {r.id for r in related} == {task2.id, task3.id}


class TestLabels:
    """Test label functionality."""

    def test_create_label(self, task_manager):
        """Can create a label."""
        label = task_manager.create_label("bug", "#ff0000", "Bug label")

        assert label.id is not None
        assert label.name == "bug"
        assert label.color == "#ff0000"

    def test_get_label(self, task_manager):
        """Can retrieve a label by ID."""
        label = task_manager.create_label("feature")
        retrieved = task_manager.get_label(label.id)

        assert retrieved is not None
        assert retrieved.name == "feature"

    def test_get_label_by_name(self, task_manager):
        """Can retrieve a label by name."""
        task_manager.create_label("urgent")
        retrieved = task_manager.get_label_by_name("urgent")

        assert retrieved is not None
        assert retrieved.name == "urgent"

    def test_list_labels(self, task_manager):
        """Can list all labels."""
        task_manager.create_label("label1")
        task_manager.create_label("label2")

        labels = task_manager.list_labels()
        assert len(labels) == 2

    def test_add_label_to_task(self, task_manager):
        """Can add a label to a task."""
        task = task_manager.create_task("Task")
        label = task_manager.create_label("important")

        task_manager.add_label_to_task(task.id, label.id)

        task = task_manager.get_task(task.id)
        assert label.id in task.label_ids

    def test_remove_label_from_task(self, task_manager):
        """Can remove a label from a task."""
        task = task_manager.create_task("Task")
        label = task_manager.create_label("temp")

        task_manager.add_label_to_task(task.id, label.id)
        task_manager.remove_label_from_task(task.id, label.id)

        task = task_manager.get_task(task.id)
        assert label.id not in task.label_ids

    def test_filter_tasks_by_label(self, task_manager):
        """Can filter tasks by label."""
        label = task_manager.create_label("bug")
        task1 = task_manager.create_task("Bug task", label_ids=[label.id])
        task2 = task_manager.create_task("Other task")

        tasks = task_manager.list_tasks(label_id=label.id)
        assert len(tasks) == 1
        assert tasks[0].id == task1.id


class TestMilestones:
    """Test milestone functionality."""

    def test_create_milestone(self, task_manager):
        """Can create a milestone."""
        due = datetime.now(timezone.utc) + timedelta(days=30)
        milestone = task_manager.create_milestone("v1.0", "First release", due)

        assert milestone.id is not None
        assert milestone.name == "v1.0"
        assert milestone.due_date is not None

    def test_get_milestone(self, task_manager):
        """Can retrieve a milestone by ID."""
        milestone = task_manager.create_milestone("v2.0")
        retrieved = task_manager.get_milestone(milestone.id)

        assert retrieved is not None
        assert retrieved.name == "v2.0"

    def test_list_milestones(self, task_manager):
        """Can list milestones."""
        task_manager.create_milestone("m1")
        task_manager.create_milestone("m2")

        milestones = task_manager.list_milestones()
        assert len(milestones) == 2

    def test_close_milestone(self, task_manager):
        """Can close a milestone."""
        milestone = task_manager.create_milestone("release")
        task_manager.close_milestone(milestone.id)

        milestone = task_manager.get_milestone(milestone.id)
        assert milestone.is_closed
        assert milestone.closed_at is not None

    def test_milestone_progress(self, task_manager):
        """Can get milestone progress."""
        milestone = task_manager.create_milestone("sprint")

        task1 = task_manager.create_task("Task 1", milestone_id=milestone.id)
        task2 = task_manager.create_task("Task 2", milestone_id=milestone.id)
        task3 = task_manager.create_task("Task 3", milestone_id=milestone.id)

        task_manager.complete_task(task1.id)

        progress = task_manager.get_milestone_progress(milestone.id)
        assert progress["total"] == 3
        assert progress["done"] == 1
        assert progress["percent_complete"] == 33

    def test_filter_tasks_by_milestone(self, task_manager):
        """Can filter tasks by milestone."""
        m1 = task_manager.create_milestone("M1")
        m2 = task_manager.create_milestone("M2")

        task_manager.create_task("T1", milestone_id=m1.id)
        task_manager.create_task("T2", milestone_id=m1.id)
        task_manager.create_task("T3", milestone_id=m2.id)

        tasks = task_manager.list_tasks(milestone_id=m1.id)
        assert len(tasks) == 2


class TestTimeTracking:
    """Test time tracking functionality."""

    def test_start_timer(self, task_manager):
        """Can start a timer for a task."""
        task = task_manager.create_task("Task")
        entry = task_manager.start_timer(task.id, "Working on it")

        assert entry.id is not None
        assert entry.task_id == task.id
        assert entry.is_running
        assert entry.note == "Working on it"

    def test_stop_timer(self, task_manager):
        """Can stop a running timer."""
        task = task_manager.create_task("Task")
        task_manager.start_timer(task.id)

        entry = task_manager.stop_timer(task.id)
        assert entry is not None
        assert not entry.is_running
        assert entry.stopped_at is not None

    def test_get_running_timer(self, task_manager):
        """Can get the running timer for a task."""
        task = task_manager.create_task("Task")
        task_manager.start_timer(task.id)

        running = task_manager.get_running_timer(task.id)
        assert running is not None
        assert running.is_running

    def test_no_running_timer_after_stop(self, task_manager):
        """No running timer after stop."""
        task = task_manager.create_task("Task")
        task_manager.start_timer(task.id)
        task_manager.stop_timer(task.id)

        running = task_manager.get_running_timer(task.id)
        assert running is None

    def test_get_time_entries(self, task_manager):
        """Can get all time entries for a task."""
        task = task_manager.create_task("Task")

        task_manager.start_timer(task.id)
        task_manager.stop_timer(task.id)
        task_manager.start_timer(task.id)
        task_manager.stop_timer(task.id)

        entries = task_manager.get_time_entries(task.id)
        assert len(entries) == 2

    def test_get_total_time(self, task_manager):
        """Can get total time spent on a task."""
        task = task_manager.create_task("Task")

        entry = task_manager.start_timer(task.id)
        task_manager.stop_timer(task.id)

        total = task_manager.get_total_time(task.id)
        assert total.total_seconds() >= 0


class TestSessions:
    """Test session management."""

    def test_start_session(self, task_manager):
        """Can start a new session."""
        session = task_manager.start_session("agent-1")

        assert session.id is not None
        assert session.agent_id == "agent-1"
        assert session.is_active

    def test_get_active_session(self, task_manager):
        """Can get the active session."""
        task_manager.start_session("agent-1")

        active = task_manager.get_active_session("agent-1")
        assert active is not None
        assert active.is_active

    def test_end_session(self, task_manager):
        """Can end a session with handoff notes."""
        session = task_manager.start_session()
        task_manager.end_session(
            session.id,
            summary="Did some work",
            next_steps=["Continue feature", "Write tests"],
            blockers=["Waiting on API"],
            notes="See PR #123",
        )

        session = task_manager.get_session(session.id)
        assert not session.is_active
        assert session.summary == "Did some work"
        assert len(session.next_steps) == 2
        assert len(session.blockers) == 1

    def test_get_last_session(self, task_manager):
        """Can get the most recent completed session."""
        s1 = task_manager.start_session()
        task_manager.end_session(s1.id, summary="First session")

        s2 = task_manager.start_session()
        task_manager.end_session(s2.id, summary="Second session")

        last = task_manager.get_last_session()
        assert last is not None
        assert last.summary == "Second session"

    def test_list_sessions(self, task_manager):
        """Can list recent sessions."""
        task_manager.start_session()
        task_manager.start_session()

        sessions = task_manager.list_sessions()
        assert len(sessions) == 2

    def test_format_handoff(self, task_manager):
        """Can format handoff notes."""
        session = task_manager.start_session()
        task_manager.end_session(
            session.id,
            summary="Implemented login",
            next_steps=["Add tests"],
        )

        handoff = task_manager.format_handoff()
        assert "Previous Session Handoff" in handoff
        assert "Implemented login" in handoff
        assert "Add tests" in handoff


class TestRecommendations:
    """Test recommendation engine."""

    def test_recommend_next_prioritizes_high_priority(self, task_manager):
        """Higher priority tasks are recommended first."""
        task_manager.create_task("Low priority", priority=Priority.LOW)
        high = task_manager.create_task("High priority", priority=Priority.HIGH)

        recommendations = task_manager.recommend_next()
        assert len(recommendations) > 0
        assert recommendations[0].id == high.id

    def test_recommend_next_considers_in_progress(self, task_manager):
        """In-progress tasks get a bonus."""
        task1 = task_manager.create_task("Not started")
        task2 = task_manager.create_task("In progress")
        task_manager.start_task(task2.id)

        recommendations = task_manager.recommend_next()
        # In-progress should be first due to momentum bonus
        assert recommendations[0].id == task2.id

    def test_recommend_next_excludes_blocked(self, task_manager):
        """Blocked tasks are not recommended."""
        blocker = task_manager.create_task("Blocker")
        blocked = task_manager.create_task("Blocked", priority=Priority.CRITICAL)
        task_manager.add_dependency(blocked.id, blocker.id)
        task_manager.start_task(blocked.id)

        recommendations = task_manager.recommend_next()
        blocked_ids = {t.id for t in recommendations}
        assert blocked.id not in blocked_ids

    def test_recommend_next_empty_when_all_done(self, task_manager):
        """No recommendations when all tasks are done."""
        task = task_manager.create_task("Only task")
        task_manager.complete_task(task.id)

        recommendations = task_manager.recommend_next()
        assert len(recommendations) == 0


class TestTreeView:
    """Test tree visualization."""

    def test_format_tree_basic(self, task_manager):
        """Can format basic tree."""
        task_manager.create_task("Task 1")
        task_manager.create_task("Task 2")

        tree = task_manager.format_tree()
        assert "Task 1" in tree
        assert "Task 2" in tree

    def test_format_tree_with_hierarchy(self, task_manager):
        """Tree shows parent-child relationships."""
        parent = task_manager.create_task("Parent")
        task_manager.create_task("Child", parent_id=parent.id)

        tree = task_manager.format_tree()
        assert "Parent" in tree
        assert "Child" in tree
        # Child should be indented under parent
        lines = tree.split("\n")
        parent_line = next(l for l in lines if "Parent" in l)
        child_line = next(l for l in lines if "Child" in l)
        assert len(child_line) > len(parent_line) - 10  # Rough check for indentation

    def test_format_tree_shows_status(self, task_manager):
        """Tree shows task status icons."""
        task = task_manager.create_task("Done task")
        task_manager.complete_task(task.id)

        tree = task_manager.format_tree()
        # Should have checkmark for done task
        assert "Done task" in tree


class TestExportImport:
    """Test export and import functionality."""

    def test_export_json(self, task_manager):
        """Can export all data to JSON."""
        task_manager.create_task("Task")
        task_manager.create_label("label")
        task_manager.create_milestone("milestone")

        data = task_manager.export_json()

        assert "version" in data
        assert "tasks" in data
        assert "labels" in data
        assert "milestones" in data
        assert len(data["tasks"]) == 1
        assert len(data["labels"]) == 1
        assert len(data["milestones"]) == 1

    def test_import_json_merge(self, task_manager):
        """Can import and merge data."""
        existing = task_manager.create_task("Existing")

        data = {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [
                Task(title="Imported").to_dict(),
            ],
            "labels": [],
            "milestones": [],
            "sessions": [],
        }

        counts = task_manager.import_json(data, merge=True)

        assert counts["tasks"] == 1
        all_tasks = task_manager.list_tasks()
        assert len(all_tasks) == 2

    def test_import_json_replace(self, task_manager):
        """Can import and replace data."""
        task_manager.create_task("To replace")

        data = {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [
                Task(title="Imported").to_dict(),
            ],
            "labels": [],
            "milestones": [],
            "sessions": [],
        }

        counts = task_manager.import_json(data, merge=False)

        assert counts["tasks"] == 1
        all_tasks = task_manager.list_tasks()
        assert len(all_tasks) == 1
        assert all_tasks[0].title == "Imported"


class TestArchiving:
    """Test task archiving."""

    def test_archive_done_tasks(self, task_manager):
        """Can archive old completed tasks."""
        # Create a task and backdate its completion
        task = task_manager.create_task("Old task")
        task_manager.complete_task(task.id)

        # Manually backdate the closed_at
        task = task_manager.get_task(task.id)
        task.closed_at = datetime.now(timezone.utc) - timedelta(days=60)
        task_manager.update_task(task)

        count = task_manager.archive_done_tasks(older_than_days=30)
        assert count == 1

        task = task_manager.get_task(task.id)
        assert task.is_archived

    def test_archive_excludes_recent(self, task_manager):
        """Recent completed tasks are not archived."""
        task = task_manager.create_task("Recent task")
        task_manager.complete_task(task.id)

        count = task_manager.archive_done_tasks(older_than_days=30)
        assert count == 0

        task = task_manager.get_task(task.id)
        assert not task.is_archived


class TestDataclassSerialization:
    """Test dataclass to_dict/from_dict methods."""

    def test_task_serialization(self):
        """Task can be serialized and deserialized."""
        task = Task(
            title="Test",
            description="Description",
            priority=Priority.HIGH,
        )

        data = task.to_dict()
        restored = Task.from_dict(data)

        assert restored.title == task.title
        assert restored.priority == task.priority

    def test_label_serialization(self):
        """Label can be serialized and deserialized."""
        label = Label(name="bug", color="#ff0000")

        data = label.to_dict()
        restored = Label.from_dict(data)

        assert restored.name == label.name
        assert restored.color == label.color

    def test_milestone_serialization(self):
        """Milestone can be serialized and deserialized."""
        milestone = Milestone(
            name="v1.0",
            due_date=datetime.now(timezone.utc),
        )

        data = milestone.to_dict()
        restored = Milestone.from_dict(data)

        assert restored.name == milestone.name
        assert restored.due_date is not None

    def test_session_serialization(self):
        """Session can be serialized and deserialized."""
        session = Session(
            summary="Did work",
            next_steps=["Step 1", "Step 2"],
        )

        data = session.to_dict()
        restored = Session.from_dict(data)

        assert restored.summary == session.summary
        assert restored.next_steps == session.next_steps
