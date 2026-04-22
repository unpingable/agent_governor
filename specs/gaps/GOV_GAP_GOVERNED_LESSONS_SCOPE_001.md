---
audience: repo-local
status: active
---

# GOV_GAP_GOVERNED_LESSONS_SCOPE_001

Status: draft
Owner: Governor
Type: scope-only gap
Filed: 2026-04-19

Source proposal (not absorbed as doctrine): [`docs/inbox/2026-04-19_cohort_witness_soong_thread.md`](../../docs/inbox/2026-04-19_cohort_witness_soong_thread.md) (companion drop on cohort witness) and a separate substantial drop on governed lessons subsystem from the same Sunday session, preserved as a memory pointer rather than a checked-in doctrine artifact.

Depends on:
- Q1 ratified — kernel composition (`docs/doctrine/decisions/Q1-kernel-composition.md`)
- Q2 ratified — closed-set enum + extension via `policy_declaration` (`docs/doctrine/decisions/Q2-subject-derivation.md`)
- Q4 ratified — validator provenance (`docs/doctrine/decisions/Q4-validator-provenance.md`)
- [`STRUCTURED_EVIDENCE_AND_PROMOTION_GAP.md`](STRUCTURED_EVIDENCE_AND_PROMOTION_GAP.md) — per-action vs lifecycle authorization, witness evidence types
- [`CONTINUITY_BEARING_SYSTEMS.md`](CONTINUITY_BEARING_SYSTEMS.md) — classification before recovery policy

Note on Q3: the exception-class registry (`docs/doctrine/decisions/Q3-exception-class-registry.md`) is intentionally not listed as a current inherited dependency. The closed-vocab + `policy_declaration`-extension pattern lessons need is established by Q2; Q3 just applies that same pattern to exception classes specifically. Q3 may become directly relevant in the full gap spec if `lesson_binding` semantics introduce a compressed-authorization path (e.g., emergency binding without full review). It is surfaced there, not here.

## 1. Problem

Governor already has continuity-bearing machinery for recording work, collaboration, state, receipts, and decision traces. What it does **not** yet have is a governed way to derive, review, and preserve **long-term lessons** from that continuity without allowing summaries, folklore, or model output to silently become authority.

This gap exists because "memory" is the wrong abstraction.

The real problem is governed persistence:

- continuity records what happened
- future execution may need to inherit something from that history
- inheritance must not happen through uncited summary seepage
- authority must not arise from private experience that has not been externalized and reviewed

In short: Governor needs a way to distinguish **recorded history** from **promoted lessons**, and to prevent promoted lessons from becoming quiet law without explicit standing.

## 2. Why a scope-only gap exists first

A full subsystem proposal for governed lessons already exists in rough form, including candidate artifact types, class vocabularies, invariants, retrieval rules, and binding concepts. That material is referenced from the source proposal and preserved as a memory pointer.

That material is useful, but it is still a proposal. It must not enter doctrine wholesale. A scope-only gap comes first so the project can ratify the boundary of the problem before ratifying the subsystem shape.

This follows the same rule the proposal itself argues for:

- proposals may be generated freely
- durability requires adjudication
- execution consequence requires a stricter path still

The governed-lessons proposal is therefore treated as input to this gap, not as pre-ratified doctrine.

## 3. Core distinction this gap introduces

This gap asserts the need for a three-part distinction:

### continuity
Evidence-bearing record of work, collaboration, state, rationale, receipts, and transitions.

### lessons
Derived, reviewable compressions of continuity that preserve what may matter across runs, agents, or operator sessions.

### bindings
Separate mechanisms, if any, by which a lesson may affect future execution.

This gap does **not** yet ratify the final artifact model. It only establishes that these are distinct constitutional concerns and must not be collapsed into one undifferentiated "memory" bucket.

## 4. Scope

This gap is limited to defining the problem boundary for governed lessons.

It is in scope to decide that:

- long-term lessons are a **Governor concern**
- continuity alone is insufficient for governing long-term lessons
- lessons must be treated as **derived artifacts**, not raw continuity entries
- retrieval of a lesson must not by itself imply authority
- authority of a lesson must not by itself imply execution consequence
- any execution consequence must pass through a distinct governed path
- closed vocabularies are needed at authority-changing seams
- flexible fields may remain open where the project is still learning the world
- the subsystem must inherit existing Governor decisions rather than reopening them

## 5. In scope (questions the full gap spec must answer)

The future full gap spec for governed lessons SHALL cover at least the following boundary questions:

1. Whether lessons require separate object classes for:
   - proposed lesson
   - durable lesson
   - execution-relevant binding

2. Which lesson concepts are constitutional enough to require closed vocabularies.

3. Which lesson concepts should remain structured-but-open pending more field experience.

4. What invariants are required to preserve the boundary between:
   - continuity
   - lessons
   - bindings
   - validator behavior

5. How retrieval-is-not-authority will be enforced in validation and runtime behavior.

6. How lesson promotion interacts with standing, review, provenance, and existing authorization semantics.

7. Whether repeated override pressure may create lesson candidates, and under what explicit prohibition it must not create binding power directly.

8. Whether any part of the governed-lessons artifact model should eventually be extracted into a shared schema library after ratification stabilizes.

## 6. Out of scope

