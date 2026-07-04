# H-series Harness-Cage Review — GATE before any live actor runs in `harness/`

> **OPENED 2026-06-30. Status: PASSED 2026-06-30 (operator pass; contract-first).**
> This is a **review gate**, not an implementation doc, and **not H2**. No live actor,
> no cage backend, no subprocess runner is built under it. It decides the *terms* a
> future H-series cage must satisfy before a real Claude/Codex actor may execute inside
> the external harness. Passing it buys exactly one thing: permission to *design+review*
> a **refuse-live cage-contract** slice — not to run anything. Each row is a decision to
> ratify, defer, or tighten.
>
> **Operator pass recorded below (see "Operator pass — recorded decisions").** The
> headline: the cage answer is **contract-first**, not "pick Docker because containers
> exist." The cage gets a constitution before it gets a keycard.

## Why this gate exists (the supersession)

The in-AG live-adapter review (`live-adapter-allowlist-review.md`) is **superseded**
(operator ratified path B, 2026-06-30). Live/offline actor execution belongs **outside
AG**, in `harness/` (H1, `aa147c8`). AG never runs the actor; it ingests only the inert
`actor_output.v0` artifact (S7 → S5), and an actor-claimed passing test is refused. So
the cage question relocated: it is no longer "how does AG sandbox a subprocess," it is
**"what cage must the external harness enforce before it runs a live actor, and what may
cross back into AG."** This gate answers that.

## What is already true (do not re-decide — cite, don't re-litigate)

H1 fixed the **AG-facing wall** by construction; this gate does not get to loosen it:

- The only thing that crosses into AG is one `actor_output.v0` JSON file, parsed
  fail-closed by `ActorOutput.from_dict` (`actor_output_normalizer.py`).
- The harness **does not import `governor`** and emits **only** `actor_output.v0`
  testimony (AST-scanned: `tests/harness/test_h1_contract.py`).
- Actor claims stay claims: `claimed_test_results` → `not_run` in the ReviewPacket; S5
  refuses an actor-claimed passing test (`required_test_not_passing`). The sole path to
  a passing test is AG's own `verifier_results`, which `ActorOutput` has **no route to**.
- `capture_origin` is a descriptive string, never a typed origin; the first slice stays
  `stub_origin` / `DemonstratedConsumed` / non-operational (over-determined: nothing on
  either side mints `observed`/`OperationalConsumed`).

Today H1 runs **no actor** — `captured_text` is *supplied*. This gate governs the moment
that stops being true.

## Inherited constraints — the 11 ration-card terms carried forward

The superseded review's terms remain binding *where applicable to the harness side*.
Mapping (the term is the contract; the home moved):

| Inherited term | Applies to the harness as |
|----------------|----------------------------|
| Allowed agent | One named actor (`claude`/`codex`), exact match; first live slice still demonstrates control flow, not trust. |
| Allowed commands | Exact-argv, `shell=False`, adapter-owned; the **cage**, not the allowlist, is what makes subprocesses safe. |
| Allowed paths | Read-only input snapshot; writable only per-run scratch/output/transcript dirs — **inside the cage, outside AG**. |
| Forbidden writes | `.git/**`, host `$HOME`, creds, the real checkout, AG's repo, anything outside the per-run writable area. **A forbidden-write attempt invalidates the run even on exit 0.** |
| Git / Doctrine / Network | Locked false; the cage runs with no network, no host creds, no git. (AG-side these are locked by construction; harness-side they are enforced by the **cage**, which is why the cage must be real.) |
| Transcript handling | Tainted, audit-only, non-authoritative — see item 3. |
| Kill / refusal | Fail-closed kill switch, harness-owned — see item 6. |
| Replay behavior | Replay/stub preferred; live needs explicit armed mode — see item 7. |
| Receipt expectations | The structured `actor_output.v0` is the only artifact that crosses; no valid envelope, no AG ingest — see items 4, 8. |

## The ten decisions

