"""
Friendly CLI layer for Agent Governor.

This provides a human-friendly interface layered by persona:
- governor (bare): Friendly status overview
- governor fiction: Writer-focused commands
- governor code: Developer-focused commands
- governor resolve: Universal violation resolution
- governor advanced: Power user commands (50+)

Design principles:
- Bare command = friend, not manual
- Her language, not yours
- Progressive disclosure
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import click

from .continuity import create_registry, ContinuityChecker, Anchor, AnchorType, Severity


# =============================================================================
# Helpers
# =============================================================================

def get_mode(gov_dir: Path) -> str:
    """Get current mode (fiction or code)."""
    config_path = gov_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return config.get("mode", "code")
    return "code"


def set_mode(gov_dir: Path, mode: str) -> None:
    """Set current mode."""
    config_path = gov_dir / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
    config["mode"] = mode
    config_path.write_text(json.dumps(config, indent=2))


def get_story_name(gov_dir: Path) -> str:
    """Get story name for fiction mode."""
    config_path = gov_dir / "config.json"
    if config_path.exists():
        config = json.loads(config_path.read_text())
        return config.get("story_name", "Untitled")
    return "Untitled"


def format_time_ago(dt: datetime) -> str:
    """Format datetime as 'X ago' string."""
    now = datetime.now()
    delta = now - dt

    if delta.days > 0:
        if delta.days == 1:
            return "yesterday"
        return f"{delta.days} days ago"

    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours} hour{'s' if hours > 1 else ''} ago"

    minutes = delta.seconds // 60
    if minutes > 0:
        return f"{minutes} minute{'s' if minutes > 1 else ''} ago"

    return "just now"


# =============================================================================
# Fiction Commands
# =============================================================================

@click.group()
@click.pass_context
def fiction(ctx: click.Context) -> None:
    """Fiction writing commands.

    Manage characters, world rules, and story constraints.
    """
    pass


@fiction.command("init")
@click.option("--name", prompt="Story name", help="Name of your story")
@click.pass_context
def fiction_init(ctx: click.Context, name: str) -> None:
    """Start a new story project."""
    from . import cli as main_cli

    gov_dir = main_cli.get_governor_dir(ctx)

    # Initialize if needed
    if not gov_dir.exists():
        ctx.invoke(main_cli.init)
        gov_dir = main_cli.get_governor_dir(ctx)

    set_mode(gov_dir, "fiction")

    # Save story name
    config_path = gov_dir / "config.json"
    config = {}
    if config_path.exists():
        config = json.loads(config_path.read_text())
    config["story_name"] = name
    config["mode"] = "fiction"
    config_path.write_text(json.dumps(config, indent=2))

    click.echo()
    click.echo(f"  Started story: {name}")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    governor fiction character add <name>   Add a character")
    click.echo("    governor fiction world add \"<rule>\"     Add a world rule")
    click.echo("    governor fiction forbid \"<pattern>\"     Add something that shouldn't happen")
    click.echo()


@fiction.command("status")
@click.pass_context
def fiction_status(ctx: click.Context) -> None:
    """Show current story state."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)

    story_name = get_story_name(gov_dir)

    # Load anchors
    registry = create_registry(gov_dir)
    anchors = registry.all()

    # Categorize anchors
    characters = [a for a in anchors if a.anchor_type == AnchorType.CANON and "char-" in a.id.lower()]
    world_rules = [a for a in anchors if a.anchor_type == AnchorType.DEFINITION]
    prohibitions = [a for a in anchors if a.anchor_type == AnchorType.PROHIBITION]

    click.echo()
    click.echo(f"  Story: \"{story_name}\"")
    click.echo()

    # Characters
    click.echo(f"  Characters ({len(characters)})")
    if characters:
        for char in characters[:5]:
            name = char.id.replace("char-", "").replace("-", " ").title()
            desc = char.description[:50] + "..." if len(char.description) > 50 else char.description
            click.echo(f"     {name} - {desc}")
        if len(characters) > 5:
            click.echo(f"     ... and {len(characters) - 5} more")
    else:
        click.echo("     No characters yet. Run 'governor fiction character add <name>'")
    click.echo()

    # World Rules
    click.echo(f"  World Rules ({len(world_rules)})")
    if world_rules:
        for rule in world_rules[:3]:
            desc = rule.description[:60] + "..." if len(rule.description) > 60 else rule.description
            click.echo(f"     * {desc}")
        if len(world_rules) > 3:
            click.echo(f"     ... and {len(world_rules) - 3} more")
    else:
        click.echo("     No world rules yet. Run 'governor fiction world add \"<rule>\"'")
    click.echo()

    # Prohibitions
    click.echo(f"  Things That Shouldn't Happen ({len(prohibitions)})")
    if prohibitions:
        for prob in prohibitions[:3]:
            desc = prob.description[:60] + "..." if len(prob.description) > 60 else prob.description
            click.echo(f"     * {desc}")
        if len(prohibitions) > 3:
            click.echo(f"     ... and {len(prohibitions) - 3} more")
    else:
        click.echo("     None yet. Run 'governor fiction forbid \"<pattern>\"'")
    click.echo()


