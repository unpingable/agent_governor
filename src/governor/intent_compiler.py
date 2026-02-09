"""
Intent Compiler — structured hypothesis-collapse for governance sessions.

One expensive model call proposes a structured decision space (branches with
confidence scores), then cheap deterministic UI interactions collapse it into a
concrete intent.  The compiler deterministically converts the collapsed form
into constraints + execution parameters.

Doctrine: Form structure freedom is proportional to blast radius.
  - Authoritative modes (governor/code) use templates only.
  - Non-authoritative modes (fiction/ideation) allow custom forms.

Spec: INTENT_COMPILER_SPEC.md (Phase 7 of AG2 build order)
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class IntentFormPolicy(str, Enum):
    """Mode-gated policy for form structure freedom."""

    TEMPLATE_ONLY = "template_only"          # governor, code — finite, auditable
    VALIDATED_CUSTOM = "validated_custom"     # research, nonfiction — model-proposed, validated
    CUSTOM_OK = "custom_ok"                  # fiction, ideation — user can build forms


class WidgetType(str, Enum):
    """Allowed widget types for intent forms."""

    SELECT_ONE = "select_one"
    SELECT_MANY = "select_many"
    SLIDER = "slider"
    TEXT_SHORT = "text_short"
    TEXT_LONG = "text_long"
    CONDITIONAL = "conditional"
    CONFIRMATION = "confirmation"


class EscapeClassification(str, Enum):
    """Classification for 'Other' escape hatch responses."""

    SCHEMA_VIOLATION = "schema_violation"
    NEW_CONSTRAINT = "new_constraint"
    WAIVER_CANDIDATE = "waiver_candidate"
    CLARIFICATION_NEEDED = "clarification_needed"


# ---------------------------------------------------------------------------
# Core Dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FieldOption:
    """An option within a SELECT_ONE or SELECT_MANY field."""

    value: str
    label: str
    confidence: float = 0.0     # model's confidence this is the right choice
    branch_id: str = ""         # link to hypothesis branch

    def to_dict(self) -> dict[str, Any]:
        return {
            "value": self.value,
            "label": self.label,
            "confidence": self.confidence,
            "branch_id": self.branch_id,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FieldOption:
        return cls(
            value=d["value"],
            label=d["label"],
            confidence=d.get("confidence", 0.0),
            branch_id=d.get("branch_id", ""),
        )


@dataclass
class FormField:
    """A single field in an intent form."""

    field_id: str
    widget: WidgetType
    label: str
    options: list[FieldOption] | None = None     # for select_one/select_many
    range: tuple[float, float] | None = None     # for slider
    default: Any = None
    required: bool = True
    depends_on: str | None = None                # conditional rendering
    help_text: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "field_id": self.field_id,
            "widget": self.widget.value,
            "label": self.label,
            "required": self.required,
            "help_text": self.help_text,
        }
        if self.options is not None:
            d["options"] = [o.to_dict() for o in self.options]
        if self.range is not None:
            d["range"] = list(self.range)
        if self.default is not None:
            d["default"] = self.default
        if self.depends_on is not None:
            d["depends_on"] = self.depends_on
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> FormField:
        options = None
        if "options" in d:
            options = [FieldOption.from_dict(o) for o in d["options"]]
        rng = None
        if "range" in d:
            rng = tuple(d["range"])
        return cls(
            field_id=d["field_id"],
            widget=WidgetType(d["widget"]),
            label=d["label"],
            options=options,
            range=rng,
            default=d.get("default"),
            required=d.get("required", True),
            depends_on=d.get("depends_on"),
            help_text=d.get("help_text", ""),
        )


@dataclass
class HypothesisBranch:
    """A hypothesis branch in the model's decision space."""

    branch_id: str
    name: str
    description: str
    confidence: float
    constraints_implied: list[str]     # constraint IDs that activate if chosen
    fields_affected: list[str]         # field_ids whose defaults change

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch_id": self.branch_id,
            "name": self.name,
            "description": self.description,
            "confidence": self.confidence,
            "constraints_implied": self.constraints_implied,
            "fields_affected": self.fields_affected,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> HypothesisBranch:
        return cls(
            branch_id=d["branch_id"],
            name=d["name"],
            description=d["description"],
            confidence=d.get("confidence", 0.0),
            constraints_implied=d.get("constraints_implied", []),
            fields_affected=d.get("fields_affected", []),
        )


