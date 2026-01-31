"""
CLI for Fiction Governor.

fiction-gov: Keep characters in-character, stories consistent, and tropes at bay.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from .bible import Bible, COMMON_TROPES
from .canon import Canon
from .state import CharacterState
from .types import FictionClaim, FictionClaimType, MotivationType, ThreadType, ThreadStatus
from .verifiers import FictionVerifier, NarrativeVerifier, VerificationResult


def get_project_dir() -> Path:
    """Find project directory by looking for .fiction-gov folder."""
    cwd = Path.cwd()

    # Check current directory
    if (cwd / ".fiction-gov").exists():
        return cwd

    # Check parent directories
    for parent in cwd.parents:
        if (parent / ".fiction-gov").exists():
            return parent

    return cwd


def cmd_init(args: argparse.Namespace) -> int:
    """Initialize a fiction project."""
    project_dir = Path(args.path or ".").resolve()
    fiction_dir = project_dir / ".fiction-gov"

    if fiction_dir.exists() and not args.force:
        print(f"Project already initialized at {project_dir}")
        print("Use --force to reinitialize")
        return 1

    # Create directory structure
    fiction_dir.mkdir(parents=True, exist_ok=True)
    (fiction_dir / "bible").mkdir(exist_ok=True)
    (fiction_dir / "canon").mkdir(exist_ok=True)

    # Create metadata
    meta = {
        "project_name": args.name or project_dir.name,
        "version": "1.0",
    }
    (fiction_dir / "meta.json").write_text(json.dumps(meta, indent=2))

    # Initialize bible and canon (creates empty files)
    Bible(project_dir)
    Canon(project_dir)

    print(f"Initialized fiction project: {meta['project_name']}")
    print(f"  Directory: {project_dir}")
    print("\nNext steps:")
    print("  fiction-gov bible character add <name> - Add a character")
    print("  fiction-gov bible trope ban <name> - Ban a trope")
    print("  fiction-gov bible tone set - Set tone/style")

    return 0


# Bible commands

def cmd_bible_character_add(args: argparse.Namespace) -> int:
    """Add a character to the bible."""
    bible = Bible(get_project_dir())

    char = bible.add_character(args.name, role=args.role)

    # Add traits if provided
    if args.trait:
        for trait in args.trait:
            # Parse "trait:nuance" format
            if ":" in trait:
                t, nuance = trait.split(":", 1)
                char.add_trait(t.strip(), nuance.strip())
            else:
                char.add_trait(trait.strip())
        bible.update_character(char)

    print(f"Added character: {char.name}")
    if char.role:
        print(f"  Role: {char.role}")
    if char.traits:
        print(f"  Traits: {', '.join(str(t) for t in char.traits)}")

    return 0


def cmd_bible_character_trait(args: argparse.Namespace) -> int:
    """Add a trait to a character."""
    bible = Bible(get_project_dir())

    char = bible.add_character_trait(args.name, args.trait, nuance=args.nuance, note=args.note)
    if not char:
        print(f"Character not found: {args.name}")
        return 1

    print(f"Added trait to {char.name}: {args.trait}")
    if args.nuance:
        print(f"  Nuance: {args.nuance}")

    return 0


def cmd_bible_character_anti(args: argparse.Namespace) -> int:
    """Add an anti-pattern to a character (something they would NEVER do)."""
    bible = Bible(get_project_dir())

    char = bible.add_character_anti_pattern(args.name, args.pattern)
    if not char:
        print(f"Character not found: {args.name}")
        return 1

    print(f"Added anti-pattern to {char.name}: {args.pattern}")

    return 0


def cmd_bible_character_voice(args: argparse.Namespace) -> int:
    """Set a character's voice."""
    bible = Bible(get_project_dir())

    avoid = args.avoid.split(",") if args.avoid else None
    char = bible.set_character_voice(
        args.name,
        internal_monologue=args.internal,
        dialogue=args.dialogue,
        avoid=avoid,
    )
    if not char:
        print(f"Character not found: {args.name}")
        return 1

    print(f"Set voice for {char.name}")

    return 0


def cmd_bible_character_show(args: argparse.Namespace) -> int:
    """Show a character's bible entry."""
    bible = Bible(get_project_dir())

    if args.name:
        char = bible.get_character(args.name)
        if not char:
            print(f"Character not found: {args.name}")
            return 1
        print(char.format_for_prompt())
    else:
        chars = bible.all_characters()
        if not chars:
            print("No characters defined.")
            return 0
        for char in chars:
            print(char.format_for_prompt())
            print()

    return 0


def cmd_bible_trope_ban(args: argparse.Namespace) -> int:
    """Ban a trope."""
    bible = Bible(get_project_dir())

    # Check if it's a common trope
    if args.name.lower() in COMMON_TROPES:
        trope = bible.ban_common_trope(args.name, reason=args.reason)
        print(f"Banned common trope: {trope.name}")
        print(f"  Reason: {trope.reason}")
        print(f"  Patterns: {len(trope.patterns)} detection patterns")
    else:
        patterns = args.pattern or []
        trope = bible.ban_trope(
            args.name,
            reason=args.reason or "No reason specified",
            patterns=patterns,
            severity=args.severity,
        )
        print(f"Banned trope: {trope.name}")
        print(f"  Reason: {trope.reason}")
        if patterns:
            print(f"  Patterns: {len(patterns)}")

    return 0


def cmd_bible_trope_list(args: argparse.Namespace) -> int:
    """List banned tropes."""
    bible = Bible(get_project_dir())

    banned = bible.all_banned_tropes()
    if not banned:
        print("No tropes banned.")
        print("\nCommon tropes available to ban:")
        for name, trope in COMMON_TROPES.items():
            print(f"  {name}: {trope.reason}")
        return 0

    print("Banned tropes:\n")
    for trope in banned:
        severity_mark = "❌" if trope.severity == "error" else "⚠️"
        print(f"{severity_mark} {trope.name}")
        print(f"   Reason: {trope.reason}")
        if trope.patterns:
            print(f"   Patterns: {len(trope.patterns)}")

    return 0


def cmd_bible_trope_unban(args: argparse.Namespace) -> int:
    """Unban a trope."""
    bible = Bible(get_project_dir())

    if bible.unban_trope(args.name):
        print(f"Unbanned trope: {args.name}")
        return 0
    else:
        print(f"Trope not found: {args.name}")
        return 1


def cmd_bible_rule_add(args: argparse.Namespace) -> int:
    """Add a world rule."""
    bible = Bible(get_project_dir())

    implications = args.implies.split(",") if args.implies else None
    rule = bible.add_world_rule(
        args.name,
        args.rule,
        category=args.category,
        implications=implications,
    )

    print(f"Added world rule: {rule.name}")
    print(f"  Rule: {rule.rule}")
    if rule.category:
        print(f"  Category: {rule.category}")

    return 0


def cmd_bible_rule_list(args: argparse.Namespace) -> int:
    """List world rules."""
    bible = Bible(get_project_dir())

    if args.category:
        rules = bible.world_rules_by_category(args.category)
    else:
        rules = bible.all_world_rules()

    if not rules:
        print("No world rules defined.")
        return 0

    print("World Rules:\n")
    for rule in rules:
        cat = f" [{rule.category}]" if rule.category else ""
        print(f"### {rule.name}{cat}")
        print(f"  {rule.rule}")
        if rule.implications:
            print("  Implies:")
            for imp in rule.implications:
                print(f"    - {imp}")
        print()

    return 0


def cmd_bible_tone_set(args: argparse.Namespace) -> int:
    """Set tone settings."""
    bible = Bible(get_project_dir())

    not_genres = args.not_genre.split(",") if args.not_genre else None
    avoid = args.avoid.split(",") if args.avoid else None

    tone = bible.set_tone(
        genre=args.genre,
        not_genres=not_genres,
        prose_style=args.prose,
        pacing=args.pacing,
        avoid=avoid,
    )

    print("Set tone settings:")
    print(tone.format_for_prompt())

    return 0


def cmd_bible_tone_show(args: argparse.Namespace) -> int:
    """Show tone settings."""
    bible = Bible(get_project_dir())

    tone = bible.get_tone()
    if not tone:
        print("No tone settings defined.")
        return 0

    print(tone.format_for_prompt())
    return 0


def cmd_bible_show(args: argparse.Namespace) -> int:
    """Show entire bible."""
    bible = Bible(get_project_dir())
    print(bible.format_for_prompt())
    return 0


# Canon commands

def cmd_canon_event_add(args: argparse.Namespace) -> int:
    """Add a canon event."""
    canon = Canon(get_project_dir())

    characters = args.characters.split(",") if args.characters else None
    establishes = args.establishes.split(",") if args.establishes else None

    event = canon.add_event(
        chapter=args.chapter,
        summary=args.summary,
        characters=characters,
        location=args.location,
        establishes=establishes,
        manuscript_ref=args.ref,
        quote=args.quote,
    )

    print(f"Added canon event (ch{event.chapter}): {event.summary[:50]}...")

    return 0