This scope-only gap does **not** decide any of the following:

- final artifact schemas
- final enum member sets
- final retrieval ranking algorithms
- final review quorum or cohort-witness requirements
- final receipt role additions
- full validator logic for lesson influence detection
- Rust vs Python vs mixed implementation strategy
- repo extraction timing beyond the general "not yet" direction
- UI or operator workflow details beyond what is needed to state the problem boundary

Those belong to the full governed-lessons gap and later implementation work.

## 7. Inherited decisions

This gap explicitly inherits and does not reopen the following already-established directions:

### 7.1 Kernel composition (Q1 ratified)
Governed lessons, if adopted, emit through the existing `receipt_kernel` discipline rather than inventing a parallel durability mechanism. Lesson artifacts inherit Merkle-style parent integrity from the kernel hash chain.

### 7.2 Closed-set enum discipline with extension path (Q2 ratified)
Where lessons introduce authority-changing semantics, those seams follow the same closed-set + `policy_declaration` extension discipline established for `subject_derivation`. Drift at authority seams would be governance drift.

### 7.3 Validator provenance (Q4 ratified)
Any lesson promotion, review, or binding path must preserve provenance discipline consistent with other governed artifacts. Validator changes affecting lesson semantics are policy changes, not config edits.

### 7.4 Structured evidence and promotion (cited gap)
Lessons are not exempt from evidence/promotion discipline. They are a stronger case of it.

### 7.5 Continuity-bearing systems (cited gap)
Continuity is the substrate from which lessons are derived. Lessons do not replace continuity; they govern what may persist from it.

## 8. Framing assumptions

The full gap spec should proceed under these framing assumptions unless later ratification rejects them:

1. The relevant distinction is not "knowledge vs memory" but **externalized knowledge vs internalized experience**.

2. Agents may accumulate effective experience that changes behavior before that experience has been externalized.

3. Private experience may inform proposals, but shared authority must derive from externalized, cited, reviewable artifacts.

4. Governor's role is not to maximize retention. Its role is to govern what the past is allowed to do to the future.

5. Over-rigidity and under-rigidity are both failure modes:
   - too little structure yields folklore and quiet law
   - too much structure yields forced buckets and disguised workarounds

6. Therefore the likely correct shape is:
   - hard control at authority-changing boundaries
   - softer structure where meaning is still being discovered

These are framing assumptions, not yet ratified doctrine.

## 9. Design pressure this gap recognizes

This gap records the following pressures without yet deciding their final resolution:

- continuity is not the same thing as durable lessons
- lessons are dangerously close to policy and therefore need constitutional treatment
- agent experience that is not externalized can become operationally real without becoming governable
- lessons must not become a side-channel by which summaries or tacit behavior acquire standing
- enum drift at authority seams would be governance drift
- freezing categories too early would turn temporary working distinctions into constitutional truths

These pressures justify the full gap. They are not, by themselves, implementation decisions.

## 10. Deliverables required from the full gap spec

The follow-on full governed-lessons gap (`GOV_GAP_GOVERNED_LESSONS_001`) SHALL answer, at minimum:

1. **Artifact boundary:** what kinds of lesson-related objects exist, what they are allowed to do, what they are forbidden to do.
2. **Vocabulary boundary:** which fields are closed-set, which fields are open or semi-structured, how growth of vocabulary is governed.
3. **Promotion boundary:** what evidence is required, what review is required, what standing is required, what supersession/expiry paths exist.
4. **Retrieval boundary:** what may be surfaced to future runs, what metadata must accompany retrieval, how retrieval avoids becoming hidden law.
5. **Binding boundary:** what separate mechanism, if any, grants execution consequence; how that mechanism is reviewed; how it is inspected and revoked.
6. **Validator boundary:** how the system detects lesson influence without valid binding; how it records lesson-related effects in receipts and audit surfaces.

## 11. Default architectural direction

Until a full governed-lessons gap is ratified, the project adopts the following non-final direction:

- governed lessons are treated as a **Governor component**
- not a standalone tool
- not a separate service
- not a free-floating memory layer

A later shared schema/validator library may be considered only after the artifact model and invariants stabilize through ratification.

This is directional guidance, not final extraction doctrine.

## 12. Exit criteria

This scope-only gap is complete when all of the following are true:

1. The project agrees that governed lessons are a distinct problem and belong inside Governor's constitutional surface.
2. The project agrees that continuity, lessons, and bindings are separate concerns that must not be collapsed.
3. The project agrees that this work inherits prior ratified decisions rather than reopening them.
4. The project agrees on the list of deferred questions the full gap spec must answer.
5. The project agrees that no lesson subsystem implementation should proceed as doctrine before those questions are ratified.

## 13. Non-ratified candidate doctrine lines captured for later consideration

The following lines are captured as useful but not yet doctrine:

- Continuity records what happened. Lessons govern what may persist from it.
- Models may propose lessons. Only adjudication may grant durability.
- Retrieval does not imply authority.
- Authority does not imply binding.
- The past may govern the future only through cited, classified, reviewable objects.
- Private experience may shape proposals; it must not silently govern others.

These lines are intentionally preserved as candidate language for future ratification work in the full gap spec, not absorbed into the compressed doctrine list in `docs/doctrine/`.
