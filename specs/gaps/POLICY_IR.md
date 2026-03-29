# Gap Spec: Policy Intermediate Representation

**Status:** proposed
**Affects:** GovernorHooks, continuity anchors, intent compiler, chat_bridge renderers
**Date:** 2026-03-29
**Origin:** polyglot benchmark — empirical evidence that semantic slots, not English prose, are the real control surface

## Problem

Governor currently stores and transmits policy as English prose. System prompts built by `GovernorHooks`, anchor descriptions, intent templates — all are natural language strings treated as authoritative. But natural language is lossy, unversioned, and provider-sensitive. When a model update changes how Claude interprets "be concise," the policy hasn't changed — the rendering has drifted. We can't detect that because the prose *is* the policy. There's no layer underneath to diff against.

The polyglot benchmark demonstrated something specific: structured semantic slots (`[B][NG][U][J]`, `[简][禁推][疑][J]`, `concise;no_guess;json`) achieve equivalent compliance to their English expansions at lower token cost. The English was never the authority — the semantic slots were. English is one possible lossy expansion of them.

**The architectural seam:** `system_prefix` is currently pretending to be policy, but it's really compiled output.

## Current Leakage Points

### GovernorHooks system prompts (`chat_bridge.py`)

`GovernorHooks._build_system_prompt()` assembles mode-specific prose strings that get prepended to every message. These strings encode policy decisions (what the model should enforce, what it should flag) but are not versioned, hashed, or diffable as policy. They're build artifacts pretending to be source.

### Continuity anchor descriptions

`governor continuity anchor add --description "Never use eval() in production code"` — the `--forbidden` pattern is structured, but the `--description` is prose the model reads during gate checks. If the description matters for compliance (and it does — it's what the model uses to understand intent), it's unversioned authority in a prose costume.

### Intent compiler templates

`session_start`, `task_scope`, `verification_config` are already structured forms that compile to constraints. This is halfway to a policy IR — structured input, deterministic compilation, receipt emission. But the compiled output is still English prose fed to the model. The templates are policy; the compiled text is a rendering.

## Proposed Architecture

### Control slots as canonical policy

A `ControlSlot` is a named semantic directive with a stable identity:

```python
@dataclass(frozen=True)
class ControlSlot:
    slot_id: str          # "CONCISE", "NO_GUESS", "OUTPUT_JSON"
    description: str      # human-readable documentation (NOT authority)
    category: str         # "output_format", "epistemic", "behavioral"
```

A `ControlVocabulary` is a versioned, content-addressed set of slots:

```python
@dataclass(frozen=True)
class ControlVocabulary:
    vocab_id: str         # "governor_core_v1"
    version: str          # semver
    slots: frozenset[ControlSlot]
    content_hash: str     # H(canonical_json(slots))
```

Policy is expressed as a slot set, not a string:

```python
policy = SlotSet(
    vocab="governor_core_v1",
    active={"CONCISE", "NO_GUESS", "OUTPUT_JSON", "LIST_UNCERTAINTY"},
)
```

### Backend renderers

A renderer compiles a `SlotSet` into a provider-specific prompt fragment:

```python
class Renderer(Protocol):
    renderer_id: str      # "claude_prose_v2", "gpt_dsl_v1"
    version: str

    def render(self, slots: SlotSet, context: RenderContext) -> str:
        """Compile slot set to provider-specific control syntax."""
        ...
```

Different renderers for different backends:

- `claude_prose_v1` → `"Be concise. Do not guess. Return valid JSON."`
- `claude_compact_v1` → `"concise;no_guess;json"`
- `gpt_dsl_v1` → `"[B][NG][U][J]"`
- `ollama_direct_v1` → whatever works for the local model

The rendered string is a **build artifact**, not policy. It's disposable and reproducible from (slot_set, renderer, version).

### Renderer receipts

Every prompt assembly emits a receipt:

```python
{
    "gate": "prompt_render",
    "vocab_id": "governor_core_v1",
    "vocab_hash": "sha256:a3f...",
    "slot_set": ["CONCISE", "NO_GUESS", "OUTPUT_JSON"],
    "renderer_id": "claude_prose_v2",
    "renderer_version": "0.3.0",
    "rendered_hash": "sha256:e7b...",
    "verdict": "observe"
}
```

When a model update causes compliance drift, the receipt chain shows exactly which renderer/version was in use. Diff the rendered output between versions, correlate with benchmark regressions. No mystery.

### Benchmark promotion gate

Polyglot becomes a promotion gate for renderer candidates:

1. Candidate renderer (e.g., `claude_compact_v2`) is proposed
2. Benchmark suite runs: all tasks × candidate vs incumbent
3. Quality, compliance, and token cost are measured
4. Candidate promoted only if it meets threshold vs incumbent
5. Promotion receipt emitted with benchmark run ID and scores

This is straight Governor logic: no vibes, only promoted artifacts.

## Key Distinction

- **Canonical slot set** is policy. It's what you version, hash, and diff.
- **Human-readable expansion** is documentation. It explains what a slot means to humans.
- **Rendered prompt** is a build artifact. It's compiled output, disposable, reproducible.

This prevents prompt lore from sneaking back in wearing a fake mustache. If someone changes a renderer's output text and quality improves, that's fine — promote the new renderer version. But the policy (which slots are active) didn't change. If someone wants to change *which slots are active*, that's a policy change and goes through the normal Governor decision flow.

## Non-Goals

- **Not replacing all natural language everywhere.** User-facing messages, error text, documentation — all still prose. This is about the *control surface* between Governor and model, not all text.
- **Not making the benchmark winner automatically authoritative.** Promotion still requires human review. The benchmark provides evidence; the human decides.
- **Not a universal prompt language.** The slot vocabulary is Governor-specific. Other systems can define their own vocabularies if they want.
- **Not optimizing for minimum tokens at all costs.** Token savings are a nice side effect. The real value is separating policy from presentation so drift is detectable.

## Migration Sketch

### Phase 0: Benchmark harness (polyglot — exists)
Polyglot stays string-oriented. It benchmarks rendered outputs. No changes needed — it's already the right shape for a promotion gate.

### Phase 1: Define core vocabulary
Extract the implicit control semantics from existing `GovernorHooks` system prompts into named slots. Start with the slots that are already effectively structured (output format, epistemic constraints, behavioral directives). This is taxonomy, not new features.

### Phase 2: Renderer protocol + receipts
Implement `Renderer` protocol. Build one prose renderer per backend that reproduces current behavior. Wire receipt emission into `GovernorHooks._build_system_prompt()`. At this point, behavior is identical but the prompt assembly is receipted and the policy/rendering boundary exists.

### Phase 3: Benchmark gate
Wire polyglot (or a Governor-side equivalent) as a promotion check for renderer candidates. When a new renderer version is proposed, benchmark it against the incumbent on the standard task suite. Emit promotion receipt.

### Phase 4: Alternative renderers
Build compact/DSL/CJK renderers. Benchmark them. Promote the ones that hold quality. Context savings accrue naturally for long governed sessions where the system prompt is resent every turn.

## Dependencies

- `polyglot` benchmark harness (exists, `~/git/polyglot`)
- `GovernorHooks._build_system_prompt()` in `chat_bridge.py`
- `context_manifest.py` (already tracks what went into the system prompt)
- `gate_receipt.py` (receipt emission infrastructure)
- `intent_compiler.py` (existing structured-form-to-constraint compilation)
