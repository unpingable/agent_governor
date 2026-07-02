# Phosphor lane machinery — LaneSpec (feeds R-PHOS-2)

**Status:** RATIFIED machinery (2026-07-02). This is the **machinery half**
of R-PHOS-2 only: the lane abstraction both target lanes instantiate. The
ops-casework lane's CONTENT (case-card ontology, source boundaries, next-safe-
move surface) remains the operator-owned design in
`docs/roadmaps/tools/phosphor.md` R-PHOS-2 — nothing here pre-empts it.

## Finding this fixes

Phosphor's "lanes" are a metaphor: env-var-switched modes hardcoded across
~50 `GOVERNOR_MODE` branches in a 4,493-line adapter.py, with no registry, no
dispatcher, no sidebar factory. The sound parts — daemon delegation enforced
by parity tripwire tests, the mode-agnostic artifact engine, the capture loop
— are exactly what the abstraction should preserve and generalize.

## LaneSpec (minimal: a dataclass and a dispatcher, NOT a framework)

```python
@dataclass(frozen=True)
class LaneSpec:
    lane_id: str                      # "governed-session", "ops-casework", ...
    routes: tuple[RouteSpec, ...]     # (page_id, path, handler module)
    sidebar: tuple[NavSlot, ...]      # label, icon, route, badge_source
    artifact_kinds: tuple[str, ...]   # what it may read/write via the artifact engine
    capture_kinds: tuple[str, ...]    # chips → accept → receipt kinds
    daemon_methods: tuple[str, ...]   # enumerated RPC allowlist for this lane
```

## The lane contract: two enforced, testable rules

1. **Every governance-relevant (mutating) action goes through a method in
   `daemon_methods`.** The existing 5 parity tripwires generalize into
   **per-lane generated tests**: no direct governor imports on mutating
   paths; no RPC calls outside the lane's allowlist. (The tripwire pattern is
   phosphor's best idea — promoted from hand-written to generated.)
2. **Lanes render substrate refusals verbatim and add none.** NQ testifies,
   Nightshift classifies, AG governs, ticketing coordinates, the operator
   decides — a lane is glass, not a gavel.

Deliberately NOT in LaneSpec: data-source ontology (which NQ/ticket fields a
lane consumes is lane content, not machinery — the casework lane's source
boundaries are R-PHOS-2's operator design); middleware/hooks/plugin systems
(framework creep is the stop condition on GS-16).

## The two instantiating lanes

**Governed-session lane v0 (GS-17)** — the web mirror of maude's desk:
- pages: queue · session view · sessions board (diff rides the promotion
  card, as in maude).
- backend: proxies `libs/ag_shell_client`; **RPC-only** — this lane has NO
  direct-import read path, which begins the retirement of the split-brain
  architecture (and with it the PHOSPHOR_COMPAT_UNVERIFIED_281 failure
  class). SSE relays `operator.watch` to the browser with since_seq resume.
- `daemon_methods = {operator.decisions.*, operator.watch, runtime.session.*,
  runtime.budget.get, why.chain}`.

**Ops-casework lane (later; content = operator's R-PHOS-2)**:
- `daemon_methods = {operator.decisions.*, receipts.*, claims.*}` (adjust at
  design time); NQ/ticket sources composed lane-side, never through AG.
- Rides the same decision envelope — `refs[]` (nq_finding, ticket) is already
  in the contract so no schema break is needed when this lane lands.

## Existing modes (ratified: new-lanes-only, D-GS-3)

fiction/code/research stay on the env-var path for now; converting them to
LaneSpec is a later separable slice with its own record. The registry must
not require their conversion to function (coexistence is a GS-16 acceptance
criterion in effect: new lanes route through the registry, old modes are
untouched).
