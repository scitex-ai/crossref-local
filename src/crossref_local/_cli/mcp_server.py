"""MCP server for CrossRef Local - Claude integration.

This server exposes crossref-local functionality as MCP tools,
enabling Claude Desktop and other MCP clients to search academic papers.

Usage:
    crossref-local serve                    # stdio (Claude Desktop)
    crossref-local serve -t http --port 8082  # HTTP transport
    crossref-local-mcp                      # Direct entry point
"""

import json

try:
    from fastmcp import FastMCP
except ImportError:  # fastmcp absent — the [mcp]-gated MCP capability only
    FastMCP = None  # type: ignore[assignment]

MCP_AVAILABLE = FastMCP is not None
MCP_EXTRA_HINT = "pip install 'crossref-local[mcp]'"


from .. import (
    get as _get,
    info as _info,
    search as _search,
)

# Initialize MCP server (None without fastmcp; tools register as plain
# functions and run_server refuses with the install hint).
mcp = (
    FastMCP(
        name="crossref-local",
        instructions="Local CrossRef database with 167M+ works and full-text search. "
        "Use search to find papers, search_by_doi for DOI lookup, enrich_dois to add "
        "citation counts and references, and status for stats.",
    )
    if MCP_AVAILABLE
    else None
)


def search(
    query: str,
    limit: int = 10,
    offset: int = 0,
    with_abstracts: bool = False,
    save_path: str | None = None,
    save_format: str = "json",
) -> str:
    """Search for academic works by title, abstract, or authors.

    Uses FTS5 full-text search index for fast searching across 167M+ papers.
    Supports FTS5 query syntax: AND, OR, NOT, "exact phrases".

    Args:
        query: Search query (e.g., "machine learning", "CRISPR", "neural network AND hippocampus")
        limit: Maximum number of results to return (default: 10)
        offset: Skip first N results for pagination (default: 0)
        with_abstracts: Include abstracts in results (default: False)
        save_path: Optional file path to save results (e.g., "results.json", "papers.bib")
        save_format: Output format for save_path: "text", "json", or "bibtex" (default: "json")

    Returns:
        JSON string with search results including total count and matching works.

    Examples:
        search("machine learning")
        search("CRISPR", limit=20)
        search("neural network AND memory", with_abstracts=True)
        search("epilepsy", save_path="epilepsy.bib", save_format="bibtex")
    """
    results = _search(query, limit=limit, offset=offset)

    # Save to file if requested
    saved_path = None
    if save_path:
        from .._core.export import save as _save

        try:
            saved_path = _save(
                results, save_path, format=save_format, include_abstract=with_abstracts
            )
        except Exception as e:
            return json.dumps({"error": f"Failed to save: {e}"})

    works_data = []
    for work in results.works:
        work_dict = {
            "doi": work.doi,
            "title": work.title,
            "authors": work.authors,
            "year": work.year,
            "journal": work.journal,
        }
        if with_abstracts and work.abstract:
            work_dict["abstract"] = work.abstract
        works_data.append(work_dict)

    result = {
        "query": results.query,
        "total": results.total,
        "returned": len(works_data),
        "elapsed_ms": round(results.elapsed_ms, 2),
        "works": works_data,
    }

    if saved_path:
        result["saved_to"] = saved_path

    return json.dumps(result, indent=2)


def search_by_doi(
    doi: str,
    as_citation: bool = False,
    save_path: str | None = None,
    save_format: str = "json",
) -> str:
    """Get detailed information about a work by DOI.

    Args:
        doi: Digital Object Identifier (e.g., "10.1038/nature12373")
        as_citation: Return formatted citation instead of full metadata
        save_path: Optional file path to save result (e.g., "paper.json", "paper.bib")
        save_format: Output format for save_path: "text", "json", or "bibtex" (default: "json")

    Returns:
        JSON string with work metadata, or formatted citation string.

    Examples:
        search_by_doi("10.1038/nature12373")
        search_by_doi("10.1126/science.aax0758", as_citation=True)
        search_by_doi("10.1038/nature12373", save_path="paper.bib", save_format="bibtex")
    """
    work = _get(doi)

    if work is None:
        return json.dumps({"error": f"DOI not found: {doi}"})

    # Save to file if requested
    saved_path = None
    if save_path:
        from .._core.export import save as _save

        try:
            saved_path = _save(work, save_path, format=save_format)
        except Exception as e:
            return json.dumps({"error": f"Failed to save: {e}"})

    if as_citation:
        result = work.citation()
        if saved_path:
            result += f"\n\n(Saved to: {saved_path})"
        return result

    result = work.to_dict()
    if saved_path:
        result["saved_to"] = saved_path

    return json.dumps(result, indent=2)


