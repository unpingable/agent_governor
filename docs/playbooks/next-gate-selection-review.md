# Next-Gate Selection Review — bwrap backend: live C1–C10 substrate compatibility validation (fresh-eyes)

> **PROPOSED 2026-07-01. PASSED 2026-07-01 (operator pass, with amendments — see
> "Operator pass" at end). Status: the proposed evidence-only gate is OPEN.** The operator
> authorized exactly one code slice: a **minimal fenced validation entrypoint** for the live
> C1–C10 substrate compatibility run — **an evidence run, not implementation.** Still no actor,
> no H2, no seccomp implementation, no operational effect, no live admission; C11 unavailable
> must force refusal.
>
> *(Original proposal header, preserved:)*
> **fresh-eyes gate-selection recommendation, not yet opened by an operator. NON-AUTHORIZING.** This packet recommends *which* gate an operator
> should open next and fixes what that gate may and may not do. It authorizes no build, no
> seccomp, no H2, no live admission, no operational effect. It does **not** itself open a
> gate — only an operator does that. If passed, the gate it proposes would authorize **only
> the evidence run** scoped in §5 (a live C1–C10 substrate compatibility validation with
> mandatory C11 refusal), and **no implementation of any kind**.
>
> **Why this doc edit is allowed** (register discipline): writing a PROPOSED/DRAFT review-gate
> doc is *routine implementation*, not custody-affecting. It changes no canonical definition,
> kernel, receipt format, ratification rule, or public claim; it recommends and awaits an
> operator verdict — the same posture `harness-cage-review.md` and `real-cage-backend-review.md`
> held before their operator pass. It edits nothing under the governor package and touches no
> code. `docs/REENTRY.md` is deliberately **not** edited (see §7): the admission pointer is not
> updated for an un-opened, un-passed gate.

## Context snapshot (derived, not remembered)

The gate stack, current truth:

```
real cage backend (bubblewrap) — constitution PASSED (2026-06-30)
  bwrap backend IMPLEMENTATION slice — LANDED (d4e6115); refuses live in v0 by construction
    → [THIS REVIEW selects the next gate]
      → H2 implementation (UNBUILT — separate gate)
        → operational effect (UNBUILT — separate, even later)
```

`harness/bwrap_cage.py` exists and **runs no actor** (only `bwrap` probe commands). It mints
`confirms_isolation=True` only when the per-run negative-probe battery witnesses **all** of
C1–C11 (conjunctive, guarantee-typed). In v0 it refuses live for two independent reasons:

1. **No compiled seccomp filter** → `RealBwrapProber` can never witness **C11** → conjunctive
   mint refuses on *every* host, capable or not.
2. **Nested sandbox** (this dev host): cage smoke fails (loopback `EPERM`) → `assess_host`
   refuses before any battery runs.
3. All passing evidence to date is against an injected `FakeProber` → **synthetic
   compatibility, not live testimony.** No probe has ever run against real `bwrap`.

## 1. Smallest next gate that should be opened

**A live C1–C10 substrate compatibility validation with mandatory C11 refusal**, run once on
a capable Linux host against the *existing* bwrap backend — **an evidence run, not
implementation.** It builds nothing (the backend is already written, reviewed, and landed),
runs no actor, and cannot reach live admission (C11 remains unwitnessable in v0 → guaranteed
refuse). Its entire job is to convert the C1–C10 witness layer from *synthetic* (FakeProber)
to *live substrate compatibility* (real `bwrap` on real userns), and to confirm the
conjunctive mint correctly **refuses** when C11 is absent.

It is the smallest gate because it adds zero capability, authorizes zero implementation, needs
zero new module code, and its worst-case outcome is a *correct refusal*.

## 2. Which of the four options

- **Live C1–C10 substrate compatibility validation (with mandatory C11 refusal) of the
  existing bwrap backend on a capable Linux host — YES**, as an *evidence run only*: validate
  the C1–C10 probe machinery + host-gate + refusal path, **not** to achieve a passing battery
  (impossible in v0, and must stay impossible) and **not** to implement anything.
- **Real C11 seccomp implementation — NO, not yet.** It is a build slice, forbidden here, and
  mis-ordered: you would bolt a seccomp filter onto a C1–C10 witness layer that has never run
  against real `bwrap`. Validate the substrate first so the seccomp gate builds on live
  evidence, not synthetic. Seccomp is the gate *after* this one.
- **H2 implementation — NO.** Forbidden here, and structurally premature: H2 needs a backend
  that can *witness* a live cage; none exists (v0 refuses everywhere). Building an actor
  runner now is capability ahead of the containment that would justify it.
- **None of the above — NO.** Doing nothing leaves the whole cage layer resting on
  FakeProber. There is a real, safe, bounded evidence upgrade available; take it.

**Recommendation: propose Option 1 for an operator to open — evidence-run-only, no
implementation, as scoped here.**

## 3. Exact evidence the chosen gate must produce

A single run-record on a capable Linux host, persisted to the tainted audit store
(`$XDG_STATE_HOME/agent-gov/harness-runs/`, AG-never-ingested). The record **must declare its
substrate facts** — the run is testimony only if it names the ground it stood on:

0. **Substrate declaration (mandatory, or the run is inadmissible):**
   - **host identity / class** (which host, and whether bare-metal / VM / container / CI);
   - **kernel** (`uname -a`, or at least version + arch);
   - **`bwrap` version** (`bwrap --version`);
   - **userns availability** (unprivileged user namespaces enabled) and **seccomp
     availability** (kernel seccomp support), each as observed, not assumed;
   - **nested-sandbox status** — is this host itself inside another sandbox/container? (the
     dev host is; a capable host must declare it is **not**, since nesting is what `EPERM`s the
     cage smoke);
   - **exact commands run** (the `bwrap` invocations and every probe command, verbatim);
   - **full transcript** of the battery (stdout/stderr per probe, exit codes);
   - **audit-store path** the record was written to (the concrete `harness-runs/<run_id>/`).

   A run that cannot name its host, kernel, `bwrap` version, or nested status produces no
   admissible substrate evidence — unknown substrate → the run is discarded, not "assumed
   capable."

1. **`assess_host` result** — Linux + `bwrap` on PATH + user namespaces + seccomp *kernel*
   support + **cage-smoke PASS** (a real isolated cage actually starts — the thing that fails
   in the nested sandbox). This is the first live proof the backend can start a cage at all.
2. **Per-fact `FactWitness` battery for C1–C10**, each run *inside a real bwrap cage*, each a
   **negative probe** observed to fail as required: outbound TCP/DNS fails (C1); host-pid kill
   fails, process list is cage-only (C2); uid≠0, setuid gains nothing (C3); input mount write
   → EROFS (C4); write outside the one writable dir fails + write-manifest ⊆ writable (C5);
   `~/.ssh`/host `$HOME`/cred paths absent (C6); host block devices absent (C7); env == the
   declared allowlist, no host secrets (C8); rlimits + timeout observed, cage dies with parent
   (C9); workspace is per-run and absent next run (C10).
3. **C11 = `unavailable`** (no compiled filter) → **`all_required_witnessed` = False** →
   **`confirms_isolation` = False → refuse-live.** The refusal is the *expected pass
   condition* of this gate.
4. **A structured verdict doc** (results section appended here or a sibling
   `bwrap-live-validation-results.md`) recording: which C1–C10 probes fired live, any probe
   that behaved differently against real `bwrap` than against FakeProber (→ a bug to fix under
   this gate, evidence-driven, not new capability), and the confirmed refusal at C11.

**What a fully-green C1–C10 battery with C11 unavailable *is*, stated plainly:** it is
**not live admission.** It is a **successful refusal plus partial substrate evidence** — the
cage was correctly refused (C11 missing), and the C1–C10 layer gained *live substrate
compatibility* evidence for the first time. "Partial" is load-bearing: C11 is not merely
untested, it is *structurally unwitnessable in v0*, so the substrate evidence is by
construction incomplete and confers no admission. **Live compatibility of the C1–C10 witness
machinery ≠ a live-admissible cage.**

## 4. Evidence that remains explicitly NON-authorizing

- **A fully green C1–C10 live battery does NOT authorize live admission** — C11 is still
  unwitnessed, so the mint refuses; and even a hypothetical full C1–C11 pass would be
  *necessary, not sufficient* (H2 remains its own gate).
- **A passing cage-smoke on a capable host does NOT mean "safe for an actor"** — no actor is
  run; it means the machinery starts.
- **Live compatibility of the prober does NOT upgrade the backend to production-ready**, does
  NOT authorize seccomp implementation, and does NOT arm `armed_live`.
- **This DRAFT's operator pass, the pushed code, and any green test count are not live
  testimony** and confer no admission.
- **Cage evidence in the tainted audit store is not AG authority** — referenced by digest /
  run id only; AG must not crawl or ingest it (only `actor_output.v0` is ingestible, and no
  actor runs here so none is produced).

## 5. Files likely touched — only after the gate is opened

Prefer **zero new module code.** The validation is an invocation of the already-built
`RealBwrapProber` + battery on a capable host, with evidence captured to the audit store.

- **New:** a results doc under `docs/playbooks/` (or a results section appended to this file).
- **Possibly new (fenced):** a thin, battery-only capture entrypoint if a REPL invocation is
  insufficient. It must invoke the probe battery **only**, run **no actor**, and must **not**
  live at or resemble `harness/run.py` (that path is reserved for the H2 actor runner and is a
  separate, later gate). Name it as validation, not as a runner.
- **`harness/bwrap_cage.py`:** touched **only** if the live run reveals a real prober↔bwrap
  incompatibility — a bugfix under this gate, evidence-driven, never a capability addition and
  never a new path to `confirms_isolation=True`.
- **`docs/REENTRY.md`:** updated **only after** the run completes and the operator accepts the
  results — to record the outcome, not to pre-authorize it.

Explicitly **not** touched: any seccomp/BPF module, any actor kind (`offline_echo_actor` et
al.), `runtime/adapters/claude_code.py`, `confer_operational_effect`, the AG governor package.

## 6. Refusal conditions that must remain HARD failures

