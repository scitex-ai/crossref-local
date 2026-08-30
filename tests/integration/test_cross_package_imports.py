"""Runtime cross-package import gate (PS-140 §2).

This test imports every cross-package module that crossref-local
references in its source tree. Two outcomes:

- Module installed AND import succeeds → test PASSES.
- Module installed BUT import fails (e.g. internal rename) → test FAILS loudly.
- Module NOT installed (peer standalone absent in the CI env) → test is
  SKIPPED via `pytest.importorskip` on the ROOT package only.

The skip is deliberately taken on the ROOT (``scitex_dev``) and the FULL
dotted path is then hard-imported: skipping on the full path would make an
internal rename (``scitex_dev.store`` moving or disappearing) look like an
absent peer, which is exactly the failure this gate exists to catch. A
blanket hard import is equally wrong — it breaks a lean install where the
peer is legitimately absent.
"""

import importlib

import pytest

CROSS_PACKAGE_IMPORTS = [
    "scitex.cli.introspect",
    "scitex_config",
    "scitex_dev",
    "scitex_dev._cli._completion",
    "scitex_dev.cli",
    "scitex_dev.decorators",
    "scitex_dev.ecosystem",
    # The corpus lives in the shared store primitive; this is now a
    # first-class runtime dependency of _core/store.py.
    "scitex_dev.store",
]


@pytest.mark.parametrize("module_path", CROSS_PACKAGE_IMPORTS)
def test_cross_package_import_resolves_module(module_path: str) -> None:
    """Each cross-package import resolves cleanly when the peer is installed."""
    # Arrange
    root = module_path.split(".")[0]
    pytest.importorskip(root)
    # Act
    mod = importlib.import_module(module_path)
    # Assert
    assert mod.__name__ == module_path