def status() -> str:
    """Report local CrossRef database status — path, work count (~167M), FTS5 index size, citation-graph edge count, and access mode (DB vs HTTP). Use when the user asks "is the CrossRef db ready?", "how many papers do I have?", "check crossref-local status", or before running a search to confirm the db is usable.

    Returns:
        JSON string with database path, work count, FTS index count, and citation count.
    """
    db_info = _info()
    return json.dumps(db_info, indent=2)


def enrich_dois(dois: list[str]) -> str:
    """Enrich DOIs with full metadata including citation counts and references.

    Use this after search() to get detailed metadata for papers.
    The search() tool returns basic info (title, authors, year, journal).
    This tool adds: citation_count, references, volume, issue, publisher, etc.

    Typical workflow:
    1. search("epilepsy seizure prediction") -> get DOIs
    2. enrich_dois([doi1, doi2, ...]) -> get full metadata

    Args:
        dois: List of DOIs to enrich (e.g., ["10.1038/nature12373", "10.1126/science.aax0758"])

    Returns:
        JSON string with enriched works including citation_count and references.

    Examples:
        enrich_dois(["10.1038/nature12373"])
        enrich_dois(["10.1038/s41467-017-02577-y", "10.1093/brain/aww019"])
    """
    from .. import get_many as _get_many

    works = _get_many(dois)

    works_data = []
    for work in works:
        works_data.append(work.to_dict())

    return json.dumps(
        {
            "requested": len(dois),
            "found": len(works_data),
            "works": works_data,
        },
        indent=2,
    )


def check_citations(
    identifiers: list[str],
    validate_metadata: bool = True,
    suggest_enrichment: bool = True,
) -> str:
    """Check citations against the local CrossRef database.

    Validates whether DOIs exist in the database and checks metadata completeness.

    Args:
        identifiers: List of DOIs to check
        validate_metadata: Check for incomplete metadata (default: True)
        suggest_enrichment: Suggest metadata improvements (default: True)

    Returns:
        JSON with summary (total, found, missing, with_issues) and per-entry details.
    """
    from .._core.checker import check_citations as _check

    result = _check(identifiers, validate_metadata, suggest_enrichment)
    return json.dumps(result.to_dict(), indent=2)


def check_bibtex_file(
    file_path: str, validate_metadata: bool = True, suggest_enrichment: bool = True
) -> str:
    """Check all citations in a BibTeX file against the local database.

    Args:
        file_path: Absolute path to BibTeX file
        validate_metadata: Check for incomplete metadata
        suggest_enrichment: Suggest metadata improvements

    Returns:
        JSON with summary and per-entry details including source_key from BibTeX.
    """
    from .._core.checker import check_bibtex as _check

    result = _check(file_path, validate_metadata, suggest_enrichment)
    return json.dumps(result.to_dict(), indent=2)


def cache_create(
    name: str,
    query: str,
    limit: int = 1000,
) -> str:
    """Create a paper cache from search query.

    Fetches full metadata for papers matching query and saves to disk cache.
    Use this to build a reusable paper collection for a research topic.

    Args:
        name: Cache name (e.g., "epilepsy", "alzheimers")
        query: FTS search query
        limit: Max papers to cache (default: 1000)

    Returns:
        JSON with cache info (path, paper count, size)

    Example:
        cache_create("epilepsy", "epilepsy seizure prediction", limit=500)
    """
    from .. import cache

    info = cache.create(name, query=query, limit=limit)
    return json.dumps(info.to_dict(), indent=2)


