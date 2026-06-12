# Constellation networking patterns — the complete map

**Status: CANDIDATE / non-binding.** Recognition record, not build authorization.
Source: operator + ChatGPT ("Chatty") + Fable session, 2026-06-12 morning audit.
Canonical doctrine homes when ratified: `docs/constellation-zoning.md` (the map),
`~/git/wlp` (the wire treaty), nq repo (crosstalk build). AG-side this doc is the
handle for review; the zoning appendix carries the carved summary.

**Forcing-case status (operator, 2026-06-12):** nearer than the drawer assumed.
Labelwatch lives on the linode VM; everything cross-host today is ssh tunnels;
operator intends that to change soon. The day the first component leaves the
host — concretely, labelwatch's *reporting home* becoming cross-host member
traffic — is the forcing day. Not before.

---

## 1. The map — three patterns, two shortcuts, one axis

| Pattern | Shape | Failure concern | Members |
|---|---|---|---|
| **Verdict RPC** | ask → typed outcome (synchronous, authority-shaped) | don't collapse transport/speaker/doctrine failures | WLP, wicket, verifier, standing checks, LA spends |
| **Testimony flow** | signed append, push, eventual delivery | preserve origin, detect gaps | NQ crosstalk, heartbeats, receipt shipping |
| **Retraction fan-out** | urgent, reliance-indexed, delivery-accounted | prevent stale authority from continuing | revocation, lapse, taint — *already filed as zoning organ; see §5* |
| — blob pull (sub-case) | content-addressed fetch-by-hash; integrity free by construction | integrity / availability | segments, corpora, sealed logs |
| — subscription tail (sub-case) | testimony flow with a standing subscription instead of push batches | bounded live observation | phosphor watching remote instances |
| *(axis)* member / foreign | standing-backed keys vs. **no standing at all** | evidence class / egress effect | constellation seams vs. MCP endpoints, ATProto firehose |

Dispatch decomposes, no new pattern: admission → verdict RPC, execution log →
testimony flow, cancellation → retraction fan-out (maybe). There is no
"orchestration protocol" — that phrase is killed in the crib. The zoo is closed
until a specimen refuses to fit.

The carved version (README-survivable):

> **Constellation networking has three primary idioms: verdict RPC, testimony
> flow, and retraction fan-out. Blob pull and subscription tail are degenerate
> testimony forms. Member/foreign is an orthogonal trust axis. Pipes provide
> delivery; signed claims provide evidence; retractions require
> reliance-indexed delivery accounting.**

Keeper lines (carve-grade):

> Transport may secure delivery, but only signed envelopes create durable
> speaker evidence. Component keys receive Standing; WLP verifies the speaker
> before evaluating the claim.

> NQ replication is evidence logistics, not shared state.

> No bearer-token authority. Possession is not standing.

---

## 2. Verdict RPC — WLP over the wire (W-series)

Steal shamelessly; don't invent networking unless the transport itself becomes
the specimen.

**Stack ranking:** axum + reqwest + serde JSON is the default theft target
(first real over-wire WLP, internal HTTP, easy debug). tonic/prost gRPC good
later, once the treaty stabilizes (proto enums will flatten the refusal algebra
into parking-lot signage). tarpc = tempting internal-bus shortcut, wrong for a
public-ish contract. quinn/QUIC only if transport behavior is itself
load-bearing. Cap'n Proto = ceremony trap.

**Crate split (the treaty is a crate, not a server):**

```text
wlp-core     -> local pure logic (no networking, no tokio)
wlp-wire     -> serde structs / schema / fixtures ("the treaty")
wlp-server   -> axum route calling wlp-core
wlp-client   -> reqwest client returning typed outcomes
```

**Envelope + outcome shape (v0 sketch, from the session):** versioned
`WlpWireRequest { schema: "wlp.wire.v0", request_id, idempotency_key, actor,
packet_hash, operation, inputs }`; outcome is a tagged enum —
`Authorized { receipt, receipt_hash, scope } | Refused { reason_code,
unsettled_kinds, receipt } | CannotTestify { reason_code, admissible_scope } |
Stale { clock_ref, bound }`.

**The load-bearing pattern is receipt-carrying RPC**, not RPC that happens to
return JSON: `Result<WlpWireOutcome, TransportError>` — never
`Result<AuthorizationReceipt, Error>`. Transport failure is not WLP refusal.
Do not let HTTP status cosplay as doctrine:

