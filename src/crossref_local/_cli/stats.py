#!/usr/bin/env python3
"""``refresh-stats`` command for the crossref-local CLI.

Thin Click wrapper over :func:`crossref_local._core.stats.refresh_stats`.
Kept in its own module (mirroring ``update.py``) to honour the line
limit on ``cli.py``.
"""

import sys
import time

import click


@click.command("refresh-stats")
@click.option(
    "--db",
    "db_path",
    type=click.Path(),
    default=None,
    help="Database path override (else use auto-discovery).",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def refresh_stats_cmd(db_path, as_json):
    """Recompute exact table counts into the ``db_stats`` cache.

    Runs COUNT(*) on works / works_fts / citations (slow — ~17.5 s on
    the production database) and writes the results to the ``db_stats``
    table, so ``info()`` and the HTTP ``/info`` endpoint can report
    exact counts instantly (``counts_source: "exact"``). Without this
    cache they fall back to fast MAX(rowid) estimates.

    Requires write access to the database. Run after ingest/rebuild
    (``crossref-local update`` runs it automatically).

    \b
    Example:
      $ crossref-local refresh-stats
      $ crossref-local refresh-stats --db /path/to/crossref.db
      $ crossref-local refresh-stats --json
    """
    import json as json_module

    from .._core.stats import refresh_stats

    started = time.time()
    try:
        counts = refresh_stats(db_path=db_path)
    except FileNotFoundError as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)
    except Exception as e:
        click.secho(
            f"Error: could not refresh stats ({e}). "
            "Is the database writable?",
            fg="red",
            err=True,
        )
        sys.exit(1)
    elapsed = time.time() - started

    if as_json:
        click.echo(json_module.dumps(counts, indent=2))
        return

    click.secho("db_stats cache refreshed (exact counts):", fg="green")
    click.echo(f"  Works:       {counts['works']:,}")
    click.echo(f"  FTS indexed: {counts['fts_indexed']:,}")
    click.echo(f"  Citations:   {counts['citations']:,}")
    click.echo(f"  Computed at: {counts['counts_computed_at']}")
    click.echo(f"  Elapsed:     {elapsed:.1f}s")


# EOF
