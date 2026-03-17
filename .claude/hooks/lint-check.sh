#!/bin/bash
# PostToolUse hook: run ruff on the file that was just written/edited.
# Reads tool input from stdin (JSON), extracts file_path, runs ruff.
# Outputs additionalContext on lint errors so Claude sees them immediately.

set -euo pipefail

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('tool_name',''))" 2>/dev/null || true)

# Only check Write/Edit on Python files
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    exit 0
fi

FILE_PATH=$(echo "$INPUT" | python3 -c "
import sys, json
d = json.load(sys.stdin)
ti = d.get('tool_input', {})
print(ti.get('file_path', ti.get('path', '')))
" 2>/dev/null || true)

if [[ -z "$FILE_PATH" || ! "$FILE_PATH" == *.py ]]; then
    exit 0
fi

if [[ ! -f "$FILE_PATH" ]]; then
    exit 0
fi

# Run ruff on just this file
ERRORS=$(python3 -m ruff check "$FILE_PATH" 2>/dev/null || true)

if [[ -n "$ERRORS" ]]; then
    # Output context so Claude sees the lint errors
    python3 -c "
import json, sys
print(json.dumps({
    'hookSpecificOutput': {
        'hookEventName': 'PostToolUse',
        'additionalContext': 'LINT ERRORS in $FILE_PATH:\\n' + '''$ERRORS'''
    }
}))
"
fi
