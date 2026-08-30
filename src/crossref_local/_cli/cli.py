"""Command-line interface for crossref_local."""

import sys

import click
from rich.console import Console

from .. import __version__, info

console = Console()


class AliasedGroup(click.Group):
    """Click group that supports command aliases."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases = {}

    def command(self, *args, aliases=None, **kwargs):
        """Decorator that registers aliases for commands."""

        def decorator(f):
            cmd = super(AliasedGroup, self).command(*args, **kwargs)(f)
            if aliases:
                for alias in aliases:
                    self._aliases[alias] = cmd.name
            return cmd

        return decorator

    def get_command(self, ctx, cmd_name):
        """Resolve aliases to actual commands."""
        cmd_name = self._aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)

    def format_commands(self, ctx, formatter):
        """Format commands with aliases shown inline."""
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue

            # Find aliases for this command
            aliases = [a for a, c in self._aliases.items() if c == subcommand]
            if aliases:
                name = f"{subcommand} ({', '.join(aliases)})"
            else:
                name = subcommand

            help_text = cmd.get_short_help_str(limit=50)
            commands.append((name, help_text))

        if commands:
            with formatter.section("Commands"):
                formatter.write_dl(commands)


CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


def _print_recursive_help(ctx, param, value):
    """Callback for --help-recursive flag."""
    if not value or ctx.resilient_parsing:
        return

    def _print_command_help(cmd, prefix: str, parent_ctx):
        """Recursively print help for a command and its subcommands."""
        console.print(f"\n[bold cyan]━━━ {prefix} ━━━[/bold cyan]")
        sub_ctx = click.Context(cmd, info_name=prefix.split()[-1], parent=parent_ctx)
        console.print(cmd.get_help(sub_ctx))

        if isinstance(cmd, click.Group):
            for sub_name, sub_cmd in sorted(cmd.commands.items()):
                _print_command_help(sub_cmd, f"{prefix} {sub_name}", sub_ctx)

    # Print main help
    console.print("[bold cyan]━━━ crossref-local ━━━[/bold cyan]")
    console.print(ctx.get_help())

    # Print all subcommands recursively
    for name, cmd in sorted(cli.commands.items()):
        _print_command_help(cmd, f"crossref-local {name}", ctx)

    ctx.exit(0)


@click.group(cls=AliasedGroup, context_settings=CONTEXT_SETTINGS)
@click.help_option("-h", "--help")
@click.version_option(
    version=__version__, prog_name="crossref-local", message="%(prog)s %(version)s"
)
@click.option(
    "-V",
    "--show-version",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=lambda ctx, _p, v: (click.echo(__version__), ctx.exit(0))
    if v and not ctx.resilient_parsing
    else None,
    help="Show the version and exit.",
)
@click.option("--http", is_flag=True, help="Use HTTP API instead of the local store")
@click.option(
    "--api-url",
    envvar="CROSSREF_LOCAL_API_URL",
    help="API URL for http mode (default: auto-detect)",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Emit machine-readable JSON output (propagated to subcommands).",
)
@click.option(
    "--help-recursive",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_print_recursive_help,
    help="Show help for all commands recursively.",
)
@click.pass_context
def cli(ctx, http: bool, api_url: str, as_json: bool):
    """Local CrossRef corpus with 167M+ works and full-text search.

    Supports both direct store access (db mode) and HTTP API (http mode).

    \b
    Configuration precedence:
      ./config.yaml -> $CROSSREF_LOCAL_CONFIG -> ~/.scitex/crossref-local/runtime/config.yaml -> defaults

    \b
    DB mode (default when a store resolves):
      crossref-local search "machine learning"

    \b
    HTTP mode (connect to API server):
      crossref-local --http search "machine learning"
    """
    from .._core.config import Config

    ctx.ensure_object(dict)
    ctx.obj["as_json"] = as_json

    if api_url:
        Config.set_api_url(api_url)
    elif http:
        Config.set_mode("http")


# Register search commands from search module
from .search import search_by_doi_cmd, search_cmd

cli.add_command(search_cmd)
cli.add_command(search_by_doi_cmd)

# Register check command
from .check import check_cmd

cli.add_command(check_cmd)
# Backward-compat alias: `check` -> `check-citations`
cli._aliases["check"] = check_cmd.name


@cli.command("show-status", aliases=["status"], context_settings=CONTEXT_SETTINGS)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def show_status(as_json):
    """Show status and configuration.

    \b
    Example:
      $ crossref-local show-status
      $ crossref-local show-status --json
      $ crossref-local status              # alias
    """
    import json as json_module
    import os
    import sys

    from .._core.config import Config, DEFAULT_API_URLS, store_available

    if as_json:
        try:
            status_info = info()
        except (FileNotFoundError, ConnectionError, OSError) as e:
            click.echo(
                json_module.dumps({"status": "error", "error": str(e)}, indent=2)
            )
            sys.exit(1)
        click.echo(json_module.dumps(status_info, indent=2))
        return

    click.secho("CrossRef Local - Status", fg="cyan", bold=True)
    click.echo("=" * 50)
    click.echo()

    # Environment variables
    click.echo("Environment Variables:")
    click.echo()
    env_vars = [
        (
            "SCITEX_STORE_DSN",
            "Connection string for the shared store (resolved by scitex-dev)",
        ),
        ("CROSSREF_LOCAL_API_URL", "HTTP API URL (e.g., http://localhost:31291)"),
        ("CROSSREF_LOCAL_MODE", "Force mode: 'db', 'http', or 'auto'"),
        ("CROSSREF_LOCAL_HOST", "Host for relay server (default: 0.0.0.0)"),
        ("CROSSREF_LOCAL_PORT", "Port for relay server (default: 31291)"),
    ]
    #: A DSN can carry a password, and this output gets pasted into bug
    #: reports. Report that it is set; never what it says.
    _REDACTED = {"SCITEX_STORE_DSN"}
    for var_name, description in env_vars:
        value = os.environ.get(var_name)
        if value:
            shown = "(set)" if var_name in _REDACTED else value
            click.echo(f"  {var_name}={shown}")
        else:
            click.echo(f"  {var_name} (not set)")
        click.echo(f"      | {description}")
        click.echo()

    # Store — a credential-free description, never the DSN. Resolution
    # only: this opens no connection, so `show-status` stays instant even
    # when the store is unreachable.
    click.echo("Store:")
    store_found = store_available()
    marker = "[OK]" if store_found else "[ ]"
    click.echo(f"  {marker} {Config.describe_store()}")
    click.echo()

    # API health checks
    click.echo("API Health Checks:")
    api_found = None
    for url in DEFAULT_API_URLS:
        health_url = f"{url}/health"
        click.echo(f"  $ curl {health_url}")
        try:
            import urllib.request

            req = urllib.request.Request(health_url, method="GET")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    data = json_module.loads(resp.read().decode())
                    click.secho(f"    -> {data.get('status', 'ok')}", fg="green")
                    if api_found is None:
                        api_found = url
                else:
                    click.secho(f"    -> HTTP {resp.status}", fg="red")
        except Exception as e:
            click.secho(f"    -> unreachable ({type(e).__name__})", fg="red")
    click.echo()

    def _echo_counts(payload, works_key="works"):
        """Print the three counts, or say they are not known.

        ``counts_source`` of anything but ``"exact"`` means nothing has
        measured the corpus. The counts are zero in that case, and
        printing "Works: 0" would present a number nobody took as a
        measurement — the one thing _core/stats.py refuses to do.
        """
        if payload.get("counts_source") != "exact":
            click.secho(
                "Counts: unavailable — run `crossref-local sync-stats --yes`",
                fg="yellow",
            )
            return
        click.echo(f"Works: {payload.get(works_key, 0):,}")
        click.echo(f"FTS Indexed: {payload.get('fts_indexed', 0):,}")
        click.echo(f"Citations: {payload.get('citations', 0):,}")

    # Corpus info via /info endpoint
    if api_found:
        info_url = f"{api_found}/info"
        click.echo(f"  $ curl {info_url}")
        try:
            req = urllib.request.Request(info_url, method="GET")
            req.add_header("Accept", "application/json")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json_module.loads(resp.read().decode())
                click.secho(f"    -> ok", fg="green")
                _echo_counts(data, works_key="total_papers")
        except Exception:
            click.secho(f"    -> timed out (server may need update)", fg="yellow")
            # Fallback to info() which uses health-first approach
            try:
                _echo_counts(info())
            except Exception:
                pass
    elif store_found:
        try:
            _echo_counts(info())
        except Exception as e:
            click.secho(f"Error: {e}", fg="red", err=True)


# Register MCP subcommand group
from .mcp import mcp

cli.add_command(mcp)

# Register update-db command (extracted to its own module for the line limit)
from .update import update_db_cmd

cli.add_command(update_db_cmd)

# Register sync-stats command (extracted for the same line limit)
from .stats import sync_stats_cmd

cli.add_command(sync_stats_cmd)

# Old spellings (`update`, `refresh-stats`) — hidden warn-phase aliases
# for the 0.8.1 audit renames (see _cli/deprecations.py).
from .deprecations import register_deprecated_aliases

register_deprecated_aliases(cli)


@cli.command("relay", context_settings=CONTEXT_SETTINGS)
@click.option("--host", default=None, envvar="CROSSREF_LOCAL_HOST", help="Host to bind")
@click.option(
    "--port",
    default=None,
    type=int,
    envvar="CROSSREF_LOCAL_PORT",
    help="Port to listen on (default: 31291)",
)
@click.option(
    "--force",
    is_flag=True,
    help="Kill existing process using the port if any",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be started without starting",
)
def relay(host: str, port: int, force: bool, dry_run: bool):
    """Run HTTP relay server for remote corpus access.

    \b
    This runs a FastAPI server that provides full-text search across all
    167M+ papers for hosts with no store of their own.

    \b
    Example:
      crossref-local relay                  # Run on 0.0.0.0:31291
      crossref-local relay --port 8080      # Custom port
      crossref-local relay --force          # Kill existing process if port in use

    \b
    Then connect with http mode:
      crossref-local --http search "CRISPR"
      curl "http://localhost:8333/works?q=CRISPR&limit=10"
    """
    try:
        from .._server import run_server
    except ImportError:
        click.echo(
            "API server requires fastapi and uvicorn. Install with:\n"
            "  pip install fastapi uvicorn",
            err=True,
        )
        sys.exit(1)

    from .._server import DEFAULT_HOST, DEFAULT_PORT

    host = host or DEFAULT_HOST
    port = port or DEFAULT_PORT

    if dry_run:
        click.echo(f"[dry-run] Would start relay server on {host}:{port}")
        click.echo(f"[dry-run] Search endpoint: http://{host}:{port}/works?q=<query>")
        click.echo(f"[dry-run] Docs: http://{host}:{port}/docs")
        return

    # Handle force flag
    if force:
        from .utils import kill_process_on_port

        kill_process_on_port(port)

    click.echo(f"Starting CrossRef Local relay server on {host}:{port}")
    click.echo(f"Search endpoint: http://{host}:{port}/works?q=<query>")
    click.echo(f"Docs: http://{host}:{port}/docs")
    run_server(host=host, port=port)


@cli.command("list-python-apis", context_settings=CONTEXT_SETTINGS)
@click.option(
    "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +doc, -vvv full"
)
@click.option("-d", "--max-depth", type=int, default=5, help="Max recursion depth")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def list_python_apis(verbose, max_depth, as_json):
    """List Python APIs (alias for: scitex introspect api crossref_local).

    \b
    Example:
      $ crossref-local list-python-apis
      $ crossref-local list-python-apis -vv
      $ crossref-local list-python-apis --json
    """
    try:
        from scitex.cli.introspect import api

        ctx = click.Context(api)
        ctx.invoke(
            api,
            dotted_path="crossref_local",
            verbose=verbose,
            max_depth=max_depth,
            as_json=as_json,
        )
    except ImportError:
        # Fallback if scitex not installed
        click.echo("Install scitex for full API introspection:")
        click.echo("  pip install scitex")
        click.echo()
        click.echo("Or use: scitex introspect api crossref_local")


# Register docs and skills subcommands (from scitex-dev). Audit §13:
# self-maintenance commands nest under `dev`, so skills mounts as
# `crossref-local dev skills`; the old top-level `skills` stays as a
# hidden warn-phase deprecated alias.
try:
    from scitex_dev.cli import docs_click_group, skills_click_group

    cli.add_command(docs_click_group(package="crossref-local"))
    _skills_group = skills_click_group(package="crossref-local")
    try:
        from scitex_dev.ecosystem import CliHelp, SpecGroup

        _dev_group = SpecGroup(
            "dev",
            help_spec=CliHelp(
                summary="Package self-maintenance commands (doctrine §13)."
            ),
        )
        _dev_group.add_command(_skills_group)
        cli.add_command(_dev_group)
        # Audit corpus tension: §13 wants `skills` NESTED under `dev`,
        # while §1a REQUIRES a top-level `skills` GROUP whenever the
        # package ships _skills/. Bridge: a second, HIDDEN skills-group
        # instance at top level carrying the Phase-W `_deprecated_alias`
        # metadata (§13's documented escape hatch), so `dev skills` is
        # canonical and old `crossref-local skills ...` keeps working.
        _skills_alias = skills_click_group(package="crossref-local")
        _skills_alias.hidden = True
        _skills_alias._deprecated_alias = {
            "target": "dev skills",
            "remove_in": "0.10",
            "phase": "warn",
        }
        cli.add_command(_skills_alias)
    except ImportError:
        # Old scitex-dev without ecosystem helpers — legacy top-level mount.
        cli.add_command(_skills_group)
except ImportError:
    pass


# Wire canonical install-shell-completion + print-shell-completion
# (§1a — required top-level commands). The helper writes a static
# completion cache file rather than emitting an eval-the-binary line,
# so `source ~/.bashrc` stays microsecond-fast (PS-147).
try:
    from scitex_dev._cli._completion import attach_shell_completion

    attach_shell_completion(cli, prog_name="crossref-local")
except ImportError:
    pass


def main():
    """Entry point for CLI."""
    cli()


# audit §4 — inject version into root --help. `main` is a thin
# wrapper; the click Group is `cli`.
try:
    from importlib.metadata import version as _v

    cli.help = (
        f"crossref-local (v{_v('crossref-local')}) — " + (cli.help or "").lstrip()
    )
except Exception:
    pass


if __name__ == "__main__":
    main()
