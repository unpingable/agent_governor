"""
Task management for Agent Governor.

A lightweight issue tracker integrated with the governor:
- Subtasks with parent/child hierarchy
- Dependencies (blocking relationships)
- Related tasks (many-to-many linking)
- Labels and priorities
- Milestones/epics for release planning
- Time tracking with start/stop timers
- Session management with handoff notes
- Recommendations for what to work on next
"""

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from .storage import Storage, get_storage


class TaskStatus(Enum):
    """Task lifecycle states."""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    DONE = "done"
    ARCHIVED = "archived"


class Priority(Enum):
    """Task priority levels."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    NONE = 5


@dataclass
class Label:
    """A label for organizing tasks."""
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    color: str = "#808080"  # Hex color for display
    description: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "color": self.color,
            "description": self.description,
            "created_at": self.created_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Label":
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            color=data.get("color", "#808080"),
            description=data.get("description", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
        )


@dataclass
class Milestone:
    """A milestone/epic grouping related tasks."""
    id: UUID = field(default_factory=uuid4)
    name: str = ""
    description: str = ""
    due_date: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None

    @property
    def is_closed(self) -> bool:
        return self.closed_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "created_at": self.created_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Milestone":
        return cls(
            id=UUID(data["id"]),
            name=data["name"],
            description=data.get("description", ""),
            due_date=datetime.fromisoformat(data["due_date"]) if data.get("due_date") else None,
            created_at=datetime.fromisoformat(data["created_at"]),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
        )


@dataclass
class TimeEntry:
    """A time tracking entry."""
    id: UUID = field(default_factory=uuid4)
    task_id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None
    note: str = ""

    @property
    def duration(self) -> timedelta:
        """Get duration of this entry."""
        end = self.stopped_at or datetime.now(timezone.utc)
        return end - self.started_at

    @property
    def is_running(self) -> bool:
        return self.stopped_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "task_id": str(self.task_id),
            "started_at": self.started_at.isoformat(),
            "stopped_at": self.stopped_at.isoformat() if self.stopped_at else None,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TimeEntry":
        return cls(
            id=UUID(data["id"]),
            task_id=UUID(data["task_id"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            stopped_at=datetime.fromisoformat(data["stopped_at"]) if data.get("stopped_at") else None,
            note=data.get("note", ""),
        )


@dataclass
class Task:
    """A task/issue in the tracker."""
    id: UUID = field(default_factory=uuid4)
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.OPEN
    priority: Priority = Priority.MEDIUM

    # Hierarchy
    parent_id: UUID | None = None  # For subtasks

    # Organization
    label_ids: list[UUID] = field(default_factory=list)
    milestone_id: UUID | None = None

    # Relationships
    depends_on: list[UUID] = field(default_factory=list)  # Blocked by these tasks
    related_to: list[UUID] = field(default_factory=list)  # Related tasks (bidirectional)

    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: datetime | None = None
    archived_at: datetime | None = None

    # Agent association
    agent_id: str | None = None

    # Context from proposals
    proposal_ids: list[str] = field(default_factory=list)

    @property
    def is_subtask(self) -> bool:
        return self.parent_id is not None

    @property
    def is_blocked(self) -> bool:
        return self.status == TaskStatus.BLOCKED

    @property
    def is_done(self) -> bool:
        return self.status == TaskStatus.DONE

    @property
    def is_archived(self) -> bool:
        return self.archived_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "priority": self.priority.value,
            "parent_id": str(self.parent_id) if self.parent_id else None,
            "label_ids": [str(lid) for lid in self.label_ids],
            "milestone_id": str(self.milestone_id) if self.milestone_id else None,
            "depends_on": [str(did) for did in self.depends_on],
            "related_to": [str(rid) for rid in self.related_to],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "closed_at": self.closed_at.isoformat() if self.closed_at else None,
            "archived_at": self.archived_at.isoformat() if self.archived_at else None,
            "agent_id": self.agent_id,
            "proposal_ids": self.proposal_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            id=UUID(data["id"]),
            title=data["title"],
            description=data.get("description", ""),
            status=TaskStatus(data["status"]),
            priority=Priority(data["priority"]),
            parent_id=UUID(data["parent_id"]) if data.get("parent_id") else None,
            label_ids=[UUID(lid) for lid in data.get("label_ids", [])],
            milestone_id=UUID(data["milestone_id"]) if data.get("milestone_id") else None,
            depends_on=[UUID(did) for did in data.get("depends_on", [])],
            related_to=[UUID(rid) for rid in data.get("related_to", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            closed_at=datetime.fromisoformat(data["closed_at"]) if data.get("closed_at") else None,
            archived_at=datetime.fromisoformat(data["archived_at"]) if data.get("archived_at") else None,
            agent_id=data.get("agent_id"),
            proposal_ids=data.get("proposal_ids", []),
        )


@dataclass
class Session:
    """A work session with handoff notes."""
    id: UUID = field(default_factory=uuid4)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    # Context
    agent_id: str | None = None
    task_ids: list[UUID] = field(default_factory=list)  # Tasks worked on

    # Handoff
    summary: str = ""  # What was accomplished
    next_steps: list[str] = field(default_factory=list)  # What to do next
    blockers: list[str] = field(default_factory=list)  # What's blocking progress
    notes: str = ""  # Free-form notes

    # Links
    proposal_ids: list[str] = field(default_factory=list)  # Proposals created
    decision_ids: list[str] = field(default_factory=list)  # Decisions made

    @property
    def is_active(self) -> bool:
        return self.ended_at is None

    @property
    def duration(self) -> timedelta:
        end = self.ended_at or datetime.now(timezone.utc)
        return end - self.started_at

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "agent_id": self.agent_id,
            "task_ids": [str(tid) for tid in self.task_ids],
            "summary": self.summary,
            "next_steps": self.next_steps,
            "blockers": self.blockers,
            "notes": self.notes,
            "proposal_ids": self.proposal_ids,
            "decision_ids": self.decision_ids,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        return cls(
            id=UUID(data["id"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data.get("ended_at") else None,
            agent_id=data.get("agent_id"),
            task_ids=[UUID(tid) for tid in data.get("task_ids", [])],
            summary=data.get("summary", ""),
            next_steps=data.get("next_steps", []),
            blockers=data.get("blockers", []),
            notes=data.get("notes", ""),
            proposal_ids=data.get("proposal_ids", []),
            decision_ids=data.get("decision_ids", []),
        )


# Schema extension for tasks
TASKS_SCHEMA = """
-- Tasks/issues
CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    status TEXT NOT NULL DEFAULT 'open',
    priority INTEGER NOT NULL DEFAULT 3,
    parent_id TEXT,
    milestone_id TEXT,
    label_ids_json TEXT DEFAULT '[]',
    depends_on_json TEXT DEFAULT '[]',
    related_to_json TEXT DEFAULT '[]',
    agent_id TEXT,
    proposal_ids_json TEXT DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    closed_at TEXT,
    archived_at TEXT,
    FOREIGN KEY (parent_id) REFERENCES tasks(id),
    FOREIGN KEY (milestone_id) REFERENCES milestones(id)
);

CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_priority ON tasks(priority);
CREATE INDEX IF NOT EXISTS idx_tasks_parent ON tasks(parent_id);
CREATE INDEX IF NOT EXISTS idx_tasks_milestone ON tasks(milestone_id);
CREATE INDEX IF NOT EXISTS idx_tasks_archived ON tasks(archived_at);

-- Labels
CREATE TABLE IF NOT EXISTS labels (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#808080',
    description TEXT DEFAULT '',
    created_at TEXT NOT NULL
);

-- Milestones/epics
CREATE TABLE IF NOT EXISTS milestones (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    due_date TEXT,
    created_at TEXT NOT NULL,
    closed_at TEXT
);

-- Time tracking entries
CREATE TABLE IF NOT EXISTS time_entries (
    id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    stopped_at TEXT,
    note TEXT DEFAULT '',
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX IF NOT EXISTS idx_time_entries_task ON time_entries(task_id);
CREATE INDEX IF NOT EXISTS idx_time_entries_running ON time_entries(stopped_at);

-- Sessions with handoff notes
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    agent_id TEXT,
    task_ids_json TEXT DEFAULT '[]',
    summary TEXT DEFAULT '',
    next_steps_json TEXT DEFAULT '[]',
    blockers_json TEXT DEFAULT '[]',
    notes TEXT DEFAULT '',
    proposal_ids_json TEXT DEFAULT '[]',
    decision_ids_json TEXT DEFAULT '[]'
);

