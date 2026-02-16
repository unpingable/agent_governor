# Canon Capture — Promote Chat Facts to Canonical Store

**Status:** gap
**Priority:** high (fiction UX — reduces friction between chat and structured data)
**Effort:** medium (2-3 sessions)
**Depends on:** CANON_AUTHORITY_PROMPT.md (quick fix should ship first)

## Problem

The fiction WebUI has two authority surfaces:
1. **Chat** — ephemeral conversation, not persisted as canon
2. **Sidebar panels** — Characters, World Rules, Forbidden Things (canonical, persisted)

Users naturally define their world in chat because the chat input is the most salient affordance. The sidebar requires switching context, clicking "+ Add Character", filling a modal. That's friction. The result: important canon facts live only in chat history and are lost across sessions.

## Solution

Detect "definition-ish" statements in chat and offer a lightweight promotion path to the canonical store. Two components:

### Component 1: Canon Capture Classifier

A deterministic pattern matcher that flags messages likely containing canonical definitions. Runs on user messages before they're sent to the backend.

**Detection patterns** (ordered by confidence):

```
EXPLICIT_MARKERS (high confidence):
  - "Character: X is ..."
  - "Rule: ..."
  - "World rule: ..."
  - "Backstory: ..."
  - "{Name}'s backstory is ..."

COPULA_DEFINITIONS (medium confidence):
  - "{ProperNoun} is {descriptor}" — "Bee is from Karsovik"
  - "{ProperNoun} is a {role}" — "Marcus is a blacksmith"
  - "{ProperNoun} has {trait}" — "Elena has green eyes"
  - "{ProperNoun} was {origin}" — "She was raised in the capital"

RELATIONSHIP_MARKERS (medium confidence):
  - "{Name} and {Name} are {relationship}" — "Bee and Fen are rivals"
  - "{Name} is {Name}'s {role}" — "Marcus is Elena's father"

WORLD_BUILDING (medium confidence):
  - "In this world, ..." / "In {setting}, ..."
  - "Magic works by ..."
  - "The law says ..."
  - "There is no ..." / "There are no ..."

CONSTRAINT_MARKERS (medium confidence):
  - "{Name} would never ..."
  - "{Name} can't / cannot ..."
  - "{Name} always ..."
  - "It's forbidden to ..."
```

**Implementation approach:**

Reuse `ManuscriptScanner` pattern infrastructure from `src/fiction_governor/manuscript.py` — it already has proper-noun extraction, dialogue detection, and deduplication. Add a new `CanonCaptureClassifier` class alongside it (or in a new module `src/fiction_governor/canon_capture.py`).

**Output schema:**

```python
@dataclass
class CapturedCanon:
    """A provisional canon fact detected in chat."""
    capture_type: CaptureType  # CHARACTER, WORLD_RULE, RELATIONSHIP, CONSTRAINT
    confidence: float          # 0.0-1.0
    entity_name: str | None    # Extracted proper noun if applicable
    statement: str             # The raw text that triggered detection
    suggested_field: str       # "description", "voice", "wont", "rule"
    source_message_id: str     # Chat message ID for provenance
```

**What NOT to detect:**
- Questions ("Is Elena tall?")
- Hypotheticals ("What if Elena had blue eyes?")
- Scene content / narration (dialogue lines, action descriptions)
- Meta-discussion ("I'm thinking about making her a doctor")

The classifier should err on the side of **missing definitions** rather than flagging narration. False positives are more annoying than false negatives here — the user can always add manually.

### Component 2: Promote-to-Canon UI

When the classifier detects a definition-ish message, show a lightweight inline affordance in the chat response area.

**Option A: Inline chip (recommended)**

After the assistant's response, append a small non-intrusive chip:

```
┌──────────────────────────────────────────────────────┐
│ [Assistant response about Bee's background...]       │
│                                                      │
│  📌 Add to canon?  [Character: Bee] [World Rule]     │
└──────────────────────────────────────────────────────┘
```

Clicking opens the existing Add Character / Add World Rule modal, **pre-filled** with:
- Character name (extracted from the message)
- Description (the relevant statement)

**Option B: Draft queue (more conservative)**

Captured definitions appear in a "Pending" section at the top of the Characters/World Rules panel:

```
Characters
  ┌─────────────────────────────────┐
  │ 📋 Pending (2)                  │
  │   Bee — "is from Karsovik"  [✓] │
  │   Bee — "stubborn, loyal"   [✓] │
  └─────────────────────────────────┘
  Bee (confirmed)
  Elena (confirmed)
```

Clicking ✓ promotes to canon. Items expire after session end if not promoted.

**Recommendation:** Start with Option A (inline chip). It's lower effort, doesn't require sidebar changes, and the existing modal already handles the CRUD.

### Component 3: Assistant Integration

When canon is captured (whether via chip or draft queue), the assistant's system prompt should include a note about pending captures so it can reference them appropriately:

```
## Pending Canon
The following facts were mentioned in chat but not yet added to canon:
- Bee: "is from Karsovik" (pending — user has not confirmed)

Treat pending items as provisional. Do not reference them as established facts.
```

