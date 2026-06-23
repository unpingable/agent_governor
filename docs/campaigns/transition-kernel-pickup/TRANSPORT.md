# Slice 1b transport reduction — how AG consumes a Standing grant-use verdict

Date: 2026-06-23. Reduction only — no adapter, no `activation.py` change.

> **STATUS: contract RATIFIED (D010b/D010c) and BUILT.** The `standing.grant_use.v1` witness
> packet is implemented in Standing (`grant use --json`, commit `f101c55`) with asymmetric
> custody. The shape below is final, not proposed. Slice 1b (AG adapter) is unblocked.

## Verdict: **(C)** — Standing must add machine-readable verdict output before AG can consume `grant use` honestly

The transport *shape* is settled (subprocess + JSON; see below), but the Standing CLI does
not yet emit a typed verdict for `grant use`, so AG cannot consume it without parsing prose
or trusting an exit code — both forbidden. One small Standing change (Slice 1a-bis) unblocks
the AG adapter.

## Transport inventory

| Surface | Finding |
|---|---|
| AG `StandingClient` (`standing_client.py`) | VERIFY stub: `verify(receipt_id)` via an injected `verify_fn`, returns `StandingReceiptRef \| None`. "No real transport; harness wires subprocess later." Emits `standing_required` / `dangling_receipt_reference` only. Does **not** invoke a spend. |
| AG subprocess idiom | Present (`demo_interrogate._run_cli` → `subprocess.run` on a CLI). Subprocess-to-`standing` is feasible. |
| AG ↔ Standing SQLite | AG must **not** open Standing's DB (that makes AG a store peer, not a consumer). Subprocess to the `standing` binary keeps AG a consumer. |
| `activation.py` Office 2 | `activate(..., standing_ok: bool, external_standing_receipt: str\|None)`; `if not standing_ok → REFUSED_NO_STANDING`; `standing_basis` receipt field ready (`activation.py:390/400/450/170`). |
| **Standing CLI `grant use` output** | **PROSE ONLY.** Success: `println!("used {id}")` + `receipt: {digest}`. Failure: `main()` `eprintln!("error: {e}")` + `exit(1)` — the refusal *class* (scope/expiry/subject/…) lives only inside the Display string. No `--json`, no typed refusal class. (Only `identity create` emits JSON today.) |

**Why this forces C:** with prose-only output, AG could only get the refusal class by parsing
the human error string (forbidden: "no parsing human prose as authority") or by trusting the
exit code (forbidden: "no exit-0-alone as admission"). Honest consumption needs a typed result.

## Required Standing output contract (Slice 1a-bis — the missing piece)

Add a `--json` mode to `grant use` (and `activate`) that writes one JSON object to **stdout**
on **both** paths (so the refusal class survives), with exit codes preserved:

```json
// success
{ "result": "used", "grant_id": "<uuid>", "receipt_digest": "<sha256>",
  "scope": { "action": "deploy", "target": "prod" } }

// refusal — TYPED class (this is the load-bearing addition)
{ "result": "refused",
  "refusal_class": "scope_mismatch" | "expired" | "already_spent" |
                   "replay" | "subject_mismatch" | "not_found" | "invalid_transition",
  "detail": "<prose for humans>", "granted": "deploy/prod", "attempted": "deploy/staging" }
```

The refusal JSON must reach stdout from the `grant use` handler **before** `main()`'s generic
`eprintln!("error: {e}")`, so AG reads a typed class rather than a prose string. Map each
`StoreError` variant to a `refusal_class` at the CLI boundary.

## Refusal mapping — Standing → AG (`REFUSED_NO_STANDING`), and the transport ≠ refusal line

| Source | `result` AG records | AG verdict |
|---|---|---|
| `refusal_class: scope_mismatch` | `standing_refused: scope_mismatch` | `REFUSED_NO_STANDING` |
| `refusal_class: expired` | `standing_refused: expired` | `REFUSED_NO_STANDING` |
| `refusal_class: already_spent` (terminal `Used`) | `standing_refused: already_spent` | `REFUSED_NO_STANDING` |
| `refusal_class: subject_mismatch` | `standing_refused: subject_mismatch` | `REFUSED_NO_STANDING` |
| `refusal_class: replay` | `standing_refused: replay` | `REFUSED_NO_STANDING` |
| `refusal_class: not_found` | `standing_refused: not_found` | `REFUSED_NO_STANDING` |
| `result: used` but no `receipt_digest` | `standing_receipt_missing` | `REFUSED_NO_STANDING` |
| subprocess error / nonzero with no parseable JSON / binary absent | `standing_transport_failed` | `REFUSED_NO_STANDING` |
| stdout not valid JSON / unknown `refusal_class` | `standing_output_unparseable` | `REFUSED_NO_STANDING` |

