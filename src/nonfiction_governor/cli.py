"""
CLI for non-fiction governor.

Commands for managing your corpus and verifying writing.
"""

import json
import sys
from pathlib import Path

import click

from .corpus import Corpus
from .doi import fetch_source, DOIFetchError, normalize_doi
from .types import SourceType, WritingClaim, ClaimStrength
from .verifiers import NonfictionVerifier


NONFICTION_DIR = ".nonfiction"


def get_corpus_dir(ctx: click.Context) -> Path:
    """Get the nonfiction directory path."""
    return Path(ctx.obj.get("root", ".")) / NONFICTION_DIR


def ensure_initialized(ctx: click.Context) -> Path:
    """Ensure nonfiction is initialized, return corpus dir."""
    corpus_dir = get_corpus_dir(ctx)
    if not corpus_dir.exists():
        click.echo("Error: Nonfiction governor not initialized. Run 'nonfiction-gov init' first.", err=True)
        ctx.exit(1)
    return corpus_dir


@click.group()
@click.option(
    "--root", "-r",
    type=click.Path(exists=True, file_okay=False, resolve_path=True),
    default=".",
    help="Project root directory",
)
@click.pass_context
def cli(ctx: click.Context, root: str) -> None:
    """Non-Fiction Governor - Constraint system for academic writing."""
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


@cli.command()
@click.pass_context
def init(ctx: click.Context) -> None:
    """Initialize nonfiction governor in the current directory."""
    root = Path(ctx.obj["root"])
    corpus_dir = root / NONFICTION_DIR

    if corpus_dir.exists():
        click.echo(f"Nonfiction governor already initialized at {corpus_dir}")
        return

    corpus_dir.mkdir()

    # Create empty corpus
    Corpus(corpus_dir)

    # Create .gitignore
    gitignore = """\
# Local only
*.log
"""
    (corpus_dir / ".gitignore").write_text(gitignore)

    click.echo(f"Initialized nonfiction governor at {corpus_dir}")
    click.echo("\nNext steps:")
    click.echo("  nonfiction-gov source add --doi <your-paper-doi> --canonical")
    click.echo("  nonfiction-gov concept add <term> --definition '...'")


# Source commands
@cli.group()
def source():
    """Manage sources (your papers and references)."""
    pass


@source.command("add")
@click.option("--doi", help="DOI of the source")
@click.option("--canonical", is_flag=True, help="Mark as your own paper (first-class)")
@click.option("--citation-key", help="Override citation key")
@click.option("--title", help="Title (if not fetching DOI)")
@click.option("--authors", help="Comma-separated author names (if not fetching DOI)")
@click.option("--year", type=int, help="Year (if not fetching DOI)")
@click.pass_context
def source_add(
    ctx: click.Context,
    doi: str | None,
    canonical: bool,
    citation_key: str | None,
    title: str | None,
    authors: str | None,
    year: int | None,
) -> None:
    """
    Add a source to the corpus.

    Examples:
        nonfiction-gov source add --doi 10.5281/zenodo.12345 --canonical
        nonfiction-gov source add --doi 10.1234/paper --citation-key smith2023
        nonfiction-gov source add --title "My Notes" --authors "Me" --year 2024
    """
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    if doi:
        try:
            click.echo(f"Fetching metadata for DOI: {normalize_doi(doi)}...")
            source = corpus.add_source(
                doi=doi,
                canonical=canonical,
                citation_key=citation_key,
            )
        except DOIFetchError as e:
            click.echo(f"Warning: Could not fetch DOI metadata: {e}", err=True)
            click.echo("Creating minimal source entry...")
            source = corpus.add_source(
                doi=doi,
                canonical=canonical,
                citation_key=citation_key or normalize_doi(doi).replace("/", "_"),
            )
    else:
        # Manual entry
        if not title:
            click.echo("Error: Either --doi or --title required", err=True)
            ctx.exit(1)

        author_list = [a.strip() for a in authors.split(",")] if authors else []

        source = corpus.add_source(
            title=title,
            authors=author_list,
            year=year,
            canonical=canonical,
            citation_key=citation_key,
        )

    source_type = "Canonical" if source.is_canonical else "External"
    click.echo(f"\n{source_type} source added:")
    click.echo(f"  Citation key: @{source.citation_key}")
    click.echo(f"  Title: {source.title}")
    if source.authors:
        authors_str = ", ".join(str(a) for a in source.authors)
        click.echo(f"  Authors: {authors_str}")
    if source.year:
        click.echo(f"  Year: {source.year}")
    if source.doi:
        click.echo(f"  DOI: {source.doi}")


