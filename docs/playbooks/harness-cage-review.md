# H-series Harness-Cage Review — GATE before any live actor runs in `harness/`

> **OPENED 2026-06-30. Status: DRAFT — awaiting operator pass.**
> This is a **review gate**, not an implementation doc, and **not H2**. No live actor,
> no cage backend, no subprocess runner is built under it. It decides the *terms* a
> future H-series cage must satisfy before a real Claude/Codex actor may execute inside
> the external harness. Passing it buys exactly one thing: permission to *design+review*
> a cage slice — not to run one. Each row is a decision to ratify, defer, or tighten.

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
| 1 | What the external harness cage **is** | nothing yet (H1 runs no actor) | OS/container-enforced (Docker/Podman/bubblewrap); disposable per-run workspace; read-only input snapshot; non-root; no network; no host `$HOME`/creds; process+time limits; env allowlist; post-run write-manifest validation. **No "safe" claim unless the backend confirms isolation.** | PROPOSE |
| 2 | What actor execution may **touch** | — | Read-only repo snapshot + the S6 `handoff` (PROMPT.md/handoff.json) + per-run scratch/output/transcript. Nothing else: not the real checkout, `.git`, host home, network, creds, AG's repo. | PROPOSE |
| 3 | Where **transcripts** live | `captured_text` is advisory; S7 routes it to `design_notes` | In the per-run cage transcript dir (outside AG). Only the `captured_text` *field* of `actor_output.v0` crosses, as tainted advisory text. Raw streams/logs stay in the harness audit store. | PROPOSE |
| 4 | What gets **imported into AG** | exactly one `actor_output.v0`, fail-closed parse | **One `actor_output.v0` JSON file. Nothing else.** | RATIFIED (H1) |
| 5 | What **never** crosses into AG | harness can't import governor; emits only the envelope | Raw transcript streams; inline diff/patch content; any executable; process handles; network artifacts; creds; **any `ReviewTestResult` / verifier result / receipt** (item 9). | PROPOSE (4+9 already hard) |
| 6 | **Timeout / kill-switch** behavior | — (harness owns the process) | One-shot; low first timeout (**30–60 s**); TERM-then-KILL; global kill (`PLAYBOOKS_RATION_KILL=1` + `.playbooks-kill` sentinel) checked before launch and during; hung actor terminated; partial output kept as tainted audit, never consumed as success; harness may not write/clear the switch. | PROPOSE |
| 7 | **Replay** discipline | AG durable-spend gate refuses replay | Replay/stub is the default; live execution requires an explicit operator-armed mode; a replay fixture suppresses live unless deliberately overridden. Tests never "accidentally" go live. | PROPOSE |
| 8 | Any artifact **besides** `actor_output.v0`? | envelope has no diff field | **No.** One envelope crosses. A diff, if ever needed, crosses as a **reference (path+sha256) inside the envelope**, never inline, and only via a *separately-ratified* `actor_output` schema bump (hotter change — name it, don't slip it). | PROPOSE (default: no) |
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

## Open questions for the operator pass

1. **Cage backend choice** — Docker / Podman / bubblewrap / "decide per environment"? (Or
   defer: first slice demonstrates the cage *contract* with an honest no-containment
   backend that refuses live admission, and the backend choice is its own decision.)
2. **Where the harness audit store lives** — inside `harness/` working tree, a sibling
   dir, or `$XDG_*`? (It holds tainted transcripts; it must be outside AG's ingest path.)
3. **Item 8** — confirm "one artifact only" as a hard default, and that any diff-reference
   field is deferred to a named future schema bump.

## Exit (to be completed by the operator pass)

> Pending. When the operator completes the pass, record per-row decisions here and the
> recommendation (authorize a cage-*design* slice / refuse / defer), exactly as the
> superseded review recorded its exit. Until then, **no cage slice and no H2.**
