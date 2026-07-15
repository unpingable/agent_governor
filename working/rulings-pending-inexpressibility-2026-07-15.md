# Four pending rulings — the inexpressibility family

**Filed:** 2026-07-15
**Status:** **NAMED, UNRULED.** Operator slicing, in-session:
*"those are each unique slices… 'nothing fixed' is correct. This is not one
patch. It is at least four separate rulings."* Naming is not ratification;
none of these authorizes an edit.
**Evidence:** `working/lean-sweep-2026-07-15.md` ·
`working/finding-oracle-class-self-attested-2026-07-15.md`
**Formal instrument:** `~/git/lean/docs/AG-AUDIT-CHECKLIST.md` (v10 shipped)

## The four, as ruled-to-be-ruled

### R1 — Publish/release decisions must consume claim-indexed provenance, not confidence classes

- **Evidence:** `oracle_class` is a self-attested integer
  (`oracle_pytest.py:284-291` constructor param → `evidence_gate.py:1181` →
  blob `meta` → `_helpers.py:89` → `oracle_independence` →
  `release_taint.py:40-44` publish threshold).
- **Backing:** check 1 F2 (`fluentSystem` — score without provenance binding
  at >1 unrelated gate) + check 4 (`reliance_roots_in_provenance`,
  `HighConfidence ⊬ MayRely`).
- **What the ruling decides:** what a publish decision is permitted to root
  in. Four options already drafted in the oracle_class finding (derive what's
  derivable · type asserted-vs-derived · fence the policy · rule it
  acceptable and say so at the boundary).
- **Custody:** receipt-kernel invariants + publish boundary. Custody-affecting.
- **Severity:** LATENT — thresholds ship at class 0 (inert); live the moment
  anyone raises the bar as the docstring invites.

### R2 — Refresh must require new evidence, and probably return a new state rather than mutate age away

- **Evidence:** `TTLManager.revalidate(claim_id)` (`ttl.py:235`) restores
  `last_validated_at` **and** `current_confidence = original_confidence`,
  taking no evidence parameter.
- **Backing:** check 5, `refresh_is_inexpressible`.
- **What the ruling decides:** two things, separably — (a) must refresh take
  evidence (`revalidate(claim_id, *, evidence)`)? (b) must it **return a new
  state** rather than mutate the tracked claim in place? The operator hedged
  (b) ("probably") and it is the deeper question: in-place mutation means the
  pre-refresh age is *gone*, so nothing can testify that a refresh happened
  or what it rested on. A returned successor state preserves the lineage the
  way every other successor in this estate does.
- **Custody:** TTL semantics. Custody-affecting.
- **Severity:** LATENT — sole caller (`ttl.py:609`) fires only on
  `AuditDecision.ALLOW_HARD`; the caller is disciplined, the method is the lane.

### R3 — Compaction loss must always produce testimony, regardless of convenience flags

- **Evidence:** `context_compact.py:580,611` — `preserved_* = … if
  self.config.always_keep_* else []`, while `dropped_items` is populated only
  from `dropped_turns`. Flags off ⇒ decisions/anchors/constraints vanish with
  **no `DroppedItem`**.
- **Backing:** check 8, `checkpoint_mints_nothing`.
- **What the ruling decides:** whether a config flag may switch off *custody*
  as opposed to *retention*. Note the available split: "don't preserve it" and
  "don't record that it's gone" are different powers, and today one flag buys
  both. A ruling could keep the convenience and still forbid the silence.
- **Custody:** compaction custody. Custody-affecting.
- **Severity:** LATENT — all three flags default `True`.

### R4 — Public APIs must make unearned transitions unrepresentable, not merely discouraged

**This one is not the same kind of thing as R1–R3.** R1–R3 are code slices
against named evidence. R4 is **doctrine**: the general law of which R1–R3
are instances, and of which today produced six more.

- **The claim:** an operation that would launder must not be *sayable*. Not
  guarded, not documented, not conventionally-avoided — unrepresentable in
  the signature.
- **Why it is genuinely new, not a restatement:** the estate already holds
  *"authority gates MUST allowlist — novel value → typed refusal"*
  (`memory/feedback_allowlist_authority_blocklist_detection`). That governs
  **what values a field may hold**. R4 governs **what operations may exist at
  all**. `revalidate(claim_id)` has no invalid value — the argument is fine;
  the *signature* permits refresh without evidence. A vocabulary rule cannot
  reach it. Different axis, adjacent law.
- **The formal source:** the `*_is_inexpressible` family
  (`refresh_is_inexpressible`, `caveat_dropping_is_inexpressible`). Their
  content is exactly this: the discipline's claim is that the operation is not
  expressible, not that it happens to be unexercised.
- **The AG evidence, today, six instances:** `operator_mode` (str →
  closed domain, fixed) · axis values (free-form → closed vocab, fixed) ·
  `custody:` strings (fixed) · `Belief.source` (free-form → `TransmissionPath`,
  fixed) · `oracle_class` (open) · `revalidate()` (open). The meta-finding
  from the sweep: **every lane is latent — safe defaults, disciplined callers,
  expressible violations.** AG has been enforcing the unsaid half by
  convention; the kernel says convention is the wrong instrument.
- **What the ruling decides:** whether this is promoted to doctrine, and at
  what scope. Candidate for `~/.claude/CLAUDE.md` (constellation-wide — the
  law is not AG-specific and the Lean kernel is its source), which would make
  it a **doctrine-promotion** act under the promotion rule, with provenance
  and firing cases carried up. Local trim would point upward.
- **Custody:** doctrine. Operator fiat.

## What the four do NOT cover

Recorded so the slicing is not mistaken for completeness — the operator said
*"at least four"*:

- **Unverified codex candidates** (`working/lean-sweep-2026-07-15.md`):
  `claims_evidence_binding` `has_blob`-any-state (check 5);
  **`ci.py:459` caveat-blind pass acceptance** (check 6, burden shedding —
  *not* covered by R1–R4 and it is the checklist's own named unscreened
  attack: "burdens are decorative wherever demand is caveat-blind");
  `confer_operational_effect` re-read (check 7, linearity — also uncovered);
  `commitment_transport` multiplicity collapse (check 8). All four remain
  **codex testimony, unverified by this session.**
- **Checks 1–4 in full** — applied only insofar as `oracle_class` answers
  them. No universal-stamp census, no crossroads screen, no midpoint-matching
  pass, no per-decision provenance rooting.
- **The lean roadmap v7→v10 correction** — mechanical, not a ruling.

## Stop lines

- Naming is not ratification. Each of R1–R4 needs its own explicit ruling.
- R1–R3 are separately rulable and separately buildable; nothing about R4
  waits on them, and nothing about them waits on R4 (though R4 would decide
  the *shape* of R1–R3's fixes if ruled first).
- No item here is authorized. No kernel invariant, TTL semantic, publish
  threshold, or compaction path is edited on the strength of this record.