# Character subgroup
@fiction.group("character")
def fiction_character() -> None:
    """Manage characters in your story."""
    pass


@fiction_character.command("add")
@click.argument("name")
@click.option("--looks", help="Physical description")
@click.option("--voice", help="How they talk and act")
@click.option("--wont", help="Things they wouldn't do")
@click.pass_context
def fiction_character_add(ctx: click.Context, name: str, looks: str | None, voice: str | None, wont: str | None) -> None:
    """Add a character to your story."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)

    # Interactive prompts if not provided
    if not looks and not voice and not wont:
        click.echo()
        click.echo(f"  Adding character: {name}")
        click.echo()
        looks = click.prompt("  What's true about them? (appearance, background - or skip)", default="", show_default=False)
        voice = click.prompt("  How do they talk and act? (or skip)", default="", show_default=False)
        wont = click.prompt("  Things they wouldn't do? (or skip)", default="", show_default=False)

    # Build description
    desc_parts = []
    if looks:
        desc_parts.append(f"Appearance: {looks}")
    if voice:
        desc_parts.append(f"Voice: {voice}")
    description = "; ".join(desc_parts) if desc_parts else f"Character: {name}"

    # Create anchor(s)
    registry = create_registry(gov_dir)
    char_id = f"char-{name.lower().replace(' ', '-')}"

    # Main character anchor
    anchor = Anchor(
        id=char_id,
        anchor_type=AnchorType.CANON,
        description=description,
        severity=Severity.REJECT,
    )
    registry.register(anchor)

    # Prohibition anchor if wont provided
    if wont:
        patterns = [p.strip() for p in wont.split(",")]
        prob_anchor = Anchor(
            id=f"{char_id}-wont",
            anchor_type=AnchorType.PROHIBITION,
            description=f"{name} wouldn't: {wont}",
            forbidden_patterns=patterns,
            severity=Severity.REJECT,
        )
        registry.register(prob_anchor)

    # Save
    registry.save(gov_dir / "continuity" / "anchors.json")

    click.echo()
    click.echo(f"  {name} added")
    click.echo()
    click.echo("  I'll catch anything that contradicts this.")
    click.echo()


@fiction_character.command("list")
@click.pass_context
def fiction_character_list(ctx: click.Context) -> None:
    """List all characters."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    characters = [a for a in registry.all() if a.anchor_type == AnchorType.CANON and "char-" in a.id]

    click.echo()
    if not characters:
        click.echo("  No characters yet.")
        click.echo("  Run 'governor fiction character add <name>' to add one.")
    else:
        click.echo(f"  Characters ({len(characters)})")
        click.echo()
        for char in characters:
            name = char.id.replace("char-", "").replace("-", " ").title()
            click.echo(f"  {name}")
            click.echo(f"     {char.description}")
            click.echo()


