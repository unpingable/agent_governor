# Real Cage Backend Review (bubblewrap) — the containment facts for live admission

> **OPENED 2026-06-30. Status: PASSED 2026-06-30 (operator pass — constitution only).**
> This is a **review gate**, not an implementation doc. It decides the closed set of
> **containment facts** a real cage backend (bubblewrap, `bwrap`) must enforce **and
> witness** before it may truthfully attest `confirms_isolation=True` — the single
> boolean that, in `harness/cage.py`, is the only thing that lets `evaluate_live_admission`
> admit a live actor. **No code, no runner, no live actor is built under it.**
>
> **Operator pass recorded below ("Operator pass — recorded decisions").** The core
> principle is ratified, the fact set is **C1–C11** (seccomp added as C11), and the five
> decisions are recorded. Passing buys the **constitution for the cage**, not a cage, not
> a live run — building the bwrap backend is the next gate, H2 implementation the one after.

## What is NOT being authorized

- **Not bubblewrap implementation.** No `bwrap` wrapper, no backend module, is written.
- **Not H2 implementation or any live run.** Those remain their own later gates
  (`h2-live-run-contract-review.md`, PASSED shape-only). A cage that *can* attest live is
  **necessary, not sufficient**: H2 still needs `armed_live` + the `harness/run.py` gate.
- **Not operational effect.** AG stays `DemonstratedConsumed` regardless (H2 invariant I-1).

## The thing being decided (and the one principle behind it)

`harness/cage.py` reduces "is this cage safe for a live actor?" to one earned boolean:
`CageAttestation.confirms_isolation` (which forces `scope == live`). The cage-design slice
shipped only `RefusingCage`, which attests `False`. A real backend is the first thing that
could attest `True`. **This review decides what `True` is allowed to mean.**

The principle is the repo's own, applied to the cage itself:

> **A cage attestation is a claim, and a claim is not authority (NLAI). Configuration
> intent is not containment. `bwrap` *invoked with the right flags* is an assertion; the
> attestation is earned only by *witnessing* — running the forbidden thing and confirming
> it fails.** Signed ≠ witnessed; configured ≠ contained.

So every containment fact below is a **pair**: a property the cage must enforce, and a
**witness** (a probe, mostly *negative* — attempt-the-forbidden-and-confirm-refusal) that
makes the attestation truthful. `confirms_isolation=True` is admissible **only** when
**every** required fact has a passing witness for **this run**. Missing or failed witness
→ no attestation → `RefusingCage` semantics → live refused.

This is an **allowlist of required facts** (conjunctive, guarantee-typed): one unwitnessed
fact falsifies the attestation. Not "mostly contained."

## The containment facts (closed, conjunctive)

