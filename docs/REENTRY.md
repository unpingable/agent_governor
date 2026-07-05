# AG Re-entry

> The **admission pointer** for in-flight work, on `main` so a clean checkout finds it.
>
> **Branch existence is not admission.** A branch is work that has a digest, not a verdict —
> local, unpushed, deniable; `main` never has to acknowledge it. This file says where *canonical*
> work lives and what's parked. It hand-authors **only doctrine** (lane pointers, push-order,
> stop lines); detailed branch/commit/status is **derived from git** (commands below) — a
> hand-maintained table is a map that eventually lies, which is the exact remembered-approval
> failure the rest of this repo exists to refuse.
>
> Updated 2026-07-05. `.governor/loop.json` is **stale** (tracks the completed AG-on-AG thread) — use this.

## LIVE THREAD (2026-07-05) — public-MVP campaign

**Canonical:** `docs/campaigns/public-mvp/STATUS.md` (card: `CAMPAIGN.md` same
dir). Sprints 1-4 closed same-day; Sprint 5 (front door + coherence + launch)
in flight. **Push-state note:** everything below tagged `LOCAL` landed on
`origin/main` with the 2026-07-04 merges — verified `0 ahead / 0 behind` on
2026-07-05; those tags are HISTORY of pre-merge commit ids, not a live
disk-SPOF. Operator acts stacked: work-container ratification (memo in the
campaign dir), spine OQ-1..5, site deploy + public mint at S5 exit.

## LANDED 2026-07-04 — both playbook lanes are on main

**Track B (`feat/playbooks-gov-loop`, slices 0–7) and the synthetic conveyor
(`feat/playbooks-synthetic-conveyor`, S1–S7 + H1 + bwrap substrate) merged to
main** (`a803b7b` + `57b383e`; tips preserved as `refs/preserve/playbooks-*`).
Landing ≠ operational promotion — surface classification, receipts, and the
tag-namespace lesson live in
`docs/campaigns/conveyor-dogfood/LANDING.md`. C11/seccomp and H2 remain
unarmed gates; doctrine unchanged (*evidence, never facts; no bounded
autopilot*). The dogfood program consuming the landed law:
`docs/campaigns/conveyor-dogfood/`. The two lane descriptions below are
retained as HISTORY of what the branches carried; the branches are no longer
the canonical residence.

## Canonical lanes (hand-authored: meaning, not state)

- **Track B — governed playbooks** · `feat/playbooks-gov-loop`  *(LANDED on main 2026-07-04 — see above; description retained as history)*
  - Slices 0–7 complete: measurement digests → Wicket admission-as-evidence → governed
    spend → durable/replay-safe spend → self-hosted chore → one-shot ration-card dispatch.
  - **Live-adapter allowlist review gate PASSED (2026-06-29)** — `docs/playbooks/live-adapter-allowlist-review.md`:
    all 11 ration-card terms decided + 4 open questions answered (conservative defaults).
  - Post-review slices landed green (2026-06-29):
    - **B-8** (`94cfd52`) — the allowlist decision doc *is* the slice; no runner code under it.
    - **B-9/10** (`7c88ee2`) — `playbooks/rationed_runner.py`: stub-origin execution contract
      (timeout / kill-before / kill-during / closed result vocab / non-authoritative receipt),
      all via injected fakes. No subprocess, no live origin.
    - **B-11** (`515afb0`) — `playbooks/sandbox_cage.py`: cage contract + honest `NullCage`.
      `evaluate_cage_safety` is safe only when every isolation property is confirmed;
      `admit_origin_under_cage` refuses any non-stub origin under an unconfirmed cage.
  - card: `docs/campaigns/governed-playbooks-track-b/CAMPAIGN.md`
  - **B-12 (live sandbox experiment) was REFRAMED as a decoy gate** (operator, 2026-06-29).
    The real near-term value is not live autonomy; it is *lossless delegation* — offline
    production of reviewable work. Active development moved to a new branch (below). B-12
    stays radioactive: operator-manual, blocked on a real cage backend, not next.
  - **Push state: PUSHED to `515afb0`** (B-8/9-10/11 now on remote, off the disk-SPOF).