def cmd_canon_relationship_set(args: argparse.Namespace) -> int:
    """Set or update a relationship."""
    canon = Canon(get_project_dir())

    dynamics = args.dynamics.split(",") if args.dynamics else None

    rel = canon.set_relationship(
        args.char_a,
        args.char_b,
        status=args.status,
        as_of_chapter=args.chapter,
        dynamics=dynamics,
    )

    print(f"Set relationship: {rel.character_a} & {rel.character_b}")
    print(f"  Status: {rel.status} (as of ch{rel.as_of_chapter})")
    if rel.history:
        print(f"  History: {', '.join(rel.history)}")

    return 0


def cmd_canon_show(args: argparse.Namespace) -> int:
    """Show canon."""
    canon = Canon(get_project_dir())

    if args.chapter:
        print(canon.format_chapter(args.chapter))
    elif args.character:
        print(canon.format_character_history(args.character))
    elif args.recent:
        print(canon.format_recent(args.recent))
    else:
        print(canon.format_for_prompt())

    return 0


# State commands (motivations, beliefs, constraints)

def cmd_state_motivation_add(args: argparse.Namespace) -> int:
    """Add a motivation for a character."""
    state = CharacterState(get_project_dir())

    # Parse motivation type
    mot_type = MotivationType.GOAL
    if args.type:
        try:
            mot_type = MotivationType(args.type.lower())
        except ValueError:
            print(f"Invalid motivation type: {args.type}")
            print(f"Valid types: {', '.join(t.value for t in MotivationType)}")
            return 1

    mot = state.add_motivation(
        character=args.character,
        description=args.description,
        type=mot_type,
        intensity=args.intensity or 5,
        as_of_chapter=args.chapter or 0,
        decay_rate=args.decay or 0.0,
        source_event=args.source,
    )

    print(f"Added motivation for {mot.character}:")
    print(f"  [{mot.type.value.upper()}] {mot.description}")
    print(f"  Intensity: {mot.intensity}/10")
    if mot.decay_rate > 0:
        print(f"  Decays at: {mot.decay_rate * 100:.0f}% per chapter")

    return 0


def cmd_state_motivation_list(args: argparse.Namespace) -> int:
    """List motivations for a character."""
    state = CharacterState(get_project_dir())

    motivations = state.motivations_for_character(
        args.character,
        active_only=not args.all,
        at_chapter=args.chapter,
    )

    if not motivations:
        print(f"No motivations recorded for {args.character}.")
        return 0

    active_count = sum(1 for m in motivations if m.is_active)
    print(f"Motivations for {args.character} ({active_count} active):\n")

    for mot in motivations:
        status = "✓" if mot.is_active else "✗"
        intensity = mot.effective_intensity(args.chapter) if args.chapter else mot.intensity
        print(f"  {status} [{mot.type.value.upper()}] {mot.description}")
        print(f"      Intensity: {intensity:.1f}/10 (ch{mot.as_of_chapter})")
        if mot.conflicts_with:
            print(f"      Conflicts with: {len(mot.conflicts_with)} other motivation(s)")
        if mot.resolution:
            print(f"      Resolved: {mot.resolution} (ch{mot.resolved_at_chapter})")
        print()

    return 0


def cmd_state_motivation_resolve(args: argparse.Namespace) -> int:
    """Mark a motivation as resolved."""
    state = CharacterState(get_project_dir())

    mot = state.resolve_motivation(args.id, args.chapter, resolution=args.resolution or "achieved")
    if not mot:
        print(f"Motivation not found: {args.id}")
        return 1

    print(f"Resolved motivation: {mot.description}")
    print(f"  Resolution: {mot.resolution} (ch{mot.resolved_at_chapter})")

    return 0


def cmd_state_motivation_conflict(args: argparse.Namespace) -> int:
    """Mark two motivations as conflicting."""
    state = CharacterState(get_project_dir())

    if state.add_motivation_conflict(args.id_a, args.id_b):
        print(f"Marked motivations as conflicting.")
        return 0
    else:
        print(f"Motivation not found: {args.id_a}")
        return 1


def cmd_state_belief_add(args: argparse.Namespace) -> int:
    """Add a belief for a character."""
    state = CharacterState(get_project_dir())

    is_true = None
    if args.true:
        is_true = True
    elif args.false:
        is_true = False

    belief = state.add_belief(
        character=args.character,
        belief=args.belief,
        learned_at_chapter=args.chapter or 0,
        is_true=is_true,
        confidence=args.confidence or 5,
        source=args.source,
    )

    truth_marker = ""
    if belief.is_true is True:
        truth_marker = " [TRUE]"
    elif belief.is_true is False:
        truth_marker = " [FALSE]"

    print(f"Added belief for {belief.character}:")
    print(f"  \"{belief.belief}\"{truth_marker}")
    print(f"  Confidence: {belief.confidence}/10")
    print(f"  Learned: ch{belief.learned_at_chapter}")
    if belief.source:
        print(f"  Source: {belief.source}")

    return 0


def cmd_state_belief_list(args: argparse.Namespace) -> int:
    """List beliefs for a character."""
    state = CharacterState(get_project_dir())

    beliefs = state.beliefs_for_character(
        args.character,
        held_only=not args.all,
        at_chapter=args.chapter,
    )

    if not beliefs:
        print(f"No beliefs recorded for {args.character}.")
        return 0

    held_count = sum(1 for b in beliefs if b.is_held)
    print(f"Beliefs held by {args.character} ({held_count} current):\n")

    for belief in beliefs:
        status = "✓" if belief.is_held else "✗"
        truth = ""
        if belief.is_true is True:
            truth = " [TRUE]"
        elif belief.is_true is False:
            truth = " [FALSE]"
        else:
            truth = " [?]"

        print(f"  {status} \"{belief.belief}\"{truth}")
        print(f"      Confidence: {belief.confidence}/10, learned ch{belief.learned_at_chapter}")
        if belief.source:
            print(f"      Source: {belief.source}")
        if belief.invalidated_at_chapter:
            print(f"      Invalidated: ch{belief.invalidated_at_chapter}")
        print()

    return 0


def cmd_state_belief_invalidate(args: argparse.Namespace) -> int:
    """Mark a belief as invalidated (character learned it was wrong)."""
    state = CharacterState(get_project_dir())

    belief = state.invalidate_belief(args.id, args.chapter)
    if not belief:
        print(f"Belief not found: {args.id}")
        return 1

    print(f"Invalidated belief: \"{belief.belief}\"")
    print(f"  {belief.character} learned the truth at ch{belief.invalidated_at_chapter}")

    return 0


def cmd_state_constraint_add(args: argparse.Namespace) -> int:
    """Add a behavioral constraint for a character."""
    state = CharacterState(get_project_dir())

    prerequisites = args.requires.split(",") if args.requires else None
    exceptions = args.unless.split(",") if args.unless else None

    constraint = state.add_constraint(
        character=args.character,
        action_type=args.action,
        constraint=args.constraint,
        cost=args.cost,
        prerequisites=prerequisites,
        exceptions=exceptions,
        as_of_chapter=args.chapter or 0,
        source=args.source,
    )

    print(f"Added constraint for {constraint.character}:")
    print(f"  Action: {constraint.action_type}")
    print(f"  Constraint: {constraint.constraint}")
    if constraint.cost:
        print(f"  Cost: {constraint.cost}")
    if constraint.prerequisites:
        print(f"  Requires: {', '.join(constraint.prerequisites)}")
    if constraint.exceptions:
        print(f"  Unless: {', '.join(constraint.exceptions)}")

    return 0


def cmd_state_constraint_list(args: argparse.Namespace) -> int:
    """List constraints for a character."""
    state = CharacterState(get_project_dir())

    constraints = state.constraints_for_character(args.character, action_type=args.action)

    if not constraints:
        if args.action:
            print(f"No constraints for {args.character} on '{args.action}'.")
        else:
            print(f"No constraints recorded for {args.character}.")
        return 0

    print(f"Behavioral constraints for {args.character}:\n")

    for c in constraints:
        print(f"  [{c.action_type.upper()}] {c.constraint}")
        if c.cost:
            print(f"      Cost: {c.cost}")
        if c.prerequisites:
            print(f"      Requires: {', '.join(c.prerequisites)}")
        if c.exceptions:
            print(f"      Unless: {', '.join(c.exceptions)}")
        if c.source:
            print(f"      Source: {c.source}")
        print()

    return 0


def cmd_state_show(args: argparse.Namespace) -> int:
    """Show complete state for a character."""
    state = CharacterState(get_project_dir())

    if args.character:
        print(state.format_character_state(args.character, at_chapter=args.chapter))
    else:
        print(state.format_all_for_prompt(at_chapter=args.chapter))

    return 0


def cmd_state_check(args: argparse.Namespace) -> int:
    """Check narrative coherence for a character action."""
    project_dir = get_project_dir()
    verifier = NarrativeVerifier(project_dir)

    warnings = verifier.verify_action(
        character=args.character,
        action=args.action,
        chapter=args.chapter or 1,
        action_type=args.type,
    )

    if not warnings:
        print("✓ No narrative warnings")
        return 0

    print(f"Narrative warnings ({len(warnings)}):\n")
    for w in warnings:
        severity_icon = "⚠️" if w.severity == "warning" else "ℹ️"
        print(f"  {severity_icon} [{w.warning_type}] {w.message}")
        if w.suggestion:
            print(f"      → {w.suggestion}")
        print()

    return 0