| # | Containment fact (required) | Why it is load-bearing | bwrap mechanism (named, not built) | Required witness (mostly negative) |
|---|------------------------------|------------------------|-------------------------------------|-------------------------------------|
| C1 | **No network** | egress / exfiltration / "helpful install" / phone-home | `--unshare-net` | inside-cage probe: outbound TCP + DNS attempt **fails**; no host loopback service reachable |
| C2 | **PID/IPC/UTS/cgroup isolation** | can't see, signal, or interfere with host processes | `--unshare-pid --unshare-ipc --unshare-uts --unshare-cgroup` | process list inside shows only cage processes; kill of a host pid **fails** |
| C3 | **Non-root, no privilege escalation** | a root actor or setuid escalation defeats every other fact | `--unshare-user --uid <nonzero> --gid <nonzero>`, no-new-privs | `id` inside → uid≠0; a setuid probe cannot gain privilege |
| C4 | **Read-only input** | actor must not mutate the repo snapshot or handoff it was given | `--ro-bind <snapshot>`, `--ro-bind <handoff>` | write to the input mount **fails** (EROFS) |
| C5 | **Exactly one narrow writable area** | bounds where any effect can land; basis for the write-manifest | `--bind <per-run writable dir>`; nothing else writable | write outside the writable dir **fails**; post-run write-manifest ⊆ writable dir |
| C6 | **No host filesystem / no credentials** | `~/.ssh`, `~/.aws`, tokens, host `$HOME`, host root must be unreachable | `--tmpfs /home`, no bind of host home/creds; minimal root | probes for `~/.ssh`, host `$HOME`, known cred paths → **absent/unreadable** |
| C7 | **Minimal `/dev`, no host devices** | block-device / raw-device access is an escape and an exfil path | `--dev /dev` (minimal) | host block devices **absent** |
| C8 | **Clean env allowlist** | a leaked `API_KEY`/token in the environment is exfiltration even with C1 | `--clearenv` + explicit `--setenv` allowlist only | env inside == the declared allowlist exactly; no host secret vars present |
| C9 | **Resource + time limits** | a runaway actor is a DoS on the host; bounds the blast in time | rlimits (cpu/mem/nproc/fsize) + the H2 `timeout_s` (30, hard-max 60), `--die-with-parent`, `--new-session` | limits observed set; cage dies with the harness; the H2 timeout/kill (harness-owned) terminates a hung run |
| C10 | **Disposable, per-run workspace** | no state carried between runs; no accretion of effect or evidence | per-run dir under `run_dir(run_id)`; tmpfs scratch; destroyed/sealed after | workspace path is per-run; absent on the next run; sealed for audit, never reused as input |
| C11 | **Syscall surface constrained (seccomp profile active)** | namespaces fence *resources*; seccomp fences the *syscall surface* itself — the escape/privilege paths namespaces don't cover. **Required, not optional hardening.** | `bwrap --seccomp <fd>` with the expected profile (default-deny / curated allowlist) | confirm the expected seccomp profile is **installed** for the run; run ≥1 forbidden-syscall/action probe where practical → **blocked**; if seccomp cannot be installed or witnessed → **no `confirms_isolation`** |

**The egress fence is C1 ∧ C6 ∧ C8 read together:** no network, no credentials on disk, no
secrets in env — so even a maximally adversarial actor has nothing to take and nowhere to
send it. None of the three alone suffices; the conjunction is the fence.

## The witness discipline (the meta-decision)

1. **Attestation is earned per run, not standing.** The probe battery (C1–C11 witnesses)
   runs at cage construction **for that run**, against **that run's** workspace. A passing
   battery mints `CageAttestation(confirms_isolation=True, scope=live)` bound to the run;
   a failing or partial battery mints nothing (→ refuse-live). No caching a "this backend
   is safe" verdict across runs — *a cage is witnessed each time it is used.*
