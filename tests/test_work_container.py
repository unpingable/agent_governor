# SPDX-License-Identifier: Apache-2.0
"""Slice 4 — WorkContainer projection over the proven CD-4B live shape.

Ten pins, matching the S4 acceptance criteria. The through-line: the container is a
faithful PROJECTION of already-admitted work — it validates, traces every field to a
shipped object, links to the produced ReviewPacket, and NEVER lets provider status,
registry membership, or a stale/forged digest manufacture admission. Projection, not
delegation.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from governor import work_container as wc_mod
from governor.work_container import (
    AdmissionBasis,
    Citation,
    DigestMismatchError,
    MalformedAdmissionRefError,
    Origin,
    RationProjection,
    ScopeProjection,
    UnverifiedCitationError,
    project_cd4b_work_container,
    project_work_container,
    verify_container,
    verify_seal,
)

def _imports_module(source: str, name: str) -> bool:
    """True iff an import STATEMENT (not prose) references ``name``. The module's
    docstring names provider_registry/governed_dispatch to describe boundaries; we
    care only that it does not IMPORT them."""
    for line in source.splitlines():
        s = line.strip()
        if (s.startswith("import ") or s.startswith("from ")) and name in s:
            return True
    return False


_REPO = Path(__file__).resolve().parents[1]
_SPECIMEN = _REPO / "docs" / "campaigns" / "conveyor-dogfood" / "specimens" / "cd4-docs-normalize"
_SCHEMA_PATH = _REPO / "schemas" / "work_container.v1.json"


@pytest.fixture()
def container():
    return project_cd4b_work_container(_SPECIMEN)


# 1. Projection validates against the DRAFT schema. -------------------------- #
def test_projection_validates_against_v1_schema(container):
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(container.to_schema_dict())


# 2. Includes plan_ref / admission basis / citation verification state. ------ #
def test_projection_carries_plan_ref_and_verified_citations(container):
    sd = container.to_schema_dict()
    # plan_ref is the governed plan's raw-bytes digest (the CD-4B evidence spine).
    plan_ref = wc_mod.sha256_ref_of_bytes((_SPECIMEN / "plan.md").read_bytes())
    assert sd["origin"]["proposal_ref"] == plan_ref
    # admission_ref is a re-verifiable sha256 citation, not prose.
    assert sd["admission_ref"].startswith("sha256:")
    # citation verification state is present and every load-bearing citation resolved.
    basis = sd["admission_basis"]
    assert basis["all_citations_verified"] is True
    names = {c["name"] for c in basis["citations"]}
    assert names == {"playbook_digest", "ration_card_digest", "queued_playbook_ref", "approval_ref"}
    assert all(c["verified"] for c in basis["citations"])


def test_admission_ref_is_recomputable_from_the_basis(container):
    # admission_ref is the seal over {plan_ref, citations} — re-verifiable, not asserted.
    sd = container.to_schema_dict()
    plan_ref = wc_mod.sha256_ref_of_bytes((_SPECIMEN / "plan.md").read_bytes())
    recomputed = wc_mod._seal_over(
        {"plan_ref": plan_ref, "citations": sd["admission_basis"]["citations"]}
    )
    assert recomputed == sd["admission_ref"]


# 3. Includes ration/fence scope and stop conditions. ------------------------ #
def test_projection_carries_ration_scope_and_stop_conditions(container):
    sd = container.to_schema_dict()
    ration = json.loads((_SPECIMEN / "ration_card.json").read_bytes())
    ration_ref = wc_mod.sha256_ref_of_bytes((_SPECIMEN / "ration_card.json").read_bytes())
    # ration_projection is a read-only snapshot of the RationCard locked axes.
    rp = sd["ration_projection"]
    assert rp["source_ref"] == ration_ref
    assert rp["network"] is ration["network_allowed"]
    assert rp["git"] is ration["git_allowed"]
    assert rp["doctrine_writes"] is ration["doctrine_writes_allowed"]
    assert rp["observe_only"] is ration["output_is_observe_only"]
    assert rp["external_send"] is False  # no card axis; fail-closed
    # write scope traces to the RationCard; forbidden fence to the queued item.
    assert sd["scope_projection"]["source_ref"] == ration_ref
    assert tuple(sd["scope_projection"]["allowed_write_paths"]) == tuple(ration["allowed_write_paths"])
    queue = json.loads((_SPECIMEN / "queue.json").read_bytes())["items"][0]
    assert tuple(sd["scope_projection"]["forbidden_paths"]) == tuple(queue["forbidden_paths"])
    assert tuple(sd["stop_conditions"]) == tuple(queue["stop_conditions"])


# 4. Records adapter/runtime target WITHOUT granting provider trust. --------- #
def test_routing_target_is_a_label_not_trust(container):
    sd = container.to_schema_dict()
    # The plan's declared harness is recorded as a routing candidate…
    assert sd["routing"]["eligible_provider"] == "claude_code"
    # …but nothing in the container confers trust or advances conformance. The
    # projector never imports or touches the provider registry (proven in test 8);
    # routing is a bare label, no trust/conformance field anywhere.
    assert "conformance" not in json.dumps(sd)
    assert "trusted" not in json.dumps(sd)


# 5. Links to the produced ReviewPacket (or obstruction) output. ------------- #
def test_projection_links_produced_review_packet(container):
    sd = container.to_schema_dict()
    pr = sd["produced_receipts"]
    packet_ref = wc_mod.sha256_ref_of_bytes((_SPECIMEN / "review_packet.manifest.json").read_bytes())
    assert pr["review_packet_ref"] == packet_ref
    assert pr["review_packet_status"] == "no_change"
    assert pr["run_session_id"] == wc_mod.CD4B_SESSION_ID
    assert pr["promotion_id"] == wc_mod.CD4B_PROMOTION_ID


# 6. Dirty flip/specimen files fenced from promotion are correctly represented. #
def test_flip_files_are_not_the_runs_output(container):
    sd = container.to_schema_dict()
    # The flip files (plan/queue/approval witness) are the admission CITATIONS, not
    # the run's produced output. They must appear only as citation refs, never as
    # a produced/changed artifact of the run.
    packet = json.loads((_SPECIMEN / "review_packet.manifest.json").read_bytes())
    assert packet["files_changed"] == []  # the CD-4B keep changed no fenced flip file
    cited_refs = {c["ref"] for c in sd["admission_basis"]["citations"]}
    # queue.json (a flip file) is a verified citation, i.e. represented as basis…
    queue_ref = wc_mod.sha256_ref_of_bytes((_SPECIMEN / "queue.json").read_bytes())
    assert queue_ref in cited_refs
    # …and the approval witness filename is one of the fenced flip files.
    assert "operator_queued_playbook.operator_approved_2026-07-04" in wc_mod.CD4B_FENCED_FLIP_FILES


# 7. Provider success/completion cannot be read as AG admitted success. ------ #
def test_provider_status_does_not_alter_admission(container):
    base_admission = container.admission_ref
    # Swap the produced testimony to a fabricated "success"-shaped packet status.
    forged = dataclasses.replace(
        container,
        produced_receipts=dataclasses.replace(
            container.produced_receipts, review_packet_status="proposed_patch"
        ),
    )
    # admission_ref is untouched by provider testimony — it is basis-derived, not
    # status-derived. Provider status lives only in produced_receipts.
    assert forged.admission_ref == base_admission
    sd = forged.to_schema_dict()
    # There is no field that flips to admitted/accepted on provider status.
    assert "admitted" not in json.dumps(sd)
    assert "accepted" not in json.dumps(sd)
    # The status is explicitly the ReviewPacket lifecycle word, not an AG verdict.
    assert sd["produced_receipts"]["review_packet_status"] == "proposed_patch"


# 8. Registry presence/absence cannot alter the admission verdict. ----------- #
def test_registry_state_does_not_change_the_projection():
    from governor.provider_descriptors import claude_code_descriptor
    from governor.provider_registry import ProviderRegistry

    empty_digest = project_cd4b_work_container(_SPECIMEN).seal()
    # Register the routed provider, then project again — byte-identical container.
    reg = ProviderRegistry()
    reg.register(claude_code_descriptor())
    assert reg.get("claude_code") is not None
    registered_digest = project_cd4b_work_container(_SPECIMEN).seal()
    assert registered_digest == empty_digest
    # The projector never consults a registry — its module imports none.
    src = Path(wc_mod.__file__).read_text()
    assert not _imports_module(src, "provider_registry")


# 9. Digest mismatch / stale projection / unverified citation fail closed. --- #
def test_seal_mismatch_fails_closed(container):
    sd = container.to_schema_dict()
    verify_seal(sd)  # honest container verifies
    tampered = json.loads(json.dumps(sd))
    tampered["intent"] = tampered["intent"] + " (tampered)"  # body changed, seal stale
    with pytest.raises(DigestMismatchError):
        verify_seal(tampered)


def test_unverified_citation_is_refused():
    # A governed plan whose citation does not resolve is not admitted work.
    with pytest.raises(UnverifiedCitationError):
        project_work_container(
            work_id="wc-x",
            admission_ref="sha256:" + "0" * 64,
            origin=Origin(submitted_by="operator"),
            intent="x",
            scope_projection=ScopeProjection(source_ref="sha256:" + "1" * 64),
            ration_projection=RationProjection(
                source_ref="sha256:" + "1" * 64,
                network=False, external_send=False, git=False,
                doctrine_writes=False, observe_only=True,
            ),
            admission_basis=AdmissionBasis(
                citations=(Citation("ration_card_digest", "sha256:" + "2" * 64, False),)
            ),
        )


def test_malformed_admission_ref_is_refused():
    with pytest.raises(MalformedAdmissionRefError):
        project_work_container(
            work_id="wc-x",
            admission_ref="not-a-digest",
            origin=Origin(submitted_by="operator"),
            intent="x",
            scope_projection=ScopeProjection(source_ref="sha256:" + "1" * 64),
            ration_projection=RationProjection(
                source_ref="sha256:" + "1" * 64,
                network=False, external_send=False, git=False,
                doctrine_writes=False, observe_only=True,
            ),
            admission_basis=AdmissionBasis(
                citations=(Citation("ration_card_digest", "sha256:" + "2" * 64, True),)
            ),
        )


# 10. No dispatch behavior — the module moves no cargo, it only describes it. - #
def test_projection_has_no_dispatch_verb_and_is_pure():
    # The module exposes no run/dispatch/execute/launch surface; dispatch stays in
    # governed_dispatch. A projection is data, not an action.
    for verb in ("run", "dispatch", "execute", "launch", "run_once", "dispatch_under_ration_card"):
        assert not hasattr(wc_mod, verb)
    # Purity/determinism: projecting twice yields byte-identical wire records (no
    # timestamps, no ambient state, no side effects that would change output).
    a = project_cd4b_work_container(_SPECIMEN).to_json()
    b = project_cd4b_work_container(_SPECIMEN).to_json()
    assert a == b
    # And it does not import the dispatch membrane.
    src = Path(wc_mod.__file__).read_text()
    assert not _imports_module(src, "governed_dispatch")


def test_forged_all_citations_verified_is_refused(container):
    # The seal is a content hash, not a signature — a forger can recompute it. So a
    # hand-authored container claiming all_citations_verified:true while a citation
    # says false (with a matching, freshly-computed seal) must still be refused on
    # read. verify_seal alone would pass; verify_container closes the seam.
    forged = json.loads(json.dumps(container.to_schema_dict()))
    forged["admission_basis"]["citations"][0]["verified"] = False  # a lie vs the flag
    # rebuild a matching seal over the tampered body (the forger's move)
    body = {k: v for k, v in forged.items() if k != "custody"}
    body["custody"] = {k: v for k, v in forged["custody"].items() if k != "digest"}
    forged["custody"]["digest"] = wc_mod._seal_over(body)
    verify_seal(forged)  # seal recomputes — integrity check alone is fooled
    with pytest.raises(UnverifiedCitationError):
        verify_container(forged)  # …but the non-laundering gate refuses


def test_approval_witness_must_be_declared_and_nonempty(tmp_path):
    # Hardening (codex F3): an approval witness that is a bare empty stub must NOT
    # count as verified — "a written 'approved' is prose until independently
    # witnessed" (CD-1a governance_approval_unverified). Copy the specimen, empty the
    # witness, and the projector must refuse (unverified citation).
    import shutil

    dst = tmp_path / "spec"
    shutil.copytree(_SPECIMEN, dst)
    witness = dst / "operator_queued_playbook.operator_approved_2026-07-04"
    witness.write_text("")  # empty stub — the spoof
    with pytest.raises(UnverifiedCitationError):
        project_cd4b_work_container(dst)


def test_source_ref_must_be_a_content_address():
    # Hardening (codex F4): a projection must cite its source by sha256, so the
    # snapshot is re-verifiable against that source.
    with pytest.raises(wc_mod.WorkContainerError):
        project_work_container(
            work_id="wc-x",
            admission_ref="sha256:" + "0" * 64,
            origin=Origin(submitted_by="operator"),
            intent="x",
            scope_projection=ScopeProjection(source_ref="not-a-digest"),
            ration_projection=RationProjection(
                source_ref="sha256:" + "1" * 64,
                network=False, external_send=False, git=False,
                doctrine_writes=False, observe_only=True,
            ),
            admission_basis=AdmissionBasis(
                citations=(Citation("ration_card_digest", "sha256:" + "2" * 64, True),)
            ),
        )


def test_verify_container_rejects_wrong_schema_version(container):
    # Hardening (codex F5): the read gate refuses an unexpected schema_version even
    # if the seal recomputes over the tampered body.
    forged = json.loads(json.dumps(container.to_schema_dict()))
    forged["schema_version"] = "work_container.v2"
    body = {k: v for k, v in forged.items() if k != "custody"}
    body["custody"] = {k: v for k, v in forged["custody"].items() if k != "digest"}
    forged["custody"]["digest"] = wc_mod._seal_over(body)
    verify_seal(forged)  # seal is internally consistent…
    with pytest.raises(wc_mod.WorkContainerError):
        verify_container(forged)  # …but the version gate refuses


# Persisted specimen artifact stays in sync with the projector. -------------- #
def test_persisted_artifact_matches_projection(container):
    persisted = json.loads((_SPECIMEN / "work_container.v1.json").read_text())
    assert persisted == container.to_schema_dict()
    verify_container(persisted)  # full non-laundering read gate on the shipped artifact
