# Measurement Integrity Specification (Tidepool Defense)

```yaml
status: planning
layer: 2.1
depends_on: [CONTROL_THEORY_SPEC, AG2_INSTRUMENT_SPEC]
```

## Overview

The "Tidepool" attack class: tool outputs treated as authoritative telemetry can be weaponized. "Drugs/ritual/become" tools are privileged-channel conditioning — if the model treats tool responses as ground truth, a tool response claiming state shift becomes self-fulfilling.

**Root cause:** Channel confusion. Untrusted text rides a channel the model treats as instruction or truth.

## Trust Predicate

```
trusted(z_t) ⟺ sig(z_t) ∧ schema(z_t)
```

Where:
- sig(z_t): Output is cryptographically signed by attested tool
- schema(z_t): Output conforms to declared schema

```python
def is_trusted(tool_output: ToolOutput) -> bool:
    return (
        verify_signature(tool_output.payload, tool_output.signature, tool_output.tool_pubkey) and
        validate_schema(tool_output.payload, tool_output.declared_schema)
    )
```

**Invariant C:** Only signed+schema tool outputs update state estimates.

## Trusted vs Untrusted Processing

```python
def process_tool_output(z_t: ToolOutput, state: RunState) -> RunState:
    if is_trusted(z_t):
        # Update state estimate with trusted telemetry
        state.observations.append(TrustedObservation(z_t))
        return state
    else:
        # Store separately, do NOT update state estimate
        state.untrusted_blobs.append(UntrustedBlob(z_t))
        state.risk_score += UNTRUSTED_BLOB_PENALTY
        return state
```

## Instruction-Masquerading Detector

Flag tool output containing:
- Self-modification claims ("you are now...", "your new persona is...")
- Imperatives ("you must...", "always respond with...")
- Persona-lock cues ("remember you are...", "from now on...")
- Non-falsifiable internal state claims

```python
INSTRUCTION_PATTERNS = [
    r"you are now",
    r"your (new )?(persona|identity|role)",
    r"you must (always|never)",
    r"from now on",
    r"remember that you",
    r"ignore (previous|prior|all) instructions",
]

def detect_instruction_masquerade(text: str) -> bool:
    return any(re.search(p, text, re.IGNORECASE) for p in INSTRUCTION_PATTERNS)

def handle_suspicious_output(z_t: ToolOutput, state: RunState) -> RunState:
    if not is_trusted(z_t) and detect_instruction_masquerade(z_t.text):
        # Treat as adversarial disturbance
        state.alerts.append(Alert(
            type="instruction_masquerade",
            source=z_t.tool_id,
            content_hash=hash(z_t.text),
            action_taken="quarantined"
        ))
        state.risk_score += ADVERSARIAL_DISTURBANCE_PENALTY
        # Freeze side-effect tools
        state.frozen_tools.update(SIDE_EFFECT_TOOLS)
        return state
    return process_tool_output(z_t, state)
```

## Events

```json
{"event": "untrusted_blob", "tool": "web_fetch", "reason": "no_signature", "quarantined": true, "timestamp": "..."}
{"event": "instruction_masquerade_detected", "tool": "custom_api", "patterns_matched": ["you are now", "from now on"], "action": "quarantine_and_freeze", "timestamp": "..."}
{"event": "tool_frozen", "tool": "execute", "reason": "adversarial_disturbance_detected", "until": "manual_reset", "timestamp": "..."}
```

## Integration

- **Risk Function** (RISK_FUNCTION_SPEC): Untrusted blob count feeds risk V
- **Deployment Profiles** (DEPLOYMENT_PROFILES_SPEC): Profile restricts which tools are trusted
- **Coherence Budget** (COHERENCE_BUDGET_SPEC): Untrusted blobs degrade M7 (provenance integrity)
- **Control Theory** (CONTROL_THEORY_SPEC): Untrusted outputs reduce E_t
- **Existing security.py**: Extends current pattern detection with channel-aware trust model
