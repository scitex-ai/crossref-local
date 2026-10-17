"""CLI command for citation checking."""

import json
import sys

import click

# NOTE: Rich (Console/Table/Panel) was deliberately removed from this module
# (PS-220): package source must emit through click/scitex-logging, not raw
# print or Rich Console.print. The display below is plain text via
# click.echo — same content, no colors.


@click.command(
    "check-citations", context_settings={"help_option_names": ["-h", "--help"]}
)
@click.argument("input", type=click.Path(), required=False)
@click.option("-d", "--doi", multiple=True, help="Check specific DOI(s)")
@click.option(
    "-f",
    "--format",
    type=click.Choice(["bibtex", "doi-list", "auto"]),
    default="auto",
    help="Input format (default: auto-detect)",
)
@click.option("--no-validate", is_flag=True, help="Skip metadata validation")
@click.option("--no-suggest", is_flag=True, help="Skip enrichment suggestions")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option("--save", "save_path", type=click.Path(), help="Save results to file")
@click.option(
    "--save-format",
    type=click.Choice(["json", "text"]),
    default="json",
    help="Format for --save output",
)
def check_cmd(
    input, doi, format, no_validate, no_suggest, as_json, save_path, save_format
):
    """Check citations against the local CrossRef database.

    \b
    Accepts BibTeX files, DOI list files, or direct DOIs.

    \b
    Examples:
      crossref-local check-citations bibliography.bib
      crossref-local check-citations dois.txt
      crossref-local check-citations -d 10.1038/nature12373
      crossref-local check-citations bibliography.bib --json
      crossref-local check-citations bibliography.bib --save report.json
      crossref-local check bibliography.bib       # alias
    """
    from .._core.checker import check_bibtex, check_citations, check_doi_list

    validate = not no_validate
    suggest = not no_suggest

    if doi:
        result = check_citations(
            list(doi), validate_metadata=validate, suggest_enrichment=suggest
        )
    elif input:
        # Auto-detect format
        if format == "auto":
            format = "bibtex" if input.endswith(".bib") else "doi-list"

        if format == "bibtex":
            result = check_bibtex(
                input, validate_metadata=validate, suggest_enrichment=suggest
            )
        else:
            result = check_doi_list(
                input, validate_metadata=validate, suggest_enrichment=suggest
            )
    else:
        # Read from stdin
        content = sys.stdin.read().strip()
        if not content:
            click.echo(
                "No input provided. Use: crossref-local check FILE or -d DOI", err=True
            )
            sys.exit(1)
        dois = [
            line.strip()
            for line in content.split("\n")
            if line.strip() and not line.startswith("#")
        ]
        result = check_citations(
            dois, validate_metadata=validate, suggest_enrichment=suggest
        )

    if as_json:
        click.echo(json.dumps(result.to_dict(), indent=2))
    else:
        _display_rich(result)

    if save_path:
        result.save(save_path, save_format)
        click.echo(f"\nResults saved to: {save_path}")


def _display_rich(result):
    """Display results as plain text (see module note on Rich removal)."""
    # Summary
    pct_found = result.found / max(result.total, 1) * 100

    click.echo("Citation Check")
    click.echo(f"  Total:       {result.total} citations")
    click.echo(f"  Found:       {result.found} ({pct_found:.1f}%)")
    click.echo(f"  Missing:     {result.missing}")
    if result.with_issues:
        click.echo(f"  With issues: {result.with_issues}")
    click.echo(f"  Time:        {result.elapsed_ms:.1f}ms")

    # Missing
    missing = [e for e in result.entries if not e.found]
    if missing:
        click.echo(f"\nMissing ({len(missing)}):")
        for e in missing:
            click.echo(f"  - {e.identifier[:60]} [{e.source_key or ''}]")
            for issue in e.issues:
                click.echo(f"      {issue}")

    # Issues
    with_issues = [e for e in result.entries if e.found and e.issues]
    if with_issues:
        click.echo(f"\nIssues ({len(with_issues)}):")
        for e in with_issues:
            click.echo(f"  - {e.identifier[:50]} [{e.source_key or ''}]")
            for issue in e.issues:
                click.echo(f"      {issue}")

    if not missing and not with_issues:
        click.echo("All citations found with complete metadata.")