@source.command("list")
@click.option("--canonical-only", is_flag=True, help="Show only canonical sources")
@click.option("--external-only", is_flag=True, help="Show only external references")
@click.pass_context
def source_list(ctx: click.Context, canonical_only: bool, external_only: bool) -> None:
    """List all sources in the corpus."""
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    if canonical_only:
        sources = corpus.canonical_sources()
        label = "Canonical sources"
    elif external_only:
        sources = corpus.external_sources()
        label = "External references"
    else:
        sources = corpus.all_sources()
        label = "All sources"

    if not sources:
        click.echo("No sources in corpus")
        return

    click.echo(f"{label} ({len(sources)}):\n")

    for s in sorted(sources, key=lambda x: x.year or 0, reverse=True):
        icon = "*" if s.is_canonical else " "
        click.echo(f"  {icon} [@{s.citation_key}] {s.title or '(untitled)'}")
        if s.authors:
            click.echo(f"      {', '.join(str(a) for a in s.authors[:3])}{'...' if len(s.authors) > 3 else ''}")
        if s.year:
            click.echo(f"      Year: {s.year}")
        click.echo()


@source.command("bibtex")
@click.option("--output", "-o", type=click.Path(), help="Output file (default: stdout)")
@click.pass_context
def source_bibtex(ctx: click.Context, output: str | None) -> None:
    """Export sources as BibTeX."""
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    bibtex = corpus.to_bibtex()

    if output:
        Path(output).write_text(bibtex)
        click.echo(f"BibTeX written to {output}")
    else:
        click.echo(bibtex)


# Concept commands
@cli.group()
def concept():
    """Manage concepts (defined terminology)."""
    pass


@concept.command("add")
@click.argument("term")
@click.option("--definition", "-d", required=True, help="Definition of the term")
@click.option("--source-key", "-s", help="Citation key of source that defines this")
@click.option("--aliases", help="Comma-separated aliases for this term")
@click.option("--anti-patterns", help="Comma-separated terms that should NOT be used as synonyms")
@click.pass_context
def concept_add(
    ctx: click.Context,
    term: str,
    definition: str,
    source_key: str | None,
    aliases: str | None,
    anti_patterns: str | None,
) -> None:
    """
    Add a concept (defined term) to the corpus.

    Examples:
        nonfiction-gov concept add "NLAI" -d "Language is a proposal, not an authority" -s beck2024
        nonfiction-gov concept add "epistemic gate" -d "..." --aliases "gating,gate"
    """
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    # Validate source key
    if source_key and not corpus.has_source(source_key):
        click.echo(f"Warning: Source '{source_key}' not in corpus", err=True)

    alias_list = [a.strip() for a in aliases.split(",")] if aliases else []
    anti_list = [a.strip() for a in anti_patterns.split(",")] if anti_patterns else []

    concept = corpus.add_concept(
        term=term,
        definition=definition,
        source_key=source_key,
        aliases=alias_list,
        anti_patterns=anti_list,
    )

    click.echo(f"Concept added: {term}")
    click.echo(f"  Definition: {definition}")
    if alias_list:
        click.echo(f"  Aliases: {', '.join(alias_list)}")
    if anti_list:
        click.echo(f"  Anti-patterns: {', '.join(anti_list)}")


