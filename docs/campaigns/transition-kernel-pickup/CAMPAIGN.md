# Campaign — transition-kernel pickup (AG mint boundary)

Status: **resumed under the roadmap program** (2026-07-02; was reduction mode
2026-06-23). Slices 1a/1a-bis DONE in Standing (unpushed); AG Slice 1b (=B4)
unblocked. The 2026-07-02 resume adds the **B-series** (Rust-kernel lane): the
standalone `~/git/transition-kernel` repo — Rust `Admit | Refuse(kind,reasons) |
Escalate(required_authority)`, 9-case byte-conformance vs Python via
`scripts/differential.py`, summit `stage3b2-first-effect` — was NOT in the
2026-06-23 inventory and must be reconciled (B1) before Rust work resumes.

Capsule: [INVENTORY.md](INVENTORY.md) (crosswalk + verdict) · [DECISIONS.md](DECISIONS.md)
(D010 ratified; B-series sign-off questions) · [NEXT.md](NEXT.md) (Slice 1b = B4;
B-series slices). Routing per `docs/roadmaps/ROUTING.md`; program hub
`docs/roadmaps/README.md`; tool view `docs/roadmaps/tools/transition-kernel.md`.

## Question

> Does Standing already issue something that can honestly testify as a **grant token** for
> AG mint/continuation, or do we only have adjacent authorization records?

**Answered (reduction): (B)** — Standing issues an honest grant-token that refuses
expiry/single-spend/replay/subject-binding itself, but **cannot refuse a spend-time
scope-mismatch**. AG's mint boundary needs that refusal; locating it is the open fork.

## Campaign boundary (the pickup point)

AG picks up the transition kernel **only at the mint boundary**:

```
Standing-issued grant token → AGGrantAdapter → governed actor/session/step authority
```

This is **not** `ag_admit`, self-correction, repair-provider wiring, or conductor behavior —
those are transport/admission rails (the `ag-admit-self-build` campaign). Pickup begins when
actor/session/step minting *depends* on a Standing-issued grant token instead of AG-local
trusted construction.

## Invariant — a token is not "present" unless Standing already refuses it

> A grant token is "present" only if Standing can refuse replay / spend / scope / expiry
> failures **without AG inventing those refusals locally.** "Has scope-ish fields" ≠ "may mint
> governed authority."

By this rule the Standing `Grant` is present for 4 of 5 classes; scope-mismatch is the gap.

## Allowed (this campaign, when it leaves reduction)

A narrow `StandingGrantToken → AGGrantAdapter` at one mint boundary (cleanest: `activation.py`
Office 2, replacing `standing_ok: bool`); a failing test that AG cannot mint/continue without a
Standing-issued grant token; receipts recording token id / scope / spend / actor-session
binding; refusals for missing / expired / wrong-scope / already-spent.

## Forbidden

No adapter implementation in reduction; no AG mint-behavior change; no conductor/planner change;
no token vocabulary minted without inventory; **no treating AG-local trusted construction as
equivalent to a Standing grant** (the laundering surfaces are named in INVENTORY.md); no
self-hosting-first; no global "AG consumes the kernel everywhere" — one mint boundary, one slice.

## Laundering surfaces (named in-code — do not let these stand once pickup lands)

- `activation.py:450` — `standing_ok: bool` fiat; `external_standing_receipt` carried-not-parsed.
- `supervisor.py:752` — AG-on-AG self-authorization in `observe` mode (`kernel_refuse_vs_governed_continue`).
- `supervisor.py:433` — `fork_session` extends authority on prior *local* approval, no fresh standing.

## Stop-lines — Rust-kernel lane (B-series, verbatim from the packet, 2026-07-02)

- Do not build bounded autopilot; do not promote playbooks to operational authority.
- Do not make AG self-bootstrap its own authority.
- Do not treat Lean theorem names as implementation requirements without stating
  the operational invariant they encode.
- **Rust is not the truth mint** — it enforces declared contracts; it does not
  create authority.
- Do not delete or sideline Python AG: Python remains orchestration /
  control-plane / reference / **explicit observable fallback**. No silent
  Rust→Python fallback, ever.
- Do not broaden the kernel beyond the smallest invariant-bearing core.
- Do not turn Wicket into a second policy language unless the fixtures force it.
- Do not make LA spend implicit.
- Wicket verdict map is the stable contract surface: `authorized→PASS`,
  `denied→BLOCK`, `gap→WARN`, `advisory_only→OBSERVE`, `unaccounted→ERROR`.
- Separation holds: Standing decides authority/admissibility; LA decides
  consumable capacity/spend; the kernel decides lawful transition; receipts
  preserve what happened.

## Exit (reduction phase) — done

Returned **(B)**: Standing records are close but missing a named refusal (spend-time scope
match). The first real build is therefore *not* a blind adapter — it must place the
scope-mismatch refusal explicitly (Model X vs Y, [INVENTORY.md](INVENTORY.md)). See
[NEXT.md](NEXT.md) for the recommended Slice 1 and the operator decision it needs.
