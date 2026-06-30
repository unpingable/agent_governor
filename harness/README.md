# `harness/` — H-series external actor harness (OUTSIDE AG)

> **H1 may run the actor; AG may only ingest the captured artifact.**

This directory is deliberately **not** part of the governor package
(`src/governor/`). It is the *foreign producer* in the synthetic overnight conveyor:
the thing that runs an offline Claude/Codex actor and captures what it said into an
inert `actor_output.v0` JSON artifact. AG (the courthouse) then ingests that JSON
through the existing S7 normalizer → S5 validator and refuses anything the actor
merely *claimed*.

```
S4 queue → S6 render_handoff → handoff.json
                                   │
            ┌──────────────────────┴─────────────────────────┐
            │  OUTSIDE AG:  harness/  (this dir, "H1")         │
            │  runs the actor, captures the reply             │
            │  emits  actor_output.v0.json   (testimony only) │
            └──────────────────────┬─────────────────────────┘
                                   │   the wall is a JSON file
                                   ▼
        AG ingests:  ActorOutput.from_dict → S7 normalize → S5 validate
        result:  actor-claimed passing tests STILL fail required_test_not_passing
```

## The treaty this enforces

```
actor execution ≠ AG execution
captured output ≠ verifier receipt
claimed pass    ≠ passed test
offline harness ≠ live adapter
```

## Hard invariants (enforced by `tests/harness/test_h1_contract.py`)

1. **No import of AG.** Nothing under `harness/` may `import governor` (or S5 / S7 /
   ration-card / admission / validator internals). The contract between H1 and AG is
   the **JSON envelope**, redeclared here on purpose — not shared Python types. An AST
   scan fails the build if the dependency arrow ever points into AG.
2. **Testimony only.** H1 emits **only** `actor_output.v0`. It has no code path that
   produces a `ReviewTestResult`, `verifier_results`, a verifier receipt, an admission
   receipt, or anything that can satisfy S5. `claimed_test_results` are the actor's
   *claims*; AG (Model B) represents them as `not_run`, and only an **AG-owned
   independent verifier** can ever make a required test `passed`.
3. **No live effect (this slice).** No live actor is spawned, no patch applied, no git,
   network, or subprocess against the actor. `captured_text` is *supplied* — the
   "capture" is structuring a provided reply. Live execution is a later, explicit
   H-series slice gated behind the live-adapter allowlist review.

## What it is NOT (and must not become here)

- Not a live Claude Code adapter; no `runtime.adapters.claude_code` execution.
- Not a bounded autopilot loop; not a sandbox executor.
- No new origin enum; no new ration-card type. `capture_origin` is a **descriptive
  string**, never a typed origin that gates admission.

## Usage

```bash
# Emit the canned laundering specimen (actor claims its test passed):
python3 -m harness.actor_harness --sample --out actor_output.v0.json

# Capture a real offline reply against an S6 handoff:
python3 -m harness.actor_harness \
    --handoff handoff.json \
    --captured-text-file actor_reply.txt \
    --out actor_output.v0.json
```

The emitted JSON is what you hand to AG. AG re-parses it with its own
`ActorOutput.from_dict`; if the wire shape ever drifts, that parse fails loudly —
which is the intended drift control, not shared types.

## The cage (`harness/cage.py`) — contract-first, refuse-live

The cage-design slice (harness-cage review, operator pass 2026-06-30) defines the cage
**contract** and ships exactly one backend — `RefusingCage` / `NoLiveCage` — that
**always refuses live actor admission**. There is **no execution surface**: admission is
a *decision*, never an invocation. Running a live actor is H2, a separate later gate.

- **Refuse-live by attestation.** A cage admits a live actor only if its attestation
  *confirms isolation* in *live* scope. `RefusingCage` attests nothing, so live is
  refused — typed (`LiveAdmission.refusal_code`, or the raising `require_live_admission`).
  No shipped backend attests live isolation, so live admission is structurally unreachable
  (`evaluate_live_admission` is the pure guard; `CageAttestation.__post_init__` forbids a
  half-confirmed cage). bubblewrap is the *named, not authorized* first real backend.
- **Audit store, outside AG.** `audit_store_root()` →
  `$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback `~/.local/state/...`); `run_dir(id)`
  is a per-run dir under it. Pure path computation — writes nothing. Tainted transcripts
  live here, never in the repo, never in AG's ingest path; AG must not crawl it.
- **One-artifact boundary.** `assert_ag_ingestible()` refuses anything but
  `actor_output.v0` — no diff reference, no verifier result, no auxiliary bundle.

## The one seam to guard going forward

The single path that turns a required test `passed` on the AG side is
`normalize_actor_output_to_review_packet(..., verifier_results=...)`. Today it is
sealed because **`ActorOutput` has no route to `verifier_results`** — H1 cannot reach
it. Keep it that way: H1 must never produce `ReviewTestResult` / verifier results, and
AG must never feed actor claims in as verifier results. If a future H-series slice
needs verified tests, the verifier runs **inside AG**, independently — not here.
