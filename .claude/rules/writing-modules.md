---
paths:
  - "src/governor/writing_*.py"
  - "tests/test_writing_*"
---
# W5 Writing Modules

Spec application from fic.md, nonfic.md, anc.md, tone.md, writingconstraints.md. 11 modules, 922 tests.

## Modules

- **writing_patterns.py** — 18 pattern banks: hedge, self-reference, apology/meta, committee, meaning-word, normative, causal humility, falsifier, strawman, anxiety hedge, governance artifacts, institutional markers, bad exit, inflated weight, instruction filler, fake confidence, premature closure, bureaucratic (68 tests)
- **writing_governance.py** — GovernanceVisibilityScorer (6 artifact categories), GovernanceLeakDetector (5 institutional voice types), SmoothingSuppressor, ExitShapeChecker (82 tests)
- **writing_tone.py** — ToneVector (6D), ToneEnvelope, 16 regime envelopes, ToneCollision, ToneStabilityController, ToneDriftScorer (95 tests)
- **writing_regime.py** — AffectRegime enum, RegimeVector, RegimeHysteresis, RpScorer, TragedyConstraints, SincerityTracker, DramaConstraints, MixerConfig (112 tests)
- **writing_nonfiction.py** — NfClaimLevel, NfClaimNode, PromotionGate, VelocityController, EpScorer, ReScorer, HedgeCalibrator, AhScorer, NleadChecker, NonfictionFailureDetector (89 tests)
- **writing_intent.py** — IntentCategory, IntentClassifier, 12 ancillary regime scorers (Ap, Fi, Au, Fp, Mt, Pa, Ut, Vv, De, Mc, Sa, Lm), RegimeCollision matrix (72 tests)
- **writing_constraints.py** — 11 structural constraints + Section 14 causal narration resistance (6 techniques, 10 failure modes) (118 tests)
- **writing_ticketing.py** — 14 prose + 11 code ticket types, recurrence detection, routing actions, auto-triage (102 tests)
- **writing_puppet.py** — Extended puppet constraints from puppet.md spec (98 tests)
- **writing_code.py** — Code-specific constraints from code.md spec (86 tests)
- **writing_router.py** — Writing-aware routing from specs
