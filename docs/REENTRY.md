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
  - **Push state:** branch pushed at `19b310f`; **three commits local/unpushed**
    (`94cfd52`, `7c88ee2`, `515afb0`) — operator holds push timing.

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
  - **The branch is a complete inert "law machine": synthetic origin → synthetic cage verdict
    → review packet → queue parser → queue-vs-review validator.** Tests: full playbooks dir
    189/189 green; full-suite collection clean (16377).
  - **NEXT = S6** (handoff renderer: a `QueuedPlaybook` → sealed Claude/Codex operator packet —
    where this format becomes a reusable handoff machine). Then S7 (actor-output → ReviewPacket
    normalizer). The external harness (H-series) stays OUTSIDE AG; AG is the courthouse, not
    the getaway car. Ladder: S6 → S7 → (checkpoint) → H1.
  - **Push state: NOTHING pushed — 5 commits local/unpushed (S1–S5), disk-SPOF.** Operator
    holds push timing (checkpoint push considered after S5, deferred). If this disk is lost the
    branch is gone; a session *clear* keeps it (commits are on disk).
  - Re-entry probe: `git log --oneline feat/playbooks-gov-loop..feat/playbooks-synthetic-conveyor`
    should show S1–S5 (`c909e89 a6f8299 0d32639 5c2f831 08d3b45`); `pytest tests/playbooks -q` green.

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