**Transport failure is NOT a Standing refusal.** The AG receipt must keep the difference:

```
standing_result = no_verified_result
reason          = standing_transport_failed | standing_output_unparseable | standing_receipt_missing
ag_refusal      = REFUSED_NO_STANDING
```

AG may refuse to mint because it *cannot verify* Standing, but it must not claim Standing
*refused the grant* unless Standing emitted that typed refusal. (Otherwise: laundering in a
JSON raincoat.) `standing_basis` records the verified receipt digest on success; on refusal it
records `standing_refused:<class>`; on transport failure it records `no_verified_result:<reason>`.

## Recommended Slice 1b plan (two steps, gated)

1. **Slice 1a-bis (Standing, prerequisite):** add `--json` typed verdict to `grant use`
   (success + typed refusal class to stdout, exit codes preserved). Small, self-contained,
   testable in the Standing workspace. **Blocks the AG adapter.**
2. **Slice 1b (AG, after 1a-bis):** `AGGrantAdapter` subprocess-invokes
   `standing grant use --json …`, parses the typed result, applies the mapping above, and
   replaces `activation.py` Office 2's `standing_ok: bool` with the verified result. AG does
   **no** local scope/expiry/spend/replay/subject adjudication — it consumes Standing's verdict;
   `standing_basis` carries the distinction (verified / standing_refused / no_verified_result).
   `StandingClient` graduates from VERIFY-stub to a real subprocess client **only** for this seam.

## Custody finding — rule #4 fired (STOP): no `receipt_digest` for non-consuming use-refusals

When tightening the wire contract to `standing.grant_use.v1`, the requirement "refusal packet
carries `receipt_digest`" hit Standing's core model. Reduction (2026-06-23):

- Standing invariant: **"no receipt without a valid transition"** (`standing-store/src/lib.rs:7`).
- `ReceiptKind`: `GrantRequested/Issued/Denied/Activated/Used/Expired/Revoked/Abandoned` —
  **no `GrantRefused`/use-refusal kind**. `GrantState` has **no "use-refused" state**.
  `GrantDenied` works only because `Requested → Denied` is a real transition.
- A grant-**use** refusal has **no transition**, so no receipt:
  - `scope_mismatch`, `subject_mismatch` → **non-consuming** (D010a) → grant stays `Active` → no transition → no digest;
  - `not_found` → no grant → no digest;
  - `already_spent` → grant already `Used`; the *first* `GrantUsed` receipt exists, the second attempt writes nothing;
  - `expired` → currently errors without transitioning to `Expired`.

So `receipt_digest` cannot be honestly required on a non-consuming refusal without a **Standing
constitutional change**. The SUCCESS path is unaffected — `Active → Used` mints a `GrantUsed`
receipt, so the success packet's `receipt_digest` (the load-bearing `standing_basis`) is real.

### Fork (operator-fiat — blocks Slice 1a-bis)

- **(A) Mint refusal-witness receipts.** Add a `GrantRefused` receipt + an `Active → Active`
  (or side-log) refusal transition, OR relax "no receipt without a transition." A Standing
  constitutional slice; gives every refusal a `receipt_digest`. Cost: the receipt chain grows
  on refused attempts (a wrong-target spammer inflates the chain, though never consumes the grant).
- **(B) Refusal is typed-class-only; `receipt_digest` is success-only.** A non-consuming refusal
  is the *absence* of a transition, so there is no receipt to cite. **Not weaker in the
  load-bearing sense:** AG never *mints* on a refusal, so there is no authority to custody — the
  typed `refusal_class` is sufficient for AG to record *why* it refused. `receipt_digest` stays
  **required on `used`** (the real `standing_basis`) and `null`/absent on `refused`.

**Recommendation: (B).** Receipts witness transitions; a non-consuming refusal has none, so a
refusal `receipt_digest` would be either fabricated or force a model change that grows the chain
on hostile input. The custody that matters (the mint's `standing_basis`) is on the success path
and is real. If the operator wants refusal-witness receipts for audit, that is a separate
Standing constitutional slice, not a precondition for the AG pickup.

## Open sub-question for Slice 1b (flag, do not resolve here)

Does AG *trigger the spend* (`grant use`) at the mint boundary, or *verify a use-receipt* the
caller already produced? Triggering means AG's activation spends the grant (one-shot, ties the
mint to the spend); verifying means the spend happened upstream and AG checks its receipt. The
inventory supports either; it is an authority-shape call for the operator when Slice 1b starts.