def cache_query(
    name: str,
    fields: list[str] | None = None,
    include_abstract: bool = False,
    include_references: bool = False,
    include_citations: bool = False,
    year_min: int | None = None,
    year_max: int | None = None,
    journal: str | None = None,
    limit: int | None = None,
) -> str:
    """Query cached papers with field filtering.

    Returns minimal data to reduce context usage. Specify only fields needed.

    Args:
        name: Cache name
        fields: Explicit field list (e.g., ["doi", "title", "year"])
        include_abstract: Include abstract (default: False)
        include_references: Include references list (default: False)
        include_citations: Include citation_count (default: False)
        year_min: Filter by minimum year
        year_max: Filter by maximum year
        journal: Filter by journal name (substring match)
        limit: Max results to return

    Returns:
        JSON array of filtered papers

    Examples:
        cache_query("epilepsy", fields=["doi", "title", "year"])
        cache_query("epilepsy", year_min=2020, include_citations=True, limit=50)
    """
    from .. import cache

    papers = cache.query(
        name,
        fields=fields,
        include_abstract=include_abstract,
        include_references=include_references,
        include_citations=include_citations,
        year_min=year_min,
        year_max=year_max,
        journal=journal,
        limit=limit,
    )
    return json.dumps({"count": len(papers), "papers": papers}, indent=2)


def cache_stats(name: str) -> str:
    """Get cache statistics.

    Returns year distribution, top journals, citation stats without loading full data.

    Args:
        name: Cache name

    Returns:
        JSON with statistics (paper_count, year_range, top_journals, etc.)
    """
    from .. import cache

    stats = cache.stats(name)
    return json.dumps(stats, indent=2)


def cache_list() -> str:
    """List all available caches.

    Returns:
        JSON array of cache info (name, path, paper_count, size)
    """
    from .. import cache

    caches = cache.list_caches()
    return json.dumps([c.to_dict() for c in caches], indent=2)


def cache_top_cited(
    name: str,
    n: int = 20,
    year_min: int | None = None,
    year_max: int | None = None,
) -> str:
    """Get top cited papers from cache.

    Args:
        name: Cache name
        n: Number of papers to return
        year_min: Filter by minimum year
        year_max: Filter by maximum year

    Returns:
        JSON array of top cited papers
    """
    from .._cache.viz import get_top_cited

    papers = get_top_cited(name, n=n, year_min=year_min, year_max=year_max)
    return json.dumps(papers, indent=2)


def cache_citation_summary(name: str) -> str:
    """Get citation statistics for cached papers.

    Returns mean, median, max citations and counts of highly cited papers.

    Args:
        name: Cache name

    Returns:
        JSON with citation statistics
    """
    from .._cache.viz import get_citation_summary

    summary = get_citation_summary(name)
    return json.dumps(summary, indent=2)


def cache_plot_scatter(
    name: str,
    output: str,
    top_n: int = 10,
) -> str:
    """Generate year vs citations scatter plot.

    Saves plot to file and returns top cited papers.

    Args:
        name: Cache name
        output: Output file path (png/pdf/svg)
        top_n: Number of top papers to label on plot

    Returns:
        JSON with output path and top papers list
    """
    from .._cache.viz import plot_year_citations

    result = plot_year_citations(name, output=output, top_n=top_n)
    return json.dumps(result, indent=2)


def cache_plot_network(
    name: str,
    output: str,
    max_nodes: int = 100,
) -> str:
    """Generate citation network visualization.

    Creates interactive HTML graph showing citation relationships.

    Args:
        name: Cache name
        output: Output HTML file path
        max_nodes: Maximum papers to include

    Returns:
        JSON with network stats
    """
    from .._cache.viz import plot_citation_network

    result = plot_citation_network(name, output=output, max_nodes=max_nodes)
    return json.dumps(result, indent=2)


