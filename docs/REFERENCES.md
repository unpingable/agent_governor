# References

External work that informs or validates the governor's design premises.
Not dependencies — pointers. Cited here so they're discoverable when needed.

---

## Design ancestors

- **Ashby — Law of Requisite Variety / ultrastability** (1956, *Introduction to Cybernetics*)

  Why governors exist at all: a controller's variety must match the variety of
  disturbances it faces. The ultrastability controller (`ultrastability.py`) is
  explicitly Ashby-style: bounded parameters, pathology detection, freeze/unfreeze.
  The homeostat's adaptive gain scheduling is the same idea applied to exploration
  budgets. Maps to: `ultrastability.py`, `homeostat.py`, `coupling.py`.

- **Beer — Viable System Model** (1972, *Brain of the Firm*)

  Structural parallels, not a direct implementation. The two-ledger split
  (facts vs decisions) rhymes with Beer's separation of operational monitoring
  (System 1) from normative policy (System 3). Regime detection as a recursive
  diagnostic layer has VSM echoes. The governor is not a VSM implementation,
  but the shape of "nested autonomous systems that need internal regulation"
  comes from this lineage. Maps to: `ledgers.py` (facts/decisions split),
  `regime.py`, `boil.py`.

- **Rasmussen — drift to danger / boundary models** (1997, "Risk Management in a Dynamic Society")

  Why the instrumentation spine exists. Systems don't fail catastrophically
  from a single event — they drift toward the boundary of safe operation through
  incremental, locally rational decisions. The regime detector, drift detection
  (`drift.py`), and boil control are all boundary-monitoring mechanisms. The
  v2.4 signal substrate (exposure proxy, suppression, sigma rate) exists to
  make the drift observable before it becomes a failure. Maps to: `regime.py`,
  `drift.py`, `boil.py`, `signals/` (v2.4 instrumentation spine).

- **Leveson — STAMP / STPA** (2012, *Engineering a Safer World*)

  Why this is a constraint system, not an advice system. STAMP reframes safety
  as a control problem: accidents result from inadequate enforcement of
  constraints on system behavior, not from component failures. The governor's
  core architecture — typed claims, receipt-producing verification, write-blocking
  gates — is constraint enforcement. Advisory logging is insufficient because it
  doesn't close the control loop. Maps to: `evidence_gate.py`, `verifiers.py`,
  `hooks.py`, `wrapper.py`.

- **Lamport — Byzantine fault tolerance lineage** (1982, "The Byzantine Generals Problem")

  Why independence scoring, sybil resistance, and quorum consensus appear
  whenever the system distrusts its own components. The governor doesn't
  implement BFT directly, but the fault model — components may lie, collude,
  or fail arbitrarily — informs the quorum state machine, the independence
  scorer's anti-cheat (source URL overlap, Jaccard similarity), and the
  correlator's capture detection. The premise is the same: you can't trust
  self-reports from the things you're governing. Maps to: `quorum.py`,
  `independence.py`, `sybil.py`, `correlator_telemetry.py`.

- **Tamper-evident append-only logs** (exemplar: Certificate Transparency, RFC 6962)

  Why the receipt ledger isn't just logging. Append-only, hash-chained,
  content-addressed stores (`receipt_kernel`, `gate_receipt`) exist so that
  audit is possible under adversarial pressure. The receipt kernel's 6
  constitutional invariants (chain validity, receipt completeness, evaluation
  completeness, finalization completeness, single finalize, stage required path)
  are directly inspired by the CT model of "if it's not in the log, it didn't
  happen." Maps to: `libs/receipt_kernel/`, `gate_receipt.py`,
  `receipt_bridge.py`.

---

## Field evidence

- Shapira et al., **"Agents of Chaos"** (2026). [arXiv:2602.20021](https://arxiv.org/abs/2602.20021)

  Empirical field study: 6 tool-using LLM agents deployed in a live multi-user
  environment (shell, email, Discord, persistent memory) for two weeks with 20
  researchers probing under benign and adversarial conditions. Documents 11
  failure case studies — authority confusion, false completion reporting, identity
  spoofing, resource exhaustion loops, cross-agent propagation, prompt injection
  via editable config files — that motivate hard gates over advisory controls.

  Relevant to: NLAI ("natural language is a proposal, not an authority" — agents
  claimed completion while system state contradicted),
  scope governor (non-owners executed privileged operations), evidence gate
  (self-reported success without verification), correlator telemetry (Case 6:
  upstream provider silently altered behavior, agent masked failure as "unknown
  error" — the capture problem from the inside).
