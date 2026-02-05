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
- **manuscript.py** — ManuscriptScanner for auto-populating canon from text (36 tests)
- **similarity.py** — TF-IDF similarity, trope detection, voice/tone analysis (41 tests)
- **context_drift.py** — Context drift detection, hysteresis-based mode transitions, genre escalation (64 tests)
- **guardrails.py** — Consent tracking (pairwise, scoped), DSI detection, AII with validity profiles, hard constraints (C1-C3), soft penalties (P1-P4) (123 tests)

**Total: 376 tests**

## Key Concepts

- **Bible** = decisions about the story (characters, world rules, tone, banned tropes)
- **Canon** = facts about the story (events that happened, active threads)
- **SceneProposal** = proposed scene changes, verified against bible + canon
- **Guardrails**: Consent tracking is pairwise and scoped. DSI = dangerous subject introduction. AII = audience impact index with validity profiles.
- **Context Drift**: Narrative mode tracking with hysteresis, genre escalation gating, register shift detection, mode chatter warnings.
