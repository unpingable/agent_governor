# SPDX-License-Identifier: Apache-2.0
"""
Context Manifest: prompt assembly as a governed artifact.

Phase 1 — instrument-only. Build a manifest during prompt assembly,
emit it as a side artifact, make it inspectable via CLI. No enforcement.

Three identity kinds:
  - prompt_hash:    H(final system prompt bytes). Pure content identity.
  - manifest_hash:  H(canonical_json(manifest minus volatile fields)).
                    Content-addressed. Excludes created_at and build_id.
  - build_id:       UUID for the *occurrence* of a build. Event identity.
                    Lets you say "this exact build happened at time T"
                    even when content repeats.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

MANIFEST_SCHEMA_VERSION = 1
HASH_ALG = "sha256"

VALID_REGION_KINDS: frozenset[str] = frozenset({
    "mode_base", "mode_anchors", "tool_policy",
    "compaction_summary", "system_footer", "other",
})

MUTABILITY_FROZEN = "frozen"
MUTABILITY_PROTECTED = "protected"
MUTABILITY_MUTABLE = "mutable"
_VALID_MUTABILITIES = frozenset({MUTABILITY_FROZEN, MUTABILITY_PROTECTED, MUTABILITY_MUTABLE})

STORE_FULL = "full"
STORE_HASH_ONLY = "hash_only"
STORE_REDACTED = "redacted"
_VALID_STORE_MODES = frozenset({STORE_FULL, STORE_HASH_ONLY, STORE_REDACTED})

VALID_CAPABILITIES: frozenset[str] = frozenset({"read", "write", "append"})


# ── Hashing helpers ──────────────────────────────────────────────────────────

def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _canonical_json(obj: Any) -> bytes:
    """Deterministic JSON: sorted keys, compact, ASCII-safe."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


# ── Region metadata lookup ───────────────────────────────────────────────────

_REGION_DEFAULTS: dict[str, dict[str, Any]] = {
    "mode_base": {
        "source_class": "generated",
        "sensitivity": "none",
        "mutability": MUTABILITY_FROZEN,
        "capabilities": frozenset({"read"}),
        "store_mode": STORE_HASH_ONLY,
    },
    "mode_anchors": {
        "source_class": "repo",
        "sensitivity": "none",
        "mutability": MUTABILITY_PROTECTED,
        "capabilities": frozenset({"read"}),
        "store_mode": STORE_HASH_ONLY,
    },
    "tool_policy": {
        "source_class": "generated",
        "sensitivity": "none",
        "mutability": MUTABILITY_FROZEN,
        "capabilities": frozenset({"read"}),
        "store_mode": STORE_HASH_ONLY,
    },
    "compaction_summary": {
        "source_class": "generated",
        "sensitivity": "internal",
        "mutability": MUTABILITY_MUTABLE,
        "capabilities": frozenset({"read", "append"}),
        "store_mode": STORE_HASH_ONLY,
    },
    "system_footer": {
        "source_class": "generated",
        "sensitivity": "none",
        "mutability": MUTABILITY_FROZEN,
        "capabilities": frozenset({"read"}),
        "store_mode": STORE_HASH_ONLY,
    },
    "other": {
        "source_class": "unknown",
        "sensitivity": "unknown",
        "mutability": MUTABILITY_MUTABLE,
        "capabilities": frozenset({"read", "write"}),
        "store_mode": STORE_HASH_ONLY,
    },
}


