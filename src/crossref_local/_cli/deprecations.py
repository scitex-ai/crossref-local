#!/usr/bin/env python3
"""Phase-W deprecated CLI spellings (audit-driven renames, 0.8.1).

Two commands were renamed to satisfy the CLI audit:

* ``update`` -> ``update-db`` (§1: bare transitive verb at top level
  needs an object)
* ``refresh-stats`` -> ``sync-stats`` (§1f: 'refresh' is a
  non-canonical synonym of ``sync-<object>``)

The old spellings keep working as HIDDEN warn-phase aliases: preferred
path is :func:`scitex_dev.ecosystem.deprecated_alias` (carries the
``_deprecated_alias`` metadata the static auditor §5 verifies); when the
installed scitex-dev predates that helper, a thin hidden forwarding
command emits a ``DeprecationWarning`` instead.
"""

import warnings

import click

_REMOVE_IN = "0.10"


def register_deprecated_aliases(cli: click.Group) -> None:
    """Register ``update`` and ``refresh-stats`` warn-phase aliases."""
    from .stats import sync_stats_cmd
    from .update import update_db_cmd

    pairs = (
        ("update", update_db_cmd),
        ("refresh-stats", sync_stats_cmd),
    )
    try:
        from scitex_dev.ecosystem import deprecated_alias
    except ImportError:  # pragma: no cover — old scitex-dev
        for old_name, target in pairs:
            _fallback_alias(cli, old_name, target)
        return
    for old_name, target in pairs:
        deprecated_alias(cli, old_name, target=target, remove_in=_REMOVE_IN)


def _fallback_alias(
    cli: click.Group, old_name: str, target: click.Command
) -> None:  # pragma: no cover — only without scitex_dev.ecosystem
    """Thin hidden forwarder emitting a DeprecationWarning."""

    @click.pass_context
    def _forward(ctx, **kwargs):
        warnings.warn(
            f"'{old_name}' is deprecated; use '{target.name}' "
            f"(removed in {_REMOVE_IN})",
            DeprecationWarning,
            stacklevel=2,
        )
        click.secho(
            f"deprecated: '{old_name}' — use '{target.name}'",
            fg="yellow",
            err=True,
        )
        ctx.forward(target)

    alias = click.Command(
        old_name,
        params=list(target.params),
        callback=_forward,
        hidden=True,
        help=f"Deprecated alias for '{target.name}'.",
    )
    cli.add_command(alias)


# EOF
