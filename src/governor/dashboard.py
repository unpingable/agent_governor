# SPDX-License-Identifier: Apache-2.0
"""
Telemetry Dashboard - Real-time regime visualization.

Rich TUI for visualizing governor state, regime transitions, and system health.

Usage:
    governor dashboard              # Live dashboard (refreshes from logs)
    governor dashboard replay PATH  # Replay trace file
    governor dashboard --demo       # Generate and play demo trace

Design (adapted from epistemic_governor observability):
    - Phase Space: λ (event arrival) vs μ (resolution rate)
    - Regime Gauge: ELASTIC → WARM → DUCTILE → UNSTABLE
    - Energy Trace: Rolling system stress over time
    - Event Log: Recent decisions, violations, interventions
"""

import argparse
import json
import random
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Deque

try:
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.align import Align
    from rich.table import Table
    from rich.console import Console
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False


# =============================================================================
# Phase Space Plot
# =============================================================================

class PhaseSpacePlot:
    """
    Visualizes system stability: arrival rate (λ) vs resolution rate (μ).

    - Below diagonal (green): Stable - resolving faster than arriving
    - Above diagonal (red): Unstable - arriving faster than resolving
    """

    def __init__(self, history_len: int = 30):
        self.history: Deque[tuple[float, float]] = deque(maxlen=history_len)
        self.width = 40
        self.height = 15

    def update(self, lambda_val: float, mu_val: float) -> None:
        """Add a new data point."""
        self.history.append((lambda_val, mu_val))

    def render(self) -> Panel:
        """Render the phase space plot."""
        # Create grid
        grid = [[" " for _ in range(self.width)] for _ in range(self.height)]

        # Draw stability boundary (diagonal y=x)
        for i in range(min(self.width, self.height)):
            r = (self.height - 1) - i
            c = int(i * self.width / self.height)
            if 0 <= r < self.height and 0 <= c < self.width:
                grid[r][c] = "[dim]·[/]"

        # Draw axes
        for r in range(self.height):
            grid[r][0] = "[dim]│[/]"
        for c in range(self.width):
            grid[self.height - 1][c] = "[dim]─[/]"
        grid[self.height - 1][0] = "[dim]└[/]"

        # Plot history trail
        if self.history:
            max_lambda = max(max(h[0] for h in self.history), 1)
            max_mu = max(max(h[1] for h in self.history), 1)
            scale_x = (self.width - 2) / max_lambda
            scale_y = (self.height - 2) / max_mu

            for i, (lam, mu) in enumerate(self.history):
                x = int(lam * scale_x) + 1
                y = int(mu * scale_y)
                r = (self.height - 2) - y

                # Clamp to grid
                r = max(0, min(self.height - 2, r))
                x = max(1, min(self.width - 1, x))

                # Color: red if unstable (λ > μ), green if stable
                color = "red" if lam > mu else "green"
                opacity = "dim" if i < len(self.history) - 5 else "bold"
                char = "●" if i == len(self.history) - 1 else "·"

                grid[r][x] = f"[{opacity} {color}]{char}[/]"

        # Render to string
        rows = ["".join(row) for row in grid]
        chart = "\n".join(rows)

        return Panel(
            chart,
            title="[bold cyan]Phase Space[/] [dim](λ vs μ)[/]",
            subtitle="[dim]▲μ resolve  →λ arrive | [green]●stable[/] [red]●unstable[/][/]",
            border_style="cyan",
        )


# =============================================================================
# Regime Gauge
# =============================================================================

