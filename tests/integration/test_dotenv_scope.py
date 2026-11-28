"""Import exports only CROSSREF_LOCAL_* keys from .env (scitex-config#47).

A fresh interpreter runs with a real temporary HOME/cwd holding a real
``.env``; nothing is mocked.
"""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_PROBE = textwrap.dedent(
    """
    import os
    import crossref_local
    print(os.environ.get("CROSSREF_LOCAL_DOTENV_PROBE", "<unset>"))
    print(os.environ.get("FOREIGN_SERVICE_API_KEY", "<unset>"))
    """
)


@pytest.fixture
def import_lines(tmp_path: Path) -> list:
    """Import crossref_local in a child whose HOME/.env holds own + foreign keys."""
    (tmp_path / ".env").write_text(
        "CROSSREF_LOCAL_DOTENV_PROBE=from-dotenv\n"
        "FOREIGN_SERVICE_API_KEY=fake-value-not-a-secret\n"
    )
    import crossref_local as _pkg

    src = str(Path(_pkg.__file__).resolve().parent.parent)
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("CROSSREF_LOCAL_DOTENV_PROBE", "FOREIGN_SERVICE_API_KEY")
    }
    env["HOME"] = str(tmp_path)
    env["PYTHONPATH"] = os.pathsep.join([src, *(p for p in sys.path if p)])
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=str(tmp_path),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr)
    return result.stdout.strip().splitlines()[-2:]


def test_own_prefixed_key_is_exported(import_lines: list) -> None:
    # Arrange
    expected = "from-dotenv"
    # Act
    value = import_lines[0]
    # Assert
    assert value == expected


def test_foreign_key_is_not_exported(import_lines: list) -> None:
    # Arrange
    expected = "<unset>"
    # Act
    value = import_lines[1]
    # Assert
    assert value == expected