def cache_export(
    name: str,
    output_path: str,
    format: str = "json",
    fields: list[str] | None = None,
) -> str:
    """Export cache to file.

    Args:
        name: Cache name
        output_path: Output file path
        format: Export format (json, csv, bibtex, dois)
        fields: Fields to include (for json/csv)

    Returns:
        JSON with output path
    """
    from .. import cache

    path = cache.export(name, output_path, format=format, fields=fields)
    return json.dumps({"exported": path, "format": format})


# §5 — skills introspection (audit-mcp-tools)


def crossref_local_skills_list() -> str:
    """List the names of every skill page shipped by crossref-local.

    Returns
    -------
        JSON string with `{"success": true, "package": "crossref-local",
        "skills": ["01_configuration", ...]}`.
    """
    from pathlib import Path

    try:
        skills_dir = Path(__file__).resolve().parents[1] / "_skills" / "crossref-local"
        names = sorted(p.stem for p in skills_dir.glob("*.md") if p.name != "SKILL.md")
        return json.dumps(
            {"success": True, "package": "crossref-local", "skills": names},
            indent=2,
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


def crossref_local_skills_get(name: str) -> str:
    """Fetch the full Markdown content of one crossref-local skill page.

    Args:
        name: Skill page name without `.md`, e.g. `01_configuration`.

    Returns
    -------
        JSON string with `{"success": true, "package": "crossref-local",
        "name": <name>, "content": <markdown>}`, or an error envelope.
    """
    from pathlib import Path

    try:
        skills_dir = Path(__file__).resolve().parents[1] / "_skills" / "crossref-local"
        target = skills_dir / f"{name}.md"
        if not target.exists():
            available = sorted(
                p.stem for p in skills_dir.glob("*.md") if p.name != "SKILL.md"
            )
            return json.dumps(
                {
                    "success": False,
                    "error": f"unknown skill {name!r}; available: {available}",
                },
                indent=2,
            )
        return json.dumps(
            {
                "success": True,
                "package": "crossref-local",
                "name": name,
                "content": target.read_text(encoding="utf-8"),
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, indent=2)


def _register_tools() -> None:
    """Register every tool function against the FastMCP server.

    A no-op without fastmcp: there is no server to register against.
    Explicit names preserve the prior ``@mcp.tool(name=...)`` decorators;
    the rest derive from the function names as before.
    """
    if mcp is None:
        return
    mcp.tool(name="search_works")(search)
    mcp.tool()(search_by_doi)
    mcp.tool(name="get_status")(status)
    mcp.tool()(enrich_dois)
    mcp.tool()(check_citations)
    mcp.tool(name="check_bibtex")(check_bibtex_file)
    mcp.tool()(cache_create)
    mcp.tool()(cache_query)
    mcp.tool()(cache_stats)
    mcp.tool()(cache_list)
    mcp.tool()(cache_top_cited)
    mcp.tool()(cache_citation_summary)
    mcp.tool()(cache_plot_scatter)
    mcp.tool()(cache_plot_network)
    mcp.tool()(cache_export)
    mcp.tool()(crossref_local_skills_list)
    mcp.tool()(crossref_local_skills_get)


_register_tools()


def run_server(
    transport: str = "stdio",
    host: str = "localhost",
    port: int = 8082,
    force: bool = False,
) -> None:
    """Run the MCP server.

    Args:
        transport: Transport protocol ("stdio", "sse", or "http")
        host: Host for HTTP/SSE transport
        port: Port for HTTP/SSE transport
        force: Kill existing process using the port if any (http/sse only)
    """
    # Handle force flag for http/sse transports
    if force and transport in ("http", "sse"):
        from .utils import kill_process_on_port

        kill_process_on_port(port)

    if mcp is None:
        raise RuntimeError(
            "fastmcp is not installed, so the crossref-local MCP server is "
            f"unavailable. Install it with: {MCP_EXTRA_HINT}"
        )
    if transport == "stdio":
        mcp.run(transport="stdio")
    elif transport == "sse":
        mcp.run(transport="sse", host=host, port=port)
    elif transport == "http":
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        raise ValueError(f"Unknown transport: {transport}")


def main():
    """Entry point for crossref-local-mcp command."""
    run_server(transport="stdio")


if __name__ == "__main__":
    main()