class RegimeGauge:
    """
    Visualizes current operational regime and system pressure.

    Regimes:
    - ELASTIC: Normal operation
    - WARM: Elevated load
    - DUCTILE: High stress
    - UNSTABLE: Critical state
    """

    COLORS = {
        "ELASTIC": "green",
        "WARM": "yellow",
        "DUCTILE": "orange1",
        "UNSTABLE": "red",
        "UNKNOWN": "white",
    }

    ICONS = {
        "ELASTIC": "🟢",
        "WARM": "🟡",
        "DUCTILE": "🟠",
        "UNSTABLE": "🔴",
        "UNKNOWN": "⚪",
    }

    def render(
        self,
        regime: str,
        stress: float,
        violations: int = 0,
        proposals: int = 0,
        rejections: int = 0,
    ) -> Panel:
        """Render the regime gauge."""
        color = self.COLORS.get(regime, "white")
        icon = self.ICONS.get(regime, "⚪")

        # Pressure bar
        bar_width = 25
        filled = int(stress * bar_width)
        bar = f"[{color}]" + "█" * filled + "[dim]░[/]" * (bar_width - filled) + "[/]"

        # Rejection rate color
        if proposals > 0:
            rej_rate = rejections / proposals
            rej_color = "green" if rej_rate < 0.1 else "yellow" if rej_rate < 0.3 else "red"
            rej_text = f"{rej_rate:.0%}"
        else:
            rej_color = "dim"
            rej_text = "N/A"

        # Build content table
        content = Table.grid(padding=(0, 1))
        content.add_column(justify="right", style="bold")
        content.add_column(justify="left")

        content.add_row("Regime:", f"[bold {color}]{icon} {regime}[/]")
        content.add_row("Pressure:", f"{bar} {stress:.0%}")
        content.add_row("Violations:", f"[{'red' if violations > 0 else 'green'}]{violations}[/]")
        content.add_row("Proposals:", f"[cyan]{proposals}[/]")
        content.add_row("Rejection Rate:", f"[{rej_color}]{rej_text}[/]")

        return Panel(
            Align.center(content, vertical="middle"),
            title="[bold]System Vitals[/]",
            border_style=color,
        )


# =============================================================================
# Energy Sparkline
# =============================================================================

class EnergySparkline:
    """Rolling sparkline of system stress/energy."""

    def __init__(self, width: int = 60):
        self.history: Deque[float] = deque(maxlen=width)
        self.width = width

    def update(self, energy: float) -> None:
        self.history.append(energy)

    def render(self) -> Panel:
        """Render the sparkline."""
        if not self.history:
            return Panel("[dim]No data[/]", title="System Load")

        # Normalize to 0-1 range
        max_e = max(max(self.history), 0.01)
        normalized = [e / max_e for e in self.history]

        # Convert to spark characters
        chars = " ▁▂▃▄▅▆▇█"
        spark = ""
        for v in normalized:
            idx = int(v * (len(chars) - 1))
            # Color based on value
            if v < 0.3:
                spark += f"[green]{chars[idx]}[/]"
            elif v < 0.6:
                spark += f"[yellow]{chars[idx]}[/]"
            else:
                spark += f"[red]{chars[idx]}[/]"

        # Stats
        current = self.history[-1] if self.history else 0
        avg = sum(self.history) / len(self.history)

        content = f"{spark}\n[dim]Current: {current:.1f} | Avg: {avg:.1f} | Max: {max_e:.1f}[/]"

        return Panel(
            Align.center(content),
            title="[bold]System Load[/]",
            border_style="blue",
        )


# =============================================================================
# Event Log
# =============================================================================

class EventLog:
    """Scrolling log of recent events."""

    def __init__(self, max_entries: int = 12):
        self.entries: Deque[str] = deque(maxlen=max_entries)

    def add(self, event_type: str, details: str = "", level: str = "info") -> None:
        """Add a log entry."""
        symbols = {
            "proposal": "[bold cyan]◆[/]",
            "verification": "[bold green]✓[/]",
            "llm_call": "[bold blue]⚡[/]",
            "error": "[bold red]✗[/]",
            "security_scan": "[bold yellow]🔒[/]",
            "claim_registered": "[bold magenta]◇[/]",
            "autonomous_iteration": "[bold white]↻[/]",
            "continuity_trace": "[bold cyan]〰[/]",
            "continuity_result": "[bold green]◎[/]",
            "profile_change": "[bold yellow]⚙[/]",
        }

        level_colors = {
            "debug": "dim",
            "info": "white",
            "warn": "yellow",
            "error": "red",
        }

        symbol = symbols.get(event_type, "[dim]·[/]")
        color = level_colors.get(level, "white")
        ts = datetime.now().strftime("%H:%M:%S")

        detail_str = f" [{color}]{details[:40]}[/]" if details else ""
        self.entries.append(f"[dim]{ts}[/] {symbol} {event_type}{detail_str}")

    def render(self) -> Panel:
        """Render the event log."""
        if not self.entries:
            content = "[dim]Waiting for events...[/]"
        else:
            content = "\n".join(self.entries)

        return Panel(
            content,
            title="[bold]Event Log[/]",
            border_style="white",
        )


