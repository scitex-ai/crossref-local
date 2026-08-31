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

The ``--db`` option is gone with the file it named: the corpus lives in
the fleet's shared store, whose target is resolved by scitex-dev. The
``--yes`` / ``--dry-run`` / ``--json`` contract is unchanged, including
the refusal (exit 2) on a mutating run without ``--yes``.
"""

import sys
import time

import click

_HELP_SUMMARY = "Recompute exact collection counts into the corpus-stats cache."
_HELP_DESCRIPTION = (
    "Counts the works, searchable and citations collections exactly and "
    "writes the results to the crossref_corpus_stats collection, so "
    "info() and the HTTP /info endpoint report exact counts instantly "
    '(counts_source: "exact"). Without this cache they report '
    '"unavailable" — the read path never counts, because the store has '
    "no aggregate and counting means reading every record.",
    "Slow by design: it reads each collection in full. Requires write "
    "access to the store. Run after ingest/rebuild (`update-db` runs it "
    "automatically on success).",
)
_HELP_EXAMPLES = (
    ("{prog} sync-stats --yes", "Recompute exact counts into the cache."),
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
            exit_codes=((0, "success"), (1, "store unreachable or not writable"),
                        (2, "refused: --yes missing on a mutating run")),
        ),
    }
except ImportError:  # pragma: no cover — old scitex-dev without help_spec
    _COMMAND_KWARGS = {
        "help": "\n\n".join((_HELP_SUMMARY,) + _HELP_DESCRIPTION),
    }


@click.command("sync-stats", **_COMMAND_KWARGS)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show the current cache state; write nothing.",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Required for a real run (non-interactive CLI contract).",
)
def sync_stats_cmd(as_json, dry_run, yes):
    """Recompute exact counts into the ``crossref_corpus_stats`` cache."""
    import json as json_module

    from .._core.stats import refresh_stats

    if dry_run:
        # Report the CURRENT state — cache only, no counting, no writes.
        from .._core.stats import get_counts

        try:
            counts = get_counts()
        except Exception as e:
            click.secho(f"Error: {e}", fg="red", err=True)
            sys.exit(1)
        if as_json:
            click.echo(json_module.dumps(counts, indent=2))
            return
        click.secho(
            "[dry-run] would count works / searchable / citations and "
            "write crossref_corpus_stats; current state:",
            fg="yellow",
        )
        click.echo(f"  Works:       {counts['works']:,}")
        click.echo(f"  FTS indexed: {counts['fts_indexed']:,}")
        click.echo(f"  Citations:   {counts['citations']:,}")
        click.echo(f"  Source:      {counts['counts_source']}")
        return

    if not yes:
        click.secho(
            "Refusing to recompute crossref_corpus_stats without --yes/-y "
            "(non-interactive CLI contract, audit §2). "
            "Re-run with -y/--yes, or preview with --dry-run.",
            fg="red",
            err=True,
        )
        sys.exit(2)

    started = time.time()
    try:
        counts = refresh_stats()
    except Exception as e:
        click.secho(
            f"Error: could not refresh stats ({e}). "
            "Is the store reachable and writable?",
            fg="red",
            err=True,
        )
        sys.exit(1)
    elapsed = time.time() - started

    if as_json:
        click.echo(json_module.dumps(counts, indent=2))
        return

    click.secho("crossref_corpus_stats cache refreshed (exact counts):", fg="green")
    click.echo(f"  Works:       {counts['works']:,}")
    click.echo(f"  FTS indexed: {counts['fts_indexed']:,}")
    click.echo(f"  Citations:   {counts['citations']:,}")
    click.echo(f"  Computed at: {counts['counts_computed_at']}")
    click.echo(f"  Elapsed:     {elapsed:.1f}s")


# EOF