@fiction_character.command("show")
@click.argument("name")
@click.pass_context
def fiction_character_show(ctx: click.Context, name: str) -> None:
    """Show character details."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    char_id = f"char-{name.lower().replace(' ', '-')}"
    anchor = registry.get(char_id)

    if not anchor:
        # Try partial match
        for a in registry.all():
            if name.lower() in a.id.lower() and "char-" in a.id:
                anchor = a
                break

    if not anchor:
        click.echo(f"  Couldn't find character: {name}")
        click.echo()
        click.echo("  Did you mean one of these?")
        for a in registry.all():
            if "char-" in a.id:
                n = a.id.replace("char-", "").replace("-", " ").title()
                click.echo(f"    * {n}")
        return

    char_name = anchor.id.replace("char-", "").replace("-", " ").title()
    click.echo()
    click.echo(f"  {char_name}")
    click.echo(f"  {'=' * len(char_name)}")
    click.echo()
    click.echo(f"  {anchor.description}")
    click.echo()

    # Check for related prohibitions
    wont_anchor = registry.get(f"{anchor.id}-wont")
    if wont_anchor:
        click.echo("  Things they won't do:")
        for pattern in wont_anchor.forbidden_patterns:
            click.echo(f"    * {pattern}")
        click.echo()


@fiction_character.command("remove")
@click.argument("name")
@click.pass_context
def fiction_character_remove(ctx: click.Context, name: str) -> None:
    """Remove a character."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    char_id = f"char-{name.lower().replace(' ', '-')}"

    anchor = registry.unregister(char_id)
    wont_anchor = registry.unregister(f"{char_id}-wont")

    if anchor:
        registry.save(gov_dir / "continuity" / "anchors.json")
        click.echo(f"  Removed: {name}")
    else:
        click.echo(f"  Couldn't find character: {name}")


# World subgroup
@fiction.group("world")
def fiction_world() -> None:
    """Manage world rules."""
    pass


@fiction_world.command("add")
@click.argument("rule")
@click.pass_context
def fiction_world_add(ctx: click.Context, rule: str) -> None:
    """Add a world rule."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    # Generate ID
    rule_id = f"world-{len([a for a in registry.all() if 'world-' in a.id]) + 1}"

    anchor = Anchor(
        id=rule_id,
        anchor_type=AnchorType.DEFINITION,
        description=rule,
        severity=Severity.REJECT,
    )
    registry.register(anchor)
    registry.save(gov_dir / "continuity" / "anchors.json")

    click.echo()
    click.echo("  World rule added")
    click.echo()
    click.echo("  I'll catch anything that contradicts this.")
    click.echo()


@fiction_world.command("list")
@click.pass_context
def fiction_world_list(ctx: click.Context) -> None:
    """List all world rules."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    rules = [a for a in registry.all() if a.anchor_type == AnchorType.DEFINITION]

    click.echo()
    if not rules:
        click.echo("  No world rules yet.")
        click.echo("  Run 'governor fiction world add \"<rule>\"' to add one.")
    else:
        click.echo(f"  World Rules ({len(rules)})")
        click.echo()
        for rule in rules:
            click.echo(f"  * {rule.description}")
    click.echo()


@fiction.command("forbid")
@click.argument("description")
@click.option("--patterns", "-p", multiple=True, help="Specific patterns to match")
@click.pass_context
def fiction_forbid(ctx: click.Context, description: str, patterns: tuple[str, ...]) -> None:
    """Add something that shouldn't happen in your story."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    # Generate ID
    forbid_id = f"forbid-{len([a for a in registry.all() if 'forbid-' in a.id]) + 1}"

    forbidden_patterns = list(patterns) if patterns else [description]

    anchor = Anchor(
        id=forbid_id,
        anchor_type=AnchorType.PROHIBITION,
        description=description,
        forbidden_patterns=forbidden_patterns,
        severity=Severity.REJECT,
    )
    registry.register(anchor)
    registry.save(gov_dir / "continuity" / "anchors.json")

    click.echo()
    click.echo("  Added to things that shouldn't happen")
    click.echo()
    if patterns:
        click.echo("  I'll flag these specific phrases.")
    else:
        click.echo(f"  I'll flag anything that looks like: {description}")
    click.echo()


@fiction.command("corrections")
@click.option("--all", "show_all", is_flag=True, help="Show all corrections")
@click.pass_context
def fiction_corrections(ctx: click.Context, show_all: bool) -> None:
    """View correction history."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)

    # Load exceptions (precedents)
    exceptions_dir = gov_dir / "exceptions"
    if not exceptions_dir.exists():
        click.echo()
        click.echo("  Nothing yet.")
        click.echo()
        click.echo("  When I catch something that contradicts your")
        click.echo("  story, it'll show up here.")
        click.echo()
        return

    exceptions = []
    for f in exceptions_dir.glob("*.json"):
        try:
            exc = json.loads(f.read_text())
            exceptions.append(exc)
        except:
            pass

    if not exceptions:
        click.echo()
        click.echo("  Nothing yet.")
        click.echo()
        return

    # Sort by date
    exceptions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    click.echo()
    click.echo("  Corrections")
    click.echo()

    for exc in exceptions[:10 if not show_all else None]:
        action = exc.get("action", "unknown")
        icon = {"fix": "Fixed", "revise": "Changed", "proceed": "Allowed"}.get(action, action)
        anchor = exc.get("anchor_id", "unknown")
        reason = exc.get("rationale", "")

        click.echo(f"  {icon}")
        click.echo(f"     {anchor}")
        if reason:
            click.echo(f"     Reason: {reason}")
        click.echo()

    if len(exceptions) > 10 and not show_all:
        click.echo(f"  (Showing 10 of {len(exceptions)}. Use --all for everything.)")
        click.echo()


