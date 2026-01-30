# Agent Governor - Local Development Quickstart

This guide helps you set up local LLM development with Ollama to save on API tokens while working on Agent Governor.

## Why Local Models?

The core architecture of Agent Governor is now built. For most extension work:
- Adding new policy packs
- Writing tests
- Documentation updates
- Minor refactoring

A local model is sufficient and saves significant costs on Claude API tokens.

**Use Claude (Opus/Sonnet) for:**
- Complex architectural decisions
- Subtle bug investigation
- Major new features

**Use local models for:**
- Adding policy packs (follow existing patterns)
- Writing tests (patterns are established)
- CLI command additions
- Documentation

## Quick Setup

```bash
# Run the setup script
./scripts/local-dev.sh
```

Or follow the manual steps below.

## Manual Setup

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Linux
curl -fsSL https://ollama.com/install.sh | sh

# Verify
ollama --version
```

### 2. Pull Recommended Models

For code work on this project, these models work well:

```bash
# Best overall for coding (7B, fast)
ollama pull deepseek-coder:6.7b

# Alternative: CodeLlama (good for Python)
ollama pull codellama:7b

# Larger model if you have GPU/RAM (better quality)
ollama pull deepseek-coder:33b
```

### 3. Start Ollama Server

```bash
# Start the server (runs on localhost:11434)
ollama serve

# Or run in background
ollama serve &
```

### 4. Configure Claude Code for Ollama

Claude Code can use Ollama as a backend. Set up your environment:

```bash
# In your shell config (.bashrc, .zshrc, etc.)
export ANTHROPIC_API_KEY="your-key-here"  # Keep for fallback
export OLLAMA_HOST="http://localhost:11434"
```

### 5. Using with Claude Code

When starting Claude Code for local development:

```bash
# Use the local model flag (if supported)
claude --model ollama:deepseek-coder:6.7b

# Or set in your config
```

## Project-Specific Tips

### Policy Pack Development

The patterns are established. When adding a new policy pack:

1. Look at existing packs in `src/ops_governor/policy.py`
2. Follow the `create_*_pack()` function pattern
3. Add to `BUILTIN_PACKS` dict
4. Add tests in `tests/test_ops_governor.py`

Example prompt for local model:
```
Look at create_deploy_safe_rollout_pack() in src/ops_governor/policy.py.
Create a similar function called create_kubernetes_deploy_pack() for
Kubernetes deployments with claims for: namespace_exists, deployment_ready,
pods_healthy.
```

### Test Writing

Tests follow pytest conventions:
```
Read tests/test_ops_governor.py and add a test for the new
kubernetes/deploy policy pack. Follow the existing TestBuiltinPacks pattern.
```

### CLI Commands

CLI uses Click (main governor) and argparse (ops-gov standalone):
```
Read src/ops_governor/cli.py. Add a new 'window' subcommand to manage
change windows, similar to how 'runbook' commands are structured.
```

## Model Recommendations by Task

| Task | Recommended Model | Notes |
|------|------------------|-------|
| Add policy pack | deepseek-coder:6.7b | Pattern following |
| Write tests | deepseek-coder:6.7b | Pattern following |
| CLI commands | codellama:7b | Good at argparse |
| Bug fixes | deepseek-coder:33b+ | May need more context |
| Documentation | Any 7B model | Straightforward |
| Architecture | Claude Opus | Complex reasoning |

## Troubleshooting

### Ollama not responding
```bash
# Check if running
curl http://localhost:11434/api/tags

# Restart
pkill ollama && ollama serve
```

### Model too slow
- Use smaller quantized versions: `deepseek-coder:6.7b-instruct-q4_0`
- Ensure GPU acceleration is working: `ollama run deepseek-coder:6.7b --verbose`

### Out of memory
- Use smaller models (7B instead of 33B)
- Close other applications
- Try quantized versions (q4_0, q4_1)

## File Structure Reference

```
src/
├── governor/           # Main governor (claim verification, FSM)
├── fiction_governor/   # Fiction writing constraints
├── nonfiction_governor/# Research/citation verification
└── ops_governor/       # SRE/Ops (this is where most work happens)
    ├── types.py        # Core types (ProofType, ClaimDefinition, etc.)
    ├── policy.py       # Policy packs and claim verification
    ├── verifiers.py    # Specialized verifiers (runbook, time window, etc.)
    └── cli.py          # Standalone CLI

tests/
└── test_ops_governor.py  # Main test file for ops governor
```

## Running Tests

Always run tests after changes:
```bash
# All tests
python3 -m pytest tests/ -x -q

# Just ops_governor tests
python3 -m pytest tests/test_ops_governor.py -v

# Specific test
python3 -m pytest tests/test_ops_governor.py::TestBuiltinPacks -v
```

## Current Test Count

842 tests passing as of last update.
