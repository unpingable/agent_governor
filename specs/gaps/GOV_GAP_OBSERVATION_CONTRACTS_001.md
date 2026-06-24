# GOV_GAP_OBSERVATION_CONTRACTS_001 — Human-authored observation contracts

> **Status: candidate, non-binding. NOT build authorization.** A handle for review (gap-spec
> format). Filed AG-side as the cross-repo custody root; **primary build home is NQ** (owns the
> witness grammar). Captured 2026-06-24 from a multi-model design pass. Doc-only.

## Keeper

> **Human-authored observation contracts.** Humans get to set the bounds of *attention*; they do
> not get to make the instrument lie more conveniently. Scope is human; meaning is the kernel's.

The dangerous version is "configurable witnesses" (Nagios in a trench coat with a fake
epistemology badge: `success_regex: "0% loss"` → `verdict: healthy`). The good version is a
bounded, schema-checked, digest-bound declaration of *what to observe, from where, with what
perturbation* — never *what the observation means*.

## Problem (the forcing case)

Several witnesses are currently **agent-shaped**: agents discover targets, infer probe shape,
choose read surfaces, and assemble receipts. Workable for exploration; bad as doctrine — *agents
are the only ones who know where the bodies are buried.* Humans need a bounded way to declare
what should be observed **without** being allowed to redefine what the observation means. (pfSense
Step-0 gateway checks are the live specimen: dpinger socket + bounded ICMP, must not lift
reachability into "WAN healthy".)

## The load-bearing cut: scope vs meaning

| Humans MAY configure (scope) | Humans MAY NOT configure (meaning) |
|---|---|
| source / vantage | parser invariants |
| target / resource | verdict semantics |
| approved read surfaces | refusal classes |
| perturbation budget | non-lift rules (reachability ≠ WAN health) |
| privacy / scrubbing rules | receipt schema |
| allowed witness kind | "unknown → cannot_testify, not false" discipline |
| operator-approval requirements | the admissible verdict *set* |

## What already exists (reuse — do NOT reinvent)

**This is the governed-playbooks four-layer model at the witness seam.** It is isomorphic; build
it as that pattern, not a new config system (the same anti-shadow-constitution discipline as the
`ag-frontend` jurisdiction map, `docs/playbooks/receipt-jurisdiction-map.md`):

| Observation-contract layer | = existing AG pattern (`governor.playbooks`, Slices 0–3 shape) |
|---|---|
| **Witness kernel** (code, not configurable) | parser + restricted dialect + closed verdict set |
| **Witness profile** (reviewed) | `CertifiedPlaybook` / `certified_kind` measurement — reviewed, certified over its domain |
| **Specimen manifest** (operator/local) | `RunPlan` — bound inputs + target + actor |
| **Run request** (fresh approval) | `RunRequest → Wicket`, frozen plan digest |
| `plan` output (pre-effect) | the frozen RunPlan digest |
| run receipt | `RunInstance` |

Specifically reusable, already shipped:
- **`certified_kind` ceiling discipline** (the verdict-narrowing rule below) — playbooks Slice 1.
- **Standing-spendability two-clock freshness** (`standing_spendability.py`, `StandingWindow`,
  `standing_before_spendability_not_bounded`) — for the stale-approval bound below.
- **`OE-001` observation-is-effectful** (`docs/playbooks/invariant-ledger.md`) — why perturbation
  budget is an LA spend, not a free read.
- **`governor why` / `parent_receipt_ids` chain** — manifest → plan → run as a digest chain.

## What needs building (later; this gap does not authorize it)

A human-editable, schema-checked, digest-bound **witness profile** (reviewed/repo) + **specimen
manifest** (operator/local) + a `plan` step that prints the exact observation contract before any
live touch, and a **run request** that re-approves freshly.

### Invariant 1 — humility-only (the validator enforces *direction*)

The softest part of the naive design is `claims_allowed`. Layer-1 says the kernel owns the
verdict set; a profile that hands humans `claims_allowed` is either redundant or *the leak*.
Resolution is an **asymmetry the validator checks**:

- **Substantive claims** (`dpinger_metrics_observed`, `path_reachability_observed`) are a
  **CEILING.** The kernel ships the full menu per `witness_kind`; the profile may only **narrow**
  it; the validator **rejects anything not in the kernel menu.** Narrowing is always safe;
  widening is the carbon-monoxide leak. (Identical to the `certified_kind` ceiling.)
- **Refusal / abstention claims** (`cannot_testify_*`, `path_ambiguous`) are a **FLOOR.** The
  profile **cannot remove them.** Stripping a witness's ability to say "I can't testify" forces it
  to commit — the same attack, opposite hat.
- **`non_claims`** (`does_not_claim_wan_healthy`, …) are **append-only** (removing a non-claim ==
  removing an abstention).