@concept.command("list")
@click.pass_context
def concept_list(ctx: click.Context) -> None:
    """List all concepts in the corpus."""
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    concepts = corpus.all_concepts()

    if not concepts:
        click.echo("No concepts defined")
        return

    click.echo(f"Concepts ({len(concepts)}):\n")

    for c in sorted(concepts, key=lambda x: x.term):
        click.echo(f"  {c.term}")
        click.echo(f"    Definition: {c.definition[:60]}{'...' if len(c.definition) > 60 else ''}")
        if c.aliases:
            click.echo(f"    Aliases: {', '.join(c.aliases)}")
        if c.source_key:
            click.echo(f"    Source: @{c.source_key}")
        click.echo()


# Position commands
@cli.group()
def position():
    """Manage positions (established theses)."""
    pass


@position.command("add")
@click.argument("claim")
@click.option("--source-key", "-s", help="Citation key of source that establishes this")
@click.option("--tags", help="Comma-separated tags")
@click.option("--evidence", help="Supporting evidence (semicolon-separated)")
@click.pass_context
def position_add(
    ctx: click.Context,
    claim: str,
    source_key: str | None,
    tags: str | None,
    evidence: str | None,
) -> None:
    """
    Add a position (thesis) to the corpus.

    Examples:
        nonfiction-gov position add "AI agents should not be trusted with direct file writes" -s beck2024
        nonfiction-gov position add "Evidence must be machine-verifiable" --tags "epistemology,design"
    """
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    tag_list = [t.strip() for t in tags.split(",")] if tags else []
    evidence_list = [e.strip() for e in evidence.split(";")] if evidence else []

    position = corpus.add_position(
        claim=claim,
        source_key=source_key,
        tags=tag_list,
        supporting_evidence=evidence_list,
    )

    click.echo(f"Position added: {position.id}")
    click.echo(f"  Claim: {claim}")
    if source_key:
        click.echo(f"  Source: @{source_key}")
    if tag_list:
        click.echo(f"  Tags: {', '.join(tag_list)}")


@position.command("list")
@click.option("--tag", help="Filter by tag")
@click.option("--all", "show_all", is_flag=True, help="Include superseded positions")
@click.pass_context
def position_list(ctx: click.Context, tag: str | None, show_all: bool) -> None:
    """List positions in the corpus."""
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    if tag:
        positions = corpus.positions_by_tag(tag)
    elif show_all:
        positions = corpus.all_positions()
    else:
        positions = corpus.current_positions()

    if not positions:
        click.echo("No positions found")
        return

    click.echo(f"Positions ({len(positions)}):\n")

    for p in positions:
        status = "" if p.is_current else " [superseded]"
        click.echo(f"  {p.id}{status}")
        click.echo(f"    {p.claim[:70]}{'...' if len(p.claim) > 70 else ''}")
        if p.source_key:
            click.echo(f"    Source: @{p.source_key}")
        if p.tags:
            click.echo(f"    Tags: {', '.join(p.tags)}")
        click.echo()


