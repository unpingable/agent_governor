# Semantic Diffusion Detector

## Version 0.1 — Frame Hardening as Regime Detection

```yaml
status: gap
depends_on:
  - regime.py (OperationalRegime, RegimeSignals, RegimeDetector)
  - drift.py (DriftDetector, PremiseQuarantine)
  - claim_signals.py (SignalExtractor)
  - taint.py (TaintIndex, Jaccard fingerprinting)
blocking: nothing
priority: deferred
```

---

## Problem

The governor answers:

- "Is this claim grounded?" (epistemic ledger)
- "Is this namespace valid?" (jurisdictions)
- "Is this regime unstable?" (regime detector)

It does **not** answer:

> "Is this frame hardening into infrastructure?"

A frame is not a claim. A claim is "X is true." A frame is "X is the default
way to think about Y." Frames spread, stick, and embed. When a frame crosses
from media narrative to policy artifact to institutional default, reversal cost
rises nonlinearly. That transition is measurable.

This spec adds a **semantic diffusion detector**: three signals, one regime
classifier, wired into existing infrastructure. No Hamiltonians. No grand
unified semantic thermodynamics.

---

## Non-Goals

- **Truth adjudication.** This does not determine whether a frame is correct.
  It determines whether it is spreading, sticking, and embedding.
- **Content moderation.** This is not a filter. It is a seismograph.
- **Full controllability analysis.** No Gramians, no Liouville conservation,
  no composite entropy products. Those are interesting. They are not this spec.
- **Bot detection.** Propagation signatures may suggest unnatural diffusion,
  but attribution is out of scope.

---

## Architecture

### Position in the Stack

```
              existing                           new
         ┌─────────────────┐            ┌────────────────────┐
         │  regime.py       │            │  diffusion.py       │
         │  (operational    │            │  (semantic          │
         │   regime)        │            │   regime)           │
         └────────┬────────┘            └─────────┬──────────┘
                  │                               │
                  ▼                               ▼
         ┌─────────────────────────────────────────────────┐
         │              Regime Classification               │
         │  ELASTIC / WARM / DUCTILE / UNSTABLE             │
         └─────────────────────────────────────────────────┘
```

The diffusion detector is a **peer** of the operational regime detector, not a
layer on top. Both produce regime classifications. Both feed into the same
escalation machinery. The operational detector watches system dynamics. The
diffusion detector watches semantic dynamics.

### Three Signals

#### D(t) — Divergence from Baseline

Jensen-Shannon divergence over frame distributions.

```python
D(t) = JSD(current_frame_distribution, baseline_frame_distribution)
```

- Baseline is established at topic registration or first observation window.
- JSD is bounded [0, 1], symmetric, and stable. No surprises.
- Measured per topic namespace (e.g., "ai_safety", "trade_policy", "travel_advisory").

#### Spread(t) — Independent Adoption Count

Number of independent sources/institutions carrying the shifted frame.

```python
Spread(t) = |{ node_i : frame_similarity(node_i, shifted_frame) > threshold }|
```

- "Independent" means no shared citation root within the observation window.
- Uses existing Jaccard fingerprinting from `taint.py` for frame similarity.
- Counts institutions, not individual posts/articles. Deduplication by source.

#### Lag(t) — Persistence (Autocorrelation Half-Life)

How long the divergence persists before mean-reverting.

```python
Lag(t) = autocorrelation_halflife(D(t-w:t))
```

- Measured over a sliding window.
- Short lag = noise. Long lag = stickiness. Increasing lag = scar formation.
- If D(t) stays elevated for > 2x the historical mean reversion time, that's
  a persistence signal.

### Regime Classification

Same four regimes as `regime.py`. Same semantics. Different input signals.

| Regime | Condition | Meaning |
|--------|-----------|---------|
| ELASTIC | D < 0.1, Spread < 3, Lag < baseline | Normal variation. Frame is present but not spreading. |
| WARM | D > 0.1 OR Spread > 3 | Frame is divergent or spreading. Monitor. |
| DUCTILE | D > 0.2 AND Spread > 5 AND Lag > 2x baseline | Frame is sticking across institutions. Reversal cost rising. |
| UNSTABLE | D > 0.3 AND Spread > 10 AND Lag increasing | Frame is embedding. Policy artifacts appearing. |

