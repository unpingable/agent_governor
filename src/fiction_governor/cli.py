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
from .types import FictionClaim, FictionClaimType
from .verifiers import FictionVerifier, VerificationResult


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
