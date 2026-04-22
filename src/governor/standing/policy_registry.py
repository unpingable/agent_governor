# SPDX-License-Identifier: Apache-2.0
"""Policy registry: loads ratified policy_declaration artifacts.

The registry resolves ``policy_artifact_id`` references on binding
receipts (validator_contract §8.2). It also exposes the
exception-class registry, which per the ratified Q3 decision starts
empty — any compressed authorization is rejected until at least one
exception class is added via its own policy_declaration.

Stdlib-only frontmatter parser. We do not pull in PyYAML — the
frontmatter we read is single-line ``key: value`` pairs and we want the
parse to be deterministic and easy to audit.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from governor.standing.types import canonical_json


@dataclass(frozen=True)
class PolicyArtifact:
    """A loaded, ratified policy artifact.

    ``content_hash`` is the SHA-256 of the file bytes (the on-disk
    artifact is the policy_declaration). ``frontmatter`` carries
    ``policy_artifact_id``, ``ontology_version``, ``ratifier``, etc.
    """

    policy_artifact_id: str
    ontology_version: str
    ratified_at: str
    ratifier: str
    supersedes: str | None
    content_hash: str
    source_path: str
    frontmatter: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "policy_artifact_id": self.policy_artifact_id,
            "ontology_version": self.ontology_version,
            "ratified_at": self.ratified_at,
            "ratifier": self.ratifier,
            "supersedes": self.supersedes,
            "content_hash": self.content_hash,
            "source_path": self.source_path,
        }


@dataclass
class ExceptionClassDeclaration:
    """An entry in the exception-class registry (Q3).

    Initial registry is empty per the ratified Q3 decision. When a
    declaration is added it must carry the six required fields per Q3
    §"Required fields per exception-class policy_declaration".
    """

    exception_class: str
    allowed_source_standing: str
    allowed_target_standing: str
    required_parent_evidence: tuple[str, ...]
    scope_limits: tuple[str, ...]
    expiry_or_review_date: str
    declared_by: str  # the policy_artifact_id that introduced this class

    def to_dict(self) -> dict[str, Any]:
        return {
            "exception_class": self.exception_class,
            "allowed_source_standing": self.allowed_source_standing,
            "allowed_target_standing": self.allowed_target_standing,
            "required_parent_evidence": list(self.required_parent_evidence),
            "scope_limits": list(self.scope_limits),
            "expiry_or_review_date": self.expiry_or_review_date,
            "declared_by": self.declared_by,
        }


@dataclass
class PolicyRegistry:
    """In-memory snapshot of ratified policy artifacts."""

    artifacts: dict[str, PolicyArtifact] = field(default_factory=dict)
    exception_classes: dict[str, ExceptionClassDeclaration] = field(default_factory=dict)
    ontology_versions: set[str] = field(default_factory=set)

    def add(self, artifact: PolicyArtifact) -> None:
        self.artifacts[artifact.policy_artifact_id] = artifact
        self.ontology_versions.add(artifact.ontology_version)

    def get(self, policy_artifact_id: str) -> PolicyArtifact | None:
        return self.artifacts.get(policy_artifact_id)

    def has(self, policy_artifact_id: str) -> bool:
        return policy_artifact_id in self.artifacts

    def has_ontology_version(self, version: str) -> bool:
        return version in self.ontology_versions

    def add_exception_class(self, decl: ExceptionClassDeclaration) -> None:
        self.exception_classes[decl.exception_class] = decl

    def get_exception_class(
        self, name: str
    ) -> ExceptionClassDeclaration | None:
        return self.exception_classes.get(name)

    def registry_hash(self) -> str:
        """Content hash of the loaded registry, for Q4 policy_registry_hash.

        Order-independent: artifacts and exception classes are sorted by
        id before hashing so the value is stable across load order.
        """

        snapshot = {
            "artifacts": [
                self.artifacts[k].to_dict()
                for k in sorted(self.artifacts.keys())
            ],
            "exception_classes": [
                self.exception_classes[k].to_dict()
                for k in sorted(self.exception_classes.keys())
            ],
        }
        return f"sha256:{hashlib.sha256(canonical_json(snapshot)).hexdigest()}"


# =============================================================================
# Loader
# =============================================================================


def _parse_frontmatter(text: str) -> tuple[dict[str, Any], str] | None:
    """Parse YAML-style ``---\\n...---\\n`` frontmatter.

    Returns ``(frontmatter_dict, body)`` or ``None`` if the file has no
    frontmatter block.
    """

    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return None
    # Find the closing ``---``.
    rest = text.split("\n", 1)[1] if text.startswith("---\n") else text.split("\r\n", 1)[1]
    end = rest.find("\n---\n")
    if end < 0:
        end = rest.find("\r\n---\r\n")
    if end < 0:
        return None
    front_block = rest[:end]
    body = rest[end:].split("\n", 2)[-1] if "---\n" in rest[end:] else ""
    fm: dict[str, Any] = {}
    for line in front_block.splitlines():
        line = line.rstrip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "null" or value == "":
            fm[key] = None
        else:
            # Strip optional surrounding quotes.
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            fm[key] = value
    return fm, body


def _file_content_hash(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def load_decisions_directory(
    decisions_dir: str | os.PathLike[str],
) -> PolicyRegistry:
    """Load every ratified policy_declaration under ``decisions_dir``.

    Files without a ``policy_artifact_id`` in frontmatter (e.g. README)
    are skipped. Files with ``status: candidate`` are skipped — only
    ``status: ratified`` artifacts enter the registry.
    """

    registry = PolicyRegistry()
    base = Path(decisions_dir)
    if not base.is_dir():
        return registry
    for entry in sorted(base.iterdir()):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        text = entry.read_text(encoding="utf-8")
        parsed = _parse_frontmatter(text)
        if parsed is None:
            continue
        fm, _body = parsed
        policy_artifact_id = fm.get("policy_artifact_id")
        if not policy_artifact_id:
            continue
        if fm.get("status") != "ratified":
            continue
        artifact = PolicyArtifact(
            policy_artifact_id=str(policy_artifact_id),
            ontology_version=str(fm.get("ontology_version") or ""),
            ratified_at=str(fm.get("ratified_at") or ""),
            ratifier=str(fm.get("ratifier") or ""),
            supersedes=(
                None
                if fm.get("supersedes") is None
                else str(fm.get("supersedes"))
            ),
            content_hash=_file_content_hash(entry),
            source_path=str(entry),
            frontmatter=dict(fm),
        )
        registry.add(artifact)
    return registry
