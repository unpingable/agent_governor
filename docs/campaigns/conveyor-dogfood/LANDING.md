# Landing note — playbook conveyor onto main (CD-0, 2026-07-04)

Operator ruling CD-D2: "branches are staging, not jurisprudence" — the dogfood
program may cite only main-line law. **Landing is NOT blanket operational
promotion**; the classification below says what each landed surface IS.

## Ref map

| what | ref | landed as |
|---|---|---|
| `feat/playbooks-gov-loop` tip (slices 0–7) | `515afb0` → preserved `refs/preserve/playbooks-gov-loop` | merge `a803b7b` (landing 1/2) |
| `feat/playbooks-synthetic-conveyor` tip (S1–S7, H1, bwrap; superset of gov-loop) | `b47ee87` → preserved `refs/preserve/playbooks-synthetic-conveyor` | merge `57b383e` (landing 2/2) |

Preservation refs live in `refs/preserve/` (NOT `refs/tags/`): the QA
self-governance suite owns the tag namespace's meaning
(`test_pyproject_version_matches_latest_git_tag` uses
`git describe --tags`) — landing tags briefly broke it; moved to non-tag refs,
test re-verified green. Lesson recorded here so the next landing doesn't
re-step on it.

**The landing was gate-checked twice, and both catches were the gates working
as designed:** the tag-namespace guardrail (above) and the curated-CLI
taxonomy guardrail (below, merge 2). Neither failure was in the landed law
itself — both were seam mismatches between branch-era additions and
main-side discipline that grew after the branch point. This is the expected
shape of a branch tax, and exactly why the ruling requires full-suite
verification after EACH merge.

## Verification receipts

- Merge 1: full suite `[pass]` — verify-run receipt `bb380cbe`
  (`.governor/verify_receipts/landing1_fullsuite.json`), exit_source=child_exit.
  (First run was `[block]` `08070100` — the tag lesson above; fixed, re-run.)
- Merge 2: `tests/playbooks tests/harness` — **311 passed** (grew from the
  REENTRY-era 296 with the later slices), exit 0 bare. First full-suite run
  `[block]` (`d6603d78`): the **curated-CLI gate caught the landed branch's
  `state-index` group** — uncategorized, and defined below
  `_populate_advanced()` so it never dual-registered into the attic. Repaired
  (group relocated above the populate call + ordering constraint NOTE pinned
  in cli.py; `state-index` added to the attic allowlist; both routes
  verified). Final full-suite verify-run receipt: `landing2_fullsuite.json`.
- Ruff: all landed surfaces clean (`src/governor/playbooks/`,
  `state_index_export.py`, `harness/`, tests).
- Branch-era evidence retained: fresh-eyes checkpoint CLEAN (2026-06-30),
  substrate validation PASSED + C5 writable-root gap found and fixed
  (2026-07-01), per-slice codex sandwiches on the branches.

## Surface classification (the load-bearing table)

### Citable substrate (main-line law the dogfood program may cite)

| surface | module | what it is |
|---|---|---|
| PlaybookSpec → CertifiedPlaybook | `playbooks/spec.py`, `certify.py`, `canonical.py`, `digest.py`, `closure.py` | restricted-YAML admission, canonical form, content digests, dependency closure — structural verification, not authority |
| Wicket admission-as-evidence | `playbooks/admission_evidence.py`, `wicket_client.py` | PlaybookAdmissionEvidence; admission is evidence, never execution authorization |
| Durable spend | `playbooks/durable_spend.py` | replay-safe spend intent; unknown-custody poison honored |
| RationCard | `playbooks/ration_card.py` | absence-restrictive allowlists (write paths, shell commands); **locked axes raise on construction**: git=False, doctrine_writes=False, network=False, output_is_observe_only=True |
| QueuedPlaybook | `playbooks/playbook_queue.py` | inert queue parser; per-item `operator_approved` latch; path fences |
| ReviewPacket (+ validator) | `playbooks/review_packet.py`, `review_packet_validator.py` | evidence-not-authority; structural `used ≤ granted`; cross-validation incl. `changed_path_outside_allowed_paths` |
| HandoffRenderer | `playbooks/handoff_renderer.py` | sha256 content-sealed actor handoff; strings only, no IO |
| ActorOutputNormalizer | `playbooks/actor_output_normalizer.py` | actor claims stripped unless an independent verifier receipt covers them — the actor cannot green its own gate |
| ORIGIN_SYNTHETIC + SyntheticCage verdict | `playbooks/sandbox_cage.py` | synthetic-only verdicts; safe ≠ live admission by construction |
| state_index_export | `state_index_export.py` | state-registry Slice 0/1 (`state_index_export.v0`) — specimen 1's base |

### CANDIDATE (landed, not promoted)

- `governed-playbook.v0` schema itself (v0, may change);
- specimen/fixture material in `docs/playbooks/*` exit tickets and reviews;
- `GOV_GAP_STATE_REGISTRY_001` + state-registry backlog stubs (recorded, not
  authorized).

### Inert / disabled (landed as text+contracts; operational gates NOT satisfied)

- **BwrapCage live execution** (`harness/bwrap_cage.py`): probe/evidence
  commands only in v0; refuses live actor execution by construction. C11/
  seccomp is an unarmed, separate gate.
- **H2 live-run contract** (`docs/playbooks/h2-live-run-contract-review.md`):
  shape-only review; NOT implemented.
- **RationedAgentRunner + sandbox cage contracts**: contracts with kill
  semantics; no live agent dispatch is wired to an operational effect surface.
- Doctrine unchanged and binding: *the overnight system may create EVIDENCE,
  never FACTS*; *no bounded autopilot; no promoting sandbox playbooks to
  operational use.*

### Fix-on-touch / known debts (nonblocking)

- `docs/playbooks/live-adapter-allowlist-review.md` exists in both branch
  lineages (gov-loop full + conveyor addendum) — content merged additively;
  normalize on specimen 2 (its exact task).
- REENTRY.md still describes the lanes as branch-resident — updated in this
  landing's docs pass.

## What this landing does NOT do

No new refusal kinds, no daemon RPC changes, no autopilot, no live sandbox
authority, no operational promotion of any conveyor surface. It makes the law
citable from main; every activation remains its own gated slice.