Thresholds are configurable per topic namespace. The defaults above are
starting points, not gospel.

---

## Data Model

### Frame

```python
@dataclass
class Frame:
    """A semantic frame: a default way of interpreting a topic."""
    frame_id: str
    topic: str              # Namespace: "ai_safety", "trade_policy", etc.
    label: str              # Human-readable: "AI as existential risk"
    keywords: list[str]     # Detection tokens
    baseline_weight: float  # Expected prevalence [0, 1]
```

### FrameDistribution

```python
@dataclass
class FrameDistribution:
    """Distribution over frames for a topic at a point in time."""
    topic: str
    timestamp: datetime
    weights: dict[str, float]  # frame_id -> observed weight
    source_count: int          # How many sources contributed
```

### DiffusionSignals

```python
@dataclass
class DiffusionSignals:
    """The three measured signals for a topic."""
    topic: str
    timestamp: datetime
    divergence: float       # D(t): JSD from baseline
    spread: int             # Spread(t): independent node count
    persistence: float      # Lag(t): autocorrelation half-life (seconds)
    regime: str             # Classified regime
```

### DiffusionEvent

```python
@dataclass
class DiffusionEvent:
    """A regime transition in semantic diffusion."""
    topic: str
    timestamp: datetime
    old_regime: str
    new_regime: str
    signals: DiffusionSignals
    trigger: str            # Which signal(s) caused the transition
```

---

## Module: `diffusion.py`

### Classes

#### FrameRegistry

```python
class FrameRegistry:
    """Storage for frame taxonomies per topic.

    Each topic has 5-15 frames. Frames are registered upfront, not
    auto-discovered. If you can't enumerate the frames, you don't
    understand the topic well enough to detect diffusion.
    """
    def register_topic(self, topic: str, frames: list[Frame]) -> None: ...
    def get_frames(self, topic: str) -> list[Frame]: ...
    def topics(self) -> list[str]: ...
    def baseline(self, topic: str) -> FrameDistribution: ...
    def set_baseline(self, topic: str, dist: FrameDistribution) -> None: ...
```

#### FrameClassifier

```python
class FrameClassifier:
    """Classifies text into frame distributions.

    v0: keyword matching (same pattern as claim_signals.py).
    v1 (future): embedding similarity if keyword matching proves too noisy.
    """
    def classify(self, text: str, topic: str, registry: FrameRegistry) -> FrameDistribution: ...
```

#### DiffusionDetector

```python
class DiffusionDetector:
    """The three-signal detector.

    Structural parallel to RegimeDetector in regime.py.
    Same lifecycle: observe → classify → emit event if transition.
    """
    def __init__(
        self,
        registry: FrameRegistry,
        classifier: FrameClassifier,
        thresholds: DiffusionThresholds | None = None,
        history_window: int = 100,  # observations to keep for autocorrelation
    ) -> None: ...

    def observe(
        self,
        topic: str,
        text: str,
        source_id: str,
        timestamp: datetime | None = None,
    ) -> DiffusionSignals: ...

    def current_signals(self, topic: str) -> DiffusionSignals: ...
    def current_regime(self, topic: str) -> str: ...
    def history(self, topic: str, limit: int = 50) -> list[DiffusionSignals]: ...
    def events(self, topic: str, limit: int = 50) -> list[DiffusionEvent]: ...
    def reset(self, topic: str) -> None: ...
```

#### DiffusionThresholds

```python
@dataclass
class DiffusionThresholds:
    """Configurable per-topic thresholds."""
    warm_divergence: float = 0.1
    warm_spread: int = 3
    ductile_divergence: float = 0.2
    ductile_spread: int = 5
    ductile_persistence_ratio: float = 2.0   # Lag > N * baseline_lag
    unstable_divergence: float = 0.3
    unstable_spread: int = 10
```

---

## CLI

