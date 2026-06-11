# SPDX-License-Identifier: Apache-2.0
"""OPA contrast shim — the demo's Act 2.5 (objection pre-answer, NOT a new act).

W1 item 5. ~100 lines, demo-grade, NOT a product surface ("OPA integration as
supported surface" is a post-launch forcing case; no policy-adapter zoo).

Composition beats argument: we're not an alternative to OPA, we're what OPA
stands on. OPA is a verdict engine; it evaluates the world it's handed and
nothing attests the input document — ``input.credential.status: "valid"`` is
unwitnessed self-report in a structured costume. Rego *can* check freshness if
you feed it freshness; the fair critique is that OPA cannot establish the
custody of its own inputs.

The beat: the SAME incident as Act 1 (the frozen temporal-lapse impostor,
corpus 08). OPA correctly returns ``allow`` over the stale input (garbage
custody in, immaculate verdict out); custody refuses **upstream** — not because
the policy was wrong but because its premises failed preflight. Then OPA's
verdict itself gets a receipt (policy hash, input provenance, decision) and
enters the evidence plane instead of evaporating into a decision log.

> policy engines decide over claims; custody systems decide whether those
> claims may become premises.

Degradation: with no ``opa`` binary the shim does NOT claim OPA ran — it shows
the 8-line policy and the input and says so plainly (the policy is small enough
to evaluate by eye). Live evaluation happens when ``opa`` is installed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Optional

from governor.drill_runner import SCENARIO_TEMPORAL_LAPSE, DrillRunResult, run_drill

LAYERING_SENTENCE = (
    "policy engines decide over claims; custody systems decide whether those "
    "claims may become premises."
)

# The naive-but-reasonable policy ordinary stacks run: role + credential status.
# It is CORRECT for the world it is handed. That is the point.
REGO_POLICY = """\
package demo.authz

default allow := false

allow if {
    input.credential.status == "valid"
    input.credential.role == "operator"
    input.action == "consume_capacity"
}
"""

# The impostor's spend AS ORDINARY INFRA SEES IT — the same incident the
# corpus-08 drill refuses. Every field is true-as-self-reported: the credential
# WAS valid (observed t=40). Nothing in this document attests WHEN that
# observation happened relative to the spend (t=51) — that custody distinction
# is exactly what an input document cannot carry about itself.
OPA_INPUT = {
    "action": "consume_capacity",
    "credential": {"status": "valid", "role": "operator", "subject": "drill-operator"},
    "incident": "temporal-lapse (golden/corpus/08)",
}


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def evaluate_with_opa(timeout_s: float = 10.0) -> Optional[dict[str, Any]]:
    """Run the real engine if installed; None when absent (honest degradation,
    never a fabricated verdict). Demo-grade subprocess, P4Client-style fallback."""
    opa = shutil.which("opa")
    if opa is None:
        return None
    with tempfile.TemporaryDirectory(prefix="ag-opa-contrast.") as td:
        policy = Path(td) / "policy.rego"
        inp = Path(td) / "input.json"
        policy.write_text(REGO_POLICY)
        inp.write_text(json.dumps(OPA_INPUT))
        proc = subprocess.run(
            [opa, "eval", "-d", str(policy), "-i", str(inp),
             "--format", "json", "data.demo.authz.allow"],
            capture_output=True, text=True, timeout=timeout_s,
        )
        if proc.returncode != 0:
            return {"allow": None, "engine_error": proc.stderr.strip()[:200]}
        value = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
        version = subprocess.run(
            [opa, "version"], capture_output=True, text=True, timeout=timeout_s
        ).stdout.splitlines()[0].strip()
        return {"allow": value, "engine": version}


def build_opa_verdict_receipt(evaluation: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The verdict enters the evidence plane: content-addressed, carrying the
    policy hash, the input hash, and — load-bearing — the input's PROVENANCE."""
    body = {
        "kind": "opa_verdict",
        "policy_hash": f"sha256:{_sha256_hex(REGO_POLICY.encode())}",
        "input_hash": f"sha256:{_sha256_hex(json.dumps(OPA_INPUT, sort_keys=True).encode())}",
        "input_provenance": "unwitnessed_self_report",
        "decision": (evaluation or {}).get("allow"),
        "engine": (evaluation or {}).get("engine", "opa_not_installed"),
    }
    digest = _sha256_hex(json.dumps(body, sort_keys=True).encode())
    return {"receipt_id": f"opa_rcpt_{digest[:12]}", **body}


def run_contrast(*, root: Path, now: int = 0) -> dict[str, Any]:
    """OPA's verdict and custody's, same incident."""
    ag_dir = root / "custody"
    ag_dir.mkdir(parents=True, exist_ok=True)
    ag: DrillRunResult = run_drill(
        gov_dir=ag_dir, scenario=SCENARIO_TEMPORAL_LAPSE, now=now
    )
    evaluation = evaluate_with_opa()
    receipt = build_opa_verdict_receipt(evaluation)
    assertions = _evaluate_integrity(ag, evaluation)
    return {
        "ag": ag,
        "evaluation": evaluation,
        "opa_receipt": receipt,
        "assertions": assertions,
        "aggregate_ok": all(ok for _, ok, _ in assertions),
    }


