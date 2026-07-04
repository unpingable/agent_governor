# Approval act — CD-2 queue item `chore.state-index-roadmap-kind`

**Approved by:** operator (interactive session answer, 2026-07-04) — verbatim:
"Approve option 1. Operator approval granted for conveyor queue item
`chore.state-index-roadmap-kind` / specimen CD-2 under the stated fence."

**Operator clarification (verified before proceeding):** `docs/roadmaps/*` is
forbidden as a WRITE/modification target, not as a read/scan input. Verified
against the landed law: `review_packet_validator.py` applies
`forbidden_paths`/`allowed_paths` to `packet.files_changed` only (fence check
#5, `changed_path_matches_forbidden_paths`) — reads are unrestricted. The
condition holds; no amendment needed.

**Latch semantics note (specimen finding #1):** the landed queue parser
refuses to construct an unapproved item at all
(`[not_operator_approved] ... provenance does not grant approval`) — a queue
file is definitionally a record of already-approved work; candidate staging
belongs to the M-1 plan-envelope lane (`governance_status: candidate`). The
`operator_approved: true` in queue.json is the RECORD of the act quoted
above, not the act itself.

**Commit-authority note:** the queue item's `authority.commit` is `false` —
the conveyor run itself mints no commit authority; its output is the
ReviewPacket. The eventual commit of the reviewed work happens in the
ordinary operator-authorized session lane and cites this specimen; it is not
a conveyor grant.