# =============================================================================
# Code Commands
# =============================================================================

@click.group(invoke_without_command=True)
@click.option("--profile", "-p", help="Set autopilot profile (greenfield/established/production/hotfix/refactor)")
@click.option("--scope", "-s", multiple=True, help="Set allowed path patterns")
@click.option("--timebox", "-t", type=int, help="Set timebox in minutes")
@click.option("--because", "reason", help="Reason for this intent")
@click.option("--status", "show_status", is_flag=True, help="Show autopilot status")
@click.pass_context
def code(
    ctx: click.Context,
    profile: str | None,
    scope: tuple[str, ...],
    timebox: int | None,
    reason: str | None,
    show_status: bool,
) -> None:
    """Code development commands (with Autopilot support).

    Manage decisions, constraints, and verification.

    \b
    Autopilot shortcuts:
      governor code --profile hotfix --scope "src/**" --timebox 90
      governor code --status
    """
    from . import cli as main_cli

    # If profile specified, set intent and apply autopilot settings
    if profile:
        from .intent import Intent, set_intent
        from .autopilot import get_autopilot_profile, apply_autopilot_profile

        gov_dir = main_cli.ensure_initialized(ctx)

        profile_config = get_autopilot_profile(profile)
        if not profile_config:
            valid_profiles = ["greenfield", "established", "production", "hotfix", "refactor"]
            click.echo(f"Unknown profile: {profile}", err=True)
            click.echo(f"Valid profiles: {', '.join(valid_profiles)}", err=True)
            ctx.exit(1)
            return

        intent = Intent(
            profile=profile,
            scope=list(scope) if scope else None,
            timebox_minutes=timebox,
            reason=reason,
            source="cli",
        )

        set_intent(gov_dir, intent)
        applied = apply_autopilot_profile(gov_dir, profile_config)

        click.echo()
        click.echo(f"  Autopilot: {intent.to_status_string()}")
        if reason:
            click.echo(f"  Reason: {reason}")
        click.echo()
        return

    # If --status flag, show autopilot status
    if show_status:
        from .intent import resolve_intent

        gov_dir = main_cli.get_governor_dir(ctx)
        if not gov_dir.exists():
            click.echo("Governor not initialized. Run 'governor init' first.")
            return

        intent, provenance = resolve_intent(gov_dir)
        click.echo()
        click.echo(f"  Autopilot: {intent.to_status_string()}")
        click.echo(f"  Source: {intent.source}")
        if intent.reason:
            click.echo(f"  Reason: {intent.reason}")
        if intent.scope:
            click.echo(f"  Scope: {', '.join(intent.scope)}")
        if intent.deny:
            click.echo(f"  Deny: {', '.join(intent.deny)}")
        click.echo()
        return

    # If no subcommand and no options, show help
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@code.command("init")
@click.pass_context
def code_init(ctx: click.Context) -> None:
    """Start a new code project."""
    from . import cli as main_cli

    gov_dir = main_cli.get_governor_dir(ctx)

    # Initialize if needed
    if not gov_dir.exists():
        ctx.invoke(main_cli.init)
        gov_dir = main_cli.get_governor_dir(ctx)

    set_mode(gov_dir, "code")

    click.echo()
    click.echo("  Code project initialized")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    governor code decision add \"<decision>\"    Record a decision")
    click.echo("    governor code constraint add \"<constraint>\" Add a constraint")
    click.echo("    governor code verify                        Run verification")
    click.echo()


