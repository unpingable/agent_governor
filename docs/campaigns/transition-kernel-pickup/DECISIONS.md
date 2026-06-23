# Decisions — transition-kernel pickup

## D010 — transition-kernel pickup boundary  **(RATIFIED 2026-06-23, Model X)**

Status: **RATIFIED** (operator, 2026-06-23). The scope-locus fork was decided **Model X**:
**Standing owns spend-time scope-mismatch refusal.** The `AGGrantAdapter` may only *inherit*
Standing's grant-use verdicts; it must **not** synthesize scope authority from carried grant
fields. Model Y (adapter-local scope matching) is acceptable **only** as a temporary
diagnostic specimen to demonstrate the gap — never to authorize mint/continuation in
production.

Ratified rule (verbatim intent): *Standing decides whether the grant authorizes the attempted
act; AG only consumes that decision at the mint boundary.* The adapter must inherit all five
refusals (expiry, replay, spent-token, subject-binding, **scope-mismatch**) and must not mint
or continue from carried scope fields alone.

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

### Resolved fork — scope-mismatch refusal locus → **Model X**

Decided 2026-06-23. Standing closes its own token; the alternative (Model Y, adapter-local
matching) was rejected as authority because it makes AG the scope adjudicator — "trusted
construction with a nicer hat." It survives only as a non-authorizing diagnostic.

### D010a — scope check is non-consuming (no DoS primitive)

A scope mismatch **must be checked BEFORE spend** and **must NOT consume the grant** (it emits
a refusal receipt, leaves the token unspent) — unless Standing adopts an explicit "failed
presentation burns tokens" doctrine. Otherwise any wrong-target presentation becomes a
denial-of-service primitive against a single-use grant. (Operator catch, 2026-06-23.)
