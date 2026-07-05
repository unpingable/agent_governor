# Agent Integration Contract (v1)

**Status: v1 — RATIFIED 2026-07-05 (operator, Option A per docs/campaigns/public-mvp/ratification-memo-work-container-v1.md). First provider: claude_code, STRUCTURALLY conformant (registered, fail-closed) with live supervised evidence via CD-4B (sess_aabb2a056f9f); RUNTIME (container-consumption) conformance not yet demonstrated — gated on S4 dispatch wiring. Schema changes from here are versioned (v1 → v2), not silent.** This document is a
**formalization over surfaces that already exist and already enforce the law** —
it adds a name and a closed vocabulary, not new enforcement.

> This contract exports AG's existing admission and rationing machinery to agents
> and providers. It is not a replacement authority layer. Agents may propose;
> providers may perform or testify; only AG admits reliance.

> **This slice exports names for existing law; it does not create a new authority
> surface.**

This is a projection of the shared law in
[`work-container-contract.md`](work-container-contract.md) onto the **agent → AG**
direction. Read that document first.

An *agent* is an external actor that asks AG what it may do and submits proposed
work (Claude Code, Codex, Antigravity-as-agent, Hermes-hosted agents). Contrast a
*provider* (`provider-integration.md`), which *performs* work.

---

## 1. What an agent MAY do

Every verb below already has a concrete surface on the daemon
(`src/governor/daemon.py`) or the MCP server (`src/governor/mcp_server.py`). This
contract names them as one membrane; it does not add authority.

| Agent may…                        | Existing surface                                             |
| --------------------------------- | ----------------------------------------------------------- |
| submit a proposal (claims)        | `governor_propose` (MCP); FSM DRAFT→PROPOSED                 |
| request verification of a proposal| `governor_verify` (MCP) — runs external verifiers → receipts |
| submit a plan-envelope            | `run <plan.md>` ingress (`plan-envelope-v0`, maude M-2)     |
| claim/reserve work scope          | `task.claim` / `task.heartbeat` / `task.complete` (RPC)     |
| attach evidence / materials       | `governor_verify` pointers; proposal materials              |
| ask for current decision state    | `governor_status`, `commit.pending`, docket query (RPC/MCP) |
| report / fix a blocked item       | `commit.fix` / `commit.revise` (RPC) — validated externally |
| request reconsideration           | `commit.revise`; resubmit a narrowed proposal               |
| read receipts (audit)             | `receipts.list` / `receipts.detail` (read-only)             |

**Proposal is speech, not authority.** `plan_review.py`: a `Proposal` is an inert,
content-addressed language object; an `Agenda` is the authority object, derived
only from a proposal *plus explicit human review decisions* via
`compile_agenda()`. The agent authors proposals; it never authors decisions.

## 2. What an agent MAY NOT do (already blocked)

None of these are new prohibitions — each is already unreachable through the
existing surfaces. This contract just states them as a closed list.

| Agent may NOT…                        | Why it's already impossible                                    |
| ------------------------------------- | -------------------------------------------------------------- |
| approve its own proposal              | only `authorize_agenda()` confers force; operator-only (`ROLE_AUTHORITY`) |
| promote an artifact into a receipt    | receipts are minted by verifiers/gates, not agents (NLAI)      |
| self-grant standing                   | standing is verified AG-side (`standing_client`), never asserted |
| expand scope silently                 | `reservations.py` hard-gates scope by *registered* permissions |
| mutate doctrine / anchors / policy    | no RPC/MCP tool exists to write them                           |
| mark a receipt valid                  | `receipt_id` is content-addressed; a claim can't backdate authority |
| external-send without admitted scope  | egress gate + `output_is_observe_only` RationCard axis          |
| auto-resolve a docket case            | docket rulings are operator-only (`operator.decisions.resolve`) |

**The deep enforcement is NLAI** ("Language is a proposal, not an authority",
`src/governor/types.py`, `verifiers.py`, `producers.py`): an agent supplies
*pointers*; AG produces *receipts*. Agent success is testimony, never authority.

## 3. Admissibility push-back

When a proposal is underspecified, AG pushes back rather than guessing
(`admissibility.py`): `PROCEED` (A≥0.7) · `SOFT` (cap confidence) · `HARD` (deny
COMMIT, ask up to 3 clarifying questions) · `SAFE` (any S3/irreversible unknown →
block actuation regardless of score). A waiver does not clean-pass — it emits
`proceed` with an explicit **unsettled claim** naming what was *not* certified, so
a downstream consumer can still refuse.

## 4. Closed error / refusal vocabulary

Reuse the existing typed refusals; do not invent per-call strings:
`plan-envelope-v0` refusal classes (`invalid_plan_envelope`,
`submitter_limits_missing`, `governance_not_approved`, `governance_ref_mismatch`,
`governance_approval_unverified`); reservation errors (`AgentNotRegistered`,
`PermissionDenied`, `ScopeConflict`, `TaskNotOwned`); admissibility modes (§3).

## 5. Relationship to WorkContainer

An agent submits a **Proposal** or **plan-envelope** (a *request*). AG admits and
rations it. The **WorkContainer** is what AG *emits* afterward (an admitted,
bounded instruction) — the agent does not author a WorkContainer, and a provider
never receives a raw agent proposal. See `work-container-contract.md` §1.

## 6. Not in this slice

- No new HTTP endpoints. The daemon JSON-RPC + MCP surfaces already are the
  transport; an HTTP re-export is a later slice once this contract is ratified.
- No new convenience RPC (e.g. a single propose→decision round-trip) is *built*
  here; it is only *named* as a candidate.
- **Open question the reviewer should weigh in on:** is the existing
  `RuntimeAdapter` protocol enough to also describe agent runtimes, or is a thin
  `ProviderAdapter` super-protocol needed? Posed here; not answered in code.
