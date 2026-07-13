#!/usr/bin/env python3
"""S6 cross-repo integration evidence: AG v1 successor specimen → maude parse →
admission → projection → runtime.grant.activate request shape. Run with both
repos present. NOT a committed test (cross-repo path dependency); the receipt it
prints is the evidence recorded in the specimen README."""
import hashlib
import sys

sys.path.insert(0, "/home/jbeck/git/agent_gov_ui/maude/src")

from maude.plan import PlanRefusal, admit_for_execution, parse_plan_envelope  # noqa: E402
from maude.plan.execution_request import project_execution_request  # noqa: E402

SPEC = (
    "/home/jbeck/git/agent_gov/docs/campaigns/nightshift-functional-mvp/"
    "specimens/ns-1r-refusal-registry-v1/"
)
plan_bytes = open(SPEC + "plan.md", "rb").read()
plan_text = plan_bytes.decode()
ration_bytes = open(SPEC + "ration_card.json", "rb").read()
playbook_bytes = open(SPEC + "playbook.yaml", "rb").read()

print("plan_ref (candidate):", "sha256:" + hashlib.sha256(plan_bytes).hexdigest())

# 1. candidate parses but admission REFUSES (born-candidate rule)
env = parse_plan_envelope(plan_text)
assert env.plan_version == 1, env.plan_version
assert env.execution_request is not None
assert env.execution_request.write_paths == (
    "crates/nightshiftd/src/*", "crates/nightshiftd/tests/*"
)
assert [(c.program, c.argv_prefix) for c in env.execution_request.commands] == [
    ("cargo", ("test",)), ("cargo", ("build",))
]
try:
    admit_for_execution(env, witness_resolver=lambda c: None)
    raise SystemExit("FAIL: candidate should refuse")
except PlanRefusal as e:
    assert e.refusal_class == "governance_not_approved", e.refusal_class
    print("1. candidate admission refused:", e.refusal_class, "OK")

# 2. promote a throwaway copy → admits + projects the block
witness = b"operator approved NS-1R for S6 integration evidence"
promoted_text = plan_text.replace(
    "  governance_status: candidate\n",
    '  approval_ref: "operator:ns1r-s6"\n  governance_status: approved\n',
)
penv = parse_plan_envelope(promoted_text)
store = {
    "sha256:" + hashlib.sha256(playbook_bytes).hexdigest(): playbook_bytes,
    "sha256:" + hashlib.sha256(ration_bytes).hexdigest(): ration_bytes,
    "operator:ns1r-s6": witness,
}
rec = admit_for_execution(penv, witness_resolver=store.get)
assert rec.governed is True
print("2. promoted admission:", dict(rec.verified), "OK")

# 3. projection reads the execution_request block (nothing inferred)
call = project_execution_request(penv, store.get)
assert call is not None
req = call.execution_request
assert req["write_paths"] == ["crates/nightshiftd/src/*", "crates/nightshiftd/tests/*"]
assert req["commands"] == [
    {"program": "cargo", "argv_prefix": ["test"]},
    {"program": "cargo", "argv_prefix": ["build"]},
]
assert req["network_requested"] is False and req["git_requested"] is False
assert req["horizon"] == "run"
assert req["source_plan_digest"] == penv.plan_ref
assert req["approval_witness_digest"] == "sha256:" + hashlib.sha256(witness).hexdigest()
print("3. projected execution_request from block:")
print("   write_paths:", req["write_paths"])
print("   commands:", req["commands"])
print("   source_plan_digest:", req["source_plan_digest"])
print("ALL OK — v1 successor parses, admits when promoted, projects from the block.")