@code.command("status")
@click.pass_context
def code_status(ctx: click.Context) -> None:
    """Show current project state (including Autopilot)."""
    from . import cli as main_cli
    from .ledgers import DecisionLedger
    from .intent import resolve_intent
    from .overrides import OverrideManager

    gov_dir = main_cli.ensure_initialized(ctx)

    # Load intent
    intent, _ = resolve_intent(gov_dir)

    # Load decisions
    decision_ledger = DecisionLedger(gov_dir)
    decisions = list(decision_ledger.all())

    # Load constraints
    registry = create_registry(gov_dir)
    constraints = [a for a in registry.all() if a.anchor_type == AnchorType.PROHIBITION]
    invariants = [a for a in registry.all() if a.constraint_class.value == "invariant"]

    # Load overrides
    override_manager = OverrideManager(gov_dir=gov_dir)
    active_overrides = override_manager.list_active()

    click.echo()
    click.echo("  Project Status")
    click.echo()

    # Autopilot
    click.echo(f"  Autopilot: {intent.to_status_string()}")
    if intent.reason:
        click.echo(f"     Reason: {intent.reason}")
    click.echo()

    # Decisions
    click.echo(f"  Decisions ({len(decisions)})")
    if decisions:
        for dec in decisions[:5]:
            click.echo(f"     * {dec.topic}: {dec.choice}")
        if len(decisions) > 5:
            click.echo(f"     ... and {len(decisions) - 5} more")
    else:
        click.echo("     No decisions yet. Run 'governor code decision add \"<decision>\"'")
    click.echo()

    # Constraints with invariant count
    click.echo(f"  Constraints ({len(constraints)}, {len(invariants)} invariants)")
    if constraints:
        for con in constraints[:5]:
            class_marker = "[I]" if con.constraint_class.value == "invariant" else "[P]"
            click.echo(f"     {class_marker} {con.description}")
        if len(constraints) > 5:
            click.echo(f"     ... and {len(constraints) - 5} more")
    else:
        click.echo("     No constraints yet. Run 'governor code constraint add \"<constraint>\"'")
    click.echo()

    # Active overrides
    if active_overrides:
        click.echo(f"  Active Overrides ({len(active_overrides)})")
        for override in active_overrides[:3]:
            click.echo(f"     * {override.to_status_string()}")
        if len(active_overrides) > 3:
            click.echo(f"     ... and {len(active_overrides) - 3} more")
        click.echo()


# Decision subgroup
@code.group("decision")
def code_decision() -> None:
    """Manage architectural decisions."""
    pass


@code_decision.command("add")
@click.argument("decision")
@click.option("--rationale", "-r", help="Why this decision was made")
@click.pass_context
def code_decision_add(ctx: click.Context, decision: str, rationale: str | None) -> None:
    """Record an architectural decision."""
    from . import cli as main_cli
    from .ledgers import DecisionLedger
    from .claims import decision as make_decision

    gov_dir = main_cli.ensure_initialized(ctx)

    # Interactive prompt for rationale if not provided
    if not rationale:
        rationale = click.prompt("  Why this decision? (helps future-you remember - or skip)", default="", show_default=False)

    # Parse decision into topic/choice
    if ":" in decision:
        topic, choice = decision.split(":", 1)
    elif "," in decision:
        parts = decision.split(",", 1)
        topic = parts[0].strip()
        choice = parts[1].strip() if len(parts) > 1 else topic
    else:
        topic = "architecture"
        choice = decision

    topic = topic.strip()
    choice = choice.strip()

    # Add to ledger
    decision_ledger = DecisionLedger(gov_dir)
    claim = make_decision(topic, choice)
    decision_ledger.add(claim, rationale=rationale)

    click.echo()
    click.echo("  Decision recorded")
    click.echo()
    click.echo("  I'll catch anything that contradicts this.")
    click.echo()


