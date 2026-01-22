# Integration Ideas: Making the Governor Actually Govern

The governor is built. Now: how do we actually put it in the path of agent file writes?

---

## 1. Claude Code Hook Integration

Claude Code supports hooks that run before/after tool calls. A pre-response hook could intercept file writes.

### Approach A: User-Space Hook (Works Today)

```bash
# ~/.config/claude-code/hooks/pre-write.sh
#!/bin/bash
# Intercept file write attempts

FILE_PATH="$1"
CONTENT="$2"

# Check if governor is initialized
if [ -d ".governor" ]; then
    # Create a proposal for this write
    PROPOSAL_ID=$(governor propose --claim "type=file_exists,path=$FILE_PATH" --json | jq -r '.proposal_id')

    # Verify it
    RESULT=$(governor verify "$PROPOSAL_ID" --json)

    if [ "$(echo $RESULT | jq -r '.status')" != "verified" ]; then
        echo "Governor rejected write to $FILE_PATH"
        echo "$RESULT" | jq '.rejection'
        exit 1
    fi
fi
```

**Limitation**: Claude Code doesn't currently expose file write content to hooks before write happens. Would need Claude Code to add this.

### Approach B: Claude Code Feature Request

Request from Anthropic:
- `pre-file-write` hook that receives (path, content) and can return (approve/reject)
- Hook runs BEFORE the write happens
- If rejected, Claude Code shows the rejection reason and doesn't write

### Approach C: Wrapper Mode (Works Today)

```bash
# Instead of running claude-code directly:
governor wrap -- claude-code

# The wrapper:
# 1. Takes a snapshot of the directory
# 2. Runs claude-code
# 3. Detects what files changed
# 4. For each change, creates a proposal
# 5. If any proposal fails verification, rolls back ALL changes
```

This is what we built in `wrapper.py`. Downside: it's post-hoc, not preventive.

---

## 2. Agent SDK Middleware

For developers building agents with the Anthropic SDK (Python/TypeScript), provide middleware that intercepts tool calls.

### Python SDK Integration

```python
from anthropic import Anthropic
from governor.sdk import GovernorMiddleware

client = Anthropic()
governor = GovernorMiddleware(project_root=".")

# Wrap the client
governed_client = governor.wrap(client)

# Now all tool calls go through governor
response = governed_client.messages.create(
    model="claude-sonnet-4-20250514",
    tools=[...],
    messages=[...]
)

# If agent tries to use a file-write tool without a verified proposal,
# the middleware intercepts and either:
# - Auto-creates a proposal and verifies it (exploratory mode)
# - Rejects the tool call and returns an error to the model (strict mode)
```

### Implementation Sketch

```python
# src/governor/sdk.py

class GovernorMiddleware:
    """Middleware for Anthropic SDK that enforces governor on tool calls."""

    WRITE_TOOLS = {"write_file", "edit_file", "create_file", "str_replace_editor"}

    def __init__(self, project_root: Path, mode: str = "strict"):
        self.root = project_root
        self.gov_dir = project_root / ".governor"
        self.mode = mode

    def wrap(self, client: Anthropic) -> "GovernedClient":
        return GovernedClient(client, self)

    def intercept_tool_use(self, tool_name: str, tool_input: dict) -> tuple[bool, str]:
        """
        Intercept a tool call and check if it should be allowed.

        Returns (allowed, reason).
        """
        if tool_name not in self.WRITE_TOOLS:
            return True, "Not a write operation"

        # Extract path from tool input
        path = tool_input.get("path") or tool_input.get("file_path")
        if not path:
            return False, "Write tool called without path"

        # Check if this path has a verified proposal
        if self._has_approval(path):
            return True, "Path approved by governor"

        if self.mode == "exploratory":
            # Auto-create and verify proposal
            proposal_id = self._auto_propose(path, tool_input)
            if self._auto_verify(proposal_id):
                return True, "Auto-approved in exploratory mode"

        return False, f"No governor approval for write to {path}"

    def _has_approval(self, path: str) -> bool:
        """Check if path has been approved in a recent proposal."""
        # ... check proposals.json for applied proposals covering this path
        pass

    def _auto_propose(self, path: str, tool_input: dict) -> str:
        """Create a proposal automatically from tool input."""
        # ... create proposal with file_exists claim
        pass

    def _auto_verify(self, proposal_id: str) -> bool:
        """Attempt to verify a proposal."""
        # ... run verification
        pass


class GovernedClient:
    """Wrapped Anthropic client that enforces governor."""

    def __init__(self, client: Anthropic, middleware: GovernorMiddleware):
        self._client = client
        self._middleware = middleware

    def messages_create(self, **kwargs):
        # Intercept the response and check tool uses
        response = self._client.messages.create(**kwargs)

        for block in response.content:
            if block.type == "tool_use":
                allowed, reason = self._middleware.intercept_tool_use(
                    block.name,
                    block.input
                )
                if not allowed:
                    # Return a modified response that tells the model it was blocked
                    return self._create_rejection_response(block, reason)

        return response
```

### TypeScript SDK Integration

```typescript
import Anthropic from '@anthropic-ai/sdk';
import { GovernorMiddleware } from 'agent-governor';

const client = new Anthropic();
const governor = new GovernorMiddleware({ projectRoot: '.' });

// Wrap the client
const governedClient = governor.wrap(client);

// Same idea - intercept tool calls
```

---

## 3. MCP Server Integration (Already Built)

The MCP server (`governor mcp serve`) already exposes governor as tools. Claude Desktop can be configured to use it:

```json
// Claude Desktop MCP config
{
  "mcpServers": {
    "governor": {
      "command": "governor",
      "args": ["mcp", "serve"],
      "cwd": "/path/to/project"
    }
  }
}
```

Then Claude can call:
- `governor_propose` - Create proposals
- `governor_verify` - Verify proposals
- `governor_apply` - Apply proposals
- `governor_decisions` - Query what's been decided

**The gap**: Claude has to *choose* to use these tools. It's advisory, not mandatory.

### Making MCP Mandatory

Would require MCP protocol extension or Claude Desktop feature:
- "Required tools" that must be called before certain actions
- Or: Governor MCP server that *also* provides the file-write tools, and only executes them after verification

---

## 4. Git-Based Enforcement (Already Built)

The pre-commit hook (`governor hook install`) enforces at commit time:

```bash
# Any commit with unapproved files is blocked
git commit -m "Add feature"
# COMMIT BLOCKED: Files not approved by governor
#
# Unapproved files:
#   - src/new_feature.py
#
# To commit these changes:
#   1. Create a proposal: governor propose --claim '...'
#   2. Verify it: governor verify <id>
#   3. Apply it: governor apply <id>
```

This is the "last line of defense" - even if the agent bypasses runtime checks, it can't land unapproved changes.

---

## Priority Order

1. **Git hooks** - Already done, works today
2. **Wrapper mode** - Already done, works today (post-hoc)
3. **MCP server** - Already done, but advisory
4. **SDK middleware** - New development, high impact
5. **Claude Code native hook** - Requires Anthropic feature

---

## Open Questions

1. **Granularity**: Should every file write need a proposal, or batch them per "task"?
2. **Auto-approval**: In exploratory mode, should we auto-approve everything that verifies?
3. **Context passing**: How does the agent know what decisions have been made? (We have `governor decisions` but it's not in the prompt automatically)
4. **Undo**: If a proposal is rejected after partial application, how do we rollback cleanly?
