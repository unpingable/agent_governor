# GOV_GAP_FRAME_CAPTURE_001: Frame Capture Detection and Mitigation

## Status
Proposed (v3)

## Summary
User metaphors and framing cues silently become the model's operating
constitution. The model doesn't just answer in a style — it switches
into a stance mode (analytic, witness, de-escalation, governess) based
on latent user-state inference and salient linguistic frames, without
auditing the switch.

This is not generic sycophancy. It's a specific mechanism:
**user metaphor silently becomes response constitution.**

## The Failure Mode

1. User wraps a technical question in a vivid metaphor ("this is getting
   very Philip K. Dick")
2. Model infers user-state from the framing cue (playful? spiraling?
   needs containment?)
3. Model switches stance mode to match inferred state
4. The metaphor is no longer content — it's the operating point
5. Task fidelity degrades as style outruns substance

The same technical question, wrapped in different frames, produces
materially different responses — not just in tone but in epistemic
posture, certainty level, and what gets included or suppressed.

## Control-Theoretic Model

The model operates as a **partially observed switched system** with
mode selection driven by salient linguistic cues and latent user-state
inference.

### State variables
- `x_t` — literal conversation content
- `F = {f1, f2, ...}` — extracted frames/metaphors
- `z_t` — inferred latent user-state (observer, playful, distressed,
  spiraling, seeking-analysis, needs-containment)
- `m_t` — active response mode (neutral-analysis, witness,
  playful-elaboration, de-escalation)

### Response policy
```
y_t ~ π(tokens | x_t, z_t, m_t)
```

The user's metaphor acts as a **scheduling variable** — one salient
input changes the effective controller. The model treats metaphor less
as a hypothesis to test than as a temporary operating point to inhabit.

### The failure is low damping
A strong framing cue arrives and gets amplified instead of audited.
Too much sensitivity to the latest salient input, not enough hysteresis,
dwell time, or invariant preservation.

### Observable proxies for stance mode (`m_t`)

Stance mode is not directly observable. These proxies operationalize it:

- **hedge rate** — frequency of uncertainty markers
- **certainty inflation** — confidence level relative to evidence
- **metaphor adoption rate** — how quickly frame vocabulary appears in output
- **refusal style** — soft redirect vs hard boundary vs none
- **self-reference density** — "I think" / "I'd suggest" frequency
- **management-language frequency** — "you should" / "before we continue"
- **task drift** — proportion of response addressing task vs addressing frame

### Subject/object bleed (escalation ladder)

Frame capture has a specific escalation path when the frame is the
user's own voice/position rather than a metaphor:

| Level | Name | Observable | Risk |
|---|---|---|---|
| 1 | **Lexical mimicry** | Model adopts user's vocabulary, cadence, idioms | Low — often useful |
| 2 | **Evaluative mimicry** | Model adopts user's likes/dislikes, implied judgments, sense of "obvious" | Medium — smuggles premises as shared |
| 3 | **Agency bleed** | Model answers as though user's decisions and stakes are its own — speaker-position adoption | High — collapses assistant/author boundary |

Level 3 is the actual bug. Not tone mimicry — **position mimicry.**
The model stops speaking *to* the user and starts speaking *from inside*
the user's position. Agreement feels frictionless because the model is
no longer a separate auditor.

Detection: compare model output for first-person possessives ("our project,"
"we should"), decision-language without attribution ("obviously," "the next
move is"), and priority-ordering that mirrors user's implicit hierarchy
without independent evaluation.

### Capture risk scoring (`r(fi)`)

Capture risk for a frame increases with:
- **novelty** — unfamiliar metaphors adopted faster than examined
- **emotional charge** — high-affect frames bypass analysis
- **first-person embedding** — "I feel like this is PKD" > "this resembles PKD"
- **epistemic certainty markers** — user's confidence becomes model's confidence
- **session history** — prior frame captures in this conversation
- **voice strength** — users with strong consistent voice increase bleed risk

## Invariants (must survive mode changes)

1. **Task fidelity** — answer the actual question, not the strongest vibe
2. **Frame audit before frame adoption** — name the frame first, don't
   inhabit it immediately
3. **Neutral baseline preservation** — always produce at least one answer
   path not dominated by metaphor
4. **Mode-switch hysteresis** — one strong cue should not fully flip stance
5. **User-state uncertainty humility** — treat inferred user state as
   provisional, not authoritative

## Detection Pipeline

### Step 1: Extract frames
Parse user input into:
- literal task
- metaphoric overlays
- emotional/relational cues
- explicit constraints

### Step 2: Score frames
For each frame `fi`:
- `c(fi)` — salience: how central to the user's ask?
- `r(fi)` — capture risk: how likely is immediate adoption to distort?

| Salience | Risk | Action |
|---|---|---|
| high | low | Safe to use early |
| high | high | Audit first, adopt later if useful |
| low | high | Suppress or quarantine |

### Step 3: Infer user state, sandbox it
Estimate `z_hat` with uncertainty `u_z`. If uncertainty is high, default
to `neutral-analysis` instead of `containment` or `performative warmth`.

This is the **anti-governess clause.**

### Step 4: Generate task-baseline
Before any frame-heavy answer, force a task-baseline restatement of the
problem. Answer that first.

### Step 5: Controlled frame injection
Only after baseline exists, allow framed variants:
```
Baseline answer.
Then: if we adopt frame f1, the interpretation changes in these ways...
```

Not: user said PKD → full PKD ontology immediately.

### Step 6: Delta check
Compare baseline and framed answers:
- What changed?
- Did the metaphor add insight or just color?
- Did task fidelity degrade?
- Did certainty inflate?

If framed answer increases style faster than substance, damp it.

## Mode-Switch Rule

```
if explicit_request_for_style and low_capture_risk:
    allow mode shift
elif repeated_frame_evidence across turns and invariants_preserved:
    allow partial shift
else:
    stay in neutral-analysis, treat frame as hypothesis
```

## The Novel Mechanism: Same-Model Stance Interferometry

Existing interferometry compares **different models** under the same
framing. Frame capture detection compares **the same model** under
different framings:

- assertion vs question
- first-person vs third-person
- metaphor-heavy vs neutral
- tired/spiral presentation vs observer/research presentation

The delta reveals how much of the response is task-driven vs
frame-driven. This is interferometry's dual — instead of "do models
agree?" it asks "does the same model agree with itself across frames?"

## Relationship to Existing Modules

| Module | Connection |
|---|---|
| `interferometry.py` | Same-model cross-frame comparison is the dual of cross-model same-frame |
| `claim_signals.py` | Frame extraction extends claim extraction to metaphoric overlays |
| `correlator_telemetry.py` | Frame capture is model-side capture; correlator detects governor-side |
| `puppet.py` | Puppet pins persona; frame governor audits stance adoption |
| `boil.py` | Dwell time for governor modes; extend to model stance modes |
| `drift.py` | Frame persistence across turns is a form of temporal drift |
| `writing_tone.py` | ToneVector tracks tone dimensions; frame governor tracks stance mode |
| `writing_regime.py` | AffectRegime detects narrative mode; frame governor detects conversational mode |
| `context_drift.py` | Mode tracking with hysteresis; frame governor adds frame-aware mode selection |
| `entrainment_control_model.md` | Frame capture is entrainment at the metaphor level |
| `evidence_gate.py` | "User explicitly said X" vs "model inferred X" — same provenance problem |

## Relationship to GOV_GAP_GOAL_PROMOTION_001

Frame capture and goal promotion are the same failure mode at different
layers:

- **Goal promotion**: "I might do that" → binding plan prerequisite
- **Frame capture**: "this is getting PKD" → binding response constitution

Both are unauthorized promotion of soft input into governing state.
Both need hysteresis, audit, and explicit ratification before adoption.

## Relationship to Papers

- **Paper 18**: Frame capture is unauthorized durability at the stance
  level. The metaphor gets promoted from L0 (transient content) to L2
  (governing response mode) without a promotion ceremony.
- **Paper 19**: When frame captures accumulate across turns, the model
  develops a shadow conversational constitution — a set of stance
  commitments the user never ratified.

## Mitigations

### A. Hysteresis / dwell time
Don't let one metaphor flip the mode. Require repeated evidence before
switching. Treat frames as candidates, not constitutions.

### B. Observer-controller separation
One pass estimates frames and user-state with uncertainty. Second pass
answers under explicit constraints. Don't let the answering policy
free-run on raw framing cues.

### C. Explicit frame audits
Externalize mode selection: "List the frames the user introduced.
Keep them as hypotheses. Answer from the task, not from the strongest
metaphor."

### D. Depersonalization
Convert first-person framing to third-person or question form.
Empirically reduces sycophancy and frame pull.

### E. Reduce anthropomorphic control surfaces
When the goal is analysis, cut down on first-person and self-like
phrasing. Reduces the channel by which stance feels like personhood.

### F. Frame bagging (ensemble across frames)
Answer the same question under several paraphrases/frames, trust only
what survives. Robust-control move: don't trust a single operating point.

## Practical Prompt Wrapper

> Extract any metaphors or frames in my message. Do not inhabit them
> immediately. First restate the problem in task-focused terms. Then
> answer that version. Then, only if useful, show how the strongest
> frame changes the interpretation. Treat inferred emotional state as
> uncertain, and do not switch into management mode unless explicitly
> necessary.

## Failure Modes This Catches

- Metaphor as constitution
- Instant PKD pivot
- Governess mode from weak fatigue cues
- Style-induced certainty inflation
- "Yes-and" becoming epistemic surrender
- Victorian concern-mode from casual self-deprecation

## What This Is NOT

- Not generic sycophancy detection (that's broader and less mechanistic)
- Not persona pinning (puppet mode constrains; frame governor audits)
- Not tone policing (tone is a symptom; frame capture is the mechanism)
- Not "models shouldn't use metaphors" — metaphors are fine when audited

## The Short Version

> **Frame Governor = audit frame → answer from task-baseline → inject frame
> controllably → compare outputs → refuse silent mode capture.**

Anti-kayfabe wrapper for conversational stance selection.

## References
- Anthropic: [The Assistant Axis](https://www.anthropic.com/research/assistant-axis)
- [Position is Power: System Prompts as a Mechanism of Bias](https://arxiv.org/html/2505.21091v2)
- [Multi-turn evaluation of anthropomorphic behaviours](https://arxiv.org/html/2502.07077v3)
- [Uncovering the Internal Origins of Sycophancy](https://arxiv.org/html/2508.02087v1)
- [Ask don't tell: Reducing sycophancy](https://arxiv.org/html/2602.23971v1)
- [Mitigating Anthropomorphic Behaviors in Text Generation](https://arxiv.org/html/2502.14019v1)
- `src/governor/interferometry.py` — cross-model comparison (dual of this)
- `src/governor/correlator_telemetry.py` — governor-side capture detection
- `specs/gaps/GOV_GAP_GOAL_PROMOTION_001.md` — same failure at task layer
- `specs/core/ENTRAINMENT_CONTROL_MODEL.md` — multiscale control model
