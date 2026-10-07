"""Tests for the completion drop-in contract v1.

``crossref-local completion install`` writes the drop-in file
``$SCITEX_DIR/crossref-local/runtime/completion/crossref-local``
atomically and never touches shell rc files. Install-behaviour tests run
under an isolated temp ``HOME`` (with ``SCITEX_DIR`` unset) so the real
``~/.bashrc`` and ``~/.scitex`` are never touched. No mocks: ``$SHELL``,
``$HOME`` and ``$SCITEX_DIR`` are managed via yield-based save/restore
fixtures (the rule-sanctioned replacement for ``monkeypatch``).
"""

import os
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
def shell_env():
    """Yield-based save/restore for ``$SHELL``; yields a setter."""
    saved = os.environ.get("SHELL")

    def setter(value: str | None) -> None:
        if value is None:
            os.environ.pop("SHELL", None)
        else:
            os.environ["SHELL"] = value

    try:
        yield setter
    finally:
        if saved is None:
            os.environ.pop("SHELL", None)
        else:
            os.environ["SHELL"] = saved


@pytest.fixture
def isolated_home(tmp_path):
    """Point ``$HOME`` at a tmp dir and unset ``$SCITEX_DIR``."""
    saved_home = os.environ.get("HOME")
    saved_scitex_dir = os.environ.get("SCITEX_DIR")
    os.environ["HOME"] = str(tmp_path)
    os.environ.pop("SCITEX_DIR", None)
    try:
        yield tmp_path
    finally:
        if saved_home is None:
            os.environ.pop("HOME", None)
        else:
            os.environ["HOME"] = saved_home
        if saved_scitex_dir is None:
            os.environ.pop("SCITEX_DIR", None)
        else:
            os.environ["SCITEX_DIR"] = saved_scitex_dir


@pytest.fixture
def scitex_dir_env():
    """Yield-based save/restore for ``$SCITEX_DIR``; yields a setter."""
    saved = os.environ.get("SCITEX_DIR")

    def setter(value: str) -> None:
        os.environ["SCITEX_DIR"] = value

    try:
        yield setter
    finally:
        if saved is None:
            os.environ.pop("SCITEX_DIR", None)
        else:
            os.environ["SCITEX_DIR"] = saved


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
    # Arrange
    expected = (
        isolated_home
        / ".scitex"
        / "crossref-local"
        / "runtime"
        / "completion"
        / PROG_NAME
    )
    # Act
    path = dropin_path()
    # Assert
    assert path == expected


def test_dropin_path_honours_scitex_dir(tmp_path, scitex_dir_env):
    # Arrange
    scitex_dir_env(str(tmp_path / "custom"))
    expected = (
        tmp_path / "custom" / "crossref-local" / "runtime" / "completion" / PROG_NAME
    )
    # Act
    path = dropin_path()
    # Assert
    assert path == expected


# ---------- _script_for_shell ----------


@pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
def test_script_for_shell_emits_nonempty_script(shell):
    # Arrange
    # Act
    script = _script_for_shell(shell)
    # Assert
    assert len(script.strip()) > 0


def test_script_for_bash_references_complete_var():
    # Arrange
    # Act
    script = _script_for_shell("bash")
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in script


def test_script_for_bash_references_prog_name():
    # Arrange
    # Act
    script = _script_for_shell("bash")
    # Assert
    assert PROG_NAME in script


def test_script_for_unknown_shell_raises_value_error():
    # Arrange
    shell = "unknown_shell"
    # Act
    ctx = pytest.raises(ValueError, match="Unsupported shell")
    # Assert
    with ctx:
        _script_for_shell(shell)


# ---------- _install_completion (isolated HOME) ----------


def test_install_completion_writes_dropin_file(isolated_home):
    # Arrange
    # Act
    path = _install_completion("bash")
    # Assert
    assert path.is_file()


def test_install_completion_returns_dropin_path(isolated_home):
    # Arrange
    # Act
    path = _install_completion("bash")
    # Assert
    assert path == dropin_path()


def test_install_completion_file_holds_bash_script(isolated_home):
    # Arrange
    # Act
    path = _install_completion("bash")
    # Assert
    assert "CROSSREF_LOCAL_COMPLETE" in path.read_text()


def test_install_completion_rerun_returns_same_path(isolated_home):
    # Arrange
    first = _install_completion("bash")
    # Act
    second = _install_completion("bash")
    # Assert
    assert second == first


def test_install_completion_rerun_keeps_bytes_identical(isolated_home):
    # Arrange
    path = _install_completion("bash")
    before = path.read_bytes()
    # Act
    _install_completion("bash")
    # Assert
    assert path.read_bytes() == before


def test_install_completion_leaves_no_temp_files(isolated_home):
    # Arrange
    # Act
    _install_completion("bash")
    leftovers = list(dropin_path().parent.glob(f"{PROG_NAME}.*"))
    # Assert
    assert leftovers == []


def test_install_completion_does_not_touch_bashrc(isolated_home):
    # Arrange
    # Act
    _install_completion("bash")
    # Assert
    assert not (isolated_home / ".bashrc").exists()


def test_install_completion_does_not_touch_zshrc(isolated_home):
    # Arrange
    # Act
    _install_completion("bash")
    # Assert
    assert not (isolated_home / ".zshrc").exists()


def test_install_completion_rejects_unknown_shell(isolated_home):
    # Arrange
    shell = "unknown_shell"
    # Act
    ctx = pytest.raises(ValueError, match="Unsupported shell")
    # Assert
    with ctx:
        _install_completion(shell)