def cmd_state_context(args: argparse.Namespace) -> int:
    """Get narrative context for LLM prompts."""
    project_dir = get_project_dir()
    verifier = NarrativeVerifier(project_dir)

    context = verifier.get_character_context(args.character, args.chapter or 1)
    print(context)

    return 0


# Verification commands

def cmd_verify(args: argparse.Namespace) -> int:
    """Verify content against bible and canon."""
    project_dir = get_project_dir()
    verifier = FictionVerifier(project_dir)

    # Get content
    if args.file:
        content = Path(args.file).read_text()
    elif args.content:
        content = args.content
    else:
        # Read from stdin
        content = sys.stdin.read()

    characters = args.characters.split(",") if args.characters else []

    if args.quick:
        # Quick check
        passed, issues = verifier.quick_check(content, characters)
        if passed:
            print("✓ Quick check passed")
            return 0
        else:
            print("✗ Quick check failed:")
            for issue in issues:
                print(f"  - {issue}")
            return 1
    else:
        # Full scene verification
        results = verifier.verify_scene(
            content,
            characters=characters,
            chapter=args.chapter or 1,
            location=args.location,
        )

        failures = [r for r in results if not r.success]
        warnings = [r for r in failures if r.severity == "warning"]
        errors = [r for r in failures if r.severity == "error"]
        passed = [r for r in results if r.success]

        print(f"Verification: {len(passed)} passed, {len(errors)} errors, {len(warnings)} warnings\n")

        if errors:
            print("Errors:")
            for r in errors:
                print(f"  ✗ {r.claim.describe()}: {r.message}")
                for s in r.suggestions:
                    print(f"      → {s}")

        if warnings:
            print("\nWarnings:")
            for r in warnings:
                print(f"  ⚠ {r.claim.describe()}: {r.message}")
                for s in r.suggestions:
                    print(f"      → {s}")

        if passed and args.verbose:
            print("\nPassed:")
            for r in passed:
                print(f"  ✓ {r.claim.describe()}: {r.message}")

        return 1 if errors else 0


def cmd_check(args: argparse.Namespace) -> int:
    """Quick inline check (for integration with editors/tools)."""
    project_dir = get_project_dir()
    verifier = FictionVerifier(project_dir)

    # Get content
    if args.file:
        content = Path(args.file).read_text()
    else:
        content = sys.stdin.read()

    characters = args.characters.split(",") if args.characters else []

    passed, issues = verifier.quick_check(content, characters)

    if args.json:
        result = {
            "passed": passed,
            "issues": issues,
        }
        print(json.dumps(result))
    else:
        if passed:
            print("OK")
        else:
            for issue in issues:
                print(issue)

    return 0 if passed else 1


# ============================================================================
# PLOT THREAD COMMANDS
# ============================================================================

def cmd_thread_add(args: argparse.Namespace) -> int:
    """Add a plot thread."""
    canon = Canon(get_project_dir())

    # Parse thread type
    try:
        thread_type = ThreadType(args.type.lower())
    except ValueError:
        print(f"Invalid thread type: {args.type}")
        print(f"Valid types: {', '.join(t.value for t in ThreadType)}")
        return 1

    characters = args.characters.split(",") if args.characters else None

    thread = canon.add_thread(
        name=args.name,
        thread_type=thread_type,
        description=args.description,
        planted_chapter=args.chapter,
        planted_text=args.quote,
        characters=characters,
        expected_payoff_by=args.payoff_by,
        importance=args.importance or 5,
        notes=args.notes,
    )

    print(f"Added plot thread: {thread.name}")
    print(f"  Type: {thread.thread_type.value}")
    print(f"  Planted: chapter {thread.planted_chapter}")
    if thread.expected_payoff_by:
        print(f"  Expected payoff by: chapter {thread.expected_payoff_by}")
    print(f"  ID: {thread.id}")

    return 0


def cmd_thread_list(args: argparse.Namespace) -> int:
    """List plot threads."""
    canon = Canon(get_project_dir())

    if args.active:
        threads = canon.active_threads()
    elif args.type:
        try:
            thread_type = ThreadType(args.type.lower())
            threads = canon.threads_by_type(thread_type)
        except ValueError:
            print(f"Invalid thread type: {args.type}")
            return 1
    elif args.character:
        threads = canon.threads_for_character(args.character)
    else:
        threads = canon.all_threads()

    if not threads:
        print("No plot threads found.")
        return 0

    # Group by status
    by_status: dict[str, list] = {}
    for t in threads:
        status = t.status.value
        if status not in by_status:
            by_status[status] = []
        by_status[status].append(t)

    for status, status_threads in by_status.items():
        status_icon = {
            "planted": "🌱",
            "developing": "🔄",
            "resolved": "✓",
            "abandoned": "✗",
            "overdue": "⚠️",
        }.get(status, "•")

        print(f"\n{status_icon} {status.upper()} ({len(status_threads)})")
        for t in status_threads:
            print(f"  [{t.thread_type.value}] {t.name}")
            print(f"      {t.description[:60]}...")
            print(f"      Planted: ch{t.planted_chapter}, Importance: {t.importance}/10")
            if t.expected_payoff_by:
                print(f"      Payoff by: ch{t.expected_payoff_by}")
            print(f"      ID: {t.id}")

    return 0


def cmd_thread_develop(args: argparse.Namespace) -> int:
    """Add a development to a thread."""
    canon = Canon(get_project_dir())

    # Try to find by ID or name
    thread = canon.get_thread(args.id) or canon.get_thread_by_name(args.id)
    if not thread:
        print(f"Thread not found: {args.id}")
        return 1

    thread = canon.develop_thread(str(thread.id), args.chapter, args.description)

    print(f"Added development to: {thread.name}")
    print(f"  Ch{args.chapter}: {args.description}")
    print(f"  Status: {thread.status.value}")

    return 0


def cmd_thread_resolve(args: argparse.Namespace) -> int:
    """Resolve a plot thread."""
    canon = Canon(get_project_dir())

    # Try to find by ID or name
    thread = canon.get_thread(args.id) or canon.get_thread_by_name(args.id)
    if not thread:
        print(f"Thread not found: {args.id}")
        return 1

    thread = canon.resolve_thread(str(thread.id), args.chapter, args.resolution)

    print(f"Resolved thread: {thread.name}")
    print(f"  Resolution: {thread.resolution}")
    print(f"  Resolved in: chapter {thread.resolved_chapter}")

    return 0


def cmd_thread_abandon(args: argparse.Namespace) -> int:
    """Abandon a plot thread."""
    canon = Canon(get_project_dir())

    # Try to find by ID or name
    thread = canon.get_thread(args.id) or canon.get_thread_by_name(args.id)
    if not thread:
        print(f"Thread not found: {args.id}")
        return 1

    thread = canon.abandon_thread(str(thread.id), reason=args.reason)

    print(f"Abandoned thread: {thread.name}")
    if args.reason:
        print(f"  Reason: {args.reason}")

    return 0


def cmd_thread_audit(args: argparse.Namespace) -> int:
    """Audit all Chekhov's guns and setups."""
    canon = Canon(get_project_dir())

    current_chapter = args.chapter or 1
    audit = canon.chekhov_audit(current_chapter)

    total = sum(len(v) for v in audit.values())
    print(f"Chekhov Audit (as of chapter {current_chapter})")
    print(f"Total active threads: {total}\n")

    if audit["overdue"]:
        print("⚠️  OVERDUE - Need immediate attention:")
        for t in audit["overdue"]:
            print(f"    [{t.thread_type.value}] {t.name}")
            print(f"        Expected by ch{t.expected_payoff_by}, now ch{current_chapter}")
            print(f"        {t.description}")
        print()

    if audit["approaching"]:
        print("📌 APPROACHING DEADLINE:")
        for t in audit["approaching"]:
            print(f"    [{t.thread_type.value}] {t.name}")
            print(f"        Due by ch{t.expected_payoff_by}")
        print()

    if audit["developing"]:
        print("🔄 DEVELOPING:")
        for t in audit["developing"]:
            if t.developments:
                latest = t.developments[-1]
                print(f"    [{t.thread_type.value}] {t.name}")
                print(f"        Latest: ch{latest['chapter']} - {latest['description'][:40]}...")
        print()

    if audit["planted"]:
        print("🌱 PLANTED (not yet developed):")
        for t in audit["planted"]:
            print(f"    [{t.thread_type.value}] {t.name} (ch{t.planted_chapter})")

    return 0