# =============================================================================
# Budget Panel
# =============================================================================

class BudgetPanel:
    """Shows budget status and spending rate."""

    def __init__(self):
        self.spent = 0.0
        self.budget = 0.0
        self.tokens = 0
        self.history: Deque[float] = deque(maxlen=20)

    def update(self, spent: float, budget: float = 0.0, tokens: int = 0) -> None:
        self.spent = spent
        self.budget = budget
        self.tokens = tokens
        self.history.append(spent)

    def render(self) -> Panel:
        """Render budget status."""
        # Spending bar (if budget set)
        if self.budget > 0:
            pct = min(1.0, self.spent / self.budget)
            color = "green" if pct < 0.5 else "yellow" if pct < 0.8 else "red"
            bar_width = 20
            filled = int(pct * bar_width)
            bar = f"[{color}]" + "█" * filled + "[dim]░[/]" * (bar_width - filled) + "[/]"
            budget_line = f"Budget: {bar} ${self.spent:.2f}/${self.budget:.2f}"
        else:
            budget_line = f"Spent: [cyan]${self.spent:.4f}[/]"

        # Token count
        if self.tokens > 1_000_000:
            token_str = f"{self.tokens / 1_000_000:.1f}M"
        elif self.tokens > 1_000:
            token_str = f"{self.tokens / 1_000:.1f}K"
        else:
            token_str = str(self.tokens)

        content = f"{budget_line}\nTokens: [blue]{token_str}[/]"

        return Panel(
            Align.center(content),
            title="[bold]Budget[/]",
            border_style="cyan",
        )


# =============================================================================
# Dashboard State
# =============================================================================

@dataclass
class DashboardState:
    """Aggregated dashboard state."""
    regime: str = "UNKNOWN"
    stress: float = 0.0
    violations: int = 0
    proposals: int = 0
    rejections: int = 0
    spent_usd: float = 0.0
    budget_usd: float = 0.0
    tokens: int = 0
    lambda_rate: float = 0.0
    mu_rate: float = 0.0
    energy: float = 0.0
    events: list[dict[str, Any]] = field(default_factory=list)


# =============================================================================
# Log Parser
# =============================================================================

def parse_log_line(line: str) -> dict[str, Any] | None:
    """Parse a JSONL log line into an event dict."""
    try:
        return json.loads(line.strip())
    except json.JSONDecodeError:
        return None


def load_recent_logs(log_dir: Path, max_lines: int = 500) -> list[dict[str, Any]]:
    """Load recent log entries from the logs directory."""
    if not log_dir.exists():
        return []

    # Find most recent log file
    log_files = sorted(log_dir.glob("governor-*.jsonl"), reverse=True)
    if not log_files:
        return []

    events = []
    for log_file in log_files[:3]:  # Check last 3 days of logs
        try:
            with open(log_file, 'r') as f:
                for line in f:
                    event = parse_log_line(line)
                    if event:
                        events.append(event)
                    if len(events) >= max_lines:
                        break
        except (IOError, OSError):
            continue
        if len(events) >= max_lines:
            break

    return events[-max_lines:]  # Most recent


