# Smallest End-to-End Governed Workflow

> STATUS: CANDIDATE (public-mvp S2) — not minted

---

## 1. What you'll see and why it matters

The core Governor loop is three commands: **propose** a typed claim, **verify** it (the Governor runs the check and produces a receipt), **apply** it (the FSM gate only opens if a receipt exists). Without verification the apply is refused — this is the point: nothing is trusted on say-so, only on machine-produced receipts. Every fact recorded in the ledger traces back to a Governor-generated receipt with a hash, a timestamp, and the exact command or file snapshot that justified it.

---

## 2. Prerequisites

```bash
git clone https://github.com/unpingable/agent_governor.git
cd agent_governor
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

Verify the CLI is present:

```
$ governor --version
governor, version 2.8.1
```

---

## 3. Set up a toy project

```bash
mkdir myapp && cd myapp
git init

cat > main.py << 'EOF'
def greet(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(greet("world"))
EOF

cat > test_main.py << 'EOF'
from main import greet

def test_greet():
    assert greet("Alice") == "Hello, Alice!"
EOF

git add -A
git -c user.email="you@example.com" -c user.name="You" commit -m "initial"
```

---

## 4. Initialize the Governor

```
$ governor init
Initialized governor at /path/to/myapp/.governor

  facts/       — tracked claims about your project state
  decisions/   — saved policy choices and judgments
  receipts/    — verification records from governor runs
```

Exit code: 0. This creates `.governor/` with an empty ledger, a config template, and a `proposals.json` store.

---

## 5. The core loop: propose → verify → apply → inspect

### Step 1 — Propose a claim

Claims are typed. The vocabulary is `file_exists`, `tests_pass`, `decision`, `changeset`, `symbol_defined`, `api_surface`.

```
$ governor propose --claim "type=file_exists,path=main.py"
Proposal created: 1bbe45fa-ad52-4b71-84cd-7381a8568cf0
State: proposed
Claims: 1
  [0] File exists: main.py
```

Exit code: 0. The proposal is in **proposed** state — no verification has happened yet.

You can also propose a normative decision (framework choice, style rule, etc.):

```
$ governor propose --claim "type=decision,topic=test-framework,choice=pytest"
Proposal created: 74b888e7-...
State: proposed
Claims: 1
  [0] Decision [test-framework]: pytest
```

And a test suite check:

```
$ governor propose --claim "type=tests_pass,command=python3 -m pytest test_main.py -q"
Proposal created: b30de853-...
State: proposed
Claims: 1
  [0] Tests pass: python3 -m pytest test_main.py -q
```

### Step 2 — Verify (Governor runs the check, produces a receipt)

```
$ governor verify 1bbe45fa-ad52-4b71-84cd-7381a8568cf0
Operating in strict mode
  [✓] Claim 0: verified

Proposal VERIFIED: 1 receipt(s) produced
Run 'governor apply 1bbe45fa-ad52-4b71-84cd-7381a8568cf0' to apply the changes
```

Exit code: 0. The Governor examined `main.py`, took a `FileSnapshot` receipt (path, SHA-256 blob hash, size, timestamp), and stored it in `.governor/facts/index.json`. For a `tests_pass` claim it actually runs the command and records a `CmdRun` receipt (exit code, stdout hash, stderr hash, duration).

For a `decision` claim, verification confirms the claim is well-formed and records a receipt immediately.

### Step 3 — Apply (FSM gate: only VERIFIED proposals pass)

```
$ governor apply 1bbe45fa-ad52-4b71-84cd-7381a8568cf0
  Added fact: File exists: main.py

Proposal APPLIED
```

Exit code: 0. The fact is now recorded in the facts ledger. Decisions go to the decisions ledger instead:

```
$ governor apply 74b888e7-...
  Added decision: test-framework = pytest

Proposal APPLIED
```

### Step 4 — Inspect state

**Facts ledger** (empirical, auto-decays when files change):

```
$ governor facts
Facts (2):

  [e267fa45-...]
    Tests pass: python3 -m pytest test_main.py -q
    Created: 2026-07-05T17:40:51+00:00

  [3d3ea4a1-...]
    File exists: main.py
    Created: 2026-07-05T17:39:35+00:00
```

Exit code: 0.

**Decisions ledger** (normative, persists until explicitly revised):

```
$ governor decisions
Active decisions (1):

  [test-framework] pytest
    ID: c7ddc562-...
```

Exit code: 0.

**Staleness check** — modify `main.py` and run:

```
$ echo "# changed" >> main.py
$ governor decay
Checking 2 fact(s) for staleness...

  ⚠️ [STALE] File exists: main.py
  ✓ [ok] Tests pass: python3 -m pytest test_main.py -q

Found 1 stale fact(s)
Run with --auto-prune to remove stale facts
```

Exit code: 0. The Governor detected the file hash no longer matches the receipt it produced at verify time.

---

## 6. The refusal moment

### Refusal A — Apply before verify

If you try to apply a proposal that is still in `proposed` state:

```
$ governor propose --claim "type=file_exists,path=utils.py"
Proposal created: e1972ff9-...

$ governor apply e1972ff9-...
Error: Proposal is in proposed state, cannot apply
Only VERIFIED proposals can be applied
```

Exit code: **1**. The FSM gate refuses. No argument or flag overrides this in strict mode.

### Refusal B — Claim whose verification fails

Propose a claim with a test that actually fails:

```
$ cat > broken_test.py << 'EOF'
def test_broken():
    assert 1 == 2, "always fails"
EOF

$ governor propose --claim "type=tests_pass,command=python3 -m pytest broken_test.py -q"
Proposal created: 8b840496-...

$ governor verify 8b840496-...
Operating in strict mode
  [✗] Claim 0: Tests failed with exit code 1

Proposal REJECTED: 1 claim(s) failed

Errors:
  [0] tests_failed: Tests failed with exit code 1
      Suggestion: Fix failing tests before proposing
```

Exit code: **1**. The proposal is now in `rejected` state. Attempting `apply` on a rejected proposal produces the same refusal:

```
$ governor apply 8b840496-...
Error: Proposal is in rejected state, cannot apply
Only VERIFIED proposals can be applied
```

Exit code: **1**. The rejection history is queryable:

```
$ governor rejections
Rejected proposals (1):

  ❌ 8b840496...
     Reason: Verification failed
     Failed claims: [0]
       [0] tests_failed: Tests failed with exit code 1
     Suggestion: Fix failing tests before proposing
```

Exit code: 0.

---

## 7. Where state lives

```
.governor/
├── config.toml          # permissions by agent role, path allowlists
├── proposals.json       # all proposals with state + embedded receipts
├── facts/
│   ├── index.json       # applied facts with their Governor-produced receipts
│   └── receipts/        # (populated by gate-check receipts, not proposal receipts)
└── decisions/
    └── index.json       # normative choices (framework, style, etc.)
```

**Two ledgers, two semantics:**

| Ledger | Purpose | Decay |
|--------|---------|-------|
| `facts/` | Empirical — file existence, test results, API surface | Auto-decays when underlying files change (`governor decay`) |
| `decisions/` | Normative — framework choices, style rules, policy decisions | Persists until explicitly revised with `governor decide` / `governor revise` |

**Receipt storage:** Proposal receipts live inside `.governor/proposals.json` and `.governor/facts/index.json`. Each receipt is a typed record: `FileSnapshot` (path, blob hash, size) for file claims, `CmdRun` (command, exit code, stdout hash, stderr hash, duration) for test claims. The Governor also maintains a separate gate-receipt store (inspectable with `governor receipts`) used by the evidence gate subsystem.

---

## 8. What just happened — NLAI in one paragraph

The Governor enforces a single rule: language is a proposal, not an authority (NLAI). When an agent says "main.py exists" or "tests pass," that sentence is a *proposal*, not a fact — it enters the ledger only after the Governor independently runs a verifier, produces a receipt (a hashed, timestamped artifact produced by the Governor's own check, never by the agent — though note the documented bootstrap limit: local receipts are tamper-evident, not tamper-proof, against an actor with filesystem access), and the FSM gate confirms the receipt exists before allowing `apply`. The agent provided a pointer (`path=main.py`, `command=python3 -m pytest ...`); the Governor produced the evidence; nothing was trusted on say-so.

---

## 9. Quick reference

```bash
# Initialize
governor init

# Propose claims (typed, not free-form)
governor propose --claim "type=file_exists,path=<path>"
governor propose --claim "type=tests_pass,command=<cmd>"
governor propose --claim "type=decision,topic=<topic>,choice=<choice>"

# Verify (Governor runs the check, produces receipts)
governor verify <proposal-id>       # exit 0 = VERIFIED, exit 1 = REJECTED

# Apply (FSM gate: only VERIFIED proposals admitted)
governor apply <proposal-id>        # exit 0 = APPLIED, exit 1 = refused

# Inspect ledgers
governor facts                      # empirical facts with timestamps
governor decisions                  # normative choices
governor rejections                 # rejected proposals with reasons
governor decay                      # check facts against current file hashes
governor status                     # health: mode, regime, drift, scars
```

---

*Every command in this document was run against governor 2.8.1 on a local test project. RAN: propose, verify, apply, facts, decisions, rejections, decay, status, receipts (list + show), status --json. READ but not reproduced here: receipts --evidence (structure confirmed from facts/index.json), state --json.*