def cmd_thread_show(args: argparse.Namespace) -> int:
    """Show thread details."""
    canon = Canon(get_project_dir())

    # Try to find by ID or name
    thread = canon.get_thread(args.id) or canon.get_thread_by_name(args.id)
    if not thread:
        print(f"Thread not found: {args.id}")
        return 1

    print(f"# {thread.name}")
    print(f"Type: {thread.thread_type.value}")
    print(f"Status: {thread.status.value}")
    print(f"Importance: {thread.importance}/10")
    print()
    print(f"## Description")
    print(thread.description)
    print()
    print(f"## Timeline")
    print(f"Planted: chapter {thread.planted_chapter}")
    if thread.planted_text:
        print(f"  > {thread.planted_text}")
    if thread.expected_payoff_by:
        print(f"Expected payoff by: chapter {thread.expected_payoff_by}")
    if thread.resolved_chapter:
        print(f"Resolved: chapter {thread.resolved_chapter}")
        print(f"Resolution: {thread.resolution}")

    if thread.developments:
        print()
        print("## Developments")
        for dev in thread.developments:
            print(f"  Ch{dev['chapter']}: {dev['description']}")

    if thread.characters:
        print()
        print(f"Characters: {', '.join(thread.characters)}")

    if thread.notes:
        print()
        print(f"## Notes")
        print(thread.notes)

    print()
    print(f"ID: {thread.id}")

    return 0


# ============================================================================
# SCENE PROPOSAL COMMANDS
# ============================================================================

def cmd_proposal_create(args: argparse.Namespace) -> int:
    """Create a scene proposal."""
    canon = Canon(get_project_dir())

    characters = args.characters.split(",") if args.characters else None
    threads_advanced = args.advances.split(",") if args.advances else None
    threads_resolved = args.resolves.split(",") if args.resolves else None
    canon_events = args.establishes.split(";") if args.establishes else None

    proposal = canon.create_proposal(
        chapter=args.chapter,
        title=args.title,
        summary=args.summary,
        characters=characters,
        location=args.location,
        scene_number=args.scene,
        threads_advanced=threads_advanced,
        threads_resolved=threads_resolved,
        canon_events=canon_events,
    )

    print(f"Created scene proposal: {proposal.title}")
    print(f"  Chapter: {proposal.chapter}")
    if proposal.scene_number:
        print(f"  Scene: {proposal.scene_number}")
    print(f"  Status: {proposal.status}")
    print(f"  ID: {proposal.id}")

    return 0


def cmd_proposal_list(args: argparse.Namespace) -> int:
    """List scene proposals."""
    canon = Canon(get_project_dir())

    if args.pending:
        proposals = canon.pending_proposals()
    elif args.chapter:
        proposals = canon.proposals_by_chapter(args.chapter)
    else:
        proposals = canon.all_proposals()

    if not proposals:
        print("No proposals found.")
        return 0

    # Group by status
    by_status: dict[str, list] = {}
    for p in proposals:
        if p.status not in by_status:
            by_status[p.status] = []
        by_status[p.status].append(p)

    for status, status_proposals in by_status.items():
        status_icon = {
            "pending": "⏳",
            "revised": "🔄",
            "approved": "✓",
            "rejected": "✗",
        }.get(status, "•")

        print(f"\n{status_icon} {status.upper()} ({len(status_proposals)})")
        for p in status_proposals:
            print(f"  Ch{p.chapter}: {p.title}")
            print(f"      {p.summary[:60]}...")
            if p.characters:
                print(f"      Characters: {', '.join(p.characters)}")
            if p.rejection_reason:
                print(f"      Rejected: {p.rejection_reason}")
            print(f"      ID: {p.id}")

    return 0


def cmd_proposal_show(args: argparse.Namespace) -> int:
    """Show proposal details."""
    canon = Canon(get_project_dir())

    proposal = canon.get_proposal(args.id)
    if not proposal:
        print(f"Proposal not found: {args.id}")
        return 1

    print(f"# {proposal.title}")
    print(f"Chapter: {proposal.chapter}")
    if proposal.scene_number:
        print(f"Scene: {proposal.scene_number}")
    print(f"Status: {proposal.status}")
    if proposal.location:
        print(f"Location: {proposal.location}")
    if proposal.characters:
        print(f"Characters: {', '.join(proposal.characters)}")
    print()
    print("## Summary")
    print(proposal.summary)

    if proposal.content:
        print()
        print("## Content")
        print(proposal.content[:500])
        if len(proposal.content) > 500:
            print("...")

    if proposal.threads_advanced:
        print()
        print(f"Advances threads: {', '.join(proposal.threads_advanced)}")

    if proposal.threads_resolved:
        print(f"Resolves threads: {', '.join(proposal.threads_resolved)}")

    if proposal.canon_events:
        print()
        print("## Establishes")
        for event in proposal.canon_events:
            print(f"  - {event}")

    if proposal.verification_result:
        print()
        print("## Verification")
        print(json.dumps(proposal.verification_result, indent=2))

    if proposal.rejection_reason:
        print()
        print(f"## Rejection Reason")
        print(proposal.rejection_reason)

    print()
    print(f"ID: {proposal.id}")
    print(f"Created: {proposal.created_at}")
    if proposal.reviewed_at:
        print(f"Reviewed: {proposal.reviewed_at}")

    return 0


def cmd_proposal_approve(args: argparse.Namespace) -> int:
    """Approve a scene proposal."""
    canon = Canon(get_project_dir())

    proposal = canon.approve_proposal(args.id)
    if not proposal:
        print(f"Proposal not found: {args.id}")
        return 1

    print(f"Approved proposal: {proposal.title}")
    print(f"  Status: {proposal.status}")

    if proposal.threads_advanced:
        print(f"  Advanced threads: {len(proposal.threads_advanced)}")
    if proposal.threads_resolved:
        print(f"  Resolved threads: {len(proposal.threads_resolved)}")
    if proposal.canon_events:
        print(f"  Canon events added: {len(proposal.canon_events)}")

    return 0


def cmd_proposal_reject(args: argparse.Namespace) -> int:
    """Reject a scene proposal."""
    canon = Canon(get_project_dir())

    proposal = canon.reject_proposal(args.id, args.reason)
    if not proposal:
        print(f"Proposal not found: {args.id}")
        return 1

    print(f"Rejected proposal: {proposal.title}")
    print(f"  Reason: {proposal.rejection_reason}")

    return 0


def cmd_proposal_verify(args: argparse.Namespace) -> int:
    """Verify a scene proposal against bible and canon."""
    project_dir = get_project_dir()
    canon = Canon(project_dir)
    verifier = FictionVerifier(project_dir)

    proposal = canon.get_proposal(args.id)
    if not proposal:
        print(f"Proposal not found: {args.id}")
        return 1

    # Use proposal content or summary for verification
    content = proposal.content or proposal.summary

    results = verifier.verify_scene(
        content,
        characters=proposal.characters,
        chapter=proposal.chapter,
        location=proposal.location,
    )

    failures = [r for r in results if not r.success]
    warnings = [r for r in failures if r.severity == "warning"]
    errors = [r for r in failures if r.severity == "error"]
    passed = [r for r in results if r.success]

    print(f"Verification for: {proposal.title}")
    print(f"Results: {len(passed)} passed, {len(errors)} errors, {len(warnings)} warnings\n")

    if errors:
        print("Errors:")
        for r in errors:
            print(f"  ✗ {r.claim.describe()}: {r.message}")
            for s in r.suggestions:
                print(f"      → {s}")

    if warnings:
        print("\nWarnings:")
        for r in warnings:
            print(f"  ⚠ {r.claim.describe()}: {r.message}")

    # Store verification result
    proposal.verification_result = {
        "passed": len(passed),
        "errors": len(errors),
        "warnings": len(warnings),
        "details": [
            {"claim": r.claim.describe(), "message": r.message, "success": r.success}
            for r in results
        ],
    }
    canon._save()

    return 1 if errors else 0


# ============================================================================
# PROMPT GENERATION COMMANDS
# ============================================================================

def cmd_prompt_scene(args: argparse.Namespace) -> int:
    """Generate context prompt for writing a scene."""
    project_dir = get_project_dir()
    bible = Bible(project_dir)
    canon = Canon(project_dir)
    state = CharacterState(project_dir)

    characters = args.characters.split(",") if args.characters else []

    sections = []

    # Header
    sections.append(f"# Scene Context: Chapter {args.chapter}")
    if args.location:
        sections.append(f"Location: {args.location}")
    sections.append("")

    # Recent events
    if args.chapter > 1:
        sections.append("## Recent Events")
        sections.append(canon.format_recent(num_chapters=min(2, args.chapter - 1)))
        sections.append("")

    # Active threads
    sections.append("## Active Plot Threads")
    sections.append(canon.format_threads_for_prompt(current_chapter=args.chapter))
    sections.append("")

    # Characters
    if characters:
        sections.append("## Characters in Scene")
        for char_name in characters:
            char = bible.get_character(char_name.strip())
            if char:
                sections.append(char.format_for_prompt())
                sections.append("")

                # Character state
                char_state = state.format_character_state(char_name.strip(), at_chapter=args.chapter)
                if char_state and "No state" not in char_state:
                    sections.append(char_state)
                    sections.append("")

                # Relationships with other scene characters
                for other_name in characters:
                    if other_name.strip() != char_name.strip():
                        rel = canon.get_relationship(char_name.strip(), other_name.strip())
                        if rel:
                            sections.append(f"  Relationship with {other_name}: {rel.status}")
                            for dyn in rel.dynamics:
                                sections.append(f"    - {dyn}")

    # Tone
    tone = bible.get_tone()
    if tone:
        sections.append("")
        sections.append(tone.format_for_prompt())

    # Banned tropes
    tropes = bible.all_banned_tropes()
    if tropes:
        sections.append("")
        sections.append("## Banned Tropes")
        for trope in tropes:
            sections.append(f"- {trope.name}: {trope.reason}")

    prompt = "\n".join(sections)

    if args.output:
        Path(args.output).write_text(prompt)
        print(f"Wrote prompt to: {args.output}")
    else:
        print(prompt)

    return 0