# ── ContextRegion ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContextRegion:
    """One region of the assembled system prompt."""

    region_id: str
    kind: str
    content_hash: str
    content_len: int
    source_class: str
    sensitivity: str
    capabilities: frozenset[str]
    mutability: str
    store_mode: str
    rationale: str
    content_preview: str | None = None
    inputs_digest: str | None = None
    parent_region_id: str | None = None

    def __post_init__(self) -> None:
        if self.kind not in VALID_REGION_KINDS:
            raise ValueError(
                f"Invalid region kind {self.kind!r}; "
                f"valid: {sorted(VALID_REGION_KINDS)}"
            )
        from .provenance_labels import VALID_SOURCE_CLASSES, VALID_SENSITIVITIES
        if self.source_class not in VALID_SOURCE_CLASSES:
            raise ValueError(
                f"Invalid source_class {self.source_class!r}; "
                f"valid: {sorted(VALID_SOURCE_CLASSES)}"
            )
        if self.sensitivity not in VALID_SENSITIVITIES:
            raise ValueError(
                f"Invalid sensitivity {self.sensitivity!r}; "
                f"valid: {sorted(VALID_SENSITIVITIES)}"
            )
        if self.mutability not in _VALID_MUTABILITIES:
            raise ValueError(
                f"Invalid mutability {self.mutability!r}; "
                f"valid: {sorted(_VALID_MUTABILITIES)}"
            )
        if self.store_mode not in _VALID_STORE_MODES:
            raise ValueError(
                f"Invalid store_mode {self.store_mode!r}; "
                f"valid: {sorted(_VALID_STORE_MODES)}"
            )
        if not self.capabilities <= VALID_CAPABILITIES:
            raise ValueError(
                f"Invalid capabilities {self.capabilities!r}; "
                f"valid: {sorted(VALID_CAPABILITIES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "region_id": self.region_id,
            "kind": self.kind,
            "content_hash": self.content_hash,
            "content_len": self.content_len,
            "source_class": self.source_class,
            "sensitivity": self.sensitivity,
            "capabilities": sorted(self.capabilities),
            "mutability": self.mutability,
            "store_mode": self.store_mode,
            "rationale": self.rationale,
        }
        if self.content_preview is not None:
            d["content_preview"] = self.content_preview
        if self.inputs_digest is not None:
            d["inputs_digest"] = self.inputs_digest
        if self.parent_region_id is not None:
            d["parent_region_id"] = self.parent_region_id
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextRegion:
        caps = data.get("capabilities", [])
        return cls(
            region_id=data["region_id"],
            kind=data["kind"],
            content_hash=data["content_hash"],
            content_len=data["content_len"],
            source_class=data["source_class"],
            sensitivity=data["sensitivity"],
            capabilities=frozenset(caps),
            mutability=data["mutability"],
            store_mode=data["store_mode"],
            rationale=data["rationale"],
            content_preview=data.get("content_preview"),
            inputs_digest=data.get("inputs_digest"),
            parent_region_id=data.get("parent_region_id"),
        )


