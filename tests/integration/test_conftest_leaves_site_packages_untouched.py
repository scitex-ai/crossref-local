"""Regression test: importing tests/conftest.py must not touch site-packages."""

import subprocess
import sys
import textwrap
from pathlib import Path

CONFTEST_PATH = Path(__file__).resolve().parents[1] / "conftest.py"


def test_conftest_leaves_site_packages_untouched():
    # Arrange
    code = textwrap.dedent(
        f"""\
        import os
        import runpy
        import site

        os.environ["COVERAGE_PROCESS_START"] = "sentinel-process-start"
        os.environ["COVERAGE_FILE"] = "sentinel-coverage-file"

        def snapshot():
            names = set()
            dirs = []
            try:
                dirs.extend(site.getsitepackages())
            except Exception:
                pass
            try:
                dirs.append(site.getusersitepackages())
            except Exception:
                pass
            for d in dirs:
                try:
                    names.update((d, n) for n in os.listdir(d))
                except OSError:
                    continue
            return names

        before = snapshot()
        runpy.run_path({str(CONFTEST_PATH)!r})
        after = snapshot()
        assert after == before, "conftest.py created files in site-packages"
        assert os.environ["COVERAGE_PROCESS_START"] == "sentinel-process-start"
        assert os.environ["COVERAGE_FILE"] == "sentinel-coverage-file"
        """
    )
    # Act
    proc = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
    )
    # Assert
    assert proc.returncode == 0, proc.stderr
