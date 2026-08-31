#!/usr/bin/env python3
"""``update-db`` command for the crossref-local CLI.

Thin Click wrapper over ``crossref_local.update`` (which forwards to the
project's differential-update logic). Kept in its own module to mirror
openalex-local's command extraction and honour the line limit on
``cli.py``.

Renamed from bare ``update`` in 0.8.1 (audit §1: a bare transitive verb
at top level needs an object); the old spelling stays as a hidden
warn-phase deprecated alias (see ``_cli/deprecations.py``). Help is
spec-built (CliHelp, audit §4b) with a free-form fallback for scitex-dev
versions without the helper. The interactive ``click.confirm`` gate was
replaced by refuse-without-``--yes`` (audit §2: non-interactive CLI
contract).

The ``--db`` option is gone with the file it named: the corpus lives in
the fleet's shared store, whose target is resolved by scitex-dev. The
``--yes`` / ``--dry-run`` / ``--quiet`` contract is unchanged, including
the refusal (exit 2) on a mutating run without ``--yes``.
"""

import sys

import click

_HELP_SUMMARY = "Incrementally update the local corpus from the CrossRef API."
_HELP_DESCRIPTION = (
    "Fetches works newer than the recorded last sync date from the "
    "CrossRef REST API (deep-paged) and upserts them into the store, "
    "then refreshes the crossref_corpus_stats exact-count cache.",
    "Non-interactive: a real (non --dry-run) run requires --yes/-y and "
    "refuses otherwise (exit 2).",
)
_HELP_EXAMPLES = (
    ("{prog} update-db --yes", "Update since the last recorded sync."),
    ("{prog} update-db --yes --since 2026-03-01", "Explicit start date."),
    ("{prog} update-db --dry-run", "Preview only — no writes."),
    ("{prog} update-db --yes --quiet", "Cron/unattended one-line output."),
)

try:
    from scitex_dev.ecosystem import CliHelp, Example, SpecCommand

    _COMMAND_KWARGS = {
        "cls": SpecCommand,
        "help_spec": CliHelp(
            summary=_HELP_SUMMARY,
            description=_HELP_DESCRIPTION,
            examples=tuple(Example(cmd, note) for cmd, note in _HELP_EXAMPLES),
            exit_codes=((0, "success"), (1, "update failed"),
                        (2, "refused: --yes missing on a mutating run")),
        ),
    }
except ImportError:  # pragma: no cover — old scitex-dev without help_spec
    _COMMAND_KWARGS = {
        "help": "\n\n".join((_HELP_SUMMARY,) + _HELP_DESCRIPTION),
    }


@click.command("update-db", **_COMMAND_KWARGS)
@click.option(
    "--since",
    default=None,
    help="Override start date (YYYY-MM-DD). Default: last recorded sync.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Preview only — no API writes or store changes.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Required for a real run (non-interactive CLI contract).",
)
@click.option(
    "--quiet",
    is_flag=True,
    help="Minimal stdout (for cron).",
)
def update_db_cmd(since, dry_run, yes, quiet):
    """Incrementally update the local corpus from the CrossRef API."""
    from .. import update as _update

    if not dry_run and not yes:
        click.secho(
            "Refusing to update the local store without --yes/-y "
            "(non-interactive CLI contract, audit §2). "
            "Re-run with -y/--yes, or preview with --dry-run.",
            fg="red",
            err=True,
        )
        sys.exit(2)

    try:
        stats = _update(since=since, dry_run=dry_run)
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
