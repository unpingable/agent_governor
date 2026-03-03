# SPDX-License-Identifier: Apache-2.0
"""Tests for WebUI Demo — Scripted, Reproducible WebUI Screenshots.

AG2 Layer 4, Item #12 of the AG2 build order.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from governor.webui_demo import (
    DemoSurface,
    StepAction,
    DemoStatus,
    DemoStep,
    DemoScenario,
    DemoManifest,
    DemoStore,
    BUILTIN_DEMOS,
    FICTION_VIOLATION_DEMO,
    CODE_GOVERNANCE_DEMO,
    INTERFEROMETRY_DEMO,
    DASHBOARD_RUN_DEMO,
    generate_playwright_spec,
    make_demo_event,
)


# ---------------------------------------------------------------------------
# Enum Tests
# ---------------------------------------------------------------------------

class TestDemoSurface:
    def test_values(self):
        assert DemoSurface.CLI.value == "cli"
        assert DemoSurface.WEBUI.value == "webui"
        assert DemoSurface.ARCHITECTURE.value == "architecture"

    def test_str_enum(self):
        assert str(DemoSurface.WEBUI) == "DemoSurface.WEBUI"
        assert DemoSurface("webui") == DemoSurface.WEBUI

    def test_all_values(self):
        assert len(DemoSurface) == 3


class TestStepAction:
    def test_values(self):
        assert StepAction.NAVIGATE.value == "navigate"
        assert StepAction.CLICK.value == "click"
        assert StepAction.FILL.value == "fill"
        assert StepAction.SCREENSHOT.value == "screenshot"
        assert StepAction.WAIT.value == "wait"
        assert StepAction.ASSERT_VISIBLE.value == "assert_visible"
        assert StepAction.ASSERT_TEXT.value == "assert_text"

    def test_all_values(self):
        assert len(StepAction) == 7


class TestDemoStatus:
    def test_values(self):
        assert DemoStatus.FRESH.value == "fresh"
        assert DemoStatus.STALE.value == "stale"
        assert DemoStatus.MISSING.value == "missing"
        assert DemoStatus.ERROR.value == "error"

    def test_all_values(self):
        assert len(DemoStatus) == 4


# ---------------------------------------------------------------------------
# DemoStep Tests
# ---------------------------------------------------------------------------

class TestDemoStep:
    def test_create_minimal(self):
        step = DemoStep(action=StepAction.NAVIGATE)
        assert step.action == StepAction.NAVIGATE
        assert step.target == ""
        assert step.value == ""
        assert step.description == ""
        assert step.screenshot_path == ""

    def test_create_full(self):
        step = DemoStep(
            action=StepAction.FILL,
            target='[name="email"]',
            value="test@example.com",
            description="Fill email field",
            screenshot_path="docs/shot.png",
        )
        assert step.action == StepAction.FILL
        assert step.target == '[name="email"]'
        assert step.value == "test@example.com"
        assert step.description == "Fill email field"
        assert step.screenshot_path == "docs/shot.png"

    def test_to_dict_minimal(self):
        step = DemoStep(action=StepAction.CLICK)
        d = step.to_dict()
        assert d == {"action": "click"}
        assert "target" not in d
        assert "value" not in d

    def test_to_dict_full(self):
        step = DemoStep(
            action=StepAction.FILL,
            target='[name="email"]',
            value="test@example.com",
            description="Fill email",
            screenshot_path="shot.png",
        )
        d = step.to_dict()
        assert d["action"] == "fill"
        assert d["target"] == '[name="email"]'
        assert d["value"] == "test@example.com"
        assert d["description"] == "Fill email"
        assert d["screenshot_path"] == "shot.png"

    def test_from_dict_minimal(self):
        step = DemoStep.from_dict({"action": "navigate"})
        assert step.action == StepAction.NAVIGATE
        assert step.target == ""

    def test_from_dict_full(self):
        d = {
            "action": "screenshot",
            "target": "",
            "description": "Capture page",
            "screenshot_path": "docs/page.png",
        }
        step = DemoStep.from_dict(d)
        assert step.action == StepAction.SCREENSHOT
        assert step.screenshot_path == "docs/page.png"

    def test_roundtrip(self):
        step = DemoStep(
            action=StepAction.ASSERT_TEXT,
            target='[data-testid="status"]',
            value="Passed",
            description="Verify status text",
        )
        restored = DemoStep.from_dict(step.to_dict())
        assert restored.action == step.action
        assert restored.target == step.target
        assert restored.value == step.value
        assert restored.description == step.description


# ---------------------------------------------------------------------------
# DemoScenario Tests
# ---------------------------------------------------------------------------

class TestDemoScenario:
    def test_create_minimal(self):
        s = DemoScenario(
            name="test_demo",
            description="A test demo",
            surface=DemoSurface.WEBUI,
        )
        assert s.name == "test_demo"
        assert s.description == "A test demo"
        assert s.surface == DemoSurface.WEBUI
        assert s.steps == []
        assert s.prerequisites == []
        assert s.tags == []

    def test_create_with_steps(self):
        s = DemoScenario(
            name="test_demo",
            description="Demo with steps",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost:3000"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="shot.png"),
            ],
            prerequisites=["WebUI running"],
            tags=["test"],
        )
        assert len(s.steps) == 2
        assert s.prerequisites == ["WebUI running"]
        assert s.tags == ["test"]

    def test_to_dict(self):
        s = DemoScenario(
            name="my_demo",
            description="Test",
            surface=DemoSurface.CLI,
            steps=[DemoStep(action=StepAction.NAVIGATE, target="http://example.com")],
            tags=["cli"],
        )
        d = s.to_dict()
        assert d["name"] == "my_demo"
        assert d["surface"] == "cli"
        assert len(d["steps"]) == 1
        assert d["steps"][0]["action"] == "navigate"
        assert d["tags"] == ["cli"]

    def test_from_dict(self):
        d = {
            "name": "restored",
            "description": "From dict",
            "surface": "architecture",
            "steps": [{"action": "click", "target": "#btn"}],
            "prerequisites": ["Something"],
            "tags": ["arch"],
        }
        s = DemoScenario.from_dict(d)
        assert s.name == "restored"
        assert s.surface == DemoSurface.ARCHITECTURE
        assert len(s.steps) == 1
        assert s.steps[0].action == StepAction.CLICK
        assert s.steps[0].target == "#btn"

    def test_from_dict_defaults(self):
        d = {"name": "minimal"}
        s = DemoScenario.from_dict(d)
        assert s.description == ""
        assert s.surface == DemoSurface.WEBUI
        assert s.steps == []
        assert s.prerequisites == []
        assert s.tags == []

    def test_roundtrip(self):
        s = DemoScenario(
            name="roundtrip",
            description="Roundtrip test",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost"),
                DemoStep(action=StepAction.CLICK, target="#btn", description="Click"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="shot.png"),
            ],
            prerequisites=["Server up"],
            tags=["test", "roundtrip"],
        )
        restored = DemoScenario.from_dict(s.to_dict())
        assert restored.name == s.name
        assert restored.surface == s.surface
        assert len(restored.steps) == len(s.steps)
        assert restored.prerequisites == s.prerequisites
        assert restored.tags == s.tags

    def test_screenshot_paths(self):
        s = DemoScenario(
            name="paths_test",
            description="Test paths extraction",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="a.png"),
                DemoStep(action=StepAction.CLICK, target="#x"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="b.png"),
            ],
        )
        assert s.screenshot_paths == ["a.png", "b.png"]

    def test_screenshot_paths_empty(self):
        s = DemoScenario(
            name="no_shots",
            description="No screenshots",
            surface=DemoSurface.CLI,
            steps=[DemoStep(action=StepAction.NAVIGATE, target="http://localhost")],
        )
        assert s.screenshot_paths == []

    def test_dedup_fingerprint_deterministic(self):
        s = DemoScenario(name="hash_test", description="Hashing", surface=DemoSurface.WEBUI)
        h1 = s.dedup_fingerprint()
        h2 = s.dedup_fingerprint()
        assert h1 == h2
        assert len(h1) == 16  # sha256[:16]

    def test_dedup_fingerprint_changes_with_content(self):
        s1 = DemoScenario(name="a", description="v1", surface=DemoSurface.WEBUI)
        s2 = DemoScenario(name="a", description="v2", surface=DemoSurface.WEBUI)
        assert s1.dedup_fingerprint() != s2.dedup_fingerprint()

    def test_dedup_fingerprint_changes_with_steps(self):
        s1 = DemoScenario(name="a", description="x", surface=DemoSurface.WEBUI)
        s2 = DemoScenario(
            name="a", description="x", surface=DemoSurface.WEBUI,
            steps=[DemoStep(action=StepAction.CLICK, target="#btn")],
        )
        assert s1.dedup_fingerprint() != s2.dedup_fingerprint()


# ---------------------------------------------------------------------------
# Built-in Demo Tests
# ---------------------------------------------------------------------------

class TestBuiltinDemos:
    def test_builtin_count(self):
        assert len(BUILTIN_DEMOS) == 4

    def test_fiction_demo(self):
        d = FICTION_VIOLATION_DEMO
        assert d.name == "fiction_violation_flow"
        assert d.surface == DemoSurface.WEBUI
        assert len(d.steps) == 12
        assert "fiction" in d.tags
        assert len(d.screenshot_paths) == 3

    def test_code_demo(self):
        d = CODE_GOVERNANCE_DEMO
        assert d.name == "code_governance_flow"
        assert d.surface == DemoSurface.WEBUI
        assert len(d.steps) == 4
        assert "security" in d.tags
        assert len(d.screenshot_paths) == 1

    def test_interferometry_demo(self):
        d = INTERFEROMETRY_DEMO
        assert d.name == "interferometry_flow"
        assert d.surface == DemoSurface.WEBUI
        assert len(d.steps) == 4
        assert "interferometry" in d.tags
        assert len(d.screenshot_paths) == 1

    def test_dashboard_demo(self):
        d = DASHBOARD_RUN_DEMO
        assert d.name == "dashboard_run_flow"
        assert d.surface == DemoSurface.WEBUI
        assert len(d.steps) == 8
        assert "dashboard" in d.tags
        assert "v2" in d.tags
        assert len(d.screenshot_paths) == 2

    def test_dashboard_demo_targets_dashboard_url(self):
        d = DASHBOARD_RUN_DEMO
        nav_step = d.steps[0]
        assert nav_step.action == StepAction.NAVIGATE
        assert "/dashboard" in nav_step.target

    def test_all_have_unique_names(self):
        names = [d.name for d in BUILTIN_DEMOS]
        assert len(names) == len(set(names))

    def test_all_serialize(self):
        for d in BUILTIN_DEMOS:
            data = d.to_dict()
            assert isinstance(data, dict)
            restored = DemoScenario.from_dict(data)
            assert restored.name == d.name

    def test_all_have_content_hash(self):
        for d in BUILTIN_DEMOS:
            h = d.dedup_fingerprint()
            assert len(h) == 16
            assert h.isalnum()


# ---------------------------------------------------------------------------
# DemoManifest Tests
# ---------------------------------------------------------------------------

class TestDemoManifest:
    def test_create_empty(self):
        m = DemoManifest()
        assert m.scenarios == {}
        assert m.generated_at == ""
        assert m.ui_hash == ""

    def test_to_dict(self):
        m = DemoManifest(
            scenarios={"test": {"scenario_hash": "abc123"}},
            generated_at="2025-01-01T00:00:00Z",
            ui_hash="xyz789",
        )
        d = m.to_dict()
        assert d["scenarios"]["test"]["scenario_hash"] == "abc123"
        assert d["generated_at"] == "2025-01-01T00:00:00Z"
        assert d["ui_hash"] == "xyz789"

    def test_from_dict(self):
        d = {
            "scenarios": {"demo1": {"scenario_hash": "h1", "screenshots": ["a.png"]}},
            "generated_at": "2025-06-01",
            "ui_hash": "uihash",
        }
        m = DemoManifest.from_dict(d)
        assert "demo1" in m.scenarios
        assert m.ui_hash == "uihash"

    def test_from_dict_defaults(self):
        m = DemoManifest.from_dict({})
        assert m.scenarios == {}
        assert m.generated_at == ""
        assert m.ui_hash == ""

    def test_roundtrip(self):
        m = DemoManifest(
            scenarios={"s1": {"scenario_hash": "h1", "screenshots": ["a.png"]}},
            generated_at="2025-01-01",
            ui_hash="abc",
        )
        restored = DemoManifest.from_dict(m.to_dict())
        assert restored.scenarios == m.scenarios
        assert restored.generated_at == m.generated_at
        assert restored.ui_hash == m.ui_hash

    def test_record_generation(self):
        m = DemoManifest()
        m.record_generation("demo1", "hash123", ["a.png", "b.png"])
        assert "demo1" in m.scenarios
        entry = m.scenarios["demo1"]
        assert entry["scenario_hash"] == "hash123"
        assert entry["screenshots"] == ["a.png", "b.png"]
        assert "generated_at" in entry

    def test_record_generation_overwrites(self):
        m = DemoManifest()
        m.record_generation("demo1", "v1", ["old.png"])
        m.record_generation("demo1", "v2", ["new.png"])
        assert m.scenarios["demo1"]["scenario_hash"] == "v2"
        assert m.scenarios["demo1"]["screenshots"] == ["new.png"]

    def test_is_fresh_missing(self):
        m = DemoManifest()
        s = DemoScenario(name="not_recorded", description="", surface=DemoSurface.WEBUI)
        assert not m.is_fresh(s)

    def test_is_fresh_hash_mismatch(self):
        m = DemoManifest()
        s = DemoScenario(name="demo", description="v1", surface=DemoSurface.WEBUI)
        m.record_generation("demo", "wrong_hash", [])
        assert not m.is_fresh(s)

    def test_is_fresh_screenshot_missing(self, tmp_path):
        m = DemoManifest()
        s = DemoScenario(name="demo", description="test", surface=DemoSurface.WEBUI)
        missing_path = str(tmp_path / "nonexistent.png")
        m.record_generation("demo", s.dedup_fingerprint(), [missing_path])
        assert not m.is_fresh(s)

    def test_is_fresh_all_ok(self, tmp_path):
        m = DemoManifest()
        s = DemoScenario(name="demo", description="test", surface=DemoSurface.WEBUI)
        shot_path = str(tmp_path / "shot.png")
        Path(shot_path).write_text("fake image")
        m.record_generation("demo", s.dedup_fingerprint(), [shot_path])
        assert m.is_fresh(s)

    def test_is_fresh_no_screenshots_needed(self):
        m = DemoManifest()
        s = DemoScenario(name="demo", description="test", surface=DemoSurface.WEBUI)
        m.record_generation("demo", s.dedup_fingerprint(), [])
        assert m.is_fresh(s)


# ---------------------------------------------------------------------------
# DemoStore Tests
# ---------------------------------------------------------------------------

class TestDemoStore:
    def test_create(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        assert store.governor_dir == tmp_path / ".governor"
        assert store.demo_dir == tmp_path / ".governor" / "demos"

    def test_load_manifest_empty(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        m = store.load_manifest()
        assert m.scenarios == {}

    def test_save_and_load_manifest(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        m = DemoManifest()
        m.record_generation("demo1", "hash1", ["a.png"])
        store.save_manifest(m)

        loaded = store.load_manifest()
        assert "demo1" in loaded.scenarios
        assert loaded.scenarios["demo1"]["scenario_hash"] == "hash1"

    def test_save_manifest_creates_dirs(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        m = DemoManifest()
        store.save_manifest(m)
        assert store.demo_dir.exists()
        assert store.manifest_path.exists()

    def test_load_manifest_corrupt(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        store.demo_dir.mkdir(parents=True)
        store.manifest_path.write_text("not json{{{")
        m = store.load_manifest()
        assert m.scenarios == {}

    def test_check_freshness_all_missing(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        results = store.check_freshness()
        assert len(results) == 4
        for r in results:
            assert r["status"] == "missing"

    def test_check_freshness_stale(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        m = DemoManifest()
        m.record_generation(FICTION_VIOLATION_DEMO.name, "wrong_hash", [])
        store.save_manifest(m)
        results = store.check_freshness()
        fiction_result = next(r for r in results if r["name"] == "fiction_violation_flow")
        assert fiction_result["status"] == "stale"

    def test_check_freshness_fresh(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        demo = FICTION_VIOLATION_DEMO
        m = DemoManifest()
        # Create screenshot files
        for path in demo.screenshot_paths:
            full = tmp_path / path
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("fake image")
        m.record_generation(
            demo.name, demo.dedup_fingerprint(),
            [str(tmp_path / p) for p in demo.screenshot_paths],
        )
        store.save_manifest(m)
        results = store.check_freshness()
        fiction_result = next(r for r in results if r["name"] == "fiction_violation_flow")
        assert fiction_result["status"] == "fresh"

    def test_save_scenario(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        s = DemoScenario(
            name="custom_demo",
            description="A custom demo",
            surface=DemoSurface.WEBUI,
        )
        path = store.save_scenario(s)
        assert path.exists()
        loaded = json.loads(path.read_text())
        assert loaded["name"] == "custom_demo"

    def test_list_scenarios_builtin_only(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        scenarios = store.list_scenarios()
        assert len(scenarios) == 4
        names = [s.name for s in scenarios]
        assert "fiction_violation_flow" in names

    def test_list_scenarios_with_custom(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        custom = DemoScenario(
            name="my_custom",
            description="Custom scenario",
            surface=DemoSurface.CLI,
        )
        store.save_scenario(custom)
        scenarios = store.list_scenarios()
        assert len(scenarios) == 5
        names = [s.name for s in scenarios]
        assert "my_custom" in names

    def test_list_scenarios_no_duplicate_builtin(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        # Save a scenario with same name as built-in
        dup = DemoScenario(
            name="fiction_violation_flow",
            description="Duplicate",
            surface=DemoSurface.WEBUI,
        )
        store.save_scenario(dup)
        scenarios = store.list_scenarios()
        # Should not duplicate
        names = [s.name for s in scenarios]
        assert names.count("fiction_violation_flow") == 1

    def test_list_scenarios_ignores_manifest(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        m = DemoManifest()
        store.save_manifest(m)
        scenarios = store.list_scenarios()
        assert len(scenarios) == 4  # Only built-ins, manifest.json ignored

    def test_list_scenarios_ignores_invalid_json(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        store.demo_dir.mkdir(parents=True)
        (store.demo_dir / "bad.json").write_text("not valid json{{{")
        scenarios = store.list_scenarios()
        assert len(scenarios) == 4  # Only built-ins


# ---------------------------------------------------------------------------
# Playwright Spec Generation Tests
# ---------------------------------------------------------------------------

class TestPlaywrightSpec:
    def test_generates_typescript(self):
        s = DemoScenario(
            name="simple_test",
            description="A simple test",
            surface=DemoSurface.WEBUI,
            prerequisites=["WebUI running"],
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost:3000"),
            ],
        )
        spec = generate_playwright_spec(s)
        assert "import { test, expect } from '@playwright/test'" in spec
        assert "test('simple_test'" in spec
        assert "await page.goto('http://localhost:3000')" in spec

    def test_all_action_types(self):
        s = DemoScenario(
            name="all_actions",
            description="All action types",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost"),
                DemoStep(action=StepAction.CLICK, target="#btn"),
                DemoStep(action=StepAction.FILL, target="#input", value="hello"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="shot.png"),
                DemoStep(action=StepAction.WAIT, target="#loading"),
                DemoStep(action=StepAction.ASSERT_VISIBLE, target="#result"),
                DemoStep(action=StepAction.ASSERT_TEXT, target="#msg", value="OK"),
            ],
        )
        spec = generate_playwright_spec(s)
        assert "page.goto" in spec
        assert "page.click" in spec
        assert "page.fill" in spec
        assert "page.screenshot" in spec
        assert "page.waitForSelector" in spec
        assert "toBeVisible" in spec
        assert "toContainText" in spec

    def test_descriptions_as_comments(self):
        s = DemoScenario(
            name="comments_test",
            description="Testing comments",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(
                    action=StepAction.CLICK,
                    target="#btn",
                    description="Click the button",
                ),
            ],
        )
        spec = generate_playwright_spec(s)
        assert "// Click the button" in spec

    def test_prerequisites_in_header(self):
        s = DemoScenario(
            name="prereq_test",
            description="Prereq test",
            surface=DemoSurface.WEBUI,
            prerequisites=["Docker running", "Port 3000 free"],
        )
        spec = generate_playwright_spec(s)
        assert "Docker running" in spec
        assert "Port 3000 free" in spec

    def test_empty_scenario(self):
        s = DemoScenario(
            name="empty",
            description="Empty scenario",
            surface=DemoSurface.WEBUI,
        )
        spec = generate_playwright_spec(s)
        assert "test('empty'" in spec
        assert "});" in spec

    def test_fiction_demo_spec(self):
        spec = generate_playwright_spec(FICTION_VIOLATION_DEMO)
        assert "fiction_violation_flow" in spec
        assert "page.goto" in spec
        assert "page.screenshot" in spec
        assert "waitForSelector" in spec

    def test_code_demo_spec(self):
        spec = generate_playwright_spec(CODE_GOVERNANCE_DEMO)
        assert "code_governance_flow" in spec
        assert "page.fill" in spec

    def test_interferometry_demo_spec(self):
        spec = generate_playwright_spec(INTERFEROMETRY_DEMO)
        assert "interferometry_flow" in spec

    def test_dashboard_demo_spec(self):
        spec = generate_playwright_spec(DASHBOARD_RUN_DEMO)
        assert "dashboard_run_flow" in spec
        assert "page.goto" in spec
        assert "/dashboard" in spec
        assert "page.fill" in spec
        assert "page.screenshot" in spec
        assert "waitForSelector" in spec


# ---------------------------------------------------------------------------
# Telemetry Event Tests
# ---------------------------------------------------------------------------

class TestDemoEvent:
    def test_create_event(self):
        evt = make_demo_event("generate", "my_demo", {"profile": "fiction"})
        assert evt["type"] == "webui_demo"
        assert evt["action"] == "generate"
        assert evt["scenario_name"] == "my_demo"
        assert evt["details"]["profile"] == "fiction"
        assert "ts" in evt

    def test_create_event_minimal(self):
        evt = make_demo_event("check")
        assert evt["type"] == "webui_demo"
        assert evt["action"] == "check"
        assert evt["scenario_name"] == ""
        assert evt["details"] == {}

    def test_create_event_no_details(self):
        evt = make_demo_event("list", "demo1")
        assert evt["details"] == {}


# ---------------------------------------------------------------------------
# Golden Schema Tests (JSON structure locking)
# ---------------------------------------------------------------------------

class TestGoldenSchemas:
    def test_demo_step_schema(self):
        step = DemoStep(
            action=StepAction.FILL,
            target="#input",
            value="text",
            description="Fill input",
            screenshot_path="",
        )
        d = step.to_dict()
        assert set(d.keys()) == {"action", "target", "value", "description"}

    def test_demo_step_schema_with_screenshot(self):
        step = DemoStep(
            action=StepAction.SCREENSHOT,
            screenshot_path="shot.png",
        )
        d = step.to_dict()
        assert "screenshot_path" in d
        assert "action" in d

    def test_demo_scenario_schema(self):
        s = DemoScenario(
            name="test", description="test", surface=DemoSurface.WEBUI,
            steps=[], prerequisites=[], tags=[],
        )
        d = s.to_dict()
        assert set(d.keys()) == {"name", "description", "surface", "steps", "prerequisites", "tags"}

    def test_demo_manifest_schema(self):
        m = DemoManifest()
        d = m.to_dict()
        assert set(d.keys()) == {"scenarios", "generated_at", "ui_hash"}

    def test_demo_event_schema(self):
        evt = make_demo_event("test", "demo", {"k": "v"})
        assert set(evt.keys()) == {"type", "action", "scenario_name", "details", "ts"}

    def test_freshness_result_schema(self, tmp_path):
        store = DemoStore(governor_dir=tmp_path / ".governor")
        results = store.check_freshness()
        for r in results:
            assert set(r.keys()) == {"name", "status", "screenshots", "scenario_hash"}


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_lifecycle(self, tmp_path):
        """Create store → save scenario → record generation → check freshness."""
        store = DemoStore(governor_dir=tmp_path / ".governor")

        # Custom scenario
        scenario = DemoScenario(
            name="lifecycle_test",
            description="Full lifecycle",
            surface=DemoSurface.WEBUI,
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="shot.png"),
            ],
            tags=["test"],
        )

        # Save scenario
        path = store.save_scenario(scenario)
        assert path.exists()

        # Initially missing
        results = store.check_freshness()
        # Only builtin demos in freshness check
        assert all(r["status"] == "missing" for r in results)

        # Record generation for a built-in
        m = store.load_manifest()
        demo = FICTION_VIOLATION_DEMO
        for p in demo.screenshot_paths:
            full = tmp_path / p
            full.parent.mkdir(parents=True, exist_ok=True)
            full.write_text("image data")
        m.record_generation(
            demo.name, demo.dedup_fingerprint(),
            [str(tmp_path / p) for p in demo.screenshot_paths],
        )
        store.save_manifest(m)

        # Now fiction demo should be fresh
        results = store.check_freshness()
        fiction = next(r for r in results if r["name"] == "fiction_violation_flow")
        assert fiction["status"] == "fresh"

    def test_scenario_to_spec_to_store(self, tmp_path):
        """Create scenario → generate spec → save both."""
        store = DemoStore(governor_dir=tmp_path / ".governor")

        scenario = DemoScenario(
            name="spec_test",
            description="Spec generation test",
            surface=DemoSurface.WEBUI,
            prerequisites=["Server running"],
            steps=[
                DemoStep(action=StepAction.NAVIGATE, target="http://localhost:3000"),
                DemoStep(action=StepAction.CLICK, target="#btn", description="Click button"),
                DemoStep(action=StepAction.SCREENSHOT, screenshot_path="result.png"),
            ],
        )

        # Save scenario
        store.save_scenario(scenario)

        # Generate Playwright spec
        spec = generate_playwright_spec(scenario)
        assert "spec_test" in spec
        assert "page.goto" in spec
        assert "page.click" in spec
        assert "page.screenshot" in spec

        # List shows custom scenario
        scenarios = store.list_scenarios()
        assert any(s.name == "spec_test" for s in scenarios)

    def test_manifest_persistence(self, tmp_path):
        """Manifest survives save/load cycle."""
        store = DemoStore(governor_dir=tmp_path / ".governor")

        m = DemoManifest(ui_hash="initial_hash")
        m.record_generation("demo1", "hash1", ["a.png"])
        m.record_generation("demo2", "hash2", ["b.png", "c.png"])
        store.save_manifest(m)

        # Re-create store from same dir
        store2 = DemoStore(governor_dir=tmp_path / ".governor")
        m2 = store2.load_manifest()
        assert m2.ui_hash == "initial_hash"
        assert len(m2.scenarios) == 2
        assert m2.scenarios["demo1"]["scenario_hash"] == "hash1"
        assert m2.scenarios["demo2"]["screenshots"] == ["b.png", "c.png"]


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_empty_steps_serialization(self):
        s = DemoScenario(name="empty", description="", surface=DemoSurface.WEBUI)
        d = s.to_dict()
        restored = DemoScenario.from_dict(d)
        assert restored.steps == []

    def test_step_with_special_chars(self):
        step = DemoStep(
            action=StepAction.FILL,
            target='[name="email"]',
            value="user@example.com",
        )
        d = step.to_dict()
        restored = DemoStep.from_dict(d)
        assert restored.value == "user@example.com"
        assert '"' in restored.target

    def test_scenario_json_sortable_hash(self):
        """Content hash uses sort_keys=True for deterministic hashing."""
        s1 = DemoScenario(
            name="a", description="b", surface=DemoSurface.WEBUI,
            tags=["x", "y"],
        )
        # Same content should always produce same hash
        hashes = {s1.dedup_fingerprint() for _ in range(10)}
        assert len(hashes) == 1

    def test_store_default_dir(self):
        store = DemoStore()
        assert store.governor_dir == Path(".governor")

    def test_manifest_from_dict_with_extra_keys(self):
        """from_dict should tolerate extra keys."""
        d = {
            "scenarios": {},
            "generated_at": "",
            "ui_hash": "",
            "extra_field": "ignored",
        }
        m = DemoManifest.from_dict(d)
        assert m.scenarios == {}
