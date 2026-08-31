"""Search commands for crossref-local CLI."""

import json
import re
import sys
from typing import Optional

import click
from rich.console import Console

from .. import get, search
from .._core.export import save as _save

console = Console()

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def _strip_xml_tags(text: str) -> str:
    """Strip XML/JATS tags from abstract text."""
    if not text:
        return text
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _get_if(issn: str) -> Optional[float]:
    """The journal's OpenAlex IF proxy for one ISSN.

    This used to be a second copy of the query the HTTP server ran, with
    its own cache. Both now call the one indexed lookup in
    :mod:`crossref_local._impact_factor.journal_lookup`, so the two
    surfaces cannot answer differently.
    """
    from .._impact_factor import impact_factor_for_issn

    return impact_factor_for_issn(issn)


@click.command("search", context_settings=CONTEXT_SETTINGS)
@click.argument("query")
@click.option(
    "-n", "--number", "limit", default=10, show_default=True, help="Number of results"
)
@click.option("-o", "--offset", default=0, help="Skip first N results")
@click.option("-a", "--abstracts", is_flag=True, help="Show abstracts")
@click.option("-A", "--authors", is_flag=True, help="Show authors")
@click.option(
    "-if", "--impact-factor", "with_if", is_flag=True, help="Show journal impact factor"
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--save",
    "save_path",
    type=click.Path(),
    help="Save results to file",
)
@click.option(
    "--format",
    "save_format",
    type=click.Choice(["text", "json", "bibtex"]),
    default="json",
    help="Output format for --save (default: json)",
)
def search_cmd(
    query: str,
    limit: int,
    offset: int,
    abstracts: bool,
    authors: bool,
    with_if: bool,
    as_json: bool,
    save_path: Optional[str],
    save_format: str,
):
    """Search for works by title, abstract, or authors.

    \b
    Example:
      $ crossref-local search "machine learning"
      $ crossref-local search "CRISPR" -n 5 --json
      $ crossref-local search "neural network" --save results.json
    """
    from .._core.config import Config

    try:
        results = search(query, limit=limit, offset=offset, with_if=with_if)
    except ConnectionError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)

    # Local IF lookup only in DB mode (HTTP gets IF from API)
    local_if = with_if and Config.get_mode() != "http"

    # Save to file if requested
    if save_path:
        try:
            saved = _save(
                results, save_path, format=save_format, include_abstract=abstracts
            )
            click.secho(
                f"Saved {len(results)} results to {saved}", fg="green", err=True
            )
        except Exception as e:
            click.secho(f"Error saving: {e}", fg="red", err=True)
            sys.exit(1)

    if as_json:
        output = {
            "query": results.query,
            "total": results.total,
            "elapsed_ms": results.elapsed_ms,
            "works": [w.to_dict() for w in results.works],
        }
        click.echo(json.dumps(output, indent=2))
    else:
        click.secho(
            f"Found {results.total:,} matches in {results.elapsed_ms:.1f}ms\n",
            fg="green",
        )
        for i, work in enumerate(results.works, start=offset + 1):
            title = _strip_xml_tags(work.title) if work.title else "Untitled"
            year = f"({work.year})" if work.year else ""
            click.secho(f"{i}. {title} {year}", fg="cyan", bold=True)
            click.echo(f"   DOI: {work.doi or 'N/A'}")
            if authors and work.authors:
                authors_str = ", ".join(work.authors[:5])
                if len(work.authors) > 5:
                    authors_str += f" et al. ({len(work.authors)} total)"
                click.echo(f"   Authors: {authors_str}")
            journal_line = f"   Journal: {work.journal or 'N/A'}"
            if_val = work.impact_factor or (
                local_if and work.issn and _get_if(work.issn)
            )
            if if_val:
                journal_line += f" (IF: {if_val:.1f}, OpenAlex)"
            click.echo(journal_line)
            if abstracts and work.abstract:
                abstract = _strip_xml_tags(work.abstract)[:500]
                click.echo(
                    f"   Abstract: {abstract}{'...' if len(work.abstract) > 500 else ''}"
                )
            click.echo()


@click.command("search-by-doi", context_settings=CONTEXT_SETTINGS)
@click.argument("doi")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--citation", is_flag=True, help="Output as citation")
@click.option(
    "--save",
    "save_path",
    type=click.Path(),
    help="Save result to file",
)
@click.option(
    "--format",
    "save_format",
    type=click.Choice(["text", "json", "bibtex"]),
    default="json",
    help="Output format for --save (default: json)",
)
def search_by_doi_cmd(
    doi: str,
    as_json: bool,
    citation: bool,
    save_path: Optional[str],
    save_format: str,
):
    """Search for a work by DOI.

    \b
    Example:
      $ crossref-local search-by-doi 10.1126/science.aax0758
      $ crossref-local search-by-doi 10.1038/nature12373 --json
      $ crossref-local search-by-doi 10.1038/nature12373 --citation
    """
    try:
        work = get(doi)
    except ConnectionError as e:
        click.echo(f"Error: {e}", err=True)
        click.echo("\nRun 'crossref-local status' to check configuration.", err=True)
        sys.exit(1)

    if work is None:
        click.echo(f"DOI not found: {doi}", err=True)
        sys.exit(1)

    # Save to file if requested
    if save_path:
        try:
            saved = _save(work, save_path, format=save_format)
            click.secho(f"Saved to {saved}", fg="green", err=True)
        except Exception as e:
            click.secho(f"Error saving: {e}", fg="red", err=True)
            sys.exit(1)

    if as_json:
        click.echo(json.dumps(work.to_dict(), indent=2))
    elif citation:
        click.echo(work.citation())
    else:
        click.echo(f"Title: {work.title}")
        click.echo(f"Authors: {', '.join(work.authors)}")
        click.echo(f"Year: {work.year}")
        click.echo(f"Journal: {work.journal}")
        click.echo(f"DOI: {work.doi}")
        if work.citation_count:
            click.echo(f"Citations: {work.citation_count}")
