---
paths:
  - "src/nonfiction_governor/**"
  - "tests/test_nonfiction_*"
  - "tests/test_tone*"
  - "tests/test_cfi*"
  - "tests/test_doi*"
---
# Non-Fiction Governor

Academic writing governance: corpus management, DOI fetching, citation verification, tone profiling, CFI (contextual frame intrusion detection).

## Modules

- **types.py** — Source, Concept, Position, WritingClaim (40 tests)
- **corpus.py** — Corpus ledger, conflict detection (26 tests)
- **verifiers.py** — CitationVerifier, TerminologyVerifier, ConsistencyVerifier (25 tests)
- **doi.py** — DOI metadata fetching (CrossRef/DataCite)
- **tone.py** — ToneProfile (28 dimensions), analyze_text, ToneChecker, ToneViolation, ToneManager, generate_tone_guidance, extract_tone_profile (corpus analysis), compare_profiles (ProfileDeviation) (122 tests)
- **cfi.py** — CFI v0: NonfictionFrame (12 frames), Perspective (4 types), CFIFaultType (4 faults), CFIDetector, pattern-based detection, frame overuse tracking, normative creep windowed detection, scope violation detection (68 tests)

**Total: 281 tests**

## Key Concepts

- **Corpus** = your papers/sources. Concepts and positions extracted from them.
- **CFI** = Contextual Frame Intrusion. 12 frames (SCIENTIFIC, LEGAL, MORAL, etc.), 4 perspective types, 4 fault types. Detects when writing shifts frames inappropriately.
- **Tone** = 28-dimensional profile. Can ingest corpus to extract author's natural tone, then check new text against it.
