# Temporal Capability Kernel — Research Note

## Status
Speculative. Not roadmap. Pattern recognition from the governor work.

## Origin
Emerged during v2.7 gap-spec work (March 2026). The observation: governor's
concepts translate to OS-level enforcement not metaphorically but structurally.
The agent-level governor may be a userspace projection of a deeper pattern.

## The Observation

Governor enforces at authority boundaries:
- tool call → governor gate → receipt
- claim → evidence gate → verdict
- scope request → escalation → grant

A kernel enforces at authority boundaries:
- syscall → LSM hook → audit record
- capability request → MAC check → allow/deny
- namespace transition → policy check → permit

These are the same shape. The receipt chain, the promotion ceremony, the
scope governor, the evidence gate — they all have kernel-level cognates
that are structurally identical, not just analogically similar.

## The Structural Mapping

| Governor | Kernel / Microkernel |
|---|---|
| tool invocation | syscall / IPC message |
| receipt | typed event record for state transition |
| lane routing | criticality class / scheduling domain |
| scope governor | capability boundary / service boundary |
| continuity checker | causal chain across message hops |
| regime detection | latency drift, retry storms, deadline miss patterns |
| evidence gate | precondition arrival (in time, from right path) |
| promotion ceremony | capability transfer with justification |
| provenance labels | binary hash, signer, parent lineage, fs origin |
| entrainment control | process drift into suspicious modes |

## Why Microkernel / RTOS, Not Monolithic

Microkernels factor authority into messages at natural chokepoints:
- IPC send/receive
- capability transfer
- service activation
- fault/restart boundaries
- scheduling decisions

These are places where a temporal receipt system attaches without needing
to understand every application semantically. Much cleaner than inferring
intent from a monolithic kernel's syscall soup.

RTOSes add the temporal dimension that makes this genuinely novel:
- Deadlines, jitter, bounded latency, admission control
- Late is wrong. Stale is dangerous.
- Missing the window changes the truth value of the action.

## The Novel Contribution (vs Existing Security Models)

Existing kernel security (SELinux, AppArmor, Capsicum, LSMs) asks:
**"Do you have the capability?"**

This asks:
**"Can you prove why you should, with what evidence, within what time
budget, with an intact causal chain?"**

Three differences from existing work:

### 1. Receipts, not logs
Hash-chained, content-addressed records that prove which policy version
produced which decision about which operation with which evidence. Not
"something happened" but "here's the proof the decision was legitimate."

### 2. Justified transition, not capability check
A process wanting to `ptrace` another shouldn't just need `CAP_SYS_PTRACE`.
It should justify the transition with evidence (debugger identity, target
relationship, signed build). That's Paper 18's write barrier at the syscall
level.

### 3. Temporal authority
Authority is not just spatial or hierarchical — it is temporal and causal.

- This result is only valid for 50 ms
- This control message must preempt lower-priority work
- This actuator command is unsafe if sensor provenance is older than X
- This request can only inherit authority if the parent chain is within
  freshness bounds

"Stale" becomes a kind of **authority failure**, not just a performance issue.

**Mandatory access control for time.**

## The Minimum Shape

Not "an OS with philosophy in ring 0."
A **tiny enforcement kernel with temporal contracts.**

Each message or capability carries:
- provenance
- deadline / freshness window
- budget
- criticality lane
- parent receipt hash / causal token

Each service declares:
- worst-case service bound
- acceptable staleness
- downgrade behavior
- escalation rules

Kernel enforces:
- admission control
- priority / budget accounting
- deadline-aware scheduling
- capability transfer constraints
- receipt emission at boundary crossings

Everything else is userspace policy.

## Where to Hook (if Linux, not clean-slate)

The sane path: eBPF + userspace policy daemon + receipt kernel.
Don't touch the kernel source. Don't start a mailing list war.

Priority syscalls:
- `execve` — code identity, signer, measurement
- `connect` — egress to sensitive destinations
- `openat` — writes to protected paths
- `ptrace` — injection / debugging
- `mount` / `bind` — overlay tricks
- `bpf` — code loading
- `setuid` / credential changes
- `setns` / `unshare` — namespace operations
- secret material access (keyrings, agent sockets)

Track per transition:
- process ancestry
- executable hash / signer
- cwd / root / ns / cgroup context
- parent receipt chain
- fd and socket origin
- policy lane

Emit: hash-chained receipts via the receipt kernel
(`libs/receipt_kernel/` already does this for agent events).

## The Shadow Governance Connection (Paper 19)

Paper 19's thesis — shadow governance stabilizes when unauthorized
promotions accumulate — is literally the story of every SELinux deployment.
Formal policy exists. Nobody can write it correctly. Permissive mode becomes
permanent. The audit log becomes the Potemkin layer.

The temporal capability kernel's answer: receipts make the shadow layer
*visible* because every authority transition is recorded with its
justification (or lack thereof). You can't accumulate shadow governance
if every transition must show its work.

## Design Constraints

1. **Don't put metaphysics in the scheduler.** The kernel enforces time
   budget, criticality separation, capability boundaries, causal token
   propagation, receipt integrity. Everything else is userspace.

2. **Only govern where authority actually changes.** Not every `read()`.
   The privilege and consequence boundaries. This is the design principle
   that prevents it from becoming auditd with a philosophy degree.

3. **Don't write a new kernel first.** eBPF hooks + userspace policy +
   receipt kernel. Prove the model before touching ring 0.

4. **Provenance explosion is real.** Process trees are easy. Real systems
   have fd passing, shared memory, unix sockets, bind mounts, overlays,
   dlopen, interpreters, plugins, JITs, containers lying about boundaries.
   The lineage question gets spiritual fast.

5. **Policy usability is the actual hard problem.** Too weak = decorative.
   Too strong = SELinux as lifestyle punishment. The gap spec, not the
   hook infrastructure, is where this succeeds or fails.

## What This Is

Pattern recognition. The governor work produced concepts that turn out to
be OS-level concepts in userspace clothing. Worth recording because:

- The receipt kernel is already substrate-agnostic
- The mapping is structural, not metaphorical
- "Mandatory access control for time" is a real research contribution
- The RTOS/microkernel fit is better than the monolithic Linux fit

## What This Is NOT

- Not a commitment to build a kernel
- Not a claim that governor needs to become an OS project
- Not a roadmap item
- Not a paper (yet)

## If It Ever Becomes a Paper

Working title: "Mandatory Access Control for Time: Temporal Capabilities
in Receipt-Bearing Microkernels"

The thesis: authority in adaptive systems is not just spatial or
hierarchical — it is temporal and causal. Existing MAC frameworks enforce
*who can do what*. A temporal capability framework enforces *who can do
what, by when, based on what evidence, with what downstream consequences
if delayed*.

## References
- Paper 18: Unauthorized Durability (promotion ceremony, write barriers)
- Paper 19: The System Beside the System (shadow governance stabilization)
- `libs/receipt_kernel/` — substrate-agnostic receipt chain (already exists)
- `src/governor/scope.py` — scope governor (capability boundaries)
- `src/governor/regime.py` — regime detection (operational drift)
- `src/governor/drift.py` — temporal asymmetry defense
- `specs/core/ENTRAINMENT_CONTROL_MODEL.md` — multiscale control model
- Capsicum (FreeBSD capability mode)
- seL4 (formally verified microkernel)
- RTEMS, Zephyr, QNX (RTOS with capability/partition models)
