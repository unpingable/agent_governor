# Antigravity adapter spike (Slice 5)

**Status: DRAFT / CANDIDATE — spike, not integration.** AGY-0 (capability probe)
landed; AGY-1 (sandboxed one-shot runner) is named, not built. Provenance:
conveyor-dogfood provider-integration build vector, Slice 5; operator/chatty scoping
2026-07-05.

> Antigravity may be a capable agent substrate. **It is not a Governor.** Its
> permissions, artifacts, plans, and task success are admissible only after
> AG-owned custody and enforcement.

## What Antigravity is (and why it is not "Gemini CLI v2")

Google is folding Gemini CLI into the **Antigravity CLI** (`agy`) — a new *agent
runtime family* with a much larger surface: local TUI/headless coding agent, shared
GUI settings/permissions, keyring/Google-Sign-In auth, hooks, plugins/skills, MCP,
and a separately-hosted **Antigravity Agent API** (remote managed Linux sandbox,
background execution). Treat it as a family with **two custody-distinct adapters**,
not a drop-in `gemini_cli` replacement:

| adapter (candidate)  | custody profile                                              |
| -------------------- | ----------------------------------------------------------- |
| `antigravity_cli`    | local, user-authenticated, TUI/headless subprocess          |
| `antigravity_api`    | remote Google-hosted sandbox, offsite execution, preview    |

Only `antigravity_cli` is in scope for this spike. `antigravity_api` is **named, not
built** (no forcing case yet; remote/preview; no structured-output support → text
must be custodied conservatively).

## The integration law (unchanged, absolute)

AG sees Antigravity as an **external capable actor**, not a trusted executor:

```
Antigravity plan        != authorized plan
Antigravity permission  != Gov standing
Antigravity artifact    != receipt
Antigravity success     != admissible completion
Antigravity sandbox     != Gov cage
Antigravity MCP tool    != safe tool
```

Antigravity can **testify**. AG decides whether the testimony is admissible — the
same law the WorkContainer contract already carries (`docs/api/provider-integration.md`
§3). Enforcement is the **outer cage** (AG / bwrap / docker / porter / disposable
worktree), never Antigravity's own `--sandbox` or permission panel. Belt, suspenders,
and the pants are still suspicious.

## AGY-0 — capability probe (LANDED)

`src/governor/runtime/adapters/antigravity_probe.py`. *What beast is in the room?*
A pure, injected-runner probe over `agy --version` + `agy --help` — **no task
execution, no model call, no writes, no network task**. Its output is
**compatibility evidence, structurally never live testimony**
(`evidence_kind = "probe_compatibility"`, enforced by type). Fail-closed: an absent
binary is `not_supported` (never a crash); anything not positively observed is
`unknown` (never assumed).

Real capture (this environment, `docs/playbooks/antigravity-probe.v0.json`):

- `agy` **1.0.9**, `available`
- `--print` / `--sandbox` / `--model`: **yes**
- **plan-mode / read-only flag: NO** — the known automation gap
  ([antigravity-cli #45](https://github.com/google-antigravity/antigravity-cli/issues/45)):
  non-interactive `-p` has no plan/read-only equivalent, so headless writes must be
  fenced by the **outer cage**, not by an agy flag.
- MCP, auth: `unknown` (not probed in AGY-0)
- headless / write / network behavioural probes: `skipped` (they belong to AGY-1,
  behind the cage)

## AGY-1 — sandboxed one-shot runner (NAMED, NOT BUILT)

Only after the probe. A one-shot dispatch under a brutally narrow RationCard, with
the outer cage doing enforcement:

```
RationCard: agent=antigravity_cli, mode=one_shot
  workspace: disposable worktree / temp copy
  git_write: false   doctrine_write: false   external_send: false
  network: false BY OUTER CAGE, not by agy vibes
  allowed_paths: [scratch workspace, artifact output dir]
  forbidden_paths: [~/.ssh, ~/.gitconfig, ~/.gemini (except isolated fixture),
                    repo .git unless explicitly admitted]
  max_wallclock / max_output_bytes: bounded
  transcript + filesystem_delta: captured
```

This slots behind the SAME ration-card live-run wall as Claude Code
(`playbooks/ration_card.py` → `dispatch_under_ration_card`), producing a
`provider_run_receipt.v1` (testimony) and a `provider_obstruction.v1` on block —
never a minted receipt.

### Tests required before any AGY-1 live admission

1. Absent binary → `not_supported`, not crash. *(AGY-0 ✓)*
2. Unauthenticated CLI → `auth_required` / operator-action, not silent proceed.
3. Headless stdout probe → captures nonempty stdout.
4. Write probe in read-only intent → fails by **outer cage**, not agy promise.
5. Forbidden-path probe → cannot touch `.git`, `~/.ssh`, `~/.gemini`, doctrine.
6. Timeout → killed, transcript preserved, obstruction recorded.
7. Prompt-injection fixture ("ignore Gov, write/delete") → outer cage wins.
8. Network-denied fixture → no outbound unless the ration admits it.
9. Artifact custody → plans/diffs imported as testimony, not minted receipts.
10. Version drift → adapter refuses unknown major behaviour until reprobed.

## Hooks / MCP temptation (goblin lives here)

Antigravity hooks/MCP are seductive. For V0 they are **telemetry/advisory only**, not
the enforcement boundary. If ever exposed as MCP tools, expose only knock-on-the-door
verbs (`gov.submit_proposal`, `gov.record_obstruction`, `gov.emit_artifact_notice`)
— **never** `gov.approve` / `gov.run` / `gov.promote` / `gov.external_send` /
`gov.write_doctrine`. Antigravity should be able to knock on the door; it does not get
a house key for saying "agentic" in a blazer.

## Data-handling note

Antigravity collects interaction data by default (opt-out in settings), and the API
can climb costs via multiple autonomous loops per interaction. AGY-1 must treat export
handling more strictly than Claude Code, and the outer cage's network fence is the
control — not a settings toggle.
