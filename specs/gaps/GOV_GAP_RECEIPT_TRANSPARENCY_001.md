# GOV_GAP_RECEIPT_TRANSPARENCY_001

## Title

AG can prove a receipt's *content* (content-addressing) and chain receipts *linearly*
(`receipt_kernel`'s hash chain). It cannot yet give a consumer **compact, trust-minimized
verification that a receipt was included in a committed set**, cannot detect **split-view
equivocation** (one history shown to Alice, another to Bob), and has **no declared authority
over ordering**. This gap names the transparency-log layer — Certificate-Transparency /
Rekor-shaped, **not** blockchain — as four candidate objects plus one firewall, with deferred
finality (challenge windows) as a future consumer, not built.

## Status

Gap spec — **containment vessel**. **No invariant, validator, planner, protocol, accumulator,
or runtime check is ratified or authorized by this filing.** Under the 2026-06-18 unfreeze
warrant it ships exactly: (a) this record, (b) skeleton dataclasses in
`src/governor/receipt_transparency/` with **no accumulator logic**, and (c) non-claim tests that
pin the firewall. The five transparency invariants below are **PROPOSED doctrine**, not ratified
constitutional invariants — they are not in the same class as `receipt_kernel`'s 13. Ratify
lazily, on a forcing case. Candidate / non-binding until locally ratified (per `~/.claude/CLAUDE.md`
§ YAGNI scope).

## Boundary law (current, accurate as of filing)

> AG today proves **content** (every receipt is content-addressed) and **linear succession**
> (`receipt_kernel` is an append-only hash chain with tamper detection). It does **not** prove
> **compact membership** ("R is in committed epoch E" without ingesting the whole ledger),
> **consistency** ("E2 extends E1, it did not replace history"), **fork evidence** (two
> incompatible roots for one lineage), or **declared ordering** ("R precedes R' under sequencer S,
> not merely by wall-clock"). The custody and replay primitives are strong; the *public-verification*
> substrate is the unbuilt corner.

Two facts fix the boundary:

1. **Chain ≠ accumulator.** `receipt_kernel` is a *linear* hash chain. Inclusion is an O(n) walk,
   not a log-depth proof; a consumer must trust the operator that a receipt is in the set, or
   ingest the set. There is no Merkle root + inclusion proof anywhere in `src/governor` (grep:
   zero hits, 2026-06-18).
2. **Root custody is the real primitive, not "add a tree."** A Merkle proof is worthless unless the
   **root itself has standing**. Otherwise "trust me" just moves from the receipt set to the root.
   The missing primitive is *signed, epoch-scoped root publication with declared membership and
   ordering semantics* — a small trapdoor wearing a tiny hat.

## Origin

Filed 2026-06-18 after a steward audit of AG against the reusable failure-scars of adversarial
recordkeeping (the defensible half of the "blockchain" corpus: ordering, replay, equivocation,
finality, inclusion, custody — minus tokens, global consensus, code-is-law, and the casino). The
audit graded AG ~6.5/10 of those primitives: **strong** on content-addressing, replay protection,
and finality-status; **partial** on append-only/fork-detection, slashing-as-scars, two-man/quorum,
ordering custody; and **genuinely missing** Merkle inclusion proofs and challenge windows.

This is the right shape to import as *prior art, not local scar* (per `~/.claude/CLAUDE.md`
§ Scars as evidence): Certificate Transparency and Rekor spent a decade hardening append-only logs,
signed tree heads, inclusion proofs, consistency proofs, and gossip-based split-view detection. The
failure class is named in the literature; it is real before it bites locally.

**Coupling forcing case (why now, not later):** the transition kernel's durable chain
(`runtime/transition_enforce.py` `reconstruct_composed`) is **linear** today. Transition receipts
without compact inclusion / root custody / fork evidence are missing their public-verification
substrate. Naming this surface *before* the kernel's durable format calcifies around a merely linear
chain is cheap; retrofitting after is not. This makes the transparency log **transition-kernel
infrastructure**, adjacent to it, not a blockchain sidequest.

## The four candidate objects

None is built beyond a skeleton dataclass. Logic (accumulation, proof generation/verification,
signature verification) is explicitly out of scope for this filing.

### 1. `ReceiptEpochRoot` — the committed-set commitment

```text
epoch_id · previous_epoch_id · previous_root_hash · accumulator_kind (merkle_v1)
membership_rule · ordering_rule · receipt_count · receipt_set_root
produced_by · produced_at · signature
```

> **The root proves committed membership only. It does not prove semantic validity.** Nail that to
> the wall before anyone gets ideas.

### 2. `InclusionProof` — compact membership

```text
receipt_id · epoch_id · leaf_hash · sibling_path[] · root_hash · accumulator_kind
```

Future verifier shape (NOT built here): `verify_inclusion(receipt, proof, epoch_root) -> Included |
NotIncluded | Malformed`. Unlocks the light-client case: a consumer verifies membership without
ingesting the whole receipt universe.

### 3. `ConsistencyProof` / `ForkEvidenceReceipt` — history-extension + split-view detection (the CT/Rekor move)

```text
ConsistencyProof:    from_epoch · to_epoch · proof_path[] · from_root · to_root
ForkEvidenceReceipt: epoch_id · root_a · root_b · observed_by · evidence
```

Two incompatible roots for one lineage become **admissible fork evidence**, not vibes. Equivocation
becomes an accountable act.

### 4. `SequenceAuthority` — ordering custody (the MEV / sequencer lesson)

```text
authority_id · scope · ordering_basis[] (predecessor_edges | monotonic_sequence |
                                         source_sequence | external_clock_witness)
may_order_receipt_kinds[]
```

Whoever sequences receipts can launder meaning by delay, omission, or rearrangement. Every ordered
receipt should declare `order_basis` / `sequence_authority_id` / `predecessor_refs[]`.

> **Timestamp order is never causality unless a declared authority says that timestamp basis has
> standing.** (Composes with `clock_witness.py`: a gap is a difference between compatible clock
> witnesses, not numbers; this is the ordering analog.)

## The firewall (PROPOSED doctrine — the soul of this gap)

> 1. **Inclusion** proves membership in a committed receipt set.
> 2. **Consistency** proves one committed set extends another.
> 3. **Ordering** proves only the declared sequence relation.
> 4. **Signatures** prove custody over the signed artifact.
> 5. **None of the above proves semantic legitimacy, admissibility, authority, freshness, or
>    operational permission.**

This is the same firewall as NLAI, the proof→world fence (`a compiled theorem is evidence *into* a
gate, never the receipt the gate emits`), and the transition kernel's *measurement ≠ authority*. The
first green artifact of this work is therefore not "a Merkle proof verifies" (commodity) — it is
**"a structurally valid `InclusionProof` still confers no operational effect."**

## Deferred consumer: challenge windows (NOT built; this is P4, reframed)

Deferred finality wants a contestable interval between `supported` and `settled`:

```text
PROPOSED -> CHALLENGEABLE -> FINALIZED ; FINALIZED -> SUPERSEDED | REVERTED | INVALIDATED
ChallengeWindowPolicy: transition_kind · window_basis · window_length ·
                       admissible_challenge_kinds[] · finalization_rule
```

> **Operational effect starts no earlier than finalization unless explicitly marked provisional.**

**Do not build challenge windows first.** They need the inclusion substrate underneath, or they
become "trust me, no challenge arrived" — finality theater with nicer nouns. This is the reopening
path for P4 (`working/P4_PARKED_2026-06-16.md`), once the boring log-proof layer exists.

## Build order (claim dependency)

1. Merkle accumulator + epoch root → 2. inclusion-proof verifier → 3. consistency / fork evidence →
4. `SequenceAuthority` → 5. challenge-window finality → 6. later: signer-standing/slashing,
threshold (M-of-N) root publication. Each step earns implementation only on a forcing case. **This
filing ships step 0**: the names, the skeleton types, and the firewall test.

## Non-goals (do not swipe the casino)

- **No tokens / stake-as-coin.** "Stake," if ever, means standing / signing authority / eligibility
  — never a coin (a future signer-slashing seam, not this filing).
- **No global total order, no distributed consensus, no sequencer election, no "code is law,"
  no proof-of-work cosplay, no immutable-mistakes-as-virtue.**
- **No M-of-N / threshold signing yet** — governance garnish until the root/proof machinery exists.
- **No live promotion / finality behavior change.** Challenge windows are named as a future consumer
  only.
- **No working accumulator / proof verification in this filing.** Skeleton types + firewall only.
- **No "blockchain" naming.** The word appears in the repo only in non-claim warnings. The primitive
  is a *transparent receipt log with compact membership and fork evidence*, not a distributed ledger.

## Forcing case (the one that promotes step 1)

> A Nightshift / Labelwatch / external consumer verifies that a witness receipt belongs to a committed
> AG/NQ epoch **without loading the entire receipt substrate** — and can detect if it was shown a
> forked history. Small, mechanical, hard to bullshit.

Until that consumer is live, steps 1+ stay candidate. The skeleton + firewall reserve the surface so
the transition kernel does not calcify around a linear-only chain in the meantime.

## Cross-references

- `libs/receipt_kernel` — the **linear** hash-chained ledger this complements (chain ≠ accumulator;
  consistency proofs are the accumulator analog of `ledger.chain_valid`).
- `gate_receipt.py` / `hash_ref.py` — content-addressing this builds membership over.
- `runtime/transition_enforce.py` (`reconstruct_composed`) — the linear durable chain that is the
  coupling forcing case; `clock_witness.py` — the ordering-basis composition for `SequenceAuthority`.
- `docs/doctrine/standing_and_receipts.md` — the bridge chain the firewall's "no operational
  permission" line rests on.
- `working/P4_PARKED_2026-06-16.md` — challenge windows are the disciplined P4 reopening path.
- `mem`: the blockchain-scar audit provenance (2026-06-18 steward session) — what was swiped
  (Merkle/accountability/finality/fork-detection) and what was left in the burning mall (the casino).
