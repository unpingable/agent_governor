# Gap Spec: Substrate Custody — Steals from Vitalik's Local LLM Setup

**Status:** proposed (multiple bounded slices)
**Affects:** scope governor, supervised sessions, action classification
**Date:** 2026-04-02
**Origin:** Vitalik Buterin's self-sovereign LLM post (2026-04-02) + Governor crosswalk

## Context

Vitalik independently arrived at "model as untrusted proposer, custody at the boundary" from the crypto self-custody direction. His setup uses bubblewrap sandboxing, per-tool daemons, tiered autonomy for wallet actions, and read-yes/write-gated communication. Governor already does most of this at the policy layer but doesn't reach down to the OS substrate or distinguish communication from file writes.

Four concrete steals, ordered by impact.

---

## 1. Communication as a first-class action class

**Problem:** Governor treats "send a Slack message" and "write a local file" as the same action class (write). They have radically different blast radius: a file write is local and reversible, a message send is external, social, reputationally irreversible, and potentially identity-bearing.

**Proposed:** Add an `COMMUNICATE` action class alongside READ and WRITE. Tool contracts declare which class they belong to. Communication-class actions get:
- Distinct approval policy (never auto-approve in supervised mode)
- Content preview in intervention UI (show the message, not just "Bash wants to run")
- Destination classification (internal vs external, known vs unknown recipient)
- Higher default severity in scope governor

**Scope:** Scope governor tool contracts (`scope.py`), supervised session write-tool classification (`runtime/adapters/`), Maude intervention display.

**Size:** Small-medium. Tool contract change + adapter classification update + Maude UI tweak.

---

## 2. Pattern-aware approval (sequence governance)

**Problem:** Governor's gate evaluates one action at a time. A stateless boundary can approve 50 individually reasonable actions that are collectively catastrophic (salami slicing, slow credential exfiltration, progressive scope creep across tool calls).

**Proposed:** Rolling-window sequence analysis at the gate level:
- Track action class × target × frequency in a sliding window per session
- Escalate approval requirements when accumulation exceeds thresholds
- Cross-tool correlation: read(secrets) followed by communicate(external) triggers composition alert even if each is individually allowed
- Surface accumulation in Maude's status bar / snapshot view

This extends the existing chain gate (composition governance) and override accumulation signal (Δr→Δw) into a unified sequence-aware approval layer.

**Note:** Governor already has the chain gate (`chain_gate.py`) for composition rules (secret read → network egress = blocked). This extends that from binary rules to graduated accumulation.

**Size:** Medium. New accumulation tracker, chain gate extension, Maude display.

---

## 3. Scope governor emitting sandbox configs

**Problem:** Governor's scope governor constrains where agents act at the policy level (axis-based containment). But the enforcement is in Governor's process, not at the OS level. A compromised or buggy agent could bypass the policy layer and access files/network directly.

**Proposed:** Scope governor emits a machine-readable sandbox config alongside its policy decisions:
- Filesystem: allowed paths → bubblewrap `--ro-bind` / `--bind` directives
- Network: allowed ports/hosts → firewall rules or bubblewrap `--unshare-net` + specific binds
- The sandbox config is a **compiled artifact** from the scope policy (same pattern as Policy IR: policy → renderer → artifact)

This moves one layer down: from "policy as interpretation" to "policy as substrate." The supervised session launcher could apply the sandbox config when spawning the agent process.

**Size:** Medium-large. New renderer for scope → sandbox config, launcher integration.

**Deferred aspect:** This probably wants OS-specific adapters (bubblewrap on Linux, Seatbelt on macOS). Start with bubblewrap only.

---

## 4. Local knowledge store as query minimization

**Problem:** Every web search or remote API call is a context injection opportunity. Vitalik's approach: download Wikipedia, docs, and reference material locally, reducing the need for remote queries during agent sessions.

**Proposed:** Governor-aware local knowledge index:
- Curated local docs registered as trusted context sources
- GovernorHooks can inject relevant local docs into context instead of the model reaching for web search
- Provenance label: `source_class: repo` (trusted) vs `source_class: web` (untrusted)
- Context manifest tracks which knowledge sources contributed to each prompt

**Size:** Small. Mostly a Maude/operator workflow concern. Governor's provenance labels already distinguish source classes.

---

## Non-goals

- Not replacing bubblewrap, Seatbelt, or any OS sandbox
- Not building a full network firewall
- Not implementing wallet-grade crypto custody (that's standing/WLP territory)
- Not auto-detecting salami attacks with ML (the accumulation tracker is threshold-based, not learned)

## Priority order

1. Communication action class (highest impact, smallest change)
2. Pattern-aware approval (biggest defensive value)
3. Sandbox config emission (deepest substrate reach)
4. Local knowledge store (nice-to-have, mostly operator workflow)
