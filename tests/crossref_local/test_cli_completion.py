"""Tests for the completion drop-in contract v1.

``crossref-local completion install`` writes the drop-in file
``$SCITEX_DIR/crossref-local/runtime/completion/crossref-local``
atomically and never touches shell rc files. Install-behaviour tests run
under an isolated temp ``HOME`` (with ``SCITEX_DIR`` unset) so the real
``~/.bashrc`` and ``~/.scitex`` are never touched. No mocks: ``$SHELL``,
``$HOME`` and ``$SCITEX_DIR`` are managed via monkeypatch.
"""

from pathlib import Path as _Path

import pytest
from click.testing import CliRunner

from crossref_local._cli.completion import (
    PROG_NAME,
    _detect_shell,
    _install_completion,
    _is_installed,
    _script_for_shell,
    _uninstall_completion,
    completion,
    dropin_path,
)


@pytest.fixture
def runner():
    """Create CLI test runner."""
    return CliRunner()


@pytest.fixture
def shell_env(monkeypatch):
    """Save/restore ``$SHELL``; returns a setter."""

    def setter(value: str | None) -> None:
        if value is None:
            monkeypatch.delenv("SHELL", raising=False)
        else:
            monkeypatch.setenv("SHELL", value)

    return setter


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Point ``$HOME`` at a tmp dir and unset ``$SCITEX_DIR``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SCITEX_DIR", raising=False)
    return tmp_path


# ---------- _detect_shell ----------


def test_detect_shell_returns_bash_for_bin_bash(shell_env):
    # Arrange
    shell_env("/bin/bash")
    # Act
    detected = _detect_shell()
    # Assert
    assert detected == "bash"


def test_detect_shell_returns_zsh_for_usr_bin_zsh(shell_env):
    # Arrange
    shell_env("/usr/bin/zsh")
    # Act
    detected = _detect_shell()
    # Assert
    assert detected == "zsh"


def test_detect_shell_returns_fish_for_usr_local_bin_fish(shell_env):
    # Arrange
    shell_env("/usr/local/bin/fish")
    # Act
    detected = _detect_shell()
    # Assert
    assert detected == "fish"


def test_detect_shell_falls_back_to_bash_for_unknown_shell(shell_env):
    # Arrange
    shell_env("/bin/unknown")
    # Act
    detected = _detect_shell()
    # Assert
    assert detected == "bash"


def test_detect_shell_falls_back_to_bash_when_env_unset(shell_env):
    # Arrange
    shell_env(None)
    # Act
    detected = _detect_shell()
    # Assert
    assert detected == "bash"


# ---------- drop-in path ----------


def test_dropin_path_defaults_under_home_scitex(isolated_home):
    # Arrange / Act
    path = dropin_path()
    # Assert
    assert path == (
        isolated_home
        / ".scitex"
        / "crossref-local"
        / "runtime"
        / "completion"
        / PROG_NAME
    )


def test_dropin_path_honours_scitex_dir(tmp_path, monkeypatch):
    # Arrange
    monkeypatch.setenv("SCITEX_DIR", str(tmp_path / "custom"))
    # Act
    path = dropin_path()
    # Assert
    assert path == (
        tmp_path / "custom" / "crossref-local" / "runtime" / "completion" / PROG_NAME
    )


# ---------- _script_for_shell ----------


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_script_for_shell_emits_nonempty_script(shell):
    # Arrange / Act
    script = _script_for_shell(shell)
    # Assert
    assert len(script.strip()) > 0


def test_script_for_bash_references_complete_var():
    # Arrange / Act
    script = _script_for_shell("bash")
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in script
    assert PROG_NAME in script


def test_script_for_unknown_shell_raises_value_error():
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="Unsupported shell"):
        _script_for_shell("unknown_shell")


# ---------- _install_completion (isolated HOME) ----------


def test_install_completion_writes_dropin_file(isolated_home):
    # Arrange / Act
    path = _install_completion("bash")
    # Assert
    assert path.is_file()
    assert path == dropin_path()


def test_install_completion_file_holds_bash_script(isolated_home):
    # Arrange / Act
    path = _install_completion("bash")
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in path.read_text()


def test_install_completion_is_idempotent(isolated_home):
    # Arrange
    first = _install_completion("bash")
    before = first.read_bytes()
    # Act
    second = _install_completion("bash")
    # Assert
    assert second == first
    assert second.read_bytes() == before


def test_install_completion_leaves_no_temp_files(isolated_home):
    # Arrange / Act
    _install_completion("bash")
    # Assert
    leftovers = list(dropin_path().parent.glob(f"{PROG_NAME}.*"))
    assert leftovers == []