@dataclass
class IntentFormSchema:
    """Complete schema for an intent form."""

    schema_id: str              # content-addressed hash
    template_name: str          # which template generated this
    mode: str                   # governor mode (fiction/code/etc)
    policy: IntentFormPolicy
    fields: list[FormField]
    branches: list[HypothesisBranch]
    escape_enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_id": self.schema_id,
            "template_name": self.template_name,
            "mode": self.mode,
            "policy": self.policy.value,
            "fields": [f.to_dict() for f in self.fields],
            "branches": [b.to_dict() for b in self.branches],
            "escape_enabled": self.escape_enabled,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IntentFormSchema:
        return cls(
            schema_id=d["schema_id"],
            template_name=d["template_name"],
            mode=d["mode"],
            policy=IntentFormPolicy(d["policy"]),
            fields=[FormField.from_dict(f) for f in d["fields"]],
            branches=[HypothesisBranch.from_dict(b) for b in d["branches"]],
            escape_enabled=d.get("escape_enabled", True),
        )


@dataclass
class IntentFormResponse:
    """User's filled-out response to an intent form."""

    schema_id: str
    values: dict[str, Any]              # field_id -> selected value
    escape_text: str | None = None      # if "Other" was chosen
    timestamp: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "schema_id": self.schema_id,
            "values": self.values,
        }
        if self.escape_text is not None:
            d["escape_text"] = self.escape_text
        if self.timestamp:
            d["timestamp"] = self.timestamp
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IntentFormResponse:
        return cls(
            schema_id=d["schema_id"],
            values=d["values"],
            escape_text=d.get("escape_text"),
            timestamp=d.get("timestamp", ""),
        )


