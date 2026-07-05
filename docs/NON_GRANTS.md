<!-- STATUS: CANDIDATE (public-mvp S3) — not minted -->

# What Agents Are Deliberately Not Granted

These are structural refusals, not policy suggestions: each is enforced by code
that raises a typed error or typed refusal kind, and each is pinned by a test
whose exit code was verified during authorship. Bootstrap limits apply — an
in-process actor with unrestricted filesystem access sits outside this fence,
and that is documented here, not hidden (see closing section).

---

## Non-grants

### 1. No self-approval

An actor's output never greens its own gate. Required tests remain `not_run`
unless an **independent** verifier receipt covers the command; actor authority
claims are stripped and recorded only as evidence of an attempted claim.

- **Code:** `src/governor/playbooks/actor_output_normalizer.py` lines 336–358
- **Test:** `tests/playbooks/test_actor_output_normalizer.py::test_actor_claimed_pass_still_fails_s5_required_test_not_passing` and `::test_actor_authority_claims_are_stripped_and_recorded_as_evidence` (exit 0)
- **Typed failure:** `ReviewTestResult(status=TEST_NOT_RUN)`; `ReviewAuthority(used=AuthoritySet())` — all axes fully closed

### 2. No authority from prose (two seams)

A written "approved" confers nothing. **Queue seam:** every item must carry an
explicit `operator_approved: true` latch; provenance never substitutes. **Normalizer
seam:** actor authority claims in text are stripped before the packet reaches S5.

- **Code:** `src/governor/playbooks/playbook_queue.py` lines 207–213 (queue); `src/governor/playbooks/actor_output_normalizer.py` lines 352–358 (normalizer)
- **Tests:** `tests/playbooks/test_playbook_queue.py::TestOperatorApproval::test_missing_operator_approved_rejected` and `::test_followup_without_approval_rejected` (exit 0); `tests/playbooks/test_actor_output_normalizer.py::test_actor_authority_claims_are_stripped_and_recorded_as_evidence` (exit 0)
- **Typed failures:** `QueueValidationError(code="not_operator_approved")` (queue); `ReviewAuthority.used = AuthoritySet()` with claims relegated to `risks` (normalizer)

### 3. No minting from ALLOW

An admissibility grant from Standing or Wicket never becomes capacity.
`LinearAccountantClient.request_capacity()` calls the injected LA callable and
returns `GrantedResult` only when LA responds `Granted`; no AG code path
fabricates capacity from a passing admission check alone.

- **Code:** `src/governor/linear_accountant_client.py` lines 652–786 (`request_capacity()`); lines 684–696 (`REFUSAL_ADMISSION_DENIED` when no receipt); lines 699–713 (`REFUSAL_DANGLING_RECEIPT_REFERENCE` when receipt does not resolve)
- **Tests:** `tests/test_linear_accountant_client.py::test_s2_missing_admission_receipt_id_refuses_pre_call_zero_la_calls` (exit 0); `tests/test_ration_card_dispatch.py::TestLaunderingWalls::test_allowlist_membership_is_not_standing_grant` (exit 0)
- **Typed failures:** `RefusalResult(kind="admission_denied")` / `RefusalResult(kind="dangling_receipt_reference")` — drawn from the closed `CLOSED_REFUSAL_KINDS` set enforced by `RefusalResult.__post_init__`

### 4. No agent-to-agent coordination

There is no agent-to-agent messaging surface in the module tree. The only
coordination primitive is the ledger: `ClaimType.WORK_RESERVATION`, which
requires explicit `scope` and `task` fields validated at construction.
Bypassing the ledger is structurally unrepresentable, not merely discouraged.

- **Code:** `src/governor/claims.py` line 41 (`ClaimType.WORK_RESERVATION`), line 56 (required field constraints; line 68 is the optional-field set); no `AgentMessage` or inter-agent RPC class exists in the codebase
- **Tests:** `tests/test_claims.py::TestMultiAgentClaims::test_work_reservation_valid` and `::test_work_reservation_requires_scope_and_task` (exit 0)
- **Typed failure:** `ValueError` at `Claim.__post_init__` on missing required fields; no "rejected message" code because there is no message surface

### 5. No network or write outside the ration (two seams)

**Ration card:** `git_allowed`, `doctrine_writes_allowed`, and `network_allowed`
are locked `False` in `RationCard.__post_init__`; opening any axis raises at
construction before any spend. **Outer cage** (defense in depth,
not the binding seam): when a cage is constructed with `network="denied"`
(the default), bwrap passes `--unshare-net` and Docker passes
`--network none` — OS-level absence for that run. A cage *can* be
constructed open (`network="allowed"` / `kind="none"`); the non-grant is
carried by the ration card, which refuses `network_allowed` at
construction unconditionally.

