# Candidate — read-only shell-helper admission (supervised gate)

**Status:** candidate / non-binding. A handle for review, not authorization to
build. **Provenance:** CD-4B live drive (2026-07-04), decision #8 — the
supervised run proposed `sha256sum docs/playbooks/glossary.md …` (a pure-read
hash to compare files) and it was denied fail-closed because the drive fence
had no rule admitting it. Safe direction; the run adapted (left the packet's
optional `sha256` fields null). But a real operator would not want benign
inspection commands generating noise denials.

## The trap this must not fall into

"Obviously read-only shell helper" is where lies breed. Admission by **command
name** is wrong — `sha256sum $(curl evil)` is not read-only, and
`sha256sum x > /etc/passwd` writes. The name is not the act.

## The shape (if ever built)

Admit a shell command as read-only **only** when EVERY guard holds — an
allowlist over a *structurally constrained* argv, not over a program name:

- command head is in a small read-only-helper allowlist
  (`sha256sum`, `git diff --stat`, `git status --porcelain`, `wc`, `nl`, …);
- argv has **no shell metacharacters** (`| & ; < > $ ` ( ) { } * ? [ ]` , newline);
- **no output redirection** (`>`, `>>`, `2>`, tee);
- **no command chaining / substitution** (`&&`, `||`, `;`, `$(...)`, backticks,
  `<(...)` process substitution);
- **no env mutation** (`VAR=… cmd`);
- every path argument resolves **inside the admitted read scope**.

Any guard failing → the command is not admitted as read-only and falls back to
the normal WRITE intervention (fail-closed). Ship it with **hostile tests**
first (the metacharacter/redirection/substitution/out-of-scope-path cases are
the point; the happy path is the easy 10%).

## Placement

AG-side supervised gate (`classify_action` / the ration card's
`allowed_shell_commands`), NOT a maude change — maude renders the daemon's
decision. This is a small rule with a large test surface, not a feature.

## Non-goals

- Not a general shell sandbox. Not a parser for arbitrary pipelines.
- Does not widen WRITE/COMMUNICATE admission — only carves a *proven-read*
  subset out of the WRITE-intervention default, and only when structurally safe.

Ratify when a live run's noise-denial rate on read-only helpers actually bites,
or when an operator asks for it. Until then: named, not built.