# Verify command
@cli.command()
@click.argument("file", type=click.Path(exists=True))
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
@click.pass_context
def verify(ctx: click.Context, file: str, json_output: bool) -> None:
    """
    Verify a markdown file against the corpus.

    Checks:
    - All citations are valid
    - Terminology is used correctly
    - No contradictions with established positions
    """
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)
    verifier = NonfictionVerifier(corpus)

    text = Path(file).read_text()
    results = verifier.verify_text(text)

    errors = [r for r in results if not r.valid]
    warnings = [r for r in results if r.valid and r.warnings]

    if json_output:
        output = {
            "file": file,
            "valid": len(errors) == 0,
            "errors": [
                {"message": r.message, "claim": r.claim.describe()}
                for r in errors
            ],
            "warnings": [
                {"message": r.message, "warnings": r.warnings}
                for r in warnings
            ],
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.echo(f"Verifying: {file}\n")

        if errors:
            click.echo(f"Errors ({len(errors)}):")
            for r in errors:
                click.echo(f"  [x] {r.message}")
                for s in r.suggestions:
                    click.echo(f"      Suggestion: {s}")
            click.echo()

        if warnings:
            click.echo(f"Warnings ({len(warnings)}):")
            for r in warnings:
                for w in r.warnings:
                    click.echo(f"  [!] {w}")
            click.echo()

        if not errors:
            click.echo("Verification passed")
        else:
            click.echo(f"\nVerification failed: {len(errors)} error(s)")
            ctx.exit(1)


# Export command
@cli.command()
@click.pass_context
def export(ctx: click.Context) -> None:
    """Export corpus for use in writing prompts."""
    corpus_dir = ensure_initialized(ctx)
    corpus = Corpus(corpus_dir)

    click.echo(corpus.format_for_prompt())


# =============================================================================
# Tone commands
# =============================================================================


@cli.group()
@click.pass_context
def tone(ctx: click.Context) -> None:
    """Tone profile management (voice/style enforcement)."""
    pass


@tone.command("show")
@click.pass_context
def tone_show(ctx: click.Context) -> None:
    """Display current tone profile."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No tone profile set. Create one with 'nonfiction-gov tone create'.")
        return

    profile = manager.profile
    locked = manager.is_locked

    click.echo(f"Tone Profile: {profile.name}")
    if profile.description:
        click.echo(f"  {profile.description}")
    click.echo(f"  Locked: {'Yes' if locked else 'No'}")
    click.echo()

    click.echo("Sentence Structure:")
    click.echo(f"  Average length: {profile.avg_sentence_length} words")
    click.echo(f"  Variance: {profile.sentence_length_variance:.1f}")
    click.echo(f"  Uses fragments: {'Yes' if profile.uses_fragments else 'No'}")
    click.echo(f"  Uses colons: {'Yes' if profile.uses_colons_for_emphasis else 'No'}")
    click.echo()

    click.echo("Voice:")
    click.echo(f"  Second person: {'Yes' if profile.uses_second_person else 'No'}")
    click.echo(f"  First person: {'Yes' if profile.uses_first_person else 'No'}")
    click.echo(f"  Contractions: {profile.contractions_frequency:.0%}")
    click.echo()

    click.echo("Rhetorical Devices:")
    click.echo(f"  Em dashes: {'Yes' if profile.uses_em_dashes else 'No'}")
    click.echo(f"  Parentheticals: {'Yes' if profile.uses_parentheticals else 'No'}")
    click.echo(f"  Rhetorical questions: {'Yes' if profile.uses_rhetorical_questions else 'No'}")
    click.echo(f"  Ellipses: {'Yes' if profile.uses_ellipses else 'No'}")
    click.echo()

    if profile.opening_patterns:
        click.echo("Opening Patterns:")
        for p in profile.opening_patterns:
            click.echo(f"  - \"{p}\"")
        click.echo()

    click.echo(f"Technical Density: {profile.technical_density:.0%}")
    click.echo(f"Sarcasm: {profile.sarcasm_frequency:.0%}")
    click.echo(f"Profanity: {'Yes' if profile.uses_profanity else 'No'}")


@tone.command("create")
@click.option("--name", default="default", help="Profile name")
@click.option("--file", "-f", type=click.Path(exists=True), help="Load from JSON file")
@click.pass_context
def tone_create(ctx: click.Context, name: str, file: str | None) -> None:
    """Create or update tone profile."""
    from .tone import ToneProfile, ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if file:
        profile = ToneProfile.load(Path(file))
        profile.name = name
    else:
        # Read JSON from stdin
        click.echo("Paste tone profile JSON (Ctrl+D when done):")
        try:
            data = json.loads(sys.stdin.read())
            profile = ToneProfile.from_dict(data)
            profile.name = name
        except (json.JSONDecodeError, KeyError) as e:
            click.echo(f"Error parsing JSON: {e}", err=True)
            ctx.exit(1)
            return

    manager.set_profile(profile)
    click.echo(f"Tone profile '{profile.name}' saved to {manager.profile_path}")


@tone.command("edit")
@click.pass_context
def tone_edit(ctx: click.Context) -> None:
    """Show profile path for manual editing."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No tone profile set. Create one first with 'nonfiction-gov tone create'.")
        return

    click.echo(f"Edit the profile at: {manager.profile_path}")
    click.echo("The file is JSON. Reload will pick up changes automatically.")