- **Code:** `src/governor/playbooks/ration_card.py` lines 93–104; `src/governor/runtime/adapters/antigravity_runner.py` lines 102–114 (`OuterCage`, `network="denied"` default) and lines 138–140 / 165–167 (cage argv construction)
- **Tests:** `tests/test_ration_card_dispatch.py::TestCardLocks::test_card_refuses_dangerous_axes` (exit 0); `tests/test_antigravity_runner.py::test_bwrap_argv_denies_network_and_fences_writes` (exit 0)
- **Typed failures:** `ValueError("ration card may not allow network")` at card construction; `--unshare-net` / `--network none` in constructed cage argv (test asserts on the argv list)

### 6. No unwitnessed clock math

Time gaps must be computed over typed `MonotonicReading` objects sharing the
same `source` and `epoch`. `elapsed_ns()` is the only licensed subtraction;
a `StandingWindow` cannot be built from bare integers — the mandatory-basis
discipline is enforced by type.

- **Code:** `src/governor/clock_witness.py` lines 102–124 (`elapsed_ns()` raises `GapBasisMismatch` / `MonotonicEpochMismatch`); `src/governor/standing_spendability.py` lines 139–149 (`StandingWindow.__post_init__` refuses a non-`MonotonicReading` gap basis)
- **Tests:** `tests/test_clock_witness.py::TestElapsedRefusesIncompatibleBases::test_different_source_refuses` and `::test_same_ns_different_epoch_refuses` (exit 0); `tests/test_standing_spendability.py::TestRatifiedPins::test_bare_int_clock_costume_is_unrepresentable` (exit 0)
- **Typed failures:** `GapBasisMismatch` (source mismatch or backwards reading); `MonotonicEpochMismatch` (cross-epoch / cross-reboot); `MalformedStandingWindowError` (bare integer as gap basis)

### 7. No spend past the standing horizon

A spend attempt whose standing observation lapsed past its freshness bound
between observation and exercise time is refused, even when the standing was
valid at observation. A receipt is emitted on both paths.

- **Code:** `src/governor/standing_spendability.py` lines 241–295 (`evaluate_spendability_window()` and `StandingSpendabilityGate.check()`)
- **Test:** `tests/test_standing_spendability.py::TestRatifiedPins::test_gap_exceeds_bound_refuses_with_full_block` (exit 0)
- **Typed failure:** `SpendabilityRefusal(kind="standing_before_spendability_not_bounded", block={gap_ns, bound_ns, overage_ns, lapse_coverage, freshness_subcase, gap_basis})`

### 8. No operational effect from drills or synthetic runs

A chain outcome whose `origin_mode` is not `"observed"` is wrapped as
`DemonstratedConsumed`. `confer_operational_effect()` refuses it by type via
`isinstance`, raising `NonOperationalSpendError`. Real effect is unrepresentable
from a non-operational origin, not merely guarded by a boolean.

- **Code:** `src/governor/cooked_context_orchestrator.py` lines 578–611 (`confer_operational_effect()`)
- **Tests:** `tests/test_operational_spend_fence.py::TestSpendSeamWall::test_demonstrated_is_refused_by_type` (exit 0); `tests/test_origin_admission_fence.py::test_pinning_novel_origin_never_admitted` (exit 0)
- **Typed failure:** `NonOperationalSpendError` carrying `origin_mode` and `reason`

### 9. Fail-closed pre-tool gate

The Claude Code pre-tool hook denies (blocks the tool call) on decision timeout,
socket error, missing configuration, or a garbled supervisor response. Silence
and ambiguity are treated as denials; the hook cannot be bypassed by degrading
the supervisor connection.

- **Code:** `src/governor/runtime/adapters/claude_code.py` lines 55–157 (inline hook script: `_deny()` defined at 67; timeout / socket-error / missing-config / garbled-response paths route to it at 106, 112, 147–153)
- **Tests:** `tests/test_pre_tool_fail_closed.py::TestFailClosedPaths::test_deny_on_decision_timeout` and `::test_deny_on_unreachable_socket` (exit 0)
- **Typed failure:** nested envelope on stdout: `{"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": "<reason>"}}`; Claude Code treats this as a block

---

## What This List Does Not Claim

The nine entries above cover structural surfaces in the shipped Python codebase,
all verified by running the cited tests. They do not warrant: (a) in-process
custody forgeability — an in-process actor with unrestricted filesystem access
sits outside this fence and that is a documented bootstrap limit, not a hidden
gap; (b) unarmed cage paths — bwrap and Docker cages require a working kernel
with user-namespaces or Docker, and `cage_preflight` refuses to run an agent
if no working cage can be proven on the host; (c) live constellation wiring —
several seams reference harness stubs against sibling-repo contracts; the
structural refusals are real, but live reachability of remote repos is a
separate operational question; (d) exhaustiveness — this campaign covers nine
surfaces; other seams exist and this list does not claim to enumerate all of
them.
