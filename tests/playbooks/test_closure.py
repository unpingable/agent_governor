# SPDX-License-Identifier: Apache-2.0
"""Slice 2 — local dependency closure + dependency_closure_digest.

Pins: the byte-identity regression (adding optional `imports` must not move an
import-less digest), opaque-ref imports via an injected resolver, missing/cycle/
duplicate refusals, canonical (order-independent) closure digest, and the
separation between the root spec digest ("I reference X") and the closure digest
("X resolved to these bytes") — no free smoothie.
"""

from __future__ import annotations

import pytest

from governor.playbooks import (
    ImportCycleError,
    ImportNotFoundError,
    PlaybookSchemaError,
    canonical_spec_bytes,
    certified_kind_measurement_digest,
    certify,
    dependency_closure_digest,
    parse_playbook,
    playbook_spec_digest,
    resolve_closure,
    resolve_closure_digest,
)

TOY = """\
schema: governed-playbook.v0
kind: procedure
name: toy-copy
steps:
  - id: step1
    action: write_file
    target: sandbox://alpha.txt
"""

# Golden values captured on the integration branch BEFORE Slice 2 edits.
GOLDEN_SPEC_DIGEST = "4444d9d06ca40e1b06e6274b907a6ec65e78f5621052508b561eca1a0027a234"
GOLDEN_CERT_DIGEST = "7de8cb8badb447761173b8562da6a30e05d270a5a73f0f96e34fc107c8ac11fd"
GOLDEN_CANON = (
    '{"kind":"procedure","name":"toy-copy","schema":"governed-playbook.v0",'
    '"steps":[{"action":"write_file","id":"step1","target":"sandbox://alpha.txt"}]}'
)


def _pb(name: str, *imports: str, target: str = "sandbox://x.txt") -> str:
    imp = ""
    if imports:
        imp = "imports:\n" + "".join(f"  - {r}\n" for r in imports)
    return (
        "schema: governed-playbook.v0\n"
        "kind: procedure\n"
        f"name: {name}\n"
        f"{imp}"
        "steps:\n"
        "  - id: s1\n"
        "    action: write_file\n"
        f"    target: {target}\n"
    )


def _resolver(graph: dict[str, str]):
    return lambda ref: graph.get(ref)


# --------------------------------------------------------------------------- #
# THE regression: optional imports must not move an import-less digest
# --------------------------------------------------------------------------- #


def test_import_less_digest_is_byte_unchanged_from_slice0() -> None:
    spec = parse_playbook(TOY)
    assert canonical_spec_bytes(spec).decode() == GOLDEN_CANON
    assert playbook_spec_digest(spec) == GOLDEN_SPEC_DIGEST
    assert certified_kind_measurement_digest(certify(spec)) == GOLDEN_CERT_DIGEST


def test_empty_imports_list_normalizes_to_absent() -> None:
    spec = parse_playbook(TOY.replace("steps:", "imports: []\nsteps:"))
    assert spec.imports == ()
    assert playbook_spec_digest(spec) == GOLDEN_SPEC_DIGEST  # identical to no-imports


# --------------------------------------------------------------------------- #
# Resolution
# --------------------------------------------------------------------------- #


def test_root_only_closure() -> None:
    closure = resolve_closure(parse_playbook(TOY), _resolver({}))
    assert closure.member_digests == (closure.root_digest,)


def test_one_local_import_resolves() -> None:
    root = parse_playbook(_pb("root", "ref/a"))
    closure = resolve_closure(root, _resolver({"ref/a": _pb("a")}))
    assert len(closure.member_digests) == 2
    assert closure.root_digest in closure.member_digests


def test_transitive_import_resolves() -> None:
    graph = {"ref/a": _pb("a", "ref/b"), "ref/b": _pb("b")}
    closure = resolve_closure(parse_playbook(_pb("root", "ref/a")), _resolver(graph))
    assert len(closure.member_digests) == 3


def test_diamond_dedups_not_refuses() -> None:
    # root -> a, root -> b, a -> c, b -> c. c appears once.
    graph = {
        "ref/a": _pb("a", "ref/c"),
        "ref/b": _pb("b", "ref/c"),
        "ref/c": _pb("c"),
    }
    closure = resolve_closure(
        parse_playbook(_pb("root", "ref/a", "ref/b")), _resolver(graph)
    )
    assert len(closure.member_digests) == 4  # root, a, b, c (c once)


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #


