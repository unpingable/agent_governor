# Security Policy

## Reporting Vulnerabilities

**Do not file security issues as public GitHub Issues.**

Use [GitHub's private vulnerability reporting](https://github.com/unpingable/agent_governor/security/advisories/new) or email the maintainer directly.

## Response Time

Best-effort. This is a solo-maintained project with no SLA. Expect acknowledgment within a week for genuine vulnerabilities; fixes depend on severity and complexity.

## Scope

**In scope:** the governor kernel itself — evidence gate, receipt chain, claim extraction, pre-commit hooks, daemon, MCP server, CLI. Anything that could allow an agent to bypass enforcement or forge receipts.

**Out of scope:** the models being constrained, third-party dependencies, deployment infrastructure you configure, or anything in the threat model's "trusted host" assumption.

## Context

Agent Governor is a constraint system, not a security product. It assumes the host is trusted and defends against untrusted agent behavior (fabricated claims, unverified writes, temporal drift). We still take vulnerabilities in the kernel seriously — a forged receipt or bypassed gate undermines the entire enforcement model.

## Disclosure

We follow coordinated disclosure. If you report a vulnerability, we'll work with you on timeline and credit. No bounties (solo project, no budget), but we'll credit you in the fix commit and release notes.
