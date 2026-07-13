#!/usr/bin/env python3
"""Portfolio report — "what named, ruled work is queued, where, and roughly how big?"

This answers that question. It does NOT answer "how complete is the
constellation?" — there is no honest single number for that, and this report
does not manufacture one.

MEASUREMENT BOUNDARY (read before trusting any count here):
- Named backlog is MEASURED — the reconciled .governor/backlog/*.json records.
- Activation obligations (what it takes to OPERATE a node persistently: TLS,
  supervision, backup/restore, health, identity) are DERIVED ONLY AFTER an
  operating posture is ratified. Un-entailed until then; not counted here.
- Scale debt and unratified ambition are EXCLUDED.
- The closure ratio below is over RECORDS, not effort. A stub is not a unit of
  work: S/M/L records count as peers, roadmap-ratification paperwork sits
  beside build slices, and naming new work makes the ratio FALL despite real
  progress. Treat it as "how much of the named list is checked off," never as
  a progress bar. See working/activation-debt-candidate.md for the class cut.

Canonical truth stays in campaign STATUS files / PROGRAM_LEDGER / tool
roadmaps — every stub carries a canonical_source + reconciled{date,basis,
confidence}. This script only aggregates; it never infers or mutates status.

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
ACTIONABLE = ("in_progress", "queued", "filed")


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

    actionable = [s for s in stubs if s.get("status") in ACTIONABLE]
    # roadmap-* stubs are "ratify the roadmap doc" paperwork, not build work.
    paperwork = [s for s in actionable if s["id"].startswith("roadmap-")]
    substantive = [s for s in actionable if s not in paperwork]
    dormant = [s for s in stubs if s.get("status") in ("blocked", "zoned")]
    bands = defaultdict(int)
    for s in actionable:
        bands[s.get("effort_band") or "?"] += 1
    band_str = " ".join(f"{k}={bands[k]}" for k in ("S", "M", "L", "?") if bands[k])

    hot = sorted((s for s in stubs
                  if s.get("status") in ("in_progress", "queued")
                  and s.get("priority_tier") == 1),
                 key=lambda s: s["id"])

    print(f"NAMED-WORK QUEUE — reconciled {newest}")
    print(f"  hot fronts:          {len(hot)} (tier-1 active or ruled-next)")
    print(f"  actionable records:  {len(actionable)}  "
          f"(in_progress {len(by_status['in_progress'])} / "
          f"queued {len(by_status['queued'])} / filed {len(by_status['filed'])})")
    print(f"    substantive build: {len(substantive)}   ·   "
          f"roadmap-ratification paperwork: {len(paperwork)}")
    print(f"    effort bands:      {band_str}  (S/M/L; ? = unsized)")
    print(f"  dormant w/ wake:     {len(dormant)} (blocked / zoned)")
    print(f"  uncertain records:   {len(unknown) + len(stale)} (verify before relying)")
    print(f"  closed/retired:      {n_done}   —   named-record closure "
          f"{100 * n_done // max(1, n_done + n_open)}% (records checked off, NOT effort, "
          f"NOT completeness)")
    print("  Measures named, ruled work only — activation/scale/ambition excluded "
          "by construction\n  (see module docstring + working/activation-debt-candidate.md).")
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