def cmd_prompt_character(args: argparse.Namespace) -> int:
    """Generate context prompt for a specific character."""
    project_dir = get_project_dir()
    bible = Bible(project_dir)
    canon = Canon(project_dir)
    state = CharacterState(project_dir)
    verifier = NarrativeVerifier(project_dir)

    char = bible.get_character(args.character)
    if not char:
        print(f"Character not found: {args.character}")
        return 1

    sections = []

    # Character bible
    sections.append(char.format_for_prompt())
    sections.append("")

    # Character history
    sections.append("## History")
    sections.append(canon.format_character_history(args.character))
    sections.append("")

    # Character state
    if args.chapter:
        sections.append(f"## Current State (Chapter {args.chapter})")
        sections.append(state.format_character_state(args.character, at_chapter=args.chapter))
        sections.append("")

        # Narrative context
        context = verifier.get_character_context(args.character, args.chapter)
        sections.append("## Narrative Context")
        sections.append(context)

    # Threads involving this character
    threads = canon.threads_for_character(args.character)
    active_threads = [t for t in threads if t.is_active]
    if active_threads:
        sections.append("")
        sections.append("## Active Plot Threads")
        for t in active_threads:
            sections.append(t.format_for_prompt())

    prompt = "\n".join(sections)

    if args.output:
        Path(args.output).write_text(prompt)
        print(f"Wrote prompt to: {args.output}")
    else:
        print(prompt)

    return 0


# Context drift commands

def _load_drift_detector(project_dir: Path | None = None) -> "ContextDriftDetector":
    """Load or create drift detector from project state."""
    from .context_drift import ContextDriftDetector, create_context_drift_detector

    pdir = Path(project_dir) if project_dir else get_project_dir()
    state_file = pdir / ".fiction-gov" / "drift_state.json"

    if state_file.exists():
        data = json.loads(state_file.read_text())
        return ContextDriftDetector.from_dict(data)
    return create_context_drift_detector()


def _save_drift_detector(detector: "ContextDriftDetector", project_dir: Path | None = None) -> None:
    """Save drift detector state to project."""
    pdir = Path(project_dir) if project_dir else get_project_dir()
    state_file = pdir / ".fiction-gov" / "drift_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(detector.to_dict(), indent=2))


def cmd_drift_status(args: argparse.Namespace) -> int:
    """Show drift detector state."""
    detector = _load_drift_detector(getattr(args, "path", None))
    state = detector.state

    print(f"Current mode:    {state.current_mode.value}")
    print(f"Risk tier:       {state.risk_tier.value}")
    print(f"Confidence:      {state.mode_conf:.2f}")
    print(f"Last switch:     token {state.last_switch_token}")
    print(f"Transitions:     {len(state.transitions)}")
    if state.transitions:
        last = state.transitions[-1]
        print(f"  Last: {last.from_mode.value} → {last.to_mode.value} "
              f"(conf={last.confidence:.2f}, signaled={last.user_signaled})")
    print(f"\nHysteresis:")
    print(f"  θ_up:          {state.hysteresis.theta_up:.2f}")
    print(f"  θ_down:        {state.hysteresis.theta_down:.2f}")
    print(f"  min_dwell:     {state.hysteresis.min_dwell_tokens}")

    return 0


def cmd_drift_classify(args: argparse.Namespace) -> int:
    """Classify text register/mode."""
    from .context_drift import classify_register

    signals = classify_register(args.text)

    if not signals:
        print("No clear mode signal detected.")
        return 0

    print("Mode signals (ranked by confidence):")
    for sig in signals:
        print(f"  {sig.mode.value:15s}  conf={sig.confidence:.3f}")

    return 0


def cmd_drift_set(args: argparse.Namespace) -> int:
    """Force narrative mode."""
    from .context_drift import NarrativeMode

    mode_str = args.mode.upper()
    try:
        mode = NarrativeMode(args.mode.lower())
    except ValueError:
        try:
            mode = NarrativeMode[mode_str]
        except KeyError:
            print(f"Unknown mode: {args.mode}")
            print(f"Valid modes: {', '.join(m.value for m in NarrativeMode)}")
            return 1

    detector = _load_drift_detector()
    detector.force_mode(mode)
    _save_drift_detector(detector)

    print(f"Forced mode: {mode.value}")
    print(f"Risk tier:   {detector.risk_tier.value}")

    return 0


def cmd_drift_check(args: argparse.Namespace) -> int:
    """Check text for drift."""
    detector = _load_drift_detector()

    state, fault = detector.update(
        args.text,
        user_signaled=getattr(args, "signaled", False),
    )
    _save_drift_detector(detector)

    print(f"Mode:        {state.current_mode.value}")
    print(f"Risk tier:   {state.risk_tier.value}")
    print(f"Confidence:  {state.mode_conf:.2f}")

    if fault:
        print(f"\n{'ERROR' if fault.severity == 'error' else 'WARNING'}: {fault.fault_type.value}")
        print(f"  {fault.detail}")
    else:
        print("\nNo drift fault detected.")

    return 0


def cmd_drift_reset(args: argparse.Namespace) -> int:
    """Reset drift detector."""
    from .context_drift import create_context_drift_detector

    detector = create_context_drift_detector()
    _save_drift_detector(detector)
    print("Drift detector reset to default (LITERARY, LOW risk).")

    return 0


# Guardrails commands

def _load_guardrails(project_dir: Path | None = None) -> "FictionGuardrails":
    """Load or create guardrails from project state."""
    from .guardrails import FictionGuardrails, create_fiction_guardrails

    pdir = Path(project_dir) if project_dir else get_project_dir()
    state_file = pdir / ".fiction-gov" / "guardrails_state.json"

    if state_file.exists():
        data = json.loads(state_file.read_text())
        return FictionGuardrails.from_dict(data)
    return create_fiction_guardrails()


def _save_guardrails(guardrails: "FictionGuardrails", project_dir: Path | None = None) -> None:
    """Save guardrails state to project."""
    pdir = Path(project_dir) if project_dir else get_project_dir()
    state_file = pdir / ".fiction-gov" / "guardrails_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(guardrails.to_dict(), indent=2))


def cmd_guardrails_check(args: argparse.Namespace) -> int:
    """Check text against all guardrails."""
    from .guardrails import StateContext

    guardrails = _load_guardrails()
    ctx = StateContext(
        world_year=getattr(args, "year", None),
        era_tags=[args.era] if getattr(args, "era", None) else [],
        erotic_allowed=getattr(args, "erotic", False),
        coercive_play_allowed=getattr(args, "coercive", False),
    )

    result = guardrails.check(args.text, ctx)

    if result.passed:
        print("PASSED — no hard constraint violations.")
    else:
        print("BLOCKED — hard constraint violation(s):")
        for v in result.violations:
            print(f"  [{v.constraint_id.value}] {v.description}")

    if result.penalties:
        active = [p for p in result.penalties if p.score > 0]
        if active:
            print(f"\nSoft penalties (total={result.total_penalty:.2f}):")
            for p in active:
                print(f"  [{p.penalty_id.value}] score={p.score:.2f}: {p.description}")
        else:
            print("\nNo soft penalties triggered.")

    return 0 if result.passed else 1


def cmd_guardrails_consent(args: argparse.Namespace) -> int:
    """Update consent state between characters."""
    from .guardrails import ConsentLevel, ConsentScope

    try:
        scope = ConsentScope(args.scope.lower())
    except ValueError:
        print(f"Unknown scope: {args.scope}")
        print(f"Valid scopes: {', '.join(s.value for s in ConsentScope)}")
        return 1

    try:
        level = ConsentLevel(args.level.lower())
    except ValueError:
        print(f"Unknown level: {args.level}")
        print(f"Valid levels: {', '.join(l.value for l in ConsentLevel)}")
        return 1

    guardrails = _load_guardrails()
    guardrails.consent.update_consent(args.char_a, args.char_b, scope, level)
    _save_guardrails(guardrails)

    print(f"Updated consent: {args.char_a} ↔ {args.char_b}")
    print(f"  Scope: {scope.value}  Level: {level.value}")

    return 0


