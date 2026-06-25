# SPDX-License-Identifier: Apache-2.0
"""Slice 3 — the Wicket seam consumes playbook measurements as EVIDENCE.

> Certification is admissible evidence for Wicket, not authority.

``WicketClient.check_playbook_admission`` is two conjunctive gates in order:
evidence coherence (pure, refuses *before* Standing is consulted), then
authority (Standing, unchanged). The boss fight: coherent evidence + absent
Standing → refusal. Certification did not become permission.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from governor.gate_receipt import GateReceiptSystem
from governor.playbooks import (
    PlaybookAdmissionEvidence,
    certified_kind_measurement_digest,
    certify,
    dependency_closure_digest,
    parse_playbook,
    playbook_spec_digest,
    resolve_closure,
)
from governor.standing_client import (
    REFUSAL_KIND_STANDING_REQUIRED,
    StandingClient,
    StandingReceiptRef,
)
from governor.wicket_client import (
    REFUSAL_KIND_PLAYBOOK_EVIDENCE_UNBOUND,
    WICKET_PLAYBOOK_EVIDENCE_GATE,
    ActorStanding,
    CookedContext,
    Precedence,
    Revocation,
    ScopeAssertion,
    WicketClient,
    WicketRefusal,
    WicketVerdict,
)

_VALID_DIGEST = "a" * 64


class _FakeStandingService:
    def __init__(self, receipts: dict[str, StandingReceiptRef] | None = None):
        self.receipts = dict(receipts or {})
        self.call_count = 0

    def __call__(self, sid: str):
        self.call_count += 1
        return self.receipts.get(sid)


class _MockWicketCheck:
    SENTINEL_VERDICT = {"surface_verdict": "authorized", "_sentinel": True}

    def __init__(self):
        self.call_count = 0
        self.last_arg: CookedContext | None = None

    def __call__(self, cooked_context: CookedContext):
        self.call_count += 1
        self.last_arg = cooked_context
        return self.SENTINEL_VERDICT


def _make_cooked(standing_receipt_id: str | None) -> CookedContext:
    return CookedContext(
        actor="claude-code",
        actor_standing=ActorStanding(cls="execute", provenance="caller_asserted"),
        intended_action="playbook.run",
        operation_class="execute",
        target="sandbox://x.txt",
        claimed_basis={"rule": "playbook-governed action", "evidence_refs": []},
        precedence=Precedence(resolution="active", provenance="caller_asserted"),
        revocation=Revocation(
            basis_revoked=False,
            standing_forbidden=False,
            provenance="caller_asserted",
        ),
        expected_effect="run a governed playbook",
        call_timestamp="2026-06-25T00:00:00Z",
        standing_receipt_id=standing_receipt_id,
        scope_assertion=ScopeAssertion(
            scope_includes_target=True, provenance="caller_asserted"
        ),
    )


def _coherent_evidence(name: str = "alpha") -> PlaybookAdmissionEvidence:
    spec = parse_playbook(
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        "steps:\n"
        "  - id: s1\n"
        "    action: write_file\n"
        "    target: sandbox://x.txt\n"
    )
    cert = certify(spec)
    closure = resolve_closure(spec, lambda ref: None)
    return PlaybookAdmissionEvidence(
        spec_digest=playbook_spec_digest(spec),
        certified_kind=cert,
        claimed_certified_kind_digest=certified_kind_measurement_digest(cert),
        closure=closure,
        claimed_closure_digest=dependency_closure_digest(closure),
    )


def _tampered_evidence() -> PlaybookAdmissionEvidence:
    """Coherent shape, but the claimed cert digest is for a different spec."""
    ev = _coherent_evidence("alpha")
    other = _coherent_evidence("beta")
    return PlaybookAdmissionEvidence(
        spec_digest=ev.spec_digest,
        certified_kind=ev.certified_kind,
        claimed_certified_kind_digest=other.claimed_certified_kind_digest,
        closure=ev.closure,
        claimed_closure_digest=ev.claimed_closure_digest,
    )


def _client(sink=None, *, valid_standing: bool):
    receipts = (
        {_VALID_DIGEST: StandingReceiptRef(digest=_VALID_DIGEST, kind="grant_issued")}
        if valid_standing
        else {}
    )
    fake_standing = _FakeStandingService(receipts=receipts)
    mock_wicket = _MockWicketCheck()
    standing = StandingClient(verify_fn=fake_standing, receipt_sink=sink)
    client = WicketClient(
        standing_client=standing,
        wicket_check_fn=mock_wicket,
        receipt_sink=sink,
    )
    return client, fake_standing, mock_wicket


# --------------------------------------------------------------------------- #
# Happy path: coherent evidence + valid standing → admit + observe record.
# --------------------------------------------------------------------------- #


class TestCoherentEvidenceValidStanding:
    def test_admits_and_records_evidence_as_observe(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        client, fake_standing, mock_wicket = _client(sink, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)
        ev = _coherent_evidence()

        result = client.check_playbook_admission(cooked, ev)

        # Admitted by authority; wicket-check ran exactly once.
        assert isinstance(result, WicketVerdict)
        assert mock_wicket.call_count == 1
        assert result.value is _MockWicketCheck.SENTINEL_VERDICT

        # Three receipts: standing(pass), wicket admission(pass), evidence(observe).
        all_receipts = sink.receipt_store.all()
        gates = sorted(r.gate for r in all_receipts)
        assert gates == sorted(
            ["standing_seam", "wicket_seam", WICKET_PLAYBOOK_EVIDENCE_GATE]
        )

        # The evidence record is observational and cites the admission decision.
        ev_receipt = next(
            r for r in all_receipts if r.gate == WICKET_PLAYBOOK_EVIDENCE_GATE
        )
        assert ev_receipt.verdict == "observe"
        bundle = sink.evidence_for(ev_receipt)
        assert bundle["evidence_not_authority"] is True
        assert bundle["playbook_spec_digest"] == ev.spec_digest
        assert bundle["certified_kind_measurement_digest"] == (
            ev.claimed_certified_kind_digest
        )
        assert bundle["dependency_closure_digest"] == ev.claimed_closure_digest
        assert bundle["certified_kind"] == "procedure"
        # Evidence is DOWNSTREAM of authority: it cites the admission, never
        # the other way round.
        assert bundle["parent_receipt_ids"] == [result.receipt_id]


# --------------------------------------------------------------------------- #
# THE BOSS FIGHT: coherent evidence, absent standing → refusal.
# Certification did not become permission.
# --------------------------------------------------------------------------- #


class TestLaunderingAttempt:
    def test_coherent_evidence_absent_standing_refuses(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        client, fake_standing, mock_wicket = _client(sink, valid_standing=False)
        # Perfect playbook evidence...
        ev = _coherent_evidence()
        # ...but NO standing authority.
        cooked = _make_cooked(standing_receipt_id=None)

        result = client.check_playbook_admission(cooked, ev)

        # Refused on authority, not evidence.
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_STANDING_REQUIRED
        # Teeth: wicket-check NEVER invoked.
        assert mock_wicket.call_count == 0
        # Certification did NOT become permission: no observe evidence record
        # was minted, because nothing was admitted.
        gates = [r.gate for r in sink.receipt_store.all()]
        assert WICKET_PLAYBOOK_EVIDENCE_GATE not in gates

    def test_coherent_evidence_does_not_short_circuit_standing(self, tmp_path: Path):
        """Even with valid evidence, the Standing seam is still consulted —
        evidence is necessary, never sufficient."""
        sink = GateReceiptSystem(tmp_path)
        client, fake_standing, mock_wicket = _client(sink, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)
        ev = _coherent_evidence()

        client.check_playbook_admission(cooked, ev)
        # Standing downstream WAS consulted (evidence did not bypass it).
        assert fake_standing.call_count == 1


# --------------------------------------------------------------------------- #
# Incoherent evidence refuses BEFORE the Standing seam is consulted.
# --------------------------------------------------------------------------- #


class TestIncoherentEvidence:
    def test_tampered_evidence_refuses_before_standing(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        # Standing WOULD be valid if reached — proving evidence gates first.
        client, fake_standing, mock_wicket = _client(sink, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check_playbook_admission(cooked, _tampered_evidence())

        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_PLAYBOOK_EVIDENCE_UNBOUND
        # Teeth: neither Standing nor the wicket-check was consulted.
        assert fake_standing.call_count == 0
        assert mock_wicket.call_count == 0
        # The refusal receipt carries the structured binding reason.
        refusal = sink.receipt_store.get_by_id(result.receipt_id)
        assert refusal is not None
        assert refusal.gate == "wicket_seam"
        assert refusal.verdict == "block"
        bundle = sink.evidence_for(refusal)
        assert bundle["binding_reason"] == "cert_digest_tampered"
        # Chain origin — no standing parent (refused before reaching standing).
        assert bundle["parent_receipt_ids"] == []

    def test_no_admission_or_evidence_receipt_on_incoherent(self, tmp_path: Path):
        sink = GateReceiptSystem(tmp_path)
        client, _, _ = _client(sink, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        client.check_playbook_admission(cooked, _tampered_evidence())

        gates = [r.gate for r in sink.receipt_store.all()]
        # Only the single block receipt — no pass admission, no observe record.
        assert WICKET_PLAYBOOK_EVIDENCE_GATE not in gates
        assert gates.count("standing_seam") == 0
        assert all(
            sink.receipt_store.get_by_id(r.receipt_id).verdict == "block"
            for r in sink.receipt_store.all()
        )


# --------------------------------------------------------------------------- #
# Back-compat: no sink still verifies + admits, just no receipts.
# --------------------------------------------------------------------------- #


class TestNoSink:
    def test_admits_without_sink(self):
        client, _, mock_wicket = _client(sink=None, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check_playbook_admission(cooked, _coherent_evidence())
        assert isinstance(result, WicketVerdict)
        assert result.receipt_id is None
        assert mock_wicket.call_count == 1

    def test_incoherent_refuses_without_sink(self):
        client, fake_standing, mock_wicket = _client(sink=None, valid_standing=True)
        cooked = _make_cooked(standing_receipt_id=_VALID_DIGEST)

        result = client.check_playbook_admission(cooked, _tampered_evidence())
        assert isinstance(result, WicketRefusal)
        assert result.refusal_kind == REFUSAL_KIND_PLAYBOOK_EVIDENCE_UNBOUND
        assert result.receipt_id is None
        assert fake_standing.call_count == 0
        assert mock_wicket.call_count == 0
