# Future Enhancements

## Fiction Governor

- [ ] **Prompt generator** - `fiction-gov prompt scene --chapter 4 --characters elena,marcus` outputs ready-to-paste prompt with bible + recent canon context
- [ ] **Manuscript scanner** - Parse existing chapters to auto-populate canon events
- [ ] **Embedding similarity** - Use embeddings for smarter anti-pattern matching (currently just keywords)
- [ ] **Plot threads** - Track Chekhov's guns, foreshadowing, unresolved threads
- [ ] **Scene proposals** - `fiction-gov propose` workflow with approve/reject/revise

## Main Governor

- [ ] **MCP server** - Expose governor as an MCP tool for Claude Desktop/other clients
- [ ] **Claude Code hooks** - Actual hook scripts that integrate with `claude` CLI
- [ ] **Git pre-commit hook** - Verify claims before allowing commits
- [ ] **Watch mode** - Continuously monitor directory, verify on change
- [ ] **Security verifier** - Check for common vulnerabilities (secrets in code, SQL injection patterns)

## Cross-cutting

- [ ] **Web UI** - Simple dashboard showing claim history, rejection rates
- [ ] **Config profiles** - `governor profile use strict` vs `governor profile use permissive`
