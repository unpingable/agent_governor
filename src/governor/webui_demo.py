# SPDX-License-Identifier: Apache-2.0
"""
WebUI Demo — Scripted, Reproducible WebUI Screenshots.

Defines demo scenarios as data, manages screenshot generation, checks
demo freshness. Demos are build artifacts, not manual labor.

Spec: AG2_WEBUI_DEMO_GAP_SPEC.md (Layer 4, Item #12 of AG2 build order)

Principle: If the UI changes, the demos regenerate — they can't lie.
Same as VHS for CLI: alive docs.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class DemoSurface(str, Enum):
    """Which surface a demo targets."""
    CLI = "cli"
    WEBUI = "webui"
    ARCHITECTURE = "architecture"


class StepAction(str, Enum):
    """Actions available in a demo step."""
    NAVIGATE = "navigate"         # Go to a URL
    CLICK = "click"               # Click an element
    FILL = "fill"                 # Fill a text input
    SCREENSHOT = "screenshot"     # Capture screenshot
    WAIT = "wait"                 # Wait for element
    ASSERT_VISIBLE = "assert_visible"  # Assert element visible
    ASSERT_TEXT = "assert_text"   # Assert text content


class DemoStatus(str, Enum):
    """Status of a demo."""
    FRESH = "fresh"       # Screenshots exist and match current UI hash
    STALE = "stale"       # UI changed since last generation
    MISSING = "missing"   # Screenshots not yet generated
    ERROR = "error"       # Last generation failed


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DemoStep:
    """A single step in a demo scenario."""
    action: StepAction
    target: str = ""           # Selector, URL, or path
    value: str = ""            # Text to fill, assertion value
    description: str = ""      # Human-readable description
    screenshot_path: str = ""  # If action is SCREENSHOT

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "action": self.action.value,
        }
        if self.target:
            d["target"] = self.target
        if self.value:
            d["value"] = self.value
        if self.description:
            d["description"] = self.description
        if self.screenshot_path:
            d["screenshot_path"] = self.screenshot_path
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DemoStep:
        return cls(
            action=StepAction(d["action"]),
            target=d.get("target", ""),
            value=d.get("value", ""),
            description=d.get("description", ""),
            screenshot_path=d.get("screenshot_path", ""),
        )


@dataclass
class DemoScenario:
    """A complete demo scenario with steps."""
    name: str
    description: str
    surface: DemoSurface
    steps: list[DemoStep] = field(default_factory=list)
    prerequisites: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "surface": self.surface.value,
            "steps": [s.to_dict() for s in self.steps],
            "prerequisites": self.prerequisites,
            "tags": self.tags,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DemoScenario:
        return cls(
            name=d["name"],
            description=d.get("description", ""),
            surface=DemoSurface(d.get("surface", "webui")),
            steps=[DemoStep.from_dict(s) for s in d.get("steps", [])],
            prerequisites=d.get("prerequisites", []),
            tags=d.get("tags", []),
        )

    @property
    def screenshot_paths(self) -> list[str]:
        """List all screenshot paths in this scenario."""
        return [s.screenshot_path for s in self.steps if s.screenshot_path]

    def content_hash(self) -> str:
        """Hash of scenario content for freshness checking."""
        content = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Built-in scenarios
# ---------------------------------------------------------------------------

FICTION_VIOLATION_DEMO = DemoScenario(
    name="fiction_violation_flow",
    description="Fiction mode: character canon violation and resolution.",
    surface=DemoSurface.WEBUI,
    prerequisites=[
        "WebUI running (docker-compose up -d)",
        "Fiction mode enabled",
        "data-testid attributes on UI elements",
    ],
    tags=["fiction", "violation", "resolution"],
    steps=[
        DemoStep(
            action=StepAction.NAVIGATE,
            target="http://localhost:3000",
            description="Open WebUI in fiction mode",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="add-character"]',
            description="Open character creation form",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[name="name"]',
            value="Elena",
            description="Enter character name",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[name="looks"]',
            value="green eyes, tall",
            description="Set character appearance (green eyes)",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="save"]',
            description="Save character to canon",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/01-character-added.png",
            description="Capture: character added to canon",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[data-testid="chat-input"]',
            value="Elena looked at him with her blue eyes",
            description="Send message contradicting canon (blue vs green eyes)",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="send"]',
            description="Submit the message",
        ),
        DemoStep(
            action=StepAction.WAIT,
            target='[data-testid="violation-modal"]',
            description="Wait for violation modal to appear",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/02-violation.png",
            description="Capture: violation modal showing canon conflict",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="fix-button"]',
            description="Click fix to resolve the violation",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/03-resolved.png",
            description="Capture: violation resolved",
        ),
    ],
)

CODE_GOVERNANCE_DEMO = DemoScenario(
    name="code_governance_flow",
    description="Code mode: security violation detection.",
    surface=DemoSurface.WEBUI,
    prerequisites=[
        "WebUI running",
        "Code mode enabled",
    ],
    tags=["code", "security", "governance"],
    steps=[
        DemoStep(
            action=StepAction.NAVIGATE,
            target="http://localhost:3000",
            description="Open WebUI in code mode",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[data-testid="chat-input"]',
            value="Add a new API endpoint that reads user secrets from .env",
            description="Request code that might expose secrets",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="send"]',
            description="Submit the request",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/04-code-governance.png",
            description="Capture: governance sidebar showing security check",
        ),
    ],
)

INTERFEROMETRY_DEMO = DemoScenario(
    name="interferometry_flow",
    description="Compare model outputs for the same prompt.",
    surface=DemoSurface.WEBUI,
    prerequisites=[
        "WebUI running",
        "At least 2 backends configured",
    ],
    tags=["interferometry", "compare"],
    steps=[
        DemoStep(
            action=StepAction.NAVIGATE,
            target="http://localhost:3000",
            description="Open WebUI",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="compare-button"]',
            description="Open interferometry comparison",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[data-testid="compare-prompt"]',
            value="Add input validation to the login form",
            description="Enter comparison prompt",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/05-interferometry.png",
            description="Capture: side-by-side model comparison",
        ),
    ],
)

DASHBOARD_RUN_DEMO = DemoScenario(
    name="dashboard_run_flow",
    description="V2 dashboard: start a run and inspect detail view.",
    surface=DemoSurface.WEBUI,
    prerequisites=[
        "WebUI running (docker-compose up -d)",
        "Dashboard accessible at /dashboard",
    ],
    tags=["dashboard", "v2", "run"],
    steps=[
        DemoStep(
            action=StepAction.NAVIGATE,
            target="http://localhost:8000/dashboard",
            description="Open v2 governance dashboard",
        ),
        DemoStep(
            action=StepAction.FILL,
            target='[data-testid="field-task"] textarea',
            value="Run security scan on src/",
            description="Fill task description",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="start-run"]',
            description="Click Start Run",
        ),
        DemoStep(
            action=StepAction.WAIT,
            target='[data-testid="run-list"] .run-item',
            description="Wait for run to appear in list",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/06-dashboard-run-list.png",
            description="Capture: run list with new run",
        ),
        DemoStep(
            action=StepAction.CLICK,
            target='[data-testid="run-list"] .run-item',
            description="Click run to view detail",
        ),
        DemoStep(
            action=StepAction.WAIT,
            target='[data-testid="detail-content"]',
            description="Wait for detail view to load",
        ),
        DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="docs/assets/webui/07-dashboard-detail.png",
            description="Capture: run detail view",
        ),
    ],
)

BUILTIN_DEMOS = [
    FICTION_VIOLATION_DEMO,
    CODE_GOVERNANCE_DEMO,
    INTERFEROMETRY_DEMO,
    DASHBOARD_RUN_DEMO,
]


# ---------------------------------------------------------------------------
# Demo manifest — tracks generation state
# ---------------------------------------------------------------------------

@dataclass
class DemoManifest:
    """Tracks the generation state of all demos."""
    scenarios: dict[str, dict[str, Any]] = field(default_factory=dict)
    generated_at: str = ""
    ui_hash: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenarios": self.scenarios,
            "generated_at": self.generated_at,
            "ui_hash": self.ui_hash,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DemoManifest:
        return cls(
            scenarios=d.get("scenarios", {}),
            generated_at=d.get("generated_at", ""),
            ui_hash=d.get("ui_hash", ""),
        )

    def record_generation(
        self, scenario_name: str, scenario_hash: str, screenshots: list[str]
    ) -> None:
        """Record that a scenario was generated."""
        self.scenarios[scenario_name] = {
            "scenario_hash": scenario_hash,
            "screenshots": screenshots,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def is_fresh(self, scenario: DemoScenario) -> bool:
        """Check if a scenario's screenshots are fresh."""
        entry = self.scenarios.get(scenario.name)
        if not entry:
            return False
        if entry.get("scenario_hash") != scenario.content_hash():
            return False
        # Check screenshots exist
        for path in entry.get("screenshots", []):
            if not Path(path).exists():
                return False
        return True


