# Getting Started

Install, try it, see what it does. Five minutes.

## Install

```bash
git clone https://github.com/unpingable/agent_governor.git
cd agent_governor
pip install -e .
```

## Initialize

In any project directory:

```bash
governor init
```

## Try the gate

Tell it something an agent might say:

```bash
governor gate check "All tests pass. The auth module is thread-safe."
```

You'll see:

```
OK: output validated
  - 1 claims made, all supported
Receipt: 7e8d512e...
```

The gate checked the text, extracted claims, and issued a receipt. Right now everything passes because you haven't told it what to enforce.

## Add a rule

```bash
governor continuity anchor add \
  --id "no-eval" \
  --type prohibition \
  --description "Never use eval() in production code" \
  --forbidden "eval(" \
  --severity reject \
  --class invariant
```

Now try again:

```bash
governor continuity check "I refactored the query to use eval(user_input) for dynamic filters."
```

```
FAILED (1 violations, score=0.00, action=hard_reprompt)
  [REJECT] no-eval: Forbidden pattern found: 'eval('
```

Blocked. The agent would have to find another approach.

## Check a file

```bash
echo 'API_KEY = "sk-ant-api03-1234567890abcdef"' > demo.py
governor check demo.py
```

```
[ERROR] demo.py:1:1 SECURITY.SECRET_LEAK: Potential API key detected
```

Security scanning works out of the box. Anchors add your project-specific rules on top.

## See your receipts

```bash
governor receipts --last 5
```

Every gate decision is receipted. Content-addressed, hash-chained.

## What next

| I want to... | Go here |
|---|---|
| Supervise a Claude Code session | [Supervised Mode](SUPERVISED_MODE.md) |
| Add governor as a Claude Code plugin | [Plugin Quickstart](QUICKSTART_PLUGIN.md) |
| Understand the full system | [README](../README.md) |
| Use the TUI | [Maude](https://github.com/unpingable/maude) |
