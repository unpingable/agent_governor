# Context Management Specification

## Version 0.1 — Smart Context Handling and Code Intelligence

```yaml
status: gap
implemented: false
depends_on:
  - SESSION_RESUME_SPEC.md
  - Routing (existing)
  - Telemetry (existing)
blocking:
  - Long conversations without context loss
  - Code mode intelligence
  - Efficient model usage
estimated_scope: medium
```

---

## Executive Summary

As conversations approach context limits, the governor should intelligently manage context through auto-compaction. Additionally, code mode should integrate with Language Server Protocol (LSP) for code intelligence, and model routing should support task-based switching (cheap for chat, expensive for execution).

**Core principle**: Context is a resource. Manage it like one.

---

## 1. The Problems

### 1.1 Context Limits

- Long conversations hit context windows
- Currently: conversation just breaks
- Need: intelligent summarization + continuation

### 1.2 Code Intelligence

- AI lacks IDE-level code understanding
- No access to definitions, references, diagnostics
- Must re-read files repeatedly

### 1.3 Model Efficiency

- Using expensive models for simple tasks wastes money
- Using cheap models for complex tasks produces errors
- Need: automatic routing by task complexity

---

## 2. Auto-Compact

### 2.1 Concept

When approaching context limits, automatically generate a summary and continue with compressed context.

```
┌─────────────────────────────────────────────┐
│  Full Conversation (approaching limit)      │
│  ┌─────────────────────────────────────┐   │
│  │ Turn 1: User asks about X           │   │
│  │ Turn 2: Assistant explains X        │   │
│  │ Turn 3: User asks follow-up         │   │
│  │ ...                                 │   │
│  │ Turn 47: Getting close to limit     │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
                    │
                    ▼ [Auto-compact trigger]
┌─────────────────────────────────────────────┐
│  Compacted Conversation                     │
│  ┌─────────────────────────────────────┐   │
│  │ Summary: "We discussed X, decided   │   │
│  │ Y, established constraints Z..."    │   │
│  └─────────────────────────────────────┘   │
│  ┌─────────────────────────────────────┐   │
│  │ Recent turns (last 5-10)            │   │
│  └─────────────────────────────────────┘   │
└─────────────────────────────────────────────┘
```

### 2.2 Compaction Strategy

```python
@dataclass
class CompactionConfig:
    """Configuration for auto-compaction."""

    # When to trigger
    context_threshold: float = 0.8  # Trigger at 80% of limit
    min_turns_before_compact: int = 20

    # What to keep
    recent_turns_to_keep: int = 10
    always_keep_decisions: bool = True
    always_keep_constraints: bool = True

    # Summary settings
    summary_max_tokens: int = 500
    include_key_facts: bool = True
```

### 2.3 What Goes in Summary

| Category | Include | Why |
|----------|---------|-----|
| Decisions made | Always | Normative, can't be re-derived |
| Active constraints | Always | Needed for governance |
| Key facts established | Yes | Context for continuation |
| Rejected options | Brief | Avoid re-proposing |
| Detailed reasoning | No | Can be re-derived |
| Raw transcripts | No | Too verbose |

### 2.4 Compaction Flow

```python
class ContextCompactor:
    def should_compact(self, conversation: Conversation) -> bool:
        """Check if compaction is needed."""
        usage = conversation.token_count / conversation.context_limit
        return (
            usage >= self.config.context_threshold
            and len(conversation.turns) >= self.config.min_turns_before_compact
        )

    def compact(self, conversation: Conversation) -> CompactedConversation:
        """Compact conversation to fit in context."""
        # 1. Extract key information
        decisions = self._extract_decisions(conversation)
        constraints = self._extract_constraints(conversation)
        key_facts = self._extract_key_facts(conversation)

        # 2. Generate summary
        summary = self._generate_summary(
            conversation,
            decisions=decisions,
            constraints=constraints,
            key_facts=key_facts,
        )

        # 3. Keep recent turns
        recent_turns = conversation.turns[-self.config.recent_turns_to_keep:]

        # 4. Construct compacted conversation
        return CompactedConversation(
            summary=summary,
            recent_turns=recent_turns,
            preserved_decisions=decisions,
            preserved_constraints=constraints,
        )
```

---

## 3. LSP Integration

### 3.1 Concept

Integrate Language Server Protocol to give the AI access to code intelligence:
- Go to definition
- Find references
- Diagnostics (errors, warnings)
- Symbol search
- Hover documentation

### 3.2 Architecture

```
┌─────────────────────────────────────────────┐
│  Governor Code Mode                          │
│  ┌─────────────────────────────────────┐    │
│  │  LSP Client                         │    │
│  │  - Connects to language servers     │    │
│  │  - Caches responses                 │    │
│  │  - Exposes tools to AI              │    │
│  └─────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
           │                │
           ▼                ▼
    ┌──────────────┐  ┌──────────────┐
    │ TypeScript   │  │ Python       │
    │ Server       │  │ Server       │
    │ (tsserver)   │  │ (pylsp)      │
    └──────────────┘  └──────────────┘
```

