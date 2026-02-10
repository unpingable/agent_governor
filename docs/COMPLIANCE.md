# Compliance Mapping: Process-Based Prudence

This document maps the Agent Governor's receipt and constraint model to existing regulatory frameworks. The alignment is structural, not aspirational: the same principles that govern fiduciary duty, aviation safety, and clinical decision-making motivate the system's design.

---

## The regulatory insight

In regulated environments, the compliance question is generally not "did the decision work?" It is: **was the decision made prudently, under the circumstances then prevailing, using a reasonable process?**

This is an ex-ante framing. The quality of a decision is judged by the process at the time, not the outcome after the fact.

The Agent Governor enforces and records exactly this: mandate adherence, risk constraints, evidence admissibility, and explicit waiver attribution.

---

## How receipts map to fiduciary audit

A gate receipt functions as an auditable record for an agent action:

| Receipt field | Fiduciary parallel |
|---|---|
| **policy_hash** | The governing policy version, pinned at decision time |
| **gate** | Which prudence check was applied |
| **verdict** | Whether the action passed, was flagged, or was blocked |
| **evidence_hash** | What due diligence was performed and recorded |
| **subject_hash** | What exactly was being evaluated |
| **Waivers / overrides** | Explicit risk acceptance, signed and attributed |

This creates a durable chain: policy was declared, checks were run, evidence was gathered, and the action was either admissible or it wasn't. If a waiver was involved, it's recorded with attribution.

---

## US regulatory parallels

### ERISA (Employee Retirement Income Security Act)

ERISA imposes a "prudent man" standard on fiduciaries managing retirement assets:

> A fiduciary shall discharge duties with the care, skill, prudence, and diligence under the circumstances then prevailing that a prudent man acting in a like capacity and familiar with such matters would use. (29 U.S.C. section 1104)

Key points:

- **"Circumstances then prevailing"** -- prudence is judged ex ante, not by outcome.
- **Diversification** is an explicit statutory requirement, not merely a best practice.
- **Process documentation** is central to fiduciary defense.

The governor's constraint model (concentration limits, evidence gates, signed waivers) maps directly onto ERISA's requirements. A receipt trail demonstrating that diversification constraints were in force, checks were run, and no unauthorized concentration occurred is precisely what a fiduciary audit would examine.

### SEC fiduciary duty (Investment Advisers Act)

The SEC frames an adviser's obligations around acting in the client's best interest. The duty of care requires:

- A reasonable basis for recommendations
- Investigation appropriate to the circumstances
- Process obligations beyond mere disclosure

The governor's evidence gates (requiring that HARD claims have supporting evidence before commitment) enforce a structural version of this duty: an agent cannot act on unsubstantiated claims in strict mode.

### Prudent process standards generally

Across financial regulation, the common thread is that fiduciary defense rests on demonstrating a **reasoned decision-making process**, not favorable outcomes. Courts evaluate:

- Whether alternatives were considered
- Whether risk was assessed and bounded
- Whether the decision-maker operated within their mandate
- Whether documentation exists

The governor produces exactly this documentation, mechanically and at every decision point.

---

## Beyond finance

The same ex-ante process framing applies in other regulated domains:

| Domain | Standard | What's audited |
|---|---|---|
| **Aviation** | Checklists, black box, crew resource management | Was the procedure followed? |
| **Medicine** | Informed consent, standard of care, clinical protocols | Was the process reasonable given available information? |
| **Software deployment** | Change management, rollback procedures, blast radius | Were safeguards in place? Were they followed? |

In each case, the question after failure is not "why did it fail?" but "was the process adequate for the known risks at the time?"

---

## Implications for AI agent deployment

When AI agents make consequential decisions, the compliance question is the same one that already governs human fiduciaries:

1. **Was the action within the declared mandate?**
   - If yes: the mandate (and its authors) bear scrutiny.
   - If no: the system violated its own constraints.

2. **Were required checks performed?**
   - If yes: the evidence trail is available for review.
   - If no: the deployment was negligent.

3. **Was risk explicitly accepted?**
   - If a waiver exists: the signer inherits liability.
   - If no waiver exists: the action was unauthorized.

4. **Does a receipt exist?**
   - If yes: the conversation is about whether rules were adequate.
   - If no: the conversation is about why the deployment had no controls.

The system doesn't make agents "right." It makes the absence of controls indefensible.

---

## Related

- [ADMISSIBILITY.md](ADMISSIBILITY.md) -- Admissibility vs correctness: the conceptual foundation
- [architecture/OVERVIEW.md](architecture/OVERVIEW.md) -- System architecture
