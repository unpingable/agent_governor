# SPDX-License-Identifier: Apache-2.0
"""
Registry-driven effective configuration.

Every known config key is registered with metadata (type, default, redaction,
explanation). ``collect_effective_config`` walks layers in priority order and
returns a list of ``ConfigEntry`` — one per registry key — with the winning
value, source, and redaction applied.

Layer order (highest wins):
    1. defaults (from CONFIG_REGISTRY)
    2. daemon.conf ($GOVERNOR_DIR/daemon.conf)
    3. .governor.toml or config.json (repo-level defaults)
    4. .envelope file
    5. .profile file + profile-implied settings
    6. intent.json (session intent)
    7. env vars
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import OrderedDict
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------

class RedactionClass(Enum):
    PUBLIC = "public"
    BOOLEAN_PRESENCE = "presence"
    REDACTED = "redacted"
    HASH_ONLY = "hash_only"


# ---------------------------------------------------------------------------
# Config key registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConfigKeySpec:
    key: str
    type: type
    default: Any
    redaction: RedactionClass
    explain: str


CONFIG_REGISTRY: OrderedDict[str, ConfigKeySpec] = OrderedDict()


def _reg(key: str, type_: type, default: Any, redaction: RedactionClass, explain: str) -> None:
    assert key not in CONFIG_REGISTRY, f"duplicate config key: {key}"
    assert explain, f"empty explain for config key: {key}"
    CONFIG_REGISTRY[key] = ConfigKeySpec(key, type_, default, redaction, explain)


_reg("backend_type", str, "auto", RedactionClass.PUBLIC,
     "Backend selection: anthropic|ollama|claude-code|codex|auto")
_reg("model", str, "", RedactionClass.PUBLIC,
     "Default model for chat/generation")
_reg("api_key_set", bool, False, RedactionClass.BOOLEAN_PRESENCE,
     "Whether an Anthropic API key is configured")
_reg("envelope", str, "strict", RedactionClass.PUBLIC,
     "Operating envelope: strict|exploratory")
_reg("mode", str, "general", RedactionClass.PUBLIC,
     "Governor mode: general|fiction|code|nonfiction|research")
_reg("profile", str, None, RedactionClass.PUBLIC,
     "Active named profile (strict/permissive/production/etc.)")
_reg("gov_backend", str, "auto", RedactionClass.PUBLIC,
     "CLI-daemon backend: rpc|local|auto")
_reg("socket_path", str, "", RedactionClass.PUBLIC,
     "Daemon Unix socket path (computed from gov_dir)")
_reg("trust_principal", bool, False, RedactionClass.PUBLIC,
     "Whether daemon trusts client-provided principal_id")
_reg("receipt_format", str, "legacy", RedactionClass.PUBLIC,
     "Default receipt format: legacy|v1")

del _reg  # not part of public API


# ---------------------------------------------------------------------------
# Config source + entry
# ---------------------------------------------------------------------------

class ConfigSource(Enum):
    DEFAULT = "default"
    DAEMON_CONF = "daemon_conf"
    REPO_CONF = "repo_conf"
    ENVELOPE_FILE = "envelope_file"
    PROFILE_FILE = "profile_file"
    INTENT = "intent"
    ENV = "env"


@dataclass
class ConfigEntry:
    key: str
    raw_value: Any
    source: ConfigSource
    source_detail: dict[str, Any]
    redaction: RedactionClass
    explain: str

    def to_dict(self) -> dict[str, Any]:
        """Serializable dict — redaction applied, raw_value never exposed."""
        return {
            "key": self.key,
            "value": self._redacted_value(),
            "source": self.source.value,
            "source_detail": self.source_detail,
            "explain": self.explain,
        }

    def display_value(self) -> str:
        """Human-readable value with redaction applied."""
        v = self._redacted_value()
        return str(v) if v is not None else "(none)"

    def _redacted_value(self) -> Any:
        if self.redaction == RedactionClass.BOOLEAN_PRESENCE:
            return bool(self.raw_value)
        if self.redaction == RedactionClass.REDACTED:
            return "***"
        if self.redaction == RedactionClass.HASH_ONLY:
            return hashlib.sha256(str(self.raw_value).encode()).hexdigest()[:8]
        return self.raw_value


# ---------------------------------------------------------------------------
# Layer readers
# ---------------------------------------------------------------------------

def _read_daemon_conf(gov_dir: Path) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read daemon.conf and return {registry_key: (value, source_detail)}."""
    from .daemon import load_daemon_config
    raw = load_daemon_config(gov_dir)
    mapping: dict[str, tuple[Any, dict[str, Any]]] = {}

    # Map flattened daemon.conf keys to registry keys
    key_map = {
        "backend.type": "backend_type",
        "backend.model": "model",
        "daemon.trust_principal_from_client": "trust_principal",
        "daemon.receipt_format": "receipt_format",
    }

    conf_path = str(gov_dir / "daemon.conf")
    for conf_key, value in raw.items():
        reg_key = key_map.get(conf_key)
        if reg_key is None:
            continue
        section, _, field = conf_key.partition(".")
        detail = {"path": conf_path, "section": section, "field": field}

        # Coerce booleans
        spec = CONFIG_REGISTRY.get(reg_key)
        if spec and spec.type is bool:
            value = value.lower() in ("1", "true", "yes")

        mapping[reg_key] = (value, detail)
    return mapping


