# Synthetic conveyor — H1 exit ticket

**Done 2026-06-30** (branch `feat/playbooks-synthetic-conveyor`). The first slice of
the **H-series external actor harness** — the foreign producer that, in the conveyor,
runs an offline actor and hands AG a captured artifact. H1 lives in a new top-level
`harness/` directory, **outside the governor package**, and crosses the wall to AG as
a JSON file only.

> **H1 may run the actor; AG may only ingest the captured artifact.**

Preceded by a clean fresh-eyes checkpoint of the inert S1–S7 conveyor (no defects;
the one named seam — `verifier_results` is the sole path to a passing test, and
`ActorOutput` has no route to it — became H1's load-bearing invariant).

## Files

- `harness/__init__.py`, `harness/actor_harness.py` (new) — the H1 producer + CLI.
  Stdlib only. **No `import governor`.**
- `harness/README.md` (new) — the boundary doctrine + the seam to guard.
- `tests/harness/test_h1_contract.py` (new, 5 tests) — AG-side contract tests.

Harness + playbooks regression: **234 passed, exit 0**. Full collection 16422, exit 0.

## Placement decision (operator, 2026-06-30)

Top-level `harness/`, **strict no-import**. H1 redeclares the `actor_output.v0` wire
shape itself; the contract is the **JSON envelope, not shared Python types**. Rejected:
importing AG's schema read-only ("points the dependency arrow the wrong way"); a
separate repo ("too much ceremony for H1").

## What H1 is (smallest slice)

A pure producer that structures a *supplied* offline-actor reply into an inert
`actor_output.v0` JSON envelope:

```
{ schema_version, actor_output_id, handoff_packet_id, actor_kind,
  captured_text, captured_at, capture_origin,
  claimed_files_touched, claimed_commands_run,
  claimed_test_results[ {command, claimed_status, exit_code?, summary?} ],
  authority_claims }
```

`capture_from_handoff()` binds the capture to an S6 `handoff.json` (reads only
`handoff_id` + `actor_kind`; does NOT verify the seal — that's AG's job, and
reimplementing the canonicalization would invite drift). CLI:
`python3 -m harness.actor_harness --sample` or `--handoff … --captured-text-file …`.

## The treaty, proven end-to-end

A foreign subprocess emits a capture whose required test is **claimed passed**
(`--sample`, the laundering specimen). AG ingests the JSON with its own
`ActorOutput.from_dict`, normalizes S7 → ReviewPacket, validates S5 — and S5 **still**
refuses with `required_test_not_passing`. The actor's word cannot green its own gate.

```
actor execution ≠ AG execution     captured output ≠ verifier receipt
claimed pass    ≠ passed test       offline harness ≠ live adapter
```

| Invariant | Test |
|-----------|------|
| foreign harness claiming a pass → S5 refuses (`required_test_not_passing`) | `test_h1_sample_subprocess_is_refused_by_s5` |
| H1 binds to a real handoff; AG still refuses | `test_h1_binds_to_handoff_and_is_refused` |
| no module under `harness/` imports `governor` (AST scan) | `test_harness_does_not_import_governor` |
| no verifier-result / admission / receipt-greening identifier in H1 code (AST scan) | `test_harness_has_no_verifier_or_admission_surface` |
| standalone sample emits well-formed wire JSON; claim carried as a *claim* | `test_harness_sample_is_well_formed_wire_json` |

## The seam to guard going forward

The only AG path that makes a required test `passed` is
`normalize_actor_output_to_review_packet(..., verifier_results=...)`. It stays sealed
because `ActorOutput` has no route to `verifier_results` and H1 has no code that
produces a `ReviewTestResult`. If a future H-series slice needs verified tests, the
verifier runs **inside AG**, independently — never in `harness/`.

## Intentionally NOT done (stop line held)

- No live Claude Code adapter; no `runtime.adapters.claude_code` execution; no
  bounded autopilot loop; no sandbox/subprocess executor *of the actor*. (The only
  subprocess is the contract test running H1 itself as a black box.)
- No new origin enum (`capture_origin` is a descriptive string, never gates) and no
  new ration-card type.
- No git / doctrine / network authority; no patch apply; no commit/push by the actor.
- H1 does not run a live actor yet — `captured_text` is supplied. Live execution is a
  later, explicit H-series slice, gated behind the live-adapter allowlist review.

## Next possible slice (do NOT start without operator go)

H2+ remains gated behind the **live-adapter allowlist review**. Live actor execution,
transcript streaming, or any path that lets the harness drive a real Claude/Codex stays
out of reach until that review explicitly authorizes it. AG is the courthouse, not the
getaway car.
