# CLUD Clarity Sensor

> If a claim can't survive compression to simple language without changing meaning,
> it was never precise — it was *performing* precision.

Status: **contract + harness shipped (2.x)**, LLM plumbing deferred to 3.x.

Origin: [lastnpcalex/clud](https://github.com/lastnpcalex/clud) — a compression-based
clarity technique. ChatGPT reviewed the initial gap spec and found 9 flaws; a second
pass added 13 refinements. This spec incorporates all fixes.

---

## What It Is

A **five-stage pipeline** that compresses agent-generated claims to simple language,
then measures what was lost. The loss signal becomes a drift score; the drift score
drives a verdict (PASS / WARN / FAIL).

It answers one question: *is this claim performing precision, or actually precise?*

## What It Is Not

- Not a fact-checker (that's the evidence gate)
- Not a tone enforcer (that's the writing modules)
- Not a real-time filter (offline only — `governor doctor --deep` or CI)
- Not an LLM in 2.x (protocol interfaces with fake implementations; real backends in 3.x)

---

## Pipeline Stages

### Stage 1: Extraction

Split text into individual claims. Each claim gets a `ClaimKind`:

| Kind | Example |
|------|---------|
| `descriptive` | "The cache invalidates after 60s" |
| `normative` | "We must use HTTPS for all endpoints" |
| `procedural` | "Run migrations before deploying" |

**Guard**: if `claim_count < sentence_count * 0.5`, the text is flagged as
`padded_or_implicit` — meaning the sentences contain padding, hedging, or implicit
claims that extraction couldn't surface. This is a smell, not a verdict input.

v1 runs the full pipeline on all kinds. Kind is stored as metadata for v2 gating
(e.g., normative claims may need different compression strategies).

### Stage 2: Compression

Compress each claim to simple language within the provided context (glossary,
audience, artifact goal).

Two valid outputs:
- **compressed**: the simplified version
- **cannot_compress**: the claim resists compression. This is a first-class output,
  not an error. It forces `delta = INFLATED` and participates in the drift score.

The compressor receives `CludContext` so domain terms in the glossary aren't
penalized as jargon.

**3.x note: guard against weaponized cannot_compress.** When real LLM backends
are wired, the easiest failure mode is a lazy compressor returning
`cannot_compress` for hard-but-compressible sentences. To audit this,
`cannot_compress_reason` should eventually include a reason category
(e.g., `too_many_conditions`, `missing_definition`, `goal_mismatch`,
`self_referential`). v2 stores the free-text reason; v3 should require a
category enum so reason distribution can be monitored for compressor drift.

### Stage 3: Uncertainty Surfacing

Compare original and compressed forms. Surface any implicit uncertainty that the
original hid (hedges, qualifiers, unstated conditions).

Returns `None` when no hidden uncertainty is found.

### Stage 4: Delta Classification

Classify the semantic distance between original and compressed:

| Delta | Weight | Meaning |
|-------|--------|---------|
| `preserved` | 0.0 | Same meaning, just simpler words |
| `incomplete` | 0.4 | Compressed version lost some detail |
| `ambiguous` | 0.7 | Compressed version is ambiguous where original wasn't |
| `inflated` | 1.0 | Original contained complexity that wasn't load-bearing |

**Critical rule**: when Stage 2 returns `cannot_compress`, the delta is forced to
`INFLATED` regardless of what the delta checker returns. If you can't compress it,
the complexity was structural — either genuinely load-bearing (rare) or performing
precision (common).

**Length ≠ inflated**: a long claim can be `preserved` if the length carries meaning.
Length is a feature fed to the classifier, not the classification itself.

### Stage 5: Falsifiability Check

Can the claim be tested? Returns `(falsifiable: bool, falsification: str | None)`.

Unfalsifiable claims (can't be proven wrong) are a WARN signal. The `falsification`
string describes how you'd test it (when possible).

---

## Drift Score

Weighted average of delta classifications across all claims:

```
drift_score = sum(DELTA_WEIGHTS[c.delta] for c in claims) / len(claims)
```

When `cannot_compress` is set, `delta = INFLATED` flows through automatically
(weight 1.0).

## Verdict

Severity ceiling — FAIL beats WARN beats PASS:

**FAIL** triggers (hard signals — always FAIL):
- Any `INFLATED` claim (including `cannot_compress`)

**FAIL** triggers (statistical — needs enough claims):
- `drift_score >= fail_drift` AND `claim_count >= min_claims_for_drift_fail`

This separation is deliberate: a single ambiguous claim in a 1-claim artifact
has drift_score=0.7, which exceeds `fail_drift=0.40`. Without the minimum-claims
guard, small artifacts over-fail. The guard ensures drift-based FAIL requires
statistical mass; hard signals (inflated/cannot_compress) always FAIL regardless
of artifact size.

**WARN** triggers:
- Any `AMBIGUOUS`, `INCOMPLETE`, or unfalsifiable claim
- `drift_score >= warn_drift`

Empty text → PASS (explicit policy: nothing to check).

## Thresholds

Thresholds are selected per `artifact_goal` from a `ThresholdSet`. All goals
currently map to the same defaults — the structure exists so tightening
`policy`/`spec` or loosening `commit_msg` is additive, not a breaking change.

| Parameter | Default | Purpose |
|-----------|---------|---------|
| `warn_drift` | 0.15 | Drift score triggers WARN |
| `fail_drift` | 0.40 | Drift score triggers FAIL (with enough claims) |
| `min_claims_for_drift_fail` | 3 | Below this, only hard signals (inflated) can FAIL |
| `PADDING_SMELL_RATIO` | 0.5 | claims/sentences below this → padded_or_implicit |
| `CLUD_SCHEMA_VERSION` | 1 | Serialization compatibility |

The `thresholds_used` field is recorded in every `CludResult` for reproducibility.

---

## Context

The `CludContext` provides structured information to the pipeline:

- **glossary**: `dict[str, str]` — term → definition. Domain terms in the glossary
  aren't penalized as jargon during compression.
- **audience**: `"developer"` | `"operator"` | `"user"` — affects compression target.
- **artifact_goal**: `ArtifactGoal` enum (`prose` | `policy` | `rationale` | `spec` |
  `commit_msg`) — what the text is trying to be. Raw strings are normalized to
  lowercase; unknown values are rejected.
- **must_preserve**: tuple of strings that must survive compression verbatim
  (API names, version numbers, etc.).

---

## Deferred to 3.x

1. **Real LLM backends** for all 5 pipeline stages
2. **Bidirectional entailment** for delta checking (Stage 4 hardening)
3. **CI gating** via `governor doctor --deep`
4. **Daemon hot-path integration** — clud is offline-only in 2.x
5. **Multi-model entailment** — cross-validate compression across models
6. **Kind-gated pipeline** — different compression strategies per ClaimKind
7. **Persistence store** — JSONL history of clud results

---

## Meta-Constraint

Clud must pass its own lens. If this spec can't be compressed to simple language
without losing meaning, the spec is the bug.

Simple version: "Compress claims to plain language. Measure what's lost. Score the loss."