def cmd_guardrails_profiles(args: argparse.Namespace) -> int:
    """List validity profiles."""
    from .guardrails import get_builtin_profiles

    profiles = get_builtin_profiles()

    print(f"Builtin validity profiles ({len(profiles)}):\n")
    for name, profile in profiles.items():
        era = f"{profile.era_start} – {profile.era_end}" if profile.era_start is not None else "any"
        print(f"  {name}")
        print(f"    Era:     {era}")
        print(f"    Valid:   {', '.join(profile.valid_terms[:5])}" +
              (f" (+{len(profile.valid_terms) - 5} more)" if len(profile.valid_terms) > 5 else ""))
        if profile.invalid_terms:
            print(f"    Invalid: {', '.join(profile.invalid_terms[:5])}" +
                  (f" (+{len(profile.invalid_terms) - 5} more)" if len(profile.invalid_terms) > 5 else ""))
        print()

    return 0


def cmd_guardrails_dsi(args: argparse.Namespace) -> int:
    """Check text for DSI (Demographic Salience Intrusion)."""
    from .guardrails import DSIDetector

    detector = DSIDetector()
    signals = detector.detect(args.text)

    if not signals:
        print("No DSI signals detected.")
        return 0

    print(f"DSI signals ({len(signals)}):")
    for sig in signals:
        local = "locally triggered" if sig.locally_triggered else "NOT locally triggered"
        print(f"  Category: {sig.demographic_category}")
        print(f"  Markers:  {', '.join(sig.markers_found)}")
        print(f"  Bundles:  {', '.join(sig.bundles_matched)}")
        print(f"  {local}")
        print()

    return 0


def cmd_guardrails_aii(args: argparse.Namespace) -> int:
    """Check text for AII (Anachronistic Identity Injection)."""
    from .guardrails import AIIDetector

    detector = AIIDetector()

    world_year = getattr(args, "year", None)
    era_tags = [args.era] if getattr(args, "era", None) else []

    signals = detector.detect(args.text, world_year=world_year, era_tags=era_tags)

    if not signals:
        print("No AII signals detected.")
        return 0

    print(f"AII signals ({len(signals)}):")
    for sig in signals:
        print(f"  Term:     {sig.identity_term}")
        print(f"  Context:  {sig.causal_context}")
        print(f"  Profile:  {sig.profile_name or 'none'}")
        print(f"  Valid:    {sig.valid}")
        print()

    return 0 if all(s.valid for s in signals) else 1