> One line: **humans can only move a witness toward humility, never toward confidence.** Both
> edges point the same way; that direction is what the validator enforces — stronger and more
> checkable than "bounded but tunable."

### Invariant 2 — digest-match ≠ still-valid (Δt inside governance)

Binding `manifest_digest` + `profile_digest` and freezing the approved digest in Standing kills
*remembered approval*. It does **not** kill *stale approval*: approval has a **time** the digest
doesn't carry. Approve digest D with a perturbation budget sized to a topology; topology shifts;
six months later the witness runs; digest still equal; contract "satisfied"; budget now wrong.
**Put a freshness bound on the binding between approval and manifest, separate from digest
equality** — the standing-spendability pattern (valid-when-approved, void-when-run). The digest
proves *what* was approved; freshness proves the approval is still *live*.

### Invariant 3 — two admissibility gates, not one

Do not collapse these into one Wicket line:
- **Profile review** — "is this profile well-formed and reviewed?" A **repo / certification**
  gate. Governs what profiles *exist*.
- **Instantiation** — "may *this operator*, from *this vantage*, aim *this profile* at *this
  target* now?" A **Wicket** gate. Governs what gets *used where*.

If any operator may bind any reviewed profile to any target, the review gate is half-defeated:
you reviewed the **instrument**, not the **aiming of it**. (= *Standing evaluates the RunPlan,
not the PlaybookSpec*.)

### Invariant 4 — perturbation budget is an LA spend

Because observation is effectful (`OE-001`: a probe trips an IDS / increments counters / marks
email read), the perturbation budget (max packets, probes fired, no-config-writes,
no-service-restart) is **spendable LA capacity**, and a witness *run* is a governed spend that
wants the same `confer_operational_effect` wall as a playbook step — not a special read.

## First slice (the safe move — NO behavior change)

> Make the human-editable surface **visible before** making it **powerful.**

- schema for `witness_profile` + `specimen_manifest`
- a validator (enforces Invariant 1's direction — narrow-only / floor / append-only)
- redacted example manifests for the three pfSense Step-0 checks
- `profile_digest` + `manifest_digest` recorded in the witness receipt
- a `plan` command that prints the observation contract (source/vantage · target · surfaces read ·
  active probes · `mutation claims: none` · max packets · allowed verdicts · non-claims · both
  digests) **before touching anything** — and `plan` output is itself digest-able, so
  manifest → plan → run is a digest chain (declared-vs-operational: `plan` = "what I'm about to
  do" witness, run = "what I observed" witness, each its own receipt).

CLI sketch (NQ): `nq-monitor witness validate-profile <file>` · `… plan <manifest>` ·
`… run --manifest <file> --emit-receipt`.

## Constellation implications (named, non-binding — commits no sibling repo)

- **NQ** — primary home: probe manifests for witness runs; the witness kernel owns meaning.
- **AG** — governed playbooks should consume *manifest digests*, not ad-hoc agent intent; the
  reusable patterns above live here.
- **Wicket** — admission checks manifest/profile compatibility (Invariant 3's instantiation gate).
- **Standing** — operator approval binds a frozen manifest digest + a freshness bound (Inv. 2).
- **Linear Accountant** — perturbation budget becomes spendable capacity (Inv. 4).
- **claimdocs** — profiles distinguish human-declared scope from kernel semantics (the Lamarr
  `packet_audition` profile is one specimen; cf. `docs/doctrine/borrow-ledger.md` RF row).
- **Corpus / doctrine** — "human-configurable scope, kernel-owned meaning" is a doctrine note.

## Non-goals / forbidden

- No "configurable witnesses": no human/agent-defined arbitrary commands + arbitrary
  interpretation (`commands: [ssh firewall "whatever"]`, `success_regex`, `verdict`). Commands are
  **generated by the witness implementation**, not freelanced by config.
- No widening of the verdict set from config (Invariant 1). No `interpretation_mode: trust_me_bro`.
- No daemon / scheduler / platform for the first slice. Schema + validator + examples + receipt
  fields + `plan` only.
- This gap does not authorize the build — it reserves the shape.

## Open questions

1. Manifest **locality**: committed-as-redacted-example only, or a local-uncommitted real form
   with a redacted public twin? (privacy: scrub private + public WAN IPs in fixtures.)
2. Where does the freshness bound (Inv. 2) live — Standing-side (approval window) or a manifest
   field the Wicket gate reads? (Likely Standing, mirroring spendability.)
3. Profile **versioning + supersession** — reuse the validator-vN supersession ceremony
   (`docs/doctrine/decisions/validator-v0_*`)?
4. Does the `plan`-witness need its own refusal classes (cannot-plan: target-unreachable-at-plan-
   time) distinct from run-time refusals?
