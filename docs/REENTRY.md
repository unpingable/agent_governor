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
> Updated 2026-06-29. `.governor/loop.json` is **stale** (tracks the completed AG-on-AG thread) — use this.

## Canonical lanes (hand-authored: meaning, not state)

- **Track B — governed playbooks** · `feat/playbooks-gov-loop`  *(active lane)*
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

- **Synthetic overnight conveyor** · `feat/playbooks-synthetic-conveyor`  *(ACTIVE lane, 2026-06-29)*
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
  - **H2 live-run CONTRACT review OPENED (`be00c63`, LOCAL, DRAFT — awaiting operator
    pass). NEXT = operator pass on that review. NOT H2 execution.**
    `docs/playbooks/h2-live-run-contract-review.md` defines the smallest one-shot actor
    invocation a FUTURE real cage backend would be allowed to run — a spec, not code.
    Proposed shape `run_once_under_cage(cage, handoff, *, actor_kind, run_id, timeout_s,
    armed_live) -> one actor_output.v0`, gated on `require_live_admission` (every shipped
    cage refuses → unreachable today). Permanent invariants: **H2 ≠ operational** (run
    stays `DemonstratedConsumed`; actor output is testimony; `confer_operational_effect`
    refused), one-invocation/one-artifact, refuse-live-until-attested, cage-is-the-
    containment. Items 6/7 inherited RATIFIED; 1–5/8 PROPOSE; 5 open questions.
    **No runner / actor run / execution method built.** Gate stack (all gated, in order):
    real cage backend (bubblewrap, unbuilt) → H2 contract (this, in review) → H2
    implementation (unbuilt) → operational effect (separate, even later).
  - **Prior gates (this lane):** cage-DESIGN slice LANDED `179de67` (`harness/cage.py`:
    contract-first `RefusingCage`/`NoLiveCage`, refuse-live by attestation, XDG audit
    store outside AG, one-artifact `assert_ag_ingestible`, 29 tests); harness-cage review
    **PASSED** (`docs/playbooks/harness-cage-review.md`); in-AG live-adapter review
    **SUPERSEDED** (fossil: `docs/playbooks/live-adapter-allowlist-review.md`). H1 = the
    external harness producing inert `actor_output.v0`. AG is the courthouse, not the
    getaway car.
  - **Push state: S1–S5 PUSHED (2026-06-29); S6 `4022f22` + S7 `ba11c7e` + S7-contract
    `d8f847c`/`75caa28` + H1 `aa147c8` + supersession/harness-cage `69528bf` +
    cage-pass `3406882` + cage-slice `179de67` + H2-contract-review `be00c63` LOCAL
    (9 unpushed — disk-SPOF until pushed).**
  - Re-entry probe: `git log --oneline feat/playbooks-gov-loop..feat/playbooks-synthetic-conveyor`
    should show S1–S7, H1, cage slice, H2-contract-review (`c909e89 … 179de67 be00c63`);
    `pytest tests/playbooks tests/harness -q` green (263).

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