@dataclass
class IntentCompilationResult:
    """Result of compiling a form response into governance intent."""

    intent_profile: str
    intent_scope: list[str] | None
    intent_deny: list[str] | None
    intent_timebox_minutes: int | None
    constraint_block: dict[str, Any] | None    # serialised ConstraintBlock
    selected_branch: str | None
    escape_classification: EscapeClassification | None
    warnings: list[str]
    receipt_hash: str                           # content-addressed hash of compilation

    def to_dict(self) -> dict[str, Any]:
        return {
            "intent_profile": self.intent_profile,
            "intent_scope": self.intent_scope,
            "intent_deny": self.intent_deny,
            "intent_timebox_minutes": self.intent_timebox_minutes,
            "constraint_block": self.constraint_block,
            "selected_branch": self.selected_branch,
            "escape_classification": (
                self.escape_classification.value
                if self.escape_classification else None
            ),
            "warnings": self.warnings,
            "receipt_hash": self.receipt_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> IntentCompilationResult:
        esc = None
        if d.get("escape_classification"):
            esc = EscapeClassification(d["escape_classification"])
        return cls(
            intent_profile=d["intent_profile"],
            intent_scope=d.get("intent_scope"),
            intent_deny=d.get("intent_deny"),
            intent_timebox_minutes=d.get("intent_timebox_minutes"),
            constraint_block=d.get("constraint_block"),
            selected_branch=d.get("selected_branch"),
            escape_classification=esc,
            warnings=d.get("warnings", []),
            receipt_hash=d["receipt_hash"],
        )


# ---------------------------------------------------------------------------
# Hashing helpers (aligned with gate_receipt.py patterns)
# ---------------------------------------------------------------------------


def _canonical_json(obj: dict[str, Any]) -> bytes:
    """Deterministic JSON: sorted keys, compact, ASCII-safe."""
    return json.dumps(
        obj,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")


def _content_hash(data: bytes) -> str:
    """SHA-256 hex digest."""
    return hashlib.sha256(data).hexdigest()


def _schema_hash(schema_dict: dict[str, Any]) -> str:
    """Content-addressed schema ID.

    Computed from the fields + branches + template_name + mode + policy,
    NOT from the schema_id itself (that would be circular).
    """
    hashable = {
        "template_name": schema_dict.get("template_name", ""),
        "mode": schema_dict.get("mode", ""),
        "policy": schema_dict.get("policy", ""),
        "fields": schema_dict.get("fields", []),
        "branches": schema_dict.get("branches", []),
        "escape_enabled": schema_dict.get("escape_enabled", True),
    }
    return _content_hash(_canonical_json(hashable))


def _compilation_receipt_hash(
    response_dict: dict[str, Any],
    schema_id: str,
    result_dict: dict[str, Any],
) -> str:
    """Deterministic hash of the full compilation."""
    payload = {
        "response": response_dict,
        "schema_id": schema_id,
        "intent_profile": result_dict.get("intent_profile", ""),
        "intent_scope": result_dict.get("intent_scope"),
        "intent_deny": result_dict.get("intent_deny"),
        "intent_timebox_minutes": result_dict.get("intent_timebox_minutes"),
        "selected_branch": result_dict.get("selected_branch"),
    }
    return _content_hash(_canonical_json(payload))


# ---------------------------------------------------------------------------
# Policy Mapping
# ---------------------------------------------------------------------------


_MODE_POLICY_MAP: dict[str, IntentFormPolicy] = {
    "code": IntentFormPolicy.TEMPLATE_ONLY,
    "general": IntentFormPolicy.TEMPLATE_ONLY,
    "nonfiction": IntentFormPolicy.VALIDATED_CUSTOM,
    "research": IntentFormPolicy.VALIDATED_CUSTOM,
    "fiction": IntentFormPolicy.CUSTOM_OK,
}


def get_form_policy(mode: str) -> IntentFormPolicy:
    """Map governor mode to form policy.

    Unknown modes default to TEMPLATE_ONLY (fail-closed).
    """
    return _MODE_POLICY_MAP.get(mode, IntentFormPolicy.TEMPLATE_ONLY)


# ---------------------------------------------------------------------------
# Built-in Templates
# ---------------------------------------------------------------------------


def _get_profile_options() -> list[FieldOption]:
    """Profile options from profiles.py BUILTIN_PROFILES."""
    try:
        from governor.profiles import BUILTIN_PROFILES
        names = sorted(BUILTIN_PROFILES.keys())
    except ImportError:
        names = ["strict", "permissive", "research", "production", "audit"]
    return [
        FieldOption(value=name, label=name.replace("_", " ").title())
        for name in names
    ]


def _build_session_start_template(
    mode: str,
    context: dict[str, Any] | None = None,
) -> IntentFormSchema:
    """Session initialization template."""
    profile_opts = _get_profile_options()
    # Set confidence heuristic: production highest for code, research for research
    for opt in profile_opts:
        if mode == "code" and opt.value == "production":
            opt.confidence = 0.4
        elif mode == "research" and opt.value == "research":
            opt.confidence = 0.4
        elif mode == "fiction" and opt.value == "permissive":
            opt.confidence = 0.4
        elif opt.value == "strict":
            opt.confidence = 0.2

    mode_opts = [
        FieldOption(value="code", label="Code", confidence=0.3 if mode == "code" else 0.1),
        FieldOption(value="fiction", label="Fiction", confidence=0.3 if mode == "fiction" else 0.1),
        FieldOption(value="nonfiction", label="Nonfiction", confidence=0.3 if mode == "nonfiction" else 0.1),
        FieldOption(value="general", label="General", confidence=0.3 if mode == "general" else 0.1),
    ]

    fields = [
        FormField(
            field_id="profile",
            widget=WidgetType.SELECT_ONE,
            label="Governance profile",
            options=profile_opts,
            default="strict",
            help_text="Controls envelope, boil preset, jurisdiction, and strict mode.",
        ),
        FormField(
            field_id="scope",
            widget=WidgetType.TEXT_SHORT,
            label="File scope (glob patterns)",
            default="",
            required=False,
            help_text="e.g. src/** or tests/*.py",
        ),
        FormField(
            field_id="mode",
            widget=WidgetType.SELECT_ONE,
            label="Governor mode",
            options=mode_opts,
            default=mode,
            help_text="Domain for governance rules.",
        ),
        FormField(
            field_id="timebox",
            widget=WidgetType.SLIDER,
            label="Session timebox (minutes)",
            range=(15.0, 480.0),
            default=120,
            required=False,
            help_text="Auto-expire after this many minutes.",
        ),
    ]

    branches = [
        HypothesisBranch(
            branch_id="strict_session",
            name="Strict session",
            description="Full enforcement, fail-closed, factual jurisdiction.",
            confidence=0.3,
            constraints_implied=["strict_envelope", "factual_jurisdiction"],
            fields_affected=["profile"],
        ),
        HypothesisBranch(
            branch_id="exploratory_session",
            name="Exploratory session",
            description="Relaxed enforcement for research or prototyping.",
            confidence=0.25,
            constraints_implied=["exploratory_envelope"],
            fields_affected=["profile"],
        ),
    ]

    policy = get_form_policy(mode)
    schema_dict = {
        "template_name": "session_start",
        "mode": mode,
        "policy": policy.value,
        "fields": [f.to_dict() for f in fields],
        "branches": [b.to_dict() for b in branches],
        "escape_enabled": True,
    }

    return IntentFormSchema(
        schema_id=_schema_hash(schema_dict),
        template_name="session_start",
        mode=mode,
        policy=policy,
        fields=fields,
        branches=branches,
        escape_enabled=True,
    )


def _build_task_scope_template(
    mode: str,
    context: dict[str, Any] | None = None,
) -> IntentFormSchema:
    """Task scoping template."""
    profile_opts = [
        FieldOption(value="inherit", label="Inherit from session", confidence=0.5),
    ] + _get_profile_options()

    verification_opts = [
        FieldOption(value="full", label="Full verification", confidence=0.4),
        FieldOption(value="minimal", label="Minimal verification", confidence=0.3),
        FieldOption(value="skip", label="Skip verification", confidence=0.1),
    ]

    fields = [
        FormField(
            field_id="task",
            widget=WidgetType.TEXT_LONG,
            label="Task description",
            help_text="What should the agent do?",
        ),
        FormField(
            field_id="profile",
            widget=WidgetType.SELECT_ONE,
            label="Profile override",
            options=profile_opts,
            default="inherit",
            required=False,
            help_text="Override session profile for this task.",
        ),
        FormField(
            field_id="scope",
            widget=WidgetType.TEXT_SHORT,
            label="File scope",
            default="",
            required=False,
            help_text="Narrow file scope for this task (glob).",
        ),
        FormField(
            field_id="deny",
            widget=WidgetType.TEXT_SHORT,
            label="Deny patterns",
            default="",
            required=False,
            help_text="Patterns to forbid (e.g. *.env, secrets/*).",
        ),
        FormField(
            field_id="verification",
            widget=WidgetType.SELECT_ONE,
            label="Verification level",
            options=verification_opts,
            default="full",
            help_text="How rigorously to verify task outputs.",
        ),
    ]

    branches = [
        HypothesisBranch(
            branch_id="scoped_task",
            name="Scoped task",
            description="Task with explicit file boundaries.",
            confidence=0.4,
            constraints_implied=["scope_enforcement"],
            fields_affected=["scope", "deny"],
        ),
        HypothesisBranch(
            branch_id="open_task",
            name="Open task",
            description="Task without file restrictions.",
            confidence=0.3,
            constraints_implied=[],
            fields_affected=[],
        ),
    ]

    policy = get_form_policy(mode)
    schema_dict = {
        "template_name": "task_scope",
        "mode": mode,
        "policy": policy.value,
        "fields": [f.to_dict() for f in fields],
        "branches": [b.to_dict() for b in branches],
        "escape_enabled": True,
    }

    return IntentFormSchema(
        schema_id=_schema_hash(schema_dict),
        template_name="task_scope",
        mode=mode,
        policy=policy,
        fields=fields,
        branches=branches,
        escape_enabled=True,
    )


def _build_verification_config_template(
    mode: str,
    context: dict[str, Any] | None = None,
) -> IntentFormSchema:
    """Verification strategy template."""
    evidence_opts = [
        FieldOption(value="full", label="Full evidence", confidence=0.4),
        FieldOption(value="sampling", label="Sampling", confidence=0.35),
        FieldOption(value="trust", label="Trust mode", confidence=0.1),
    ]

    fields = [
        FormField(
            field_id="evidence_level",
            widget=WidgetType.SELECT_ONE,
            label="Evidence level",
            options=evidence_opts,
            default="full",
            help_text="How much evidence to require.",
        ),
        FormField(
            field_id="security_scan",
            widget=WidgetType.CONFIRMATION,
            label="Enable security scanning",
            default=True,
            help_text="Run vulnerability detection on outputs.",
        ),
        FormField(
            field_id="continuity_check",
            widget=WidgetType.CONFIRMATION,
            label="Enable continuity enforcement",
            default=True,
            help_text="Check outputs against continuity anchors.",
        ),
        FormField(
            field_id="max_violations",
            widget=WidgetType.SLIDER,
            label="Max violations before halt",
            range=(0.0, 10.0),
            default=3,
            help_text="Stop execution after this many violations.",
        ),
    ]

    branches = [
        HypothesisBranch(
            branch_id="full_verification",
            name="Full verification",
            description="All checks enabled, strict evidence.",
            confidence=0.4,
            constraints_implied=["full_evidence", "security_scan", "continuity_check"],
            fields_affected=["evidence_level", "security_scan", "continuity_check"],
        ),
        HypothesisBranch(
            branch_id="light_verification",
            name="Light verification",
            description="Sampling evidence, relaxed limits.",
            confidence=0.3,
            constraints_implied=["sampling_evidence"],
            fields_affected=["evidence_level", "max_violations"],
        ),
    ]

    policy = get_form_policy(mode)
    schema_dict = {
        "template_name": "verification_config",
        "mode": mode,
        "policy": policy.value,
        "fields": [f.to_dict() for f in fields],
        "branches": [b.to_dict() for b in branches],
        "escape_enabled": True,
    }

    return IntentFormSchema(
        schema_id=_schema_hash(schema_dict),
        template_name="verification_config",
        mode=mode,
        policy=policy,
        fields=fields,
        branches=branches,
        escape_enabled=True,
    )


# Template registry
BUILTIN_TEMPLATES: dict[str, Any] = {
    "session_start": {
        "builder": _build_session_start_template,
        "description": "Initialize a governance session with profile, mode, and scope.",
    },
    "task_scope": {
        "builder": _build_task_scope_template,
        "description": "Scope a specific task before execution.",
    },
    "verification_config": {
        "builder": _build_verification_config_template,
        "description": "Configure verification strategy for a run.",
    },
}


# ---------------------------------------------------------------------------
# Schema Building
# ---------------------------------------------------------------------------


def build_form_schema(
    template_name: str,
    mode: str,
    context: dict[str, Any] | None = None,
) -> IntentFormSchema:
    """Build a form schema from a named template + mode.

    Policy enforcement:
      - TEMPLATE_ONLY: template_name must be in BUILTIN_TEMPLATES.
      - VALIDATED_CUSTOM: any template, but all fields validated against WidgetType.
      - CUSTOM_OK: any valid schema accepted.
    """
    policy = get_form_policy(mode)

    if policy == IntentFormPolicy.TEMPLATE_ONLY:
        if template_name not in BUILTIN_TEMPLATES:
            raise ValueError(
                f"Template '{template_name}' not allowed under TEMPLATE_ONLY policy. "
                f"Available: {sorted(BUILTIN_TEMPLATES.keys())}"
            )

    if template_name in BUILTIN_TEMPLATES:
        builder = BUILTIN_TEMPLATES[template_name]["builder"]
        return builder(mode, context)

    # Custom template (only reachable for VALIDATED_CUSTOM or CUSTOM_OK)
    if policy == IntentFormPolicy.VALIDATED_CUSTOM:
        # Build from context, validate widget types
        return _build_custom_schema(template_name, mode, context, validate=True)
    else:
        # CUSTOM_OK
        return _build_custom_schema(template_name, mode, context, validate=False)


def _build_custom_schema(
    template_name: str,
    mode: str,
    context: dict[str, Any] | None = None,
    validate: bool = False,
) -> IntentFormSchema:
    """Build a custom schema from context dict.

    Context should contain 'fields' and optionally 'branches'.
    """
    ctx = context or {}
    raw_fields = ctx.get("fields", [])
    raw_branches = ctx.get("branches", [])

    fields: list[FormField] = []
    for f in raw_fields:
        ff = FormField.from_dict(f) if isinstance(f, dict) else f
        if validate:
            # Ensure widget type is in allowlist
            if ff.widget not in WidgetType:
                raise ValueError(
                    f"Widget type '{ff.widget}' not in allowed types: "
                    f"{[w.value for w in WidgetType]}"
                )
        fields.append(ff)

    branches: list[HypothesisBranch] = []
    for b in raw_branches:
        branches.append(
            HypothesisBranch.from_dict(b) if isinstance(b, dict) else b
        )

    policy = get_form_policy(mode)
    schema_dict = {
        "template_name": template_name,
        "mode": mode,
        "policy": policy.value,
        "fields": [f.to_dict() for f in fields],
        "branches": [b.to_dict() for b in branches],
        "escape_enabled": ctx.get("escape_enabled", True),
    }

    return IntentFormSchema(
        schema_id=_schema_hash(schema_dict),
        template_name=template_name,
        mode=mode,
        policy=policy,
        fields=fields,
        branches=branches,
        escape_enabled=ctx.get("escape_enabled", True),
    )


# ---------------------------------------------------------------------------
# Response Validation
# ---------------------------------------------------------------------------


def validate_response(
    response: IntentFormResponse,
    schema: IntentFormSchema,
) -> list[str]:
    """Validate a response against its schema.

    Returns list of validation errors (empty = valid).
    """
    errors: list[str] = []

    if response.schema_id != schema.schema_id:
        errors.append(
            f"Schema ID mismatch: response has '{response.schema_id}', "
            f"expected '{schema.schema_id}'"
        )

    field_map = {f.field_id: f for f in schema.fields}

    # Check required fields
    for fld in schema.fields:
        if fld.required and fld.field_id not in response.values:
            # Skip if conditional and parent not selected
            if fld.depends_on:
                parent_val = response.values.get(fld.depends_on)
                if not parent_val:
                    continue  # Parent not set, conditional not required
            errors.append(f"Required field '{fld.field_id}' missing")

    # Validate each provided value
    for fid, val in response.values.items():
        if fid not in field_map:
            errors.append(f"Unknown field '{fid}'")
            continue
        fld = field_map[fid]
        field_errors = _validate_field_value(fld, val)
        errors.extend(field_errors)

    # Escape text validation
    if response.escape_text is not None and not schema.escape_enabled:
        errors.append("Escape text provided but escape is disabled on this schema")

    return errors


def _validate_field_value(fld: FormField, val: Any) -> list[str]:
    """Validate a single field value."""
    errors: list[str] = []

    if fld.widget == WidgetType.SELECT_ONE:
        if fld.options:
            valid_values = [o.value for o in fld.options]
            if val not in valid_values:
                errors.append(
                    f"Field '{fld.field_id}': value '{val}' not in options "
                    f"{valid_values}"
                )

    elif fld.widget == WidgetType.SELECT_MANY:
        if not isinstance(val, list):
            errors.append(f"Field '{fld.field_id}': expected list, got {type(val).__name__}")
        elif fld.options:
            valid_values = {o.value for o in fld.options}
            for v in val:
                if v not in valid_values:
                    errors.append(
                        f"Field '{fld.field_id}': value '{v}' not in options"
                    )

    elif fld.widget == WidgetType.SLIDER:
        if not isinstance(val, (int, float)):
            errors.append(
                f"Field '{fld.field_id}': expected number, got {type(val).__name__}"
            )
        elif fld.range:
            lo, hi = fld.range
            if val < lo or val > hi:
                errors.append(
                    f"Field '{fld.field_id}': value {val} out of range [{lo}, {hi}]"
                )

    elif fld.widget in (WidgetType.TEXT_SHORT, WidgetType.TEXT_LONG):
        if not isinstance(val, str):
            errors.append(
                f"Field '{fld.field_id}': expected string, got {type(val).__name__}"
            )

    elif fld.widget == WidgetType.CONFIRMATION:
        if not isinstance(val, bool):
            errors.append(
                f"Field '{fld.field_id}': expected boolean, got {type(val).__name__}"
            )

    return errors


# ---------------------------------------------------------------------------
# Escape Classification
# ---------------------------------------------------------------------------

# Heuristic patterns — deterministic, no LLM
_SCHEMA_VIOLATION_PATTERNS = re.compile(
    r"\b(skip|none|n/?a|cancel|abort|quit|no thanks)\b", re.IGNORECASE
)
_NEW_CONSTRAINT_PATTERNS = re.compile(
    r"\b(add|create|require|enforce|must|constraint|rule)\b", re.IGNORECASE
)
_WAIVER_PATTERNS = re.compile(
    r"\b(allow|except|waive|override|bypass|ignore|exempt)\b", re.IGNORECASE
)


def classify_escape(
    escape_text: str,
    schema: IntentFormSchema,
) -> EscapeClassification:
    """Classify an escape hatch response. Deterministic heuristic, not LLM."""
    text = escape_text.strip()
    if not text:
        return EscapeClassification.CLARIFICATION_NEEDED

    # Order matters: most specific first
    if _SCHEMA_VIOLATION_PATTERNS.search(text):
        return EscapeClassification.SCHEMA_VIOLATION
    if _WAIVER_PATTERNS.search(text):
        return EscapeClassification.WAIVER_CANDIDATE
    if _NEW_CONSTRAINT_PATTERNS.search(text):
        return EscapeClassification.NEW_CONSTRAINT
    return EscapeClassification.CLARIFICATION_NEEDED


# ---------------------------------------------------------------------------
# Compilation
# ---------------------------------------------------------------------------


def compile_intent(
    response: IntentFormResponse,
    schema: IntentFormSchema,
    governor_dir: Path | None = None,
) -> IntentCompilationResult:
    """Deterministic compilation: response + schema -> Intent + ConstraintBlock.

    Pure except for optional constraint compilation (which reads .governor/ state)
    and optional receipt emission.
    """
    warnings: list[str] = []

    # Validate first
    validation_errors = validate_response(response, schema)
    if validation_errors:
        warnings.extend(validation_errors)

    # Extract intent fields
    values = response.values
    profile = values.get("profile", "strict")
    if profile == "inherit":
        profile = "strict"
        warnings.append("Profile 'inherit' resolved to 'strict' (no parent session)")

    scope_raw = values.get("scope", "")
    scope_list: list[str] | None = None
    if scope_raw:
        scope_list = [s.strip() for s in scope_raw.split(",") if s.strip()]

    deny_raw = values.get("deny", "")
    deny_list: list[str] | None = None
    if deny_raw:
        deny_list = [s.strip() for s in deny_raw.split(",") if s.strip()]

    timebox_raw = values.get("timebox")
    timebox: int | None = None
    if timebox_raw is not None:
        timebox = int(timebox_raw)

    # Determine selected branch
    selected_branch: str | None = None
    if schema.branches:
        # Find branch matching profile selection
        for branch in schema.branches:
            for fid in branch.fields_affected:
                if fid in values:
                    selected_branch = branch.branch_id
                    break
            if selected_branch:
                break

    # Classify escape
    escape_cls: EscapeClassification | None = None
    if response.escape_text:
        escape_cls = classify_escape(response.escape_text, schema)
        if escape_cls == EscapeClassification.SCHEMA_VIOLATION:
            warnings.append("Escape text classified as schema violation")
        elif escape_cls == EscapeClassification.WAIVER_CANDIDATE:
            warnings.append("Escape text classified as waiver candidate")

    # Compile constraint block if governor_dir available
    constraint_block_dict: dict[str, Any] | None = None
    if governor_dir and governor_dir.exists():
        try:
            from governor.constraint_compiler import compile_constraints
            block = compile_constraints(
                intent=profile,
                scope=scope_list,
                mode=values.get("mode"),
                governor_dir=governor_dir,
            )
            constraint_block_dict = block.to_dict()
        except Exception as exc:
            warnings.append(f"Constraint compilation failed: {exc}")

    # Build result (before receipt hash, since hash includes result fields)
    result_dict = {
        "intent_profile": profile,
        "intent_scope": scope_list,
        "intent_deny": deny_list,
        "intent_timebox_minutes": timebox,
        "selected_branch": selected_branch,
    }

    receipt_hash = _compilation_receipt_hash(
        response.to_dict(), schema.schema_id, result_dict,
    )

    result = IntentCompilationResult(
        intent_profile=profile,
        intent_scope=scope_list,
        intent_deny=deny_list,
        intent_timebox_minutes=timebox,
        constraint_block=constraint_block_dict,
        selected_branch=selected_branch,
        escape_classification=escape_cls,
        warnings=warnings,
        receipt_hash=receipt_hash,
    )

    # Emit gate receipt if .governor/ exists
    if governor_dir and governor_dir.exists():
        _emit_receipt(response, schema, result, governor_dir)

    return result


def _emit_receipt(
    response: IntentFormResponse,
    schema: IntentFormSchema,
    result: IntentCompilationResult,
    governor_dir: Path,
) -> None:
    """Emit a gate receipt for this compilation."""
    try:
        from governor.gate_receipt import GateReceiptSystem
    except ImportError:
        return

    receipts_dir = governor_dir / "receipts"
    if not receipts_dir.parent.exists():
        return

    system = GateReceiptSystem(governor_dir)

    verdict = "pass" if not result.warnings else "warn"
    # Check for blocking conditions
    validation_errors = validate_response(response, schema)
    if validation_errors:
        verdict = "block"

    evidence_bundle = {
        "response": response.to_dict(),
        "selected_branch": result.selected_branch,
        "escape_classification": (
            result.escape_classification.value
            if result.escape_classification else None
        ),
        "warnings": result.warnings,
    }

    gate_config = {
        "policy": schema.policy.value,
        "template_name": schema.template_name,
    }

    system.emit(
        gate="intent_compiler",
        verdict=verdict,
        subject_kind="intent_form",
        subject_bytes=_canonical_json(response.to_dict()),
        evidence_bundle=evidence_bundle,
        gate_config=gate_config,
    )


# ---------------------------------------------------------------------------
# Template listing (for API)
# ---------------------------------------------------------------------------


def list_templates() -> list[dict[str, str]]:
    """List available templates with names and descriptions."""
    return [
        {"name": name, "description": entry["description"]}
        for name, entry in BUILTIN_TEMPLATES.items()
    ]
