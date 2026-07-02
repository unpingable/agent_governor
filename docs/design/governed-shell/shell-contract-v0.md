# Shell contract v0 — decision envelope, watch stream, RPC subset

**Status:** CANDIDATE (2026-07-02; = slice GS-1). Becomes the seed of
`docs/specs/shell-contract/v0.md` at GS-8. CANDIDATE means: GS-2/3/4/5
implement against this document; any need for a new kind/field returns HERE
for a version bump — downstream slices never improvise vocabulary.

Boundary law: shells orchestrate and render; AG decides. This contract is
AG's mouth — the surface shells (maude, phosphor's governed-session lane, any
future consumer) may rely on.

## 1. Closed vocabularies

- **decision kind (×6):** `intervention` · `violation` · `promotion` ·
  `docket_case` · `admissibility_question` · `operator_question`.
  (`autonomy_offer` is RESERVED for the parked v1 — not valid in v0.)
  Explicitly NOT kinds: campaign DECISIONS.md entries (documents, not queue
  items); nightshift unsettled claims (freshness reaches the docket via
  `_freshness_to_case` and arrives as `docket_case`).
- **urgency (×4):** `blocking` · `expiring` · `normal` · `info`.
  Shell mapping: interrupt on `blocking` + `expiring`; accumulate otherwise.
- **watch notification names:** `runtime.event` · `decision.event`
  (change ∈ `added` | `resolved` | `expiring`).
- **resolve errors:** `decision_not_found` · `option_not_available` ·
  `already_resolved`. Underlying subsystem refusals pass through VERBATIM —
  the door adds no refusal vocabulary of its own.

## 2. The decision envelope (`operator.decisions.list`)

Request: `{kinds?: [kind], session_id?: str, since_seq?: int,
include_resolved?: bool}` → `{items: [envelope], feed_seq: int}`

```json
{
  "decision_id": "dec_...",
  "kind": "intervention",
  "session_ref": "sess_...  | null",
  "created_at": "ISO-8601",
  "urgency": "blocking",
  "timeout_at": "ISO-8601 | null",
  "summary": "one line, human-first",
  "detail": { "...kind-specific, shape per source subsystem..." },
  "options": [
    {"key": "y", "label": "approve", "action": "approve", "args_schema": null},
    {"key": "n", "label": "deny",    "action": "deny",    "args_schema": null}
  ],
  "receipt_refs": ["..."],
  "why_ref": "receipt-or-event id | null",
  "refs": [{"kind": "nq_finding|ticket|receipt", "id": "..."}],
  "source": {"subsystem": "runtime.intervention", "native_id": "..."}
}
```

Rules:
- `options[].key` is single-char, unique per item; **the card prints it and
  the shell keymap derives from it** — no shell-invented verbs.
- `refs[]` ships in v0 (cheap, generic) so the future ops-casework lane rides
  the same envelope without a schema break. v0 emits it empty; consumers are
  P3.
- `detail` is source-shaped, not normalized — normalization is rendering's
  job; the envelope's common fields are the contract.
- The aggregator MINTS NOTHING: every item mirrors a native pending object
  (`source.native_id`); an item with no native backing is a bug, not a
  feature.

## 3. The one mutation door (`operator.decisions.resolve`)

Request: `{decision_id, option_key, args?}` — routed by `source.subsystem`:

| kind | routed to |
|---|---|
| intervention | `runtime.intervention.resolve` |
| violation | `commit.fix` / `commit.revise` / `commit.proceed` |
| promotion | `runtime.promotion.resolve` |
| docket_case | `DocketManager.rule_*` |
| admissibility_question | answer/waiver path (releases HELD launch when last question answered) |
| operator_question | records the answer against the asking subsystem |

Rules:
- The door FORWARDS, never replaces: the routed subsystem's receipt IS the
  receipt; the door emits none of its own.
- Docket rulings and admissibility answers are exposed ONLY through this door
  (their reads get plain RPC). One door = the queue is true in the protocol,
  not just the UI.
- Legacy `runtime.intervention.resolve` / `runtime.promotion.resolve` remain
  callable during transition, deprecated for shells at maude v3.0.
- Idempotence: re-resolving returns `already_resolved` with the original
  outcome; nothing mutates twice.

## 4. The watch stream (`operator.watch`)

Held JSON-RPC request over the existing socket (mechanism precedent:
`chat.stream`/`chat.delta`). Params: `{session_ids?: [id]|"all",
channels?: ["events","decisions"]}`. Pushes `runtime.event
{session_id, seq, event}` and `decision.event {change, item, feed_seq}` until
cancel/disconnect. Shells use a dedicated second socket connection.

**Durability stance (load-bearing):** the stream is a lossy accelerant, never
the source of truth. Notifications carry `seq`/`feed_seq`; on reconnect the
client resumes from `runtime.session.events since_seq` +
`operator.decisions.list since_seq`. EventBus JSONL stays canonical, AG sole
writer. Client state must be fully reconstructible from the polling surfaces;
a client that requires the stream is misbuilt.

## 5. Steering (`runtime.session.send_input`)

Request: `{session_id, text}` → rides `ControlAction(kind="send_input")` to
the adapter; emits new canonical EventKind `OPERATOR_INPUT`
(source_layer=OPERATOR). Adapter capability is honest
(`runtime.adapters.list`: claude_code true, gemini_cli false); unsupported →
typed refusal `send_input_unsupported`, never a crash, never a silent drop.
Steering widens nothing: downstream tool calls remain fully intercepted.
Unrecorded steering is invisible authority — the event is mandatory.

## 6. Read surfaces shells may rely on

`operator.decisions.list` · `operator.watch` · `runtime.session.*`
(create/launch/get/list/events/pause/resume/kill/fork) · `runtime.budget.get`
· `runtime.adapters.list` (GS-6) · `why.chain {anchor}` → ChainLink list with
DRILL/REPLAY/SYNTHETIC render prefixes (GS-6) · `docket.list/get` +
`admissibility.assessment` (GS-2, reads only) · `receipts.list/detail` ·
`governor.operator_snapshot` · `scope.escalate` (existing; the v0 widening
primitive) · probe state folded into `runtime.session.get` (GS-6).

**HELD launch state (new, GS-2):** a session created while admissibility
questions pend reports `status: "held"`; answering the last question (via the
door) transitions it to launchable. Exposure alone was insufficient —
something must hold the launch.

## 7. Compat policy

- This contract is versioned; shells pin `ag_shell_client` (which pins the
  contract). Breaking changes bump the version — alpha freedom applies until
  v1, after which the decision-envelope common fields and the closed
  vocabularies are stability-promised.
- The daemon's own `governor.methods` registry (read_only/mutating) is the
  authoritative method list; this document CITES it and enumerates the relied
  subset — it does not copy it.
- Unknown envelope fields: shells ignore-and-preserve (forward compat);
  unknown KINDS: shells render raw + flagged, never guess (the
  allowlist-recognition discipline).