# ---------- _is_installed / _uninstall_completion ----------


def test_is_installed_returns_false_before_install(isolated_home):
    # Arrange
    # Act
    installed, _path = _is_installed()
    # Assert
    assert installed is False


def test_is_installed_path_matches_dropin_before_install(isolated_home):
    # Arrange
    # Act
    _installed, path = _is_installed()
    # Assert
    assert path == dropin_path()


def test_is_installed_returns_true_after_install(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    installed, _path = _is_installed()
    # Assert
    assert installed is True


def test_is_installed_path_matches_dropin_after_install(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    _installed, path = _is_installed()
    # Assert
    assert path == dropin_path()


def test_uninstall_completion_reports_true_when_present(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    removed = _uninstall_completion()
    # Assert
    assert removed is True


def test_uninstall_completion_leaves_no_dropin_file(isolated_home):
    # Arrange
    _install_completion("bash")
    # Act
    _uninstall_completion()
    # Assert
    assert not dropin_path().exists()


def test_uninstall_completion_reports_false_when_absent(isolated_home):
    # Arrange
    # Act
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


def test_completion_install_exits_zero(runner, isolated_home, shell_env):
    # Arrange
    shell_env("/bin/bash")
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0


def test_completion_install_prints_dropin_path(runner, isolated_home, shell_env):
    # Arrange
    shell_env("/bin/bash")
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert str(dropin_path()) in result.output


def test_completion_install_writes_dropin_file(runner, isolated_home, shell_env):
    # Arrange
    shell_env("/bin/bash")
    # Act
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert dropin_path().is_file()


def test_completion_install_short_yes_flag_exits_zero(runner, isolated_home):
    # Arrange
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "-y"])
    # Assert
    assert result.exit_code == 0


def test_completion_install_short_yes_flag_writes_dropin(runner, isolated_home):
    # Arrange
    # Act
    runner.invoke(completion, ["install", "--shell", "bash", "-y"])
    # Assert
    assert dropin_path().is_file()


def test_completion_install_without_rc_touch_exits_zero(runner, isolated_home):
    # Arrange
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0


def test_completion_install_leaves_bashrc_untouched(runner, isolated_home):
    # Arrange
    # Act
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert not (isolated_home / ".bashrc").exists()


def test_completion_install_leaves_zshrc_untouched(runner, isolated_home):
    # Arrange
    # Act
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert not (isolated_home / ".zshrc").exists()


def test_completion_install_rerun_exits_zero(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert result.exit_code == 0


def test_completion_install_rerun_keeps_bytes_identical(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    before = dropin_path().read_bytes()
    # Act
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Assert
    assert dropin_path().read_bytes() == before


def test_completion_status_exits_zero_when_missing(runner, isolated_home):
    # Arrange
    args = ["status"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert result.exit_code == 0


def test_completion_status_prints_dropin_path_when_missing(runner, isolated_home):
    # Arrange
    args = ["status"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert str(dropin_path()) in result.output


def test_completion_status_reports_not_installed_when_missing(runner, isolated_home):
    # Arrange
    args = ["status"]
    # Act
    result = runner.invoke(completion, args)
    # Assert
    assert "not installed" in result.output


def test_completion_status_exits_zero_after_install(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["status"])
    # Assert
    assert result.exit_code == 0


def test_completion_status_reports_installed_after_install(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["status"])
    # Assert
    assert "installed" in result.output


def test_completion_uninstall_exits_zero(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    result = runner.invoke(completion, ["uninstall"])
    # Assert
    assert result.exit_code == 0


def test_completion_uninstall_removes_dropin_file(runner, isolated_home):
    # Arrange
    runner.invoke(completion, ["install", "--shell", "bash", "--yes"])
    # Act
    runner.invoke(completion, ["uninstall"])
    # Assert
    assert not dropin_path().exists()


def test_completion_uninstall_exits_zero_when_absent(runner, isolated_home):
    # Arrange
    # Act
    result = runner.invoke(completion, ["uninstall"])
    # Assert
    assert result.exit_code == 0


def test_completion_uninstall_reports_not_installed_when_absent(runner, isolated_home):
    # Arrange
    # Act
    result = runner.invoke(completion, ["uninstall"])
    # Assert
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


def test_completion_group_registers_install_subcommand(isolated_home):
    # Arrange (import here: pulls the full CLI tree)
    import click

    from crossref_local._cli.cli import cli

    # Act
    command = cli.get_command(click.Context(cli), "completion")
    # Assert
    assert "install" in command.commands


def test_completion_source_has_no_shell_configs_table():
    # Arrange
    import crossref_local._cli.completion as completion_module

    # Act
    source = _Path(completion_module.__file__).read_text()
    # Assert
    assert "SHELL_CONFIGS" not in source


def test_completion_source_has_no_completion_marker():
    # Arrange
    import crossref_local._cli.completion as completion_module

    # Act
    source = _Path(completion_module.__file__).read_text()
    # Assert
    assert "COMPLETION_MARKER" not in source


def test_completion_source_references_no_fish_config():
    # Arrange
    import crossref_local._cli.completion as completion_module

    # Act
    source = _Path(completion_module.__file__).read_text()
    # Assert
    assert "config.fish" not in source


def test_completion_source_contains_no_print_calls():
    # Arrange
    import crossref_local._cli.completion as completion_module

    # Act
    source = _Path(completion_module.__file__).read_text()
    # Assert: the docstring may still tell users where to add a `source`
    # line themselves; only real print() calls are forbidden.
    assert "print(" not in source
