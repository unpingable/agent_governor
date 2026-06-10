# SPDX-License-Identifier: Apache-2.0
"""
Status: S5 landing — `why <receipt-id>` join surface
Authority: read-only renderer over GateReceiptSystem
Promotion: stable when D0 demo lands; supersession requires S4-lite reopen

`why <receipt-id>` — render the receipt chain back to its origin.

The S5 slice in
``working/campaign-standing-before-spendability.md`` says:

  > Goal: extend governor receipts to join across ledgers: AG receipt →
  > admission receipt → standing receipt chain → originating NQ finding.
  > Read-only. One command, full provenance, works on refusals too.

This module is the join: it reads from the existing ``GateReceiptSystem``
(``ReceiptStore`` JSONL + ``EvidenceStore`` content-addressed blobs at
``src/governor/gate_receipt.py``) and renders the chain — for refusals,
bypasses, and happy paths — uniformly.

Hard rules honored (per S5 spec):

1. **No new top-level receipt store.** ``GateReceiptSystem`` is the
   single source of truth.
2. **Closed refusal vocabulary only.** Imported from
   ``linear_accountant_client.CLOSED_REFUSAL_KINDS``. Receipts whose
   ``refusal_kind`` is not in that set render as
   ``stale vocabulary: <kind>`` with a warning marker — NOT auto-corrected,
   NOT crashed.
3. **Bypass rendered as bypass, not refusal.** A receipt whose
   ``refusal_kind`` equals ``BYPASS_BA3_FOR_MVP`` (the closed-vocabulary
   bypass kind, also imported from ``linear_accountant_client``) renders
   with the ``BYPASS`` prefix (not ``REFUSED``) and a pointer to
   ``working/post-mvp-debt-ba3-hardshort-to-la.md``. Stays visibly weird
   by design.
4. **Absence is rendered, not erred.** Unknown receipt id → "receipt id
   not found". Missing evidence blob → "evidence blob missing for hash
   sha256:...". Chain gap → "no standing receipt cited". No tracebacks.

Chain semantics:

The join surface between receipts is the evidence bundle. A receipt's
``evidence_hash`` retrieves the bundle from ``EvidenceStore``; the bundle
may carry a ``parent_receipt_ids`` field (a list of strings) naming the
prior gate receipts that this one cites. ``why`` walks that list back to
the origin, rendering each link. If a parent id is named but not present
in the ``ReceiptStore``, the link is rendered as a dangling reference and
the walk terminates cleanly — no traceback.

This is intentionally the minimal join. Cross-tool receipt schema
unification is out (v2, per cut list). The current contract is: AG-side
producers that want to be ``why``-walkable include
``parent_receipt_ids: list[str]`` in their evidence bundle. Receipts that
don't include it terminate at themselves, which is what "this is the
origin from AG's vantage" already means.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .cooked_context_orchestrator import (
    EVIDENCE_KEY_ORIGIN_MODE,
    NQ_ORIGIN_MODES,
    ORIGIN_MODE_DRILL,
    ORIGIN_MODE_OBSERVED,
    ORIGIN_MODE_REPLAY,
    ORIGIN_MODE_SYNTHETIC,
)
from .gate_receipt import GateReceipt, GateReceiptSystem
from .linear_accountant_client import (
    BYPASS_BA3_FOR_MVP,
    CLOSED_REFUSAL_KINDS,
)


# ---------------------------------------------------------------------------
# Origin-mode render vocabulary (D0-Bridge, 2026-06-09).
#
# Cross-repo bridge: AG consumes the NQ-side ``origin_mode`` discriminator
# from each gate receipt's ``evidence_bundle["origin_mode"]`` (stamped on
# every emit by ``_OriginModeReceiptSink`` in cooked_context_orchestrator).
# When the chain's origin is non-observed, ``governor why`` renders a
# closed-vocabulary prefix at the top of output so the operator never
# mistakes a drilled chain for an observed one.
#
# Mapping is verbatim from the NQ-side concrete value to an uppercase
# display label. AG does NOT invent new render modes; this map and the
# NQ-side closed vocabulary stay synchronized.
# ---------------------------------------------------------------------------

# The render labels — closed set, uppercase by convention.
RENDER_PREFIX_DRILL = "DRILL"
RENDER_PREFIX_REPLAY = "REPLAY"
RENDER_PREFIX_SYNTHETIC = "SYNTHETIC"

# Map NQ origin_mode → render prefix for non-observed origins.
# ``observed`` deliberately absent: it is the no-render-prefix case.
NON_OBSERVED_RENDER_PREFIX: dict[str, str] = {
    ORIGIN_MODE_DRILL: RENDER_PREFIX_DRILL,
    ORIGIN_MODE_REPLAY: RENDER_PREFIX_REPLAY,
    ORIGIN_MODE_SYNTHETIC: RENDER_PREFIX_SYNTHETIC,
}


# ---------------------------------------------------------------------------
# Pointer text — must point at the BA3 debt artifact per S5 spec.
# ---------------------------------------------------------------------------

BA3_DEBT_POINTER = "working/post-mvp-debt-ba3-hardshort-to-la.md"


# ---------------------------------------------------------------------------
# Result types.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChainLink:
    """One step in the walked chain.

    A link can be one of:

      * resolved        — receipt present in the store; ``receipt`` is set,
                          ``kind`` describes its outcome shape, ``warnings``
                          flags stale-vocabulary or missing-evidence-blob.
      * receipt_missing — a parent_receipt_id was cited but the receipt is
                          not in the store. ``receipt`` is None.
                          ``cited_id`` carries the dangling reference.
      * cycle_detected  — the walk re-encountered a receipt it already
                          rendered. ``receipt`` is set to the offending one.

    ``warnings`` is a list of human-readable strings. Empty is fine.
    """

    status: str  # "resolved" | "receipt_missing" | "cycle_detected"
    cited_id: str
    receipt: GateReceipt | None
    evidence_bundle: dict[str, Any] | None
    # Outcome classification — only meaningful for ``resolved`` links.
    # One of: "refusal", "bypass", "stale_vocabulary", "non_refusal".
    kind: str
    refusal_kind: str | None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WhyResult:
    """Aggregate result of the join: ordered list of links, root last.

    ``found`` is False iff the originally-requested receipt id is unknown.
    All other absence/gap conditions are represented inside ``links`` and
    must NOT set ``found=False``.
    """

    requested_id: str
    found: bool
    links: list[ChainLink] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Classification — closed-vocabulary discipline.
#
# These functions never raise on bad input; they classify into a closed
# set and let the renderer surface the classification.
# ---------------------------------------------------------------------------


def _extract_refusal_kind(evidence_bundle: dict[str, Any] | None) -> str | None:
    """Return the refusal_kind string from the bundle, or None.

    The evidence bundle is the convention by which AG-side seams encode
    refusal kind (see ``linear_accountant_client.RefusalResult`` and the
    standing/wicket client error refusal_kind attributes). When the
    bundle is None (missing evidence blob), return None — the caller
    will surface the absence as a warning, not a refusal classification.
    """
    if evidence_bundle is None:
        return None
    value = evidence_bundle.get("refusal_kind")
    if isinstance(value, str) and value:
        return value
    return None


def _classify(refusal_kind: str | None) -> str:
    """Classify a refusal_kind string into a closed-vocabulary outcome.

    Returns one of:

      * ``non_refusal``      — no refusal_kind in evidence (happy path,
                               or any receipt where the seam did not
                               annotate a refusal).
      * ``bypass``           — refusal_kind equals the closed bypass
                               sentinel ``BA3_BYPASSED_FOR_MVP``.
      * ``refusal``          — refusal_kind is in CLOSED_REFUSAL_KINDS.
      * ``stale_vocabulary`` — refusal_kind is a non-empty string but
                               not in either closed set. We render it
                               with a warning marker. Do NOT auto-correct.
    """
    if refusal_kind is None:
        return "non_refusal"
    if refusal_kind == BYPASS_BA3_FOR_MVP:
        return "bypass"
    if refusal_kind in CLOSED_REFUSAL_KINDS:
        return "refusal"
    return "stale_vocabulary"


def _extract_origin_mode(evidence_bundle: dict[str, Any] | None) -> str | None:
    """Return the NQ-side origin_mode string from the bundle, or None.

    The bridge convention: every receipt emitted via
    ``_OriginModeReceiptSink`` carries
    ``evidence_bundle["origin_mode"]`` (see
    cooked_context_orchestrator). When that value is one of the NQ-side
    modes, the chain's origin is non-AG-internal and the renderer
    surfaces it as a top-of-output prefix.

    Returns None when the bundle is missing, the key is absent, the
    value is not a string, or the value is not in the NQ-side set —
    AG-internal modes (cli_origin, stub_origin) are explicitly not
    rendered as origin prefixes (they are AG's own labeling and do not
    speak to upstream witness provenance).
    """
    if evidence_bundle is None:
        return None
    value = evidence_bundle.get(EVIDENCE_KEY_ORIGIN_MODE)
    if not isinstance(value, str) or not value:
        return None
    if value not in NQ_ORIGIN_MODES:
        return None
    return value


def _chain_origin_mode(result: WhyResult) -> str | None:
    """Determine the chain's NQ-side origin mode, if any.

    Walks the chain's resolved links and returns the first NQ-side
    origin_mode found. The chain root (closest to the requested receipt)
    wins — the origin is the chain's deepest receipt-bound provenance,
    but since the discriminator is propagated through every emit by
    ``_OriginModeReceiptSink``, every emitted link carries the same
    value. We take the first resolved link's value as the canonical
    answer.

    Returns None when no resolved link carries a recognized NQ-side
    origin_mode. The AG-internal modes (``cli_origin``, ``stub_origin``)
    return None here because they are not upstream-witness origins.
    """
    for link in result.links:
        if link.status != "resolved":
            continue
        mode = _extract_origin_mode(link.evidence_bundle)
        if mode is not None:
            return mode
    return None


def _parent_ids(evidence_bundle: dict[str, Any] | None) -> list[str]:
    """Extract the ordered list of cited parent receipt ids.

    The convention: ``parent_receipt_ids`` is a list of strings inside
    the evidence bundle. Any other shape is ignored — we do NOT invent
    silent fallbacks (e.g. ``standing_receipt_id`` alone), because the
    closed join surface is what makes the walk auditable.

    Returns empty list when the bundle is None, missing the field, or
    has a malformed value. Missing != crash.
    """
    if evidence_bundle is None:
        return []
    raw = evidence_bundle.get("parent_receipt_ids")
    if not isinstance(raw, list):
        return []
    return [item for item in raw if isinstance(item, str) and item]


# ---------------------------------------------------------------------------
# Chain walk.
# ---------------------------------------------------------------------------


def walk_chain(
    system: GateReceiptSystem,
    receipt_id: str,
    *,
    max_depth: int = 64,
) -> WhyResult:
    """Walk a receipt's parent chain back to its origin.

    Returns a ``WhyResult``. Never raises on:

      * unknown receipt id (``found=False``, empty links)
      * missing evidence blob (link.evidence_bundle=None,
        warning recorded)
      * dangling parent receipt id (link.status="receipt_missing")
      * malformed refusal_kind (link.kind="stale_vocabulary",
        warning recorded)
      * cyclical parent references (link.status="cycle_detected",
        walk terminates)
      * depth overflow (walk terminates at max_depth; final link
        carries a warning)
    """
    root = system.receipt_store.get_by_id(receipt_id)
    if root is None:
        return WhyResult(requested_id=receipt_id, found=False, links=[])

    links: list[ChainLink] = []
    seen: set[str] = set()
    cursor: GateReceipt | None = root
    cursor_id: str = receipt_id

    for _ in range(max_depth):
        if cursor is None:
            break

        # Cycle detection.
        if cursor.receipt_id in seen:
            links.append(
                ChainLink(
                    status="cycle_detected",
                    cited_id=cursor.receipt_id,
                    receipt=cursor,
                    evidence_bundle=None,
                    kind="non_refusal",
                    refusal_kind=None,
                    warnings=[
                        f"cycle detected: receipt {cursor.receipt_id[:12]}..."
                        " was already rendered earlier in this chain"
                    ],
                )
            )
            break
        seen.add(cursor.receipt_id)

        # Resolve evidence bundle. Absence is rendered, not erred.
        bundle = system.evidence_for(cursor)
        warnings: list[str] = []
        if bundle is None:
            warnings.append(
                f"evidence blob missing for hash sha256:{cursor.evidence_hash}"
            )

        refusal_kind = _extract_refusal_kind(bundle)
        kind = _classify(refusal_kind)
        if kind == "stale_vocabulary":
            warnings.append(
                f"stale vocabulary: {refusal_kind!r} is not in the"
                " current closed refusal set (S4-lite)"
            )

        links.append(
            ChainLink(
                status="resolved",
                cited_id=cursor_id,
                receipt=cursor,
                evidence_bundle=bundle,
                kind=kind,
                refusal_kind=refusal_kind,
                warnings=warnings,
            )
        )

        # Walk to first parent. ``parent_receipt_ids`` is a list, but the
        # demo chain is linear (standing → admission → capacity → effect).
        # Multi-parent fan-in is out of scope for S5; we walk the first
        # parent and surface the rest as warnings on the final link.
        parents = _parent_ids(bundle)
        if not parents:
            break

        if len(parents) > 1:
            # Don't drop them silently. Surface the extras as a warning
            # on the current link so a reviewer sees that the walk took
            # only the first parent.
            extras = ", ".join(p[:12] + "..." for p in parents[1:])
            # Append to the just-pushed link's warnings via a rebuild
            # because ChainLink is frozen.
            current = links[-1]
            new_warnings = list(current.warnings) + [
                f"receipt cites {len(parents)} parents; walk follows the"
                f" first only. Other cited ids: {extras}"
            ]
            links[-1] = ChainLink(
                status=current.status,
                cited_id=current.cited_id,
                receipt=current.receipt,
                evidence_bundle=current.evidence_bundle,
                kind=current.kind,
                refusal_kind=current.refusal_kind,
                warnings=new_warnings,
            )

        next_id = parents[0]
        next_receipt = system.receipt_store.get_by_id(next_id)
        if next_receipt is None:
            links.append(
                ChainLink(
                    status="receipt_missing",
                    cited_id=next_id,
                    receipt=None,
                    evidence_bundle=None,
                    kind="non_refusal",
                    refusal_kind=None,
                    warnings=[
                        f"no receipt found for cited parent {next_id};"
                        " chain terminates at this gap"
                    ],
                )
            )
            break

        cursor = next_receipt
        cursor_id = next_id
    else:
        # Loop completed without break — depth was exhausted.
        if links:
            current = links[-1]
            new_warnings = list(current.warnings) + [
                f"chain walk halted at max_depth={max_depth};"
                " deeper ancestry not rendered"
            ]
            links[-1] = ChainLink(
                status=current.status,
                cited_id=current.cited_id,
                receipt=current.receipt,
                evidence_bundle=current.evidence_bundle,
                kind=current.kind,
                refusal_kind=current.refusal_kind,
                warnings=new_warnings,
            )

    return WhyResult(requested_id=receipt_id, found=True, links=links)


# ---------------------------------------------------------------------------
# Rendering.
# ---------------------------------------------------------------------------


def _render_link_header(link: ChainLink, depth: int) -> str:
    """Return the one-line header for a chain link.

    Distinctness invariants (from S5 spec):

      * BYPASS prefix for bypass receipts (NOT REFUSED).
      * REFUSED prefix for closed-set refusals.
      * STALE-VOCAB prefix for unknown kinds.
      * OK prefix for non-refusal receipts (happy path).
      * MISSING prefix for dangling parent references.
      * CYCLE prefix for cycle detection.

    Two-space indent per depth so chains read as a tree.
    """
    indent = "  " * depth

    if link.status == "receipt_missing":
        return f"{indent}MISSING  no receipt found for cited id {link.cited_id}"

    if link.status == "cycle_detected":
        rid_short = link.cited_id[:12] + "..."
        return (
            f"{indent}CYCLE    receipt {rid_short} re-encountered;"
            " walk terminates"
        )

    # status == "resolved"
    r = link.receipt
    assert r is not None  # status invariant
    rid_short = r.receipt_id[:12] + "..."
    gate = r.gate
    ts = r.timestamp

    if link.kind == "bypass":
        return (
            f"{indent}BYPASS   {link.refusal_kind}  gate={gate}  "
            f"id={rid_short}  ts={ts}"
        )
    if link.kind == "refusal":
        return (
            f"{indent}REFUSED  {link.refusal_kind}  gate={gate}  "
            f"id={rid_short}  ts={ts}"
        )
    if link.kind == "stale_vocabulary":
        return (
            f"{indent}STALE-VOCAB {link.refusal_kind!r}  gate={gate}  "
            f"id={rid_short}  ts={ts}"
        )
    # non_refusal
    return (
        f"{indent}OK       verdict={r.verdict}  gate={gate}  "
        f"id={rid_short}  ts={ts}"
    )


def render_text(result: WhyResult) -> str:
    """Render a WhyResult as plain text suitable for the terminal.

    Output shape (no surprises):

        why <receipt-id>
        ──────────────────────
        REFUSED  capacity_refused  gate=la_seam  id=abc123...  ts=...
          parent: ...
          OK     verdict=pass  gate=wicket_seam  ...
            OK     verdict=pass  gate=standing_seam  ...

    Absence:

        why <receipt-id>
        receipt id not found: <receipt-id>

    Bypass receipts always include the BA3 debt pointer line.
    """
    lines: list[str] = []
    lines.append(f"why {result.requested_id}")
    lines.append("─" * 22)

    if not result.found:
        lines.append(f"receipt id not found: {result.requested_id}")
        return "\n".join(lines) + "\n"

    if not result.links:
        # found=True but no links — shouldn't happen, but render cleanly.
        lines.append("(receipt resolved but no chain rendered)")
        return "\n".join(lines) + "\n"

    # Cross-repo bridge prefix (D0-Bridge): when the chain's NQ-side
    # origin mode is non-observed, surface a closed-vocabulary header at
    # the top so the operator never mistakes a drilled / replayed /
    # synthetic chain for an observed one. Observed origins (and chains
    # without any NQ-side origin) render with no prefix.
    chain_origin = _chain_origin_mode(result)
    if chain_origin in NON_OBSERVED_RENDER_PREFIX:
        prefix = NON_OBSERVED_RENDER_PREFIX[chain_origin]
        lines.append(
            f"{prefix}  chain origin: {chain_origin!r} "
            f"(NQ-side mint provenance — receipt does NOT carry an "
            f"observed-condition witness)"
        )
        lines.append("─" * 22)

    saw_bypass = False
    for depth, link in enumerate(result.links):
        lines.append(_render_link_header(link, depth))
        for warning in link.warnings:
            lines.append(("  " * depth) + "  ! " + warning)
        if link.kind == "bypass":
            saw_bypass = True
            lines.append(
                ("  " * depth)
                + f"  → see: {BA3_DEBT_POINTER}"
            )

    if saw_bypass:
        lines.append("")
        lines.append(
            "note: BYPASS lines are operator-ratified MVP-harness suppressions"
            f" of AG-internal BA3 surfaces; see {BA3_DEBT_POINTER}."
        )

    return "\n".join(lines) + "\n"


def render_json(result: WhyResult) -> dict[str, Any]:
    """Render a WhyResult as a JSON-friendly dict.

    The JSON shape mirrors the text but is intended for machine consumption
    (mirrors the convention of ``governor receipts --json``). Receipts are
    fully unpacked via ``GateReceipt.to_dict``; evidence bundles are
    included when present so downstream tools have the full join in one
    object.
    """
    payload_links: list[dict[str, Any]] = []
    for link in result.links:
        item: dict[str, Any] = {
            "status": link.status,
            "cited_id": link.cited_id,
            "kind": link.kind,
            "refusal_kind": link.refusal_kind,
            "warnings": list(link.warnings),
        }
        if link.receipt is not None:
            item["receipt"] = link.receipt.to_dict()
        if link.evidence_bundle is not None:
            item["evidence"] = link.evidence_bundle
        if link.kind == "bypass":
            item["debt_pointer"] = BA3_DEBT_POINTER
        payload_links.append(item)
    payload: dict[str, Any] = {
        "requested_id": result.requested_id,
        "found": result.found,
        "links": payload_links,
    }
    # Cross-repo bridge: surface chain-level NQ-side origin mode so a
    # JSON consumer never has to walk the link list to learn whether
    # the chain is observed / drill / replay / synthetic. Top-level
    # ``drill: true`` is the campaign-card-specified shape for the
    # non-observed case (per D0-Provenance DoD); we generalize it to
    # one field per non-observed mode so the JSON consumer can branch
    # mechanically.
    chain_origin = _chain_origin_mode(result)
    if chain_origin is not None:
        payload["origin_mode"] = chain_origin
        if chain_origin in NON_OBSERVED_RENDER_PREFIX:
            payload["drill"] = chain_origin == ORIGIN_MODE_DRILL
            payload["replay"] = chain_origin == ORIGIN_MODE_REPLAY
            payload["synthetic"] = chain_origin == ORIGIN_MODE_SYNTHETIC
            payload["observed"] = False
        elif chain_origin == ORIGIN_MODE_OBSERVED:
            payload["observed"] = True
            payload["drill"] = False
            payload["replay"] = False
            payload["synthetic"] = False
    return payload
