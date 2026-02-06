# WebUI Demo Specification

## Version 0.1 — Scripted, Reproducible WebUI Screenshots

```yaml
status: gap
implemented: false
depends_on: [WEBUI_UX_SPEC.md]
blocking: documentation credibility (WebUI)
estimated_scope: medium
```

---

## Executive Summary

CLI demos use VHS (scripted terminal recordings). WebUI demos should use Playwright (scripted browser automation). Screenshots and video are build artifacts, not manual labor. If the UI changes, the demos regenerate — they can't lie.

---

## 1. The Principle

Same as VHS for CLI: **alive docs**.

| Surface | Tool | Output | Trigger |
|---------|------|--------|---------|
| CLI | VHS | `.gif` | `make demo` (manual) |
| WebUI | Playwright | `.png` / `.mp4` | `make webui-demo` (manual) |
| Architecture | Mermaid | `.svg` / embedded | Inline in markdown |

All scripted. All regenerate on release. All impossible to drift.

---

## 2. Demo Flow

The primary demo captures the fiction-mode violation flow:

1. Navigate to WebUI (fiction mode)
2. Add a character with canon traits
3. Send a message that contradicts canon
4. Screenshot the violation modal
5. Resolve via fix
6. Screenshot the result

### 2.1 Playwright Spec (sketch)

```typescript
// docs/webui-demo.spec.ts
test('fiction mode violation flow', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // Add character
  await page.click('[data-testid="add-character"]');
  await page.fill('[name="name"]', 'Elena');
  await page.fill('[name="looks"]', 'green eyes, tall');
  await page.click('[data-testid="save"]');
  await page.screenshot({ path: 'docs/assets/webui/01-character-added.png' });

  // Trigger violation
  await page.fill('[data-testid="chat-input"]', 'Elena looked at him with her blue eyes');
  await page.click('[data-testid="send"]');

  // Capture violation modal
  await page.waitForSelector('[data-testid="violation-modal"]');
  await page.screenshot({ path: 'docs/assets/webui/02-violation.png' });

  // Resolve
  await page.click('[data-testid="fix-button"]');
  await page.screenshot({ path: 'docs/assets/webui/03-resolved.png' });
});
```

### 2.2 Prerequisites

- WebUI needs `data-testid` attributes on key elements (add-character, chat-input, send, violation-modal, fix-button)
- Docker Compose stack running (`docker-compose up -d`)
- Backend with a model that can trigger violations (Ollama or mock)

---

## 3. CI Integration (future)

```yaml
- name: Generate WebUI screenshots
  run: |
    docker-compose up -d
    npx playwright test docs/webui-demo.spec.ts
    docker-compose down
```

Manual-only initially (like VHS demos). Automate once the WebUI has enough human testing to stabilize the selectors.

---

## 4. Blocking On

- Sufficient human testing of the WebUI to stabilize the flow
- `data-testid` attributes on key UI elements
- Decision on mock backend vs live backend for demo generation

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 0.1 | 2025-02-06 | Initial gap spec |
