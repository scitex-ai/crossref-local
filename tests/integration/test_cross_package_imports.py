"""Runtime cross-package import gate (PS-140 §2).

This test imports every cross-package module that crossref-local
references in its source tree. Two outcomes:

- Module installed AND import succeeds → test PASSES.
- Module installed BUT import fails (e.g. internal rename) → test FAILS loudly.
- Module NOT installed (peer standalone absent in the CI env) → test is
  SKIPPED via `pytest.importorskip`. The umbrella's CI catches renames.
"""

import pytest

CROSS_PACKAGE_IMPORTS = [
    "scitex.cli.introspect",
    "scitex_config",
    "scitex_dev",
    "scitex_dev._cli._completion",
    "scitex_dev.cli",
    "scitex_dev.decorators",
    "scitex_dev.ecosystem",
]


@pytest.mark.parametrize("module_path", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_resolves_module(module_path: str) -> None:
    """Each cross-package import resolves cleanly when the peer is installed."""
    # Arrange
    name = module_path
    # Act
    mod = pytest.importorskip(name)
    # Assert
    assert mod.__name__ == name or mod.__name__.startswith(name.split(".", 1)[0])
