# SPDX-License-Identifier: Apache-2.0
"""
Provenance labels for tool outputs — lightweight taint tracking.

Labels are metadata, not policy. They answer "where did this data come from?"
so downstream gates (egress, chain, evidence) can make informed decisions.

Design authority: specs/gaps/GOV_PRIM_PROV_001.md

Principles (from ChatGPT review):
  - Typed, minimal, deterministic
  - Assignment rules explicit and testable
  - "DNS records, not narrative"

v2: Label schema + mechanical assignment + simple taint propagation.
v3: Cross-session tracking, declassification, formal lattice.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# ── Constants ────────────────────────────────────────────────────────────────

LABEL_SCHEMA_VERSION = "provenance-label-v1"

# Source classes — where the data came from
SOURCE_REPO = "repo"
SOURCE_EMAIL = "email"
SOURCE_WEB = "web"
SOURCE_SECRET_STORE = "secret_store"
SOURCE_USER_INPUT = "user_input"
SOURCE_GENERATED = "generated"
SOURCE_UNKNOWN = "unknown"

VALID_SOURCE_CLASSES = frozenset({
    SOURCE_REPO, SOURCE_EMAIL, SOURCE_WEB, SOURCE_SECRET_STORE,
    SOURCE_USER_INPUT, SOURCE_GENERATED, SOURCE_UNKNOWN,
})

# Sensitivity hints — how sensitive the data might be
SENSITIVITY_NONE = "none"
SENSITIVITY_INTERNAL = "internal"
SENSITIVITY_SECRET_CANDIDATE = "secret_candidate"
SENSITIVITY_UNKNOWN = "unknown"

VALID_SENSITIVITIES = frozenset({
    SENSITIVITY_NONE, SENSITIVITY_INTERNAL,
    SENSITIVITY_SECRET_CANDIDATE, SENSITIVITY_UNKNOWN,
})

# Ordered from lowest to highest for propagation
_SENSITIVITY_ORDER = {
    SENSITIVITY_NONE: 0,
    SENSITIVITY_INTERNAL: 1,
    SENSITIVITY_UNKNOWN: 2,
    SENSITIVITY_SECRET_CANDIDATE: 3,
}

# Default sensitivity per source class
_SOURCE_DEFAULTS: dict[str, str] = {
    SOURCE_REPO: SENSITIVITY_INTERNAL,
    SOURCE_EMAIL: SENSITIVITY_INTERNAL,
    SOURCE_WEB: SENSITIVITY_NONE,
    SOURCE_SECRET_STORE: SENSITIVITY_SECRET_CANDIDATE,
    SOURCE_USER_INPUT: SENSITIVITY_NONE,
    SOURCE_GENERATED: SENSITIVITY_NONE,
    SOURCE_UNKNOWN: SENSITIVITY_UNKNOWN,
}


# ── ProvenanceLabel ──────────────────────────────────────────────────────────

@dataclass(frozen=True)
class ProvenanceLabel:
    """Provenance metadata for a tool output.

    Immutable value type. Does NOT affect receipt identity hash —
    labels are annotation, not identity.
    """

    source_class: str        # VALID_SOURCE_CLASSES
    sensitivity_hint: str    # VALID_SENSITIVITIES
    tool_id: str             # which tool produced this output
    timestamp: str           # ISO 8601 UTC
    content_hash: str        # H(output_content)[:16] — for dedup/tracking only

    def __post_init__(self) -> None:
        if self.source_class not in VALID_SOURCE_CLASSES:
            raise ValueError(
                f"Invalid source_class {self.source_class!r}. "
                f"Valid: {sorted(VALID_SOURCE_CLASSES)}"
            )
        if self.sensitivity_hint not in VALID_SENSITIVITIES:
            raise ValueError(
                f"Invalid sensitivity_hint {self.sensitivity_hint!r}. "
                f"Valid: {sorted(VALID_SENSITIVITIES)}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": LABEL_SCHEMA_VERSION,
            "source_class": self.source_class,
            "sensitivity_hint": self.sensitivity_hint,
            "tool_id": self.tool_id,
            "timestamp": self.timestamp,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> ProvenanceLabel:
        return cls(
            source_class=d["source_class"],
            sensitivity_hint=d["sensitivity_hint"],
            tool_id=d["tool_id"],
            timestamp=d["timestamp"],
            content_hash=d["content_hash"],
        )


# ── Sensitivity propagation ─────────────────────────────────────────────────

def max_sensitivity(labels: list[ProvenanceLabel]) -> str:
    """Conservative propagation: return the highest sensitivity across labels.

    If model transforms multiple labeled inputs, the output inherits
    the highest sensitivity of all inputs.  Empty list → "none".
    """
    if not labels:
        return SENSITIVITY_NONE
    return max(
        (lbl.sensitivity_hint for lbl in labels),
        key=lambda s: _SENSITIVITY_ORDER.get(s, 0),
    )


# ── Secret path patterns ────────────────────────────────────────────────────

# File path patterns that suggest secret/credential content.
# Reuses the approach from receipt_kernel/redact.py — conservative matching.
_SECRET_PATH_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)\.env$"),
    re.compile(r"(?i)\.env\.[a-z]+$"),          # .env.local, .env.production
    re.compile(r"(?i)credentials"),
    re.compile(r"(?i)secrets?\."),               # secrets.yaml, secret.json
    re.compile(r"(?i)_key\.[a-z]+$"),            # api_key.txt, private_key.pem
    re.compile(r"(?i)\.pem$"),
    re.compile(r"(?i)\.key$"),
    re.compile(r"(?i)\.p12$"),
    re.compile(r"(?i)\.pfx$"),
    re.compile(r"(?i)\.keystore$"),
    re.compile(r"(?i)id_rsa"),
    re.compile(r"(?i)id_ed25519"),
    re.compile(r"(?i)\.htpasswd"),
    re.compile(r"(?i)token[s]?\.[a-z]+$"),       # tokens.json
    re.compile(r"(?i)auth[a-z]*\.[a-z]+$"),      # auth.yaml, authentication.json
]

# Internal hostname patterns (not public web)
_INTERNAL_URL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?i)^https?://localhost"),
    re.compile(r"(?i)^https?://127\."),
    re.compile(r"(?i)^https?://10\."),
    re.compile(r"(?i)^https?://172\.(1[6-9]|2[0-9]|3[01])\."),
    re.compile(r"(?i)^https?://192\.168\."),
    re.compile(r"(?i)^https?://[^/]+\.internal"),
    re.compile(r"(?i)^https?://[^/]+\.corp"),
    re.compile(r"(?i)^https?://[^/]+\.local"),
]


def _is_secret_path(path: str) -> bool:
    """Check if a file path matches secret patterns."""
    return any(p.search(path) for p in _SECRET_PATH_PATTERNS)


def _is_internal_url(url: str) -> bool:
    """Check if a URL matches internal/private network patterns."""
    return any(p.match(url) for p in _INTERNAL_URL_PATTERNS)


def _content_fingerprint(content: str | bytes) -> str:
    """Dedup fingerprint of content. NOT canonical content-addressing."""
    if isinstance(content, str):
        content = content.encode("utf-8")
    return hashlib.sha256(content).hexdigest()[:16]


# ── Tool-to-source-class mapping ────────────────────────────────────────────

# Known tool IDs → source class. Extend as tools are registered.
_TOOL_SOURCE_MAP: dict[str, str] = {
    # File operations
    "read_file": SOURCE_REPO,
    "Read": SOURCE_REPO,
    "file_read": SOURCE_REPO,
    "cat": SOURCE_REPO,
    "head": SOURCE_REPO,
    "tail": SOURCE_REPO,

    # Web operations
    "web_fetch": SOURCE_WEB,
    "WebFetch": SOURCE_WEB,
    "curl": SOURCE_WEB,
    "http_get": SOURCE_WEB,
    "web_search": SOURCE_WEB,
    "WebSearch": SOURCE_WEB,

    # Shell / command execution
    "bash": SOURCE_REPO,         # commands operate on repo
    "Bash": SOURCE_REPO,
    "shell": SOURCE_REPO,
    "exec": SOURCE_REPO,

    # Editor operations
    "edit_file": SOURCE_REPO,
    "Edit": SOURCE_REPO,
    "write_file": SOURCE_GENERATED,
    "Write": SOURCE_GENERATED,

    # User interaction
    "ask_user": SOURCE_USER_INPUT,
    "AskUserQuestion": SOURCE_USER_INPUT,
    "user_prompt": SOURCE_USER_INPUT,
}


# ── LabelAssigner ────────────────────────────────────────────────────────────

class LabelAssigner:
    """Mechanical, rule-based provenance label assignment.

    Deterministic: same (tool_id, args) → same label (modulo timestamp).
    No ML, no heuristics beyond pattern matching. DNS records, not narrative.
    """

    def __init__(
        self,
        *,
        extra_tool_map: dict[str, str] | None = None,
        extra_secret_patterns: list[re.Pattern[str]] | None = None,
    ) -> None:
        self._tool_map = dict(_TOOL_SOURCE_MAP)
        if extra_tool_map:
            self._tool_map.update(extra_tool_map)

        self._secret_patterns = list(_SECRET_PATH_PATTERNS)
        if extra_secret_patterns:
            self._secret_patterns.extend(extra_secret_patterns)

    def assign(
        self,
        tool_id: str,
        content: str | bytes,
        *,
        file_path: str | None = None,
        url: str | None = None,
        timestamp: str | None = None,
    ) -> ProvenanceLabel:
        """Assign a provenance label to a tool output.

        Args:
            tool_id: Which tool produced this output.
            content: The tool output content (for fingerprinting).
            file_path: File path if applicable (for sensitivity detection).
            url: URL if applicable (for internal network detection).
            timestamp: Override timestamp (ISO 8601 UTC).

        Returns:
            A frozen ProvenanceLabel.
        """
        source_class = self._classify_source(tool_id)
        sensitivity = self._classify_sensitivity(source_class, file_path, url)

        return ProvenanceLabel(
            source_class=source_class,
            sensitivity_hint=sensitivity,
            tool_id=tool_id,
            timestamp=timestamp or datetime.now(timezone.utc).isoformat(),
            content_hash=_content_fingerprint(content),
        )

    def _classify_source(self, tool_id: str) -> str:
        """Map tool_id to source class. Unknown tools → SOURCE_UNKNOWN."""
        return self._tool_map.get(tool_id, SOURCE_UNKNOWN)

    def _classify_sensitivity(
        self,
        source_class: str,
        file_path: str | None,
        url: str | None,
    ) -> str:
        """Determine sensitivity hint from source class + context.

        Sensitivity escalation only — never downgrades from source default.
        """
        default = _SOURCE_DEFAULTS.get(source_class, SENSITIVITY_UNKNOWN)

        # File path matching (escalates to secret_candidate if match)
        if file_path and any(p.search(file_path) for p in self._secret_patterns):
            return SENSITIVITY_SECRET_CANDIDATE

        # URL matching (escalates to internal if match)
        if url and _is_internal_url(url):
            return max(
                default, SENSITIVITY_INTERNAL,
                key=lambda s: _SENSITIVITY_ORDER.get(s, 0),
            )

        return default
