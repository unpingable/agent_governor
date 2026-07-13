# SPDX-License-Identifier: Apache-2.0
"""Grant-use gate (approval compression, S1) — PURE classification.

Doctrine: **a use of standing is not a request for new standing.** For one
supervised tool call this module decides whether the call falls WITHIN the
plan-approved ``RationCard`` envelope, WIDENS it (material escalation), or
cannot be cleanly classified (fail closed). It mints nothing and does no IO —
S2 (the supervisor wiring) attaches the receipt / standing verdict to turn a
decision into a ``GrantUsed`` / ``GrantRefused`` / ``NoVerifiedResult``.

Trust-not-enforcement (honest label): this enforces the DECLARED scope by
matching; substrate effects are not armed (SyntheticCage/C11/seccomp unarmed —
documented bootstrap limit). It loses nothing versus today's per-call
rubber-stamp and removes the confounding toil. The escalation (widening) prompt
is the seam that must never soften.

Fail-closed invariant: nothing reaches ``WithinGrant`` unless it is cleanly
classified AND inside the grant. Anything ambiguous (opaque shell, unknown
tool, unparseable target, effect-relocating flag) → ``Unverifiable``; anything
outside the grant → ``WidensGrant``. See design-grant-use-gate.md.

Known limits of a PURE classifier (the armed sandbox, not this gate, is the
real fence — hence ``enforcement: declared-effects-only``): it matches on the
declared path/command STRINGS, so it does not follow symlinks (a granted path
that is a symlink out of the envelope is not caught here), and an allowlisted
program still runs arbitrary code within its own process (``cargo test``
compiles + runs test binaries and build scripts). The gate bounds
program+subcommand+known-escape-flags and declared write paths; it does not —
and cannot, without the cage — bound what admitted code then does.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from typing import Any, Mapping

# --------------------------------------------------------------------------
# The grant object.
#
# NOTE (estate correction, 2026-07-10): the synthetic-conveyor ``RationCard``
# is the WRONG object for a live run — its ``__post_init__`` hard-locks it
# observe-only (no writes/net/git), so gating a live build against it would
# refuse every edit. The live-run execution grant is assembled from the
# APPROVED PLAN: ``scope_allowlist`` -> write_paths, the declared shell
# allowlist -> shell_commands, with the dangerous axes locked. That assembly
# is the activation step (S2/S3); this pure gate only consumes the result.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CommandGrant:
    """A granted command family: ``program`` plus a required ``argv_prefix``.
    STRUCTURED, never a shell string — the boundary is program+args, so a
    command is only in-grant if its parsed tokens start with this exact prefix.
    ``cargo test`` → ``CommandGrant("cargo", ("test",))``."""

    program: str
    argv_prefix: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExecutionGrant:
    """The effect envelope a supervised run may act within, minted by
    ``activate()`` from the operator-approved plan (S2). Absence-restrictive:
    an empty ``write_paths`` means NO writes are granted; a command family not
    listed widens. Dangerous axes default locked and only widen (never silently
    admitted). This is the pure effect surface the gate checks; the first-class
    grant *artifact* (id / digest / horizon / source_plan_digest /
    approval_witness_digest / derivation_version) wraps it at activation."""

    write_paths: frozenset[str] = field(default_factory=frozenset)
    commands: tuple[CommandGrant, ...] = ()
    network_allowed: bool = False
    git_allowed: bool = False


# --------------------------------------------------------------------------
# Closed vocabulary (local to the gate; distinct from standing_grant_use's
# REASON_* which describe the EXTERNAL binary transport, not local scope).
# --------------------------------------------------------------------------

#: refusal_class for a widening decision (maps to GrantRefused in S2).
GRANT_SCOPE_WIDENED = "grant_scope_widened"

#: The axis a widening decision enlarged.
AXIS_WRITE_PATH = "write_path"
AXIS_SHELL = "shell"
AXIS_NETWORK = "network"
AXIS_GIT = "git"
WIDENED_AXES = frozenset({AXIS_WRITE_PATH, AXIS_SHELL, AXIS_NETWORK, AXIS_GIT})

#: Closed reasons for an unverifiable (fail-closed) decision.
GU_OPAQUE_SHELL = "opaque_shell"          # compound/wrapped shell — not structurally checkable
GU_UNKNOWN_TOOL = "unknown_tool"          # tool not recognized — cannot map to effects
GU_UNPARSEABLE_TARGET = "unparseable_target"  # known tool, but no extractable target
GU_EFFECT_ESCAPING_FLAG = "effect_escaping_flag"  # allowlisted program + a flag that relocates its effects
UNVERIFIABLE_REASONS = frozenset(
    {GU_OPAQUE_SHELL, GU_UNKNOWN_TOOL, GU_UNPARSEABLE_TARGET, GU_EFFECT_ESCAPING_FLAG}
)

#: Flags that let an allowlisted program relocate its filesystem/config effects
#: out of the granted envelope (write elsewhere, load a different project, or —
#: for `--config` — inject an executable runner). Presence on an allowlisted
#: command → Unverifiable (prompt), never a silent yes. NAMED + DOCUMENTED and
#: deliberately NON-EXHAUSTIVE: a command allowlist is not an effect boundary
#: (an allowlisted program still runs arbitrary code — e.g. `cargo test`
#: compiles + runs test binaries and build scripts). The real fence is the
#: armed sandbox (enforcement: declared-effects-only). This denylist only
#: raises the bar on the obvious escapes.
# MIRRORED cross-repo: maude's plan/ration_containment.py duplicates this list
# for S7 ration-citation containment (Maude cannot import AG internals). If this
# changes, update that mirror too — see agent_gov S7 design note § Cross-repo
# mirror.
_EFFECT_ESCAPING_FLAGS = frozenset({
    "-C", "--config", "--target-dir", "--out-dir", "--manifest-path", "--home",
})

# --------------------------------------------------------------------------
# Pure decision types. These map 1:1 to the GrantUseResult union in S2:
#   WithinGrant   -> GrantUsed        (mint receipt, silent approve)
#   WidensGrant   -> GrantRefused     (widening intervention / prompt)
#   Unverifiable  -> NoVerifiedResult (fail closed: deny/prompt)
# They are pre-receipt: a PURE function cannot mint GrantUsed's receipt_digest.
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class WithinGrant:
    """The call is inside the approved envelope. Proceed silently in S2."""

    action: str  # tool name
    target: str  # path / command / "<read>"


@dataclass(frozen=True)
class WidensGrant:
    """The call enlarges the envelope on exactly one named axis. Prompt."""

    refusal_class: str  # always GRANT_SCOPE_WIDENED
    axis: str           # one of WIDENED_AXES
    detail: str


@dataclass(frozen=True)
class Unverifiable:
    """The call cannot be cleanly classified. Fail closed (never a silent yes)."""

    reason: str  # one of UNVERIFIABLE_REASONS
    detail: str


GrantUseDecision = WithinGrant | WidensGrant | Unverifiable


# --------------------------------------------------------------------------
# Tool taxonomy (conservative; unknown → Unverifiable, never a default WRITE-yes).
# --------------------------------------------------------------------------

# MUST stay a subset of what the supervisor's classify_action() treats as READ
# — a tool this set calls a read but the supervisor calls a WRITE would be
# silently auto-approved by the gate with no grant check (the `ls` divergence
# bug). Pinned by test_read_tools_are_reads_for_supervisor.
_READ_TOOLS = frozenset({"read", "glob", "grep", "read_file", "grep_search"})
_WRITE_FILE_TOOLS = frozenset(
    {"write", "edit", "notebookedit", "replace", "write_file"}
)
_SHELL_TOOLS = frozenset({"bash", "run_shell_command", "shell"})

#: keys a write-file tool may carry the target path under.
_PATH_KEYS = ("file_path", "path", "notebook_path", "filepath")

#: shell metacharacters that make a command compound/opaque → not structurally
#: checkable. Presence of ANY → Unverifiable(opaque_shell). "bash -lc" wrappers
#: are caught separately. Shell strings are where authz becomes folklore.
_SHELL_METACHARS = ("|", ";", "&", "`", "$", "(", ")", "<", ">", "\n", "\\")

#: shell wrappers whose real command lives in an inner string → opaque.
_SHELL_WRAPPERS = frozenset({"bash", "sh", "zsh", "dash", "eval", "exec", "source", "."})

#: leading tokens that reach the network / external communication.
_NETWORK_PROGRAMS = frozenset({"curl", "wget", "ssh", "scp", "rsync", "nc", "telnet"})


def _path_within(path: str, allowed: frozenset[str]) -> bool:
    """Concrete-path containment against allow patterns. Prefix semantics for
    ``dir/**`` / ``dir/*``; exact match otherwise. ``..`` never contained."""
    if not path or ".." in path.split("/"):
        return False
    for pat in allowed:
        if pat.endswith("/**"):
            # any depth under the directory
            prefix = pat[:-2]  # "dir/**" -> "dir/"
            if path.startswith(prefix):
                return True
        elif pat.endswith("/*"):
            # exactly one level under the directory
            prefix = pat[:-1]  # "dir/*" -> "dir/"
            if path.startswith(prefix):
                rest = path[len(prefix):]
                if rest and "/" not in rest:
                    return True
        elif path == pat:
            return True
    return False


def _extract_path(tool_input: Mapping[str, Any]) -> str | None:
    for k in _PATH_KEYS:
        v = tool_input.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _classify_shell(command: str, grant: ExecutionGrant) -> GrantUseDecision:
    """Structured shell check. Compound/wrapped/unparseable → opaque (fail
    closed). A simple command is WITHIN only if its leading tokens match a
    granted shell_commands entry AND it touches no denied axis."""
    if not command.strip():
        return Unverifiable(GU_OPAQUE_SHELL, "empty command")
    if any(mc in command for mc in _SHELL_METACHARS):
        return Unverifiable(GU_OPAQUE_SHELL, "compound/opaque shell (metacharacters)")
    try:
        tokens = shlex.split(command)
    except ValueError:
        return Unverifiable(GU_OPAQUE_SHELL, "unparseable shell string")
    if not tokens:
        return Unverifiable(GU_OPAQUE_SHELL, "empty command")
    program = tokens[0]
    if program in _SHELL_WRAPPERS:
        # bash -c "..." hides its real command in a string — opaque by design.
        return Unverifiable(GU_OPAQUE_SHELL, f"shell wrapper {program!r} (inner command opaque)")

    # Denied-axis signals come BEFORE allowlist matching — a granted program
    # that reaches the network still widens.
    if program in _NETWORK_PROGRAMS and not grant.network_allowed:
        return WidensGrant(GRANT_SCOPE_WIDENED, AXIS_NETWORK, f"{program} reaches the network (grant locks network)")
    if program == "git" and not grant.git_allowed:
        return WidensGrant(GRANT_SCOPE_WIDENED, AXIS_GIT, "git invoked (grant locks git)")

    # Structured allowlist match: program must equal the grant's program and
    # the command's argv must START WITH the granted argv_prefix. Comparison is
    # on parsed tokens, never raw string — no folklore.
    args = tokens[1:]
    for cg in grant.commands:
        n = len(cg.argv_prefix)
        if program == cg.program and tuple(args[:n]) == cg.argv_prefix:
            # Allowlisted program+subcommand — but the suffix argv is
            # unconstrained. Refuse (prompt) if it carries a flag that relocates
            # the program's fs/config effects out of the envelope. Defense in
            # depth over the trust-labeled command match, NOT the boundary.
            escaping = _find_effect_escaping_flag(args)
            if escaping is not None:
                return Unverifiable(
                    GU_EFFECT_ESCAPING_FLAG,
                    f"allowlisted {cg.program!r} carries effect-relocating flag {escaping!r}",
                )
            return WithinGrant(action="shell", target=" ".join((cg.program, *cg.argv_prefix)))
    return WidensGrant(
        GRANT_SCOPE_WIDENED, AXIS_SHELL,
        f"command {program!r} not in the grant allowlist",
    )


def _find_effect_escaping_flag(args: list[str]) -> str | None:
    """Return the first effect-relocating flag in ``args`` (``--flag`` or
    ``--flag=value`` form), else None."""
    for tok in args:
        head = tok.split("=", 1)[0]
        if head in _EFFECT_ESCAPING_FLAGS:
            return head
    return None


def classify_grant_use(
    tool_name: str,
    tool_input: Mapping[str, Any] | None,
    grant: ExecutionGrant,
) -> GrantUseDecision:
    """Classify one supervised tool call against the approved execution grant.

    PURE. Fail-closed: ambiguity → Unverifiable; outside grant → WidensGrant;
    only a cleanly-classified, in-grant call → WithinGrant.
    """
    name = tool_name.lower().strip()
    ti: Mapping[str, Any] = tool_input or {}

    if name in _READ_TOOLS:
        # Reading is observation; it produces no write/net/git effect and is
        # always within the envelope.
        target = _extract_path(ti) or "<read>"
        return WithinGrant(action=name, target=target)

    if name in _WRITE_FILE_TOOLS:
        path = _extract_path(ti)
        if path is None:
            return Unverifiable(GU_UNPARSEABLE_TARGET, f"{name}: no extractable target path")
        if _path_within(path, grant.write_paths):
            return WithinGrant(action=name, target=path)
        return WidensGrant(
            GRANT_SCOPE_WIDENED, AXIS_WRITE_PATH,
            f"write path {path!r} outside the grant",
        )

    if name in _SHELL_TOOLS:
        command = ti.get("command") or ti.get("cmd") or ti.get("shell_command") or ""
        if not isinstance(command, str):
            return Unverifiable(GU_OPAQUE_SHELL, "non-string command payload")
        return _classify_shell(command, grant)

    # Unknown tool — cannot map to effects. Fail closed (never a default yes).
    return Unverifiable(GU_UNKNOWN_TOOL, f"tool {tool_name!r} not recognized by the grant-use gate")


__all__ = [
    "ExecutionGrant", "CommandGrant",
    "GrantUseDecision", "WithinGrant", "WidensGrant", "Unverifiable",
    "classify_grant_use",
    "GRANT_SCOPE_WIDENED", "WIDENED_AXES", "UNVERIFIABLE_REASONS",
    "AXIS_WRITE_PATH", "AXIS_SHELL", "AXIS_NETWORK", "AXIS_GIT",
    "GU_OPAQUE_SHELL", "GU_UNKNOWN_TOOL", "GU_UNPARSEABLE_TARGET",
    "GU_EFFECT_ESCAPING_FLAG",
]