def test_install_completion_does_not_touch_bashrc(isolated_home):
    # Arrange / Act
    _install_completion("bash")
    # Assert
    assert not (isolated_home / ".bashrc").exists()
    assert not (isolated_home / ".zshrc").exists()


def test_install_completion_rejects_unknown_shell(isolated_home):
    # Arrange / Act / Assert
    with pytest.raises(ValueError, match="Unsupported shell"):
        _install_completion("unknown_shell")


# ---------- _is_installed / _uninstall_completion ----------


def test_is_installed_returns_false_before_install(isolated_home):
    # Arrange / Act
    installed, path = _is_installed()
    # Assert
    assert installed is False
    assert path == dropin_path()


def test_is_installed_returns_true_after_install(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    installed, path = _is_installed()
    # Assert
    assert installed is True
    assert path == dropin_path()


def test_uninstall_completion_removes_dropin_file(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    removed = _uninstall_completion()
    # Assert
    assert removed is True
    assert not dropin_path().exists()


def test_uninstall_completion_reports_false_when_absent(isolated_home):
    # Arrange / Act
    removed = _uninstall_completion()
    # Assert
    assert removed is False


# ---------- completion CLI surface ----------


def test_completion_help_exits_zero(runner):
    # Arrange
    args = ["--help"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert result.exit_code == 0


def test_completion_help_mentions_install_subcommand(runner):
    # Arrange
    args = ["--help"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "install" in result.output


def test_completion_help_mentions_status_subcommand(runner):
    # Arrange
    args = ["--help"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "status" in result.output


def test_completion_help_mentions_fish_subcommand(runner):
    # Arrange
    args = ["--help"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "fish" in result.output


def test_completion_help_references_dropin_file(runner):
    # Arrange
    args = ["--help"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "runtime/completion" in result.output


def test_completion_install_writes_dropin_and_prints_path(
    runner, isolated_home, shell_env
):
    # Arrange
    shell_env("/bin/bash")
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0
    assert str(dropin_path()) in result.output
    assert dropin_path().is_file()


def test_completion_install_accepts_short_yes_flag(runner, isolated_home):
    # Arrange / Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "-y"])
    # Assert
    assert result.exit_code == 0
    assert dropin_path().is_file()


def test_completion_install_never_touches_rc_files(runner, isolated_home):
    # Arrange / Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0
    assert not (isolated_home / ".bashrc").exists()
    assert not (isolated_home / ".zshrc").exists()


def test_completion_install_is_idempotent(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    before = dropin_path().read_bytes()
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0
    assert dropin_path().read_bytes() == before


def test_completion_status_reports_dropin_path_when_missing(
    runner, isolated_home
):
    # Arrange
    args = ["status"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert result.exit_code == 0
    assert str(dropin_path()) in result.output
    assert "not installed" in result.output


def test_completion_status_reports_installed_after_install(
    runner, isolated_home
):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["status"])
    # Assert
    assert result.exit_code == 0
    assert "installed" in result.output


def test_completion_uninstall_removes_dropin_file(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["uninstall"])
    # Assert
    assert result.exit_code == 0
    assert not dropin_path().exists()


def test_completion_uninstall_reports_when_absent(runner, isolated_home):
    # Arrange / Act
    result = runner.invoke(completion, ["uninstall"])
    # Assert
    assert result.exit_code == 0
    assert "Not installed" in result.output


def test_completion_bash_subcommand_emits_complete_var(runner):
    # Arrange
    args = ["bash"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in result.output


def test_completion_zsh_subcommand_emits_complete_var(runner):
    # Arrange
    args = ["zsh"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in result.output


def test_completion_fish_subcommand_emits_complete_var(runner):
    # Arrange
    args = ["fish"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in result.output


def test_completion_group_wired_on_main_cli(isolated_home):
    # Arrange (import here: pulls the full CLI tree)
    import click

    from crossref_local._cli.cli import cli

    # Act
    command = cli.get_command(click.Context(cli), "completion")
    # Assert
    assert isinstance(command, click.Group)
    assert "install" in command.commands


def test_completion_source_has_no_rc_write_path():
    # Arrange
    import crossref_local._cli.completion as completion_module

    # Act
    source = _Path(completion_module.__file__).read_text()
    # Assert: no rc-file write machinery remains (the docstring may still
    # tell users where to add a `source` line themselves).
    assert "SHELL_CONFIGS" not in source
    assert "COMPLETION_MARKER" not in source
    assert "config.fish" not in source
    assert "print(" not in source