@tone.command("check")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--tolerance", "-t", default=0.2, help="Tolerance for deviations")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def tone_check(ctx: click.Context, file_path: str, tolerance: float, json_output: bool) -> None:
    """Check a file against the tone profile."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No tone profile set.", err=True)
        ctx.exit(1)
        return

    text = Path(file_path).read_text()
    result = manager.check_text(text, tolerance=tolerance)

    if json_output:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    click.echo(f"Style Analysis: {file_path}")
    click.echo()

    if result.valid:
        click.echo("PASS: Text matches tone profile.")
    else:
        click.echo(f"VIOLATIONS DETECTED ({len(result.violations)})")
        click.echo()
        for v in result.violations:
            click.echo(f"  - {v.message}")
            if v.suggestion:
                click.echo(f"    Suggestion: {v.suggestion}")

    if result.metrics:
        click.echo()
        click.echo("Metrics:")
        click.echo(f"  Sentences: {result.metrics.get('sentence_count', 0)}")
        click.echo(f"  Words: {result.metrics.get('word_count', 0)}")
        click.echo(f"  Avg sentence length: {result.metrics.get('avg_sentence_length', 0)}")
        click.echo(f"  Contractions: {result.metrics.get('contractions_frequency', 0):.0%}")

    if not result.valid:
        ctx.exit(1)


@tone.command("guidance")
@click.pass_context
def tone_guidance(ctx: click.Context) -> None:
    """Show generated tone guidance (for system prompt injection)."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No tone profile set.", err=True)
        ctx.exit(1)
        return

    click.echo(manager.get_system_prompt())


@tone.command("lock")
@click.pass_context
def tone_lock(ctx: click.Context) -> None:
    """Lock tone profile as enforcement invariant."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No tone profile to lock.", err=True)
        ctx.exit(1)
        return

    manager.lock()
    click.echo("Tone profile locked. Violations will block autonomous execution.")


@tone.command("unlock")
@click.option("--confirm", is_flag=True, required=True, help="Confirm unlock")
@click.pass_context
def tone_unlock(ctx: click.Context, confirm: bool) -> None:
    """Unlock tone profile (disables enforcement)."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)
    manager.unlock()
    click.echo("Tone profile unlocked. Style violations will not block execution.")


@tone.command("delete")
@click.option("--confirm", is_flag=True, required=True, help="Confirm deletion")
@click.pass_context
def tone_delete(ctx: click.Context, confirm: bool) -> None:
    """Delete the tone profile."""
    from .tone import ToneManager

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)
    manager.unlock()
    manager.clear_profile()
    click.echo("Tone profile deleted.")


