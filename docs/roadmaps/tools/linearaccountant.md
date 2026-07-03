# Roadmap — linearaccountant × AG

**Status:** DRAFT (2026-07-02; ratifiable from exploration evidence)
Repo: `~/git/linearaccountant` (HEAD `7b07c04`, 2026-06-25; **v0 boundary frozen
2026-06-04**) · Docket: governor-atlas constellation case (LA edge)

## 1. Contract snapshot — what AG assumes today

- `src/governor/linear_accountant_client.py` mirrors the frozen `lib.rs` contract
  verbatim: `CapacityRequest{…, eligibility_reference, idempotency_key}`,
  `CapacityDecision = Granted | Denied`, `ConsumptionDecision = Consumed |
  AlreadyConsumed | InsufficientCapacity | Expired | Revoked | UnknownToken |
  ScopeMismatch`.
- S4-lite refusal mapping (ratified 2026-06-09): the seven ConsumptionDecision
  variants map onto the closed AG refusal set (`already_consumed`,
  `capacity_refused`, `token_expired`, `token_revoked`, `unknown_token`,
  `scope_mismatch`); pre-call refusals `admission_denied`,
  `dangling_receipt_reference`.
- AG is a named consumer; **AG never mints from an ALLOW** (memory:
  linearaccountant_repo). Endpoints are plain injected callables — no transport
  abstraction, no schema unification, no shared client base.
- Durable spend (playbooks Slice 5) sits post-admission/pre-LA: replay refuses
  BEFORE the LA call; the durable claim receipt cites the wicket pass as parent.

## 2. Observed drift (dated)

None. The frozen v0 surface matches the AG client exactly (verified 2026-07-02).
LA-side additions since freeze (SpendCapability mint, `la_cli` thin binary, Lean
differential oracle) are freeze-safe and not consumed by AG.

## 3. Named gaps (non-binding)

- `LA_UNIT_CLASS_FENCE` (Wall 2, `working/candidate-la-unit-class-fence.md`) —
  LA capacity is bare integers over opaque scope; per-class unit matching
  (`unit_origin_mismatch`) remains hypothetical. Fires only on a multi-currency /
  per-class capacity forcing case. Cross-repo contract change — operator-gated.

## 4. Slices

None active. Hands-off holds until a convertible-spend forcing case (memory
doctrine). When Wall 2 fires it arrives as an authority sandwich (conceptual
design → mechanical → review) spanning LA and AG, with its own campaign entry.

## 5. Do-not-build

- No unit/class fence until the forcing case (named above) actually fires.
- No transport abstraction, no new ArtifactKind/UseKind, no schema unification,
  no shared client base, no field renames (standing prohibitions, verbatim).
- No implicit LA spend anywhere (packet stop-line): every consume is explicit,
  receipted, and idempotency-keyed.

## 6. Operator questions

None open.