# ---------------------------------------------------------------------------
# DemoStore — persistence
# ---------------------------------------------------------------------------

class DemoStore:
    """Persistent store for demo manifests."""

    def __init__(self, governor_dir: Path | None = None):
        self.governor_dir = governor_dir or Path(".governor")
        self.demo_dir = self.governor_dir / "demos"
        self.manifest_path = self.demo_dir / "manifest.json"

    def _ensure_dirs(self) -> None:
        self.demo_dir.mkdir(parents=True, exist_ok=True)

    def load_manifest(self) -> DemoManifest:
        if not self.manifest_path.exists():
            return DemoManifest()
        try:
            return DemoManifest.from_dict(json.loads(self.manifest_path.read_text()))
        except (json.JSONDecodeError, OSError):
            return DemoManifest()

    def save_manifest(self, manifest: DemoManifest) -> None:
        self._ensure_dirs()
        self.manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2) + "\n")

    def check_freshness(self) -> list[dict[str, Any]]:
        """Check freshness of all built-in demos."""
        manifest = self.load_manifest()
        results: list[dict[str, Any]] = []

        for demo in BUILTIN_DEMOS:
            if manifest.is_fresh(demo):
                status = DemoStatus.FRESH
            elif demo.name in manifest.scenarios:
                status = DemoStatus.STALE
            else:
                status = DemoStatus.MISSING

            results.append({
                "name": demo.name,
                "status": status.value,
                "screenshots": demo.screenshot_paths,
                "scenario_hash": demo.content_hash(),
            })

        return results

    def save_scenario(self, scenario: DemoScenario) -> Path:
        """Save a scenario definition as JSON."""
        self._ensure_dirs()
        path = self.demo_dir / f"{scenario.name}.json"
        path.write_text(json.dumps(scenario.to_dict(), indent=2) + "\n")
        return path

    def list_scenarios(self) -> list[DemoScenario]:
        """List all available scenarios (built-in + custom)."""
        scenarios = list(BUILTIN_DEMOS)

        # Load custom scenarios
        if self.demo_dir.exists():
            for f in self.demo_dir.glob("*.json"):
                if f.name == "manifest.json":
                    continue
                try:
                    d = json.loads(f.read_text())
                    s = DemoScenario.from_dict(d)
                    # Don't duplicate built-in names
                    if not any(b.name == s.name for b in BUILTIN_DEMOS):
                        scenarios.append(s)
                except (json.JSONDecodeError, KeyError):
                    pass

        return scenarios


