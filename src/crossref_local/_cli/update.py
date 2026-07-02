#!/usr/bin/env python3
"""Update command for crossref-local CLI.

Thin Click wrapper over ``crossref_local.update`` (which forwards to the
project's differential-update logic). Kept in its own module to mirror
openalex-local's ``update`` command extraction and honour the line limit
on ``cli.py``.
"""

import sys

import click


@click.command("update")
@click.option(
    "--db",
    "db_path",
    type=click.Path(),
    default=None,
    help="Database path override (else use auto-discovery).",
)
@click.option(
    "--since",
    default=None,
    help="Override start date (YYYY-MM-DD). Default: last recorded sync.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview only — no API writes or database changes.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Skip confirmation prompts (for cron/unattended runs).",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Minimal stdout (for cron).",
)
def update_cmd(db_path, since, dry_run, yes, quiet):
    """Incrementally update the local database from the CrossRef API.

    Fetches works newer than the recorded last sync date from the
    CrossRef REST API (deep-paged) and upserts them into the database.

    \b
    Example:
      $ crossref-local update
      $ crossref-local update --since 2026-03-01
      $ crossref-local update --dry-run
      $ crossref-local update --yes --quiet   # cron/unattended
    """
    from .. import update as _update

    if not dry_run and not yes:
        target = db_path or "the auto-discovered database"
        if not click.confirm(
            f"Run incremental update against {target}?", default=True
        ):
            click.secho("Aborted.", fg="yellow", err=True)
            sys.exit(1)

    try:
        stats = _update(db_path=db_path, since=since, dry_run=dry_run)
    except Exception as e:
        click.secho(f"Error: {e}", fg="red", err=True)
        sys.exit(1)

    upserted = stats.get("records_upserted", 0)
    last_sync = stats.get("last_sync_date", since or "unchanged")

    if stats.get("dry_run"):
        if not quiet:
            click.secho(
                f"[dry-run] {upserted:,} works would be upserted; "
                "no changes made.",
                fg="yellow",
            )
        return

    if quiet:
        click.echo(f"{upserted} {last_sync}")
    else:
        click.secho(
            f"Update complete: {upserted:,} records upserted; "
            f"last_sync_date={last_sync}",
            fg="green",
        )


# EOF