def compute_state_from_events(events: list[dict[str, Any]]) -> DashboardState:
    """Compute dashboard state from recent events."""
    state = DashboardState()

    # Count event types
    for event in events:
        event_type = event.get("event_type", "")
        level = event.get("level", "info")
        fields = event.get("fields", {})

        if event_type == "proposal":
            state.proposals += 1
        elif event_type == "verification":
            if not fields.get("success", True):
                state.rejections += 1
        elif event_type == "error":
            state.violations += 1
        elif event_type == "llm_call":
            state.tokens += fields.get("tokens_used", 0)
            state.spent_usd += fields.get("cost_usd", 0.0)

    # Estimate rates from recent events
    recent_count = min(50, len(events))
    if recent_count > 0:
        recent_events = events[-recent_count:]
        arrivals = sum(1 for e in recent_events if e.get("event_type") in ("proposal", "claim_registered"))
        resolutions = sum(1 for e in recent_events if e.get("event_type") == "verification" and e.get("fields", {}).get("success", True))

        state.lambda_rate = arrivals / recent_count * 10
        state.mu_rate = resolutions / recent_count * 10

    # Compute stress (simplified: based on rejection rate and error count)
    if state.proposals > 0:
        rej_rate = state.rejections / state.proposals
    else:
        rej_rate = 0
    state.stress = min(1.0, rej_rate + state.violations * 0.1)
    state.energy = state.stress * 10 + state.violations

    # Determine regime based on stress
    if state.stress < 0.2:
        state.regime = "ELASTIC"
    elif state.stress < 0.4:
        state.regime = "WARM"
    elif state.stress < 0.7:
        state.regime = "DUCTILE"
    else:
        state.regime = "UNSTABLE"

    state.events = events[-20:]  # Keep recent for event log
    return state


# =============================================================================
# Main TUI Runner
# =============================================================================

def run_live_dashboard(log_dir: Path, refresh_interval: float = 2.0) -> None:
    """Run live dashboard that refreshes from logs."""
    if not RICH_AVAILABLE:
        print("Error: Rich library required. Install with: pip install rich")
        return

    console = Console()

    # Initialize widgets
    phase_plot = PhaseSpacePlot()
    regime_gauge = RegimeGauge()
    energy_spark = EnergySparkline()
    event_log = EventLog()
    budget_panel = BudgetPanel()

    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=12),
        Layout(name="middle", size=6),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(
        Layout(name="gauge", ratio=1),
        Layout(name="phase", ratio=1),
    )
    layout["middle"].split_row(
        Layout(name="energy", ratio=2),
        Layout(name="budget", ratio=1),
    )

    console.print("[cyan]Governor Dashboard - Live Mode[/]")
    console.print(f"[dim]Log directory: {log_dir}[/]")
    console.print("[dim]Press Ctrl+C to stop[/]\n")
    time.sleep(1)

    last_event_count = 0

    with Live(layout, refresh_per_second=2, screen=True, console=console) as live:
        while True:
            try:
                # Load recent logs
                events = load_recent_logs(log_dir)
                state = compute_state_from_events(events)

                # Update widgets
                phase_plot.update(state.lambda_rate + 1, state.mu_rate + 1)
                energy_spark.update(state.energy)
                budget_panel.update(state.spent_usd, state.budget_usd, state.tokens)

                # Add new events to log
                if len(events) > last_event_count:
                    for event in events[last_event_count:]:
                        event_log.add(
                            event.get("event_type", "unknown"),
                            str(event.get("fields", {}))[:40],
                            event.get("level", "info"),
                        )
                    last_event_count = len(events)

                # Update layout
                layout["top"]["gauge"].update(
                    regime_gauge.render(
                        state.regime, state.stress,
                        state.violations, state.proposals, state.rejections
                    )
                )
                layout["top"]["phase"].update(phase_plot.render())
                layout["middle"]["energy"].update(energy_spark.render())
                layout["middle"]["budget"].update(budget_panel.render())
                layout["bottom"].update(event_log.render())

                time.sleep(refresh_interval)

            except KeyboardInterrupt:
                break
            except Exception as e:
                event_log.add("error", str(e)[:40], "error")

    console.print("\n[cyan]Dashboard stopped.[/]")


