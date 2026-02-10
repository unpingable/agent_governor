# 0003 — Fiction/Code/Nonfiction Modes

## Status

Accepted

## Context

The governor constrains AI agent output. But governance has **opposite effects in different domains**:

| Domain | Governance visibility | What breaks trust |
|--------|----------------------|-------------------|
| Fiction | Must be invisible | "This was approved" kills the spell |
| Code | Must be visible and local | Invisible constraints kill accountability |
| Nonfiction | Must be invisible | "Predetermined conclusion" kills credibility |

A single governance mode cannot serve all three. In prose, visible governance reads as moderation and breaks immersion. In code, invisible governance reads as unowned liability — "committee code" where nobody takes responsibility. In nonfiction, visible governance reads as propaganda.

The load-bearing variable differs per domain:
- **Fiction**: Perceived Risk (R_p) — does this feel like it escaped supervision?
- **Code**: Accountability Clarity (A_p) — can I safely take custody of this?
- **Nonfiction**: Perceived Epistemic Honesty (E_p) — is the author constrained by evidence?

## Decision

Governance is split into domain-specific modes that share the same ledger architecture but apply different constraints:

- **Fiction mode** (`src/fiction_governor/`): Anchors (character bibles, world rules, canon events, plot threads) that silently block or allow output. Violations are resolved by the author (Fix/Revise/Proceed), never exposed to the audience.
- **Code mode** (`src/governor/`): Typed claims with receipts. Decisions are explicit. Failures are named and bounded. Governance contracts are visible in the output because that's how code earns trust.
- **Nonfiction mode** (`src/nonfiction_governor/`): Claims tracked with provenance and evidence requirements. Source quality must match certainty. Violations are internal editorial corrections, not visible constraints.

All modes share: ledger architecture (facts vs decisions), receipt-based verification, claim-structure validation, the proposal/commit split.

**"Same math. Different sign. Same governor architecture, different constraints."**

## Consequences

- **Retry/recovery loops differ per mode.** Fiction: rephrase to comply (invisibly). Code: add contracts/tests/bounds (visibly). Nonfiction: verify/soften/remove claim (internally).
- **Separate governor packages.** Fiction, nonfiction, and ops each get their own `src/` directory with domain-specific types, verifiers, and CLI. This prevents cross-domain constraint leakage.
- **Mode detection matters.** If the system is in fiction mode but the user switches to code, the constraint set must change. The mode detection subsystem (2.1-C) exists because getting this wrong applies the wrong polarity.
- **The universal invariant has a sign bit.** "Language earns trust when it makes the cost of being wrong legible to the reader." In prose: expose epistemic risk, hide governance. In code: expose operational risk, surface governance.

## Source

- `specs/core/CODE_SRE_CONTROLLER_SPEC.md` ("Code is not prose. The governance polarity inverts.")
- `specs/core/AUTHORIAL_CONTROL_SYSTEM_SPEC.md` (fiction governance invisibility)
- `specs/core/NONFICTION_CONTROLLER_SPEC.md` (nonfiction epistemic honesty)
