"""MCP CLI subcommands for crossref_local."""

import sys
import click

from .. import info

CONTEXT_SETTINGS = {"help_option_names": ["-h", "--help"]}


class AliasedGroup(click.Group):
    """Click group that supports command aliases."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._aliases = {}

    def command(self, *args, aliases=None, **kwargs):
        def decorator(f):
            cmd = super(AliasedGroup, self).command(*args, **kwargs)(f)
            if aliases:
                for alias in aliases:
                    self._aliases[alias] = cmd.name
            return cmd

        return decorator

    def get_command(self, ctx, cmd_name):
        cmd_name = self._aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, cmd_name)


@click.group(cls=AliasedGroup, context_settings=CONTEXT_SETTINGS)
def mcp():
    """MCP (Model Context Protocol) server commands.

    \b
    Commands:
      start        - Start the MCP server
      doctor       - Diagnose MCP setup
      installation - Show installation instructions
      list-tools   - List available MCP tools
    """
    pass


@mcp.command("start", context_settings=CONTEXT_SETTINGS)
@click.option(
    "-t",
    "--transport",
    type=click.Choice(["stdio", "sse", "http"]),
    default="stdio",
    help="Transport protocol (http recommended for remote)",
)
@click.option(
    "--host",
    default="localhost",
    envvar="CROSSREF_LOCAL_MCP_HOST",
    help="Host for HTTP/SSE transport",
)
@click.option(
    "--port",
    default=8082,
    type=int,
    envvar="CROSSREF_LOCAL_MCP_PORT",
    help="Port for HTTP/SSE transport",
)
@click.option(
    "--force",
    is_flag=True,
    help="Kill existing process using the port if any (http/sse only)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be started without starting",
)
@click.option(
    "-y",
    "--yes",
    is_flag=True,
    help="Skip interactive confirmations.",
)
def mcp_start(
    transport: str,
    host: str,
    port: int,
    force: bool,
    dry_run: bool,
    yes: bool,
):
    """Start the MCP server.

    \b
    Transports:
      stdio  - Standard I/O (default, for Claude Desktop local)
      http   - Streamable HTTP (recommended for remote/persistent)
      sse    - Server-Sent Events (deprecated as of MCP spec 2025-03-26)

    \b
    Local configuration (stdio):
      {
        "mcpServers": {
          "crossref": {
            "command": "crossref-local",
            "args": ["mcp", "start"]
          }
        }
      }

    \b
    Remote configuration (http):
      # Start server:
      crossref-local mcp start -t http --host 0.0.0.0 --port 8082

      # Client config:
      {
        "mcpServers": {
          "crossref-remote": {
            "url": "http://your-server:8082/mcp"
          }
        }
      }

    \b
    See docs/remote-deployment.md for systemd and Docker setup.

    \b
    Example:
      $ crossref-local mcp start
      $ crossref-local mcp start -t http --host 0.0.0.0 --port 8082
      $ crossref-local mcp start --dry-run
    """
    if dry_run:
        click.echo(f"[dry-run] Would start MCP server with transport={transport}")
        if transport != "stdio":
            click.echo(f"[dry-run] Host: {host}, Port: {port}")
        return

    _ = yes  # accepted for §2 conformance; start has no destructive prompt today
    run_mcp_server(transport, host, port, force)


@mcp.command("doctor", context_settings=CONTEXT_SETTINGS)
def mcp_doctor():
    """Diagnose MCP server setup and dependencies.

    \b
    Example:
      $ crossref-local mcp doctor
    """
    click.echo("MCP Server Diagnostics")
    click.echo("=" * 50)
    click.echo()

    # Check fastmcp
    click.echo("Dependencies:")
    try:
        import fastmcp

        click.echo(
            f"  [OK] fastmcp installed (v{getattr(fastmcp, '__version__', 'unknown')})"
        )
    except ImportError:
        click.echo("  [FAIL] fastmcp not installed")
        click.echo("         Fix: pip install crossref-local[mcp]")
        sys.exit(1)

    click.echo()

    # Check database
    click.echo("Database:")
    try:
        db_info = info()
        click.echo("  [OK] Database accessible")
        click.echo(f"       Works: {db_info.get('works', 0):,}")
        click.echo(f"       FTS indexed: {db_info.get('fts_indexed', 0):,}")
    except Exception as e:
        click.echo(f"  [FAIL] Database error: {e}")
        sys.exit(1)

    click.echo()
    click.echo("All checks passed! MCP server is ready.")
    click.echo()
    click.echo("Start with:")
    click.echo("  crossref-local mcp start              # stdio (Claude Desktop)")
    click.echo("  crossref-local mcp start -t http      # HTTP transport")


@mcp.command(
    "show-installation", aliases=["installation"], context_settings=CONTEXT_SETTINGS
)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mcp_installation(as_json: bool):
    """Show MCP client installation instructions.

    \b
    Example:
      $ crossref-local mcp show-installation
      $ crossref-local mcp show-installation --json
      $ crossref-local mcp installation        # alias
    """
    if as_json:
        import json as _json

        payload = {
            "stdio": {
                "mcpServers": {
                    # No env block: the corpus store is resolved by
                    # scitex-dev (SCITEX_STORE_DSN, else this host's own).
                    "crossref-local": {
                        "command": "crossref-local",
                        "args": ["mcp", "start"],
                    }
                }
            },
            "http": {
                "server_command": "crossref-local mcp start -t http --host 0.0.0.0 --port 8082",
                "client": {
                    "mcpServers": {
                        "crossref-remote": {"url": "http://your-server:8082/mcp"}
                    }
                },
            },
            "see_also": "docs/remote-deployment.md",
        }
        click.echo(_json.dumps(payload, indent=2))
        return

    click.echo("MCP Client Configuration")
    click.echo("=" * 50)
    click.echo()
    click.echo("1. Local (stdio) - Claude Desktop / Claude Code:")
    click.echo()
    click.echo("   Add to your MCP client config (e.g., claude_desktop_config.json):")
    click.echo()
    click.echo("   {")
    click.echo('     "mcpServers": {')
    click.echo('       "crossref-local": {')
    click.echo('         "command": "crossref-local",')
    click.echo('         "args": ["mcp", "start"]')
    click.echo("       }")
    click.echo("     }")
    click.echo("   }")
    click.echo()
    click.echo("   No env block is needed: the corpus store is resolved by")
    click.echo("   scitex-dev (SCITEX_STORE_DSN, else this host's own).")
    click.echo()
    click.echo("2. Remote (HTTP) - Persistent server:")
    click.echo()
    click.echo("   Server side:")
    click.echo("     crossref-local mcp start -t http --host 0.0.0.0 --port 8082")
    click.echo()
    click.echo("   Client config:")
    click.echo("   {")
    click.echo('     "mcpServers": {')
    click.echo('       "crossref-remote": {')
    click.echo('         "url": "http://your-server:8082/mcp"')
    click.echo("       }")
    click.echo("     }")
    click.echo("   }")
    click.echo()
    click.echo("See docs/remote-deployment.md for systemd and Docker setup.")


@mcp.command("list-tools", context_settings=CONTEXT_SETTINGS)
@click.option(
    "-v", "--verbose", count=True, help="Verbosity: -v sig, -vv +desc, -vvv full"
)
@click.option("-c", "--compact", is_flag=True, help="Compact signatures (single line)")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def mcp_list_tools(verbose: int, compact: bool, as_json: bool):
    """List available MCP tools.

    \b
    Verbosity levels:
      (none)  - Tool names only
      -v      - Signatures
      -vv     - Signatures + one-line description
      -vvv    - Signatures + full description

    \b
    Example:
      $ crossref-local mcp list-tools
      $ crossref-local mcp list-tools -vv
      $ crossref-local mcp list-tools --json
    """
    try:
        from .mcp_server import mcp as mcp_server
    except ImportError:
        click.secho("ERROR: Could not import MCP server", fg="red", err=True)
        click.echo("Install with: pip install crossref-local[mcp]")
        raise SystemExit(1)

    # Get tools grouped by prefix
    from scitex_dev import get_tools_sync

    tools_dict = get_tools_sync(mcp_server)
    modules = {}
    for name in sorted(tools_dict.keys()):
        prefix = name.split("_")[0]
        if prefix not in modules:
            modules[prefix] = []
        modules[prefix].append(name)

    if as_json:
        import json

        output = {
            "name": "crossref-local",
            "total": len(tools_dict),
            "modules": {
                mod: {
                    "count": len(tool_list),
                    "tools": [
                        {
                            "name": t,
                            "description": tools_dict[t].description
                            if tools_dict.get(t)
                            else "",
                        }
                        for t in tool_list
                    ],
                }
                for mod, tool_list in modules.items()
            },
        }
        click.echo(json.dumps(output, indent=2))
        return

    total = len(tools_dict)
    click.secho("CrossRef Local MCP", fg="cyan", bold=True)
    click.echo(f"Tools: {total} ({len(modules)} modules)")
    click.echo()

    for mod, tool_list in sorted(modules.items()):
        click.secho(f"{mod}: {len(tool_list)} tools", fg="green", bold=True)
        for tool_name in tool_list:
            tool_obj = tools_dict.get(tool_name)

            if verbose == 0:
                # Names only
                click.echo(f"  {tool_name}")
            elif verbose == 1:
                # Signature
                sig = (
                    _format_signature(tool_obj, multiline=not compact)
                    if tool_obj
                    else f"  {tool_name}"
                )
                click.echo(sig)
            elif verbose == 2:
                # Signature + one-line description
                sig = (
                    _format_signature(tool_obj, multiline=not compact)
                    if tool_obj
                    else f"  {tool_name}"
                )
                click.echo(sig)
                if tool_obj and tool_obj.description:
                    desc = tool_obj.description.split("\n")[0].strip()
                    click.echo(f"    {desc}")
                click.echo()
            else:
                # Signature + full description
                sig = (
                    _format_signature(tool_obj, multiline=not compact)
                    if tool_obj
                    else f"  {tool_name}"
                )
                click.echo(sig)
                if tool_obj and tool_obj.description:
                    for line in tool_obj.description.strip().split("\n"):
                        click.echo(f"    {line}")
                click.echo()
        click.echo()


def _format_signature(tool_obj, multiline: bool = False, indent: str = "  ") -> str:
    """Format tool as Python-like function signature with return type."""
    import inspect

    params = []
    if hasattr(tool_obj, "parameters") and tool_obj.parameters:
        schema = tool_obj.parameters
        props = schema.get("properties", {})
        required = schema.get("required", [])
        for name, pinfo in props.items():
            ptype = pinfo.get("type", "any")
            default = pinfo.get("default")
            if name in required:
                p = f"{click.style(name, fg='white', bold=True)}: {click.style(ptype, fg='cyan')}"
            elif default is not None:
                def_str = repr(default) if len(repr(default)) < 20 else "..."
                p = f"{click.style(name, fg='white', bold=True)}: {click.style(ptype, fg='cyan')} = {click.style(def_str, fg='yellow')}"
            else:
                p = f"{click.style(name, fg='white', bold=True)}: {click.style(ptype, fg='cyan')} = {click.style('None', fg='yellow')}"
            params.append(p)

    # Get return type
    ret_type = ""
    if hasattr(tool_obj, "fn") and tool_obj.fn:
        try:
            sig = inspect.signature(tool_obj.fn)
            if sig.return_annotation != inspect.Parameter.empty:
                ret = sig.return_annotation
                ret_name = ret.__name__ if hasattr(ret, "__name__") else str(ret)
                ret_type = f" -> {click.style(ret_name, fg='magenta')}"
        except Exception:
            pass

    name_s = click.style(tool_obj.name, fg="green", bold=True)
    if multiline and len(params) > 2:
        param_indent = indent + "    "
        params_str = ",\n".join(f"{param_indent}{p}" for p in params)
        return f"{indent}{name_s}(\n{params_str}\n{indent}){ret_type}"
    return f"{indent}{name_s}({', '.join(params)}){ret_type}"


def run_mcp_server(transport: str, host: str, port: int, force: bool = False):
    """Internal function to run MCP server."""
    try:
        from .mcp_server import run_server
    except ImportError:
        click.echo(
            "MCP server requires fastmcp. Install with:\n"
            "  pip install crossref-local[mcp]",
            err=True,
        )
        sys.exit(1)

    run_server(transport=transport, host=host, port=port, force=force)


def register_mcp_commands(cli_group):
    """Register MCP commands with the main CLI group."""
    cli_group.add_command(mcp)
