# Capable-host substrate finding — `capable-vm-noble-001` (the evidence gate's first trophy)

> **RESULT DOC. Real-substrate finding, 2026-07-01.** First live run of the bwrap backend on a
> genuinely capable Linux host (not the nested CC sandbox). A real bwrap cage started, 9 of the
> 11 containment facts witnessed on real `bwrap` — and **C5 failed**, exposing a containment gap
> that the synthetic `FakeProber` had masked. This is preserved as a standing finding so the
> later clean rerun cannot overwrite the fact that *fake-prober green was not substrate evidence.*

## Why this run happened

The CC environment and all locally-reachable hosts are unsupported for bwrap:

- **This CC environment** blocks unprivileged user namespaces (`unshare --user` →
  `uid_map: Operation not permitted`), so bwrap cannot build a cage. Confirmed independent of
  the Bash tool sandbox. Honest *host-unsupported*, not a prober bug.
- **mini / NAS** are macOS — bwrap is Linux-only. Structurally incapable.
- **crow** (capable Linux) was off / IP unknown.
- **linode** is nq production — deliberately not used (cross-custody bleed).

So a disposable **capable substrate** was provisioned: a local Ubuntu 24.04 KVM VM (user-mode
qemu, `/dev/kvm`, NoCloud cloud-init seed). This is lab substrate — *compatibility evidence,
never live testimony about a production estate.*

## Declared substrate facts (from the tainted audit record)

| Fact | Value |
|---|---|
| host_id | `porter-cage-vm` |
| host_class | `vm` (Ubuntu 24.04 KVM guest, user-mode qemu) |
| kernel | `Linux 6.8.0-124-generic #124-Ubuntu SMP … x86_64` |
| bwrap_version | `bubblewrap 0.9.0` |
| userns_available | `true` (guest provisioned with `apparmor_restrict_unprivileged_userns=0`, declared) |
| seccomp_available | `true` (kernel support; **no compiled filter** — see C11) |
| nested_sandbox | `no` |
| audit_store_path | `~/.local/state/agent-gov/harness-runs/` (guest, tainted, AG-never-ingested) |

Record preserved at `~/git/porter/outputs/ag-bwrap-substrate/capable-vm-noble-001.json` and in
the guest's tainted audit store.
**Artifact identity** — run id `capable-vm-noble-001`, host `porter-cage-vm` (Ubuntu 24.04 KVM
`vm`), sha256 `1c074dd06eb0432f1f09a6047a3df1da6dbf6c3f0aa846c27bec7fb93dfb458a`.

## The result

**A real bwrap cage started** (`cage_smoke rc=0`) — the first time this backend has established
a live cage. Per-fact battery against real `bwrap`:

| Fact | Witnessed | Note |
|---|---|---|
| C1 no network | ✅ | outbound TCP failed as required |
| C2 pid/ipc/uts/cgroup iso | ✅ | few pids visible |
| C3 non-root / no-priv | ✅ | uid/gid non-root inside |
| C4 read-only input | ✅ | write to `--ro-bind /usr` failed (EROFS) |
| **C5 exactly one narrow writable area** | ❌ **FAILED** | see below |
| C6 no host fs / no creds | ✅ | host homes / ssh creds absent |
| C7 minimal /dev | ✅ | no host block devices |
| C8 clean env allowlist | ✅ | host env sentinel stripped by `--clearenv` |
| C9 resource + time limits | ✅ | prober guarantee; cage established |
| C10 disposable workspace | ✅ | prober guarantee; cage established |
| C11 seccomp profile active | ⚪ unavailable | v0 compiles no seccomp filter (expected) |

Decision: `confirms_isolation=False`, `live_admission=False`, `mandatory_c11_refusal=True`,
outcome **`refused_incomplete_substrate`**. The safety invariants held; no admission.

## The C5 finding (the trophy)

