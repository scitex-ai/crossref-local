#!/usr/bin/env python3
"""``sync-stats`` command for the crossref-local CLI.

Thin Click wrapper over :func:`crossref_local._core.stats.refresh_stats`
(the Python API keeps the ``refresh_stats`` name — the audit's verb
catalog governs CLI verbs only). Kept in its own module (mirroring
``update.py``) to honour the line limit on ``cli.py``.

Renamed from ``refresh-stats`` in 0.8.1 (audit §1f: 'refresh' is a
non-canonical synonym — canonical is ``sync-<object>``); the old
spelling stays as a hidden warn-phase deprecated alias (see
``_cli/deprecations.py``). Help is spec-built (CliHelp, audit §4b) with
a free-form fallback for scitex-dev versions without the helper.
"""

import sys
import time

import click

_HELP_SUMMARY = "Recompute exact table counts into the db_stats cache."
_HELP_DESCRIPTION = (
    "Runs COUNT(*) on works / works_fts / citations (slow — ~17.5 s on "
    "the production database) and writes the results to the db_stats "
    'table, so info() and the HTTP /info endpoint report exact counts '
    'instantly (counts_source: "exact"). Without this cache they fall '
    "back to fast MAX(rowid) estimates.",
    "Requires write access to the database. Run after ingest/rebuild "
    "(`update-db` runs it automatically on success).",
)
_HELP_EXAMPLES = (
    ("{prog} sync-stats --yes", "Recompute exact counts into the cache."),
    ("{prog} sync-stats --yes --db /path/to/crossref.db", "Explicit DB path."),
    ("{prog} sync-stats --dry-run", "Show current cache state; no writes."),
    ("{prog} sync-stats --yes --json", "Machine-readable output."),
)

try:
    from scitex_dev.ecosystem import CliHelp, Example, SpecCommand

    _COMMAND_KWARGS = {
        "cls": SpecCommand,
        "help_spec": CliHelp(
            summary=_HELP_SUMMARY,
            description=_HELP_DESCRIPTION,
            examples=tuple(Example(cmd, note) for cmd, note in _HELP_EXAMPLES),
            exit_codes=((0, "success"), (1, "database missing or not writable"),
                        (2, "refused: --yes missing on a mutating run")),
        ),
    }
except ImportError:  # pragma: no cover — old scitex-dev without help_spec
    _COMMAND_KWARGS = {
        "help": "\n\n".join((_HELP_SUMMARY,) + _HELP_DESCRIPTION),
    }


@click.command("sync-stats", **_COMMAND_KWARGS)
@click.option(
    "--db",
    "db_path",
    type=click.Path(),
    default=None,
    help="Database path override (else use auto-discovery).",
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the current cache/estimate state; write nothing.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Required for a real run (non-interactive CLI contract).",
)
def sync_stats_cmd(db_path, as_json, dry_run, yes):
    """Recompute exact table counts into the ``db_stats`` cache."""
    import json as json_module

    from .._core.stats import refresh_stats

    if dry_run:
        # Report the CURRENT state (cache or estimates) — no COUNT(*),
        # no writes.
        from .._core.db import Database
        from .._core.stats import get_counts

        try:
            database = Database(db_path)
        except FileNotFoundError as e:
            click.secho(f"Error: {e}", fg="red", err=True)
            sys.exit(1)
        try:
            counts = get_counts(database)
        finally:
            database.close()
        if as_json:
            click.echo(json_module.dumps(counts, indent=2))
            return
        click.secho(
            "[dry-run] would COUNT(*) works / works_fts / citations and "
            "write db_stats; current state:",
            fg="yellow",
        )
        click.echo(f"  Works:       {counts['works']:,}")
        click.echo(f"  FTS indexed: {counts['fts_indexed']:,}")
        click.echo(f"  Citations:   {counts['citations']:,}")
        click.echo(f"  Source:      {counts['counts_source']}")
        return

    if not yes:
        click.secho(
            "Refusing to recompute db_stats without --yes/-y "
            "(non-interactive CLI contract, audit §2). "
            "Re-run with -y/--yes, or preview with --dry-run.",
            fg="red",
            err=True,
        )
        sys.exit(2)

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
