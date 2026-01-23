"""
Agent Governor for Agentic Development

A constraint system that makes AI coding agents production-safe by preventing
hallucination, maintaining architectural coherence, and enforcing evidence requirements.
"""

from .core import AgentGovernor
from .ledger import CodebaseLedger, Commitment, CommitID
from .validators import Validator, FileValidator, Evidence
from .types import ProposalResult, Contradiction

# SQLite-backed multi-agent components
from .storage import Storage, Lease, get_storage
from .ledgers_v2 import (
    Fact,
    Decision,
    SQLiteFactLedger,
    SQLiteDecisionLedger,
    ConflictError,
    get_ledgers,
)
from .permissions import (
    AgentPermissions,
    PermissionManager,
    PROFILES as PERMISSION_PROFILES,
    create_default_config,
)

# Task management
from .tasks import (
    Task,
    TaskStatus,
    Priority,
    Label,
    Milestone,
    TimeEntry,
    Session,
    TaskManager,
    get_task_manager,
)

# Audit graph
from .graph import (
    Node,
    Edge,
    NodeType,
    EdgeType,
    AuditGraph,
    GraphBuilder,
    build_graph,
)

__all__ = [
    # Legacy v0.1
    "AgentGovernor",
    "CodebaseLedger",
    "Commitment",
    "CommitID",
    "Validator",
    "FileValidator",
    "Evidence",
    "ProposalResult",
    "Contradiction",
    # Multi-agent (v2)
    "Storage",
    "Lease",
    "get_storage",
    "Fact",
    "Decision",
    "SQLiteFactLedger",
    "SQLiteDecisionLedger",
    "ConflictError",
    "get_ledgers",
    # Permissions
    "AgentPermissions",
    "PermissionManager",
    "PERMISSION_PROFILES",
    "create_default_config",
    # Task management
    "Task",
    "TaskStatus",
    "Priority",
    "Label",
    "Milestone",
    "TimeEntry",
    "Session",
    "TaskManager",
    "get_task_manager",
    # Audit graph
    "Node",
    "Edge",
    "NodeType",
    "EdgeType",
    "AuditGraph",
    "GraphBuilder",
    "build_graph",
]

__version__ = "0.4.0"