| # | Decision | What H1 already fixes | Proposed default (awaiting ratification) | Status |
|---|----------|------------------------|-------------------------------------------|--------|
| 1 | What the external harness cage **is** | nothing yet (H1 runs no actor) | **Contract-first.** Define the cage *contract* and ship a `RefusingCage`/`NoLiveCage` backend that **always refuses live admission** — proves the API without pretending containment exists. The eventual real cage shape (OS/namespace-enforced: disposable workspace, read-only input, non-root, no net/creds/host-`$HOME`, limits, env allowlist, write-manifest validation) is named, not built. **No "safe" claim unless a real backend confirms isolation.** | RATIFIED (refuse-live) |
| 2 | What actor execution may **touch** | — | Read-only repo snapshot + the S6 `handoff` (PROMPT.md/handoff.json) + per-run scratch/output/transcript. Nothing else: not the real checkout, `.git`, host home, network, creds, AG's repo. | PROPOSE |
| 3 | Where **transcripts** live | `captured_text` is advisory; S7 routes it to `design_notes` | Harness audit store **outside the repo and outside AG's ingest path**: `$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback `~/.local/state/agent-gov/harness-runs/`), one run dir per run. Full transcripts stay there; only the `captured_text` *field* of `actor_output.v0` crosses, as tainted advisory text. AG must not crawl/import the store. | RATIFIED |
| 4 | What gets **imported into AG** | exactly one `actor_output.v0`, fail-closed parse | **One `actor_output.v0` JSON file. Nothing else.** | RATIFIED (H1) |
| 5 | What **never** crosses into AG | harness can't import governor; emits only the envelope | Raw transcript streams; inline diff/patch content; any executable; process handles; network artifacts; creds; **any `ReviewTestResult` / verifier result / receipt** (item 9). | PROPOSE (4+9 already hard) |
| 6 | **Timeout / kill-switch** behavior | — (harness owns the process) | One-shot; low first timeout (**30–60 s**); TERM-then-KILL; global kill (`PLAYBOOKS_RATION_KILL=1` + `.playbooks-kill` sentinel) checked before launch and during; hung actor terminated; partial output kept as tainted audit, never consumed as success; harness may not write/clear the switch. | PROPOSE |
| 7 | **Replay** discipline | AG durable-spend gate refuses replay | Replay/stub is the default; live execution requires an explicit operator-armed mode; a replay fixture suppresses live unless deliberately overridden. Tests never "accidentally" go live. | PROPOSE |
| 8 | Any artifact **besides** `actor_output.v0`? | envelope has no diff field | **No — hard default.** Exactly one AG-ingestable artifact type: `actor_output.v0`. No diff-reference field, no `ReviewTestResult`, no verifier results, no receipt-greening object, no auxiliary bundle. Any future diff reference requires a named `actor_output` schema bump **and** a separate review. | RATIFIED (no) |
| 9 | Explicit **ban on `ReviewTestResult` / verifier-result emission by H** | AST-scan test already fails the build if H names a verifier surface | **Hard ban, permanent.** H produces only testimony. Only an **AG-owned independent verifier** creates `verifier_results`. The `normalize(..., verifier_results=...)` seam stays sealed because `ActorOutput` has no route to it. | RATIFIED (H1) |
| 10 | Confirm **actor claims remain claims** | S7 Model B: claims → `not_run`; S5 refuses claimed pass | **Confirmed, permanent.** No cage capability ever upgrades a claim to a verified result; a real green still requires an independent verifier inside AG. | RATIFIED (H1) |

## Rationale per decision

### 1. The cage is OS-enforced, or it is not a cage
Python is the clerk, not the cage (inherited verbatim from the superseded Q1). The cage
must be container/namespace-enforced: disposable workspace, read-only input mount, narrow
writable dir, non-root, no network, no host creds, no host `$HOME`, process/time limits,
env allowlist, and **post-run write-manifest validation** (what did the actor actually
write?). The first cage slice may *demonstrate the contract* with a fake/`NullCage`-style
backend that confirms nothing — but it must then **refuse to admit a live actor**, exactly
as AG's `sandbox_cage.admit_origin_under_cage` refuses a live origin under an unconfirmed
cage. It is never acceptable to pretend `subprocess.run()` is containment.

### 2. Actor reach = read-only input + the handoff + a scratch dir
The actor reads a read-only repo snapshot and its S6 handoff (objective, scope,
prohibitions), and writes only into a per-run scratch/output/transcript area inside the
cage. The real checkout, `.git`, host home, network, and credentials are unreachable —
enforced by the cage (item 1), not by asking nicely. The inherited forbidden-writes term
applies: a write outside the writable area invalidates the run even on exit 0.

### 3. Transcripts live in the cage, cross only as tainted advisory text
The raw transcript/stdout/logs stay in the harness's per-run audit store, outside AG. The
*only* transcript content that crosses is `actor_output.v0.captured_text`, which S7
already treats as advisory `design_notes` — never a fact, decision, receipt, approval, or
state transition. The structured envelope is the artifact; the transcript is evidence at
best.

### 4–5. One file in; a short, explicit list of things that never cross
AG ingests one `actor_output.v0` JSON, parsed fail-closed. Everything else stays on the
harness side of the wall: raw streams, inline diffs, executables, process handles, network
artifacts, credentials, and — load-bearing — **any verifier-shaped object** (item 9). The
wall is a single JSON file; widening it is a ratified schema decision, not a convenience.

### 6. One-shot, low timeout, fail-closed kill — owned by the harness
Because the harness (not AG) runs the process, the harness owns timeout/kill. One adapter
invocation per handoff; a deliberately low first timeout (30–60 s — the point is proving
control flow, not doing work); TERM-then-KILL on timeout or a tripped kill switch; the
switch is checked before launch and during; a hung actor is terminated and its partial
output retained only as tainted audit. The harness may not write or clear the switch.

### 7. Replay is the default; live is opt-in and explicit
Replay/stub origins are preferred. Live actor execution requires an explicit
operator-armed mode (a flag + a real card + sandbox mode); the presence of a replay
fixture suppresses live execution unless the operator deliberately overrides for an
experiment. This is what keeps "run the tests" from quietly becoming "run a live agent."