def run_replay(trace_path: Path, speed: float = 1.0) -> None:
    """Replay a trace file through the dashboard."""
    if not RICH_AVAILABLE:
        print("Error: Rich library required. Install with: pip install rich")
        return

    if not trace_path.exists():
        print(f"Error: Trace file not found: {trace_path}")
        return

    console = Console()

    # Initialize widgets
    phase_plot = PhaseSpacePlot()
    regime_gauge = RegimeGauge()
    energy_spark = EnergySparkline()
    event_log = EventLog()
    budget_panel = BudgetPanel()

    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(name="top", size=12),
        Layout(name="middle", size=6),
        Layout(name="bottom", ratio=1),
    )
    layout["top"].split_row(
        Layout(name="gauge", ratio=1),
        Layout(name="phase", ratio=1),
    )
    layout["middle"].split_row(
        Layout(name="energy", ratio=2),
        Layout(name="budget", ratio=1),
    )

    # Load trace
    with open(trace_path, 'r') as f:
        lines = f.readlines()

    console.print(f"[cyan]Replaying trace: {trace_path} ({len(lines)} records)[/]")
    console.print(f"[dim]Speed: {speed}x | Press Ctrl+C to stop[/]\n")
    time.sleep(1)

    state = DashboardState()

    with Live(layout, refresh_per_second=10, screen=True, console=console) as live:
        for i, line in enumerate(lines):
            event = parse_log_line(line)
            if not event:
                continue

            try:
                event_type = event.get("event_type", "")
                fields = event.get("fields", {})

                # Update state from event
                if event_type == "proposal":
                    state.proposals += 1
                    state.lambda_rate = min(10, state.lambda_rate + 0.5)
                elif event_type == "verification":
                    if fields.get("success", True):
                        state.mu_rate = min(10, state.mu_rate + 0.5)
                    else:
                        state.rejections += 1
                elif event_type == "error":
                    state.violations += 1
                elif event_type == "llm_call":
                    state.tokens += fields.get("tokens_used", 0)
                    state.spent_usd += fields.get("cost_usd", 0.0)

                # Decay rates
                state.lambda_rate *= 0.95
                state.mu_rate *= 0.95

                # Compute stress
                if state.proposals > 0:
                    rej_rate = state.rejections / state.proposals
                else:
                    rej_rate = 0
                state.stress = min(1.0, rej_rate + state.violations * 0.05)
                state.energy = state.stress * 10 + state.violations * 0.5

                # Determine regime
                if state.stress < 0.2:
                    state.regime = "ELASTIC"
                elif state.stress < 0.4:
                    state.regime = "WARM"
                elif state.stress < 0.7:
                    state.regime = "DUCTILE"
                else:
                    state.regime = "UNSTABLE"

                # Update widgets
                phase_plot.update(state.lambda_rate + 1, state.mu_rate + 1)
                energy_spark.update(state.energy)
                budget_panel.update(state.spent_usd, state.budget_usd, state.tokens)
                event_log.add(event_type, str(fields)[:40], event.get("level", "info"))

                # Update layout
                layout["top"]["gauge"].update(
                    regime_gauge.render(
                        state.regime, state.stress,
                        state.violations, state.proposals, state.rejections
                    )
                )
                layout["top"]["phase"].update(phase_plot.render())
                layout["middle"]["energy"].update(energy_spark.render())
                layout["middle"]["budget"].update(budget_panel.render())
                layout["bottom"].update(event_log.render())

                time.sleep(0.3 / speed)

            except KeyboardInterrupt:
                break
            except Exception as e:
                event_log.add("error", str(e)[:30], "error")

    console.print("\n[cyan]Replay complete.[/]")