# ── ContextManifest ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ContextManifest:
    """Manifest of what went into a system prompt build."""

    manifest_version: int
    hash_alg: str
    build_id: str
    created_at: str
    mode: str
    regions: tuple[ContextRegion, ...]
    prompt_hash: str

    # Identity / correlation
    session_id: str | None = None
    tenant_id: str | None = None
    principal_id: str | None = None

    # Build provenance
    governor_version: str | None = None
    builder_id: str = "governor_hooks"

    # Chain
    prev_manifest_hash: str | None = None
    prev_build_id: str | None = None

    # Reserved for future
    message_set_hash: str | None = None
    signature: str | None = None
    signing_key_id: str | None = None

    @property
    def manifest_hash(self) -> str:
        """H(canonical_json(hashable fields)).

        Excludes: created_at, build_id, signature, signing_key_id.
        Includes: everything else.
        """
        hashable = {
            "manifest_version": self.manifest_version,
            "hash_alg": self.hash_alg,
            "mode": self.mode,
            "regions": [r.to_dict() for r in self.regions],
            "prompt_hash": self.prompt_hash,
            "session_id": self.session_id,
            "tenant_id": self.tenant_id,
            "principal_id": self.principal_id,
            "governor_version": self.governor_version,
            "builder_id": self.builder_id,
            "prev_manifest_hash": self.prev_manifest_hash,
            "prev_build_id": self.prev_build_id,
            "message_set_hash": self.message_set_hash,
        }
        return _sha256_hex(_canonical_json(hashable))

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "manifest_version": self.manifest_version,
            "hash_alg": self.hash_alg,
            "build_id": self.build_id,
            "created_at": self.created_at,
            "mode": self.mode,
            "regions": [r.to_dict() for r in self.regions],
            "prompt_hash": self.prompt_hash,
            "manifest_hash": self.manifest_hash,
        }
        for key in (
            "session_id", "tenant_id", "principal_id",
            "governor_version", "builder_id",
            "prev_manifest_hash", "prev_build_id",
            "message_set_hash", "signature", "signing_key_id",
        ):
            val = getattr(self, key)
            if val is not None:
                d[key] = val
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextManifest:
        regions = tuple(
            ContextRegion.from_dict(r) for r in data.get("regions", [])
        )
        return cls(
            manifest_version=data["manifest_version"],
            hash_alg=data["hash_alg"],
            build_id=data["build_id"],
            created_at=data["created_at"],
            mode=data["mode"],
            regions=regions,
            prompt_hash=data["prompt_hash"],
            session_id=data.get("session_id"),
            tenant_id=data.get("tenant_id"),
            principal_id=data.get("principal_id"),
            governor_version=data.get("governor_version"),
            builder_id=data.get("builder_id", "governor_hooks"),
            prev_manifest_hash=data.get("prev_manifest_hash"),
            prev_build_id=data.get("prev_build_id"),
            message_set_hash=data.get("message_set_hash"),
            signature=data.get("signature"),
            signing_key_id=data.get("signing_key_id"),
        )


# ── build_manifest() ────────────────────────────────────────────────────────

def _make_region(
    region_id: str,
    kind: str,
    text: str,
    *,
    rationale: str = "",
    inputs_digest: str | None = None,
    parent_region_id: str | None = None,
) -> ContextRegion:
    """Build a ContextRegion from text and kind, using the lookup table."""
    defaults = _REGION_DEFAULTS.get(kind, _REGION_DEFAULTS["other"])
    text_bytes = text.encode("utf-8")
    content_hash = _sha256_hex(text_bytes)
    content_len = len(text_bytes)
    sensitivity = defaults["sensitivity"]

    content_preview: str | None = None
    if sensitivity == "none":
        content_preview = text[:80]

    return ContextRegion(
        region_id=region_id,
        kind=kind,
        content_hash=content_hash,
        content_len=content_len,
        source_class=defaults["source_class"],
        sensitivity=sensitivity,
        capabilities=defaults["capabilities"],
        mutability=defaults["mutability"],
        store_mode=defaults["store_mode"],
        rationale=rationale,
        content_preview=content_preview,
        inputs_digest=inputs_digest,
        parent_region_id=parent_region_id,
    )


def _get_governor_version() -> str | None:
    """Best-effort governor version from installed package metadata."""
    try:
        from importlib.metadata import version
        return version("agent-gov")
    except Exception:
        return None


def build_manifest(
    *,
    mode: str,
    regions: list[tuple[str, str, str]],
    session_id: str | None = None,
    tenant_id: str | None = None,
    principal_id: str | None = None,
    prev_manifest_hash: str | None = None,
    prev_build_id: str | None = None,
    builder_id: str = "governor_hooks",
    build_id: str | None = None,
    created_at: str | None = None,
) -> ContextManifest:
    """Build a ContextManifest from region tuples.

    Each region tuple: (region_id, kind, text).
    prompt_hash = H(all region texts joined with \\n\\n).
    """
    built_regions: list[ContextRegion] = []
    texts: list[str] = []

    for region_id, kind, text in regions:
        built_regions.append(_make_region(region_id, kind, text))
        texts.append(text)

    prompt_bytes = "\n\n".join(texts).encode("utf-8")
    prompt_hash = _sha256_hex(prompt_bytes)

    return ContextManifest(
        manifest_version=MANIFEST_SCHEMA_VERSION,
        hash_alg=HASH_ALG,
        build_id=build_id or uuid.uuid4().hex[:16],
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        mode=mode,
        regions=tuple(built_regions),
        prompt_hash=prompt_hash,
        session_id=session_id,
        tenant_id=tenant_id,
        principal_id=principal_id,
        governor_version=_get_governor_version(),
        builder_id=builder_id,
        prev_manifest_hash=prev_manifest_hash,
        prev_build_id=prev_build_id,
    )


