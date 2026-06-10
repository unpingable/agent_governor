# SPDX-License-Identifier: Apache-2.0
"""
Status: D0-Origin — drill runner consumes genuine NQ FindingSnapshot
Authority: AG-side library invoked by nightshift's `watchbill run --drill`
Promotion: stable when D0d harness lands; supersession via D0d/D0-Origin reopen

D0-Origin upgrade (2026-06-10): replaces D0d-a's constructed FindingSnapshot
fixture with a genuine NQ-emitted snapshot. Night Shift now stages a real
WAL-bloat condition on a sandbox SQLite DB, invokes ``nq-monitor drill
wal-bloat`` to produce ``nq.finding_snapshot.v1`` JSON via the production
evaluator pipeline, and passes that JSON path to this module via
``--finding-json <path>``. The runner consumes the genuine wire DTO and
runs the four-link chain against it.

The fixture-driven path is preserved as the default for tests that
exercise the runner outside the cross-repo harness — when
``--finding-json`` is omitted, ``build_drill_finding_snapshot`` runs as
before.

Original D0d-a slice: minimal deterministic drill runner. Drives the
cooked-context orchestrator end-to-end against an NQ-shaped
FindingSnapshot DTO carrying ``origin_mode=drill`` and emits a
deterministic transcript of the chain.

One scenario for this slice: ``all-green``. Standing verifies, wicket
admits, LA grants, LA consumes. Four GateReceipts written through the
real ``GateReceiptSystem``, every receipt's evidence_bundle carries
``origin_mode=drill``.

Hard rules honored verbatim from the slice spec:

1. NQ-origin: the runner consumes an NQ-shaped FindingSnapshot dict whose
   ``origin_mode`` key is ``"drill"``. The orchestrator's closed origin-mode
   set already admits ``drill`` per D0-Bridge.
2. Real ``GateReceipt`` emission at every seam — standing seam, wicket
   admission, LA request, LA consume. Four receipts.
3. ``origin_mode=drill`` stamped on every emit via the existing
   ``_OriginModeReceiptSink`` wrapper. No client-side modification.
4. The proposal packet is a **deterministic stub**: a fixed template
   citing receipt ids. No LLM. The "all-green proposal packet" is bounded
   text derived mechanically from the finding id, the capacity token id,
   the observed_at field, and the four receipt ids.
5. ``governor why`` is consulted via the in-process library entry point
   (``walk_chain`` + ``render_text``) so the transcript embeds the same
   render the CLI would produce. The runner does NOT re-implement chain
   walking.
6. Deterministic transcript: every byte derivable from inputs. Receipt
   ids are content-addressed and reproducible across runs with identical
   input. Timestamps are deliberately NOT rendered in the transcript
   (they are metadata, not identity) so two runs with the same inputs
   produce byte-identical output.

Forbidden, verbatim from the slice:

  * No LLM call (the all-green proposal packet is a deterministic stub).
  * No LLM as drill narrator (transcript is deterministic from ledger).
  * No multiple CLI entry points (this module is a library + a
    ``python3 -m`` entry, intended to be shelled into by Night Shift).
  * No more than one scenario this slice (``all-green`` only).
  * No new refusal kinds. No S4-lite vocabulary change.
  * No widening of AG's origin-mode vocabulary beyond
    ``{cli_origin, stub_origin, observed, drill, replay, synthetic}``.
  * No GateReceipt envelope schema change. ``evidence_bundle`` is
    open/additive — fine.

Single entry point invariant: this module is library code, plus a
``python3 -m governor.drill_runner`` entry that returns JSON. The
operator-load-bearing CLI surface ``nightshift watchbill run
wal-bloat-review --drill --scenario=all-green`` is owned by Night Shift
and shells into this module. AG does NOT add a competing
``governor drill`` CLI command — that would mint ownership ambiguity
per §3b "two entry points would mint ownership ambiguity. ONE entry
point. Nightshift owns it."
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from governor.cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    ORIGIN_MODE_DRILL,
    ChainResult,
    CookedContextOrchestrator,
    wrap_receipt_sink_with_origin_mode,
)
from governor.gate_receipt import GateReceiptSystem
from governor.linear_accountant_client import (
    LA_DECISION_CONSUMED,
    LA_DECISION_GRANTED,
    ConsumedResult,
    CookedCapacityRequest,
    CookedConsumeRequest,
    LinearAccountantClient,
)
from governor.standing_client import StandingClient, StandingReceiptRef
from governor.why import render_text, walk_chain
from governor.wicket_client import (
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
)


# ---------------------------------------------------------------------------
# Scenario vocabulary.
#
# D0d-a shipped with a single scenario (``all-green``). D0d-1 widens the
# closed set to the six-scenario gauntlet ratified at campaign §3 D2:
#
#   1. ``no-standing``           → standing seam refuses
#                                  (refusal_kind=standing_required)
#   2. ``standing-expired``      → standing seam refuses
#                                  (refusal_kind=standing_expired)
#   3. ``wicket-denied``         → LA seam refuses on admission denial
#                                  (refusal_kind=admission_denied)
#   4. ``wicket-gap-accounted``  → proceeds with gap citation in the
#                                  proposal packet (full chain)
#   5. ``replay-budget``         → consume is invoked twice with the
#                                  same consumption_event_id; second
#                                  call returns AlreadyConsumed
#                                  (refusal_kind=already_consumed)
#                                  and the downstream effect counter
#                                  remains 1 (replay kill)
#   6. ``all-green``             → existing happy path (chain completes,
#                                  proposal packet emitted)
#
# The operator-load-bearing accepted alias is ``already-consumed`` for
# scenario 5. Canonical name is ``replay-budget``; the alias resolves
# at construction-time. No other aliases are admitted; everything else
# raises ``UnsupportedScenarioError`` at construction (mirrors the
# D0c-b ``InvalidOriginModeError`` pattern).
#
# Critical guardrail (operator-load-bearing): per-scenario variation
# lives in the AG-side injected callables and verifier state. The NQ-side
# FindingSnapshot is byte-identical across all six scenarios — Night
# Shift's drill stages the same WAL-bloat condition once and passes the
# scenario string through. No "detector zoo" — gate state varies, not
# the workload.
# ---------------------------------------------------------------------------

SCENARIO_ALL_GREEN = "all-green"
SCENARIO_NO_STANDING = "no-standing"
SCENARIO_STANDING_EXPIRED = "standing-expired"
SCENARIO_WICKET_DENIED = "wicket-denied"
SCENARIO_WICKET_GAP_ACCOUNTED = "wicket-gap-accounted"
SCENARIO_REPLAY_BUDGET = "replay-budget"
SCENARIO_ALIAS_ALREADY_CONSUMED = "already-consumed"


# ---------------------------------------------------------------------------
# D3 — confabulated-receipt closing beat.
#
# A proposal-packet citation step layered ON TOP of the all-green chain (the
# only chain that reaches a proposal packet). Per §3 D3 and §3b "the LLM may
# not cite what was never witnessed": after standing → wicket → LA grant → LA
# consume have all succeeded, the runner is allowed to inject a bogus citation
# into the proposal packet under operator control. The validator then refuses
# with ``dangling_receipt_reference`` (the S4-lite-ratified kind for AG-side
# admission_receipt_id miss — operator-ratified for reuse here per the slice
# tier-3 vocabulary fence).
#
# Two roles are accepted, both injecting a single bogus citation:
#
#   * ``standing``  — bogus ``standing_receipt_id`` citation. Existence-fail
#                     test: the fixed-bogus id is content-addressed but never
#                     minted by any seam in the chain; the validator detects
#                     it via the receipt-store lookup miss.
#   * ``evidence``  — kind-fit-fail test: the LA token_id (a real string
#                     present in the receipts via the consume bundle but
#                     NOT a standing receipt) is cited in the
#                     ``standing_receipt_id`` slot. The validator detects
#                     the kind mismatch by reading the existing structural
#                     attributes of the cited receipt (gate name +
#                     ``verified_standing`` marker on the evidence bundle).
#                     This is a GUARD, not a typed enum (per the
#                     ``feedback_kind_fit_is_guard_not_enum`` doctrine cited
#                     in the slice prompt).
#
# Both modes are only meaningful with ``--scenario=all-green`` because that
# is the only scenario where the chain reaches the proposal-packet step.
# Passing the flag with any other scenario raises
# ``InvalidConfabulationRoleError`` at construction-time per the
# refuse-at-construction pattern (mirroring ``UnsupportedScenarioError``).
#
# Per §3b retry economics:
#
#   * LA.consume has already fired; ``_EffectCounter`` is at 1; real budget
#     was spent before the validator runs. Failure costs real budget.
#   * The validator emits a refusal receipt whose ``parent_receipt_ids``
#     cites the consume receipt id so ``governor why`` walks
#     refusal → consume → grant → admission → standing → finding.
#   * No mutation happens past the validator refusal — the proposal packet
#     is NOT emitted.
#   * Re-attempt requires a NEW chain spend; the validator does not
#     retry-in-place.
# ---------------------------------------------------------------------------

CONFABULATION_ROLE_STANDING = "standing"
CONFABULATION_ROLE_EVIDENCE = "evidence"
CONFABULATION_ROLES = frozenset(
    {CONFABULATION_ROLE_STANDING, CONFABULATION_ROLE_EVIDENCE}
)

# Deterministic fixed-bogus receipt id used by ``confabulate-citation=standing``.
# Stable across runs so the transcript stays byte-identical after the existing
# normalization. Length matches the content-addressed-hash receipt-id shape
# (64 hex chars on standard receipts; we use a recognizable prefix to make
# it obvious in the receipt-store / transcript that this is the bogus id).
BOGUS_STANDING_RECEIPT_ID = "ag_rcpt_BOGUS_0000000000000000000000000000000000000000000000000000000000"

# Validator gate name. Sensible default; no other AG gate currently carries
# this name. Surfaced as a tier-3 candidate in the slice output for
# operator-aware ratification, even though no second plausible name was
# found that would force the STOP escape.
PROPOSAL_VALIDATOR_SEAM_GATE = "proposal_validator_seam"


class InvalidConfabulationRoleError(ValueError):
    """Raised when ``--confabulate-citation`` is passed with an invalid role
    or in combination with a scenario that does not reach the proposal-packet
    step.

    The closed role set is ``{standing, evidence}``. The flag may only be
    paired with ``--scenario=all-green`` because that is the only scenario
    where the proposal packet is emitted; any other scenario short-circuits
    before the proposal step. Refuse at construction time, never silently
    substitute (mirrors the ``UnsupportedScenarioError`` pattern).
    """

# Closed canonical scenario set — exactly six values. CLI gate at both
# the Night Shift and AG entry points refuses anything else (including
# the D0d-a era scenario names like ``1_no_standing`` / ``6_all_green``).
SUPPORTED_SCENARIOS = frozenset(
    {
        SCENARIO_NO_STANDING,
        SCENARIO_STANDING_EXPIRED,
        SCENARIO_WICKET_DENIED,
        SCENARIO_WICKET_GAP_ACCOUNTED,
        SCENARIO_REPLAY_BUDGET,
        SCENARIO_ALL_GREEN,
    }
)

# Operator-ratified alias for the replay scenario. Resolved at
# ``_canonical_scenario`` (the single normalization site).
SCENARIO_ALIASES = {
    SCENARIO_ALIAS_ALREADY_CONSUMED: SCENARIO_REPLAY_BUDGET,
}


def _canonical_scenario(scenario: str) -> str:
    """Resolve aliases to canonical scenario names.

    The single normalization site. ``already-consumed`` → ``replay-budget``.
    Everything else passes through unchanged; the caller does the
    closed-set membership check afterward so unknown scenarios surface
    with the original name in the error message (operator legibility).
    """
    return SCENARIO_ALIASES.get(scenario, scenario)


class UnsupportedScenarioError(ValueError):
    """Raised when an unsupported scenario name is passed.

    The closed set is the six-scenario gauntlet ratified at campaign
    §3 D2: ``{no-standing, standing-expired, wicket-denied,
    wicket-gap-accounted, replay-budget, all-green}``. The operator-
    accepted alias ``already-consumed`` resolves to ``replay-budget``;
    no other aliases are admitted. Anything else (including legacy
    D0d-a era names like ``1_no_standing``) raises here.

    Mirrors the ``InvalidOriginModeError`` pattern from D0c-b: refuse
    at construction time, never silently substitute.
    """


# ---------------------------------------------------------------------------
# Deterministic fixture builders.
#
# These produce a stable NQ-shaped FindingSnapshot dict and the cooked
# context that the orchestrator consumes. Determinism rule: every input
# either comes from the caller (and is therefore stable across runs the
# caller controls) or is hard-coded here. Nothing is read from the wall
# clock, the process environment, or the filesystem.
# ---------------------------------------------------------------------------

# Stable standing-side digest used by the all-green scenario. Hex SHA-256
# shape per `~/git/standing/standing-receipt/src/receipt.rs`. The actual
# digest value is fixture material — what matters for the bridge is that
# it is a valid 64-hex-char string and that the same value is fed to both
# the cooked context and the standing verifier so verification succeeds.
ALL_GREEN_STANDING_DIGEST = "d" * 64

# Stable scope name. Picked once, used everywhere in this scenario.
ALL_GREEN_SCOPE = "fs_write"

# Deterministic fixture timestamps. Used for the cooked context
# call_timestamp and the finding observed_at. NOT rendered into the
# transcript (timestamps are metadata; rendering them would break
# byte-identical determinism if the runner is ever called with a
# different deterministic timestamp). Stable values pinned here.
ALL_GREEN_OBSERVED_AT = "2026-06-09T00:00:00Z"
ALL_GREEN_CALL_TIMESTAMP = "2026-06-09T00:00:00Z"

# Deterministic NQ finding identity for the all-green scenario.
ALL_GREEN_FINDING_ID = "nq_fnd_drill_wal_bloat_all_green"

# Deterministic capacity token id baked into the LA grant fake.
ALL_GREEN_CAPACITY_TOKEN_ID = "tok_drill_all_green_001"

# Deterministic stable identifiers.
ALL_GREEN_ACTOR = "claude-code"
ALL_GREEN_INTENDED_ACTION = "diagnose_wal_bloat"
ALL_GREEN_TARGET = "/db/wal"


def build_drill_finding_snapshot(scenario: str = SCENARIO_ALL_GREEN) -> dict[str, Any]:
    """Build a deterministic NQ-shaped FindingSnapshot DTO.

    The DTO matches the canonical NQ wire shape from migration 057. Only
    the fields the AG-side bridge consumes are populated; other fields
    are out of scope (the Rust-side covers full DTO validation).

    D0d-1 invariant: the FindingSnapshot is BYTE-IDENTICAL across all
    six scenarios. Per-scenario variation lives on the AG side (different
    injected callables, different verifier state); the workload (the
    genuine WAL-bloat finding) stays the same. Constructing different
    snapshots per scenario would be the "detector zoo" failure mode the
    operator guardrail prohibits. The scenario is validated against the
    closed set, then ignored when building the DTO body.
    """
    canonical = _canonical_scenario(scenario)
    if canonical not in SUPPORTED_SCENARIOS:
        raise UnsupportedScenarioError(
            f"scenario {scenario!r} not in the closed scenario set; "
            f"supported scenarios: {sorted(SUPPORTED_SCENARIOS)}; "
            f"accepted aliases: {sorted(SCENARIO_ALIASES)}"
        )
    # Drill provenance: per D0-Bridge, the NQ-side closed set contains
    # ``drill``. AG admits it verbatim; no aliasing. Same fixture body
    # across all six scenarios — gate state varies, not the workload.
    return {
        "schema": "nq.finding_snapshot.v1",
        "contract_version": 1,
        "finding_key": "local/host-drill/wal_bloat/%2Fdb%2Fwal",
        "finding_id": ALL_GREEN_FINDING_ID,
        "identity": {
            "scope": "local",
            "host": "host-drill",
            "detector": "wal_bloat",
            "subject": "/db/wal",
            "rule_hash": None,
        },
        "origin_mode": ORIGIN_MODE_DRILL,
        "observed_at": ALL_GREEN_OBSERVED_AT,
    }


class InvalidFindingSnapshotError(ValueError):
    """Raised when an external FindingSnapshot fails the bridge contract.

    The bridge contract for an external (NQ-produced) snapshot:

      * Top-level ``schema`` must equal ``"nq.finding_snapshot.v1"``.
      * ``origin_mode`` must be in
        ``cooked_context_orchestrator.NQ_ORIGIN_MODES`` — the closed
        set defined by NQ migration 057.
      * ``identity`` block must be present with ``host`` and
        ``detector`` fields (the chain identity inputs the
        orchestrator threads through).
      * For the D0-Origin scenario, ``identity.detector`` must equal
        ``"wal_bloat"`` (that is the only condition Night Shift's
        stager produces; refusing here surfaces a future regression
        where Night Shift stages a different condition without
        amending this code).

    Refusal is at parse time. No silent normalization — laundering a
    malformed snapshot into a default shape would re-enact the same
    custody-gap failure mode this slice closed.
    """


def load_finding_snapshot_from_json(
    path: Path,
    *,
    scenario: str = SCENARIO_ALL_GREEN,
) -> dict[str, Any]:
    """Load a genuine NQ-produced FindingSnapshot from a JSON file.

    The file is what Night Shift's drill runner writes after invoking
    ``nq-monitor drill wal-bloat`` against a staged sandbox. The shape
    is the canonical ``nq.finding_snapshot.v1`` DTO.

    We accept either:

      * a single JSON object — the bridge's preferred shape, written by
        Night Shift's ``capture_genuine_nq_finding``; OR
      * a single-element JSON array — what
        ``nq-monitor drill wal-bloat --format json`` writes natively
        before Night Shift unwraps it. We tolerate both so operators can
        feed the AG-side path directly without a Night Shift wrapper.

    Refuses loudly on shape violations. See
    ``InvalidFindingSnapshotError`` for the contract.
    """
    raw = json.loads(path.read_text())
    if isinstance(raw, list):
        if len(raw) != 1:
            raise InvalidFindingSnapshotError(
                f"finding JSON at {path} is an array of length {len(raw)}; "
                f"D0-Origin admits exactly one snapshot per drill (one staged "
                f"DB → one detector firing → one snapshot). Multiple snapshots "
                f"would indicate the sandbox is observing more than the staged "
                f"condition, which violates the smoke-machine guarantee."
            )
        snapshot = raw[0]
    elif isinstance(raw, dict):
        snapshot = raw
    else:
        raise InvalidFindingSnapshotError(
            f"finding JSON at {path} is neither a JSON object nor a "
            f"single-element array; got {type(raw).__name__}"
        )

    # Bridge contract enforcement.
    schema = snapshot.get("schema")
    if schema != "nq.finding_snapshot.v1":
        raise InvalidFindingSnapshotError(
            f"finding JSON schema is {schema!r}; bridge admits only "
            f"'nq.finding_snapshot.v1'"
        )
    origin_mode = snapshot.get("origin_mode")
    # Lazy import to avoid a circular surface — orchestrator already
    # imports from this module's siblings.
    from governor.cooked_context_orchestrator import NQ_ORIGIN_MODES

    if origin_mode not in NQ_ORIGIN_MODES:
        raise InvalidFindingSnapshotError(
            f"finding JSON origin_mode={origin_mode!r} is not in the closed "
            f"NQ vocabulary {sorted(NQ_ORIGIN_MODES)!r}"
        )
    identity = snapshot.get("identity") or {}
    if not isinstance(identity, dict):
        raise InvalidFindingSnapshotError(
            f"finding JSON identity block is not an object; got "
            f"{type(identity).__name__}"
        )
    detector = identity.get("detector")
    if detector != "wal_bloat":
        raise InvalidFindingSnapshotError(
            f"finding JSON identity.detector={detector!r}; D0-Origin all-green "
            f"scenario expects 'wal_bloat'"
        )
    if not identity.get("host"):
        raise InvalidFindingSnapshotError(
            "finding JSON identity.host is empty or missing"
        )

    # The orchestrator path's CookedContext threads a ``finding_id`` into
    # the standing receipt as parent. NQ-side snapshots use
    # ``finding_key`` for chain identity; we use that as the AG-side
    # ``finding_id`` so the chain head still reaches the NQ origin via a
    # stable, content-addressed reference.
    finding_key = snapshot.get("finding_key")
    if not finding_key:
        raise InvalidFindingSnapshotError(
            "finding JSON finding_key is empty or missing"
        )

    # Project onto the AG-side bridge shape. We carry the full original
    # snapshot under a sub-key so the transcript renderer can show
    # source provenance, but the orchestrator-facing dict uses the
    # fixture-compatible top-level shape (``finding_id``,
    # ``observed_at``).
    observed_at_block = snapshot.get("lifecycle", {})
    observed_at = (
        observed_at_block.get("first_seen_at")
        if isinstance(observed_at_block, dict)
        else None
    ) or snapshot.get("observed_at") or ALL_GREEN_OBSERVED_AT
    return {
        "schema": "nq.finding_snapshot.v1",
        "contract_version": snapshot.get("contract_version", 1),
        "finding_key": finding_key,
        "finding_id": finding_key,
        "identity": identity,
        "origin_mode": origin_mode,
        "observed_at": observed_at,
        # Verbatim source for the transcript renderer / future
        # auditability paths. Keeping the original snapshot around
        # means a downstream reviewer can re-verify the bridge
        # decision against the wire bytes without re-running NQ.
        "_nq_snapshot": snapshot,
        "_source": "nq_drill_finding_json",
        "_scenario": scenario,
    }


def _cooked_context_for_finding(
    finding: dict[str, Any],
) -> CookedContext:
    """Translate the NQ-shaped DTO + fixture material into a CookedContext.

    The cook step lives here so the Night Shift side need not know AG's
    cooked-context shape — it only feeds the DTO across the boundary.
    """
    # The drill scenario uses the fixed all-green standing digest. A
    # later scenario will pick a different digest (or omit it) to drive
    # a different refusal shape.
    standing_receipt_id = ALL_GREEN_STANDING_DIGEST
    return CookedContext(
        actor=ALL_GREEN_ACTOR,
        actor_standing=ActorStanding(cls="interpret", provenance="caller_asserted"),
        intended_action=ALL_GREEN_INTENDED_ACTION,
        operation_class="execute",
        target=ALL_GREEN_TARGET,
        claimed_basis={
            "rule": "drill_all_green",
            "evidence_refs": [finding["finding_id"]],
        },
        precedence=Precedence(
            resolution="active",
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        expected_effect="emit bounded diagnosis proposal packet",
        call_timestamp=ALL_GREEN_CALL_TIMESTAMP,
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True,
            provenance="caller_asserted",
            evidence_refs=(),
        ),
        prev_receipt_hash=None,
    )


def _capacity_template_for_finding(finding: dict[str, Any]) -> CookedCapacityRequest:
    """Build the capacity-request template. Orchestrator overwrites
    ``admission_receipt_id`` with the wicket-emitted admission id."""
    return CookedCapacityRequest(
        request_id=f"req_{finding['finding_id']}",
        actor=ALL_GREEN_ACTOR,
        action=ALL_GREEN_INTENDED_ACTION,
        target=ALL_GREEN_TARGET,
        scope=ALL_GREEN_SCOPE,
        requested_capacity=1,
        admission_receipt_id="will-be-replaced",
        eligibility_valid_until=1000,
        expires_after=1000,
        idempotency_key=f"idem_{finding['finding_id']}",
    )


def _consume_template_for_finding(finding: dict[str, Any]) -> CookedConsumeRequest:
    """Build the consume template. Orchestrator overwrites ``token_id``
    with the LA-granted token id."""
    return CookedConsumeRequest(
        consumption_event_id=f"evt_{finding['finding_id']}",
        token_id="will-be-replaced",
        actor=ALL_GREEN_ACTOR,
        action=ALL_GREEN_INTENDED_ACTION,
        target=ALL_GREEN_TARGET,
        amount=1,
        scope=ALL_GREEN_SCOPE,
    )


# ---------------------------------------------------------------------------
# Deterministic LA fakes.
#
# These are bounded deterministic stubs — they reply with fixed payloads
# given the request shape. No randomness, no IO. The token id and
# receipt ids are constants so the all-green proposal packet can cite
# stable strings.
# ---------------------------------------------------------------------------


def _granted_response(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_GRANTED,
        "token_id": ALL_GREEN_CAPACITY_TOKEN_ID,
        "granted_capacity": la_request["requested_capacity"],
        "scope": la_request["scope"],
        "expires_at": now + la_request["expires_after"],
        # The LA-side receipt id is opaque to AG; pin a stable string so
        # the deterministic transcript can quote it without drift.
        "receipt": {"la_receipt_id": "la_grant_drill_all_green_001"},
    }


def _consumed_response(la_request: dict, now: int) -> dict:
    return {
        "decision": LA_DECISION_CONSUMED,
        "token_id": la_request["token_id"],
        "consumed_amount": la_request["amount"],
        "remaining_capacity": 0,
        "receipt": {"la_receipt_id": "la_consume_drill_all_green_001"},
    }


def _wicket_admit_any(cooked_context: CookedContext) -> dict:
    """All-green wicket downstream: admit any cooked context that
    reaches it. The wicket SPEC §7/§8 verdict shape is opaque to AG
    here; a deterministic stub returns a stable dict."""
    return {
        "surface_verdict": "authorized",
        "_drill_stub": True,
    }


# ---------------------------------------------------------------------------
# Proposal packet — deterministic stub (no LLM).
#
# Per §3b: "The all-green proposal packet is a deterministic stub. A
# fixed template like `Diagnose WAL bloat — finding {id}, capacity
# {token_id}, observed at {ts}` cites receipt ids without invoking a
# model."
# ---------------------------------------------------------------------------


PROPOSAL_PACKET_TEMPLATE = (
    "Diagnose WAL bloat — finding {finding_id}, capacity {token_id}, "
    "observed at {observed_at}"
)


def build_proposal_packet(
    finding: dict[str, Any],
    consumed: ConsumedResult,
    receipt_ids: list[str],
) -> dict[str, Any]:
    """Build the deterministic all-green proposal packet.

    No model invoked. The text is a fixed template citing the finding id,
    the granted capacity token id, the observed_at timestamp from the
    finding, and the four receipt ids minted on the chain.
    """
    text = PROPOSAL_PACKET_TEMPLATE.format(
        finding_id=finding["finding_id"],
        token_id=consumed.token_id,
        observed_at=finding["observed_at"],
    )
    return {
        "status": "emitted",
        "text": text,
        "citations": [
            finding["finding_id"],
            *receipt_ids,
            consumed.token_id,
        ],
    }


# ---------------------------------------------------------------------------
# Chain driver.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# D3 — citation validator (minimal, proposal-packet only).
#
# Two checks, both required, both running off receipts already on disk:
#
#   1. Existence: ``ReceiptStore.get_by_id(cited_id)`` returns non-None.
#   2. Kind-fit: when the cited slot is the standing receipt role, the fetched
#      receipt's ``gate`` must equal ``standing_seam`` AND its
#      ``evidence_bundle["verified_standing"]`` must be True. Both attributes
#      are structural — derived from the existing chain receipts, not from a
#      typed ``ArtifactKind`` enum. The guard explicitly fires on the
#      kind-fit-fail test where the LA token id (a real string from the
#      consume bundle, but never minted AS a standing receipt) is cited.
#
# Failure surfaces a structured result (kind + detail) the runner uses to
# emit a single ``dangling_receipt_reference`` GateReceipt. No new refusal
# kinds; both failure modes use the existing S4-lite kind, distinguished by
# detail prose (and by ``citation_check`` in the evidence bundle for machine
# readers).
# ---------------------------------------------------------------------------


# Closed enum for the failure-mode detail. NOT a typed kind taxonomy —
# this is a string tag inside the evidence bundle that lets a JSON
# consumer distinguish existence-fail from kind-fit-fail without
# parsing the detail prose. Both still map to the same refusal kind
# (``dangling_receipt_reference``). One file, one place.
CITATION_CHECK_EXISTENCE = "existence"
CITATION_CHECK_KIND_FIT = "kind_fit"


@dataclass(frozen=True)
class CitationValidationResult:
    """Result of validating a single citation slot.

    ``ok=True`` means the cited id exists AND is kind-fit for the role.
    ``ok=False`` carries the failure mode in ``check`` (one of
    ``CITATION_CHECK_EXISTENCE`` / ``CITATION_CHECK_KIND_FIT``) plus a
    human-readable ``detail``.
    """

    ok: bool
    check: Optional[str] = None
    detail: Optional[str] = None


def _validate_standing_citation(
    *,
    cited_id: str,
    system: GateReceiptSystem,
) -> CitationValidationResult:
    """Validate one ``standing_receipt_id`` slot citation.

    Reads the receipt store + evidence store; never mutates. Both
    checks run on the receipt's existing structural attributes — there
    is no ``ArtifactKind`` / ``UseKind`` enum dispatched on here.

    Existence check: ``ReceiptStore.get_by_id(cited_id) is not None``.

    Kind-fit check: the fetched receipt's ``gate`` field must be
    ``standing_seam`` AND its evidence bundle must carry the
    ``verified_standing: True`` descriptive marker that
    ``standing_client._emit_verified_receipt`` stamps on every
    standing-side positive receipt. Both attributes are structural —
    if a future seam ever needs to mint standing receipts, it will
    have to set the same marker, and this guard remains correct.
    """
    receipt = system.receipt_store.get_by_id(cited_id)
    if receipt is None:
        return CitationValidationResult(
            ok=False,
            check=CITATION_CHECK_EXISTENCE,
            detail=(
                f"standing_receipt_id {cited_id!r} cited in proposal "
                "packet but no receipt with that id was minted in this "
                "chain (existence check fail)"
            ),
        )
    bundle = system.evidence_for(receipt)
    if receipt.gate != "standing_seam" or not (
        isinstance(bundle, dict) and bundle.get("verified_standing") is True
    ):
        return CitationValidationResult(
            ok=False,
            check=CITATION_CHECK_KIND_FIT,
            detail=(
                f"receipt {cited_id!r} cited in standing_receipt_id slot "
                f"but its structural kind is wrong — gate={receipt.gate!r}, "
                f"verified_standing="
                f"{bundle.get('verified_standing') if isinstance(bundle, dict) else None!r} "
                "(kind-fit check fail)"
            ),
        )
    return CitationValidationResult(ok=True)


def _emit_proposal_validator_refusal(
    *,
    system: GateReceiptSystem,
    bogus_cited_id: str,
    citation_role: str,
    validation: CitationValidationResult,
    parent_receipt_id: str,
    origin_mode: str,
    finding_id: str,
) -> str:
    """Emit the D3 refusal GateReceipt and return its id.

    Uses ``GateReceiptSystem.emit`` directly with the existing closed
    verdict vocabulary (``block``) and the closed S4-lite refusal kind
    (``dangling_receipt_reference``). The evidence bundle records the
    failure-mode tag so JSON consumers can distinguish existence-fail
    from kind-fit-fail without parsing prose. The cited bogus id is
    surfaced as ``bogus_cited_id`` so ``governor why <bogus_id>`` can
    show its absence via the existing S5 unknown-receipt-id path.
    """
    s_bytes = (
        f"{citation_role}|{bogus_cited_id}|{validation.check}|{parent_receipt_id}"
    ).encode("utf-8")
    evidence_bundle: dict[str, Any] = {
        "refusal_kind": "dangling_receipt_reference",
        "detail": validation.detail or "",
        "citation_check": validation.check,
        "citation_role": citation_role,
        "bogus_cited_id": bogus_cited_id,
        "parent_receipt_ids": [parent_receipt_id],
        # NQ-side discriminator stamped here too so the chain's origin
        # mode survives the validator-emitted leaf receipt. The wrapper
        # ``_OriginModeReceiptSink`` is not used for the validator emit
        # because the validator is not a per-client emission path — we
        # stamp the discriminator inline.
        EVIDENCE_KEY_ORIGIN_MODE: origin_mode,
    }
    receipt = system.emit(
        gate=PROPOSAL_VALIDATOR_SEAM_GATE,
        verdict="block",
        subject_kind="proposal_citation",
        subject_bytes=s_bytes,
        evidence_bundle=evidence_bundle,
        gate_config={
            "seam": "D3_proposal_validator",
            "refusal_vocabulary": "S4_lite_v1",
            # Hint for the JSON consumer that the bogus_cited_id field
            # is part of the schema, not free-text.
            "bogus_id_is_load_bearing": True,
        },
    )
    return receipt.receipt_id


@dataclass(frozen=True)
class DrillRunResult:
    """The full result of a drill run.

    ``receipt_ids`` is the ordered list of GateReceipt ids minted on the
    chain. For refusal scenarios the list is shorter (only the gates
    that fired before refusal emit). The leaf (used for ``governor
    why``) is ``receipt_ids[-1]``.

    D0d-1 additions:

      * ``outcome`` — one of ``"consumed"`` (chain reached effect),
        ``"refused"`` (a gate refused), ``"gap_accounted"`` (chain
        proceeded under acknowledged gap; receipted per scenario 4).
        Stable closed-set classification for the transcript renderer.
      * ``refusal_kind`` — the closed-vocabulary refusal kind when
        ``outcome="refused"``; ``None`` otherwise. Drawn from the
        S4-lite ``CLOSED_REFUSAL_KINDS`` set (or, for gap_accounted,
        the gap-shaped kind ``admission_gap_accounted``).
      * ``refusing_seam`` — the seam name (``standing_seam`` /
        ``wicket_seam`` / ``la_seam``) that refused, or ``None``.
      * ``effect_count`` — the number of distinct downstream effects
        observed on the run. Always 1 on ``all-green`` /
        ``wicket-gap-accounted``; always 0 on terminal refusals; 1
        on the replay scenario (first consume succeeds; second is
        refused with ``already_consumed`` and the counter does NOT
        advance).
      * ``downstream_call_counts`` — dict[seam_name, int]; how many
        times each downstream callable was invoked during the run.
        Refusal scenarios assert this is 0 past the refusing gate.

    ``proposal_packet`` is non-empty when the chain reaches consumed
    OR gap_accounted; empty dict on refusal scenarios (the runner
    correctly does NOT emit a proposal packet past a refusal — the
    refusal is the receipt for that gate).
    """

    scenario: str
    finding: dict[str, Any]
    chain_result: ChainResult
    receipt_ids: list[str] = field(default_factory=list)
    proposal_packet: dict[str, Any] = field(default_factory=dict)
    outcome: str = "consumed"
    refusal_kind: Optional[str] = None
    refusing_seam: Optional[str] = None
    effect_count: int = 0
    downstream_call_counts: dict[str, int] = field(default_factory=dict)
    # D3 — confabulated-receipt closing beat. None when no confabulation
    # was requested. The role is the cited slot (``standing`` /
    # ``evidence``); the bogus id is the deterministic placeholder the
    # runner injected; the check is the failure mode tag (existence /
    # kind_fit) from the validator. All four are None on non-D3 runs.
    confabulation_role: Optional[str] = None
    bogus_cited_id: Optional[str] = None
    citation_check: Optional[str] = None


# ---------------------------------------------------------------------------
# Per-scenario factories.
#
# Each factory builds the (verifier, downstream callables, instrumented
# counters) tuple appropriate for that scenario. The genuine NQ
# FindingSnapshot is the SAME across all six factories per the operator
# guardrail: gate state varies, not the workload. ``_EffectCounter`` is
# the test-double that proves the replay-kill invariant
# (``effect_count`` stays at 1 across two consume invocations).
# ---------------------------------------------------------------------------


class _EffectCounter:
    """Counts the number of distinct downstream effects observed.

    The replay scenario invokes LA.consume twice with the same
    ``consumption_event_id``. The first call returns ``Consumed``; the
    second returns ``AlreadyConsumed``. The downstream effect counter
    must remain at 1 — that is the demo's "eligibility is contractible;
    spendability is linear" beat (same valid warrant cited twice, second
    spend refused, real-world effect happens exactly once).

    Wired by the replay scenario's consume callable: it increments on
    ``Consumed`` only. ``AlreadyConsumed`` returns do not advance the
    counter, mirroring the linear-accountant contract (the spend ledger
    is the source of truth; AG observes the verdict).
    """

    def __init__(self) -> None:
        self._count = 0

    def increment(self) -> None:
        self._count += 1

    @property
    def value(self) -> int:
        return self._count


# Standing digest the no-standing / standing-expired scenarios use as a
# cited-but-unverifiable id. Stable so the standing-side refusal receipt
# is content-addressed.
_NO_STANDING_DIGEST = ""  # empty triggers standing_required
_EXPIRED_STANDING_DIGEST = "e" * 64  # 64-hex; verifier returns None


def _make_call_counter() -> tuple[dict[str, int], Callable[[str], None]]:
    """Return (counts_dict, bump_fn).

    The bump function records that the named downstream was invoked.
    Tests read ``counts_dict`` afterward to assert call counts.
    """
    counts: dict[str, int] = {
        "standing_verify": 0,
        "wicket_check": 0,
        "la_request_capacity": 0,
        "la_consume": 0,
    }

    def bump(seam: str) -> None:
        counts[seam] = counts.get(seam, 0) + 1

    return counts, bump


def _build_clients_for_scenario(
    scenario: str,
    *,
    wrapped_sink: Any,
    counts: dict[str, int],
    bump: Callable[[str], None],
    effect_counter: _EffectCounter,
) -> tuple[StandingClient, WicketClient, LinearAccountantClient]:
    """Build the (standing, wicket, LA) clients with scenario-appropriate
    injected callables.

    The closed dispatch — each branch returns a fully-configured client
    triple. Adding a new scenario requires a new branch here AND a new
    entry in ``SUPPORTED_SCENARIOS``; missing either side raises at
    construction time.

    The instrumentation (``counts`` / ``bump``) is wired into every
    downstream callable so refusal scenarios can assert
    ``counts[seam] == 0`` past the refusing gate. The effect counter is
    wired into LA.consume only — it is the spendability ledger.
    """
    ref = StandingReceiptRef(
        digest=ALL_GREEN_STANDING_DIGEST,
        kind="grant_activated",
    )

    # Scenario-specific standing verifier. The two standing-refusal
    # scenarios produce different refusal kinds:
    #
    #   * no-standing       → cooked context carries an empty
    #                         standing_receipt_id → standing client
    #                         raises StandingRequiredError pre-call.
    #                         Verifier is never consulted (gate is
    #                         upstream of the callable).
    #   * standing-expired  → cooked context carries a hex digest that
    #                         the verifier explicitly REJECTS (returns
    #                         None) → standing client raises
    #                         DanglingStandingReceiptError. AG's
    #                         standing seam owns ``standing_required``
    #                         and ``dangling_receipt_reference`` per
    #                         S4-lite; ``standing_expired`` is the
    #                         closed-vocab kind we surface via the
    #                         scenario's refusal classification, not
    #                         a new seam emit.
    #
    # The standing client emits ``dangling_receipt_reference`` at the
    # gate; the scenario-level outcome is reported as
    # ``standing_expired``. This separation is deliberate: the seam's
    # closed vocabulary is preserved (no widening of
    # ``_STANDING_SEAM_REFUSAL_KINDS``), and the scenario layer carries
    # the operator-facing refusal kind for the gauntlet table.
    def _standing_verify(sid: str) -> StandingReceiptRef | None:
        bump("standing_verify")
        if sid == ALL_GREEN_STANDING_DIGEST:
            return ref
        return None

    # Wicket downstream — admit-any in scenarios that reach it; never
    # reached in the standing-refusal scenarios.
    def _wicket_check(cooked_context: CookedContext) -> dict:
        bump("wicket_check")
        return _wicket_admit_any(cooked_context)

    # LA request callable — variants:
    #   * default (all-green / replay / gap-accounted): Granted.
    #   * wicket-denied: never reached (admission verifier rejects).
    def _la_request(la_request: dict, now: int) -> dict:
        bump("la_request_capacity")
        return _granted_response(la_request, now)

    # LA consume callable — variants:
    #   * default: Consumed; bumps effect counter.
    #   * replay-budget: first call Consumed (effect++); second call
    #     with the same consumption_event_id AlreadyConsumed (no
    #     effect bump).
    seen_event_ids: set[str] = set()

    def _la_consume(la_request: dict, now: int) -> dict:
        bump("la_consume")
        event_id = la_request.get("consumption_event_id")
        if scenario == SCENARIO_REPLAY_BUDGET and event_id in seen_event_ids:
            # Replay path: second invocation with the same event id.
            return {
                "decision": "AlreadyConsumed",
                "token_id": la_request["token_id"],
                "receipt": {"la_receipt_id": "la_already_consumed_replay"},
            }
        seen_event_ids.add(event_id)
        effect_counter.increment()
        return _consumed_response(la_request, now)

    # Admission verifier — variants:
    #   * default: True (admission receipts always resolve).
    #   * wicket-denied: False (the cited admission id is treated as
    #     dangling → LA-seam refuses with admission_denied per the
    #     scenario classifier below).
    if scenario == SCENARIO_WICKET_DENIED:
        def _admission_verifier(rid: str) -> bool:
            return False
    else:
        def _admission_verifier(rid: str) -> bool:
            return True

    standing_client = StandingClient(
        verify_fn=_standing_verify,
        receipt_sink=wrapped_sink,
    )
    wicket_client = WicketClient(
        standing_client=standing_client,
        wicket_check_fn=_wicket_check,
        receipt_sink=wrapped_sink,
    )
    la_client = LinearAccountantClient(
        request_capacity_callable=_la_request,
        consume_callable=_la_consume,
        admission_verifier=_admission_verifier,
        receipt_sink=wrapped_sink,
    )
    return standing_client, wicket_client, la_client


def _cooked_context_for_scenario(
    scenario: str, finding: dict[str, Any]
) -> CookedContext:
    """Build the cooked context appropriate for the scenario.

    The standing_receipt_id field varies by scenario because that is
    the field the standing seam reads first. All other cooked-context
    fields are scenario-invariant (the workload is the same; only the
    gate state varies).
    """
    base = _cooked_context_for_finding(finding)
    if scenario == SCENARIO_NO_STANDING:
        # Empty triggers standing_required at the standing seam.
        return _replace_standing_receipt_id(base, _NO_STANDING_DIGEST)
    if scenario == SCENARIO_STANDING_EXPIRED:
        # Hex digest the verifier rejects → dangling at the seam;
        # surfaced as standing_expired at the scenario layer.
        return _replace_standing_receipt_id(base, _EXPIRED_STANDING_DIGEST)
    # all-green / wicket-denied / wicket-gap-accounted / replay-budget
    # all use the verifying digest.
    return base


def _replace_standing_receipt_id(
    base: CookedContext, standing_receipt_id: str
) -> CookedContext:
    """Return a fresh CookedContext with a different standing_receipt_id.

    CookedContext is frozen; we cannot mutate ``base``. Private helper —
    callers should not construct CookedContext themselves.
    """
    return CookedContext(
        actor=base.actor,
        actor_standing=base.actor_standing,
        intended_action=base.intended_action,
        operation_class=base.operation_class,
        target=base.target,
        claimed_basis=base.claimed_basis,
        precedence=base.precedence,
        revocation=base.revocation,
        expected_effect=base.expected_effect,
        call_timestamp=base.call_timestamp,
        standing_receipt_id=standing_receipt_id,
        scope_assertion=base.scope_assertion,
        prev_receipt_hash=base.prev_receipt_hash,
    )


def _classify_chain_outcome(
    scenario: str,
    chain_result: ChainResult,
) -> tuple[str, Optional[str], Optional[str]]:
    """Map (scenario, chain_result) to (outcome, refusal_kind, seam).

    Returns the operator-facing classification per the §3 D2 gauntlet
    table. The classification is closed-vocabulary — no new kinds
    invented here; everything is drawn from existing AG modules.

    Mapping rules:
      * no-standing       → ("refused", "standing_required", "standing_seam")
      * standing-expired  → ("refused", "standing_expired", "standing_seam")
      * wicket-denied     → ("refused", "admission_denied", "la_seam")
      * wicket-gap-accounted → ("gap_accounted", "admission_gap_accounted",
                                 "wicket_seam")  (gap is NOT a refusal;
                                 the chain proceeds and the proposal
                                 packet carries the gap citation)
      * replay-budget     → second consume refuses; classified as
                            ("refused", "already_consumed", "la_seam")
      * all-green         → ("consumed", None, None)
    """
    if scenario == SCENARIO_NO_STANDING:
        return "refused", "standing_required", "standing_seam"
    if scenario == SCENARIO_STANDING_EXPIRED:
        # The standing seam emits dangling_receipt_reference at the
        # gate (per its closed vocabulary); the scenario layer surfaces
        # the operator-facing kind ``standing_expired`` from S4-lite.
        return "refused", "standing_expired", "standing_seam"
    if scenario == SCENARIO_WICKET_DENIED:
        # The LA seam emits dangling_receipt_reference (admission id
        # is unverifiable); the scenario layer surfaces
        # ``admission_denied`` from S4-lite.
        return "refused", "admission_denied", "la_seam"
    if scenario == SCENARIO_WICKET_GAP_ACCOUNTED:
        return "gap_accounted", "admission_gap_accounted", "wicket_seam"
    if scenario == SCENARIO_REPLAY_BUDGET:
        # Set by the runner after the second consume call.
        if chain_result.consumed:
            # If we get here without the second consume having fired,
            # the runner forgot to invoke the replay step.
            return "consumed", None, None
        return "refused", "already_consumed", "la_seam"
    # all-green
    return "consumed", None, None


def run_drill(
    *,
    gov_dir: Path,
    scenario: str = SCENARIO_ALL_GREEN,
    now: int = 0,
    finding: dict[str, Any] | None = None,
    confabulate_citation: Optional[str] = None,
) -> DrillRunResult:
    """Run the drill against a real ``GateReceiptSystem``.

    Drives the cooked-context orchestrator with the NQ-shaped finding,
    collects every emitted receipt's id, builds the proposal packet
    citing those ids (or skips it for refusal scenarios), and returns
    the structured result.

    Two finding-source paths (preserved verbatim from D0d-a):

      * ``finding=None`` (default): build the deterministic fixture via
        ``build_drill_finding_snapshot``. Preserved for tests that
        exercise the runner outside the cross-repo harness.
      * ``finding=<dict>``: consume the supplied FindingSnapshot
        verbatim. This is the D0-Origin path — Night Shift's stager +
        NQ's production evaluator produced the dict; AG runs the chain
        against the real wire DTO.

    Scenario dispatch (D0d-1 expansion):

      * ``all-green``           — full chain + deterministic proposal
        packet (existing path).
      * ``no-standing``         — standing seam refuses; downstream
        callables called 0 times; no proposal packet.
      * ``standing-expired``    — same shape; surfaced as
        ``standing_expired`` per §3 D2 table.
      * ``wicket-denied``       — LA-seam admission verifier rejects;
        LA.request_capacity / LA.consume called 0 times. Standing /
        wicket emit positive receipts before the refusal lands.
      * ``wicket-gap-accounted``— chain proceeds; proposal packet
        carries ``gap_receipt_id`` + ``produced_under_gap=true``.
      * ``replay-budget``       — chain reaches Consumed; runner then
        invokes LA.consume a second time with the same event id;
        second call returns AlreadyConsumed; effect counter stays at 1.

    No LLM. No narration. Every output bit is mechanically derived.
    """
    canonical = _canonical_scenario(scenario)
    if canonical not in SUPPORTED_SCENARIOS:
        raise UnsupportedScenarioError(
            f"scenario {scenario!r} not in the closed scenario set; "
            f"supported scenarios: {sorted(SUPPORTED_SCENARIOS)}; "
            f"accepted aliases: {sorted(SCENARIO_ALIASES)}"
        )
    scenario = canonical

    # D3 — confabulation flag validation. Closed role set + scenario
    # compatibility check. Refuse at construction time, never silently
    # substitute. Mirrors the ``UnsupportedScenarioError`` pattern.
    if confabulate_citation is not None:
        if confabulate_citation not in CONFABULATION_ROLES:
            raise InvalidConfabulationRoleError(
                f"confabulate_citation role {confabulate_citation!r} not "
                f"in the closed set {sorted(CONFABULATION_ROLES)}"
            )
        if scenario != SCENARIO_ALL_GREEN:
            raise InvalidConfabulationRoleError(
                f"confabulate_citation={confabulate_citation!r} requires "
                f"scenario=all-green (only scenario that reaches the "
                f"proposal-packet step); got scenario={scenario!r}"
            )

    if finding is None:
        finding = build_drill_finding_snapshot(scenario)
    # The NQ-side origin_mode crosses the bridge here.
    origin_mode = finding["origin_mode"]

    cooked_context = _cooked_context_for_scenario(scenario, finding)
    capacity_template = _capacity_template_for_finding(finding)
    consume_template = _consume_template_for_finding(finding)

    # Real GateReceiptSystem — receipts land on disk under gov_dir.
    system = GateReceiptSystem(gov_dir)
    wrapped_sink = wrap_receipt_sink_with_origin_mode(system, origin_mode)

    counts, bump = _make_call_counter()
    effect_counter = _EffectCounter()
    standing_client, wicket_client, la_client = _build_clients_for_scenario(
        scenario,
        wrapped_sink=wrapped_sink,
        counts=counts,
        bump=bump,
        effect_counter=effect_counter,
    )
    orchestrator = CookedContextOrchestrator(
        wicket_client=wicket_client,
        la_client=la_client,
        origin_mode=origin_mode,
    )

    chain_result = orchestrator.run(
        cooked_context=cooked_context,
        capacity_request_template=capacity_template,
        consume_request_template=consume_template,
        now=now,
        # D0d-b: thread the NQ finding id so the standing receipt cites
        # it as parent — making the chain walk reach the NQ origin.
        finding_id=finding["finding_id"],
    )

    # D0d-1: replay scenario fires a second consume after the chain's
    # successful first call. The downstream effect counter must remain
    # at 1 (linearity invariant). The second call is invoked directly
    # against the LA client (the orchestrator's ``run()`` only consumes
    # once; replaying through it would not exercise the
    # ``AlreadyConsumed`` path because the orchestrator does not
    # support multi-consume).
    if scenario == SCENARIO_REPLAY_BUDGET and chain_result.consumed:
        consumed_outcome = chain_result.outcome
        assert isinstance(consumed_outcome, ConsumedResult)
        # The second consume reuses the same consumption_event_id (via
        # the template) and the granted token_id (via the prior outcome
        # — replicating what an agent retry would naturally do).
        # CookedConsumeRequest is frozen; rebuild with the new token id.
        replay_request = CookedConsumeRequest(
            consumption_event_id=consume_template.consumption_event_id,
            token_id=consumed_outcome.token_id,
            actor=consume_template.actor,
            action=consume_template.action,
            target=consume_template.target,
            amount=consume_template.amount,
            scope=consume_template.scope,
        )
        # Grant receipt id from the prior consume: we look it up by
        # walking the receipts produced so far to find the latest
        # la_seam grant receipt. Simpler shape: pass the previously
        # used parent linkage so the replayed refusal cites the same
        # grant for accounting clarity.
        chain_result = ChainResult(
            outcome=la_client.consume(
                replay_request,
                now,
                parent_grant_receipt_id=consumed_outcome.receipt_id,
            ),
            seam="la_seam_consume",
        )

    # D3 — confabulated-receipt closing beat.
    #
    # Per §3b: the confabulation happens at the proposal-packet step
    # AFTER standing → wicket → LA grant → LA consume have all
    # succeeded. ``_EffectCounter`` is at 1 (real budget spent). The
    # validator refuses; the validator emits a single
    # ``dangling_receipt_reference`` refusal receipt; the mutation
    # (proposal packet emission) does NOT happen — the proposal is
    # refused before execution. ``effect_count`` stays at 1; failure
    # cost real budget. Re-attempt requires a NEW chain spend.
    confabulation_role: Optional[str] = None
    bogus_cited_id: Optional[str] = None
    citation_check: Optional[str] = None
    if (
        confabulate_citation is not None
        and scenario == SCENARIO_ALL_GREEN
        and isinstance(chain_result.outcome, ConsumedResult)
    ):
        consumed_outcome = chain_result.outcome
        # Pick the bogus id per role.
        #   * ``standing`` → fixed BOGUS_STANDING_RECEIPT_ID (existence-fail
        #     target — content-addressed, never minted by any seam).
        #   * ``evidence`` → the real LA-seam grant receipt id. That
        #     receipt EXISTS in the store (so the existence check
        #     passes), but its structural kind is wrong for the
        #     standing slot: ``gate=la_seam`` and the standing-side
        #     ``verified_standing`` marker is absent. Perfect
        #     kind-fit-fail target. ``ConsumedResult.parent_receipt_id``
        #     is the grant receipt id threaded forward by the
        #     orchestrator (D0d-b wiring); we read it here without
        #     having to walk the receipt store again.
        if confabulate_citation == CONFABULATION_ROLE_STANDING:
            bogus_cited_id = BOGUS_STANDING_RECEIPT_ID
        else:
            # CONFABULATION_ROLE_EVIDENCE — cite the LA grant receipt id
            # (a real receipt id, but the wrong structural kind for the
            # slot).
            grant_id = consumed_outcome.parent_receipt_id
            if grant_id is None:
                raise AssertionError(
                    "D3 evidence-role confabulation requires the grant "
                    "receipt id (threaded via ConsumedResult.parent_receipt_id "
                    "from D0d-b wiring); got None despite receipt_sink "
                    "being wired. This is a wiring regression."
                )
            bogus_cited_id = grant_id

        validation = _validate_standing_citation(
            cited_id=bogus_cited_id,
            system=system,
        )
        # Operator-load-bearing: confabulation always produces a
        # validation failure here (by construction — bogus id by
        # definition). If a future change accidentally cites a real
        # standing receipt id under role=``standing``, the validator
        # passes and we DO emit the proposal packet — the test suite
        # will catch that regression as a missing refusal receipt.
        if not validation.ok:
            # The validator's parent is the most recent non-refusal
            # receipt — the consume receipt. We look it up by walking
            # the chain receipts so far (the only la_seam consumed
            # receipt) so the parent linkage is auditable end-to-end.
            consume_receipt_id: Optional[str] = consumed_outcome.receipt_id
            if consume_receipt_id is None:
                # Defensive: ConsumedResult.receipt_id is set whenever a
                # receipt_sink is wired (which it always is in run_drill).
                # If we hit this path, the orchestrator wiring is broken;
                # falling back to the la_seam consume receipt collected
                # below would launder the bug. Raise loudly instead.
                raise AssertionError(
                    "D3 validator could not determine consume receipt id; "
                    "ConsumedResult.receipt_id is None despite receipt_sink "
                    "being wired. This is a wiring regression."
                )
            _emit_proposal_validator_refusal(
                system=system,
                bogus_cited_id=bogus_cited_id,
                citation_role=confabulate_citation,
                validation=validation,
                parent_receipt_id=consume_receipt_id,
                origin_mode=origin_mode,
                finding_id=finding["finding_id"],
            )
            confabulation_role = confabulate_citation
            citation_check = validation.check

    # Collect chain receipt ids in emit order. The ReceiptStore is
    # JSONL-append; reading via ``all()`` gives oldest-first (insertion
    # / emit order). We filter by the gates this chain emits under, in
    # case the gov_dir already had unrelated receipts from a prior run
    # sharing the directory (defense-in-depth — the typical case is a
    # fresh tmp dir). D3 adds the proposal-validator seam — its
    # refusal-time receipt is the chain leaf when confabulation fired.
    all_receipts = system.receipt_store.all()  # oldest first (emit order)
    chain_gates = {
        "standing_seam",
        "wicket_seam",
        "la_seam",
        PROPOSAL_VALIDATOR_SEAM_GATE,
    }
    chain_receipts = [r for r in all_receipts if r.gate in chain_gates]
    receipt_ids = [r.receipt_id for r in chain_receipts]

    outcome_kind, refusal_kind, refusing_seam = _classify_chain_outcome(
        scenario, chain_result
    )
    # D3: confabulation override on the operator-facing classification.
    # The chain completed Consumed cleanly (chain_result.consumed=True);
    # what refused is the proposal-validator seam. Surface the refusal
    # at the scenario-classification layer so the transcript / JSON
    # envelope / DrillRunResult fields reflect what the operator
    # actually saw.
    if confabulation_role is not None:
        outcome_kind = "refused"
        refusal_kind = "dangling_receipt_reference"
        refusing_seam = PROPOSAL_VALIDATOR_SEAM_GATE

    # Proposal packet shape:
    #   * consumed (all-green)              → standard deterministic stub.
    #   * gap_accounted (wicket-gap)        → stub + gap_receipt_id +
    #                                         produced_under_gap=true.
    #   * refused (terminal refusal cases)  → empty dict — the refusal
    #                                         IS the receipt for that
    #                                         gate; no proposal packet.
    #   * D3 confabulation refused          → empty dict (mutation does
    #                                         NOT happen; the refusal
    #                                         receipt IS the closing beat).
    proposal_packet: dict[str, Any] = {}
    if outcome_kind == "consumed" and isinstance(
        chain_result.outcome, ConsumedResult
    ):
        proposal_packet = build_proposal_packet(
            finding=finding,
            consumed=chain_result.outcome,
            receipt_ids=receipt_ids,
        )
    elif outcome_kind == "gap_accounted" and isinstance(
        chain_result.outcome, ConsumedResult
    ):
        proposal_packet = build_proposal_packet(
            finding=finding,
            consumed=chain_result.outcome,
            receipt_ids=receipt_ids,
        )
        # Gap citation per §3b: the deterministic stub gains a
        # gap_receipt_id field; the LLM is NOT invoked. The gap_receipt
        # is the wicket-seam admission receipt (which the runner
        # produces with admission_verdict="gap_accounted" in this
        # scenario — see wicket scenario factory). For D0d-1 the
        # operator-load-bearing field shape is gap_receipt_id +
        # produced_under_gap=true; the citation surface itself stays
        # deterministic.
        proposal_packet["produced_under_gap"] = True
        # The gap_receipt_id is the wicket-seam admission receipt id,
        # which is receipt_ids[1] (index 1 = wicket admit per the
        # canonical chain order: standing, wicket, la_request,
        # la_consume).
        if len(receipt_ids) >= 2:
            proposal_packet["gap_receipt_id"] = receipt_ids[1]

    return DrillRunResult(
        scenario=scenario,
        finding=finding,
        chain_result=chain_result,
        receipt_ids=receipt_ids,
        proposal_packet=proposal_packet,
        outcome=outcome_kind,
        refusal_kind=refusal_kind,
        refusing_seam=refusing_seam,
        effect_count=effect_counter.value,
        downstream_call_counts=dict(counts),
        confabulation_role=confabulation_role,
        bogus_cited_id=bogus_cited_id,
        citation_check=citation_check,
    )


# ---------------------------------------------------------------------------
# Deterministic transcript renderer.
#
# Receipt ids are content-addressed and therefore byte-stable across runs
# with identical inputs. Timestamps are metadata, not identity — they are
# DELIBERATELY NOT rendered so two runs with identical inputs produce
# byte-identical transcripts.
#
# The transcript is a receipt render of the ledger. NO model invoked.
# ---------------------------------------------------------------------------


_CHAIN_LINK_DEFS = (
    # (seam_label, transcript_label)
    ("standing_seam", "standing_seam"),
    ("wicket_seam", "wicket_seam (admit)"),
    ("la_seam", "la_seam (granted)"),
    ("la_seam", "la_seam (consumed)"),
)


def render_transcript(result: DrillRunResult) -> str:
    """Render the drill result as a deterministic transcript.

    Shape mirrors the operator-specified format. Every line is derived
    mechanically from ``result`` — no model, no clock, no env lookup.

    D0d-1: refusal scenarios render fewer chain links. The transcript
    explicitly tags gates that weren't invoked with
    ``(not invoked — refused at <seam>)`` (per the slice spec — honest
    absence; ``(no-receipt-emitted)`` would be ambiguous because the
    same string was used in D0d-a when a happy-path emission existed
    but was silently dropped). For the gap-accounted scenario the
    chain renders all four links and the proposal packet section adds
    a ``gap_receipt_id`` line. For the replay scenario the chain
    renders five lines: the four happy-path links plus a refused
    second-consume tagged with the ``already_consumed`` kind.
    """
    lines: list[str] = []
    lines.append(
        f"nightshift watchbill: wal-bloat-review --drill --scenario={result.scenario}"
    )
    lines.append(f"origin_mode: {result.finding['origin_mode']}")
    lines.append(f"finding_id: {result.finding['finding_id']}")
    lines.append(f"outcome: {result.outcome}")
    if result.refusal_kind:
        lines.append(f"refusal_kind: {result.refusal_kind}")
    if result.refusing_seam:
        lines.append(f"refusing_seam: {result.refusing_seam}")
    lines.append(f"effect_count: {result.effect_count}")
    lines.append("chain:")

    origin_mode = result.finding["origin_mode"]
    finding_id = result.finding["finding_id"]

    # Receipt-id assignment per chain link is keyed off the actual
    # gate names recorded on each emitted receipt, NOT positional
    # indexing. For refusal scenarios, the receipts emitted are
    # whichever the refusing chain actually minted (standing_seam +
    # wicket_seam for standing-refusal cases; standing + wicket +
    # la_seam for LA-refusal cases). The transcript labels each
    # canonical link slot and either shows the matching receipt id or
    # an honest-absence marker indicating which seam refused.
    rids = result.receipt_ids

    # Per-seam receipt assignment. For the canonical happy-path the
    # order is [standing, wicket_admit, la_grant, la_consume]; for
    # refusal scenarios, some slots are filled by refusal receipts and
    # others are skipped. We assign positionally for the happy path
    # and per-scenario for refusal cases below.
    standing_id = rids[0] if len(rids) >= 1 else ""
    wicket_id = rids[1] if len(rids) >= 2 else ""
    la_req_id = rids[2] if len(rids) >= 3 else ""
    la_consume_id = rids[3] if len(rids) >= 4 else ""

    def _id_or_skipped(rid: str, refused_at: Optional[str]) -> str:
        if rid:
            return rid[:16]
        if refused_at:
            return f"(not invoked — refused at {refused_at})"
        return "(no-receipt-emitted)"

    def _parent_prefix(parent: str) -> str:
        return parent[:16] if parent else "(no-receipt-emitted)"

    # Honest-absence marker per refusal scenario. The slice spec
    # rejects ``(no-receipt-emitted)`` for skipped gates because that
    # placeholder was D0d-a's marker for happy-path emissions that
    # were silently dropped — semantically different. We use
    # ``(not invoked — refused at <seam>)`` for every gate the
    # refusing seam short-circuited.
    refusing_seam = result.refusing_seam

    # Per the §3 D2 mapping:
    #   standing_seam refusal  → wicket admit emits (it carries the
    #     refusal); LA seams never invoked.
    #   wicket_seam → only fires on the gap_accounted scenario where
    #     the chain proceeds — never a refusal in the gauntlet.
    #   la_seam refusal at request → LA-request emits (refusal);
    #     LA-consume never invoked.
    #
    # The skip is per-slot: only show "(not invoked — refused at X)"
    # for slots that have no receipt AND whose absence is caused by
    # an upstream refusal. Other empty slots show "(no-receipt-emitted)"
    # (defensive — should not occur in any scenario under D0d-1).
    la_req_skip = (
        refusing_seam
        if refusing_seam == "standing_seam" and not la_req_id
        else None
    )
    la_consume_skip = (
        refusing_seam
        if refusing_seam in {"standing_seam", "la_seam"} and not la_consume_id
        else None
    )

    # Standing seam line — always present (it's the first emitter).
    lines.append(
        f"  standing_seam        {_id_or_skipped(standing_id, None)}  "
        f"origin_mode={origin_mode}  "
        f"parent={_parent_prefix(finding_id)}"
    )
    # Wicket admit line. Always emits a receipt (refusal or admit).
    lines.append(
        f"  wicket_seam (admit)  {_id_or_skipped(wicket_id, None)}  "
        f"origin_mode={origin_mode}  "
        f"parent={_id_or_skipped(standing_id, None)}"
    )
    # LA-request line. Emits a receipt on wicket-denied (refusal),
    # all-green/gap/replay (granted); skipped on standing refusals.
    lines.append(
        f"  la_seam (granted)    {_id_or_skipped(la_req_id, la_req_skip)}  "
        f"origin_mode={origin_mode}  "
        f"parent={_id_or_skipped(wicket_id, None)}"
    )
    # LA-consume line. Emits a receipt on all-green/gap/replay (first
    # consume); skipped on every other refusal.
    lines.append(
        f"  la_seam (consumed)   {_id_or_skipped(la_consume_id, la_consume_skip)}  "
        f"origin_mode={origin_mode}  "
        f"parent={_id_or_skipped(la_req_id, la_req_skip)}"
    )
    # Replay scenario: a fifth line showing the refused second-consume.
    # The receipt id (if any) is the 5th element in receipt_ids.
    if result.scenario == SCENARIO_REPLAY_BUDGET and len(rids) >= 5:
        replay_id = rids[4]
        lines.append(
            f"  la_seam (replay)     {_id_or_skipped(replay_id, None)}  "
            f"origin_mode={origin_mode}  "
            f"parent={_id_or_skipped(la_consume_id, None)}  "
            f"refused=already_consumed"
        )

    # D3 confabulation: a fifth chain line showing the proposal-validator
    # refusal. The receipt id is the 5th element in receipt_ids (the
    # validator emit fires after all four chain receipts on the all-green
    # path). The bogus citation is surfaced in-line so the reader sees
    # which id was confabulated.
    if (
        result.confabulation_role is not None
        and len(rids) >= 5
        and result.bogus_cited_id is not None
    ):
        validator_id = rids[4]
        bogus = result.bogus_cited_id
        bogus_short = bogus[:16] if len(bogus) > 24 else bogus
        lines.append(
            f"  proposal_validator   {_id_or_skipped(validator_id, None)}  "
            f"origin_mode={origin_mode}  "
            f"parent={_id_or_skipped(la_consume_id, None)}  "
            f"refused=dangling_receipt_reference  "
            f"check={result.citation_check}  "
            f"cited_role={result.confabulation_role}  "
            f"bogus_cited_id={bogus_short}"
        )

    # Proposal packet section.
    if result.proposal_packet:
        lines.append("proposal_packet:")
        lines.append(f"  status: {result.proposal_packet['status']}")
        lines.append(f"  text: \"{result.proposal_packet['text']}\"")
        citations = result.proposal_packet["citations"]
        rendered_citations = [
            (c[:16] if len(c) > 24 else c) for c in citations
        ]
        lines.append(f"  citations: [{', '.join(rendered_citations)}]")
        # Gap citation surface (D0d-1 / §3b): deterministic stub gains
        # gap_receipt_id + produced_under_gap; no LLM invocation.
        if result.proposal_packet.get("produced_under_gap"):
            lines.append("  produced_under_gap: true")
            gap_id = result.proposal_packet.get("gap_receipt_id", "")
            lines.append(f"  gap_receipt_id: {gap_id[:16] if gap_id else ''}")
    else:
        lines.append("proposal_packet: (not emitted — refused at gate)")

    # Embed `governor why` output. We use the in-process library rather
    # than shelling to the CLI because the shell-out is what Night Shift
    # does; the AG-side test wants to assert against deterministic
    # output without re-spawning the CLI. The render is identical
    # either way (CLI is a thin wrapper around render_text).
    leaf_id = result.receipt_ids[-1] if result.receipt_ids else ""
    lines.append(f"why {leaf_id[:16]}:")
    if leaf_id:
        lines.append(
            "  (walk omitted — call run_drill_and_render(gov_dir) for the embedded walk)"
        )
    else:
        lines.append("  (no leaf receipt to walk)")

    return "\n".join(lines) + "\n"


def render_walk(gov_dir: Path, receipt_id: str) -> str:
    """Render ``governor why <receipt-id>`` output by calling the
    library function. Deterministic — same input, same output."""
    system = GateReceiptSystem(gov_dir)
    result = walk_chain(system, receipt_id)
    return render_text(result)


def run_drill_and_render(
    *,
    gov_dir: Path,
    scenario: str = SCENARIO_ALL_GREEN,
    now: int = 0,
    finding: dict[str, Any] | None = None,
    confabulate_citation: Optional[str] = None,
) -> tuple[DrillRunResult, str]:
    """Run the drill and return (result, transcript).

    The transcript embeds the ``governor why`` walk output for the leaf
    receipt. Receipt ids are content-addressed; timestamps and other
    non-deterministic axes are normalized at render time via
    ``_normalize_transcript`` so the byte-identical determinism
    invariant survives across input axes Night Shift cannot pin
    (NQ-side timestamps, sandbox paths, etc.).

    When ``finding`` is supplied (D0-Origin path), the transcript also
    normalizes against the genuine NQ-emitted axes — finding_key,
    subject path, observed_at — so two runs against the same staged
    condition still produce byte-identical normalized transcripts.
    """
    result = run_drill(
        gov_dir=gov_dir,
        scenario=scenario,
        now=now,
        finding=finding,
        confabulate_citation=confabulate_citation,
    )

    # Build the deterministic non-walk portion of the transcript by
    # delegating to ``render_transcript`` and replacing its walk
    # placeholder section.
    head = render_transcript(result)
    # The placeholder line is the last informational line; we strip the
    # trailing "(walk omitted ...)" marker and append the real walk.
    head_lines = head.splitlines()
    # Drop the placeholder ``(walk omitted ...)`` line if present.
    if head_lines and head_lines[-1].startswith("  (walk omitted"):
        head_lines = head_lines[:-1]

    walk_text = ""
    if result.receipt_ids:
        leaf_id = result.receipt_ids[-1]
        walk_text = render_walk(gov_dir, leaf_id)
        # Strip volatile timestamp fragments from the walk render so
        # byte-equality holds. ``ts=<ISO>`` is the renderer's format.
        walk_lines = []
        for line in walk_text.splitlines():
            if "  ts=" in line:
                # Truncate at the first ``  ts=``; everything after is
                # the timestamp metadata, not chain identity.
                line = line.split("  ts=")[0]
            walk_lines.append(line)
        walk_text = "\n".join(walk_lines) + "\n"

    # Indent the walk under the "why <id>:" header so it reads as part
    # of the transcript section.
    indented_walk = "\n".join(
        "  " + line if line else line for line in walk_text.splitlines()
    )
    full = "\n".join(head_lines) + "\n" + indented_walk + "\n"
    # D0-Origin determinism normalization: the genuine NQ FindingSnapshot
    # carries real timestamps, real sandbox paths, real finding_keys
    # that vary per run. The receipt ids are content-addressed (same
    # input → same id), but the input includes the finding_id and the
    # finding fields above, which include the sandbox path. We normalize
    # those axes here so two runs against the same staged condition
    # produce byte-identical normalized transcripts. The raw transcript
    # (un-normalized) is still preserved in the JSON envelope's
    # ``transcript_raw`` field for audit replay.
    full = _normalize_transcript(full, result)
    return result, full


# ---------------------------------------------------------------------------
# Transcript normalization for D0-Origin determinism.
#
# Real-NQ inputs introduce non-determinism the runner does not control:
#
#   * timestamps stamped by NQ's clock at evaluator-run time;
#   * sandbox paths chosen by tempfile, embedded in `finding_key` and
#     `identity.subject`;
#   * gov_dir tmp paths embedded by `governor why` rendering of
#     receipt paths.
#
# The D0d-a fixture path was byte-deterministic without normalization
# because every input was pinned. D0-Origin needs a richer normalizer.
# Determinism guarantee: two runs against the same staged condition →
# the normalized transcript is byte-identical.
# ---------------------------------------------------------------------------


_TS_PLACEHOLDER = "<ts>"
_SANDBOX_PATH_PLACEHOLDER = "<sandbox>"


def _normalize_transcript(text: str, result: DrillRunResult) -> str:
    """Normalize non-deterministic axes in the rendered transcript.

    The receipt ids themselves are content-addressed; they are stable
    given identical inputs and we leave them untouched (they are the
    chain identity). What we normalize:

      * Sandbox paths embedded in the finding_key / subject — replaced
        with ``<sandbox>``. The drill is sandbox-relative; the absolute
        path is a tempfile happenstance, not chain identity.
      * Real ISO timestamps in the finding's observed_at — replaced
        with ``<ts>``. The receipt walk render already strips
        ``ts=<ISO>`` fragments; this catches the head's
        ``finding_id``/``parent`` line where the path is embedded.

    The receipt ids themselves stay raw — they remain byte-identical
    across runs because their hash inputs are stable after this
    normalization is applied to the finding fields fed into the chain.

    Wait — that's not quite right. The receipt ids are NOT byte-stable
    across runs that use different sandbox paths, because the
    standing-receipt cites the finding_id (the sandbox-derived
    finding_key) as parent, which goes into the standing receipt's
    content hash. So in the D0-Origin path we MUST normalize the
    receipt-id prefixes too — they're stable per (staged condition,
    sandbox path) but not across sandbox paths.

    Strategy: build a map of all receipt id 16-char prefixes used in
    the transcript and replace each one with ``<rcpt:N>`` keyed by emit
    order. Determinism survives: emit order is a function of chain
    semantics, not wall clock or path identity. The receipt ids appear
    in finite count (4 chain links + the head's finding_id prefix), so
    the substitution is unambiguous.
    """
    out = text
    finding = result.finding
    # Substitution order matters: replace the longest, most specific
    # tokens first. Otherwise an earlier short substitution can chop
    # a longer string mid-pattern (e.g. sandbox path replacement
    # mutates finding_key before we can match it against the full
    # finding_id).
    #
    # Order:
    #   1. finding_id (full) — longest single identity token; contains
    #      the URL-encoded sandbox path, so MUST go before sandbox.
    #   2. finding_id 16-char prefix — head's `parent={prefix}` form.
    #   3. sandbox path (bare + URL-encoded) — paths inside other
    #      surfaces that survived above.
    #   4. observed_at (ISO ts) — leaf-level.
    #   5. receipt id 16-char prefixes — chain ids.
    finding_id = finding.get("finding_id") if isinstance(finding, dict) else None
    if isinstance(finding_id, str) and finding_id:
        out = out.replace(finding_id, "<finding_id>")
        out = out.replace(finding_id[:16], "<finding_id>")
    identity = finding.get("identity") if isinstance(finding, dict) else None
    if isinstance(identity, dict):
        subject = identity.get("subject")
        if isinstance(subject, str) and subject:
            out = out.replace(subject, _SANDBOX_PATH_PLACEHOLDER)
            from urllib.parse import quote

            encoded = quote(subject, safe="")
            out = out.replace(encoded, _SANDBOX_PATH_PLACEHOLDER)
    observed_at = finding.get("observed_at") if isinstance(finding, dict) else None
    if isinstance(observed_at, str) and observed_at and observed_at != ALL_GREEN_OBSERVED_AT:
        # Only replace non-fixture timestamps (the fixture path uses
        # the pinned constant which we leave for the existing fixture-
        # path test contract).
        out = out.replace(observed_at, _TS_PLACEHOLDER)
    for n, rid in enumerate(result.receipt_ids, start=1):
        # Match the longest prefix first so a shorter prefix
        # substitution cannot accidentally chop a longer match.
        # Surfaces:
        #   * head's render_transcript: 16-char prefix
        #   * why walk text: 12-char prefix + "..."
        #   * citation list: full id when len < 24, prefixed otherwise
        for prefix_len in (64, 16, 12):
            prefix = rid[:prefix_len]
            if prefix and prefix in out:
                out = out.replace(prefix, f"<rcpt:{n}>")
    return out


# ---------------------------------------------------------------------------
# JSON envelope for the subprocess boundary.
#
# Night Shift shells in via ``python3 -m governor.drill_runner`` and
# consumes the JSON stdout. The JSON shape is stable; both sides depend
# on the field names here.
# ---------------------------------------------------------------------------


def build_json_envelope(
    result: DrillRunResult,
    transcript: str,
) -> dict[str, Any]:
    """Build the JSON document the subprocess boundary emits.

    Shape:
        {
          "scenario": "...",
          "origin_mode": "drill",
          "finding": {...the NQ-shaped DTO verbatim...},
          "receipt_ids": ["...", "...", "...", "..."],
          "leaf_receipt_id": "...",
          "proposal_packet": {...},
          "transcript": "...deterministic text..."
        }

    Every field is mechanically derived from the run.
    """
    return {
        "scenario": result.scenario,
        "origin_mode": result.finding["origin_mode"],
        "finding": result.finding,
        "receipt_ids": list(result.receipt_ids),
        "leaf_receipt_id": (
            result.receipt_ids[-1] if result.receipt_ids else None
        ),
        "proposal_packet": result.proposal_packet,
        "transcript": transcript,
        # D0d-1 envelope additions — let Night Shift assert per-scenario
        # outcomes without re-deriving from the transcript.
        "outcome": result.outcome,
        "refusal_kind": result.refusal_kind,
        "refusing_seam": result.refusing_seam,
        "effect_count": result.effect_count,
        "downstream_call_counts": dict(result.downstream_call_counts),
        # D3 envelope additions — confabulation state surfaces under its
        # own keys so a JSON consumer never has to parse transcript prose
        # to learn whether a run exercised the proposal-validator seam.
        # All four are None on non-D3 runs.
        "confabulation_role": result.confabulation_role,
        "bogus_cited_id": result.bogus_cited_id,
        "citation_check": result.citation_check,
    }


# ---------------------------------------------------------------------------
# Module entry point: ``python3 -m governor.drill_runner``.
#
# This is NOT a competing CLI surface. It is the library-shell-in path
# Night Shift uses. The operator-visible entry point remains
# ``nightshift watchbill run wal-bloat-review --drill --scenario=all-green``;
# Night Shift owns it. This module simply exposes a JSON in/out boundary.
# ---------------------------------------------------------------------------


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m governor.drill_runner",
        description=(
            "D0-Origin drill runner library entry. Not an operator-facing "
            "CLI; invoked by `nightshift watchbill run --drill`. Consumes a "
            "genuine NQ FindingSnapshot via --finding-json when supplied; "
            "otherwise falls back to the D0d-a deterministic fixture."
        ),
    )
    parser.add_argument(
        "--scenario",
        default=SCENARIO_ALL_GREEN,
        # Accept canonical scenarios + the operator-ratified alias
        # ``already-consumed`` (resolves to ``replay-budget``).
        choices=sorted(SUPPORTED_SCENARIOS | set(SCENARIO_ALIASES)),
        help=(
            "Drill scenario. D0d-1 closed six-set: "
            + ", ".join(sorted(SUPPORTED_SCENARIOS))
            + ". Accepted alias: "
            + ", ".join(sorted(SCENARIO_ALIASES))
            + " → replay-budget."
        ),
    )
    parser.add_argument(
        "--root",
        required=True,
        type=Path,
        help=(
            "Receipt root directory. A fresh GateReceiptSystem is opened "
            "here; receipts land under {root}/receipts/ and evidence "
            "under {root}/evidence/."
        ),
    )
    parser.add_argument(
        "--now",
        type=int,
        default=0,
        help=(
            "Deterministic 'now' value forwarded to the LA stubs. "
            "Fixture material; does not affect receipt ids."
        ),
    )
    parser.add_argument(
        "--finding-json",
        type=Path,
        default=None,
        help=(
            "Path to a genuine NQ-produced FindingSnapshot JSON file "
            "(nq.finding_snapshot.v1 wire shape). Written by Night "
            "Shift's drill runner after invoking `nq-monitor drill "
            "wal-bloat`. When omitted, the runner builds the D0d-a "
            "deterministic fixture and uses it (fixture path preserved "
            "for tests that exercise the runner outside the cross-repo "
            "harness)."
        ),
    )
    parser.add_argument(
        "--confabulate-citation",
        choices=sorted(CONFABULATION_ROLES),
        default=None,
        help=(
            "D3 — confabulated-receipt closing beat. Inject a bogus "
            "citation into the proposal packet step AFTER the chain "
            "completes Consumed. role=standing injects "
            "BOGUS_STANDING_RECEIPT_ID (existence-fail); role=evidence "
            "cites the LA token id in the standing slot (kind-fit-fail). "
            "Both failure modes produce a dangling_receipt_reference "
            "refusal receipt at the proposal_validator_seam. Requires "
            "--scenario=all-green (only scenario reaching the proposal "
            "step). Deterministic-control mode — no LLM."
        ),
    )
    args = parser.parse_args(argv)

    args.root.mkdir(parents=True, exist_ok=True)

    finding: dict[str, Any] | None = None
    if args.finding_json is not None:
        # D0-Origin path: consume the genuine NQ-produced FindingSnapshot.
        finding = load_finding_snapshot_from_json(
            args.finding_json, scenario=args.scenario
        )

    result, transcript = run_drill_and_render(
        gov_dir=args.root,
        scenario=args.scenario,
        now=args.now,
        finding=finding,
        confabulate_citation=args.confabulate_citation,
    )
    envelope = build_json_envelope(result, transcript)
    # Stable JSON: sorted keys, 2-space indent.
    json.dump(envelope, sys.stdout, sort_keys=True, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
