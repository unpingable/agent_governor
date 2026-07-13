#!/usr/bin/env python3
"""Portfolio report — the operator's "what remains, where, and roughly how much?"

Reads .governor/backlog/*.json (the cross-constellation projection; canonical
truth stays in campaign STATUS files / PROGRAM_LEDGER / tool roadmaps — every
stub carries a canonical_source pointer and a reconciled{date,basis,confidence}
block). This script only aggregates; it never infers or mutates status.

Usage: python3 scripts/portfolio_report.py [--json]
"""
import json
import glob
import os
import sys
from collections import defaultdict

ROOT = os.path.join(os.path.dirname(__file__), "..", ".governor", "backlog")
OPEN = ("in_progress", "queued", "filed", "blocked", "zoned")
DONE = ("done", "closed", "retired")


def load():
    stubs = []
    for p in sorted(glob.glob(os.path.join(ROOT, "*.json"))):
        try:
            with open(p) as f:
                stubs.append(json.load(f))
        except (json.JSONDecodeError, OSError) as e:
            print(f"UNREADABLE STUB {p}: {e}", file=sys.stderr)
    return stubs


def line(s):
    band = f" [{s['effort_band']}]" if s.get("effort_band") else ""
    conf = s.get("reconciled", {}).get("confidence", "UNRECONCILED")
    flag = "" if conf == "CURRENT" else f"  ({conf})"
    return f"  t{s.get('priority_tier','?')}{band} {s['id']}{flag}"


def main():
    stubs = load()
    if "--json" in sys.argv:
        print(json.dumps(stubs, indent=1))
        return

    by_status = defaultdict(list)
    for s in stubs:
        by_status[s.get("status", "?")].append(s)

    n_open = sum(len(by_status[k]) for k in OPEN)
    n_done = sum(len(by_status[k]) for k in DONE)
    stale = [s for s in stubs if "reconciled" not in s]
    unknown = [s for s in stubs
               if s.get("reconciled", {}).get("confidence") == "UNKNOWN"]
    newest = max((s.get("reconciled", {}).get("date", "") for s in stubs),
                 default="never")

    print(f"PORTFOLIO — {len(stubs)} stubs · {n_open} open · {n_done} done/"
          f"closed/retired · last reconciled {newest}")
    print(f"Ruled-scope completion (ESTIMATE, stub-count only): "
          f"~{100 * n_done // max(1, n_done + n_open)}% "
          f"(a stub is not a unit of work; see effort bands)")
    print("  SCOPE: this measures NAMED, RULED work only — not activation debt "
          "(what it takes to\n  operate a node persistently) or scale debt. Those "
          "become owed when a deployment\n  posture is ratified; until then they are "
          "un-entailed. See working/activation-debt-candidate.md.")

    hot = sorted((s for s in stubs
                  if s.get("status") in ("in_progress", "queued")
                  and s.get("priority_tier") == 1),
                 key=lambda s: s["id"])
    print(f"\nHOT FRONTS ({len(hot)}) — active or ruled-next, tier 1:")
    for s in hot:
        print(line(s))
        if s.get("open_items"):
            print(f"      -> {s['open_items'][:140]}")

    print("\nACTIONABLE QUEUE (in_progress / queued / filed):")
    for st in ("in_progress", "queued", "filed"):
        items = sorted(by_status[st],
                       key=lambda s: (str(s.get("priority_tier", 9)), s["id"]))
        if items:
            print(f" {st} ({len(items)}):")
            for s in items:
                print(line(s))

    print("\nDORMANT WITH WAKE CONDITIONS (blocked / zoned):")
    for st in ("blocked", "zoned"):
        for s in sorted(by_status[st], key=lambda s: s["id"]):
            print(line(s))
            print(f"      wake: {s.get('wake_condition', 'UNKNOWN — defect')[:140]}")

    if unknown or stale:
        print("\nUNTRUSTWORTHY RECORDS — verify before relying:")
        for s in unknown:
            print(f"  UNKNOWN-confidence: {s['id']}")
        for s in stale:
            print(f"  never reconciled:   {s['id']}")

    print("\nEvery stub carries canonical_source + reconciled.basis — "
          "trace before acting. RRP registered 2026-07-13; unregistered "
          "nodes are excluded from these totals by construction.")


if __name__ == "__main__":
    main()
