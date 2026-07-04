# SPDX-License-Identifier: Apache-2.0
"""Slice 3 — the first honest structural provider descriptor (Claude Code).

Pins: the descriptor registers as STRUCTURAL, declares no authority, its
runtime_capabilities are projected LIVE from the shipped ClaudeCodeAdapter (so it
cannot drift), it validates against the DRAFT schema, and — the deliberate
non-example — Maude is NOT modeled as a provider.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from governor.provider_descriptors import claude_code_descriptor
from governor.provider_registry import ConformanceLevel, ProviderRegistry

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas" / "provider_descriptor.v1.json"


def test_claude_code_is_agent_runtime_provider():
    d = claude_code_descriptor()
    assert d.provider_id == "claude_code"
    assert d.provider_kind == "agent_runtime"
    assert d.authority_claims == ()  # declares no authority


def test_runtime_capabilities_projected_live_from_adapter():
    # Anti-drift: the descriptor's runtime flags must equal the shipped adapter's
    # live capabilities(), so the declaration can't silently diverge from reality.
    from governor.runtime.adapters.claude_code import ClaudeCodeAdapter

    caps = ClaudeCodeAdapter().capabilities()
    live_true = {k for k, v in dataclasses.asdict(caps).items() if v is True}
    assert set(claude_code_descriptor().runtime_capabilities) == live_true
    assert live_true  # sanity: the adapter declares at least one capability


def test_descriptor_registers_as_structural():
    r = ProviderRegistry()
    entry = r.register(claude_code_descriptor())
    assert entry.conformance is ConformanceLevel.STRUCTURAL
    # It is a routing candidate for an agent_runtime that must write files...
    got = [d.provider_id for d in r.candidates_for(
        capability_requirements={"file_write"}, provider_kind="agent_runtime")]
    assert got == ["claude_code"]


def test_maude_is_not_a_provider():
    # The deliberate non-example: registering the real descriptor set yields no
    # Maude provider. Maude is an operator/ingress consumer, not a dispatch target.
    r = ProviderRegistry()
    r.register(claude_code_descriptor())
    assert r.get("maude") is None
    all_ids = {e.descriptor.provider_id for e in r.entries()}
    assert "maude" not in all_ids


def test_descriptor_validates_against_v1_schema():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(_SCHEMA_PATH.read_text())
    jsonschema.Draft202012Validator(schema).validate(claude_code_descriptor().to_schema_dict())