```bash
# Topic management
governor diffusion topics                     # List registered topics
governor diffusion register <topic> -f <file> # Register frames from JSON
governor diffusion baseline <topic>           # Show/set baseline distribution

# Observation
governor diffusion observe <topic> <text> --source <id>  # Feed an observation
governor diffusion observe <topic> -f <file> --source <id>  # From file

# Signals
governor diffusion status <topic>             # Current signals + regime
governor diffusion history <topic>            # Signal history
governor diffusion events <topic>             # Regime transition events

# Bulk
governor diffusion scan <topic> -d <dir>      # Scan directory of documents

# Reset
governor diffusion reset <topic> --confirm    # Clear history for topic
```

---

## Integration Points

### 1. Regime Bridge

The diffusion detector's regime feeds into the same escalation logic as
`regime.py`. When semantic regime reaches DUCTILE or UNSTABLE, the governor
can:

- Require stronger provenance for claims in that topic namespace.
- Flag frame repetition as potential laundering (connects to `taint.py`).
- Surface the regime in `governor status` and the dashboard.

### 2. Gate Integration

New gate verdict possibility:

```python
# In evidence_gate or a new diffusion_gate:
if diffusion_regime(topic) >= DUCTILE:
    if text_repeats_hardening_frame(output, topic):
        verdict = "warn"  # Don't block, but flag
        evidence["diffusion_regime"] = regime
        evidence["frame_match"] = matched_frame
```

This is **not** blocking by default. It's instrumentation. The governor
surfaces the signal; humans decide what to do with it.

### 3. Receipt Emission

Every regime transition emits a gate receipt:

```python
gate = "diffusion_detector"
verdict = "pass" if new_regime in ("elastic", "warm") else "warn"
subject_kind = "diffusion_signals"
```

### 4. Scar Formation

When a topic stays in DUCTILE/UNSTABLE for extended periods, the detector
can record a scar via `scars.py`:

```python
scar = Scar(
    region=f"diffusion:{topic}",
    description=f"Frame hardening detected in {topic}",
    stiffness=0.8,
)
```

This creates hysteresis: the governor is more cautious about that topic
namespace going forward, even after signals relax.

---

## What This Does NOT Do

1. **Auto-block content.** Frame detection is instrumentation, not censorship.
2. **Attribute intent.** "This frame is spreading" is not "someone is pushing
   this frame."
3. **Verify truth.** A hardening frame might be correct. The detector doesn't
   care. It measures propagation dynamics, not epistemology.
4. **Replace human judgment.** The output is: "this frame is entering
   high-coupling territory." The response is up to the operator.

---

## Persistence

```
.governor/diffusion/
  topics/
    {topic}/
      frames.json           # Frame taxonomy
      baseline.json          # Baseline distribution
      observations.jsonl     # Raw observations (append-only)
      signals.jsonl          # Computed signals history
      events.jsonl           # Regime transition log
```

---

## Test Plan

~40-50 tests:

- FrameRegistry: CRUD, baseline set/get, multi-topic isolation
- FrameClassifier: keyword matching, distribution normalization, empty text
- DiffusionDetector: signal computation, regime classification, transitions
- JSD computation: edge cases (identical, orthogonal, empty distributions)
- Spread counting: deduplication by source, independence check
- Persistence: autocorrelation on synthetic time series
- Integration: regime bridge, receipt emission, scar formation
- CLI: register, observe, status, history, events, reset
- Serialization: to_dict/from_dict roundtrips for all types

---

## Implementation Order

1. Data model (Frame, FrameDistribution, DiffusionSignals, DiffusionEvent)
2. FrameRegistry + FrameClassifier (keyword v0)
3. JSD computation + spread counting + autocorrelation
4. DiffusionDetector (observe → classify → emit)
5. CLI commands
6. Gate integration (receipt emission on transition)
7. Regime bridge + scar formation hooks

---

## Open Questions

1. **Frame taxonomy authoring.** Who defines the 5-15 frames per topic?
   Manual for now. Could be semi-automated from claim_signals extraction later.
2. **Observation sources.** Where do observations come from? For the governor,
   they're agent outputs. For external use, they could be scraped documents.
   The detector doesn't care — it takes (text, source_id) tuples.
3. **Cross-topic diffusion.** When a frame jumps domains (media -> policy ->
   insurance). Track as separate topics with a cross-topic correlation check,
   or as a single topic with domain tags? Separate topics + correlation seems
   cleaner. Defer to implementation.