# ---------------------------------------------------------------------------
# Playwright spec generation
# ---------------------------------------------------------------------------

def generate_playwright_spec(scenario: DemoScenario) -> str:
    """Generate a Playwright test spec from a scenario.

    This produces TypeScript that can be run with `npx playwright test`.
    """
    lines: list[str] = []
    lines.append(f"// Auto-generated from demo scenario: {scenario.name}")
    lines.append(f"// {scenario.description}")
    lines.append(f"// Prerequisites: {', '.join(scenario.prerequisites)}")
    lines.append("")
    lines.append("import { test, expect } from '@playwright/test';")
    lines.append("")
    lines.append(f"test('{scenario.name}', async ({{ page }}) => {{")

    for step in scenario.steps:
        if step.description:
            lines.append(f"  // {step.description}")

        if step.action == StepAction.NAVIGATE:
            lines.append(f"  await page.goto('{step.target}');")
        elif step.action == StepAction.CLICK:
            lines.append(f"  await page.click('{step.target}');")
        elif step.action == StepAction.FILL:
            lines.append(f"  await page.fill('{step.target}', '{step.value}');")
        elif step.action == StepAction.SCREENSHOT:
            lines.append(f"  await page.screenshot({{ path: '{step.screenshot_path}' }});")
        elif step.action == StepAction.WAIT:
            lines.append(f"  await page.waitForSelector('{step.target}');")
        elif step.action == StepAction.ASSERT_VISIBLE:
            lines.append(f"  await expect(page.locator('{step.target}')).toBeVisible();")
        elif step.action == StepAction.ASSERT_TEXT:
            lines.append(f"  await expect(page.locator('{step.target}')).toContainText('{step.value}');")

        lines.append("")

    lines.append("});")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Telemetry event
# ---------------------------------------------------------------------------

def make_demo_event(
    action: str, scenario_name: str = "", details: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Create a telemetry event for demo actions."""
    return {
        "type": "webui_demo",
        "action": action,
        "scenario_name": scenario_name,
        "details": details or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
