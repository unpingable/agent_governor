# Governor Skills for OpenAI Codex

Policy enforcement and receipt-producing governance for Codex workflows.

## Quick Start

Copy the skill and config into your project:

```bash
# Copy skill
cp -r .agents/ /your/project/.agents/

# Copy config
cp -r .codex/ /your/project/.codex/

# Copy AGENTS.md (or merge with existing)
cp AGENTS.md /your/project/AGENTS.md

# Install governor and initialize
pip install -e /path/to/agent_gov
cd /your/project
governor init
```

Then use Codex normally. The skill teaches Codex to call governor before
risky actions and after material changes.

## Architecture

Codex does not have Claude-style plugin bundles. Instead:

| Component | What it does |
|-----------|-------------|
| `AGENTS.md` | Ambient contract — "this repo uses governor" |
| `.agents/skills/governor/SKILL.md` | Workflow discipline — when to check/receipt/verify |
| `.codex/config.toml` | MCP server wiring + sandbox + approval policy |
| Codex rules (user/team config) | Coarse shell blocking (`rm -rf`, `git push`) |

**Ownership boundary:** Codex rules own coarse shell bans. Governor owns
rich adjudication, receipts, and appeal state.

## What This Does NOT Do

Codex does not have documented PreToolUse/PostToolUse hooks like Claude Code.
Enforcement relies on:

1. Skill instructions (Codex follows them reliably)
2. MCP tool availability (governor can deny via tool responses)
3. Codex rules (hard shell blocking)
4. Approval policy (human confirmation for side effects)

This is "governed by convention + MCP" rather than "governed by hook enforcement."
For hard enforcement, use the Claude Code plugin.

## License

Apache-2.0