- **Synthetic overnight conveyor** · `feat/playbooks-synthetic-conveyor`  *(LANDED on main 2026-07-04 — see top; description retained as history)*
  - Branched off `feat/playbooks-gov-loop` @ `515afb0`. Doctrine: *the overnight system may
    create EVIDENCE, never FACTS* — synthetic/offline work + operator-delayed review, with
    `Synthetic safe ≠ live safe` and live execution kept structurally out of reach.
  - Slices landed green + local (each its own commit; all in `src/governor/playbooks/`):
    - **S1** (`c909e89`) — `rationed_runner.py`: `ORIGIN_SYNTHETIC` first-class no-process
      origin; live still refused (not in `NO_PROCESS_ORIGINS`).
    - **S2** (`a6f8299`) — `sandbox_cage.py`: `SyntheticCage` / `synthetic_only` verdict;
      `safe==True` made *insufficient for live by construction* (verdict `__post_init__`
      makes a synthetic verdict that permits live unconstructable; admission gates on
      `live_admission_permitted`, never `safe`).
    - **S3** (`0d32639`) — `review_packet.py`: inert `ReviewPacket` (evidence, not authority);
      `used <= granted` structural; `operator_review_required` defaults True; deterministic
      serialize + round-trip.
    - **S4** (`5c2f831`) — `playbook_queue.py`: inert queue parser; per-item explicit
      `operator_approved` latch (anti-recursion), fully-closed authority, `review_packet`
      output, static-safe paths. Parser, NOT scheduler.
    - **S5** (`08d3b45`) — `review_packet_validator.py`: pure ReviewPacket-vs-QueuedPlaybook
      cross-validator (identity / authority boundary / path fences / required-test
      representation / review latch); returns a deterministic report, runs nothing.
    - **S6** (`4022f22`, LOCAL) — `handoff_renderer.py`: `QueuedPlaybook` → sealed actor
      handoff. The format becomes a reusable handoff machine: a content-sealed
      (`sha256(canonical_body)`, tamper-evident) bounded instruction for an offline
      Claude/Codex actor whose only licensed output is a ReviewPacket. NO
      authority-permitting surface (all 8 axes prohibited = unrepresentable, not
      guarded); pure renderer (no IO/actor/subprocess/git). `to_prompt_markdown` +
      `to_file_map` (handoff.json + PROMPT.md, strings only).
    - **S7** (`ba11c7e`, LOCAL) — `actor_output_normalizer.py`: actor-output →
      ReviewPacket normalizer (**Model B**, operator-ratified 2026-06-30; contract
      `docs/playbooks/synthetic-conveyor-s7-contract.md`). Inert `ActorOutput`
      (fail-closed parse) + S6 handoff → S3 ReviewPacket (schema unchanged) ready for
      S5. Actor claims are testimony: each required test represented as `not_run`
      (claim → advisory summary) unless an INDEPENDENT verifier receipt covers it, so
      S5's `required_test_not_passing` fires on actor testimony (the actor cannot green
      its own gate); authority claims stripped/refused (kept as risk evidence);
      `operator_review_required` stays True; handoff seal binding preserved + mismatch
      refused. NO live actor (`capture_origin` is descriptive, not a typed origin enum).
  - **The conveyor is a COMPLETE inert "law machine": synthetic origin → synthetic cage
    verdict → review packet → queue parser → queue-vs-review validator → sealed actor
    handoff → actor-output normalizer.** Tests: full playbooks dir 229/229 green;
    full-suite collection clean (16417). End-to-end S4→S6→S7→S5 dogfood: the
    anti-laundering wall held (actor claim stripped, S5 refused).
  - **Fresh-eyes checkpoint DONE (2026-06-30): CLEAN.** Inert S1–S7 conveyor verified;
    the one named seam — `verifier_results` is the sole AG path to a passing test and
    `ActorOutput` has no route to it — became H1's load-bearing invariant.
  - **H1 LANDED (`aa147c8`, LOCAL).** First slice of the external **H-series harness**,
    in a new top-level `harness/` dir **OUTSIDE the governor package** (operator
    placement call: strict no-import; the contract is the `actor_output.v0` JSON
    envelope, not shared Python types). H1 captures a *supplied* offline-actor reply
    into inert JSON; AG ingests it (S7→S5) and **still refuses** an actor-claimed
    passing test (`required_test_not_passing`). No live actor (`captured_text` is
    supplied). 5 AG-side contract tests; harness+playbooks 234 green; collection 16422.
    Ticket: `docs/playbooks/h1-exit-ticket.md`; doctrine: `harness/README.md`.
  - **Bubblewrap backend IMPLEMENTATION slice LANDED (`d4e6115`, LOCAL). NEXT = nothing
    authorized to build; named follow-ups (real C11 seccomp filter · live validation on a
    capable host · H2 impl) are each their own gate. No live actor / runner / H2.**
    `harness/bwrap_cage.py`: `BwrapCage` over `bwrap`, **runs no actor** (only bwrap probe
    commands). `confirms_isolation=True` earned by witnessing: host gate (`assess_host`:
    Linux + bwrap + userns + seccomp + cage smoke) → pre-flight C1–C11 negative-probe
    battery per run → conjunctive mint (`all_required_witnessed`; one missing fact → attest
    nothing) → `admit_live` reuses `evaluate_live_admission`, no second path to True. Per-
    fact `FactWitness` evidence in `CageRunAttestation`, persisted under the tainted audit
    store (`run_dir`, outside AG). **Honest v0:** bwrap can't build a cage in this nested
    sandbox (loopback EPERM) + v0 compiles no seccomp filter → real `BwrapProber` never
    witnesses C11 → real backend **refuses live by construction**; logic proven against an
    injected `FakeProber` (synthetic compatibility, not live testimony). 33 tests; harness+
    playbooks **296 green**; collection 16484. Ticket: `docs/playbooks/bwrap-backend-slice-exit-ticket.md`.
  - **Real cage backend review (bubblewrap) PASSED (`bafd3e5`, LOCAL — operator pass,
    constitution only; the slice above implements it).**
    `docs/playbooks/real-cage-backend-review.md` ratifies what `confirms_isolation=True`
    (`harness/cage.py`) is allowed to MEAN. Principle (NLAI on the cage itself): configured
    ≠ contained; the attestation is earned by **witnessing** (negative probes — run the
    forbidden thing, confirm it fails), never by passing `bwrap` flags. Closed conjunctive
    fact set **C1–C11** (no network · pid/ipc/uts/cgroup iso · non-root/no-priv-esc ·
    read-only input · one narrow writable area · no host fs/creds · minimal /dev · clean env
    allowlist · resource+time limits · disposable per-run workspace · **C11 seccomp profile
    active, REQUIRED**; egress fence = C1∧C6∧C8). Witness discipline: **pre-flight self-test
    per run** (bound to that run's attestation), negative probes mandatory, one unwitnessed
    fact → no attestation, unknown → refuse-live. Host: **Linux-only**, bubblewrap + user
    namespaces required, else refuse-live (no Docker/Podman fallback). Evidence: probe
    outputs + bwrap summary + attestation under the XDG audit store, AG never crawls it,
    referenced by digest/run id only. **Necessity-not-sufficiency:** a passing battery may
    permit `require_live_admission` for that run but does NOT authorize H2 impl; cage
    attestation is necessary for live execution, not sufficient to admit actor output as
    verified work.
  - **H2 live-run CONTRACT review PASSED (`ce71af6`, LOCAL — operator pass, shape only).**
    H2 implementation is gated on a real cage backend (the review just above). NOT H2
    execution.
    `docs/playbooks/h2-live-run-contract-review.md` — the smallest one-shot actor
    invocation contract (spec, not code), all 8 rows ratified + 4 invariants confirmed.
    Decisions: (1) first actor kind = smallest **inert** `offline_echo_actor` (text-only;
    NO repo/git/doctrine/network/verifier/patch; not claude/codex — adding the kind is the
    future impl gate); (2) `timeout_s=30`, hard max 60, timeout→captured refusal/no
    artifact, never verifier results; (3) future `run_once_under_cage` lives in
    `harness/run.py`, harness lane only, never AG/`runtime.adapters.claude_code`; (4)
    arming = **both** `armed_live=True` AND `require_live_admission`, neither sufficient
    alone (`armed_live` is a second key, never a substitute — a lone `--armed-live` must
    never admit live; unreachable with shipped cages); (5) I-1 hard confirmed — **H2 ≠
    operational** (stays `DemonstratedConsumed`; `confer_operational_effect` refused).
    **No runner / actor run / execution method built.** Gate stack (all gated, in order):
    real cage backend (bubblewrap, **constitution PASSED + impl slice LANDED `d4e6115`;
    real backend refuses live in v0**) → H2 contract (PASSED shape-only) → H2 implementation
    (UNBUILT) → operational effect (separate, even later).
  - **Substrate-validation gate PASSED + branch-3 discharged (2026-07-01, branch
    `feat/playbooks-synthetic-conveyor`).** Fenced evidence-only entrypoint
    `harness/validate_bwrap_substrate.py` LANDED (`62cee85`, PUSHED): runs the existing
    backend's battery on a real host, declares substrate facts + probe transcript, writes ONE
    tainted audit record, refuses live by construction (raises on any `confirms_isolation=True`).
    Review `docs/playbooks/next-gate-selection-review.md` (PROPOSED→PASSED w/ amendments).
    **First real capable-host run** (local Ubuntu 24.04 KVM VM — this CC env + mini/NAS/crow/
    linode all unsupported/unavailable/off-limits) **found a C5 containment gap the FakeProber
    had masked**: bwrap's root `/` is a writable tmpfs → two writable areas, violating "exactly
    one narrow writable area" (`capable-vm-noble-001`, sha256 `1c074dd0…`, outcome
    `refused_incomplete_substrate`). **C5 fixed** by sealing the root (`--remount-ro /`,
    `b765e9e`; C5 not weakened — config corrected). **Second run witnessed C1–C10 on real
    bwrap**, C11 unavailable, `confirms_isolation=False`, `live_admission=False`, outcome
    `successful_refusal_partial_substrate_evidence` (`capable-vm-noble-002`, sha256
    `c8a18021…`). Finding doc `docs/playbooks/capable-vm-substrate-finding.md`; records preserved
    under `~/git/porter/outputs/ag-bwrap-substrate/` (tainted, AG-never-ingested). Full harness
    suite 82 green. **Push state: finding/fix/clean-doc/digest commits (`000eccd b765e9e 64e098a`
    +1) LOCAL/unpushed on the branch.** **UNARMED, each its own separate gate: C11/seccomp
    (design not opened), H2 implementation, operational effect, and Porter extraction.**
  - **Prior gates (this lane):** cage-DESIGN slice LANDED `179de67` (`harness/cage.py`:
    contract-first `RefusingCage`/`NoLiveCage`, refuse-live by attestation, XDG audit
    store outside AG, one-artifact `assert_ag_ingestible`, 29 tests); harness-cage review
    **PASSED** (`docs/playbooks/harness-cage-review.md`); in-AG live-adapter review
    **SUPERSEDED** (fossil: `docs/playbooks/live-adapter-allowlist-review.md`). H1 = the
    external harness producing inert `actor_output.v0`. AG is the courthouse, not the
    getaway car.
  - **Push state: S1–S5 PUSHED (2026-06-29); S6 `4022f22` + S7 `ba11c7e` + S7-contract
    `d8f847c`/`75caa28` + H1 `aa147c8` + supersession/harness-cage `69528bf` +
    cage-pass `3406882` + cage-slice `179de67` + H2-contract-review `be00c63` +
    H2-contract-pass `ce71af6` + real-cage-backend-review `0e36635` +
    real-cage-backend-pass `bafd3e5` + bwrap-backend-slice `d4e6115` LOCAL
    (13 unpushed — disk-SPOF until pushed).**
  - Re-entry probe: `git log --oneline feat/playbooks-gov-loop..feat/playbooks-synthetic-conveyor`
    should show S1–S7, H1, cage slice, the review/pass chain, then the bwrap slice
    (`c909e89 … 0e36635 bafd3e5 d4e6115`);
    `pytest tests/playbooks tests/harness -q` green (296).

