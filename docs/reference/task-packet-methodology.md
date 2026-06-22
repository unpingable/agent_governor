# Task Packet Methodology

**Status: PROVISIONAL** (landed 2026-06-22). Prose companion to
`docs/reference/task-packet-template.md`. The **template** describes the brief handed to a
builder. This **methodology** describes the step before that: how you decide a packet should
exist at all, and whether packets may batch. It is the front-half the template assumes.

This document is itself a worked example: the three artifacts committed on 2026-06-22
(`weak_property` laundering-conservation, `closure-authority-incumbency`,
`organ-separation-and-refusal-closure`, plus the `packet-waiver-completeness` brief) were
each produced by running this methodology on a design dialogue. The deflation each time —
"most of this already exists; here is the small additive residue" — *is* the method working.

## The failure mode this prevents

```
discover a seam
→ overgeneralize it into architecture
→ spawn agents
→ agents rebuild existing substrate
→ repo becomes an archaeological crime scene
```

The dangerous energy is not scarcity of ideas; it is an idea at 1 a.m. that *feels* like new
architecture and is mostly already built. The methodology converts idea-energy into bounded,
admitted work — or into an explicit refusal to build. **Before batching work, govern
batching.**

## Front-half: from idea to (maybe) a packet

A packet is *earned*, not assumed. Four steps, before any template field is filled:

### 1. Intake — normalize to claims

Input is messy (a dialogue, a grep finding, an operator rant from a car in Michigan). Output
is a flat list of candidate **claims**, each a single sentence: "Waiver admission must be
downstream-visible." "Planner is refusal-closure." Not "implement organ separation" — that
is a program, not a claim.

### 2. Substrate check — the deflation step

For each claim, classify against the *actual repo* (this is `grep-before-sketch` /
`grep-receipts-before-paper-specs` operationalized — memory
`feedback_grep_before_sketch`). The categories:

| Verdict | Action |
|---|---|
| **Already exists** | Discard. Do not re-file, do not build. |
| **Already exists but under-named** | Doctrine note or index pointer, *not* code. (Highest-value category — most "new ideas" land here.) |
| **Completeness gap** | Packet candidate. Gap on an *opened* surface — finish it (completeness lane, memory `feedback_completeness_overrules_forcing_case_monitoring`). |
| **New build surface** | Forcing-case gate applies (YAGNI). Usually a record, not a build, until a forcing case exists. |
| **Rejected / duplicate / dangerous** | Tombstone (below). |

The grep is non-optional. Today three dialogues' worth of "new architecture" collapsed to
~four additive sentences against `activation.py`, `gate_receipt.py`, `overrides.py`, and the
zoning notes.

### 3. Delta extraction — packet from a sentence, not a program

A packet is born from a sentence naming what *exists* and what is *missing*:

> Existing `OverrideReceipt` is scoped/expiring, but waiver-admitted acts do not yet carry a
> verdict-distinct, downstream-visible non-claim that clean antecedents were not satisfied.

Never: "implement organ separation" (exists). The delta sentence becomes the template's
Objective; the named existing modules become its Scope fence and read-only context.

### 4. Tombstone — refuse a build, on the record

A claim classified "rejected / new-surface-without-forcing-case" gets a **tombstone**: a
short record of "considered, won't build (yet), here is the resurrection condition." This is
the anti-reincarnation valve — it stops the same shiny idea returning three conversations
later in a fake mustache. AG already does this informally: parked memories, reserved-but-
unfiled gap names (`recovery_topology_candidate`, `amendment_fragment_candidate`), and the
"named, not built, forcing case = X" sections in the cross-tool notes. The methodology just
names the move. A tombstone is a legitimate packet outcome — produce it, don't skip it.

## The discover≠implement invariant

The single rule that keeps overnight / delegated execution honest:

> **No packet may both discover and implement.** Execution agents may emit a
> `FollowupCandidate` (a claim back into intake); they may not self-spawn work from it.

Discovery resets to intake → substrate-check → human-or-operator admission. Otherwise the
gremlins unionize: an agent finds a seam mid-run and "helpfully" builds through it, which is
exactly the substrate-rebuild failure mode, now unsupervised.

The consolidated catechism — note each line **points at doctrine AG already holds**, this is
a checklist, not new law:

```
No packet both discovers and implements.        (this section; loop dispatch-and-verify)
No packet both defines an interface and consumes it.   (organ-separation note: build-independence)
No packet touches multiple organs without declaring seam status.  (organ-separation note)
No packet widens authority without a visible receipt.  (weak_property / laundering conservation)
No packet creates a silent success path.         (no-silent-path pin; laundering conservation)
```

## Batch eligibility (prose rules — NOT a scheduler)

This is a YAGNI-record: the *rules* for when two packets may run in parallel, written down so
they exist as a handle, with **no scheduler/router built** (the template's deliberate
non-build stands; memory `feedback_yagni_scope`). Two packets may batch only when **all** hold:

1. Allowed-file sets are disjoint.
2. Neither violates the other's forbidden-files.
3. Neither changes a shared interface.
4. Neither is a cross-organ seam.
5. Each has an independent, self-checkable exit receipt.

Default-parallel-safe: doctrine-only, schema/types-only, test-only, organ-local with disjoint
files, synthetic-graph-algorithm work. Default-serialized: kernel interface, ledger
transaction semantics, waiver choreography, consumer admission behavior, storage migrations,
**anything touching `activation.py`**. The organ separation enforced for *soundness* is what
makes parallelism *safe* — same fact, two uses (see
`docs/cross-tool/organ-separation-and-refusal-closure-note.md`).

## Overnight shape (if/when delegated execution runs)

```
Evening:   packetize · substrate-check · dependency sort · freeze the packet set
Overnight: run independent packets · fail closed on forbidden-file diffs · emit patch receipts
Morning:   inspect receipts · merge one at a time · run integration suite · tombstone failures
```

The dogfood verdict (does the pipeline that gates this still hold?) is operator-side and
never delegated — an agent grading the pipeline that gates it is self-amendment-adjacent
(memory `feedback_campaign_card_discipline`).

## Authoring surface: structured Markdown, stable headings

The format is Markdown — but *structured* Markdown, not essay soup. The distinction that
matters:

> **Markdown is the authoring surface; stable headings are the structure; a code schema
> waits for a forcing consumer.**

LLM executors do better with **named slots** (the regularity the packet experiments showed),
and named slots live perfectly well in headings — they do not require YAML. The template's
ten fields *are* the stable slot names; render them as regular Markdown headings (the
`packet-waiver-completeness` brief is the reference rendering). Same heading names, same
order, every packet — that regularity is the whole benefit a schema would have bought, minus
the costs.

A machine-readable block (YAML/JSON front-matter, or a fenced `deps/files/tests` block) is
justified **only when a real consumer parses it** — not before. The forcing consumers, named
so the trigger is recognizable when it arrives:

- an overnight runner that needs machine-readable `deps` / `allowed_files` / verify commands;
- CI that validates packet structure;
- a dashboard that indexes packet status;
- an AG scheduler that dispatches packets.

Until one of those exists, YAML is a costume the prose wears to look employed — and it drags
in a validation surface, migration burden, compatibility promises, and the failure mode where
**fields become authority by accident** and agents optimize to satisfy the schema instead of
doing the work. That is the "schema as institution" disease this very methodology exists to
prevent; do not contract it five minutes after writing the cure. When a forcing consumer does
arrive, add the machine block *alongside* the prose (the prose stays the source of truth for
review), and let the parser read only the block it needs.

## Not built (deliberately)

- **No Packetizer subsystem, no code.** This is prose, like the template. No forcing case.
- **No YAML/JSON packet schema, no validator, no enum** — the template's own non-build, kept.
- **No typed `packet-kind` / `organ-scope` enum.** The classifications here are a *human
  checklist*, exactly like the sizing rubric. Do not promote into code (tripwire: memory
  `feedback_kind_fit_is_guard_not_enum` — kind-fit is a guard, not an enum).
- **No scheduler/router wiring.** Batch rules are prose until a real multi-packet overnight
  run forces them (and even then, wiring is a separate ratchet leg with its own evidence).

## Composes with

- `docs/reference/task-packet-template.md` — the brief fields this front-half feeds.
- `docs/cross-tool/organ-separation-and-refusal-closure-note.md` — organ separation = the
  build-independence graph that makes batch eligibility decidable.
- `docs/doctrine/weak_property_strong_property.md` — "no silent success path" / "no authority
  widening without visible receipt" are instances of laundering conservation.
- memory `feedback_grep_before_sketch`, `feedback_yagni_scope`,
  `feedback_kind_fit_is_guard_not_enum`, `feedback_campaign_card_discipline`.