@code_decision.command("list")
@click.pass_context
def code_decision_list(ctx: click.Context) -> None:
    """List all decisions."""
    from . import cli as main_cli
    from .ledgers import DecisionLedger

    gov_dir = main_cli.ensure_initialized(ctx)
    decision_ledger = DecisionLedger(gov_dir)

    decisions = list(decision_ledger.all())

    click.echo()
    if not decisions:
        click.echo("  No decisions yet.")
        click.echo("  Run 'governor code decision add \"<decision>\"' to add one.")
    else:
        click.echo(f"  Decisions ({len(decisions)})")
        click.echo()
        for dec in decisions:
            click.echo(f"  {dec.topic}: {dec.choice}")
            if dec.rationale:
                click.echo(f"     \"{dec.rationale}\"")
            click.echo()


# Constraint subgroup
@code.group("constraint")
def code_constraint() -> None:
    """Manage code constraints."""
    pass


@code_constraint.command("add")
@click.argument("constraint")
@click.option("--patterns", "-p", multiple=True, help="Patterns to match")
@click.pass_context
def code_constraint_add(ctx: click.Context, constraint: str, patterns: tuple[str, ...]) -> None:
    """Add a code constraint."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    # Generate ID
    con_id = f"constraint-{len([a for a in registry.all() if 'constraint-' in a.id]) + 1}"

    forbidden_patterns = list(patterns) if patterns else []

    anchor = Anchor(
        id=con_id,
        anchor_type=AnchorType.PROHIBITION,
        description=constraint,
        forbidden_patterns=forbidden_patterns,
        severity=Severity.REJECT,
    )
    registry.register(anchor)
    registry.save(gov_dir / "continuity" / "anchors.json")

    click.echo()
    click.echo("  Constraint added")
    click.echo()


@code_constraint.command("list")
@click.pass_context
def code_constraint_list(ctx: click.Context) -> None:
    """List all constraints."""
    from . import cli as main_cli

    gov_dir = main_cli.ensure_initialized(ctx)
    registry = create_registry(gov_dir)

    constraints = [a for a in registry.all() if a.anchor_type == AnchorType.PROHIBITION]

    click.echo()
    if not constraints:
        click.echo("  No constraints yet.")
        click.echo("  Run 'governor code constraint add \"<constraint>\"' to add one.")
    else:
        click.echo(f"  Constraints ({len(constraints)})")
        click.echo()
        for con in constraints:
            click.echo(f"  * {con.description}")
    click.echo()


@code.group("verify")
def code_verify_group() -> None:
    """Run verification checks."""
    pass


@code_verify_group.command("all")
@click.pass_context
def code_verify_all(ctx: click.Context) -> None:
    """Run all verification checks."""
    click.echo()
    click.echo("  Running checks...")
    click.echo()

    # TODO: Actually run configured verification commands
    click.echo("  Tests: (not configured)")
    click.echo("  Types: (not configured)")
    click.echo("  Lint: (not configured)")
    click.echo()
    click.echo("  Configure with 'governor advanced hook install'")
    click.echo()


@code.command("ledger")
@click.option("--recent", is_flag=True, help="Show recent entries")
@click.option("--decisions", "show_decisions", is_flag=True, help="Show only decisions")
@click.option("--facts", "show_facts", is_flag=True, help="Show only facts")
@click.pass_context
def code_ledger(ctx: click.Context, recent: bool, show_decisions: bool, show_facts: bool) -> None:
    """View decision/fact history."""
    from . import cli as main_cli
    from .ledgers import DecisionLedger, FactLedger

    gov_dir = main_cli.ensure_initialized(ctx)

    click.echo()
    click.echo("  Ledger")
    click.echo()

    if show_decisions or not show_facts:
        decision_ledger = DecisionLedger(gov_dir)
        decisions = list(decision_ledger.all())

        click.echo("  Decisions")
        click.echo("  " + "-" * 50)
        if decisions:
            for dec in decisions[:10 if recent else None]:
                click.echo(f"  {dec.topic}: {dec.choice}")
                if dec.rationale:
                    click.echo(f"     \"{dec.rationale}\"")
        else:
            click.echo("  No decisions recorded.")
        click.echo()

    if show_facts or not show_decisions:
        fact_ledger = FactLedger(gov_dir)
        facts = list(fact_ledger.all())

        click.echo("  Facts")
        click.echo("  " + "-" * 50)
        if facts:
            for fact in facts[:10 if recent else None]:
                click.echo(f"  {fact.claim.describe()}")
        else:
            click.echo("  No facts recorded.")
        click.echo()


# Code Compare (convenience alias for governor interferometry compare)
@code.command("compare")
@click.argument("prompt", required=False)
@click.option("--backends", "-b", default=None, help="backend:model pairs")
@click.option("--last", "show_last", is_flag=True, help="Analyze most recent run.")
@click.option("--id", "run_id", default=None, help="Analyze specific run.")
@click.option("--markers", "show_markers", is_flag=True, help="Show markers only.")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
@click.pass_context
def code_compare(ctx: click.Context, prompt: str | None, backends: str | None,
                 show_last: bool, run_id: str | None, show_markers: bool,
                 as_json: bool) -> None:
    """Compare code across models — risk markers + anchor conflicts.

    Alias for: governor interferometry compare
    """
    from . import cli as main_cli
    # Delegate to the interferometry compare command
    ctx.invoke(
        main_cli.interferometry_compare,
        prompt=prompt,
        backends=backends,
        show_last=show_last,
        run_id=run_id,
        show_markers=show_markers,
        as_json=as_json,
    )


# =============================================================================
# Resolve Commands
# =============================================================================

@click.group(invoke_without_command=True)
@click.pass_context
def resolve(ctx: click.Context) -> None:
    """Resolve pending violations.

    When something contradicts your canon/decisions, use these
    commands to decide what to do.
    """
    if ctx.invoked_subcommand is None:
        # Show pending violation interactively
        from . import cli as main_cli
        from .violation_resolver import ViolationResolver

        gov_dir = main_cli.ensure_initialized(ctx)
        resolver = ViolationResolver(gov_dir)

        pending = resolver.get_pending()
        if not pending:
            click.echo()
            click.echo("  No unresolved issues")
            click.echo()
            return

        # Show the violation
        click.echo()
        click.echo("  This contradicts your canon")
        click.echo()
        click.echo("  What was written:")
        click.echo(f"    \"{pending.blocked_content[:100]}...\"" if len(pending.blocked_content) > 100 else f"    \"{pending.blocked_content}\"")
        click.echo()
        click.echo("  What you established:")
        click.echo(f"    {pending.anchor_description}")
        click.echo(f"    (anchor: {pending.anchor_id})")
        click.echo()
        click.echo("  What do you want to do?")
        click.echo()
        click.echo("    [1] Rewrite - fix to match your canon")
        click.echo("    [2] Change canon - update what you established")
        click.echo("    [3] Allow once - let it go this time")
        click.echo()

        choice = click.prompt("  Choice", type=click.Choice(["1", "2", "3"]))

        if choice == "1":
            ctx.invoke(resolve_fix)
        elif choice == "2":
            ctx.invoke(resolve_change)
        else:
            ctx.invoke(resolve_allow)


@resolve.command("fix")
@click.pass_context
def resolve_fix(ctx: click.Context) -> None:
    """Rewrite to match your canon/decisions."""
    from . import cli as main_cli
    from .violation_resolver import ViolationResolver, ResolutionAction

    gov_dir = main_cli.ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)

    result = resolver.resolve(ResolutionAction.FIX)

    if result.success:
        click.echo()
        click.echo("  Marked for rewrite. The next generation will match your canon.")
        click.echo()
    else:
        click.echo()
        click.echo(f"  {result.message}")
        click.echo()


@resolve.command("change")
@click.pass_context
def resolve_change(ctx: click.Context) -> None:
    """Update your canon/decisions to match what was written."""
    from . import cli as main_cli
    from .violation_resolver import ViolationResolver, ResolutionAction

    gov_dir = main_cli.ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)

    result = resolver.resolve(ResolutionAction.REVISE)

    if result.success:
        click.echo()
        click.echo("  Canon updated.")
        click.echo()
    else:
        click.echo()
        click.echo(f"  {result.message}")
        click.echo()


@resolve.command("allow")
@click.option("--reason", "-r", help="Why you're allowing this")
@click.pass_context
def resolve_allow(ctx: click.Context, reason: str | None) -> None:
    """Allow this once (log as exception)."""
    from . import cli as main_cli
    from .violation_resolver import ViolationResolver, ResolutionAction

    gov_dir = main_cli.ensure_initialized(ctx)
    resolver = ViolationResolver(gov_dir)

    if not reason:
        reason = click.prompt("  Why allow? (optional, helps you remember)", default="", show_default=False)

    result = resolver.resolve(ResolutionAction.PROCEED, rationale=reason or None)

    if result.success:
        click.echo()
        click.echo("  Allowed this time. Logged as exception.")
        click.echo()
    else:
        click.echo()
        click.echo(f"  {result.message}")
        click.echo()


# =============================================================================
# Friendly Bare Command
# =============================================================================

def show_friendly_status(ctx: click.Context) -> None:
    """Show friendly status when governor is run with no arguments."""
    from . import cli as main_cli
    from .violation_resolver import ViolationResolver

    root = Path(ctx.obj.get("root", "."))
    gov_dir = root / ".governor"

    # Get version
    version = "0.9.0"  # TODO: Get from package

    click.echo()
    click.echo(f"  Agent Governor v{version}")
    click.echo()

    # Not initialized
    if not gov_dir.exists():
        click.echo("  Welcome! Looks like this is a new project.")
        click.echo()
        click.echo("  What are you working on?")
        click.echo()
        click.echo("    governor fiction init        Start a story")
        click.echo("    governor code init           Start a code project")
        click.echo()
        click.echo("  Or run 'governor help' to explore.")
        click.echo()
        return

    mode = get_mode(gov_dir)

    # Check for pending violation
    resolver = ViolationResolver(gov_dir)
    pending = resolver.get_pending()

    if pending:
        click.echo("  There's an unresolved issue")
        click.echo()
        click.echo(f"  This contradicts your {'canon' if mode == 'fiction' else 'decisions'}:")
        click.echo(f"    {pending.anchor_description}")
        click.echo()
        click.echo("  Run 'governor resolve' to handle it.")
        click.echo()
        click.echo("  Or choose now:")
        click.echo("    governor resolve fix         Rewrite to comply")
        click.echo("    governor resolve change      Update your canon")
        click.echo("    governor resolve allow       Allow it this time")
        click.echo()
        return

    # Fiction mode status
    if mode == "fiction":
        story_name = get_story_name(gov_dir)
        registry = create_registry(gov_dir)
        anchors = registry.all()

        characters = len([a for a in anchors if "char-" in a.id])
        rules = len([a for a in anchors if a.anchor_type == AnchorType.DEFINITION])
        prohibitions = len([a for a in anchors if a.anchor_type == AnchorType.PROHIBITION and "char-" not in a.id])

        click.echo("  Mode: Fiction")
        click.echo(f"  Story: \"{story_name}\"")
        click.echo(f"     {characters} characters * {rules} world rules * {prohibitions} boundaries")
        click.echo()
        click.echo("  No unresolved issues")
        click.echo()
        click.echo("  Quick start:")
        click.echo("    governor fiction status      Full story overview")
        click.echo("    governor fiction character   Manage characters")
        click.echo("    governor check <file>        Check a file")
        click.echo()

    # Code mode status
    else:
        from .ledgers import DecisionLedger

        decision_ledger = DecisionLedger(gov_dir)
        decisions = len(list(decision_ledger.all()))

        registry = create_registry(gov_dir)
        constraints = len([a for a in registry.all() if a.anchor_type == AnchorType.PROHIBITION])

        click.echo("  Mode: Code")
        click.echo(f"     {decisions} decisions * {constraints} constraints")
        click.echo()
        click.echo("  No unresolved issues")
        click.echo()
        click.echo("  Quick start:")
        click.echo("    governor code status         Full project overview")
        click.echo("    governor code decision       Manage decisions")
        click.echo("    governor check <file>        Check a file")
        click.echo()

    click.echo("  Run 'governor help' for all commands.")
    click.echo()