- **Local candidate worker + cargo-triage** · `feat/local-candidate-worker`  *(live-validated, PUSHED)*
  - Off `feat/playbooks-gov-loop` @ `515afb0`. Budget valve: a cheap LOCAL model (Ollama/Qwen on
    the mini) does first-pass triage so the frontier isn't spent reading slop. *"Local output is
    cheap testimony, never standing."*
  - **Slice 0** (`960c6ed`) — `src/governor/local_candidate.py`: `triage_failure` over
    `ModelTier.LOCAL` via `chat_bridge.OllamaBackend`; structured candidate receipt
    (`verdict=observe`, fails `is_authority_admission_receipt`); hard-refuses authority claims
    (`tests_pass` / `safe_to_commit` / …). Reuses `ration_card.RationCard` (all-closed) as the
    fence — NO new origin enum, NO spend chain, NO repo write. Live seam `ollama_candidate_client`.
  - **A/B (live, qwen2.5-coder:7b on the mini):** Python 21/21 schema-valid, ~18/21 useful, 0
    authority escapes, 0 mutations; **Rust 8/8** (better `failure_kind` accuracy). **`failure_triage`
    RATIFIED to the allowed-local lane (operator, 2026-06-29).** Caveat: `failure_kind` unreliable
    for Python runtime errors. Results `working/local-candidate-ab-results.md`; runbook + verified
    gotchas (wake mini; homebrew ollama needs its `llama-server` runner; models wrap JSON ~1/3 →
    worker extracts the object) `working/local-candidate-worker-ab-runbook.md`.
  - **cargo-triage Slice 0** (`a8abb81`) — `src/governor/cargo_triage.py`: generic, on-prem,
    frontier-free driver (run cargo → capture env → split rustc diagnostics → triage each via the
    ratified worker → candidate receipts). For the SECRET NQ mac-port: run it locally; build output
    never touches the frontier.
  - **NQ-on-mac live run DONE (2026-06-30, fork 1).** The shipped `triage_cargo_project`
    ran entirely on the mini against the SECRET NQ mac port, frontier-free. Result: **the
    port is GREEN** — `cargo check`/`test` both exit 0, 359 passed / 0 failed across 14
    binaries, 129 crates compiled fresh (rustc 1.96.0, aarch64-apple-darwin). Validated the
    SECRET/local custody path (full transcripts stayed on the mini; frontier saw only
    sanitized aggregate; exit read from `subprocess.returncode`, no `|tail`; every receipt
    observe-verdict; no repo mutation except cargo `target/`). The harness emitted ZERO
    diagnostics rather than inventing work. Results: `working/cargo-triage-nq-live-run-results.md`
    (`d9bb5cb` on `feat/local-candidate-worker`, LOCAL). Reproduce: bundle+venv armed on the
    mini at `~/nq_triage_run/`.
  - **Slice 1 `platform_specificity` PARKED** (operator, 2026-06-30): designing the enum
    (mac_only|rust_version|dependency|environment|unknown) after a clean run is fake
    precision. Unpark on **natural** breakage or a relevant historical broken commit — not
    manufactured breakage. Synthetic Rust A/B already proved the worker reads rustc failures.
  - **Push state: Slice 0 PUSHED; results note `d9bb5cb` LOCAL (unpushed).**