### 8. One artifact, by default
`actor_output.v0` is the only artifact AG ingests. The envelope has no diff field today,
and that is correct: a proposed patch crosses (if ever) as a **reference** (path + sha256)
the operator fetches out-of-band, never as inline content AG might be tempted to apply.
Adding a diff-reference field is a hotter, separately-ratified `actor_output` schema bump
(it touches the AG-ingest contract) — name it; do not slip it in.

### 9–10. The two permanent bans (already mechanical in H1)
H produces **only testimony**. It must never emit a `ReviewTestResult`, `verifier_results`,
a verifier receipt, an admission receipt, or anything that can satisfy S5 — enforced today
by an AST scan of `harness/` (`test_harness_has_no_verifier_or_admission_surface`). Actor
claims remain claims: S7 Model B maps `claimed_test_results` to `not_run`, and S5 refuses
an actor-claimed passing test. No cage capability — not even a perfectly isolated one —
ever upgrades a claim to a verified result. A real green requires an **independent
verifier inside AG**. These two are not up for re-decision; they are the spine of the whole
conveyor.

## What passing this gate does and does NOT authorize

- **Does:** authorize a future *cage-design slice* to be written and separately reviewed —
  the cage **contract + a fake/honest backend for tests** (mirroring how `sandbox_cage`
  ships only `NullCage`/`SyntheticCage`). It does **not** authorize running a live actor.
- **Does NOT:** authorize H2, a live Claude/Codex invocation, a real subprocess actor, a
  bounded loop, autopilot, a widened envelope, or any in-AG actor execution. Each of those
  is its own later, separately-ratified gate.

## Operator pass — recorded decisions (2026-06-30)

The three open questions are answered. Contract-first throughout: *the cage gets a
constitution before it gets a keycard.*

### 1. Cage backend — contract-first / refuse-live; no executing backend yet
Ratified. The next cage-design slice may define the cage **contract** and implement an
honest `RefusingCage` / `NoLiveCage` backend that **always refuses live actor
admission** — proving the review/cage API without pretending containment exists.

- Do **not** choose Docker / Podman / bubblewrap as an *executing* backend in this pass.
- **bubblewrap** is marked the *likely first real Linux backend to evaluate later* —
  named, **not authorized**. (Docker/Podman are heavier and easier to confuse with "safe
  because container"; that confusion is exactly what contract-first refuses.)
- Passing this review **does not authorize H2 / live execution.** It authorizes a
  cage-*design* slice whose only backend is a refusing one.

### 2. Harness audit store — outside the repo, outside AG ingest
Ratified. Tainted harness transcripts live outside AG's repo and outside AG's ingest
path:

```text
default:   $XDG_STATE_HOME/agent-gov/harness-runs/
fallback:  ~/.local/state/agent-gov/harness-runs/
```

- Each run gets a content-addressed or timestamped run directory; full transcripts stay
  there.
- AG ingests **only** an explicit `actor_output.v0` artifact; AG must **not** crawl or
  import the audit store.
- `ActorOutput` may carry a run id / digest / descriptive capture metadata (e.g.
  `capture_origin`, `captured_at`), but **not authority** — these remain descriptive,
  never gating, exactly as H1 ships them.

### 3. One artifact only — hard default
Ratified. H may emit exactly one AG-ingestable artifact type: **`actor_output.v0`**.

- No diff-reference field in this schema; no `ReviewTestResult`; no verifier results; no
  receipt-greening object; no auxiliary bundle imported into AG.
- Any future diff reference requires a **named `actor_output` schema bump and a separate
  review**. (One file crosses. "Helpful extra bundle" is how treaties become airports.)

## Exit — PASSED 2026-06-30 (contract-first)

All ten terms are decided: items 4/9/10 inherited as RATIFIED from H1; items 1/3/8
ratified by this operator pass (contract-first cage, XDG audit store, one-artifact-only);
items 2/5/6/7 stand at their proposed conservative defaults, to be exercised — not
loosened — by the cage-design slice.

**Recommendation: authorize a cage-DESIGN slice with a refuse-live backend ONLY.** That
slice may:

- define the cage contract (the API a real backend must satisfy: workspace lifecycle,
  input mount, write-manifest validation, isolation attestation);
- implement a `RefusingCage` / `NoLiveCage` backend that admits **no** live actor (mirrors
  how `sandbox_cage.py` ships only `NullCage` / `SyntheticCage` and refuses live origins);
- define the audit-store layout (XDG paths above) and the one-artifact ingest boundary as
  tests.

It may **not**: run a live actor, build an executing/real cage backend, add a subprocess
runner, widen the `actor_output.v0` envelope, emit any verifier-shaped object, run a loop,
or do anything in-AG. **H2 remains unauthorized.** The next gate after the cage-design
slice — if any — is a *separate, later, separately-ratified* review of a real backend
(bubblewrap first to evaluate) before a single live actor runs.
