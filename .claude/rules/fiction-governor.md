---
paths:
  - "src/fiction_governor/**"
  - "tests/test_fiction_*"
  - "tests/test_guardrails*"
  - "tests/test_context_drift*"
  - "tests/test_manuscript*"
  - "tests/test_similarity*"
---
# Fiction Governor

Plot threads, scene proposals, prompt generation, narrative constraints, manuscript scanning, similarity matching, context drift detection, fiction guardrails.

## Modules

- **types.py** — Character, WorldRule, BannedTrope, CanonEvent, PlotThread, SceneProposal (20 tests)
- **bible.py** — Bible ledger: characters, world rules, tone, tropes (12 tests)
- **canon.py** — Canon ledger: events, relationships, threads, proposals (30 tests)
- **verifiers.py** — InCharacterVerifier, TropeVerifier, ToneVerifier, NarrativeVerifier (32 tests)
- **state.py** — CharacterState: motivations, beliefs, constraints (18 tests)
- **knowledge.py** — KnowledgeVerifier: transmission-path adjudication against canon (25 tests)
- **manuscript.py** — ManuscriptScanner for auto-populating canon from text (36 tests)
- **similarity.py** — TF-IDF similarity, trope detection, voice/tone analysis (41 tests)
- **context_drift.py** — Context drift detection, hysteresis-based mode transitions, genre escalation (64 tests)
- **guardrails.py** — Consent tracking (pairwise, scoped), DSI detection, AII with validity profiles, hard constraints (C1-C3), soft penalties (P1-P4) (123 tests)

**Total: 401 tests**

## Key Concepts

- **Bible** = decisions about the story (characters, world rules, tone, banned tropes)
- **Canon** = facts about the story (events that happened, active threads)
- **Knowledge paths (2026-07-15)**: `Belief.transmission` is a closed `TransmissionPath`
  (`WITNESSED{event_id}` / `TOLD_BY{teller, at_chapter}` / `INFERRED` / `ASSUMED` /
  `UNSPECIFIED`); `WITNESSED` without an event and `TOLD_BY` without a teller refuse at
  construction — an uncheckable claim must not look checked. `Belief.source` (free text)
  is retained **display-only**; a string is not its own evidence (same split as
  nightshift's typed refusal beside free-text `blocked[]`). `KnowledgeVerifier`
  adjudicates paths against canon presence + chapter ordering: **contradiction** (claimed
  witnessed, wasn't there / no such event), **premature_knowledge** (knew it before it
  happened), **unsupported_path** (no verifiable path — a GAP, not a violation),
  **self_declared** (inferred/assumed claim no backing), **legal_extension** (path holds).
  Advisory: it reports; only an author act changes canon. NOT checked (named, unbuilt):
  the teller's own path — a recursive knowledge chain.
- **SceneProposal** = proposed scene changes, verified against bible + canon
- **Guardrails**: Consent tracking is pairwise and scoped. DSI = dangerous subject introduction. AII = audience impact index with validity profiles.
- **Context Drift**: Narrative mode tracking with hysteresis, genre escalation gating, register shift detection, mode chatter warnings.
