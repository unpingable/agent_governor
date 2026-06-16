# Resume point — 2026-06-12 (NQ loop + verifier wrapper session)

Session: AG-Claude drove NQ's *own* governor loop (instantiated from AG's pattern, NQ ops-grammar) through several batches, ratified Standing Conditional Authorization, then built a governor-level verifier wrapper. nq-claude was stood down (impunity granted). Pick up from this table.

## State by artifact

| Work | Repo | Committed? | Pushed? |
|------|------|-----------|---------|
| NQ ecosystem triage + loop standup (`.governor/`, loop-protocol.md, lane survey) | nq | ✅ | ✅ |
| Recovered orphaned UI slice (host-detail + posture-legend) | nq | ✅ `0f35a2c` | ✅ |
| NQ-CLOSE-003 host-trust (shipped) + NQ-CLOSE-002 retention policy (locked, 3wk/6mo confirmed) | nq | ✅ `2892432` | ✅ |
| Scrape-target provenance persistence (migration 058) + honest collision guard | nq | ✅ `1bd5c38` | ✅ |
| Standing Conditional Authorization doctrine + re-survey | nq | ✅ `333da0d` | ✅ |
| SILENCE_UNIFICATION V1 (smart+zfs witness contract) + batch-A masking repair | nq | ✅ `d955578` | ✅ |
| Verification-discipline hardening (exit codes are the verdict) | nq | ✅ `77302ed` | ✅ |
| nq-blackbox smoke harness + provenance precondition closed | nq-blackbox | ✅ `dcb8e66` | ✅ |
| **Governor verifier wrapper** (`verify.py`, `governor verify-run`, tests) | agent_gov | ✅ `d732060` | ❌ **(no push — slice said so)** |
| Global rule: `~/.claude/CLAUDE.md` § Verification discipline | (dotfile) | n/a | n/a |

## Uncommitted loose ends (mine — commit next session in one docs commit)

- `agent_gov/docs/doctrine/briefings_not_cockpits.md` (cross-project UI doctrine)
- `agent_gov/docs/visual_registers.md` (back-ref to briefings)
- `agent_gov/working/GOV_GAP_GOVERNED_SWEEP_PROTOCOL_001.md` (governed periodic-sweep protocol gap — design captured, not built)

**Do NOT touch** (operator's pre-existing uncommitted work, untouched all session): `working/campaign-standing-before-spendability.md`, `working/nightshift-governor-unsettled-integration-state.md`, `working/parked-constellation-alignment-pass.md`, `.tick/tick01-gov/`, `.tick/tick02-gov/`, `working/GOV_GAP_AUTHORIZATION_SHELF_LIFE_001.md`, `working/GOV_GAP_OUT_OF_SCOPE_RUNTIME_LAUNDERING_001.md`, `working/candidate-2026-06-09-nightshift-claim-route.md`, `working/cybernetics-and-admissibility.md`, `working/endgame-synthesis-2026-06-10.md`, `working/next-session-debt-sweep.md`.

## Referred to operator (decisions pending — see NQ docs)

1. **Series-identity migration** (`nq/docs/working/decisions/NQ_SCRAPE_TARGET_IDENTITY_SCOPE.md`) — the irreversible 3-table rebuild. Forcing condition: a second bare-metric scrape target. Plus 2 historical-interpretation decisions (NULL-provenance rows; labels_json as identity).
2. **SILENCE OQ3/OQ4** — the four non-witness silence detectors (stale_host/signal_dropout = liveness vs silence). Deferred; needs ruling or REGISTRY_PROJECTION.
3. **Sweep protocol** (the GOV_GAP above) — design-only gap; build is a separate future authorization.

## Clean next-actions (executable under Standing Conditional Authorization, no fresh approval)

- NQ: DETECTOR_TAXONOMY bucket-2 silence sub-taxonomy doc (2 detectors now carry the contract).
- AG: commit the 3 dangling doc captures above.
- Deploy session (not loop): nq-blackbox Bucket 1 live promotion (harness is ready; needs live exporter + nq-serve).

## Loop state
- NQ loop: idle in AUDIT (`nq/.governor/loop.json`). Receipts under `nq/.governor/loop-receipts/`.
- Key doctrine this session: **Standing Conditional Authorization** (`nq/docs/loop-protocol.md` — operator ratifies classes + admission predicate; loop executes matches until policy/external/irreversibility/ambiguity, then refers) + **Verification discipline** (exit codes are the verdict; `governor verify-run` enforces it).

## The two scars worth remembering
- `cargo test | tail` masks exit codes (pipeline returns tail's status). → global doctrine + `governor verify-run`.
- "Guards have a way of becoming policy wearing a hoodie" — the `!metric_sets.is_empty()` guard is classified as a 058-repair side-effect, not silence policy.