def test_missing_import_refuses() -> None:
    with pytest.raises(ImportNotFoundError, match="did not resolve"):
        resolve_closure(parse_playbook(_pb("root", "ref/missing")), _resolver({}))


def test_duplicate_import_ref_refuses_at_parse() -> None:
    with pytest.raises(PlaybookSchemaError, match="duplicate import ref"):
        parse_playbook(_pb("root", "ref/a", "ref/a"))


def test_direct_cycle_refuses() -> None:
    # root imports a ref that resolves back to root.
    root_src = _pb("root", "ref/self")
    with pytest.raises(ImportCycleError, match="cycle"):
        resolve_closure(parse_playbook(root_src), _resolver({"ref/self": root_src}))


def test_indirect_cycle_refuses() -> None:
    root_src = _pb("root", "ref/a")
    a_src = _pb("a", "ref/root")
    graph = {"ref/a": a_src, "ref/root": root_src}
    with pytest.raises(ImportCycleError):
        resolve_closure(parse_playbook(root_src), _resolver(graph))


def test_non_string_import_ref_refuses() -> None:
    src = (
        "schema: governed-playbook.v0\nkind: procedure\nname: root\n"
        "imports:\n  - 123\nsteps:\n  - {id: s1, action: a, target: t}\n"
    )
    with pytest.raises(PlaybookSchemaError, match="non-empty string ref"):
        parse_playbook(src)


# --------------------------------------------------------------------------- #
# Closure digest: order-stable, content-sensitive
# --------------------------------------------------------------------------- #


def test_import_declaration_order_is_not_semantic() -> None:
    # imports is a set: [a, b] and [b, a] are the same dependency declaration, so
    # both the root spec digest AND the closure digest are unchanged by reordering.
    graph = {"ref/a": _pb("a"), "ref/b": _pb("b")}
    r1 = parse_playbook(_pb("r", "ref/a", "ref/b"))
    r2 = parse_playbook(_pb("r", "ref/b", "ref/a"))
    assert playbook_spec_digest(r1) == playbook_spec_digest(r2)
    assert resolve_closure_digest(r1, _resolver(graph)) == resolve_closure_digest(
        r2, _resolver(graph)
    )


def test_closure_digest_independent_of_member_discovery_order() -> None:
    # Same root, same dependency set, resolvers that present deps in different
    # internal order — the closure digest (sorted by member digest) is identical.
    graph = {"ref/a": _pb("a"), "ref/b": _pb("b")}
    root = parse_playbook(_pb("r", "ref/a", "ref/b"))
    assert resolve_closure_digest(root, _resolver(graph)) == resolve_closure_digest(
        root, _resolver(dict(reversed(list(graph.items()))))
    )


def test_closure_digest_changes_when_imported_content_changes() -> None:
    root = parse_playbook(_pb("r", "ref/a"))
    v1 = resolve_closure_digest(root, _resolver({"ref/a": _pb("a", target="sandbox://1")}))
    v2 = resolve_closure_digest(root, _resolver({"ref/a": _pb("a", target="sandbox://2")}))
    assert v1 != v2


# --------------------------------------------------------------------------- #
# No free smoothie: root spec digest vs closure digest are different claims
# --------------------------------------------------------------------------- #


def test_root_spec_digest_changes_when_import_ref_text_changes() -> None:
    # The author changing which ref they reference changes the AUTHORED spec.
    a = playbook_spec_digest(parse_playbook(_pb("r", "ref/a")))
    b = playbook_spec_digest(parse_playbook(_pb("r", "ref/b")))
    assert a != b


def test_imported_content_change_moves_closure_not_root_spec_digest() -> None:
    # The boundary: changing X's CONTENT moves the closure digest but leaves the
    # root's spec digest unchanged (the root only says "I reference X").
    root = parse_playbook(_pb("r", "ref/a"))
    root_digest = playbook_spec_digest(root)
    c1 = resolve_closure_digest(root, _resolver({"ref/a": _pb("a", target="sandbox://1")}))
    c2 = resolve_closure_digest(root, _resolver({"ref/a": _pb("a", target="sandbox://2")}))
    assert c1 != c2  # closure moved
    assert playbook_spec_digest(root) == root_digest  # root spec digest did not


def test_closure_digest_is_not_the_root_spec_digest() -> None:
    root = parse_playbook(_pb("r", "ref/a"))
    closure_d = resolve_closure_digest(root, _resolver({"ref/a": _pb("a")}))
    assert closure_d != playbook_spec_digest(root)
