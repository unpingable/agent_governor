.PHONY: test lint demo clean

test:
	python3 -m pytest tests/ -v

lint:
	ruff check src/ tests/ --output-format=github

# Demo GIF generation — manual only, not part of CI.
# Requires: vhs (https://github.com/charmbracelet/vhs)
# Run: make demo
demo: docs/demo/fiction.gif docs/demo/code.gif docs/demo/security.gif

docs/demo/%.gif: docs/demo/%.tape
	vhs $<

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