def _read_envelope_file(gov_dir: Path) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read .envelope file if it exists."""
    envelope_path = gov_dir / ".envelope"
    if not envelope_path.exists():
        return {}
    content = envelope_path.read_text().strip()
    if not content:
        return {}
    return {
        "envelope": (content, {"path": str(envelope_path)}),
    }


def _read_profile_file(gov_dir: Path) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read .profile file if it exists."""
    profile_path = gov_dir / ".profile"
    if not profile_path.exists():
        return {}
    content = profile_path.read_text().strip()
    if not content:
        return {}
    detail: dict[str, Any] = {"path": str(profile_path), "profile": content}

    result: dict[str, tuple[Any, dict[str, Any]]] = {
        "profile": (content, detail),
    }

    # Profile-implied envelope (production/strict → strict, etc.)
    strict_profiles = {"production", "strict", "audit"}
    if content in strict_profiles:
        result["envelope"] = (
            "strict",
            {"path": str(profile_path), "profile": content, "implied": {"envelope": "strict"}},
        )

    return result


def _read_intent_file(gov_dir: Path) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read intent.json if it exists."""
    intent_path = gov_dir / "intent.json"
    if not intent_path.exists():
        return {}
    try:
        data = json.loads(intent_path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}
    result: dict[str, tuple[Any, dict[str, Any]]] = {}
    if "profile" in data:
        result["profile"] = (
            data["profile"],
            {"path": str(intent_path), "field": "profile"},
        )
    if "mode" in data:
        result["mode"] = (
            data["mode"],
            {"path": str(intent_path), "field": "mode"},
        )
    return result


def _read_repo_conf(gov_dir: Path) -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read .governor.toml or config.json if either exists."""
    # Try .governor.toml first
    toml_path = gov_dir / ".governor.toml"
    if toml_path.exists():
        try:
            # stdlib tomllib available 3.11+
            import tomllib
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
        except (ImportError, Exception):
            data = {}
        defaults = data.get("defaults", {})
        result: dict[str, tuple[Any, dict[str, Any]]] = {}
        for field, value in defaults.items():
            if field in CONFIG_REGISTRY:
                result[field] = (
                    value,
                    {"path": str(toml_path), "section": "defaults", "field": field},
                )
        return result

    # Fall back to config.json
    json_path = gov_dir / "config.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
        result = {}
        for field, value in data.items():
            if field in CONFIG_REGISTRY:
                result[field] = (
                    value,
                    {"path": str(json_path), "field": field},
                )
        return result

    return {}


def _read_env_vars() -> dict[str, tuple[Any, dict[str, Any]]]:
    """Read config from environment variables."""
    result: dict[str, tuple[Any, dict[str, Any]]] = {}

    env_map = {
        "BACKEND_TYPE": "backend_type",
        "GOVERNOR_MODEL": "model",
        "GOV_BACKEND": "gov_backend",
        "GOV_PROFILE": "profile",
        "TRUST_PRINCIPAL_FROM_CLIENT": "trust_principal",
    }

    for env_var, reg_key in env_map.items():
        value = os.environ.get(env_var)
        if value is not None:
            spec = CONFIG_REGISTRY.get(reg_key)
            if spec and spec.type is bool:
                value = value.strip().lower() in ("1", "true", "yes")
            result[reg_key] = (value, {"var": env_var})

    # Special case: ANTHROPIC_API_KEY → api_key_set (boolean presence)
    if os.environ.get("ANTHROPIC_API_KEY"):
        result["api_key_set"] = (True, {"var": "ANTHROPIC_API_KEY"})

    return result


# ---------------------------------------------------------------------------
# collect_effective_config
# ---------------------------------------------------------------------------

def collect_effective_config(gov_dir: Path) -> list[ConfigEntry]:
    """Walk all config layers and return one ConfigEntry per registry key.

    Layer order (highest wins): defaults < daemon.conf < repo_conf <
    envelope_file < profile_file < intent < env.
    """
    # Start with defaults
    entries: dict[str, ConfigEntry] = {}
    for key, spec in CONFIG_REGISTRY.items():
        entries[key] = ConfigEntry(
            key=key,
            raw_value=spec.default,
            source=ConfigSource.DEFAULT,
            source_detail={},
            redaction=spec.redaction,
            explain=spec.explain,
        )

    # Layer sources in priority order (each overwrites previous)
    layers: list[tuple[ConfigSource, dict[str, tuple[Any, dict[str, Any]]]]] = [
        (ConfigSource.DAEMON_CONF, _read_daemon_conf(gov_dir)),
        (ConfigSource.REPO_CONF, _read_repo_conf(gov_dir)),
        (ConfigSource.ENVELOPE_FILE, _read_envelope_file(gov_dir)),
        (ConfigSource.PROFILE_FILE, _read_profile_file(gov_dir)),
        (ConfigSource.INTENT, _read_intent_file(gov_dir)),
        (ConfigSource.ENV, _read_env_vars()),
    ]

    for source, layer_data in layers:
        for key, (value, detail) in layer_data.items():
            if key not in CONFIG_REGISTRY:
                continue  # Unknown keys silently ignored
            spec = CONFIG_REGISTRY[key]
            entries[key] = ConfigEntry(
                key=key,
                raw_value=value,
                source=source,
                source_detail=detail,
                redaction=spec.redaction,
                explain=spec.explain,
            )

    # Socket path is computed, not configured — always set it
    from .daemon import default_socket_path
    sock = default_socket_path(gov_dir)
    entries["socket_path"] = ConfigEntry(
        key="socket_path",
        raw_value=str(sock),
        source=ConfigSource.DEFAULT,
        source_detail={"computed_from": str(gov_dir)},
        redaction=RedactionClass.PUBLIC,
        explain=CONFIG_REGISTRY["socket_path"].explain,
    )

    # Return in registry order
    return [entries[key] for key in CONFIG_REGISTRY if key in entries]
