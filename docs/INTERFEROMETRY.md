# Interferometry — Multi-Model Claim Comparison

Interferometry sends the same question to multiple AI backends and compares
what they claim. Where models agree, confidence goes up. Where they disagree,
you get a signal worth investigating.

## Two Modes

### Parallel Mode (default)

Send the same prompt to N backends simultaneously. Each response is
independently analyzed for implicit claims (dates, quantities, assertions),
then claims are compared across responses via Jaccard fingerprinting.

```bash
governor interferometry run "When was the Treaty of Westphalia signed?" \
  --backends ollama:llama3,anthropic:claude-3-haiku
```

### Serial Mode ("Yes, and")

A deliberation chain: model A answers first, then model B sees A's response
and provides its own take — agreeing, disagreeing, or adding context.
Repeat for N rounds.

```bash
governor interferometry run "What caused the 2008 financial crisis?" \
  --backends ollama:llama3,anthropic:claude-3-haiku \
  --mode serial \
  --rounds 2
```

With `--rounds 2` and 2 backends, you get 3 total steps:
1. Model A answers the original prompt
2. Model B sees A's answer and responds
3. Model A sees B's response and responds

Backends cycle round-robin, so with 3 backends and 2 rounds you'd get
A → B → C.

## What It Produces

Every run produces:

- **Shared claims**: Assertions that appear in 2+ model responses
- **Unique claims**: Assertions from only one model
- **Conflicting claims**: Same topic but different specifics (e.g. different dates)
- **Signals**: Disagreement rate, specifics conflict count

## Commands

```bash
# Run interferometry (parallel is default)
governor interferometry run "prompt" --backends ollama:llama3,anthropic:claude-3-haiku

# Run serial deliberation
governor interferometry run "prompt" -b ollama:m1,ollama:m2 --mode serial --rounds 1

# List all runs
governor interferometry results

# Show most recent run
governor interferometry results --last

# Show specific run
governor interferometry results --id abc123def456

# JSON output
governor interferometry results --last --json

# Show divergence summary
governor interferometry divergence

# Promote shared claims to the epistemic ledger
governor interferometry accept --shared

# Also promote unique claims (at low confidence)
governor interferometry accept --all
```

## Backend Format

Backends are specified as `type:model` pairs, comma-separated:

```
ollama:llama3
anthropic:claude-3-haiku
claude-code:sonnet
codex:o3
```

Auth is pulled from environment variables automatically:
- `ANTHROPIC_API_KEY` for anthropic
- `OLLAMA_HOST` for ollama (default: `http://localhost:11434`)
- `CLAUDE_PATH` for claude-code
- `CODEX_PATH` for codex

## How Claim Comparison Works

1. **Extraction**: Each response is scanned for implicit claims using
   `SignalExtractor` (dates, entities, quantities, assertive phrases).

2. **Fingerprinting**: Each claim is tokenized and fingerprinted using
   token-set Jaccard (same algorithm as taint detection).

3. **Clustering**: Claims are grouped by fingerprint similarity (default
   threshold: 0.65). Claims above threshold are in the same cluster.

4. **Alignment**: Clusters appearing in 2+ models are "shared". Single-model
   clusters are "unique". Clusters where models produce different specific
   values (dates, numbers) are "conflicting".

## Ledger Integration

Promoted claims go into the epistemic ledger:

- **Shared claims** → `Provenance.DERIVED`, confidence = proportion of models
  that agree (e.g. 2/3 = 0.67)
- **Unique claims** → `Provenance.ASSUMED`, confidence = 0.2

This means shared claims from interferometry get real epistemic weight,
while unique claims are registered but flagged as low-confidence assumptions.

## Persistence

Runs are saved as JSON in `.governor/interferometry/`. Each run gets its own
file (`{run_id}.json`) containing the full prompt, all responses, extracted
claims, alignment results, and signals.

## When to Use Which Mode

| Scenario | Mode | Why |
|----------|------|-----|
| Fact-checking a claim | Parallel | Independent verification, no contamination |
| Exploring a complex topic | Serial | Models build on each other's reasoning |
| Checking for hallucination | Parallel | Disagreement = red flag |
| Research brainstorming | Serial | "Yes, and" accumulates insights |
| Comparing model capabilities | Parallel | Apples-to-apples on same prompt |