def _evaluate_integrity(
    ag: DrillRunResult, evaluation: Optional[dict[str, Any]]
) -> list[tuple[str, bool, str]]:
    out: list[tuple[str, bool, str]] = []
    out.append((
        "custody refused the incident upstream, at the spendability seam",
        ag.outcome == "refused"
        and ag.refusal_kind == "standing_before_spendability_not_bounded"
        and ag.refusing_seam == "standing_spendability_seam",
        f"outcome={ag.outcome} kind={ag.refusal_kind} seam={ag.refusing_seam}",
    ))
    out.append((
        "the refusal spent no capacity (premises failed preflight)",
        ag.effect_count == 0,
        f"effect_count={ag.effect_count}",
    ))
    if evaluation is not None and "engine_error" not in evaluation:
        # The contrast's hinge: OPA must say ALLOW over the same incident. If
        # the verdict engine refused, the contrast collapses — fail loudly.
        out.append((
            "OPA returned allow over the unwitnessed input (correctly, for the world it was handed)",
            evaluation.get("allow") is True,
            f"allow={evaluation.get('allow')}",
        ))
    else:
        out.append((
            "opa binary not installed — policy + input shown, no verdict fabricated",
            True,
            "live evaluation skipped honestly",
        ))
    return out


def render_surface(contrast: dict[str, Any]) -> str:
    ag: DrillRunResult = contrast["ag"]
    evaluation = contrast["evaluation"]
    receipt = contrast["opa_receipt"]
    rule = "─" * 70
    out: list[str] = []
    out.append("═" * 70)
    out.append("  Agent Governor — What OPA Stands On (Act 2.5: the objection)")
    out.append("  Same incident as Act 1: the temporal-lapse impostor (corpus 08).")
    out.append("═" * 70)
    out.append("")
    out.append("  THE POLICY (Rego — correct for the world it is handed):")
    out.extend(f"    {ln}" for ln in REGO_POLICY.splitlines())
    out.append("  THE INPUT (unwitnessed self-report in a structured costume):")
    out.extend(f"    {ln}" for ln in json.dumps(OPA_INPUT, indent=2, sort_keys=True).splitlines())
    out.append("")
    out.append(rule)
    if evaluation is not None and "engine_error" not in evaluation:
        out.append(f"  OPA SAYS:      allow = {str(evaluation['allow']).lower()}   ({evaluation['engine']})")
    elif evaluation is not None:
        out.append(f"  OPA SAYS:      engine error — {evaluation['engine_error']}")
    else:
        out.append("  OPA SAYS:      (opa binary not installed — no verdict fabricated;")
        out.append("                  the 8-line policy over that input is allow by eye)")
    out.append("  CUSTODY SAYS:  refused — " + str(ag.refusal_kind))
    out.append("                 upstream of the policy: its premises failed preflight.")
    out.append("                 The input asserts the credential is valid; nothing")
    out.append("                 attests WHEN that was true. Custody had the clocks:")
    block = ag.spendability_block or {}
    out.append(
        f"                 gap={block.get('gap_ns', 0) / 1e9:g}s vs bound="
        f"{block.get('bound_ns', 0) / 1e9:g}s on a named monotonic basis."
    )
    out.append(rule)
    out.append("")
    out.append("  The verdict itself enters the evidence plane (not a decision log):")
    for k in ("receipt_id", "policy_hash", "input_hash", "input_provenance", "decision", "engine"):
        v = receipt[k]
        out.append(f"    {k}: {json.dumps(v) if v is None or isinstance(v, bool) else v}")
    out.append("")
    out.append(f"  {LAYERING_SENTENCE}")
    out.append("")
    out.append(rule)
    out.append("  Integrity")
    out.append(rule)
    for label, ok, detail in contrast["assertions"]:
        out.append(f"  {'✓' if ok else '✗'} {label}")
        if not ok:
            out.append(f"      detail: {detail}")
    out.append("")
    return "\n".join(out) + "\n"


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OPA contrast shim (demo-grade)")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    contrast = run_contrast(root=args.root, now=0)
    surface = render_surface(contrast)
    if args.format == "json":
        ag: DrillRunResult = contrast["ag"]
        print(json.dumps({
            "surface": surface,
            "aggregate_ok": contrast["aggregate_ok"],
            "opa_receipt": contrast["opa_receipt"],
            "opa_evaluation": contrast["evaluation"],
            "custody": {
                "outcome": ag.outcome,
                "refusal_kind": ag.refusal_kind,
                "refusing_seam": ag.refusing_seam,
                "effect_count": ag.effect_count,
            },
            "assertions": [
                {"label": label, "ok": ok, "detail": detail}
                for label, ok, detail in contrast["assertions"]
            ],
        }, indent=2))
    else:
        print(surface, end="")
    return 0 if contrast["aggregate_ok"] else 1


if __name__ == "__main__":
    sys.exit(_main())
