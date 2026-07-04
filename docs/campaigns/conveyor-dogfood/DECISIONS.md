# Decisions — conveyor dogfood

## CD-D1 — hybrid envelope architecture  **(RATIFIED 2026-07-04, operator)**

M-1 stays maude's execution-instance contract; it gains a `governance:`
binding block citing AG law by digest/ref. Rejected: Option B (QueuedPlaybook
IS the envelope — demotes maude to an AG UI skin) and Option A (independent
maude stack — duplicates QueuedPlaybook/ReviewPacket/RationCard/
ActorOutputNormalizer, "two infrastructure-shaped mammals fighting over the
same burrow").

Binding rules (verbatim intent):
- AG playbook conveyor owns governance/admissibility semantics; maude M-1 owns
  execution-instance semantics.
- `governance:` fields: authority_system, playbook_id, playbook_digest,
  ration_card_digest, review_packet_ref, queued_playbook_ref (conveyor-routed
  only), approval_ref, governance_status ∈ {candidate, approved, refused,
  obstructed}.
- **Constraint-projection rule:** if maude enforces allowed/forbidden paths,
  command classes, budgets, or stop conditions that originate in AG, the
  envelope records BOTH (1) the resolved constraints maude enforced and
  (2) the AG object/digest they were projected from.
- **No import coupling:** maude consumes serialized refs/digests/projections;
  stable import-level coupling waits until AG mints the exported conveyor
  surface.
- Invariant: "AG grants/limits the shape. Maude enforces the run instance."
  A valid AG playbook does not prove maude enforcement; a successful maude run
  does not prove AG semantics.

## CD-D2 — land both branches before any dogfood run  **(RATIFIED 2026-07-04, operator)**

"Branches are staging, not jurisprudence." Merge `playbooks-gov-loop` first,
verify, then `playbooks-synthetic-conveyor`, verify, push; preserve tips as
tags; landing note maps refs → main commits. Landing is NOT blanket
operational promotion — classification required (citable substrate /
CANDIDATE / disabled-inert / fix-on-touch); C11/seccomp/H2-dependent paths
remain inert; no live sandbox/autopilot authority implied by merge. STOP if a
merge requires treating unresolved gates as operationally complete.

## CD-D3 — lane assignment  **(RATIFIED 2026-07-04, operator)**

This session executes both lanes (AG + maude): the maude sibling session
wrapped its lane at GS-10b leg 3c (`98a3831`; queue/sessions/adapters desks
live; 239 green; why→GS-13 and report→M-4 correctly deferred).

## CD-D4 — specimen ladder  **(RATIFIED 2026-07-04, operator)**

(1) `state-index-roadmap-kind` — boring, self-referential, mutating, pure-AG,
objectively checkable. (2) playbook docs normalization. Night Shift later
(first run must not cross repos). A2 re-sweep rejected as FIRST specimen
(observe-only "doesn't prove the execution path has teeth") — remains a valid
later report-only specimen. First-run requirements: cite only main-line landed
law; bounded paths; no broad docs rewrite; no semantic roadmap classification
beyond the named kind; acceptance test; suite+lint clean; receipt surfaces
separated if maude is involved. "Index itself → clean its own playbook docs →
then maybe touch Night Shift. Self-support, not recursion cosplay."
