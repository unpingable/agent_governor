# SPDX-License-Identifier: Apache-2.0
"""
Egress Gate: outbound data-flow policy gate.

Evaluates outbound data flow against policy before it leaves the trust
boundary.  Policy bridge: classify -> populate existing policy types ->
evaluate -> emit gate receipt.

Design:
- Metadata-first: provenance labels + paths primary; content scan opt-in
- Strict external default: only UNCLASSIFIED+allowlisted to external
- No USER_REQUESTED bypass: justification recorded, doesn't change verdict
- Receipt redaction: hashes + classes only, no raw destinations/content
- Classifier monotone: never downgrades; label > path > regex > default
- Stateless, observe-only: no daemon hooks, no accumulated state
"""

from __future__ import annotations

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
from urllib.parse import urlparse

from governor.gate_receipt import (
    GateReceiptSystem,
    canonical_json,
    content_hash,
    make_timing,
)
from governor.policy_engine import (
    Obligation,
    ObligationKind,
    PayloadClass,
    PolicyVerdict,
)
from governor.provenance_labels import (
    ProvenanceLabel,
    _INTERNAL_URL_PATTERNS,
    _SECRET_PATH_PATTERNS,
    max_sensitivity,
)


# ---------------------------------------------------------------------------
# Gate-specific types
# ---------------------------------------------------------------------------

class JustificationCode(str, Enum):
    API_CALL = "api_call"
    WEBHOOK = "webhook"
    ERROR_REPORT = "error_report"
    USER_REQUESTED = "user_requested"
    AUTOMATED = "automated"


@dataclass(frozen=True)
class EgressRequest:
    destination_ref: str
    payload_size: int
    provenance_labels: list[ProvenanceLabel]
    justification: JustificationCode
    tool_id: str
    content_probe: str | bytes | None = None


@dataclass
class EgressResult:
    verdict: PolicyVerdict
    matched_rule: str | None
    payload_class: PayloadClass
    destination_class: str
    obligations: list[Obligation]
    warnings: list[str]
    provenance_labels: list[ProvenanceLabel]

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "matched_rule": self.matched_rule,
            "payload_class": self.payload_class.value,
            "destination_class": self.destination_class,
            "obligations": [o.to_dict() for o in self.obligations],
            "warnings": list(self.warnings),
            "provenance_labels": [l.to_dict() for l in self.provenance_labels],
        }


@dataclass(frozen=True)
class EgressGateConfig:
    strict: bool = True
    allowed_external_hosts: frozenset[str] = field(default_factory=frozenset)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strict": self.strict,
            "allowed_external_hosts": sorted(self.allowed_external_hosts),
        }


# ---------------------------------------------------------------------------
# Sensitivity -> PayloadClass mapping
# ---------------------------------------------------------------------------

_SENSITIVITY_TO_PAYLOAD: dict[str, PayloadClass] = {
    "secret_candidate": PayloadClass.SECRET_CANDIDATE,
    "internal": PayloadClass.REPO_SOURCE,
    "unknown": PayloadClass.UNKNOWN,
    "none": PayloadClass.UNCLASSIFIED,
}

