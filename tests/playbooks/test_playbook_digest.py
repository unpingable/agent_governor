# SPDX-License-Identifier: Apache-2.0
"""Slice 0 — custody over authored bytes: parse → canonical → digest.

Measurement only: no Wicket / Standing / LA / certified_kind / closure. These
specimens pin the load-bearing properties — deterministic canonical bytes,
formatting-invariance, semantic-sensitivity (incl. step order), and that every
unsupported construct REFUSES with a typed error rather than coercing.
"""

from __future__ import annotations

import pytest

from governor.playbooks import (
    CANONICAL_VERSION,
    DIGEST_BASIS_VERSION,
    PARSER_VERSION,
    PlaybookSchemaError,
    PlaybookSpec,
    PlaybookStep,
    RestrictedYAMLError,
    canonical_spec_bytes,
    digest_basis,
    parse_playbook,
    playbook_spec_digest,
)

# The aggressively boring fixture — no reactors, pipelines, or imports.
TOY = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""

TWO_STEP = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
  - id: step2
    action: write_file
    target: sandbox://beta.txt
"""


# --------------------------------------------------------------------------- #
# Parse
# --------------------------------------------------------------------------- #


def test_fixture_parses() -> None:
    spec = parse_playbook(TOY)
    assert isinstance(spec, PlaybookSpec)
    assert spec.schema == "governed-playbook.v0"
    assert spec.kind == "procedure"
    assert spec.name == "toy-copy"
    assert spec.steps == (
        PlaybookStep(id="step1", action="write_file", target="sandbox://alpha.txt"),
    )


# --------------------------------------------------------------------------- #
# Determinism + formatting-invariance
# --------------------------------------------------------------------------- #


def test_canonical_bytes_are_deterministic() -> None:
    a = canonical_spec_bytes(parse_playbook(TOY))
    b = canonical_spec_bytes(parse_playbook(TOY))
    assert a == b
    assert isinstance(a, bytes)


def test_equivalent_formatting_produces_same_digest() -> None:
    # Reordered top-level keys, reordered step keys, comments, extra blank lines,
    # and quoted scalars — all semantically identical to TOY.
    reformatted = """\
# a comment
name: "toy-copy"

kind: procedure
steps:
  - target: sandbox://alpha.txt
    action: write_file
    id: step1
schema: governed-playbook.v0
"""
    assert playbook_spec_digest(parse_playbook(TOY)) == playbook_spec_digest(
        parse_playbook(reformatted)
    )


def test_flow_style_same_digest() -> None:
    # JSON-ish flow style is the same document.
    flow = (
        '{"schema": "governed-playbook.v0", "kind": "procedure", '
        '"name": "toy-copy", "steps": [{"id": "step1", '
        '"action": "write_file", "target": "sandbox://alpha.txt"}]}'
    )
    assert playbook_spec_digest(parse_playbook(TOY)) == playbook_spec_digest(
        parse_playbook(flow)
    )


# --------------------------------------------------------------------------- #
# Semantic-sensitivity
# --------------------------------------------------------------------------- #


def test_semantic_change_produces_different_digest() -> None:
    changed = TOY.replace("alpha.txt", "gamma.txt")
    assert playbook_spec_digest(parse_playbook(TOY)) != playbook_spec_digest(
        parse_playbook(changed)
    )


def test_name_change_produces_different_digest() -> None:
    changed = TOY.replace("toy-copy", "toy-move")
    assert playbook_spec_digest(parse_playbook(TOY)) != playbook_spec_digest(
        parse_playbook(changed)
    )


def test_step_order_is_semantic() -> None:
    swapped = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step2
    action: write_file
    target: sandbox://beta.txt
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""
    assert playbook_spec_digest(parse_playbook(TWO_STEP)) != playbook_spec_digest(
        parse_playbook(swapped)
    )


# --------------------------------------------------------------------------- #
# Restricted-dialect refusals (typed, never coerced)
# --------------------------------------------------------------------------- #


def test_anchor_is_refused() -> None:
    src = """\
schema: governed-playbook.v0
kind: &k procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""
    with pytest.raises(RestrictedYAMLError, match="anchor"):
        parse_playbook(src)


def test_alias_is_refused() -> None:
    src = """\
schema: governed-playbook.v0
kind: &k procedure
name: *k
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""
    with pytest.raises(RestrictedYAMLError, match="anchor|alias"):
        parse_playbook(src)


def test_merge_key_is_refused() -> None:
    src = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
defaults: &d
  action: write_file
steps:
  - id: step1
    <<: *d
    target: sandbox://alpha.txt
"""
    with pytest.raises(RestrictedYAMLError):
        parse_playbook(src)


def test_duplicate_key_is_refused() -> None:
    src = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
name: shadow
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""
    with pytest.raises(RestrictedYAMLError, match="duplicate"):
        parse_playbook(src)


def test_custom_tag_is_refused() -> None:
    src = """\
schema: governed-playbook.v0
kind: procedure
name: !!python/object/apply:os.system ["echo hi"]
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""
    with pytest.raises(RestrictedYAMLError):
        parse_playbook(src)


# --------------------------------------------------------------------------- #
# Schema/shape refusals
# --------------------------------------------------------------------------- #


def test_unknown_top_level_key_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="unknown top-level"):
        parse_playbook(TOY + "extra: nope\n")


def test_missing_key_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="missing required"):
        parse_playbook("schema: governed-playbook.v0\nkind: procedure\nname: x\n")


def test_unknown_schema_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="unsupported schema"):
        parse_playbook(TOY.replace("governed-playbook.v0", "governed-playbook.v9"))


def test_implicit_bool_in_string_field_is_refused() -> None:
    # `name: true` is coerced by YAML to a bool — refused at the typed boundary.
    with pytest.raises(PlaybookSchemaError, match="must be a string"):
        parse_playbook(TOY.replace("name: toy-copy", "name: true"))


def test_integer_in_string_field_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="must be a string"):
        parse_playbook(TOY.replace("name: toy-copy", "name: 123"))


def test_steps_not_a_list_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="steps must be a list"):
        parse_playbook(
            "schema: governed-playbook.v0\nkind: procedure\nname: x\nsteps: nope\n"
        )


def test_empty_steps_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="non-empty"):
        parse_playbook(
            "schema: governed-playbook.v0\nkind: procedure\nname: x\nsteps: []\n"
        )


def test_unknown_step_key_is_refused() -> None:
    src = TOY.replace(
        "    target: sandbox://alpha.txt",
        "    target: sandbox://alpha.txt\n    rollback: true",
    )
    with pytest.raises(PlaybookSchemaError, match="unknown key"):
        parse_playbook(src)


def test_top_level_sequence_is_refused() -> None:
    with pytest.raises(PlaybookSchemaError, match="must be a mapping"):
        parse_playbook("- a\n- b\n")


# --------------------------------------------------------------------------- #
# Digest basis carries explicit versions
# --------------------------------------------------------------------------- #


def test_digest_basis_includes_versions() -> None:
    basis = digest_basis(parse_playbook(TOY))
    assert basis["digest_basis"] == DIGEST_BASIS_VERSION
    assert basis["parser_version"] == PARSER_VERSION
    assert basis["canonical_version"] == CANONICAL_VERSION
    assert basis["spec"]["name"] == "toy-copy"


def test_digest_is_hex_sha256() -> None:
    d = playbook_spec_digest(parse_playbook(TOY))
    assert isinstance(d, str)
    assert len(d) == 64
    int(d, 16)  # raises if not hex
