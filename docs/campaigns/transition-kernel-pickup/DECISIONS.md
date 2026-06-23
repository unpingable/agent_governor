# Decisions — transition-kernel pickup

## D010 — transition-kernel pickup boundary  **(PROPOSED — NOT RATIFIED)**

Status: proposed 2026-06-23, pending the scope-locus fork below. Per the operator: "record
D010 as a proposed decision, not ratified until the inventory supports it." The inventory
supports the *boundary* but leaves the *scope-refusal locus* open, so D010 is proposed, not
ratified.

- **decision:** AG does **not** pick up the transition kernel at `ag_admit`, self-correction,
  or repair-provider wiring — those are transport/admission rails. Pickup begins **only at the
  mint boundary**, when AG requires a Standing-issued grant token to mint or continue governed
  actor/session/step authority.
- **default_action:** build the first pickup as a narrow adapter
  `StandingGrantToken → AGGrantAdapter → existing AG mint/admission path`, at the cleanest seam
  (`activation.py` Office 2, replacing `standing_ok: bool`).
- **forbidden:** no global AG rewrite; no planner/conductor semantics change; no self-hosting-first;
  no accepting AG-local trust as equivalent to a Standing grant; no unstamped actor/session/step
  continuation.
- **requires_human_if:** token spend semantics are unclear; grant scope cannot be mapped to AG
  authority scope; the adapter would alter conductor/admission projection; pickup requires new
  kernel vocabulary.
- **evidence:** [INVENTORY.md](INVENTORY.md) (verdict B); operator seed 2026-06-23.

### Open ratification fork (blocks ratifying D010) — scope-mismatch refusal locus

The Standing `Grant` refuses expiry/spend/replay/subject itself but **not** spend-time
scope-mismatch (INVENTORY.md). Two models; ratify D010 only after the operator chooses:

- **Model X — Standing closes its own token.** Add `StoreError::ScopeMismatch` to Standing's
  spend path; AG adapts the then-complete token. Honors the invariant literally. Cost: cross-repo
  Standing change first.
- **Model Y — consumer matches the attested scope.** Standing attests the scope value; the
  `AGGrantAdapter` matches it against the requested act and refuses a mismatch. Not laundering
  (the value is attested, not invented), but the refusal's *locus* is AG.

Whichever is chosen, the scope-mismatch refusal must be **explicit and receipted** — never an
implicit pass. This is a custody/authority-boundary call (`requires_human` per the rule above),
so it is operator-fiat, not loop-resolved.

> When this is ratified, copy D010 into the campaign's ratified set and update STATUS.
