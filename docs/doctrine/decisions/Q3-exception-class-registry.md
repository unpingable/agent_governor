---
audience: repo-local
status: ratified
policy_artifact_id: decision.validator_integration.q3
ontology_version: gov-doctrine-v1
supersedes: null
ratifier: James Beck <unpingable@users.noreply.github.com>
ratified_at: 2026-04-19T18:20:51Z
---

# Q3 Ratification Candidate — Exception-Class Registry

## Selection

**Option A.** The exception-class registry is closed and governed. Every `exception_class` referenced by a compressed-path authorization must appear in a ratified `policy_declaration` before it is admissible. Unknown classes → `INVALID_STRUCTURAL`. Additions to the registry bump `ontology_version` and require their own `policy_declaration` lineage.

The initial allowed compression direction is **`OBSERVE → AUTHORIZE` only**. No other compressed transition is admissible at first pass; widening the allowed set requires a `policy_declaration` adding new direction(s) to the registry rules.

Telemetry counts compressed-path authorizations **by `exception_class`**, not as a single flat counter.

## Source

`specs/gaps/GOV_GAP_VALIDATOR_INTEGRATION_001.md` §Q3.

## Basis

This is a doctrine-level question, like Q2 and Q4. The argument for A is structural:

- The exception space *is* an ontology. The doctrine states "ontology drift is policy drift" (`standing_and_receipts.md` §9, `validator_contract.md` §9). If the exception class set is open, the validator inherits an unbounded policy substrate that nobody declared.
- Option B (open registry, telemetry-only) defers the problem rather than closing it — operators under load will invent new strings to get past denial, and "review later" never arrives.
- Option C (binary flag, no taxonomy) erases the structure entirely — the system can no longer distinguish "operator-acknowledged emergency compression" from "convenience shortcut," which is exactly the distinction the receipts exist to preserve.
- A makes operator pressure visible: the gate counts compressed paths *by class*, so a class becoming the silent default appears in telemetry rather than in folklore.

A note on what zero counts mean: per the gap spec falsification framing, a validator exception counter at zero across real traffic is not necessarily a success indicator — it may mean the gate is too loose elsewhere and operators never need the compression path. The signal is in *distribution*, not absence.

## Required fields per exception-class `policy_declaration` (frozen)

A `policy_declaration` introducing or amending an `exception_class` must include:

- `exception_class` — name (must be unique within the registry version)
- `allowed_source_standing` — the lower-standing receipt being compressed from (initially: `OBSERVE`)
- `allowed_target_standing` — the higher-standing receipt being compressed to (initially: `AUTHORIZE`)
- `required_parent_evidence` — the explicit evidence required on the compressed authorization (e.g. `operator_approval` parent receipt, or equivalent constitutional-standing artifact)
- `scope_limits` — the operational scope under which this exception is admissible (e.g. specific subjects, specific actor classes, specific environments)
- `expiry_or_review_date` — date by which the class must be re-ratified or expires; an exception class without an expiry/review date is not admissible

A declaration missing any of these fields is invalid and the class it attempts to introduce is not registered.

## What this ratifies

- The registry rule (Option A): exception classes are governed ontology, additions require `policy_declaration`.
- The six required fields above on every exception-class `policy_declaration`.
- The initial direction restriction: `OBSERVE → AUTHORIZE` is the only allowed compression direction at this ratification's effective time. Other directions require a `policy_declaration` widening the registry rules themselves (a meta-amendment, not a class addition).
- The telemetry rule: validator counts compressed authorizations by `exception_class`, not as a single counter.
- The `VALID_WITH_EXCEPTION` outcome requires (a) a compressed path matching a registered exception class, AND (b) all `required_parent_evidence` for that class present and verified. Missing evidence → `INVALID_SEMANTIC`, not `VALID_WITH_EXCEPTION`.
- The initial registry is **empty**. At validator startup with no ratified exception-class `policy_declaration`s in the registry, the validator admits no compressed paths. Any compressed authorization is `INVALID_STRUCTURAL` until at least one exception class is introduced via its own `policy_declaration`. This is a feature: maximally strict initial state, opt-in widening through governed declaration.

## Acceptance criteria (frozen for validator implementation)

These criteria become test assertions when validator implementation begins (gap spec C2):

1. A `VALID_WITH_EXCEPTION` outcome requires a resolvable, ratified `exception_class` in the registry; unknown classes → `INVALID_STRUCTURAL`.
2. Compressed authorization telemetry is keyed by `exception_class`; per-class counts are queryable. A flat all-classes counter is not sufficient.
3. Adding an exception class produces a `policy_declaration` with all six required fields. Missing fields → declaration invalid, class not registered.
4. If `required_parent_evidence` declared by an exception class is absent on a compressed authorization, the outcome is `INVALID_SEMANTIC`, not `VALID_WITH_EXCEPTION`.
5. The validator must not admit compressed paths in directions other than those allowed by the registry rules currently in force. At ratification time, only `OBSERVE → AUTHORIZE` is allowed.
6. An exception class past its `expiry_or_review_date` is not admissible; the validator treats it as if not registered. Re-ratification produces a new `policy_declaration` with `supersedes` referencing the prior version.

## Open sub-decisions (deferred follow-on ratifications)

These are implementation choices, not constitutional ones, and may be ratified separately as Q3.A, Q3.B, Q3.C without re-opening Q3:

- **Q3.A — Telemetry export shape.** How per-class compressed-authorization counts are exposed (Prometheus metric naming, telemetry event schema, dashboard surface). Affects operator visibility but not constitutional structure.
- **Q3.B — `operator_approval` evidence shape.** Whether `operator_approval` is itself a typed receipt (e.g. its own `receipt_role`), an externally-signed artifact, or both. Ties into Q1.A (event-type strategy) and the eventual seat-based authority work flagged in `decisions/README.md`.
- **Q3.C — Registry-rule meta-amendments.** The mechanism by which the *direction restriction itself* (currently `OBSERVE → AUTHORIZE` only) is widened. Probably its own `policy_declaration` shape distinct from class additions, but the exact form is deferred.

## What this does NOT ratify

- Any specific exception class. The registry is empty at ratification time. Each operationally-needed exception class requires its own `policy_declaration` introducing it, with all six required fields populated.
- Q1.A, Q1.B, Q4.A, Q4.B, Q2.A, Q2.B, Q3.A, Q3.B, Q3.C (above)
- The mechanism for revoking a registered exception class mid-life (vs. waiting for `expiry_or_review_date`). Probably a `policy_declaration` with `supersedes` and explicit revocation, but the form is deferred.
- Receipt envelope schema (gap spec C3)
- Validator implementation (gap spec C2)

## How to ratify

The ratifier — and only the ratifier — flips this candidate to active by:

1. Setting `status: ratified`
2. Filling `ratifier: <name>`
3. Filling `ratified_at: <ISO 8601 UTC>`
4. Committing the change

Editing any other field after ratification requires a successor decision artifact with `supersedes: decision.validator_integration.q3`. The ratified record is immutable; corrections are made by superseding, not by mutation.

## Effect on validator implementation unblocking

Q3 is the last of Q1–Q4. When ratified, all four constitutional blockers are closed and gap spec C2 (validator implementation) becomes legal. Q5's pre-ratification fallbacks collapse in the same change that introduces C2 — they are removed, not retrofitted.
