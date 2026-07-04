# Candidate: external communication as a channel-generic class

**Status:** CANDIDATE — non-binding. Record, NOT stub. Provenance: operator
framing, 2026-07-04 (during the maude legibility pass, where the supervised
intervention warning `COMMUNICATE` became `External send`). Promote only with a
forcing case + explicit ratification. **No hooks, no adapters, no aspirational
integration architecture until the authority model exists.**

## The thing to write down

`External send` is **not email-specific**. It is the first visible instance of a
broader class: *communication that leaves the machine / local workspace*. Email
(`send_email`) is the current specimen surfaced by the runtime supervisor; it
should not be treated as the category.

Later channels enter as **communication adapters under the same operator-approval
+ receipt semantics**, e.g.:

```
email / send_email          (current specimen)
slack / post_message
slack / dm
webhook / post
github / comment
issue / update
```

## The likely object (sketch — do NOT build yet)

```
CommunicationIntent
  channel_kind
  destination
  payload_summary
  sensitivity
  actor_claim
  requires_operator_approval
  receipt_expected
```

Adapters then become **cargo handlers, not authority sources** — which is exactly
the intermodal rule from [WORK_CONTAINER.md](WORK_CONTAINER.md): a terminal
transports; it does not mint. Authority (approve + receipt) stays central; the
channel adapter only moves the payload.

## Why record-not-stub

Stubbing fake hooks that *look* operational before the authority model exists is
the worst outcome: aspirational integration architecture that implies supported
channels that don't exist. Naming the seam costs nothing and prevents the
email-specific special-case from calcifying. Building the adapters before a
forcing case is speculative expansion (YAGNI).

## Do-not

- Do not add channel hooks / adapters before the CommunicationIntent authority
  model is ratified.
- Do not imply supported channels (Slack/webhook/GitHub) before they exist.
- Do not let `send_email` become the category — it is one specimen.
- Do not promote to doctrine without a forcing case + ratification.