### 3.3 LSP Tools for AI

```python
# Tools exposed via MCP or direct integration

def lsp_goto_definition(file: str, line: int, col: int) -> Location | None:
    """Go to symbol definition."""
    ...

def lsp_find_references(file: str, line: int, col: int) -> list[Location]:
    """Find all references to symbol."""
    ...

def lsp_get_diagnostics(file: str) -> list[Diagnostic]:
    """Get errors and warnings for file."""
    ...

def lsp_symbol_search(query: str) -> list[Symbol]:
    """Search for symbols by name."""
    ...

def lsp_hover(file: str, line: int, col: int) -> HoverInfo | None:
    """Get hover documentation for symbol."""
    ...
```

### 3.4 Caching

LSP responses are cached to avoid repeated queries:

```python
@dataclass
class LSPCache:
    definitions: dict[tuple[str, int, int], Location]
    references: dict[tuple[str, int, int], list[Location]]
    diagnostics: dict[str, list[Diagnostic]]
    ttl: timedelta = timedelta(minutes=5)
```

---

## 4. Task-Based Model Routing

### 4.1 Concept

Use cheap models for simple tasks, expensive models for complex ones.

| Task Type | Model Tier | Examples |
|-----------|------------|----------|
| Chat / clarification | Cheap (Haiku) | "What do you mean?", "Can you explain?" |
| Simple code changes | Medium (Sonnet) | Rename variable, add comment |
| Complex reasoning | Expensive (Opus) | Architecture decisions, debugging |
| Verification | Cheap | Running tests, checking syntax |

### 4.2 Integration with Routing

The existing `routing.py` module handles complexity estimation. Extend it:

```python
@dataclass
class TaskRoutingConfig:
    """Configuration for task-based model routing."""

    # Chat tasks
    chat_model: str = "haiku"
    chat_complexity_threshold: float = 0.3

    # Execution tasks
    execution_model: str = "sonnet"
    execution_complexity_threshold: float = 0.7

    # Complex tasks
    complex_model: str = "opus"

    # Override for specific task types
    task_overrides: dict[str, str] = field(default_factory=dict)
```

### 4.3 Routing Flow

```python
class TaskRouter:
    def route(self, task: Task) -> str:
        """Route task to appropriate model."""
        # 1. Check for explicit override
        if task.type in self.config.task_overrides:
            return self.config.task_overrides[task.type]

        # 2. Estimate complexity
        complexity = self.estimate_complexity(task)

        # 3. Route by complexity
        if complexity < self.config.chat_complexity_threshold:
            return self.config.chat_model
        elif complexity < self.config.execution_complexity_threshold:
            return self.config.execution_model
        else:
            return self.config.complex_model
```

---

## 5. CLI Interface

```bash
# Context management
governor context status                    # Show context usage
governor context compact                   # Manually trigger compaction
governor context compact --preview         # Show what would be summarized

# LSP integration
governor lsp status                        # Show LSP server status
governor lsp start <language>              # Start LSP server
governor lsp stop <language>               # Stop LSP server
governor lsp definition <file> <line> <col>  # Go to definition
governor lsp references <file> <line> <col>  # Find references

# Model routing
governor routing config                    # Show routing configuration
governor routing set-chat <model>          # Set chat model
governor routing set-execution <model>     # Set execution model
governor routing estimate <task>           # Show complexity estimate
```

---

## 6. Integration Points

### WebUI

- Context usage indicator (progress bar)
- "Compact now" button
- LSP status in code mode
- Model indicator showing current tier

### VS Code Extension

- LSP integration via existing VSCode LSP clients
- Context indicator in status bar
- Model tier indicator

### Telemetry

- Track compaction events
- Track model tier usage
- Track LSP cache hit rates

---

## 7. Success Criteria

| Criterion | Test |
|-----------|------|
| Auto-compact triggers | Conversation at 80% triggers compact |
| Summary preserves decisions | Decisions in summary match original |
| Recent turns preserved | Last N turns intact after compact |
| LSP definitions work | Go-to-definition returns correct location |
| LSP references work | Find-references returns all usages |
| Task routing works | Simple tasks → cheap, complex → expensive |
| Cost reduction | Measurable reduction in expensive model usage |

---

## 8. Implementation Notes

### What Exists

- `routing.py` — Complexity estimation, model registry
- `telemetry.py` — Event tracking
- `chat_bridge.py` — Backend abstraction

### What Needs Building

| Component | Effort |
|-----------|--------|
| ContextCompactor | Medium |
| Summary generation | Medium |
| LSP client wrapper | Medium |
| LSP tool handlers | Small |
| Task routing extension | Small |
| CLI commands | Small |

Total: ~800-1000 lines of new code.

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2026-02-05 | Initial gap spec |