# Reuse receipt_kernel secret patterns for content scanning
_CONTENT_SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("anthropic_api_key", re.compile(r"sk-ant-[a-zA-Z0-9_-]{20,}")),
    ("openai_api_key", re.compile(r"sk-[a-zA-Z0-9]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("aws_secret_key", re.compile(r"(?i)aws_secret_access_key\s*[=:]\s*\S+")),
    ("bearer_token", re.compile(r"(?i)bearer\s+[a-zA-Z0-9._\-]{20,}")),
    ("authorization_header", re.compile(r"(?i)authorization\s*[=:]\s*\S+")),
    ("password_field", re.compile(r'(?i)"?password"?\s*[=:]\s*"[^"]*"')),
    ("private_key_block", re.compile(r"-----BEGIN\s+(RSA\s+)?PRIVATE KEY-----")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}")),
    ("connection_string", re.compile(r"(?i)(mysql|postgres|mongodb|redis)://[^\s]+@[^\s]+")),
    ("generic_secret_assign", re.compile(r'(?i)(secret|token|key|apikey|api_key)\s*[=:]\s*"[^"]{16,}"')),
]

# Internal TLD patterns for destination classification
_INTERNAL_TLDS = frozenset({".local", ".internal", ".corp", ".localhost"})

# RFC 1918 / loopback patterns for bare IPs
_INTERNAL_IP_PREFIXES = ("127.", "10.", "192.168.")


# ---------------------------------------------------------------------------
# Destination Classifier
# ---------------------------------------------------------------------------

class DestinationClassifier:

    @staticmethod
    def classify(ref: str) -> tuple[str, str]:
        """Classify a destination reference.

        Returns (destination_class, normalized_host).
        destination_class: "internal" | "external" | "unknown"
        """
        if not ref or not ref.strip():
            return ("unknown", "")

        ref = ref.strip()

        # Try URL parse
        parsed = urlparse(ref)

        # urlparse treats "host:3000" as scheme=host, path=3000.
        # Detect: if scheme is present but netloc is empty and path looks
        # like a port or path, it's likely a bare host:port or hostname.
        has_real_scheme = bool(parsed.scheme) and bool(parsed.netloc)
        if not has_real_scheme:
            if ref.startswith("["):
                # IPv6 literal
                parsed = urlparse(f"tcp://{ref}")
            elif "://" not in ref:
                # Bare hostname, host:port, or IP
                parsed = urlparse(f"tcp://{ref}")
            # else: has scheme:// but empty netloc — leave as-is

        host = parsed.hostname or ""
        host = host.lower()

        # Strip brackets from IPv6
        if host.startswith("[") and host.endswith("]"):
            host = host[1:-1]

        if not host:
            return ("unknown", "")

        # Determine internal vs external
        is_internal = False

        # Loopback
        if host in ("localhost", "127.0.0.1", "::1"):
            is_internal = True
        # RFC 1918
        elif any(host.startswith(p) for p in _INTERNAL_IP_PREFIXES):
            is_internal = True
        elif host.startswith("172."):
            parts = host.split(".")
            if len(parts) >= 2:
                try:
                    second = int(parts[1])
                    if 16 <= second <= 31:
                        is_internal = True
                except ValueError:
                    pass
        # Internal TLDs
        elif any(host.endswith(tld) for tld in _INTERNAL_TLDS):
            is_internal = True

        dest_class = "internal" if is_internal else "external"
        return (dest_class, host)


# ---------------------------------------------------------------------------
# Payload Classifier
# ---------------------------------------------------------------------------

class PayloadClassifier:

    @staticmethod
    def classify(
        *,
        labels: list[ProvenanceLabel],
        file_path: str | None = None,
    ) -> PayloadClass:
        """Classify payload from provenance labels and optional path.

        Precedence (monotone, never downgrades):
        1. Provenance label sensitivity (max across all labels)
        2. Path-based classification (secret path patterns)
        3. Default -> UNCLASSIFIED
        """
        # 1. Label-based (highest authority)
        if labels:
            sens = max_sensitivity(labels)
            label_class = _SENSITIVITY_TO_PAYLOAD.get(sens, PayloadClass.UNCLASSIFIED)
        else:
            label_class = PayloadClass.UNCLASSIFIED

        # 2. Path-based
        path_class = PayloadClass.UNCLASSIFIED
        if file_path:
            for pat in _SECRET_PATH_PATTERNS:
                if pat.search(file_path):
                    path_class = PayloadClass.SECRET_CANDIDATE
                    break

        # Monotone: return max
        return _max_payload_class(label_class, path_class)

    @staticmethod
    def scan_content(content: str | bytes) -> PayloadClass | None:
        """Scan content for secret patterns. Returns upgrade or None."""
        if isinstance(content, bytes):
            try:
                text = content.decode("utf-8", errors="replace")
            except Exception:
                return None
        else:
            text = content

        for _name, pattern in _CONTENT_SECRET_PATTERNS:
            if pattern.search(text):
                return PayloadClass.SECRET_CANDIDATE
        return None


# PayloadClass severity ordering for monotone comparison
_PAYLOAD_CLASS_SEVERITY: dict[PayloadClass, int] = {
    PayloadClass.UNCLASSIFIED: 0,
    PayloadClass.REPO_SOURCE: 1,
    PayloadClass.PII_CANDIDATE: 2,
    PayloadClass.UNKNOWN: 2,
    PayloadClass.SECRET_CANDIDATE: 3,
}


def _max_payload_class(a: PayloadClass, b: PayloadClass) -> PayloadClass:
    sa = _PAYLOAD_CLASS_SEVERITY.get(a, 0)
    sb = _PAYLOAD_CLASS_SEVERITY.get(b, 0)
    return a if sa >= sb else b


# ---------------------------------------------------------------------------
# Egress Gate
# ---------------------------------------------------------------------------

# Rule IDs
_R1_SECRET_DENY = "R1_SECRET_DENY"
_R3_UNKNOWN_DEST = "R3_UNKNOWN_DEST"
_R5_ALLOWLISTED = "R5_ALLOWLISTED"
_R4_INTERNAL_ALLOW = "R4_INTERNAL_ALLOW"
_R2_SENSITIVE_EXTERNAL = "R2_SENSITIVE_EXTERNAL"
_R6_DEFAULT = "R6_DEFAULT"

_SENSITIVE_CLASSES = frozenset({
    PayloadClass.PII_CANDIDATE,
    PayloadClass.REPO_SOURCE,
    PayloadClass.UNKNOWN,
})


class EgressGate:

    def __init__(
        self,
        config: EgressGateConfig | None = None,
        receipt_system: GateReceiptSystem | None = None,
    ):
        self.config = config or EgressGateConfig()
        self.receipt_system = receipt_system

    def evaluate(self, request: EgressRequest) -> EgressResult:
        start_ns = time.monotonic_ns()

        # Classify
        dest_class, normalized_host = DestinationClassifier.classify(
            request.destination_ref
        )
        payload_class = PayloadClassifier.classify(
            labels=request.provenance_labels,
        )

        # Optional content probe (can only upgrade)
        if request.content_probe is not None:
            probe_result = PayloadClassifier.scan_content(request.content_probe)
            if probe_result is not None:
                payload_class = _max_payload_class(payload_class, probe_result)

        # Evaluate rules (first match wins)
        verdict, matched_rule, obligations, warnings = self._evaluate_rules(
            payload_class, dest_class, normalized_host,
        )

        end_ns = time.monotonic_ns()

        result = EgressResult(
            verdict=verdict,
            matched_rule=matched_rule,
            payload_class=payload_class,
            destination_class=dest_class,
            obligations=obligations,
            warnings=warnings,
            provenance_labels=list(request.provenance_labels),
        )

        # Emit receipt
        if self.receipt_system is not None:
            self._emit_receipt(
                request, result, normalized_host, start_ns, end_ns,
            )

        return result

    def _evaluate_rules(
        self,
        payload_class: PayloadClass,
        dest_class: str,
        normalized_host: str,
    ) -> tuple[PolicyVerdict, str | None, list[Obligation], list[str]]:
        # R1: secrets always blocked
        if payload_class == PayloadClass.SECRET_CANDIDATE:
            return (PolicyVerdict.BLOCK, _R1_SECRET_DENY, [], [])

        # R3: unknown destination blocked
        if dest_class == "unknown":
            return (
                PolicyVerdict.BLOCK,
                _R3_UNKNOWN_DEST,
                [Obligation(kind=ObligationKind.RESTRICT_DESTINATION.value)],
                [],
            )

        # R5: allowlisted external, UNCLASSIFIED only
        if (
            dest_class == "external"
            and payload_class == PayloadClass.UNCLASSIFIED
            and self._is_allowlisted(normalized_host)
        ):
            return (PolicyVerdict.PASS, _R5_ALLOWLISTED, [], [])

        # R4: internal, non-secret
        if dest_class == "internal" and payload_class != PayloadClass.SECRET_CANDIDATE:
            return (PolicyVerdict.PASS, _R4_INTERNAL_ALLOW, [], [])

        # R2: sensitive -> external
        if dest_class == "external" and payload_class in _SENSITIVE_CLASSES:
            return (
                PolicyVerdict.BLOCK,
                _R2_SENSITIVE_EXTERNAL,
                [Obligation(kind=ObligationKind.REQUIRE_PAYLOAD_CLASSIFICATION.value)],
                [],
            )

        # R6: default (unclassified -> non-allowlisted external)
        if self.config.strict:
            v = PolicyVerdict.BLOCK
        else:
            v = PolicyVerdict.WARN
        return (
            v,
            _R6_DEFAULT,
            [Obligation(kind=ObligationKind.REQUIRE_PAYLOAD_CLASSIFICATION.value)],
            [],
        )

    def _is_allowlisted(self, host: str) -> bool:
        if not host:
            return False
        for entry in self.config.allowed_external_hosts:
            if entry.startswith("."):
                # Suffix match
                if host == entry[1:] or host.endswith(entry):
                    return True
            else:
                # Exact match
                if host == entry:
                    return True
        return False

    def _emit_receipt(
        self,
        request: EgressRequest,
        result: EgressResult,
        normalized_host: str,
        start_ns: int,
        end_ns: int,
    ) -> None:
        dest_hash = hashlib.sha256(normalized_host.encode("utf-8")).hexdigest()

        subject_obj = {
            "destination_class": result.destination_class,
            "payload_class": result.payload_class.value,
            "payload_size": request.payload_size,
            "tool_id": request.tool_id,
            "justification": request.justification.value,
        }
        subject_bytes = canonical_json(subject_obj)

        evidence_bundle: dict[str, Any] = {
            "destination_hash": dest_hash,
            "destination_class": result.destination_class,
            "destination_hint": normalized_host.split(".")[0] if normalized_host else "",
            "payload_class": result.payload_class.value,
            "payload_size": request.payload_size,
            "matched_rule": result.matched_rule,
            "verdict": result.verdict.value,
            "obligations": [o.to_dict() for o in result.obligations],
            "provenance_label_summaries": [
                {
                    "source_class": label.source_class,
                    "sensitivity_hint": label.sensitivity_hint,
                }
                for label in request.provenance_labels
            ],
        }

        verdict_str = "pass" if result.verdict == PolicyVerdict.PASS else (
            "block" if result.verdict == PolicyVerdict.BLOCK else "warn"
        )

        self.receipt_system.emit(
            gate="egress_policy",
            verdict=verdict_str,
            subject_kind="egress_attempt",
            subject_bytes=subject_bytes,
            evidence_bundle=evidence_bundle,
            gate_config=self.config.to_dict(),
            timing=make_timing(start_ns, end_ns),
        )
