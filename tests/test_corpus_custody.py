# SPDX-License-Identifier: Apache-2.0
"""Corpus custody guard (Packet C, C3) — the executable half of the custody
model in ``docs/campaigns/corpus-custody/custody-model.md``.

The decision corpus (``golden/corpus/*.json``) is constitutional substrate: B2
ruled "the corpus is the contract." This guard stops that ruling from decaying
into "fixtures are scripture" — i.e. stops *membership in the directory* from
silently meaning *authority*.

The load-bearing object is ``golden/corpus/MANIFEST.json`` (schema
``agent_governor.corpus_manifest.v1``): the admission record. A case funds
verdicts ONLY if the manifest lists it in a funding class with a hash that
matches the file on disk. The case files themselves stay pure conformance
vectors — byte-identical across the sovereign and any mirror — so custody lives
in the admission record, not in the vectors, and not in the directory listing.

What this guard refuses:
  * a corpus file present on disk but absent from the manifest (unadmitted
    scripture — "file exists therefore contract");
  * a manifest case whose on-disk bytes no longer match its admitted hash
    (silent mutation of a frozen decision);
  * an unknown/absent ``custody_class`` (allowlist discipline);
  * a ``retired``/``disputed`` case being counted in the funding set;
  * a transition-kernel mirror that has silently diverged from the admitted
    bytes (checked only when the mirror repo is present; otherwise skipped with
    an explicit recorded reason, never a silent pass).

This guard is deliberately small and sharp. It is not a governance engine; it
adds one admission record and the checks that keep it honest.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

CORPUS_DIR = Path(__file__).parent.parent / "golden" / "corpus"
MANIFEST_PATH = CORPUS_DIR / "MANIFEST.json"
MANIFEST_SCHEMA = "agent_governor.corpus_manifest.v1"

# The closed custody vocabulary (custody-model.md C1). Unknown class => refused.
CUSTODY_CLASSES = {"contract", "example", "regression", "retired", "disputed", "generated"}
# Only these fund live verdicts. retired/disputed are fenced; example is
# illustrative; generated borrows its source's authority (not independent).
FUNDING_CLASSES = {"contract", "regression"}

# The conformance mirror. Present in a full constellation checkout; absent in a
# bare AG CI run (then the mirror check skips WITH a reason).
MIRROR_DIR = Path.home() / "git" / "transition-kernel" / "vectors" / "legacy"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_manifest() -> dict:
    assert MANIFEST_PATH.is_file(), (
        f"no admission manifest at {MANIFEST_PATH}. The corpus is constitutional "
        f"substrate; it may not be consumed as contract without an admission "
        f"record. See docs/campaigns/corpus-custody/custody-model.md."
    )
    return json.loads(MANIFEST_PATH.read_text())


MANIFEST = _load_manifest()
CASES = MANIFEST.get("cases", [])
CASE_IDS = [c["id"] for c in CASES]


def _corpus_files() -> list[Path]:
    return sorted(p for p in CORPUS_DIR.glob("*.json") if p.name != "MANIFEST.json")


def test_manifest_schema_and_shape():
    assert MANIFEST.get("schema") == MANIFEST_SCHEMA, (
        f"manifest schema must be {MANIFEST_SCHEMA!r}, got {MANIFEST.get('schema')!r}"
    )
    assert CASES, "manifest lists no cases (a glob-empty admission record is not admission)"
    seen = set()
    for c in CASES:
        assert {"id", "sha256", "custody_class"} <= set(c), f"manifest case missing fields: {c}"
        assert c["id"] not in seen, f"duplicate manifest entry for {c['id']!r}"
        seen.add(c["id"])


def test_every_custody_class_is_in_the_closed_vocabulary():
    # Allowlist discipline: an unknown or absent custody_class is refused, never
    # silently treated as contract.
    for c in CASES:
        assert c["custody_class"] in CUSTODY_CLASSES, (
            f"{c['id']}: custody_class {c['custody_class']!r} not in "
            f"{sorted(CUSTODY_CLASSES)} — unknown status is not admitted."
        )


def test_no_unadmitted_corpus_file_on_disk():
    # "file exists in the corpus dir" must not mean "file has authority": every
    # .json on disk must be an admitted manifest case. A stray/dropped file is a
    # loud failure, not silent scripture.
    on_disk = {p.name for p in _corpus_files()}
    admitted = set(CASE_IDS)
    unadmitted = on_disk - admitted
    assert not unadmitted, (
        f"corpus files present on disk but absent from the manifest: "
        f"{sorted(unadmitted)}. Admit them (custody-model.md C2) or remove them; "
        f"presence in the directory is not authority."
    )
    missing = admitted - on_disk
    assert not missing, f"manifest admits cases with no file on disk: {sorted(missing)}"


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_admitted_hash_matches_disk(case: dict):
    # A frozen decision may not change silently: the admitted sha256 must match
    # the bytes on disk. If a case content changed, this fails and updating the
    # manifest hash becomes a deliberate, attributable, reviewed act.
    path = CORPUS_DIR / case["id"]
    actual = _sha256(path)
    assert actual == case["sha256"], (
        f"{case['id']}: on-disk sha256 {actual[:12]} != admitted {case['sha256'][:12]}. "
        f"A contract corpus case changed. If intended, update MANIFEST.json "
        f"deliberately and cite the decision — never a silent regeneration."
    )


def test_retired_and_disputed_are_not_in_the_funding_set():
    # The fence is executable, not a comment: a case marked retired/disputed may
    # not fund live verdicts. (Today none are; this guards the future.)
    funding = MANIFEST.get("funding_classes", sorted(FUNDING_CLASSES))
    assert set(funding) == FUNDING_CLASSES, (
        f"funding_classes drifted: {funding} != {sorted(FUNDING_CLASSES)}. "
        f"retired/disputed/example/generated must never fund verdicts."
    )
    fenced = {c["id"]: c["custody_class"] for c in CASES if c["custody_class"] in {"retired", "disputed"}}
    for cid, klass in fenced.items():
        # A fenced case must not also be claimed as a funding case anywhere.
        assert klass not in FUNDING_CLASSES, f"{cid}: {klass} case cannot fund verdicts"


def test_generated_cases_carry_executable_provenance():
    # A `generated` case borrows its source's authority; it may not be
    # independent, and its provenance may not be forgeable. Fail-closed
    # UNCONDITIONALLY: `derived_from` must resolve to an existing, admitted,
    # DISTINCT, non-generated source, and the bytes must match — no missing-file
    # skip, no self-source, no generated-cites-generated chain that never bottoms
    # out at a real admitted source. Today no case is generated, so this refuses
    # a future generated case that arrives without honest provenance.
    admitted_by_id = {c["id"]: c for c in CASES}
    for c in CASES:
        if c["custody_class"] != "generated":
            continue
        src = c.get("derived_from")
        assert src, f"{c['id']}: custody_class=generated but no derived_from source."
        assert src != c["id"], (
            f"{c['id']}: derived_from cannot be itself — self-source is not "
            f"provenance."
        )
        src_case = admitted_by_id.get(src)
        assert src_case is not None, (
            f"{c['id']}: derived_from {src!r} is not an admitted manifest case; a "
            f"generated artifact may not cite a phantom or unadmitted source."
        )
        assert src_case["custody_class"] != "generated", (
            f"{c['id']}: derived_from {src!r} is itself generated; provenance must "
            f"bottom out at a real (non-generated) admitted source."
        )
        src_path = CORPUS_DIR / src
        assert src_path.is_file(), (
            f"{c['id']}: derived_from source {src!r} has no file on disk."
        )
        assert _sha256(src_path) == c["sha256"], (
            f"{c['id']}: generated bytes do not match declared source {src!r}; a "
            f"generated artifact may not diverge from its source."
        )


def test_no_fenced_case_is_consumed_by_the_verdict_test():
    # Cross-test coupling (closes the tautology codex flagged): the funding set
    # the verdict test actually consumes must exclude every retired/disputed
    # case. Proven by consulting the SAME manifest the verdict test now filters
    # on, so the two cannot drift apart.
    fenced = {c["id"] for c in CASES if c["custody_class"] in {"retired", "disputed"}}
    funded = {c["id"] for c in CASES if c["custody_class"] in FUNDING_CLASSES}
    assert not (fenced & funded), (
        f"cases both fenced and funded: {sorted(fenced & funded)}"
    )
    # And the verdict test's loader must agree with this manifest's funding set.
    from tests.test_corpus_contract import _ADMITTED_FUNDING

    assert _ADMITTED_FUNDING == funded, (
        f"verdict-test funding set {sorted(_ADMITTED_FUNDING)} != manifest funding "
        f"set {sorted(funded)} — the consumer and the admission record disagree."
    )


def test_funding_cases_have_the_contract_verdict_shape():
    # A case that funds verdicts must actually carry an expected_verdict — a
    # funding case that only illustrates is a laundering surface.
    from_verdict_fields = {
        "outcome", "refusal_kind", "refusing_seam", "effect_count",
        "consumed", "operational", "proposal_packet_present",
    }
    for c in CASES:
        if c["custody_class"] not in FUNDING_CLASSES:
            continue
        obj = json.loads((CORPUS_DIR / c["id"]).read_text())
        ev = obj.get("expected_verdict")
        assert isinstance(ev, dict) and set(ev) == from_verdict_fields, (
            f"{c['id']}: funding case must carry the full expected_verdict "
            f"({sorted(from_verdict_fields)}); got {sorted(ev) if isinstance(ev, dict) else ev!r}"
        )


def test_mirror_matches_admitted_bytes_or_is_absent():
    # The conformance mirror (transition-kernel/vectors/legacy) must PROVE it is
    # consuming the admitted corpus, not a local fork. Byte-identity by hash.
    # When the mirror repo is not checked out (bare AG CI), skip WITH a reason —
    # never a silent pass that could hide divergence.
    if not MIRROR_DIR.is_dir():
        pytest.skip(
            f"mirror repo not present at {MIRROR_DIR}; identity unverifiable in "
            f"this checkout (recorded, not silently passed). Full-constellation "
            f"CI must run this check."
        )
    mirror_files = {p.name: p for p in MIRROR_DIR.glob("*.json") if p.name != "MANIFEST.json"}
    admitted = {c["id"]: c["sha256"] for c in CASES}
    # Every admitted case must appear in the mirror with a matching hash.
    for cid, want in admitted.items():
        assert cid in mirror_files, (
            f"mirror is missing admitted case {cid!r} — the mirror has diverged "
            f"from the admitted corpus (dropped a case)."
        )
        got = _sha256(mirror_files[cid])
        assert got == want, (
            f"mirror {cid}: sha256 {got[:12]} != admitted {want[:12]} — the mirror "
            f"mutated expected behavior locally. Mirrors prove identity; they do "
            f"not crown their own fixtures."
        )
    # The mirror may not carry an EXTRA legacy case the sovereign never admitted
    # (that would be transition-kernel inventing local scripture).
    extra = set(mirror_files) - set(admitted)
    assert not extra, (
        f"mirror carries legacy cases absent from the admitted corpus: "
        f"{sorted(extra)}. Local corpus authorship is a custody violation; admit "
        f"upstream first."
    )
