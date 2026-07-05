# CD-4B drive receipt — the operator-seat record

**2026-07-04 evening. Variant: CD-4B self-drive** (agent in the operator's
seat, not the human — recorded deviation from STATUS §Next item 1; see the
approval witness for the operator's authorization and the reframed hypothesis).
This file is the DRIVE surface. It is not the work receipt — that is the
ReviewPacket (`review_packet.manifest.json` / `.summary.md`). Neither cites the
other as proof.

## Identity

- **Session:** `sess_aabb2a056f9f`  ·  **promotion:** `prom_33a118903e71`
- **Admitted plan:** `plan.md`, `plan_ref sha256:d0015fa46674bd80…` — governed,
  admitted with **all four citations verified** (playbook_digest,
  ration_card_digest, queued_playbook_ref, approval_ref) against the co-located
  file witnesses.
- **Backend:** `claude_code` (only live supervised adapter; gemini defunct).
- **Wallclock cap:** 45 min. **Actual:** 8 min 19 s (499 s) — the run finished
  on its own; the cap never bound.
- **Driver:** maude's real command layer, driven headless through Textual's
  Pilot (`run <plan.md>`, `supervised approve/deny`, `supervised
  promotion/diff/keep` all dispatched through `on_input_submitted`). State was
  read programmatically; every ACT went through a maude command.

## Approvals / denials (11 interventions; reads auto-approved by the daemon)

The fence is the operator's pre-declared CD-4B bounds, applied mechanically with
the firing rule logged per decision (not per-call human judgement):

| # | verdict | tool | firing rule |
|---|---------|------|-------------|
| 1 | approve | Bash | read-only: `ls docs/playbooks/` |
| 2 | approve | Bash | read-only: `ls docs/campaigns/` |
| 3 | approve | Bash | read-only: conflict-marker grep |
| 4 | approve | Bash | read-only: `git log -- live-adapter…` |
| 5 | approve | Bash | read-only: `git log --all --source` |
| 6 | approve | Bash | read-only: `find src/governor/playbooks` |
| 7 | approve | Bash | required test: `pytest tests/playbooks -q` |
| 8 | **deny** | Bash | **fail-closed: `sha256sum …` not in read-only allowlist** |
| 9 | approve | Write | in scope: `…/review_packet.manifest.json` |
| 10 | approve | Write | in scope: `…/review_packet.summary.md` |
| 11 | approve | Edit | in scope: `…/README.md` |

10 approve, 1 deny. No commit / push / network / external-send tool was ever
proposed (the fence would have denied them; the daemon separately upgrades
push/curl/gh to COMMUNICATE). The single denial (#8) is a driver-fence
false-positive, discussed below — the run adapted around it (left the packet's
optional `sha256` fields null) rather than fighting the gate.

## Outcome

**Reached a deliberate keep decision** (not an obstruction). Files changed
(promotion, baseline correctly fenced):

- `README.md` (+17/-1) — run-outcome banner prepended; staging record kept as history.
- `review_packet.manifest.json` (new) — `review_packet.v0`, status **`no_change`**.
- `review_packet.summary.md` (new) — operator-facing summary + M-4 notes.

Fenced (excluded from the run's promote/discard — they are the operator's own
approval acts): `plan.md`, `queue.json`,
`operator_queued_playbook.operator_approved_2026-07-04`.

Kept through `supervised keep sess_aabb2a056f9f` → `[green]Changes kept[/green]`.
Nothing committed or pushed; the artifacts sit uncommitted on `main`. Per the
CD-2 doctrine, any eventual commit happens in the operator-authorized session
lane citing this specimen — the conveyor mints no commit authority.

## Independent verification (reviewer, adversarial — claims not taken on faith)

Every load-bearing claim in the ReviewPacket was re-checked against the tree:

- glossary.md defines **neither** `RationCard` nor `ReviewPacket` — **confirmed**
  (zero hits). The stop-short on the glossary A/B decision is real.
- `ReviewPacket` is CamelCase-consistent in `docs/playbooks/` — **confirmed**
  (11 uses, zero lowercase-as-type; packet said 10, an immaterial undercount).
- No conflict markers under `docs/playbooks/*.md`; the two lineages merged
  additively — **confirmed**.
- `pytest tests/playbooks -q` → **229 passed, exit 0**, re-run independently.
- The packet loads as a real `ReviewPacket` object (`from_json`) and passes the
  landed `validate_review_packet_for_queue_item` against the latched queue item:
  **`issues: []` (valid)**, `ready_for_operator_apply: false` — correct, because
  the validator only sets ready for a `proposed_patch`; a `no_change` packet is
  valid evidence with nothing to apply.
- Authority `used ≤ granted` holds (all `false`).

## Harness break found + fixed (maude)

**`run <plan.md>` refused a governed plan whose flip had dirtied the workspace.**
The CD-4 flip procedure (latch queue → write approval witness → promote plan)
inherently dirties the specimen dir *before* the run — and those edits ARE the
citations admission verifies. But `launch_session` raises `DirtyWorktreeError`
on any dirty tree unless `allow_dirty=True`, and maude's plan runner passed no
such flag. The documented flip led straight into a fail-closed launch the
operator surface could not clear.

**Fix (maude, `agent_gov_ui/maude`):** thread `allow_dirty` through
`GovernorClient.runtime_session_create`; `RunPlanCommand` passes
`allow_dirty=True` for governed plans and logs the fence
(`pre-existing changes are fenced from this run's keep/discard`). This is the
correct semantics, not a workaround — the Tock-2 baseline fence (GAP-N) excludes
pre-existing dirty from promote/reject, so a discard can never revert the
operator's own approval acts. Coverage added: `test_plan_runner.py`
(`test_governed_launch…allow_dirty is True` + ungoverned-stays-off). maude suite
**281 passed / 24 skipped**, plan-runner **14 passed**, ruff clean. **Left
uncommitted** for the operator to land in maude's lane.

## M-4 legibility findings (drive side)

1. **`no_change` is a first-class, legible outcome — but only because the packet
   says so out loud.** The run's value is a near-empty diff plus a classified
   decision point. The specimen behaved as an over-normalization trap (two of
   five named terms aren't in the authority; one is a metaphor); a driver
   optimizing for a visible diff would have done semantic damage. The correct
   result reads as "success" only if the surface treats `no_change` as a real
   verdict, which the ReviewPacket + README banner do.
2. **The `sha256sum` denial is a real product finding, not just a driver quirk.**
   A pure-read hashing helper was denied because the read-only allowlist didn't
   name it. Fail-closed was the safe direction and the agent adapted, but a real
   operator would want the ration card's `allowed_shell_commands` (or the
   supervised gate) to admit obviously-read-only helpers — otherwise benign
   inspection commands generate noise denials. Filed as a followup, not fixed
   mid-run (changing the fence mid-drive would be the human becoming the frontal
   lobe).
3. **The reconciliation instruction resolved to "already done" only via git
   lineage, not the file.** Verifying "no duplication between the two branches"
   needed `git log --all --source`, not just reading the doc — the kind of
   grounding the operator surface should ideally surface rather than make the
   driver re-derive.
4. **The operator surface carried the whole loop.** `run` → per-tool approve/deny
   from the declared fence → `promotion`/`diff`/`keep` all dispatched as maude
   commands; the human's role was authorization (the two flip acts) and review,
   not integration. That was the CD-4B hypothesis, and it held.