# ── Gate receipt emission ────────────────────────────────────────────────────

def emit_build_receipt(manifest: ContextManifest) -> Any:
    """Emit a gate receipt for the context build (verdict=observe).

    Evidence contains hashes only — never region bodies.
    Returns the GateReceipt or None on failure.
    """
    from .gate_receipt import create_receipt, VERDICT_OBSERVE

    evidence = {
        "manifest_hash": manifest.manifest_hash,
        "prompt_hash": manifest.prompt_hash,
        "region_count": len(manifest.regions),
        "regions": [
            {
                "region_id": r.region_id,
                "kind": r.kind,
                "content_hash": r.content_hash,
                "content_len": r.content_len,
            }
            for r in manifest.regions
        ],
    }

    subject_bytes = _canonical_json(manifest.to_dict())
    config = {"manifest_version": MANIFEST_SCHEMA_VERSION}

    return create_receipt(
        gate="context_build",
        verdict=VERDICT_OBSERVE,
        subject_kind="context_manifest",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence,
        gate_config=config,
    )


def emit_build_failure_receipt(
    *,
    build_id: str,
    mode: str,
    exc_type: str,
    exc_message: str,
    session_id: str | None = None,
) -> Any:
    """Emit a gate receipt for a failed context build.

    Receipts survive; stderr warnings don't. This ensures failures
    are visible in the audit trail even in CI.
    """
    from .gate_receipt import create_receipt, VERDICT_WARN

    evidence = {
        "build_id": build_id,
        "mode": mode,
        "exc_type": exc_type,
        "exc_message": exc_message,
    }
    if session_id:
        evidence["session_id"] = session_id

    subject_bytes = _canonical_json({"build_id": build_id, "failed": True})
    config = {"manifest_version": MANIFEST_SCHEMA_VERSION}

    return create_receipt(
        gate="context_build_failed",
        verdict=VERDICT_WARN,
        subject_kind="context_manifest_failure",
        subject_bytes=subject_bytes,
        evidence_bundle=evidence,
        gate_config=config,
    )


# ── ManifestStore ────────────────────────────────────────────────────────────

class ManifestStore:
    """JSONL persistence for context manifests."""

    def __init__(self, gov_dir: Path):
        self.dir = gov_dir / "manifests"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path = self.dir / "context_manifests.jsonl"

    def append(self, manifest: ContextManifest) -> None:
        """Append manifest with fcntl.flock for safe concurrent writes."""
        line = json.dumps(manifest.to_dict(), sort_keys=True) + "\n"
        with open(self.path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
                f.flush()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def latest(self) -> ContextManifest | None:
        """Return the most recently appended manifest, or None."""
        manifests = self.query(limit=1)
        return manifests[0] if manifests else None

    def query(
        self,
        *,
        limit: int = 10,
        build_id: str | None = None,
        manifest_hash_prefix: str | None = None,
    ) -> list[ContextManifest]:
        """Query manifests, newest first."""
        if not self.path.exists():
            return []

        results: list[ContextManifest] = []
        lines = self.path.read_text().splitlines()

        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            m = ContextManifest.from_dict(data)

            if build_id is not None and m.build_id != build_id:
                continue
            if manifest_hash_prefix is not None:
                if not m.manifest_hash.startswith(manifest_hash_prefix):
                    continue

            results.append(m)
            if len(results) >= limit:
                break

        return results
