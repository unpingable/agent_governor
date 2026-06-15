# RESUME — P4 mint LANDED 2026-06-15 (committed local, NOT pushed)

P4.0a HIGH-prep AND P4.0b (the mint) are both done and committed locally. The
constitutional furniture moved: a surviving trial value can now be minted into a
`ControlBaseline` via the four-office ceremony, gated by the dual-witness predicate and
the operator-basis act-standing. Green, exit-witnessed, **not pushed**.

> Eligibility opens the courtroom door. Promotion moves the constitution. P4.0b made the
> move. Operator basis authorizes attribution; it does not legitimize promotion and
> cannot cure missing evidence.

## Commits this session (local, NOT pushed)
```
85601bd  P4.0a-HIGH-prep: ratify promotion basis spec (doctrine + bundle/freshness spec)
632414d  P4.0a clarification: basis_bundle_hash is raw SHA-256 hex (docs only)
e8cb8e2  P4.0b: promotion mint — basis_bundle_hash + ControlBaseline supersession
2e94dee  P4 slice-2: align operator-basis shadow with strong facts (substitution seam closed)
2b7fa5a  P4 closeout specimen (docs-only cold-start map)
f449164  P4 slice-3a: real evidence substrate (read-only discovery)
bc1dc90  P4 slice-3b: discovery-backed mint input path (no auto-mint)
```
Closeout map: `working/P4_CLOSEOUT_2026-06-15.md` (the six-section "no séance" artifact).
Boundary held verbatim: `85601bd`+`632414d` = authority/spec surface; `e8cb8e2` =
implementation that CONSUMES that authority (never co-authors, never self-cites).

## What P4.0b shipped (`e8cb8e2`, zero existing source modified)
- `src/governor/basis_bundle.py` — `compute_basis_bundle_hash` (pure; raw-hex; excludes
  operator basis + clocks; sorted observations; frozen open-claims).
- `src/governor/promotion_mint.py` — `PromotionReceipt` (content-addressed, no hash
  cycle), `mint_promotion` (four-office: gate eligibility + STRONG
  `derive_operator_basis_present` bound to the computed bundle hash + single receipt +
  `ControlBaseline` admission w/ `supersedes` lineage), `revert_promoted_baseline`
  (supersession, not undo).
- `tests/test_promotion_mint.py` — 6 acceptance + 9 negative, synthetic fixtures only.
- Cargo verdict PASS (15 new + full suite 15910 passed / 62 skipped, exit 0). Dogfood
  verdict HELD (fail-closed; fence held; keeper passed).

## Review acceptances recorded (operator-present 2026-06-15)
1. raw-hex `basis_bundle_hash` ratified (`632414d`); algorithm identity from field
   semantics, not an inline prefix.
2. `kernel_fuse_ratification_side_effect` is OUTSIDE the bundle hash — separate gate
   predicate, refused independently.
3. two-operator-basis seam ACCEPTED for this slice + carried as **explicit follow-up
   debt** (marker in `promotion_mint.py` docstring): weak gate-shadow bool vs strong
   mint-time derivation must not substitute; future work aligns them or adds a bridge.
4. synthetic `config_hashes` are fixture stand-ins only — no live config custody, no real
   `max_slices=4` promotion.

## Next (operator-set order; 2 and 2.5 DONE)
- **(2) Two-operator-basis alignment — DONE (`2e94dee`).** Reduction proved weak =
  pure projection of strong → alignment, not bridge. `OperatorBasisFacts.project()` is the
  one readout; mint refuses `operator_basis_weak_strong_mismatch`. Seam closed.
- **(2.5) P4 closeout specimen — DONE.** `working/P4_CLOSEOUT_2026-06-15.md` (docs-only).
- **(3a) Real evidence substrate, read-only — DONE (`f449164`).** `promotion_discovery`
  reads the four real stores → assembles bundle → runs the gate. Custody, not permission;
  discovery is not admissibility.
- **(3b) Discovery-backed mint input path — DONE (`bc1dc90`).** `prepare_mint_input`
  packages eligible discovery into mint input; never mints/writes; MintInput is
  preparation, not authorization. Mint stays an explicit operator-present act that
  re-derives.
- **(3c) Actual operational promotion — DONE (operator-present, cold re-entry 2026-06-15).**
  `src/governor/operational_promotion.py`: `operational_promote` (the explicit act:
  prepare→mint→persist) + `PromotionReceiptStore` (durable spend-ledger, no delete) +
  `OperationalPromotionOutcome`. 15 tests green; full suite green (exit-code observed).
  Live-root specimen: fired at the real `.governor/` → refused (empty chamber:
  `evidence_insufficient`/`not_walkable`/`replay_missing`/`operator_basis_absent`), **zero
  writes** — the successful 3c outcome. No path from discovery/prepare to a write (proven
  behaviorally + statically + no-fiat-knob). Admission/closeout:
  `working/P4-slice-3c-{admission,closeout}-2026-06-15.md`. Still: no real `max_slices=4`
  (config_hashes remain the accepted fixture stand-in); no CLI front door (candidate).
- **(4) Second profile (ops/NQ)** — gated on self-governance surviving one full promotion
  cycle (constructor-refused otherwise). After real custody, not before.
- **(5) Fuse kernel-enforcement LAST** — `GOV_GAP_GOVERNOR_FUSE_ENFORCEMENT_001` (still
  folklore). Fuse hardens settled doctrine; it is not where doctrine is discovered.

## Still NOT done / NOT touched
- No push (operator owns that signal; work-hours rule).
- No real `max_slices=4` promotion.
- No kernel/fuse/ratification invariant change.
- `working/GOV_GAP_ESTIMATION_CALIBRATION_RECEIPTS_001.md` filed this session (candidate,
  uncommitted, separate surface — estimation/calibration, NOT P4).
