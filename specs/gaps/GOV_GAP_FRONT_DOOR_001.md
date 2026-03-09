# GOV_GAP_FRONT_DOOR_001 — Front Door Pass (PyPI Readiness)

**Status:** `shipped` (v2.x — no new subsystems, staging + packaging only)
**Track:** Distribution / onboarding
**Depends on:** nothing (all required subsystems exist)

---

## Problem

Governor is infrastructure-mature but not product-mature. A stranger cannot
`pip install agent-governor`, run one command, get one understandable result,
and know what to do next.

This is not a missing-feature problem. It's a **narrative and sequencing**
problem. The system assumes repo intimacy: familiarity with the daemon, the
state model, the claim/receipt vocabulary. None of that is required for the
first interaction to be coherent — it just hasn't been staged yet.

## The Gate

One test determines readiness:

> Can a stranger install it, run one obvious command, get one understandable
> result, and know what to do next?

When this passes, PyPI stops being premature and starts being distribution.

## What This Is

A **front door pass**: four deliverables that make governor installable and
first-run-coherent for someone who has never seen the repo. No new subsystems,
no architecture changes, no docs rewrite.

## What This Is NOT

- Not a docs overhaul (README stays as-is, just better first-run output)
- Not an architecture rethink
- Not a daemon unification
- Not a new abstraction layer
- Not a wizard
- Not "maybe we should redesign the whole house"

The welcome mat does not need Kubernetes.

---

## Deliverables

### 1. Post-init epilogue

`governor init` currently creates `.governor/` silently. After init, print:

```
Created .governor/ with:
  facts/       — tracked claims about your project state
  decisions/   — saved policy choices and judgments
  receipts/    — verification records from governor runs

Next:
  governor gate check "The tests pass and the code is safe."
```

**Scope:** CLI output only. No new flags, no interactive prompts.
Just tell the stranger what happened and what to do next.
Keep the copy concrete — minute one is not the time for ontology.

### 2. One golden path (no daemon required)

The golden path command is `governor gate check`. It already exists, works
without the daemon, and produces a visible receipt. The gap is that a stranger
doesn't know it exists or what to do with the output.

Requirements:
- `governor gate check <text>` works immediately after `governor init`
- Output includes the receipt ID and a one-line explanation of the verdict
- No daemon, no hooks, no prior configuration required
- The init epilogue points here

If `gate check` output is currently too terse or too noisy for a first-time
user, adjust the default (non-`--json`) output to be human-legible:

```
Verdict: pass
Claims:  2 extracted (1 assertive, 1 hedged)
Receipt: sha256:a1b2c3...

Run `governor gate check --help` for options.
```

### 3. Standalone CLI autonomy

Classify all CLI commands into three buckets. Fix only the core-path
blockers now — everything else gets labeled for later.

**Core path (must work standalone — fix if broken):**
- `governor init`
- `governor gate check`
- `governor receipts`
- `governor facts` / `governor decisions`
- `governor hook install`

**Classification buckets for everything else:**
- `standalone` — works without daemon
- `daemon-required` — needs `governor serve`
- `unclear / follow-up` — needs investigation later

The daemon is an advanced mode for multi-agent coordination, session
management, and WebUI integration. It is not a prerequisite for single-user
governance.

**Deliverable:** classify commands, fix core-path blockers only. If a
core-path command silently fails without the daemon, fix it or error
clearly. Do not turn this into a daemon decoupling project.

### 4. Packaging for `pipx install`

Add `[project.scripts]` entry point to `pyproject.toml`:

```toml
[project.scripts]
governor = "governor.cli:main"
```

Ship only `governor` for now. The domain-specific CLIs (`fiction-gov`,
`nonfiction-gov`, `ops-gov`) can be added later once they've earned their
own front door. One entry point keeps the install legible — four doors
and hoping one looks welcoming is not a strategy.

Verify:
- `pipx install .` from repo root works
- `governor init && governor gate check "hello"` works from the installed path
- Entry point resolves correctly (Click group, not raw function)

**Do not publish to PyPI yet.** This deliverable proves the packaging works.
Publication is a separate decision after the other three deliverables land.

### 5. Golden path smoke test

Add a CI smoke test that exercises the exact stranger path:

```bash
pip install .                    # or pipx install .
governor init
governor gate check "hello"
```

Assert:
- `init` exits 0, `.governor/` exists
- `gate check` exits 0, output contains verdict + receipt ID
- Output is human-readable (not raw JSON unless `--json` flag)

This prevents the front door from regressing when someone refactors the CLI.
Can reuse or extend the existing `@smoke` marker in `test_fresh_clone.py`.

---

## Explicit Non-Goals

| Temptation | Why not |
|-----------|---------|
| Guided wizard / interactive setup | Overengineered for "run one command" |
| `governor quickstart` command | The golden path IS the quickstart |
| Onboarding tutorial in CLI | That's docs, not product |
| Daemon auto-start | Complexity; standalone must work first |
| New subsystems | The system is complete; this is staging |
| Dependency changes | Stdlib-only is a feature |

## Risks

1. **Scope creep.** "Welcome mat" metastasizes into "redesign the house."
   Mitigation: four deliverables, nothing else. If it's not on the list,
   it's not in scope.

2. **Bikeshedding output format.** The epilogue and gate check output could
   be debated forever. Pick something, ship it, iterate if anyone complains.

3. **Hidden daemon coupling.** Some CLI commands may silently assume daemon
   state. The audit (deliverable 3) may surface surprises. Fix or document,
   don't redesign.

## Success Criteria

A fresh virtualenv. No prior repo clone. No docs read.

```bash
pipx install agent-governor
governor init
governor gate check "The tests pass and the code is safe."
```

The user sees:
1. What `init` created
2. What command to run next
3. A verdict, claim count, and receipt ID
4. Where to go from here

Total elapsed time from install to "I understand what this does": under 2
minutes.

---

## Sequencing

This can ship as a single PR. No phasing required — the deliverables are
independent and small. The only ordering constraint: deliverable 4 should be
verified after 1-3 land (so the installed path exercises the improved output).

After this ships, the PyPI publication decision is a separate, non-technical
conversation about whether the social contract of a public package is worth
accepting.