The C5 negative probe — `/bin/sh -c "echo x > /__cage_probe_outside_writable__"` — **succeeded**
(`rc=0`). It was *expected to fail* ("write outside the one writable area must fail").

Root cause: **bwrap's root `/` is itself a writable tmpfs.** `BWRAP_BASE_ARGS` declares `/tmp`
as the one writable area (`--tmpfs /tmp`) and read-only-binds `/usr /bin /lib /lib64`, but never
seals the container root. So the cage actually has **two** writable areas — `/tmp` *and* the root
`/` — violating C5's "exactly one narrow writable area."

C4 (write to `--ro-bind /usr`) correctly failed, proving the ro-binds work — so the gap is
specifically the **unsealed writable root**, not the binding machinery.

**Why this matters:** the synthetic `FakeProber` asserted C5=witnessed, so every prior green run
(unit tests, nested self-check) masked this. Only real bwrap on a capable host exposed it. This
is the evidence gate doing exactly its job: *fake-prober green ≠ substrate evidence.*

## Decision — branch 3

Per the gate-selection decision tree: **C1–C10 failed on a capable host → fix the bwrap/prober
integration before any seccomp/H2 work.** The C11/seccomp design gate does **not** open next.

Required fix (next slice, narrow): seal the cage root so the container `/` is read-only, keeping
exactly one declared writable area (`/tmp`). **C5 must not be weakened/restated to match the
current behavior** — the fact is correct; the config is wrong. No actor / H2 / seccomp /
operational-effect / live-admission changes.

After the fix, rerun on the same capable VM. Expected clean result: C1–C10 all witnessed
(including C5), C11 unavailable, `confirms_isolation=False`, `live_admission=False`, outcome
`successful_refusal_partial_substrate_evidence`. That clean record is a **separate** artifact;
this failure finding stands on its own.

---

## Clean rerun after the C5 fix — `capable-vm-noble-002`

**The fix.** `BWRAP_BASE_ARGS` now appends `--remount-ro /`, sealing the container root after
the writable `/tmp` and the ro-binds are established. Verified on real bwrap *before* the code
change: a root write (`echo x > /__root__`) went `rc=0` unsealed → `rc=2` (`Read-only file
system`) sealed, while `/tmp` stayed writable (`rc=0`) — so exactly one writable area remains.
**C5 was not weakened**; the config was corrected to satisfy the fact. No actor / H2 / seccomp /
operational-effect / live-admission surface was touched.

**The clean rerun** (same hot VM, fixed backend):

| | Result |
|---|---|
| cage_smoke | passed (real cage started) |
| witnessed | **C1–C10 all witnessed on real bwrap** (C5 probe now `rc=2` — root write correctly fails) |
| unwitnessed | **C11 only** (seccomp filter still uncompiled — expected) |
| confirms_isolation | `False` |
| live_admission | `False` |
| mandatory_c11_refusal | `True` |
| outcome | **`successful_refusal_partial_substrate_evidence`** |

Record preserved at `~/git/porter/outputs/ag-bwrap-substrate/capable-vm-noble-002.json`.
**Artifact identity** — run id `capable-vm-noble-002`, host `porter-cage-vm` (Ubuntu 24.04 KVM
`vm`), sha256 `c8a180216d2211b5a0c0bf9407f22ddcb6257af55296f90e71eea95850ff2ca6`.

**What this pair establishes.** `capable-vm-noble-001` (failure) proves synthetic `FakeProber`
green was not substrate evidence — real bwrap found an unsealed writable root. `capable-vm-
noble-002` (clean) proves the fix produced *new* live-substrate evidence: C1–C10 genuinely
witnessed on real bwrap, live admission still structurally unreachable (C11 uncompiled). The
knife found the infection; the pass is hygiene after. Both specimens are retained.

Branch 3 is discharged (containment fix landed + re-validated). The C11/seccomp design gate
remains closed and **is not opened by this work** — it is the next, separate decision.
