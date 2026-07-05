# Run it in 30 minutes

> STATUS: CANDIDATE (docs-professionalization D-2)

Two paths, both from a fresh clone. Prerequisite: Python 3.11+.

```bash
git clone https://github.com/unpingable/agent_governor.git
cd agent_governor
python3 -m venv .venv && . .venv/bin/activate
pip install -e .
```

## Path 1 — the three-act demo (~15 min)

Follow [../TOUR.md](../TOUR.md). You will watch a credential that was
*valid when checked* get refused at the moment of spend — one second past
its horizon — then cross-examine the receipts with six runnable questions,
then see what a conventional policy engine would have said about the same
incident (it says yes; that's the point).

```bash
./demo/refused-spend.sh
demo/interrogate.sh
demo/opa-contrast.sh
```

The demo fails loudly if it passes for the wrong reason.

## Path 2 — the smallest governed workflow (~15 min)

Follow [../GOVERNED_WORKFLOW.md](../GOVERNED_WORKFLOW.md). You will
propose typed claims about a toy project, watch the governor verify them
and produce receipts, apply only what verified, and hit two refusals on
purpose (applying before verification; a claim whose test genuinely
fails). No AI agent involved — the point is the gate, and the gate does
not care who proposes.

Both documents were transcribed from live runs; every command in them was
executed with its exit code recorded before it was written down.