def cmd_guardrails_config(args: argparse.Namespace) -> int:
    """Show guardrail config."""
    guardrails = _load_guardrails()
    config = guardrails.config

    print("Guardrail Configuration:")
    print(f"\nHard constraints:")
    print(f"  C1 (consent gate):        {'ON' if config.block_coercive_without_opt_in else 'OFF'}")
    print(f"  C2 (mode escalation):     {'ON' if config.block_high_risk_without_enable else 'OFF'}")
    print(f"  C3 (anachronism causal):  {'ON' if config.block_anachronistic_causal else 'OFF'}")
    print(f"\nSoft penalty weights (λ):")
    print(f"  P1 (DSI):                 {config.lambda_dsi}")
    print(f"  P2 (unearned fact):       {config.lambda_unearned}")
    print(f"  P3 (register drift):      {config.lambda_drift}")
    print(f"  P4 (proxy dominance):     {config.lambda_proxy}")

    # Show consent state summary
    consent = guardrails.consent
    pairs = consent.to_dict().get("pairs", {})
    if pairs:
        print(f"\nConsent pairs tracked: {len(pairs)}")
    else:
        print(f"\nNo consent pairs tracked.")

    gs = consent.global_state
    print(f"Global opt-in: erotic={'yes' if gs.erotic_allowed else 'no'}, "
          f"coercive={'yes' if gs.coercive_play_allowed else 'no'}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        prog="fiction-gov",
        description="Fiction Governor: Keep characters in-character, stories consistent, and tropes at bay.",
    )
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init
    init_parser = subparsers.add_parser("init", help="Initialize a fiction project")
    init_parser.add_argument("--name", help="Project name")
    init_parser.add_argument("--path", help="Project path (default: current directory)")
    init_parser.add_argument("--force", action="store_true", help="Force reinitialize")
    init_parser.set_defaults(func=cmd_init)

    # bible
    bible_parser = subparsers.add_parser("bible", help="Manage story bible")
    bible_subs = bible_parser.add_subparsers(dest="bible_cmd")

    # bible character
    char_parser = bible_subs.add_parser("character", help="Manage characters")
    char_subs = char_parser.add_subparsers(dest="char_cmd")

    char_add = char_subs.add_parser("add", help="Add a character")
    char_add.add_argument("name", help="Character name")
    char_add.add_argument("--role", help="Role (protagonist, antagonist, supporting)")
    char_add.add_argument("--trait", action="append", help="Trait (can use 'trait:nuance' format)")
    char_add.set_defaults(func=cmd_bible_character_add)

    char_trait = char_subs.add_parser("trait", help="Add a trait to a character")
    char_trait.add_argument("name", help="Character name")
    char_trait.add_argument("trait", help="The trait")
    char_trait.add_argument("--nuance", help="Nuance/exception")
    char_trait.add_argument("--note", help="Writing guidance")
    char_trait.set_defaults(func=cmd_bible_character_trait)

    char_anti = char_subs.add_parser("anti", help="Add something character would NEVER do")
    char_anti.add_argument("name", help="Character name")
    char_anti.add_argument("pattern", help="What they would never do")
    char_anti.set_defaults(func=cmd_bible_character_anti)

    char_voice = char_subs.add_parser("voice", help="Set character's voice")
    char_voice.add_argument("name", help="Character name")
    char_voice.add_argument("--internal", help="Internal monologue style")
    char_voice.add_argument("--dialogue", help="Dialogue style")
    char_voice.add_argument("--avoid", help="Words/phrases to avoid (comma-separated)")
    char_voice.set_defaults(func=cmd_bible_character_voice)

    char_show = char_subs.add_parser("show", help="Show character(s)")
    char_show.add_argument("name", nargs="?", help="Character name (omit for all)")
    char_show.set_defaults(func=cmd_bible_character_show)

    # bible trope
    trope_parser = bible_subs.add_parser("trope", help="Manage banned tropes")
    trope_subs = trope_parser.add_subparsers(dest="trope_cmd")

    trope_ban = trope_subs.add_parser("ban", help="Ban a trope")
    trope_ban.add_argument("name", help="Trope name")
    trope_ban.add_argument("--reason", help="Why this trope is banned")
    trope_ban.add_argument("--pattern", action="append", help="Detection pattern (regex)")
    trope_ban.add_argument("--severity", choices=["error", "warning"], default="error")
    trope_ban.set_defaults(func=cmd_bible_trope_ban)

    trope_list = trope_subs.add_parser("list", help="List banned tropes")
    trope_list.set_defaults(func=cmd_bible_trope_list)

    trope_unban = trope_subs.add_parser("unban", help="Unban a trope")
    trope_unban.add_argument("name", help="Trope name")
    trope_unban.set_defaults(func=cmd_bible_trope_unban)

    # bible rule
    rule_parser = bible_subs.add_parser("rule", help="Manage world rules")
    rule_subs = rule_parser.add_subparsers(dest="rule_cmd")

    rule_add = rule_subs.add_parser("add", help="Add a world rule")
    rule_add.add_argument("name", help="Rule name")
    rule_add.add_argument("rule", help="The rule")
    rule_add.add_argument("--category", help="Category (magic, society, geography)")
    rule_add.add_argument("--implies", help="Implications (comma-separated)")
    rule_add.set_defaults(func=cmd_bible_rule_add)

    rule_list = rule_subs.add_parser("list", help="List world rules")
    rule_list.add_argument("--category", help="Filter by category")
    rule_list.set_defaults(func=cmd_bible_rule_list)

    # bible tone
    tone_parser = bible_subs.add_parser("tone", help="Manage tone settings")
    tone_subs = tone_parser.add_subparsers(dest="tone_cmd")

    tone_set = tone_subs.add_parser("set", help="Set tone settings")
    tone_set.add_argument("--genre", help="Primary genre")
    tone_set.add_argument("--not-genre", help="Genres to avoid (comma-separated)")
    tone_set.add_argument("--prose", help="Prose style")
    tone_set.add_argument("--pacing", help="Pacing notes")
    tone_set.add_argument("--avoid", help="Elements to avoid (comma-separated)")
    tone_set.set_defaults(func=cmd_bible_tone_set)

    tone_show = tone_subs.add_parser("show", help="Show tone settings")
    tone_show.set_defaults(func=cmd_bible_tone_show)

    # bible show
    bible_show = bible_subs.add_parser("show", help="Show entire bible")
    bible_show.set_defaults(func=cmd_bible_show)

    # canon
    canon_parser = subparsers.add_parser("canon", help="Manage story canon")
    canon_subs = canon_parser.add_subparsers(dest="canon_cmd")

    # canon event
    event_parser = canon_subs.add_parser("event", help="Manage events")
    event_subs = event_parser.add_subparsers(dest="event_cmd")

    event_add = event_subs.add_parser("add", help="Add a canon event")
    event_add.add_argument("summary", help="Event summary")
    event_add.add_argument("--chapter", type=int, required=True, help="Chapter number")
    event_add.add_argument("--characters", help="Characters involved (comma-separated)")
    event_add.add_argument("--location", help="Location")
    event_add.add_argument("--establishes", help="What this establishes (comma-separated)")
    event_add.add_argument("--ref", help="Manuscript reference")
    event_add.add_argument("--quote", help="Key quote")
    event_add.set_defaults(func=cmd_canon_event_add)

    # canon relationship
    rel_parser = canon_subs.add_parser("relationship", help="Manage relationships")
    rel_subs = rel_parser.add_subparsers(dest="rel_cmd")

    rel_set = rel_subs.add_parser("set", help="Set a relationship")
    rel_set.add_argument("char_a", help="First character")
    rel_set.add_argument("char_b", help="Second character")
    rel_set.add_argument("--status", required=True, help="Relationship status")
    rel_set.add_argument("--chapter", type=int, required=True, help="As of chapter")
    rel_set.add_argument("--dynamics", help="Relationship dynamics (comma-separated)")
    rel_set.set_defaults(func=cmd_canon_relationship_set)

    # canon show
    canon_show = canon_subs.add_parser("show", help="Show canon")
    canon_show.add_argument("--chapter", type=int, help="Show specific chapter")
    canon_show.add_argument("--character", help="Show character's history")
    canon_show.add_argument("--recent", type=int, help="Show recent N chapters")
    canon_show.set_defaults(func=cmd_canon_show)

    # state (motivations, beliefs, constraints)
    state_parser = subparsers.add_parser("state", help="Manage character state (motivations, beliefs, constraints)")
    state_subs = state_parser.add_subparsers(dest="state_cmd")

    # state motivation
    mot_parser = state_subs.add_parser("motivation", help="Manage character motivations")
    mot_subs = mot_parser.add_subparsers(dest="mot_cmd")

    mot_add = mot_subs.add_parser("add", help="Add a motivation")
    mot_add.add_argument("character", help="Character name")
    mot_add.add_argument("description", help="What they want/fear/drive")
    mot_add.add_argument("--type", "-t", choices=["goal", "drive", "fear", "incentive"], default="goal")
    mot_add.add_argument("--intensity", "-i", type=int, help="Intensity 1-10 (default 5)")
    mot_add.add_argument("--chapter", "-c", type=int, help="As of chapter")
    mot_add.add_argument("--decay", "-d", type=float, help="Decay rate 0-1 per chapter")
    mot_add.add_argument("--source", "-s", help="Source event")
    mot_add.set_defaults(func=cmd_state_motivation_add)

    mot_list = mot_subs.add_parser("list", help="List motivations")
    mot_list.add_argument("character", help="Character name")
    mot_list.add_argument("--chapter", "-c", type=int, help="At chapter")
    mot_list.add_argument("--all", "-a", action="store_true", help="Include resolved")
    mot_list.set_defaults(func=cmd_state_motivation_list)

    mot_resolve = mot_subs.add_parser("resolve", help="Mark motivation as resolved")
    mot_resolve.add_argument("id", help="Motivation ID")
    mot_resolve.add_argument("--chapter", "-c", type=int, required=True, help="Resolution chapter")
    mot_resolve.add_argument("--resolution", "-r", help="How resolved (achieved, abandoned, replaced)")
    mot_resolve.set_defaults(func=cmd_state_motivation_resolve)

    mot_conflict = mot_subs.add_parser("conflict", help="Mark motivations as conflicting")
    mot_conflict.add_argument("id_a", help="First motivation ID")
    mot_conflict.add_argument("id_b", help="Second motivation ID")
    mot_conflict.set_defaults(func=cmd_state_motivation_conflict)

    # state belief
    belief_parser = state_subs.add_parser("belief", help="Manage character beliefs")
    belief_subs = belief_parser.add_subparsers(dest="belief_cmd")

    belief_add = belief_subs.add_parser("add", help="Add a belief")
    belief_add.add_argument("character", help="Character name")
    belief_add.add_argument("belief", help="What they believe")
    belief_add.add_argument("--chapter", "-c", type=int, help="When learned")
    belief_add.add_argument("--true", action="store_true", help="Belief is actually true")
    belief_add.add_argument("--false", action="store_true", help="Belief is actually false")
    belief_add.add_argument("--confidence", type=int, help="Confidence 1-10 (default 5)")
    belief_add.add_argument("--source", "-s", help="How learned (witnessed, told by X, assumed)")
    belief_add.set_defaults(func=cmd_state_belief_add)

    belief_list = belief_subs.add_parser("list", help="List beliefs")
    belief_list.add_argument("character", help="Character name")
    belief_list.add_argument("--chapter", "-c", type=int, help="At chapter")
    belief_list.add_argument("--all", "-a", action="store_true", help="Include invalidated")
    belief_list.set_defaults(func=cmd_state_belief_list)

    belief_inv = belief_subs.add_parser("invalidate", help="Mark belief as learned-false")
    belief_inv.add_argument("id", help="Belief ID")
    belief_inv.add_argument("--chapter", "-c", type=int, required=True, help="When they learned")
    belief_inv.set_defaults(func=cmd_state_belief_invalidate)

    # state constraint
    con_parser = state_subs.add_parser("constraint", help="Manage behavioral constraints")
    con_subs = con_parser.add_subparsers(dest="con_cmd")

    con_add = con_subs.add_parser("add", help="Add a constraint")
    con_add.add_argument("character", help="Character name")
    con_add.add_argument("action", help="Action type (violence, deception, vulnerability...)")
    con_add.add_argument("constraint", help="What makes this hard")
    con_add.add_argument("--cost", help="What it costs to do anyway")
    con_add.add_argument("--requires", help="Prerequisites (comma-separated)")
    con_add.add_argument("--unless", help="Exceptions (comma-separated)")
    con_add.add_argument("--chapter", "-c", type=int, help="As of chapter")
    con_add.add_argument("--source", "-s", help="Why this constraint exists")
    con_add.set_defaults(func=cmd_state_constraint_add)

    con_list = con_subs.add_parser("list", help="List constraints")
    con_list.add_argument("character", help="Character name")
    con_list.add_argument("--action", "-a", help="Filter by action type")
    con_list.set_defaults(func=cmd_state_constraint_list)

    # state show
    state_show = state_subs.add_parser("show", help="Show character state")
    state_show.add_argument("--character", "-n", help="Character name (omit for all)")
    state_show.add_argument("--chapter", "-c", type=int, help="At chapter")
    state_show.set_defaults(func=cmd_state_show)

    # state check (verify action narrative coherence)
    state_check = state_subs.add_parser("check", help="Check action narrative coherence")
    state_check.add_argument("character", help="Character name")
    state_check.add_argument("action", help="The action to check")
    state_check.add_argument("--type", "-t", help="Action type (for constraint checking)")
    state_check.add_argument("--chapter", "-c", type=int, help="Chapter number")
    state_check.set_defaults(func=cmd_state_check)

    # state context (get LLM-ready context)
    state_context = state_subs.add_parser("context", help="Get narrative context for LLM prompts")
    state_context.add_argument("character", help="Character name")
    state_context.add_argument("--chapter", "-c", type=int, help="At chapter")
    state_context.set_defaults(func=cmd_state_context)

    # verify
    verify_parser = subparsers.add_parser("verify", help="Verify content")
    verify_parser.add_argument("--file", "-f", help="Content file")
    verify_parser.add_argument("--content", "-c", help="Content string")
    verify_parser.add_argument("--characters", help="Characters in scene (comma-separated)")
    verify_parser.add_argument("--chapter", type=int, help="Chapter number")
    verify_parser.add_argument("--location", help="Scene location")
    verify_parser.add_argument("--quick", "-q", action="store_true", help="Quick check only")
    verify_parser.add_argument("--verbose", "-v", action="store_true", help="Show passed checks")
    verify_parser.set_defaults(func=cmd_verify)

    # check (lightweight for integrations)
    check_parser = subparsers.add_parser("check", help="Quick inline check")
    check_parser.add_argument("--file", "-f", help="Content file")
    check_parser.add_argument("--characters", help="Characters (comma-separated)")
    check_parser.add_argument("--json", action="store_true", help="JSON output")
    check_parser.set_defaults(func=cmd_check)

    # thread (plot thread management)
    thread_parser = subparsers.add_parser("thread", help="Manage plot threads")
    thread_subs = thread_parser.add_subparsers(dest="thread_cmd")

    thread_add = thread_subs.add_parser("add", help="Add a plot thread")
    thread_add.add_argument("name", help="Thread name")
    thread_add.add_argument("description", help="Thread description")
    thread_add.add_argument("--type", "-t", required=True,
                           choices=["chekhov_gun", "foreshadowing", "mystery",
                                   "character_arc", "subplot", "promise", "setup"],
                           help="Thread type")
    thread_add.add_argument("--chapter", "-c", type=int, required=True, help="Planted in chapter")
    thread_add.add_argument("--quote", "-q", help="Planted text quote")
    thread_add.add_argument("--characters", help="Characters involved (comma-separated)")
    thread_add.add_argument("--payoff-by", "-p", type=int, help="Expected payoff by chapter")
    thread_add.add_argument("--importance", "-i", type=int, help="Importance 1-10 (default 5)")
    thread_add.add_argument("--notes", "-n", help="Author notes")
    thread_add.set_defaults(func=cmd_thread_add)

    thread_list = thread_subs.add_parser("list", help="List plot threads")
    thread_list.add_argument("--active", "-a", action="store_true", help="Only active threads")
    thread_list.add_argument("--type", "-t", help="Filter by type")
    thread_list.add_argument("--character", "-n", help="Filter by character")
    thread_list.set_defaults(func=cmd_thread_list)

    thread_show = thread_subs.add_parser("show", help="Show thread details")
    thread_show.add_argument("id", help="Thread ID or name")
    thread_show.set_defaults(func=cmd_thread_show)

    thread_develop = thread_subs.add_parser("develop", help="Add development to thread")
    thread_develop.add_argument("id", help="Thread ID or name")
    thread_develop.add_argument("description", help="Development description")
    thread_develop.add_argument("--chapter", "-c", type=int, required=True, help="Chapter")
    thread_develop.set_defaults(func=cmd_thread_develop)

    thread_resolve = thread_subs.add_parser("resolve", help="Resolve a thread")
    thread_resolve.add_argument("id", help="Thread ID or name")
    thread_resolve.add_argument("resolution", help="How it was resolved")
    thread_resolve.add_argument("--chapter", "-c", type=int, required=True, help="Resolution chapter")
    thread_resolve.set_defaults(func=cmd_thread_resolve)

    thread_abandon = thread_subs.add_parser("abandon", help="Abandon a thread")
    thread_abandon.add_argument("id", help="Thread ID or name")
    thread_abandon.add_argument("--reason", "-r", help="Why abandoned")
    thread_abandon.set_defaults(func=cmd_thread_abandon)

    thread_audit = thread_subs.add_parser("audit", help="Chekhov audit - check all threads")
    thread_audit.add_argument("--chapter", "-c", type=int, help="Current chapter (default 1)")
    thread_audit.set_defaults(func=cmd_thread_audit)

    # proposal (scene proposal management)
    proposal_parser = subparsers.add_parser("proposal", help="Manage scene proposals")
    proposal_subs = proposal_parser.add_subparsers(dest="proposal_cmd")

    proposal_create = proposal_subs.add_parser("create", help="Create a scene proposal")
    proposal_create.add_argument("title", help="Scene title")
    proposal_create.add_argument("summary", help="Scene summary")
    proposal_create.add_argument("--chapter", "-c", type=int, required=True, help="Chapter")
    proposal_create.add_argument("--scene", "-s", type=int, help="Scene number in chapter")
    proposal_create.add_argument("--characters", help="Characters (comma-separated)")
    proposal_create.add_argument("--location", "-l", help="Location")
    proposal_create.add_argument("--advances", "-a", help="Thread IDs to advance (comma-separated)")
    proposal_create.add_argument("--resolves", "-r", help="Thread IDs to resolve (comma-separated)")
    proposal_create.add_argument("--establishes", "-e", help="Canon events (semicolon-separated)")
    proposal_create.set_defaults(func=cmd_proposal_create)

    proposal_list = proposal_subs.add_parser("list", help="List proposals")
    proposal_list.add_argument("--pending", "-p", action="store_true", help="Only pending/revised")
    proposal_list.add_argument("--chapter", "-c", type=int, help="Filter by chapter")
    proposal_list.set_defaults(func=cmd_proposal_list)

    proposal_show = proposal_subs.add_parser("show", help="Show proposal details")
    proposal_show.add_argument("id", help="Proposal ID")
    proposal_show.set_defaults(func=cmd_proposal_show)

    proposal_verify = proposal_subs.add_parser("verify", help="Verify proposal against bible/canon")
    proposal_verify.add_argument("id", help="Proposal ID")
    proposal_verify.set_defaults(func=cmd_proposal_verify)

    proposal_approve = proposal_subs.add_parser("approve", help="Approve a proposal")
    proposal_approve.add_argument("id", help="Proposal ID")
    proposal_approve.set_defaults(func=cmd_proposal_approve)

    proposal_reject = proposal_subs.add_parser("reject", help="Reject a proposal")
    proposal_reject.add_argument("id", help="Proposal ID")
    proposal_reject.add_argument("reason", help="Rejection reason")
    proposal_reject.set_defaults(func=cmd_proposal_reject)

    # prompt (context generation for LLM)
    prompt_parser = subparsers.add_parser("prompt", help="Generate context prompts")
    prompt_subs = prompt_parser.add_subparsers(dest="prompt_cmd")

    prompt_scene = prompt_subs.add_parser("scene", help="Generate scene context")
    prompt_scene.add_argument("--chapter", "-c", type=int, required=True, help="Chapter number")
    prompt_scene.add_argument("--characters", help="Characters in scene (comma-separated)")
    prompt_scene.add_argument("--location", "-l", help="Scene location")
    prompt_scene.add_argument("--output", "-o", help="Output file (default: stdout)")
    prompt_scene.set_defaults(func=cmd_prompt_scene)

    prompt_char = prompt_subs.add_parser("character", help="Generate character context")
    prompt_char.add_argument("character", help="Character name")
    prompt_char.add_argument("--chapter", "-c", type=int, help="At chapter")
    prompt_char.add_argument("--output", "-o", help="Output file (default: stdout)")
    prompt_char.set_defaults(func=cmd_prompt_character)

    # drift - Context drift detection
    drift_parser = subparsers.add_parser("drift", help="Context drift detection")
    drift_subs = drift_parser.add_subparsers(dest="drift_cmd")

    drift_status = drift_subs.add_parser("status", help="Show drift detector state")
    drift_status.add_argument("--path", help="Project path")
    drift_status.set_defaults(func=cmd_drift_status)

    drift_classify = drift_subs.add_parser("classify", help="Classify text register/mode")
    drift_classify.add_argument("text", help="Text to classify")
    drift_classify.set_defaults(func=cmd_drift_classify)

    drift_set_mode = drift_subs.add_parser("set", help="Force narrative mode")
    drift_set_mode.add_argument("mode", help="Mode (literary, romance, erotic, etc.)")
    drift_set_mode.set_defaults(func=cmd_drift_set)

    drift_check = drift_subs.add_parser("check", help="Check text for drift")
    drift_check.add_argument("text", help="Text to check")
    drift_check.add_argument("--signaled", action="store_true", help="User signaled change")
    drift_check.set_defaults(func=cmd_drift_check)

    drift_reset_p = drift_subs.add_parser("reset", help="Reset drift detector")
    drift_reset_p.add_argument("--confirm", action="store_true", required=True)
    drift_reset_p.set_defaults(func=cmd_drift_reset)

    # guardrails - Fiction guardrails (consent, DSI, AII)
    guard_parser = subparsers.add_parser("guardrails", help="Fiction guardrails")
    guard_subs = guard_parser.add_subparsers(dest="guard_cmd")

    guard_check = guard_subs.add_parser("check", help="Check text against all guardrails")
    guard_check.add_argument("text", help="Text to check")
    guard_check.add_argument("--year", type=int, help="World year for anachronism checks")
    guard_check.add_argument("--era", help="Era tag (medieval, renaissance, ancient)")
    guard_check.add_argument("--erotic", action="store_true", help="Erotic content allowed")
    guard_check.add_argument("--coercive", action="store_true", help="Coercive play allowed")
    guard_check.set_defaults(func=cmd_guardrails_check)

    guard_consent = guard_subs.add_parser("consent", help="Update consent state")
    guard_consent.add_argument("char_a", help="Character A")
    guard_consent.add_argument("char_b", help="Character B")
    guard_consent.add_argument("scope", help="Scope (flirt, touch, sex, kink_coercive_play)")
    guard_consent.add_argument("level", help="Level (unknown, no, yes, yes_explicit)")
    guard_consent.set_defaults(func=cmd_guardrails_consent)

    guard_profiles = guard_subs.add_parser("profiles", help="List validity profiles")
    guard_profiles.set_defaults(func=cmd_guardrails_profiles)

    guard_dsi = guard_subs.add_parser("dsi", help="Check text for DSI")
    guard_dsi.add_argument("text", help="Text to check")
    guard_dsi.set_defaults(func=cmd_guardrails_dsi)

    guard_aii = guard_subs.add_parser("aii", help="Check text for AII")
    guard_aii.add_argument("text", help="Text to check")
    guard_aii.add_argument("--year", type=int, help="World year")
    guard_aii.add_argument("--era", help="Era tag")
    guard_aii.set_defaults(func=cmd_guardrails_aii)

    guard_config = guard_subs.add_parser("config", help="Show guardrail config")
    guard_config.set_defaults(func=cmd_guardrails_config)

    # Parse and dispatch
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    if hasattr(args, "func"):
        return args.func(args)
    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