CREATE INDEX IF NOT EXISTS idx_sessions_agent ON sessions(agent_id);
CREATE INDEX IF NOT EXISTS idx_sessions_active ON sessions(ended_at);
"""


class TaskManager:
    """
    Manages tasks, labels, milestones, time tracking, and sessions.

    Provides CRUD operations plus:
    - Dependency resolution
    - Recommendation engine
    - Tree visualization
    - Export/import
    """

    def __init__(self, storage: Storage):
        self.storage = storage
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        """Create tasks tables if they don't exist."""
        with self.storage.transaction() as cursor:
            cursor.executescript(TASKS_SCHEMA)

    # =========================================================================
    # Task CRUD
    # =========================================================================

    def create_task(
        self,
        title: str,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        parent_id: UUID | None = None,
        milestone_id: UUID | None = None,
        label_ids: list[UUID] | None = None,
        agent_id: str | None = None,
    ) -> Task:
        """Create a new task."""
        now = datetime.now(timezone.utc)
        task = Task(
            title=title,
            description=description,
            priority=priority,
            parent_id=parent_id,
            milestone_id=milestone_id,
            label_ids=label_ids or [],
            agent_id=agent_id,
            created_at=now,
            updated_at=now,
        )

        self.storage.insert(
            "tasks",
            {
                "id": str(task.id),
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority.value,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "milestone_id": str(task.milestone_id) if task.milestone_id else None,
                "label_ids_json": json.dumps([str(lid) for lid in task.label_ids]),
                "depends_on_json": json.dumps([]),
                "related_to_json": json.dumps([]),
                "agent_id": task.agent_id,
                "proposal_ids_json": json.dumps([]),
                "created_at": task.created_at.isoformat(),
                "updated_at": task.updated_at.isoformat(),
                "closed_at": None,
                "archived_at": None,
            },
        )

        return task

    def get_task(self, task_id: UUID) -> Task | None:
        """Get a task by ID."""
        row = self.storage.get_by_id("tasks", str(task_id))
        if not row:
            return None
        return self._row_to_task(row)

    def update_task(self, task: Task) -> None:
        """Update an existing task."""
        task.updated_at = datetime.now(timezone.utc)
        self.storage.update(
            "tasks",
            "id",
            str(task.id),
            {
                "title": task.title,
                "description": task.description,
                "status": task.status.value,
                "priority": task.priority.value,
                "parent_id": str(task.parent_id) if task.parent_id else None,
                "milestone_id": str(task.milestone_id) if task.milestone_id else None,
                "label_ids_json": json.dumps([str(lid) for lid in task.label_ids]),
                "depends_on_json": json.dumps([str(did) for did in task.depends_on]),
                "related_to_json": json.dumps([str(rid) for rid in task.related_to]),
                "agent_id": task.agent_id,
                "proposal_ids_json": json.dumps(task.proposal_ids),
                "updated_at": task.updated_at.isoformat(),
                "closed_at": task.closed_at.isoformat() if task.closed_at else None,
                "archived_at": task.archived_at.isoformat() if task.archived_at else None,
            },
        )

    def delete_task(self, task_id: UUID) -> bool:
        """Delete a task."""
        return self.storage.delete("tasks", "id", str(task_id))

    def list_tasks(
        self,
        status: TaskStatus | None = None,
        milestone_id: UUID | None = None,
        parent_id: UUID | None = None,
        include_archived: bool = False,
        label_id: UUID | None = None,
    ) -> list[Task]:
        """List tasks with optional filters."""
        where: dict[str, Any] = {}
        if status:
            where["status"] = status.value
        if milestone_id:
            where["milestone_id"] = str(milestone_id)
        if parent_id:
            where["parent_id"] = str(parent_id)

        rows = self.storage.query("tasks", where=where or None, order_by="priority ASC, created_at DESC")

        tasks = []
        for row in rows:
            task = self._row_to_task(row)

            # Filter archived if needed
            if not include_archived and task.archived_at:
                continue

            # Filter by label if specified
            if label_id and label_id not in task.label_ids:
                continue

            tasks.append(task)

        return tasks

    def get_subtasks(self, parent_id: UUID) -> list[Task]:
        """Get all subtasks of a task."""
        return self.list_tasks(parent_id=parent_id)

    def _row_to_task(self, row) -> Task:
        """Convert a database row to a Task object."""
        return Task(
            id=UUID(row["id"]),
            title=row["title"],
            description=row["description"] or "",
            status=TaskStatus(row["status"]),
            priority=Priority(row["priority"]),
            parent_id=UUID(row["parent_id"]) if row["parent_id"] else None,
            milestone_id=UUID(row["milestone_id"]) if row["milestone_id"] else None,
            label_ids=[UUID(lid) for lid in json.loads(row["label_ids_json"])],
            depends_on=[UUID(did) for did in json.loads(row["depends_on_json"])],
            related_to=[UUID(rid) for rid in json.loads(row["related_to_json"])],
            agent_id=row["agent_id"],
            proposal_ids=json.loads(row["proposal_ids_json"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            closed_at=datetime.fromisoformat(row["closed_at"]) if row["closed_at"] else None,
            archived_at=datetime.fromisoformat(row["archived_at"]) if row["archived_at"] else None,
        )

    # =========================================================================
    # Task Status Changes
    # =========================================================================

    def start_task(self, task_id: UUID) -> Task | None:
        """Mark a task as in progress."""
        task = self.get_task(task_id)
        if not task:
            return None

        # Check if blocked by dependencies
        if self._is_blocked(task):
            task.status = TaskStatus.BLOCKED
        else:
            task.status = TaskStatus.IN_PROGRESS

        self.update_task(task)
        return task

    def complete_task(self, task_id: UUID) -> Task | None:
        """Mark a task as done."""
        task = self.get_task(task_id)
        if not task:
            return None

        task.status = TaskStatus.DONE
        task.closed_at = datetime.now(timezone.utc)
        self.update_task(task)

        # Check if any blocked tasks can be unblocked
        self._update_blocked_tasks()

        return task

    def archive_task(self, task_id: UUID) -> Task | None:
        """Archive a completed task."""
        task = self.get_task(task_id)
        if not task:
            return None

        task.status = TaskStatus.ARCHIVED
        task.archived_at = datetime.now(timezone.utc)
        self.update_task(task)
        return task

    def reopen_task(self, task_id: UUID) -> Task | None:
        """Reopen a closed/archived task."""
        task = self.get_task(task_id)
        if not task:
            return None

        task.status = TaskStatus.OPEN
        task.closed_at = None
        task.archived_at = None
        self.update_task(task)
        return task

    def _is_blocked(self, task: Task) -> bool:
        """Check if a task is blocked by incomplete dependencies."""
        for dep_id in task.depends_on:
            dep = self.get_task(dep_id)
            if dep and dep.status != TaskStatus.DONE:
                return True
        return False

    def _update_blocked_tasks(self) -> None:
        """Update status of tasks that may have been unblocked."""
        blocked_tasks = self.list_tasks(status=TaskStatus.BLOCKED)
        for task in blocked_tasks:
            if not self._is_blocked(task):
                task.status = TaskStatus.OPEN
                self.update_task(task)

    # =========================================================================
    # Dependencies
    # =========================================================================

    def add_dependency(self, task_id: UUID, depends_on_id: UUID) -> bool:
        """Add a dependency (task_id is blocked by depends_on_id)."""
        task = self.get_task(task_id)
        if not task:
            return False

        # Prevent circular dependencies
        if self._would_create_cycle(task_id, depends_on_id):
            return False

        if depends_on_id not in task.depends_on:
            task.depends_on.append(depends_on_id)

            # Check if this blocks the task
            if task.status == TaskStatus.IN_PROGRESS and self._is_blocked(task):
                task.status = TaskStatus.BLOCKED

            self.update_task(task)

        return True

    def remove_dependency(self, task_id: UUID, depends_on_id: UUID) -> bool:
        """Remove a dependency."""
        task = self.get_task(task_id)
        if not task:
            return False

        if depends_on_id in task.depends_on:
            task.depends_on.remove(depends_on_id)

            # Check if task can be unblocked
            if task.status == TaskStatus.BLOCKED and not self._is_blocked(task):
                task.status = TaskStatus.OPEN

            self.update_task(task)

        return True

    def get_blocking_tasks(self, task_id: UUID) -> list[Task]:
        """Get tasks that are blocking this task."""
        task = self.get_task(task_id)
        if not task:
            return []

        blocking = []
        for dep_id in task.depends_on:
            dep = self.get_task(dep_id)
            if dep and dep.status != TaskStatus.DONE:
                blocking.append(dep)

        return blocking

    def get_dependent_tasks(self, task_id: UUID) -> list[Task]:
        """Get tasks that depend on this task."""
        dependents = []
        for task in self.list_tasks():
            if task_id in task.depends_on:
                dependents.append(task)
        return dependents

    def _would_create_cycle(self, task_id: UUID, new_dep_id: UUID) -> bool:
        """Check if adding this dependency would create a cycle."""
        # DFS to check if we can reach task_id from new_dep_id
        visited = set()
        to_visit = [new_dep_id]

        while to_visit:
            current_id = to_visit.pop()
            if current_id == task_id:
                return True

            if current_id in visited:
                continue
            visited.add(current_id)

            current = self.get_task(current_id)
            if current:
                to_visit.extend(current.depends_on)

        return False

    # =========================================================================
    # Related Tasks
    # =========================================================================

    def link_tasks(self, task_id_1: UUID, task_id_2: UUID) -> bool:
        """Link two tasks as related (bidirectional)."""
        task1 = self.get_task(task_id_1)
        task2 = self.get_task(task_id_2)

        if not task1 or not task2:
            return False

        if task_id_2 not in task1.related_to:
            task1.related_to.append(task_id_2)
            self.update_task(task1)

        if task_id_1 not in task2.related_to:
            task2.related_to.append(task_id_1)
            self.update_task(task2)

        return True

    def unlink_tasks(self, task_id_1: UUID, task_id_2: UUID) -> bool:
        """Remove the relationship between two tasks."""
        task1 = self.get_task(task_id_1)
        task2 = self.get_task(task_id_2)

        if task1 and task_id_2 in task1.related_to:
            task1.related_to.remove(task_id_2)
            self.update_task(task1)

        if task2 and task_id_1 in task2.related_to:
            task2.related_to.remove(task_id_1)
            self.update_task(task2)

        return True

    def get_related_tasks(self, task_id: UUID) -> list[Task]:
        """Get all tasks related to this one."""
        task = self.get_task(task_id)
        if not task:
            return []

        related = []
        for rel_id in task.related_to:
            rel = self.get_task(rel_id)
            if rel:
                related.append(rel)

        return related

    # =========================================================================
    # Labels
    # =========================================================================

    def create_label(self, name: str, color: str = "#808080", description: str = "") -> Label:
        """Create a new label."""
        label = Label(name=name, color=color, description=description)

        self.storage.insert(
            "labels",
            {
                "id": str(label.id),
                "name": label.name,
                "color": label.color,
                "description": label.description,
                "created_at": label.created_at.isoformat(),
            },
        )

        return label

    def get_label(self, label_id: UUID) -> Label | None:
        """Get a label by ID."""
        row = self.storage.get_by_id("labels", str(label_id))
        if not row:
            return None
        return Label(
            id=UUID(row["id"]),
            name=row["name"],
            color=row["color"],
            description=row["description"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def get_label_by_name(self, name: str) -> Label | None:
        """Get a label by name."""
        rows = self.storage.query("labels", where={"name": name})
        if not rows:
            return None
        row = rows[0]
        return Label(
            id=UUID(row["id"]),
            name=row["name"],
            color=row["color"],
            description=row["description"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def list_labels(self) -> list[Label]:
        """List all labels."""
        rows = self.storage.query("labels", order_by="name ASC")
        return [
            Label(
                id=UUID(row["id"]),
                name=row["name"],
                color=row["color"],
                description=row["description"] or "",
                created_at=datetime.fromisoformat(row["created_at"]),
            )
            for row in rows
        ]

    def delete_label(self, label_id: UUID) -> bool:
        """Delete a label."""
        return self.storage.delete("labels", "id", str(label_id))

    def add_label_to_task(self, task_id: UUID, label_id: UUID) -> bool:
        """Add a label to a task."""
        task = self.get_task(task_id)
        if not task:
            return False

        if label_id not in task.label_ids:
            task.label_ids.append(label_id)
            self.update_task(task)

        return True

    def remove_label_from_task(self, task_id: UUID, label_id: UUID) -> bool:
        """Remove a label from a task."""
        task = self.get_task(task_id)
        if not task:
            return False

        if label_id in task.label_ids:
            task.label_ids.remove(label_id)
            self.update_task(task)

        return True

    # =========================================================================
    # Milestones
    # =========================================================================

    def create_milestone(
        self,
        name: str,
        description: str = "",
        due_date: datetime | None = None,
    ) -> Milestone:
        """Create a new milestone."""
        milestone = Milestone(name=name, description=description, due_date=due_date)

        self.storage.insert(
            "milestones",
            {
                "id": str(milestone.id),
                "name": milestone.name,
                "description": milestone.description,
                "due_date": milestone.due_date.isoformat() if milestone.due_date else None,
                "created_at": milestone.created_at.isoformat(),
                "closed_at": None,
            },
        )

        return milestone

    def get_milestone(self, milestone_id: UUID) -> Milestone | None:
        """Get a milestone by ID."""
        row = self.storage.get_by_id("milestones", str(milestone_id))
        if not row:
            return None
        return Milestone.from_dict({
            "id": row["id"],
            "name": row["name"],
            "description": row["description"] or "",
            "due_date": row["due_date"],
            "created_at": row["created_at"],
            "closed_at": row["closed_at"],
        })

    def list_milestones(self, include_closed: bool = False) -> list[Milestone]:
        """List all milestones."""
        rows = self.storage.query("milestones", order_by="due_date ASC")
        milestones = []
        for row in rows:
            milestone = Milestone.from_dict({
                "id": row["id"],
                "name": row["name"],
                "description": row["description"] or "",
                "due_date": row["due_date"],
                "created_at": row["created_at"],
                "closed_at": row["closed_at"],
            })
            if not include_closed and milestone.is_closed:
                continue
            milestones.append(milestone)
        return milestones

    def close_milestone(self, milestone_id: UUID) -> Milestone | None:
        """Close a milestone."""
        milestone = self.get_milestone(milestone_id)
        if not milestone:
            return None

        milestone.closed_at = datetime.now(timezone.utc)
        self.storage.update(
            "milestones",
            "id",
            str(milestone_id),
            {"closed_at": milestone.closed_at.isoformat()},
        )

        return milestone

    def get_milestone_progress(self, milestone_id: UUID) -> dict[str, int]:
        """Get progress stats for a milestone."""
        tasks = self.list_tasks(milestone_id=milestone_id)

        total = len(tasks)
        done = sum(1 for t in tasks if t.status == TaskStatus.DONE)
        in_progress = sum(1 for t in tasks if t.status == TaskStatus.IN_PROGRESS)
        blocked = sum(1 for t in tasks if t.status == TaskStatus.BLOCKED)
        open_count = sum(1 for t in tasks if t.status == TaskStatus.OPEN)

        return {
            "total": total,
            "done": done,
            "in_progress": in_progress,
            "blocked": blocked,
            "open": open_count,
            "percent_complete": int((done / total * 100) if total > 0 else 0),
        }

    # =========================================================================
    # Time Tracking
    # =========================================================================

    def start_timer(self, task_id: UUID, note: str = "") -> TimeEntry:
        """Start a timer for a task."""
        # Stop any running timer for this task first
        self.stop_timer(task_id)

        entry = TimeEntry(task_id=task_id, note=note)

        self.storage.insert(
            "time_entries",
            {
                "id": str(entry.id),
                "task_id": str(entry.task_id),
                "started_at": entry.started_at.isoformat(),
                "stopped_at": None,
                "note": entry.note,
            },
        )

        return entry

    def stop_timer(self, task_id: UUID) -> TimeEntry | None:
        """Stop the running timer for a task."""
        # Find running entry
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM time_entries WHERE task_id = ? AND stopped_at IS NULL",
            (str(task_id),)
        )
        row = cursor.fetchone()

        if not row:
            return None

        now = datetime.now(timezone.utc)
        self.storage.update(
            "time_entries",
            "id",
            row["id"],
            {"stopped_at": now.isoformat()},
        )

        return TimeEntry(
            id=UUID(row["id"]),
            task_id=UUID(row["task_id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            stopped_at=now,
            note=row["note"] or "",
        )

    def get_running_timer(self, task_id: UUID) -> TimeEntry | None:
        """Get the currently running timer for a task."""
        cursor = self.storage.conn.cursor()
        cursor.execute(
            "SELECT * FROM time_entries WHERE task_id = ? AND stopped_at IS NULL",
            (str(task_id),)
        )
        row = cursor.fetchone()

        if not row:
            return None

        return TimeEntry.from_dict({
            "id": row["id"],
            "task_id": row["task_id"],
            "started_at": row["started_at"],
            "stopped_at": row["stopped_at"],
            "note": row["note"] or "",
        })

    def get_time_entries(self, task_id: UUID) -> list[TimeEntry]:
        """Get all time entries for a task."""
        rows = self.storage.query(
            "time_entries",
            where={"task_id": str(task_id)},
            order_by="started_at DESC",
        )
        return [
            TimeEntry.from_dict({
                "id": row["id"],
                "task_id": row["task_id"],
                "started_at": row["started_at"],
                "stopped_at": row["stopped_at"],
                "note": row["note"] or "",
            })
            for row in rows
        ]

    def get_total_time(self, task_id: UUID) -> timedelta:
        """Get total time spent on a task."""
        entries = self.get_time_entries(task_id)
        total = timedelta()
        for entry in entries:
            total += entry.duration
        return total

    # =========================================================================
    # Sessions
    # =========================================================================

    def start_session(self, agent_id: str | None = None) -> Session:
        """Start a new work session."""
        session = Session(agent_id=agent_id)

        self.storage.insert(
            "sessions",
            {
                "id": str(session.id),
                "started_at": session.started_at.isoformat(),
                "ended_at": None,
                "agent_id": session.agent_id,
                "task_ids_json": json.dumps([]),
                "summary": "",
                "next_steps_json": json.dumps([]),
                "blockers_json": json.dumps([]),
                "notes": "",
                "proposal_ids_json": json.dumps([]),
                "decision_ids_json": json.dumps([]),
            },
        )

        return session

    def get_session(self, session_id: UUID) -> Session | None:
        """Get a session by ID."""
        row = self.storage.get_by_id("sessions", str(session_id))
        if not row:
            return None
        return self._row_to_session(row)

    def get_active_session(self, agent_id: str | None = None) -> Session | None:
        """Get the currently active session."""
        cursor = self.storage.conn.cursor()
        if agent_id:
            cursor.execute(
                "SELECT * FROM sessions WHERE ended_at IS NULL AND agent_id = ? ORDER BY started_at DESC LIMIT 1",
                (agent_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC LIMIT 1"
            )
        row = cursor.fetchone()

        if not row:
            return None
        return self._row_to_session(row)

    def update_session(self, session: Session) -> None:
        """Update a session."""
        self.storage.update(
            "sessions",
            "id",
            str(session.id),
            {
                "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                "task_ids_json": json.dumps([str(tid) for tid in session.task_ids]),
                "summary": session.summary,
                "next_steps_json": json.dumps(session.next_steps),
                "blockers_json": json.dumps(session.blockers),
                "notes": session.notes,
                "proposal_ids_json": json.dumps(session.proposal_ids),
                "decision_ids_json": json.dumps(session.decision_ids),
            },
        )

    def end_session(
        self,
        session_id: UUID,
        summary: str = "",
        next_steps: list[str] | None = None,
        blockers: list[str] | None = None,
        notes: str = "",
    ) -> Session | None:
        """End a session with handoff notes."""
        session = self.get_session(session_id)
        if not session:
            return None

        session.ended_at = datetime.now(timezone.utc)
        session.summary = summary
        session.next_steps = next_steps or []
        session.blockers = blockers or []
        session.notes = notes

        self.update_session(session)
        return session

    def get_last_session(self, agent_id: str | None = None) -> Session | None:
        """Get the most recent completed session."""
        cursor = self.storage.conn.cursor()
        if agent_id:
            cursor.execute(
                "SELECT * FROM sessions WHERE ended_at IS NOT NULL AND agent_id = ? ORDER BY ended_at DESC LIMIT 1",
                (agent_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM sessions WHERE ended_at IS NOT NULL ORDER BY ended_at DESC LIMIT 1"
            )
        row = cursor.fetchone()

        if not row:
            return None
        return self._row_to_session(row)

    def list_sessions(self, limit: int = 10) -> list[Session]:
        """List recent sessions."""
        rows = self.storage.query("sessions", order_by="started_at DESC", limit=limit)
        return [self._row_to_session(row) for row in rows]

    def _row_to_session(self, row) -> Session:
        """Convert a database row to a Session object."""
        return Session(
            id=UUID(row["id"]),
            started_at=datetime.fromisoformat(row["started_at"]),
            ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
            agent_id=row["agent_id"],
            task_ids=[UUID(tid) for tid in json.loads(row["task_ids_json"])],
            summary=row["summary"] or "",
            next_steps=json.loads(row["next_steps_json"]),
            blockers=json.loads(row["blockers_json"]),
            notes=row["notes"] or "",
            proposal_ids=json.loads(row["proposal_ids_json"]),
            decision_ids=json.loads(row["decision_ids_json"]),
        )

    def format_handoff(self, session: Session | None = None) -> str:
        """Format session handoff for injection into agent prompts."""
        if session is None:
            session = self.get_last_session()

        if not session:
            return "No previous session found."

        lines = [
            "## Previous Session Handoff",
            "",
            f"**Ended:** {session.ended_at.isoformat() if session.ended_at else 'In progress'}",
            f"**Duration:** {session.duration}",
            "",
        ]

        if session.summary:
            lines.extend([
                "### Summary",
                session.summary,
                "",
            ])

        if session.next_steps:
            lines.extend([
                "### Next Steps",
                *[f"- {step}" for step in session.next_steps],
                "",
            ])

        if session.blockers:
            lines.extend([
                "### Blockers",
                *[f"- {blocker}" for blocker in session.blockers],
                "",
            ])

        if session.notes:
            lines.extend([
                "### Notes",
                session.notes,
                "",
            ])

        return "\n".join(lines)

    # =========================================================================
    # Recommendations
    # =========================================================================

    def recommend_next(self, agent_id: str | None = None) -> list[Task]:
        """
        Recommend tasks to work on next.

        Prioritization:
        1. High priority unblocked tasks
        2. Tasks with approaching milestone deadlines
        3. Tasks that would unblock other tasks
        4. Recently updated tasks (momentum)
        """
        all_tasks = self.list_tasks()

        # Filter to workable tasks
        workable = [
            t for t in all_tasks
            if t.status in (TaskStatus.OPEN, TaskStatus.IN_PROGRESS)
            and not self._is_blocked(t)
        ]

        # Score each task
        scored = []
        for task in workable:
            score = 0

            # Priority score (higher priority = higher score)
            score += (6 - task.priority.value) * 10

            # Milestone urgency
            if task.milestone_id:
                milestone = self.get_milestone(task.milestone_id)
                if milestone and milestone.due_date:
                    days_until = (milestone.due_date - datetime.now(timezone.utc)).days
                    if days_until < 0:
                        score += 50  # Overdue
                    elif days_until < 7:
                        score += 30
                    elif days_until < 14:
                        score += 15

            # Would unblock others
            dependents = self.get_dependent_tasks(task.id)
            blocked_dependents = [d for d in dependents if d.status == TaskStatus.BLOCKED]
            score += len(blocked_dependents) * 5

            # In progress bonus (momentum)
            if task.status == TaskStatus.IN_PROGRESS:
                score += 20

            # Recent activity bonus
            age = (datetime.now(timezone.utc) - task.updated_at).days
            if age < 1:
                score += 10
            elif age < 3:
                score += 5

            scored.append((score, task))

        # Sort by score descending
        scored.sort(key=lambda x: x[0], reverse=True)

        return [task for score, task in scored[:5]]

    # =========================================================================
    # Tree View
    # =========================================================================

    def format_tree(self, milestone_id: UUID | None = None) -> str:
        """Format tasks as a tree view."""
        if milestone_id:
            tasks = self.list_tasks(milestone_id=milestone_id)
        else:
            tasks = self.list_tasks()

        # Build parent -> children map
        children_map: dict[UUID | None, list[Task]] = {None: []}
        for task in tasks:
            if task.parent_id not in children_map:
                children_map[task.parent_id] = []
            children_map[task.parent_id].append(task)

        # Format tree recursively
        lines = []

        def format_task(task: Task, indent: str = "", is_last: bool = True) -> None:
            prefix = indent + ("└── " if is_last else "├── ")

            # Status icon
            status_icons = {
                TaskStatus.OPEN: "○",
                TaskStatus.IN_PROGRESS: "●",
                TaskStatus.BLOCKED: "⊗",
                TaskStatus.DONE: "✓",
                TaskStatus.ARCHIVED: "▣",
            }
            icon = status_icons.get(task.status, "?")

            # Priority indicator
            priority_indicators = {
                Priority.CRITICAL: "!!!",
                Priority.HIGH: "!!",
                Priority.MEDIUM: "!",
                Priority.LOW: "",
                Priority.NONE: "",
            }
            priority = priority_indicators.get(task.priority, "")

            lines.append(f"{prefix}{icon} {task.title} {priority}".rstrip())

            # Format children
            children = children_map.get(task.id, [])
            child_indent = indent + ("    " if is_last else "│   ")
            for i, child in enumerate(children):
                format_task(child, child_indent, i == len(children) - 1)

        # Format root tasks
        root_tasks = children_map.get(None, [])
        for i, task in enumerate(root_tasks):
            format_task(task, "", i == len(root_tasks) - 1)

        return "\n".join(lines) if lines else "(no tasks)"

    # =========================================================================
    # Export/Import
    # =========================================================================

    def export_json(self) -> dict[str, Any]:
        """Export all task data as JSON."""
        return {
            "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "tasks": [t.to_dict() for t in self.list_tasks(include_archived=True)],
            "labels": [l.to_dict() for l in self.list_labels()],
            "milestones": [m.to_dict() for m in self.list_milestones(include_closed=True)],
            "sessions": [s.to_dict() for s in self.list_sessions(limit=100)],
        }

    def import_json(self, data: dict[str, Any], merge: bool = True) -> dict[str, int]:
        """
        Import task data from JSON.

        Args:
            data: Exported JSON data
            merge: If True, merge with existing data. If False, replace.

        Returns:
            Dict with counts of imported items
        """
        counts = {"tasks": 0, "labels": 0, "milestones": 0, "sessions": 0}

        if not merge:
            # Clear existing data
            with self.storage.transaction() as cursor:
                cursor.execute("DELETE FROM tasks")
                cursor.execute("DELETE FROM labels")
                cursor.execute("DELETE FROM milestones")
                cursor.execute("DELETE FROM sessions")

        # Import labels first (tasks reference them)
        for label_data in data.get("labels", []):
            label = Label.from_dict(label_data)
            existing = self.get_label(label.id)
            if not existing:
                self.storage.insert(
                    "labels",
                    {
                        "id": str(label.id),
                        "name": label.name,
                        "color": label.color,
                        "description": label.description,
                        "created_at": label.created_at.isoformat(),
                    },
                )
                counts["labels"] += 1

        # Import milestones (tasks reference them)
        for milestone_data in data.get("milestones", []):
            milestone = Milestone.from_dict(milestone_data)
            existing = self.get_milestone(milestone.id)
            if not existing:
                self.storage.insert(
                    "milestones",
                    {
                        "id": str(milestone.id),
                        "name": milestone.name,
                        "description": milestone.description,
                        "due_date": milestone.due_date.isoformat() if milestone.due_date else None,
                        "created_at": milestone.created_at.isoformat(),
                        "closed_at": milestone.closed_at.isoformat() if milestone.closed_at else None,
                    },
                )
                counts["milestones"] += 1

        # Import tasks
        for task_data in data.get("tasks", []):
            task = Task.from_dict(task_data)
            existing = self.get_task(task.id)
            if not existing:
                self.storage.insert(
                    "tasks",
                    {
                        "id": str(task.id),
                        "title": task.title,
                        "description": task.description,
                        "status": task.status.value,
                        "priority": task.priority.value,
                        "parent_id": str(task.parent_id) if task.parent_id else None,
                        "milestone_id": str(task.milestone_id) if task.milestone_id else None,
                        "label_ids_json": json.dumps([str(lid) for lid in task.label_ids]),
                        "depends_on_json": json.dumps([str(did) for did in task.depends_on]),
                        "related_to_json": json.dumps([str(rid) for rid in task.related_to]),
                        "agent_id": task.agent_id,
                        "proposal_ids_json": json.dumps(task.proposal_ids),
                        "created_at": task.created_at.isoformat(),
                        "updated_at": task.updated_at.isoformat(),
                        "closed_at": task.closed_at.isoformat() if task.closed_at else None,
                        "archived_at": task.archived_at.isoformat() if task.archived_at else None,
                    },
                )
                counts["tasks"] += 1

        # Import sessions
        for session_data in data.get("sessions", []):
            session = Session.from_dict(session_data)
            existing = self.get_session(session.id)
            if not existing:
                self.storage.insert(
                    "sessions",
                    {
                        "id": str(session.id),
                        "started_at": session.started_at.isoformat(),
                        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                        "agent_id": session.agent_id,
                        "task_ids_json": json.dumps([str(tid) for tid in session.task_ids]),
                        "summary": session.summary,
                        "next_steps_json": json.dumps(session.next_steps),
                        "blockers_json": json.dumps(session.blockers),
                        "notes": session.notes,
                        "proposal_ids_json": json.dumps(session.proposal_ids),
                        "decision_ids_json": json.dumps(session.decision_ids),
                    },
                )
                counts["sessions"] += 1

        return counts

    def archive_done_tasks(self, older_than_days: int = 30) -> int:
        """Archive completed tasks older than the specified days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)

        tasks = self.list_tasks(status=TaskStatus.DONE)
        archived_count = 0

        for task in tasks:
            if task.closed_at and task.closed_at < cutoff:
                self.archive_task(task.id)
                archived_count += 1

        return archived_count


def get_task_manager(governor_dir: Path) -> TaskManager:
    """Get a TaskManager for a governor directory."""
    storage = get_storage(governor_dir)
    return TaskManager(storage)