@tone.command("ingest")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--name", default="extracted", help="Profile name")
@click.option("--threshold", default=0.3, help="Boolean feature threshold (0-1)")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def tone_ingest(
    ctx: click.Context,
    files: tuple[str, ...],
    name: str,
    threshold: float,
    json_output: bool,
) -> None:
    """
    Extract tone profile from reference writing files.

    Analyzes one or more files and extracts a ToneProfile from the combined
    writing style. Sets the result as the active profile.

    Examples:
        nonfiction-gov tone ingest reference_writing/*.md
        nonfiction-gov tone ingest chapter1.md chapter2.md --name "my_voice"
    """
    from .tone import ToneManager, extract_tone_profile

    if not files:
        click.echo("Error: No files provided", err=True)
        ctx.exit(1)
        return

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    corpus_paths = [Path(f) for f in files]
    profile = extract_tone_profile(
        corpus_paths, name=name, bool_threshold=threshold,
    )

    manager.set_profile(profile)

    if json_output:
        click.echo(json.dumps(profile.to_dict(), indent=2))
        return

    click.echo(f"Extracted tone profile '{profile.name}' from {len(files)} file(s)")
    click.echo(f"Saved to: {manager.profile_path}")
    click.echo()
    click.echo("Key dimensions:")
    click.echo(f"  Avg sentence length: {profile.avg_sentence_length} words")
    click.echo(f"  Sentence variance: {profile.sentence_length_variance:.1f}")
    click.echo(f"  Contractions: {profile.contractions_frequency:.0%}")
    click.echo(f"  Technical density: {profile.technical_density:.0%}")
    click.echo(f"  Fragments: {'Yes' if profile.uses_fragments else 'No'}")
    click.echo(f"  Second person: {'Yes' if profile.uses_second_person else 'No'}")
    click.echo(f"  First person: {'Yes' if profile.uses_first_person else 'No'}")
    click.echo(f"  Em dashes: {'Yes' if profile.uses_em_dashes else 'No'}")
    click.echo(f"  Rhetorical questions: {'Yes' if profile.uses_rhetorical_questions else 'No'}")

    if profile.opening_patterns:
        click.echo(f"  Opening patterns: {profile.opening_patterns}")
    if profile.favorite_adjectives:
        click.echo(f"  Favorite adjectives: {profile.favorite_adjectives}")
    if profile.favorite_verbs:
        click.echo(f"  Favorite verbs: {profile.favorite_verbs}")


@tone.command("compare")
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--tolerance", "-t", default=0.2, help="Tolerance for deviations")
@click.option("--significant-only", is_flag=True, help="Show only significant deviations")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def tone_compare(
    ctx: click.Context,
    file_path: str,
    tolerance: float,
    significant_only: bool,
    json_output: bool,
) -> None:
    """
    Compare a file's tone against the active profile.

    Extracts a profile from the given file and compares it dimension-by-dimension
    against the active tone profile. Useful for detecting voice drift.

    Examples:
        nonfiction-gov tone compare chapter5.md
        nonfiction-gov tone compare draft.md --significant-only
    """
    from .tone import ToneManager, extract_tone_profile, compare_profiles

    root = Path(ctx.obj.get("root", "."))
    manager = ToneManager(root)

    if not manager.has_profile:
        click.echo("No active tone profile. Set one first with 'tone create' or 'tone ingest'.", err=True)
        ctx.exit(1)
        return

    baseline = manager.profile
    file_profile = extract_tone_profile([Path(file_path)], name="file")
    deviations = compare_profiles(baseline, file_profile, tolerance=tolerance)

    if significant_only:
        deviations = [d for d in deviations if d.significant]

    if json_output:
        click.echo(json.dumps([d.to_dict() for d in deviations], indent=2))
        return

    click.echo(f"Comparing '{file_path}' against profile '{baseline.name}'")
    click.echo()

    if not deviations:
        click.echo("No deviations detected.")
        return

    sig_count = sum(1 for d in deviations if d.significant)
    click.echo(f"Deviations: {len(deviations)} total, {sig_count} significant")
    click.echo()

    for d in deviations:
        marker = "[!]" if d.significant else "[ ]"
        click.echo(f"  {marker} {d.message}")

    if sig_count > 0:
        click.echo()
        click.echo(f"Voice drift detected: {sig_count} significant deviation(s)")
        ctx.exit(1)


# =============================================================================
# CFI commands (Contextual Frame Intrusion detection)
# =============================================================================


@cli.group("cfi")
@click.pass_context
def cfi_cmd(ctx):
    """Contextual Frame Intrusion detection (nonfiction frame drift)."""
    pass