def generate_demo_trace(output_path: Path) -> Path:
    """Generate a demo trace for testing the dashboard."""
    records = []

    # Simulate 100 events with varying conditions
    for i in range(100):
        # Vary event types
        event_types = ["proposal", "verification", "llm_call", "claim_registered"]
        weights = [0.3, 0.3, 0.25, 0.15]

        # Introduce some errors mid-run
        if 40 <= i <= 60:
            event_types.append("error")
            weights = [0.25, 0.25, 0.2, 0.1, 0.2]

        event_type = random.choices(event_types, weights=weights)[0]

        # Build event
        event = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            "level": "error" if event_type == "error" else "info",
            "event_id": f"demo-{i:04d}",
            "fields": {},
        }

        if event_type == "proposal":
            event["fields"]["claim_count"] = random.randint(1, 5)
        elif event_type == "verification":
            event["fields"]["success"] = random.random() > (0.3 if 40 <= i <= 60 else 0.1)
        elif event_type == "llm_call":
            event["fields"]["tokens_used"] = random.randint(500, 5000)
            event["fields"]["cost_usd"] = random.uniform(0.001, 0.05)
            event["fields"]["model"] = random.choice(["claude-sonnet-4", "claude-haiku"])
        elif event_type == "error":
            event["fields"]["error"] = "Simulated error for demo"

        records.append(event)

    # Write trace
    with open(output_path, 'w') as f:
        for record in records:
            f.write(json.dumps(record) + "\n")

    print(f"Generated demo trace: {output_path} ({len(records)} records)")
    return output_path


def print_trace_stats(trace_path: Path) -> None:
    """Print statistics about a trace file."""
    if not trace_path.exists():
        print(f"Error: File not found: {trace_path}")
        return

    events = []
    with open(trace_path, 'r') as f:
        for line in f:
            event = parse_log_line(line)
            if event:
                events.append(event)

    if not events:
        print("No valid records found")
        return

    # Count event types
    event_counts: dict[str, int] = {}
    for e in events:
        et = e.get("event_type", "unknown")
        event_counts[et] = event_counts.get(et, 0) + 1

    print(f"\nTrace: {trace_path}")
    print(f"Records: {len(events)}")
    print("\nEvent distribution:")
    for event_type, count in sorted(event_counts.items(), key=lambda x: -x[1]):
        pct = count / len(events) * 100
        print(f"  {event_type}: {count} ({pct:.1f}%)")


# =============================================================================
# CLI Entry Point
# =============================================================================

def main() -> None:
    """CLI entry point for the dashboard."""
    parser = argparse.ArgumentParser(
        description="Governor Telemetry Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    # Live dashboard (reads from .governor/logs/)
    governor dashboard

    # Replay a trace file
    governor dashboard replay traces/session.jsonl

    # Replay at 2x speed
    governor dashboard replay traces/session.jsonl --speed 2.0

    # Generate and play demo trace
    governor dashboard --demo

    # Print trace statistics
    governor dashboard --stats traces/session.jsonl
        """
    )

    parser.add_argument("command", nargs="?", default="live",
                        choices=["live", "replay"],
                        help="Command: live (default) or replay")
    parser.add_argument("trace", nargs="?", help="Path to trace file (for replay)")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Playback speed multiplier (for replay)")
    parser.add_argument("--demo", action="store_true",
                        help="Generate and play demo trace")
    parser.add_argument("--stats", metavar="FILE",
                        help="Print trace statistics only")
    parser.add_argument("--log-dir", type=str, default=".governor/logs",
                        help="Log directory for live mode")
    parser.add_argument("--refresh", type=float, default=2.0,
                        help="Refresh interval in seconds (for live mode)")

    args = parser.parse_args()

    if not RICH_AVAILABLE:
        print("Error: Rich library required. Install with: pip install rich")
        return

    if args.stats:
        print_trace_stats(Path(args.stats))
    elif args.demo:
        trace_path = generate_demo_trace(Path("demo_trace.jsonl"))
        run_replay(trace_path, args.speed)
    elif args.command == "replay":
        if not args.trace:
            print("Error: Trace file required for replay command")
            parser.print_help()
            return
        run_replay(Path(args.trace), args.speed)
    else:
        # Live mode
        run_live_dashboard(Path(args.log_dir), args.refresh)


if __name__ == "__main__":
    main()