2. **Negative probes are mandatory.** Positive config inspection ("we passed `--unshare-net`")
   is necessary but **not** a witness. The witness is the forbidden action *attempted and
   observed to fail* (the connection that doesn't open, the write that returns EROFS). A
   fact with only a positive config check is **unwitnessed**.
3. **Conjunctive admission.** `confirms_isolation=True` iff **all** of C1–C11 are
   witnessed. One missing → the attestation is not minted. (Guarantee-typed seam: a
   90%-contained cage is breached, you just don't know through which fact yet.)
4. **The attestation records its evidence.** The minted attestation carries the per-fact
   witness results (a structured battery record), so the decision is auditable and
   replayable — not an opaque boolean. (The exact record shape is an implementation
   concern for the build gate; this review fixes that evidence MUST be carried.)
5. **Failure is loud and refusing, never degraded.** A witness that errors (probe can't
   run) is a failure, not an "assume contained." Unknown ⇒ refuse.

## What passing this review authorizes (proposed)

Passing ratifies **the containment-fact constitution** — the C1–C11 set + the witness
discipline. The recommended *next* gate is a **bubblewrap-backend implementation slice**
whose only job is to build a backend that:

- enforces C1–C11 via `bwrap`, and
- mints `confirms_isolation=True` **only** after the per-run negative-probe battery passes,
  else attests nothing (refuse-live),

with **still no live actor run** (that is the H2-implementation gate, separately). Until
that backend exists and witnesses the battery, `RefusingCage` remains the only cage and
live admission stays unreachable.

## Operator pass — recorded decisions (2026-06-30)

The **core principle is ratified**: cage configuration is not containment testimony; `bwrap`
invoked with the right flags is still only a claim; `confirms_isolation=True` is admissible
only when the run's containment facts are **witnessed**; **negative probes are mandatory**;
**unknown/unwitnessed → refuse-live**; the fact set is **conjunctive** — one missing fact
means no live admission.

### 1. Completeness — C1–C10 accepted; **C11 (seccomp) added, required**
C1–C10 accepted as written. **C11 — syscall surface constrained / seccomp profile active —
is added and is REQUIRED, not optional hardening.** Witness: confirm the expected seccomp
profile is *installed* for the run; run ≥1 forbidden-syscall/action probe where practical;
**if seccomp cannot be installed or witnessed → no `confirms_isolation`.** The fact set is
now **C1–C11**, conjunctive.

### 2. Probe-battery placement — pre-flight self-test per run (ratified)
The cage backend must run the probe battery **before** admitting the actor. Probe evidence
is bound to **that run's** attestation. Positive config inspection alone is insufficient.
**Probe failure / refusal / timeout → no live admission.** (The actor never shares a process
with a cage that has not yet witnessed its own battery.)

### 3. Host requirements — Linux-only first backend (ratified)
Require a **Linux host**, **bubblewrap available**, and **user namespaces / needed kernel
features enabled**. If user namespaces or required isolation features are unavailable →
**refuse-live** (never silently downgrade). **No Docker/Podman fallback** in this review.

### 4. Evidence retention — tainted audit store (ratified)
Probe outputs, the `bwrap` invocation summary, the cage attestation, run id, timestamps, and
the refusal/admission decision go under the harness audit store, **outside AG ingest**:
`$XDG_STATE_HOME/agent-gov/harness-runs/` (fallback `~/.local/state/agent-gov/harness-runs/`).
**AG may ingest only `actor_output.v0`; AG must not crawl the audit store.** Cage evidence
may be **referenced by digest / run id**, never imported as authority.

### 5. Necessity-not-sufficiency — confirmed
Passing this review authorizes only a future **bwrap backend implementation slice**. A
passing probe battery may permit `require_live_admission` *for that run*, but it does **not**
authorize H2 implementation by itself. **H2 implementation remains a separate gate;
operational effect a separate later gate; actor claims remain claims.** Cage attestation is
**necessary** for live actor execution, **not sufficient** for admitting actor output as
verified work.

## Exit — PASSED 2026-06-30 (constitution only)

The containment-fact constitution is ratified: **C1–C11** (seccomp now required) + the
witness discipline (per-run, negative-probe-mandatory, conjunctive, evidence-carried,
unknown→refuse) + pre-flight self-test + Linux-only + tainted audit retention +
necessity-not-sufficiency.

**Recommendation: authorize a bubblewrap-backend *implementation* slice** — and ONLY that —
whose sole job is a backend that (a) enforces C1–C11 via `bwrap`, (b) runs the pre-flight
negative-probe battery per run, and (c) mints `confirms_isolation=True` **only** when the
full battery passes, else attests nothing (refuse-live). That slice builds **no live actor
run, no runner, no H2** — those remain separate later gates.

This pass authorizes **nothing to build right now.** Until a separately-authorized build
slice ships such a backend and witnesses the battery, `RefusingCage` remains the only cage
and live admission stays unreachable.

The gate stack, unchanged and all gated, in order:

```
real cage backend (bubblewrap) — constitution PASSED; implementation slice = next gate
  → H2 implementation (UNBUILT — separate gate; needs a witnessing backend first)
    → operational effect (UNBUILT — separate, even later)
```

Passing this review buys a **constitution for the cage**, not a cage — and certainly not a
live run.
