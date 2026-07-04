# SPDX-License-Identifier: Apache-2.0
"""Concrete provider descriptors — Slice 3 (DRAFT / CANDIDATE, STRUCTURAL only).

The first HONEST conforming descriptor: **Claude Code as an `agent_runtime`
provider.** ``runtime_capabilities`` are projected LIVE from the shipped
``ClaudeCodeAdapter`` so the declaration cannot silently drift from the adapter
(a test pins the equality). STRUCTURAL conformance only — no runtime conformance
is claimed here (that needs live runs), and enforcement is the outer cage + AG
dispatch, never this descriptor.

DELIBERATE NON-EXAMPLE — **Maude is intentionally NOT registered as a provider.**
Maude is currently an operator/ingress CONSUMER of AG decisions and supervised-run
state, not a dispatch target that receives WorkContainers from AG. It talks to the
clerk; it is not a bailiff. A provider is something AG can dispatch a WorkContainer
toward and later receive testimony from — Claude Code fits; the Maude operator
surface does not. If Maude later exposes a provider-facing execution service (e.g.
``maude-supervisor-provider`` / ``maude-local-exec-provider``), THAT service may
register as a distinct provider descriptor — but the operator surface itself is
not a provider, and modeling it as one now would teach later integrations the
wrong shape.
"""

from __future__ import annotations

import dataclasses

from governor.provider_registry import ProviderDescriptor


def _adapter_runtime_flags(adapter) -> frozenset[str]:
    """The True AdapterCapabilities flag names — projected live from an adapter."""
    caps = adapter.capabilities()
    return frozenset(name for name, val in dataclasses.asdict(caps).items() if val is True)


def claude_code_descriptor() -> ProviderDescriptor:
    """Claude Code as an `agent_runtime` provider.

    ``runtime_capabilities`` project LIVE from ``ClaudeCodeAdapter().capabilities()``.
    The ``capabilities`` (CapabilityClass) set is the honest DECLARED action space
    of a coding agent — what it *can* do; a given run's *permission* is the
    WorkContainer ration, not this list. STRUCTURAL only: declared, not
    runtime-verified.
    """
    from governor.runtime.adapters.claude_code import ClaudeCodeAdapter

    return ProviderDescriptor(
        provider_id="claude_code",
        provider_kind="agent_runtime",
        display_name="Claude Code",
        version="0",
        capabilities=frozenset(
            {
                "file_read",
                "file_write",
                "shell_exec",
                "code_exec",
                "model_call",
                "network_egress",
            }
        ),
        runtime_capabilities=_adapter_runtime_flags(ClaudeCodeAdapter()),
        custody_claims=frozenset({"transcript", "filesystem_delta"}),
        authority_claims=(),
    )
