#!/usr/bin/env python3
"""Portfolio report — declared work plus explicit authority/custody axes.

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
confidence}. This script only aggregates; it never mutates status. In
particular, legacy ``open``/``queued``/priority fields never imply selection,
plan approval, runtime activity, or effect authority. Those axes are reported
only when an explicit ``state_axes`` record exists; otherwise they are
``unknown``.

Usage:
  python3 scripts/portfolio_report.py
  python3 scripts/portfolio_report.py --json        # legacy raw stubs
  python3 scripts/portfolio_report.py --audit-json  # axes + findings
  python3 scripts/portfolio_report.py --check       # read-only consistency check
"""
import argparse
import json
import glob
import os
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from governor.portfolio_audit import (  # noqa: E402
    AXES,
    build_audit,
    collect_consistency_findings,
    default_standing_db,
    project_state_axes,
    summarize_axes,
)

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


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--json", action="store_true", help="emit legacy raw backlog stubs")
    modes.add_argument(
        "--audit-json", action="store_true", help="emit explicit state axes and findings"
    )
    modes.add_argument(
        "--check",
        action="store_true",
        help="run read-only custody consistency checks (nonzero while findings remain)",
    )
    return parser.parse_args(argv)


def _print_axis_summary():
    summary = summarize_axes(project_state_axes(REPO_ROOT))
    print("\nSTATE AXES (explicit records only; absent evidence stays unknown):")
    for axis in AXES:
        values = " / ".join(f"{state}={count}" for state, count in summary[axis].items())
        print(f"  {axis + ':':20} {values or 'no records'}")
    print("  Legacy backlog status is not used to infer any axis.")


def _print_findings(findings):
    if not findings:
        print("\nCONSISTENCY: no bounded contradictions found.")
        return
    print(f"\nCONSISTENCY FINDINGS ({len(findings)}):")
    for finding in findings:
        print(f"  [{finding.severity}] {finding.code}: {finding.subject}")
        print(f"      claim: {finding.claim}")
        print(f"      ground truth: {finding.ground_truth}")
        print(f"      evidence: {', '.join(finding.evidence)}")


def main(argv=None):
    args = _parse_args(argv)
    stubs = load()
    if args.json:
        print(json.dumps(stubs, indent=1))
        return 0

    standing_db = default_standing_db(REPO_ROOT)
    if args.audit_json:
        print(json.dumps(build_audit(REPO_ROOT, standing_db=standing_db), indent=2))
        return 0
    if args.check:
        findings = collect_consistency_findings(REPO_ROOT, standing_db=standing_db)
        _print_findings(findings)
        return 1 if findings else 0

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

    print(f"DECLARED-WORK PORTFOLIO — reconciled {newest}")
    print(f"  tier-1 status tags:  {len(hot)} (records tagged in_progress / queued)")
    print(f"  open status records: {len(actionable)}  "
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
    print("  Measures named, declared records only — activation/scale/ambition excluded "
          "by construction\n  (see module docstring + working/activation-debt-candidate.md).")
    print(f"\nTIER-1 STATUS RECORDS ({len(hot)}) — not inferred as selected or authorized:")
    for s in hot:
        print(line(s))
        if s.get("open_items"):
            print(f"      -> {s['open_items'][:140]}")

    print("\nDECLARED OPEN RECORDS (in_progress / queued / filed):")
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

    _print_axis_summary()
    _print_findings(collect_consistency_findings(REPO_ROOT, standing_db=standing_db))

    print("\nEvery stub carries canonical_source + reconciled.basis — "
          "trace before acting. RRP registered 2026-07-13; unregistered "
          "nodes are excluded from these totals by construction.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
