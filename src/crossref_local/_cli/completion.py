"""Shell completion drop-in for the crossref-local CLI.

``crossref-local completion install`` writes a ready-to-source completion
script to the fleet drop-in file::

    $SCITEX_DIR/crossref-local/runtime/completion/crossref-local

(``$SCITEX_DIR`` defaults to ``~/.scitex``), then prints that path. The
install never touches shell rc files (``~/.bashrc``, ``~/.zshrc``);
activate it by sourcing the printed path from your rc once::

    echo 'source ~/.scitex/crossref-local/runtime/completion/crossref-local' >> ~/.bashrc
"""

import scitex_logging as slogging
import os
import tempfile
from pathlib import Path

import click
from click.shell_completion import BashComplete, FishComplete, ZshComplete

PROG_NAME = "crossref-local"

logger = slogging.getLogger(__name__)

_COMPLETE_VAR = "_" + PROG_NAME.upper().replace("-", "_") + "_COMPLETE"

_COMPLETION_CLASSES = {
    "bash": BashComplete,
    "zsh": ZshComplete,
    "fish": FishComplete,
}

_VALID_SHELLS = tuple(_COMPLETION_CLASSES)


def _pkg_short(prog_name: str = PROG_NAME) -> str:
    """Strip a leading ``scitex-`` prefix (fleet path convention)."""
    if prog_name.startswith("scitex-"):
        return prog_name[len("scitex-") :]
    return prog_name


def _scitex_dir() -> Path:
    """Resolve ``$SCITEX_DIR`` (default ``~/.scitex``), read at call time."""
    return Path(os.environ.get("SCITEX_DIR", os.path.expanduser("~/.scitex")))


def dropin_path(prog_name: str = PROG_NAME) -> Path:
    """Return the drop-in file path (honours ``$SCITEX_DIR`` and ``$HOME``)."""
    return (
        _scitex_dir() / _pkg_short(prog_name) / "runtime" / "completion" / prog_name
    )


def _script_for_shell(shell: str, prog_name: str = PROG_NAME) -> str:
    """Render the click completion script for ``shell`` in-process."""
    try:
        complete_cls = _COMPLETION_CLASSES[shell]
    except KeyError:
        raise ValueError(f"Unsupported shell: {shell}") from None
    return complete_cls(None, {}, prog_name, _COMPLETE_VAR).source()


def _detect_shell() -> str:
    """Detect current shell from $SHELL environment variable."""
    shell_path = os.environ.get("SHELL", "")
    shell_name = Path(shell_path).name if shell_path else ""

    if shell_name in _COMPLETION_CLASSES:
        return shell_name

    # Fallback to bash
    return "bash"


def _is_installed(prog_name: str = PROG_NAME) -> tuple[bool, Path]:
    """Check whether the drop-in file exists. Returns (installed, path)."""
    path = dropin_path(prog_name)
    return path.is_file(), path


def _install_completion(shell: str, prog_name: str = PROG_NAME) -> Path:
    """Write (or refresh) the drop-in file atomically. Returns its path.

    The write goes to a temp file in the same directory followed by
    :func:`os.replace`, so readers never see a half-written script.
    Re-installing for the same shell yields byte-identical content.
    """
    script = _script_for_shell(shell, prog_name)
    path = dropin_path(prog_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(script)
            if not script.endswith("\n"):
                f.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    logger.debug("Wrote completion drop-in for shell %s to %s", shell, path)
    return path


def _uninstall_completion(prog_name: str = PROG_NAME) -> bool:
    """Remove the drop-in file. Returns True when a file was removed."""
    path = dropin_path(prog_name)
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    logger.debug("Removed completion drop-in at %s", path)
    return True


@click.group("completion", invoke_without_command=True)
@click.pass_context
def completion(ctx):
    """Shell completion commands.

    \b
    Writes a ready-to-source completion script to the drop-in file
    (~/.scitex/crossref-local/runtime/completion/crossref-local)
    without touching your shell rc files. Running without a
    subcommand auto-installs for the detected shell.

    \b
    Examples:
      crossref-local completion install --shell bash   # Write the drop-in file
      crossref-local completion status                 # Check the drop-in file
      crossref-local completion bash                   # Show bash completion script
    """
    if ctx.invoked_subcommand is None:
        # Auto-install for detected shell
        shell = _detect_shell()
        click.echo(f"Detected shell: {shell}")

        path = _install_completion(shell)
        click.echo(f"[OK] Completion written to {path}")
        click.echo(f"\nActivate it with: source {path}")


@completion.command("install")
@click.option(
    "--shell",
    type=click.Choice(["bash", "zsh", "fish"]),
    default=None,
    help="Shell to install completion for (default: auto-detect)",
)
@click.option(
    "--yes",
    "-y",
    is_flag=True,
    default=False,
    help="Proceed without prompting (install is non-interactive).",
)
def install_cmd(shell: str | None, yes: bool):
    """Write the completion drop-in file and print its path."""
    del yes  # accepted for scripted use; install never prompts
    if shell is None:
        shell = _detect_shell()
        click.echo(f"Detected shell: {shell}")

    path = _install_completion(shell)
    click.echo(f"[OK] Completion written to {path}")
    click.echo(f"\nActivate it with: source {path}")


@completion.command("uninstall")
def uninstall_cmd():
    """Remove the completion drop-in file."""
    removed = _uninstall_completion()
    path = dropin_path()
    if removed:
        click.echo(f"[OK] Removed {path}")
    else:
        click.echo(f"Not installed (no drop-in file at {path})")


@completion.command("status")
def status_cmd():
    """Check the completion drop-in file status."""
    installed, path = _is_installed()
    current_shell = _detect_shell()

    click.echo(f"{PROG_NAME} Shell Completion Status")
    click.echo("=" * 40)
    click.echo(f"Current shell: {current_shell}")
    click.echo(f"Drop-in file: {path}")
    click.echo()
    if installed:
        click.echo(f"  [x] installed ({path.stat().st_size} bytes)")
        click.echo(f"\nActivate it with: source {path}")
    else:
        click.echo("  [ ] not installed")
        click.echo(f"\nInstall it with: {PROG_NAME} completion install")


@completion.command("bash")
def bash_cmd():
    """Show bash completion script."""
    click.echo(_script_for_shell("bash").strip())


@completion.command("zsh")
def zsh_cmd():
    """Show zsh completion script."""
    click.echo(_script_for_shell("zsh").strip())


@completion.command("fish")
def fish_cmd():
    """Show fish completion script."""
    click.echo(_script_for_shell("fish").strip())


def register_completion_commands(cli_group):
    """Register completion commands with the main CLI group."""
    cli_group.add_command(completion)