- **C11 unwitnessed → no `confirms_isolation`.** v0 has no seccomp filter; every run must
  refuse. This must not be softened to "assume constrained" on a capable host.
- **Any single fact unknown / unavailable / probe-error / timeout / refused → attest nothing**
  (conjunctive mint; one missing fact falsifies the attestation).
- **Non-Linux / no `bwrap` / no userns / no seccomp-kernel-support / cage-smoke-fail →
  `assess_host` refuses, no battery runs** (never silent downgrade; no Docker/Podman
  fallback).
- **Positive config inspection is never a witness** — the negative probe (forbidden action
  attempted and observed to fail) is mandatory.
- **The backend runs NO actor.** The validation must not introduce one.
- **No path from `armed_live` / `--armed-live` alone to admission.**
- **AG stays `DemonstratedConsumed`; `confer_operational_effect` refuses** (H2 invariant I-1),
  untouched by anything this gate produces.

## 7. Proposed anti-conflation language (for a review doc / later REENTRY)

Add the following block to the results doc when this gate closes, and — **only after operator
acceptance** — a one-line pointer in `docs/REENTRY.md`. (Not added to REENTRY now: the
admission pointer is not written for an un-passed gate.)

> **Four things that are NOT live testimony — a standing non-equivalence.** For the harness
> cage layer, none of the following, alone or combined, licenses `confirms_isolation=True` or
> admits actor output as verified work:
>
> 1. **Pushed code is not testimony.** A committed, remote, review-passed backend is a claim
>    with a digest, not a witnessed cage. Being on `origin` proves storage, not containment.
> 2. **Synthetic compatibility is not live testimony.** A green battery against `FakeProber`
>    (or any injected prober) proves the *logic*, not that real `bwrap` on a real host
>    contained anything. Live compatibility of the C1–C10 machinery is a *further* claim, and
>    even it is not a live-admissible cage while C11 is unwitnessed.
> 3. **Shape / constitution approval is not testimony.** An operator pass on a *review* fixes
>    what a boolean is *allowed to mean* (`real-cage-backend-review.md`, `h2-live-run-contract
>    -review.md`); it witnesses no run. Constitution ≠ cage; contract ≠ execution.
> 4. **Actor output is not testimony about itself.** An actor's claim that a test passed is
>    ingested as `not_run` advisory until an **independent verifier receipt** covers it (S7
>    invariant). The actor cannot green its own gate.
>
> Live testimony = a per-run C1–C11 negative-probe battery, all facts witnessed, against real
> `bwrap` on a Linux host, evidence in the tainted audit store, bound to that run. Anything
> short of that → refuse-live.

## Exit (proposed)

**Recommend an operator open Option 1 only** — a single **evidence run** (not
implementation): a live C1–C10 substrate compatibility validation with mandatory C11 refusal,
against the existing bwrap backend, on a capable Linux host. It builds nothing beyond a
minimal fenced *battery-only* entrypoint if a REPL invocation won't do (§5), runs no actor,
cannot reach live admission (C11 unwitnessable in v0), and upgrades the cage layer's
foundation from synthetic to live substrate compatibility — the strict prerequisite for
trusting any future C11/seccomp work. Seccomp design is the gate *after*; H2 and operational
effect remain where they are, unarmed. This DRAFT authorizes nothing until an operator pass is
recorded here.

## Operator pass — recorded decisions (2026-07-01)

**PASSED with amendments.** The operator opened the proposed evidence-only gate and authorized
**one code slice**: build the *minimal fenced validation entrypoint* required to perform the
approved live C1–C10 substrate compatibility run. The authorization is bounded by these
constraints, which are hard:

- **No actor execution.** The entrypoint runs `bwrap` probe / host-detection commands only —
  never a Claude/Codex/echo/actor invocation. No `run`/`spawn`/`run_once`.
- **No H2**, **no seccomp implementation**, **no operational effect**, **no live admission.**
- **C11 unavailable must force refusal.** The entrypoint never mints or asserts
  `confirms_isolation=True`; it consumes the backend's attestation, which refuses in v0 by
  construction (C11 unwitnessable). A C1–C10-green / C11-unavailable outcome is recorded as
  **successful refusal plus partial substrate evidence**, never as admission.
- **Output: exactly one tainted audit record** under the harness audit store
  (`audit_store_root()` / `run_dir(run_id)`, AG-never-ingested), carrying the **declared
  host/substrate facts** (host identity/class, kernel, `bwrap` version, userns/seccomp
  availability, nested-sandbox status, audit-store path) and the **probe transcript** (exact
  commands + captured output/exit for what the validation ran).
- **Tests may cover parser / recording / refusal behaviour only** — built on injected
  fakes / synthetic inputs. **Tests must not be described as live testimony.** A green test
  suite proves the entrypoint's logic, not that any cage contained anything.
- **`harness/run.py` is not created and not resembled.** The entrypoint is battery/probe-only
  and is named as validation.

The slice lands as `harness/validate_bwrap_substrate.py` (+ tests). Building it does **not**
authorize the next gates (seccomp design, then H2 implementation, then operational effect);
each remains separate and unarmed.