This prevents the assistant from treating captured-but-unconfirmed items as canonical, maintaining the authority boundary.

## Architecture

```
User message
    │
    ▼
CanonCaptureClassifier.scan(text)
    │
    ├─ No match → normal chat flow
    │
    └─ Match → CapturedCanon
         │
         ▼
    Response includes inline chip
         │
         ├─ User ignores → fact stays in chat only
         │
         └─ User clicks → pre-filled modal → POST /governor/fiction/characters
                                            → creates CANON anchor
                                            → fact is now canonical
```

## API Changes

### New endpoint

```
POST /governor/fiction/capture
  Request:  { "text": "Bee is from Karsovik", "message_id": "msg_123" }
  Response: { "captures": [{ "type": "character", "name": "Bee",
              "statement": "is from Karsovik", "confidence": 0.85,
              "suggested_field": "description" }] }
```

This endpoint is called by the frontend after each user message. It returns any detected canon-worthy statements. The frontend then renders the inline chip(s).

### Existing endpoints (unchanged)

- `POST /governor/fiction/characters` — still the canonical CRUD path
- `POST /governor/fiction/world-rules` — still the canonical CRUD path

The capture classifier does NOT write to canon. It only detects and suggests. The user must explicitly promote.

## Existing Infrastructure to Reuse

| Module | What to Reuse |
|--------|---------------|
| `fiction_governor/manuscript.py` | `ManuscriptScanner` pattern infrastructure, proper-noun extraction, `NON_CHARACTERS` stopword list, dedup logic |
| `governor/claim_signals.py` | `SignalExtractor` architecture (categories, confidence, context preservation), `ExtractionConfig` pattern |
| `governor/writing_intent.py` | `IntentClassifier` scoring model (multi-category, primary/secondary, confidence thresholds) |
| `fiction_governor/bible.py` | `Bible.add_character()`, `Bible.add_world_rule()` — existing persistence |
| `gov_webui/adapter.py` | `CharacterRequest`, `WorldRuleRequest` models — existing CRUD |
| `gov_webui/static/index.html` | `openModal('add-char-modal')` — existing modal, just pre-fill fields |

## Failure Modes

| Failure | Mitigation |
|---------|------------|
| Over-detection (flags narration as definitions) | Conservative patterns, require copula + proper noun, skip questions/hypotheticals |
| Under-detection (misses definitions) | Acceptable — user can always add manually. Better to miss than annoy. |
| Stale pending items | Expire pending captures at session end. Don't persist unfiled drafts. |
| Authority confusion (pending treated as canon) | System prompt explicitly marks pending as provisional |
| UI clutter (too many chips) | Cap at 2 chips per response. Batch multiple captures into one chip. |

## Scope Boundaries

**In scope:**
- Pattern-based detection of character/world/relationship definitions
- Inline promotion affordance (chip or draft queue)
- Pre-filled modal from detected content
- System prompt integration for pending items

**Out of scope:**
- LLM-based extraction (too expensive, recursive risk — model grading model)
- Auto-promotion (no silent writes to canon — user must confirm)
- Cross-session canon merging (separate feature)
- Conflict detection with existing canon (the CRUD endpoint already handles this via continuity anchors)

## Phasing

### Phase 1: Classifier only (backend)
- Build `CanonCaptureClassifier` in `src/fiction_governor/canon_capture.py`
- Add `/governor/fiction/capture` endpoint
- Tests: pattern matching, false positive filtering, confidence scoring
- No frontend changes yet — backend returns suggestions, nothing consumes them

### Phase 2: Inline chip (frontend)
- After user message, call `/governor/fiction/capture`
- If captures returned, render chip(s) below assistant response
- Chip click opens pre-filled modal
- Tests: E2E with Playwright

### Phase 3: System prompt integration
- Include pending captures in fiction system prompt
- Mark as provisional in assistant context
- Tests: verify assistant doesn't confirm pending as canonical

## Verification

1. Start fiction session, type "Bee is from Karsovik and she's stubborn"
2. Classifier returns: `[{type: "character", name: "Bee", statement: "is from Karsovik", field: "description"}, {type: "character", name: "Bee", statement: "stubborn", field: "description"}]`
3. Inline chip appears: `📌 Add to canon? [Character: Bee]`
4. Clicking opens Add Character modal with name="Bee", description="is from Karsovik; stubborn"
5. User confirms → character appears in sidebar → continuity anchor created
6. Assistant now treats "Bee is from Karsovik" as canonical fact

## Files

| File | Change |
|------|--------|
| `src/fiction_governor/canon_capture.py` | New — `CanonCaptureClassifier`, `CapturedCanon`, patterns |
| `tests/test_canon_capture.py` | New — pattern tests, false positive tests, confidence tests |
| `gov-webui/src/gov_webui/adapter.py` | Add `/governor/fiction/capture` endpoint |
| `gov-webui/src/gov_webui/static/index.html` | Add inline chip rendering, pre-fill modal on click |