| Layer | Example | Meaning |
|---|---|---|
| TCP/TLS failure | timeout, connect refused | transport failed |
| HTTP 400 | malformed wire request | bad envelope, cannot parse |
| HTTP 409-ish | idempotency conflict | request identity problem |
| HTTP 200 + `refused` | WLP considered and refused | valid WLP outcome |
| HTTP 200 + `authorized` | WLP authorized | valid WLP outcome |
| HTTP 200 + `cannot_testify` | evaluator cannot speak | valid WLP outcome |

Ward glyph: retry transport failures; do NOT retry WLP refusals unless input
evidence changed; never convert transport failure → cannot_testify; never
convert cannot_testify → refusal.

**Python is a wire participant, not a second doctrine implementation.**
Rust owns core WLP semantics; JSON/HTTP owns the treaty; Python gets typed
envelope + shims. Stack: httpx (client), FastAPI (shim server, only if Python
must serve), Pydantic (models, discriminated-union outcome on `outcome` field),
jsonschema (golden-corpus validation), PyO3/maturin only if local embedding
becomes useful (it dodges the wire specimen — don't start there). Same ward in
Python: `httpx.RequestError != refusal`, `5xx != refusal`, `parse failure !=
refusal`; refusal is a *valid body* with `outcome="refused"`.

**Schema authority: Option A (Rust authoritative).** `wlp-wire` derives
serde + schemars; Python validates fixtures against the emitted JSON Schema.
Option B (OpenAPI authoritative) risks courthouse wallpaper flattening the
weird parts; Option C (PyO3) is a later convenience, not a treaty.

**Phasing:**

```text
W0:   wlp-wire serde structs + JSON fixtures
W1:   axum server + reqwest client
W1.5: Python httpx client + Pydantic models
W2:   golden corpus validates Rust AND Python against the same fixtures
W3:   optional FastAPI shim
W4:   PyO3 only if embedding earns it
```

Fixture corpus from day one: `authorized / refused / cannot_testify / stale /
malformed_unknown_outcome / dual_failure_uncollapsed`.

(Namespace note: these W-numbers are the wlp treaty's own phases, NOT the
launch-runway W0–W2 in `docs/constellation-wire-plan.md`. Rename on ratification
if the collision annoys.)

---

## 3. Cross-host identity — keys as standing grants (X-series)

**The gap in §2 as drawn: everything assumes the `actor` field is true.** On one
host, process boundaries back it. Across hosts, `actor: "wicket-7"` is an
unwitnessed self-report in a JSON envelope. TLS doesn't fix it: TLS
authenticates the *pipe* (mTLS: the peer); doctrine cares about *claims*, and a
TLS conversation leaves no durable evidence of who said what. For an evidence
system, disqualifying.

**No CA needed. The PKI brain already exists: Standing.** A certificate is a
binding of identity to a key with validity window, scope, authority signature,
and revocation — *literally a standing grant over a key*. So:

```text
operator root fiat (marked as such) signs:
  key_id, public_key, component_identity, allowed_seams,
  valid_from, valid_until, revocation_observation_policy
```

Verification at the receiver = a standing check (grant valid, not lapsed, scope
covers seam, observation age within bound) — machinery and refusal types that
already exist.

**Sign the artifacts, not just the pipe.** Ed25519 over the canonical envelope,
key-id in the envelope, BOTH directions (a receipt delivered by an impostor
locker is worse than no receipt). Signed-is-not-witnessed still applies: the
signature attests authorship of the envelope, not truth of the claim.

**Canonicalization stance:** prefer signing a stable envelope over a
`payload_hash = sha256(exact payload bytes)` rather than canonicalizing a giant
everything-object. RFC 8785 JCS only if whole-message canonical JSON is truly
needed (canonical JSON is where everyone discovers Unicode has opinions).
Envelope protected fields v0: `schema, key_id, actor, seam_scope, request_id,
idempotency_key, issued_at, clock_basis, payload_hash` + ed25519 signature.

**Receiver discipline — three doors, never collapsed:**

```rust
Result<Verified<WlpWireOutcome>, ReceiveError>
// ReceiveError: TransportFailed | MalformedEnvelope | SignatureInvalid
//   | KeyStandingMissing | KeyStandingLapsed | KeyScopeMismatch
//   | ReplayDetected | ClockBasisMismatch
```

Door 1 transport failed (retry). Door 2 **speaker unproven** (typed refusals:
`signature_invalid`, `key_standing_lapsed`, `key_scope_mismatch`). Door 3
doctrine refused (valid WLP outcome). A lapsed key is not a transport error and
not a WLP refusal; converting between doors is the distributed-systems
battery-policy-misconfigured. Replay window keyed on idempotency-key + clock
witness (signed envelopes are replayable by construction).

**Phasing:**

```text
X0: overlay pipe (WireGuard/Tailscale — likely already there; don't build
    transport security twice; demotes the TLS-cert question entirely)
X1: signed envelopes, both directions, stored as durable evidence
X2: standing-backed keys (grants in registry; scope/validity/lapse/revocation
    observation policy; exactly one root-fiat ceremony)
X3: receiver failure taxonomy (the three doors + replay + clock refusals)
X4: golden corpus — good sig accepted / bad sig rejected / lapsed key rejected /
    wrong seam rejected / replay rejected / valid speaker + WLP refusal
    PRESERVED as doctrine refusal
```

**Standards: study, don't adopt wholesale.** RFC 9421 HTTP Message Signatures
(closest shape, maybe overkill), JWS/RFC 7515 (usable; JWT gravity cursed),
COSE (if CBOR later), PASETO (interesting; token-brain). Keep the treaty
smaller than any of them.

**Hard prohibition: no bearer tokens.** Possession-as-authority is the
anti-Standing — the exact semantics this architecture exists to refute. JWT-as-
bearer is especially cursed: the signature feels like provenance while the
operational semantics stay "string grants power." Signed envelopes checked
against key standing, every request.

**Anti-cathedral list:** no CA hierarchy, no cert rotation beyond standing
expiry, no service mesh, no SPIFFE at kitchen-fleet scale, no OAuth.

**Cross-host clocks:** two hosts = two clocks = cross-host gap math hits
`gap_basis_mismatch` and **refuses, correctly, by existing design**
(clock-witness spec anticipated this). Honest degradation on day one; the
temporal-authority organ stays zoned until distribution forces it.

**ssh-tunnel migration note:** tunnels were a perfectly respectable larval
stage — they solved reachability and confidentiality; they did not solve claim
provenance. Their authority model is bearer-at-host-granularity: whole pipe to
whoever holds the key, no per-claim provenance, no seam scoping, no durable
speaker evidence. The TLS critique with a different port number. Migration:
tunnels → overlay (same security property, less ceremony) + signed envelopes
(the part tunnels never had). The carved line:

> **Tunnels secured paths; signed envelopes secure claims.**

---

## 4. Testimony flow — NQ crosstalk (N-series)

Different idiom from verdict RPC: not "call and wait" but "ship receipts" —
append-only evidence shipping, push-shaped, eventually delivered. **The data
model deletes the hard parts of distributed systems**: receipts are append-only,
content-addressed, origin-signed, never mutated → replication conflicts cannot
exist by construction. Real problems: delivery, per-origin ordering, provenance.

| Problem | Mechanism |
|---|---|
| Who said this? | origin signature + standing grant |
| Already received? | content hash / receipt id (duplicate delivery = no-op → at-least-once is free and correct) |
| Missed something from origin? | per-origin sequence / hash chain (structural gap detection: have 41, receive 43 → gap at 42) |
| Relay altered testimony? | origin signature remains intact |
| What did the relay do? | transit receipt |
| Compare clocks? | mostly no — `gap_basis_mismatch`; order via chains + transit sequence, never cross-host timestamps |

**Relay-as-witness, now physical** (`signed_is_not_witnessed` coming home):
A forwarding B's testimony does not become its witness. Origin receipt carries
B's signature and witness identity forever; relay adds a transit receipt
(received-from-B, at-sequence-N, via-path-P) and never re-attests. Linode hub,
if used: **mailbox, not witness** — typed transit-class custody plumbing; not
promoted into epistemic authority for having a public IP and an invoice. Two
distinct testimony classes for the hub: "received heartbeat H from Plex-origin
at transit time T" vs "received NO admissible heartbeat from origin O within
covered interval C" — same nouns, different ontology.

**Phasing:**

```text
N0: transport — Tailscale/WireGuard mesh (NAT evaporates, topology becomes
    policy) OR outbound-push-to-linode mailbox hub (works today, zero deps,
    honest if typed; concentrates common-mode path — mesh preferred)
N1: identity — X1/X2 verbatim, four keypairs, four grants, operator fiat.
    Each grant's scope = that instance's witness competence set. The mac mini
    "not fully supported" = a NARROWER GRANT, not a hack state — partial
    participation typed, not tolerated.
N2: first flow — cross-host heartbeats, deliberately stupid. ONE stream:
    nq.heartbeat.v0 { origin_id, origin_seq, prev_hash, issued_at, clock_basis,
    witness_scope, observed_self_state_hash? }. Receiver emits nq.receive.v0,
    nq.origin_gap_detected.v0, nq.coverage_interval.v0. That proves the
    topology; everything else is adding species to the ark.
N3: selective testimony shipping — per-origin hash-chained streams with
    sequence numbers (notary-seal-v0's spine minus the full notary); ship
    witness classes by subscription, not everything-everywhere; transit
    receipts per hop; origin signatures untouched.
N4: query federation, lazy — `nq why` against the LOCAL REPLICA of shipped
    streams. Federated live queries = later organ with its own budget.
```

**N2's payoff is doctrine-grade, not monitoring:** absence coverage no longer
shares a failure domain with the watched thing. First physically-independent
witnesses (couldn't collude by sharing a power supply); the
watcher's-liveness-attested-elsewhere fixpoint finally separates. Caveat
carried in the receipt wording: heartbeat absence ≠ host death — it is "no
admissible heartbeat observed from origin O within coverage interval C by
observer R under transport/path assumptions P."

**Anti-scope list (this domain is the all-time ceremony champion):** no
consensus, no leader election, no gossip layer, no quorum anything, no CRDTs,
no vector clocks (per-origin sequences suffice when nothing mutates), no
distributed SQLite, no bidirectional sync negotiation (push-only, idempotent
receive). v0 = pipe, four grants, signed heartbeats, chained streams.

**Zoning line:** NQ-on-NQ is append-only testimony replication. Origins witness
facts; relays witness custody movement. Receivers validate provenance, preserve
origin signatures, detect per-origin gaps, and refuse cross-host temporal
claims without a shared clock basis.

---

## 5. Retraction fan-out — already filed; forcing case just moved

The third pattern. **Not testimony flow with urgency sprinkled on top — it has
inverted risk.** Lost receipt → incomplete knowledge / coverage gap; lost
revocation → **continued unauthorized reliance**. Different failure class →
different mechanics, none borrowable from the other two:

```text
retraction_id
target_claim_or_grant
retraction_reason
issuer
issued_at
reliance_index_snapshot
required_recipients
delivery_receipts
named_delivery_failures
```

The **reliance index is the ugly little organ**: without it, "notify everyone
relying" is vibes. With it, revocation becomes accountable — who was relying?
who was notified? who confirmed? who failed? **what remains exposed?** Not NQ
append flow: negative news with blast radius.

Canonical record: `docs/constellation-zoning.md` § Deferred organs →
**Retraction transport** (owner: nightshift + continuity). This doc adds one
fact: **X2 moves its forcing case from "someday" to "first key compromise"** —
the moment standing grants back wire identities, key revocation IS retraction
fan-out. Honest interim, documented as such: grants short-lived enough that
lapse does most of the work, bounded-lag revocation on the record.

---

## 6. The member/foreign axis — trust class, not transport

MCP calls and the ATProto firehose are not a fourth pattern; they are a trust
class — and the axis must stay **orthogonal to transport**. The failure mode if
it doesn't: one transport abstraction quietly lets MCP responses enter the same
evidentiary class as member testimony — "we implemented zero trust by trusting
YAML." The correct split:

```text
member endpoint:                    foreign endpoint:
  key has Standing                    no Standing
  claim can be speaker-verified       response is self-report
  scope can be checked                enters low evidence class
                                      promotion requires separate
                                        witness/notary/gate
```

Two-sided typing for foreign RPC: outbound = an *egress effect* metered by the
external-effect ledger; inbound = **unwitnessed third-party self-report at the
lowest evidence class** — same promotion discipline as log lines (a notary-gate
problem, not a transport problem). Labelwatch has run this pattern since birth
(drinking a foreign firehose); what changes is only that its reporting home
becomes cross-host member traffic.

---

## 7. Where builds land (repo zoning)

- **wlp-wire / server / client crates** → `~/git/wlp` (the treaty's home).
  AG side: consumer client + receipt vocabulary only.
- **NQ crosstalk N0–N4** → nq repo (its own custody seam; AG holds this
  recognition record + the zoning appendix, nothing more).
- **Keys-as-standing-grants (X2)** → `~/git/standing` owns grant semantics;
  envelope verification lives at each receiving seam.
- **Retraction transport** → stays zoned where the organ table puts it.
- This document is the review handle. A record is not authorization to build.
