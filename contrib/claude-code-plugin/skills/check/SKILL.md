---
description: Run a governor policy check on the current workspace or action
---

Use the governor MCP tools to evaluate the current workspace state against
active governance policy. Summarize:

- Current regime and lane
- Active violations (if any)
- What actions would be denied right now
- Receipt coverage status
- Minimal steps to become compliant (if violations exist)

If no governor directory exists, report that governance is not initialized
and suggest running `governor init`.
