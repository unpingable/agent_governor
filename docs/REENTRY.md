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
> Updated 2026-06-24. `.governor/loop.json` is **stale** (tracks the completed AG-on-AG thread) — use this.

## Canonical lanes (hand-authored: meaning, not state)

- **Track B — governed playbooks** · `feat/playbooks-gov-loop`
  - Slices 0–2 complete (parse→`playbook_spec_digest`; `certified_kind` measurement; dependency closure).
  - card: `docs/campaigns/governed-playbooks-track-b/CAMPAIGN.md`
  - **STOP: do not start Slice 3 (Wicket-as-evidence) without fresh review.**

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
