# Decisions — governed shell

## Ratified (operator, 2026-07-02, via design review)

### D-GS-1 — queue-first home focus
When maude opens with pending decisions, focus lands on the top queue item
(obligations before ambitions — a stale blocking intervention is a paused
agent burning wall-clock). `Tab` flips to the command line.

### D-GS-2 — chat cut from maude v3
Maude 3.0 is purely the session control plane. The PLAN/BUILD spec-lock
paradigm is removed; its soul relocates: "lock understanding before acting" →
AG admissibility questions at launch; "plan first" → autopilot profile
property. A chat lane may return later if missed — new record required.

### D-GS-3 — lane registry for new lanes only
Phosphor's LaneSpec registry is instantiated by the governed-session lane
(and later ops-casework). Existing fiction/code/research modes convert in a
later separable slice — the 4,493-line adapter.py unwind is real but not this
campaign's fight.

### D-GS-4 — AG-minted widening offers PARKED
v0 autonomy widening is operator-initiated only (`scope.escalate`, existing,
receipted, time-boxed — zero daemon work). The precedent→offer generator
(docket accumulation → "widen for 7d?" queue items) is a successor-campaign
sandwich with its own forcing case. Standing rule regardless: **offers are
AG-minted, never shell-synthesized** — a shell that decides what widening to
offer has become an authority source.

### D-GS-5 — boundary assignments (from design, operator-reviewed)
Adapters stay AG (below the authority gate; refutes the "maude owns provider
adapters" external framing). `decisions.resolve` is the ONE mutation door for
rulings/answers (docket + admissibility get read RPCs only). The watch stream
is a lossy accelerant — EventBus JSONL remains canonical, resume via
since_seq. Promotion auto-approve and mid-session budget mutation are refused
permanently (see CAMPAIGN Forbidden).

## Open

### D-GS-6 — `ag_shell_client` naming  **(OPEN, low stakes — decide by GS-8 review)**
Working name adopted. "libmaude" is retired by the boundary law (the library
is AG's mouth, not maude's guts). Operator may rename at GS-8; the contract
doc name (`shell-contract`) is independent.

### D-GS-7 — session reattach after daemon restart  **(OPEN — VERIFY FIRST)**
`resume_session` (supervisor.py:1259) is pause→resume only; RuntimeFacet's
docstring promises reconstruction from adapter + event store, but no reattach
path exists. Question: is reattach a supervisor gap (build) or intentionally
absent (kill+fork is the recovery)? A verify-first probe belongs at the top of
any slice that would depend on morning-after reattach. Not P0 — the desk works
without it (sessions that died with the daemon render as exited).

### D-GS-8 — R-MAUDE-2 narrowed  **(supersession note)**
`docs/roadmaps/tools/maude.md` R-MAUDE-2 ("resync old client to current
daemon") is narrowed by this campaign: full resync of the hand-rolled client
is dead work once GS-9 replaces it with `ag_shell_client`. R-MAUDE-1 (surface
diff) remains useful as GS-9 input evidence. maude.md updated accordingly.
