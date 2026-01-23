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


def main() -> None:
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
