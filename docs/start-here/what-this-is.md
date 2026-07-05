# What this is

> STATUS: CANDIDATE (docs-professionalization D-2)

**This is a way to let AI tools help with operational work while keeping
every action bounded, reviewable, and backed by receipts.**

**Agents can propose work. They cannot approve themselves.**

Teams are being pushed to put AI agents on real work, and nobody sane wants
one freehanding production. The usual answer — "a human is in the loop" —
is often theater: the human clicks approve on things they cannot check.

This project's answer is structural. An agent's output enters as a
*proposal* — it carries no authority of its own, no matter how confident
the prose sounds. Proposals run against gates that can say **no** and say
**why**, on the record: a refusal is a first-class outcome with a typed
reason, not an error to route around. And every decision — approvals and
refusals alike — leaves a **receipt** you can inspect afterward without
trusting anyone's summary of what happened.

What it is **not**: not a hosted service, not an agent framework, not a
claim of production hardening. It is alpha software, installed from
source, with its limits stated plainly (see the README's status line and
the [non-grants list](../NON_GRANTS.md) — the receipts are tamper-evident,
not tamper-proof, against someone with filesystem access).

Who it's for: ops/SRE people with scar tissue, security-adjacent
engineers, and staff engineers who've been asked to bless an agentic
workflow and want something firmer than vibes to bless.

Where to go next:

- [10-minute-inspect.md](10-minute-inspect.md) — check the receipts
  yourself, no install.
- [30-minute-run.md](30-minute-run.md) — run the demo and a governed
  workflow locally.
- [concepts.md](concepts.md) — the vocabulary, plain words first.
