# Bubblewrap backend implementation slice — exit ticket

**Done 2026-06-30** (branch `feat/playbooks-synthetic-conveyor`). The real cage backend
authorized by the real-cage-backend review (operator pass, 2026-06-30: facts **C1–C11**,
seccomp required). External `harness/` lane, **no `import governor`**. Implements the
`HarnessCage` contract over bubblewrap. **Runs no actor.**

> Configuration is not containment. The attestation is earned by witnessing.

## Files

- `harness/bwrap_cage.py` (new) — `BwrapCage`, `BwrapProber`, host gate, C1–C11 battery,
  evidence record, persistence. Stdlib + `harness.cage` only.
- `tests/harness/test_bwrap_cage.py` (new, 33 tests).
- `harness/README.md` — bwrap backend section added.

Harness + playbooks regression: **296 passed, exit 0**. Full collection 16484, exit 0.

## How `confirms_isolation=True` is earned (and why it usually is not)

1. **Host gate** — `assess_host` requires Linux + `bwrap` + user namespaces + seccomp
   kernel support + a **cage smoke test** (`bwrap … -- /bin/true` actually starts an
   isolated cage). Any miss → no battery, attest nothing, refuse-live.
2. **Pre-flight negative-probe battery, per run** — for each C1–C11 the prober attempts the
   forbidden action inside a fresh cage and witnesses it fails (or the safe property holds).
   Positive config inspection is not a witness.
3. **Conjunctive mint** — `all_required_witnessed` requires **every** C1–C11. One missing /
   unknown / refused / failed / timed-out fact → attest nothing → refuse-live.
4. **Evidence carried** — per-fact `FactWitness` results ride in `CageRunAttestation` and
   are persisted by `persist_run_attestation()` to the tainted audit store (`run_dir`),
   outside AG ingest. AG ingests only `actor_output.v0`.

`admit_live` reuses `cage.evaluate_live_admission` (the pure guard) — there is **no second
path** to `confirms_isolation=True` besides a full battery pass.

## Acceptance — all met

| Criterion | Evidence |
|-----------|----------|
| Refuses when bubblewrap is missing | `test_host_gate_refuses_when_a_requirement_is_missing[bwrap]`, `test_unsupported_host_refuses_with_no_battery` |
| Refuses when Linux/userns/seccomp unavailable | same parametrized host-gate test (linux/userns/seccomp cases) |
| Each C1–C11 has a test/probe path | `PROBE_SPECS` (C1–C8) + prober-guarantee (C9/C10) + seccomp (C11); `test_probe_specs_cover_inner_command_facts`, `test_fact_set_is_c1_through_c11_all_required`, per-fact `test_any_single_missing_fact_prevents_confirms_isolation` |
| A failed probe prevents `confirms_isolation=True` | `test_any_single_missing_fact_prevents_confirms_isolation` (all 11), `test_admit_live_refuses_when_battery_incomplete_typed` |
| A successful battery is the only path to `True` | `test_full_battery_is_the_only_path_to_confirms_isolation`, `test_all_required_witnessed_is_conjunctive` |
| Attestation evidence includes per-fact witnesses | `test_attestation_carries_per_fact_witnesses`, `test_evidence_persists_under_audit_store_outside_ag` |
| The backend cannot run an actor | `test_backend_has_no_actor_invocation_surface` (AST) |
| Full relevant tests pass | 296 passed, exit 0; collection 16484 |

## Honest live-validation status (lab-substrate doctrine)

This environment is a nested/restricted sandbox: `bwrap` is present and user namespaces are
enabled, but **bwrap cannot establish a cage here** (`loopback: Operation not permitted`),
so the cage smoke fails and the real backend refuses. Additionally the v0 `BwrapProber`
does **not** compile a seccomp BPF filter, so it **never witnesses C11** → the real backend
**refuses live admission in v0 by construction** (`test_real_backend_refuses_live_in_this_environment`,
`test_real_prober_never_witnesses_c11_in_v0`).

Therefore the battery/decision/evidence **logic** is proven against an injected `FakeProber`
(synthetic compatibility — explicitly *not* live testimony), and the real probe path is
real-shaped (genuine `bwrap` argv per fact, executed with a timeout, conservative on any
error). This is the intended "build the zoo, label the cages" outcome: the backend is real,
its gating is real, and it refuses precisely because it has not (and here cannot) witness
containment.

## Intentionally NOT done (stop line held)

- No live actor run; no H2 implementation; no `harness/run.py`; no actor runner. The only
  subprocesses are `bwrap` probe commands testing the cage itself.
- No Claude/Codex/echo invocation; no loop/autopilot; no operational effect; no AG-internal
  live adapter.
- No change to `harness/cage.py` (the contract) or to AG. Evidence is carried in the
  backend's own `CageRunAttestation`; the Protocol's `CageAttestation` is untouched.

## Named follow-ups (each its own gate; do NOT start without operator go)

- **Real C11 witnessing** — compile/install a seccomp BPF filter (libseccomp) so the real
  prober can witness C11 on a capable host. Until then the real backend refuses.
- **Live validation** — exercise the real battery on a host where bwrap can build a cage,
  and record the witnesses as lab-backed **compatibility** evidence (still not authority).
- **H2 implementation** — the one-shot actor invocation (`run_once_under_cage`,
  `harness/run.py`) remains a separate gate; it needs a backend that *can* attest live
  first, plus `armed_live`. A cage that can attest live is necessary, not sufficient.
