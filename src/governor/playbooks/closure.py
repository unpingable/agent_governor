# SPDX-License-Identifier: Apache-2.0
"""Local dependency closure + ``dependency_closure_digest`` (Slice 2).

A playbook may declare opaque local ``imports`` refs. The closure is the
transitive set of resolved specs (root + dependencies). Resolution is via an
**injected resolver** (``ref -> source | None``) — the playbook layer asks for
content; it never discovers the world by filesystem walk, network, registry,
``latest``, or globbing. Missing refs and cycles refuse with typed errors.

> Two facts, kept separate (no free smoothie):
>   ``playbook_spec_digest``      — this authored spec (incl. its import REFS).
>   ``dependency_closure_digest`` — root + the *resolved* dependency set.
>
> The root says "I reference X." The closure says "X resolved to these bytes."
> Changing X's content moves the closure digest but NOT the root spec digest.

Closure membership is keyed by resolved ``playbook_spec_digest`` (so a diamond
shares one member), and the digest's member list is ordered **canonically by
digest**, not author order — so import order does not move the closure digest.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from governor.gate_receipt import canonical_json, content_hash

from .digest import playbook_spec_digest
from .spec import PlaybookError, PlaybookSpec, parse_playbook

# Bump if the closure basis composition changes.
CLOSURE_DIGEST_BASIS_VERSION = "playbook-closure.v0"

# A resolver maps an opaque ref to source bytes/str, or None when not found.
Resolver = Callable[[str], "str | bytes | None"]


class ClosureError(PlaybookError):
    """Base for dependency-closure refusals."""


class ImportNotFoundError(ClosureError):
    """A declared import ref did not resolve (resolver returned None)."""


class ImportCycleError(ClosureError):
    """The import graph contains a cycle (a spec reaches itself)."""


@dataclass(frozen=True)
class DependencyClosure:
    """The resolved transitive closure of a root playbook.

    ``root_digest`` is the root's ``playbook_spec_digest``; ``member_digests`` is
    the canonically-sorted set of every member's spec digest (root included).
    """

    root_digest: str
    member_digests: tuple[str, ...]


def resolve_closure(root: PlaybookSpec, resolver: Resolver) -> DependencyClosure:
    """Resolve the transitive dependency closure of ``root`` via ``resolver``.

    Refuses (``ImportNotFoundError``) a ref the resolver cannot resolve, and
    (``ImportCycleError``) a graph in which a spec reaches itself. A diamond
    (a dependency reached by two paths) is deduplicated, not refused. Parse
    errors in resolved sources propagate as the parser's typed errors.
    """
    collected: dict[str, PlaybookSpec] = {}

    def visit(spec: PlaybookSpec, path: frozenset[str]) -> None:
        digest = playbook_spec_digest(spec)
        if digest in path:
            raise ImportCycleError(
                f"import cycle detected: spec digest {digest} reaches itself"
            )
        if digest in collected:
            return  # already collected via another path (diamond) — dedup
        collected[digest] = spec
        child_path = path | {digest}
        for ref in spec.imports:
            source = resolver(ref)
            if source is None:
                raise ImportNotFoundError(f"import ref did not resolve: {ref!r}")
            child = parse_playbook(source)
            visit(child, child_path)

    visit(root, frozenset())
    return DependencyClosure(
        root_digest=playbook_spec_digest(root),
        member_digests=tuple(sorted(collected.keys())),
    )


def closure_basis(closure: DependencyClosure) -> dict[str, Any]:
    """The exact object the closure digest is taken over (exposed for review)."""
    return {
        "closure_basis": CLOSURE_DIGEST_BASIS_VERSION,
        "root_digest": closure.root_digest,
        "member_digests": list(closure.member_digests),
    }


def dependency_closure_digest(closure: DependencyClosure) -> str:
    """SHA-256 hex over the canonically-ordered closure basis. Stable under
    import order; changes when any resolved member's content changes."""
    return content_hash(canonical_json(closure_basis(closure)))


def resolve_closure_digest(root: PlaybookSpec, resolver: Resolver) -> str:
    """Convenience: resolve the closure and return its digest."""
    return dependency_closure_digest(resolve_closure(root, resolver))


# Re-exported for callers that want the Optional alias explicit.
__all__ = [
    "CLOSURE_DIGEST_BASIS_VERSION",
    "Resolver",
    "ClosureError",
    "ImportNotFoundError",
    "ImportCycleError",
    "DependencyClosure",
    "resolve_closure",
    "closure_basis",
    "dependency_closure_digest",
    "resolve_closure_digest",
]