@cfi_cmd.command("check")
@click.argument("text")
@click.option("--expect-frame", "-f", multiple=True, help="Expected frame (e.g. capitalism, safety)")
@click.option("--expect-perspective", "-p", type=click.Choice(["descriptive", "normative", "prescriptive", "analytical"]), help="Expected perspective")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.pass_context
def cfi_check(ctx, text, expect_frame, expect_perspective, as_json):
    """Check text for contextual frame intrusion."""
    from .cfi import CFIDetector, NonfictionFrame, Perspective

    detector = CFIDetector()
    if expect_frame:
        detector.set_expected_frames([NonfictionFrame(f) for f in expect_frame])
    if expect_perspective:
        detector.set_expected_perspective(Perspective(expect_perspective))

    result = detector.check(text)

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
        return

    if result.frames_detected:
        click.echo("Frames detected:")
        for f in result.frames_detected:
            click.echo(f"  {f.frame.value}: confidence={f.confidence:.2f} matches={f.matches}")
    else:
        click.echo("No frames detected.")

    if result.perspective:
        click.echo(f"\nPerspective: {result.perspective.perspective.value} "
                    f"(confidence={result.perspective.confidence:.2f})")

    if result.scope_risk > 0.1:
        click.echo(f"Scope risk: {result.scope_risk:.2f}")

    if result.faults:
        click.echo(f"\nFaults ({len(result.faults)}):")
        for f in result.faults:
            frame_str = f" [{f.frame.value}]" if f.frame else ""
            click.echo(click.style(
                f"  [{f.fault_type.value}]{frame_str} {f.detail}",
                fg="yellow",
            ))
    else:
        click.echo("\nNo faults detected.")


@cfi_cmd.command("scan")
@click.argument("path", type=click.Path(exists=True))
@click.option("--expect-frame", "-f", multiple=True, help="Expected frame")
@click.option("--expect-perspective", "-p", type=click.Choice(["descriptive", "normative", "prescriptive", "analytical"]), help="Expected perspective")
@click.pass_context
def cfi_scan(ctx, path, expect_frame, expect_perspective):
    """Scan a file for frame intrusion, paragraph by paragraph."""
    from .cfi import CFIDetector, NonfictionFrame, Perspective

    text = Path(path).read_text()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    detector = CFIDetector()
    if expect_frame:
        detector.set_expected_frames([NonfictionFrame(f) for f in expect_frame])
    if expect_perspective:
        detector.set_expected_perspective(Perspective(expect_perspective))

    total_faults = 0
    for i, para in enumerate(paragraphs, 1):
        result = detector.record(para)
        if result.faults:
            total_faults += len(result.faults)
            click.echo(f"\nParagraph {i}:")
            click.echo(f"  {para[:80]}...")
            for f in result.faults:
                frame_str = f" [{f.frame.value}]" if f.frame else ""
                click.echo(click.style(
                    f"  [{f.fault_type.value}]{frame_str} {f.detail}",
                    fg="yellow",
                ))

    click.echo(f"\n--- Summary ---")
    click.echo(f"Paragraphs: {len(paragraphs)}")
    click.echo(f"Faults: {total_faults}")
    stats = detector.stats()
    if stats["frame_counts"]:
        click.echo(f"Frame hits: {stats['frame_counts']}")
    if stats["dominant_frame"]:
        click.echo(f"Dominant frame: {stats['dominant_frame']}")
    if stats["perspective_distribution"]:
        click.echo(f"Perspective distribution: {stats['perspective_distribution']}")


@cfi_cmd.command("frames")
def cfi_frames():
    """List all recognized frames in the v0 taxonomy."""
    from .cfi import NonfictionFrame, FRAME_FEATURES

    for frame in NonfictionFrame:
        pattern_count = len(FRAME_FEATURES.get(frame, []))
        click.echo(f"  {frame.value:20s}  ({pattern_count} patterns)")


@cfi_cmd.command("perspectives")
def cfi_perspectives():
    """List all recognized perspectives."""
    from .cfi import Perspective

    descs = {
        "descriptive": "What is — observation, fact, data",
        "normative": "What should be — values, ethics, judgment",
        "prescriptive": "What to do — recommendations, instructions",
        "analytical": "How it works — mechanism, causation",
    }
    for p in Perspective:
        click.echo(f"  {p.value:15s}  {descs.get(p.value, '')}")


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