- **Track A — transition kernel** · `feat/transition-kernel-slice-1b`
  - Slice 1b complete (Standing grant-use client + `activation.py` Office 2).
  - card: `docs/campaigns/transition-kernel-pickup/STATUS.md`
  - Standing dependency **SATISFIED** (`~/git/standing` `1e62ba9`, `f101c55` are on their remote);
    Track A is pushed and coherent.
  - STOP: supervisor hot-path pickup parked (no forcing case).

- **Constellation records** · `docs/constellation-records`
  - non-binding: `docs/doctrine/borrow-ledger.md` + `specs/gaps/GOV_GAP_OBSERVATION_CONTRACTS_001.md`.
  - **STOP: records authorize nothing.**

`main` is clean and is **not** the source of truth for in-flight work — these branches are.

## Regenerate the branch view (derive; never trust a hand-written table)

```
git for-each-ref --sort=-committerdate --format='%(refname:short)  %(objectname:short)  %(contents:subject)' refs/heads
git log --oneline --decorate --graph --all -n 40
```

## The rule

```
Branch         = storage      (a digest, NOT admission)
Push           = remote witness
REENTRY (main) = admission pointer (where canonical work lives)
Merge to main  = canonical landing
```

Canonicity is explicit *here*, never inferred from a branch name. Anything not pushed lives only
on this disk — push is the witness step.

> Maintenance rule: when branch topology changes (create / merge / delete / supersede a canonical
> lane), update the hand-authored block above in the same turn. Do **not** grow the derived part.
