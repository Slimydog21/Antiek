"""The wheel must import, not merely build.

An adversarial audit of this repository found the declared artifact was the one thing with no
test behind it:

    "`git grep -ln 'pip wheel|build --wheel|bdist_wheel|\.whl' -- tests/ tools/ .github/`
     returns no file, and the only `wheel` hits in workflows are pip's download cache."

`pip wheel .` **built cleanly** and omitted `services/` -- 117 tracked modules, imported by twelve
files inside the packaged roots -- so:

    PYTHONPATH=<wheel> python -c 'import interfaces.research.api.artifact_routes'
    ModuleNotFoundError: No module named 'services.html_projection.context'

while the identical import from the source tree succeeded. **A clean build is not evidence the
artifact works**, and nothing here said so.

## Why these tests are shaped this way

Building a wheel takes ~40 s, so it runs once per session and the assertions read that one build.
They are marked `slow` and are NOT skipped when the build fails -- a failure to build is reported as
a failure, because a test that skips when it cannot check is the defect this file exists to prevent.
"""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory) -> Path:
    """Build once, and fail loudly rather than skip if the build does not work."""
    out = tmp_path_factory.mktemp("wheel")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", ".", "-w", str(out), "--no-deps", "-q"],
        cwd=_ROOT, capture_output=True, text=True, timeout=1800,
    )
    wheels = sorted(out.glob("*.whl"))
    assert proc.returncode == 0 and wheels, (
        "the wheel did not build, so this file cannot check the artifact it exists to check. "
        f"rc={proc.returncode}. stderr tail: {proc.stderr[-400:]}"
    )
    return wheels[0]


def _configured_roots() -> list[str]:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover - older interpreters
        import tomli as tomllib  # type: ignore[no-redef]

    data = tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return list(data["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"])


def test_every_configured_root_is_in_the_wheel(built_wheel: Path) -> None:
    names = zipfile.ZipFile(built_wheel).namelist()
    missing = [r for r in _configured_roots()
               if not any(n == f"{r}/" or n.startswith(f"{r}/") for n in names)]
    assert not missing, (
        f"{missing!r} are declared as wheel package roots but contribute nothing to the built "
        "wheel. Either drop them from pyproject.toml or fix the build."
    )


def test_every_top_level_package_that_is_imported_is_packaged(built_wheel: Path) -> None:
    """THE test. It is the one that was missing.

    A root that exists in the tree and is imported by packaged code, but is absent from
    `packages`, produces a wheel that builds cleanly and cannot import. That is what happened
    to `services/`, and this asserts the general form of it rather than naming `services`.
    """
    import re

    names = zipfile.ZipFile(built_wheel).namelist()
    packaged = {n.split("/", 1)[0] for n in names if "/" in n and n.endswith(".py")}
    configured = set(_configured_roots())

    # Roots that exist in the working tree as importable packages.
    tree_roots = {
        p.name for p in _ROOT.iterdir()
        if p.is_dir() and (p / "__init__.py").exists() or
        (p.is_dir() and any(c.suffix == ".py" for c in p.rglob("*.py")))
    }
    declared = configured | packaged
    # Imported by a file that IS packaged, from outside its own root.
    referenced: set[str] = set()
    for path in _ROOT.rglob("*.py"):
        top = path.relative_to(_ROOT).parts[0]
        if top not in declared or "/.venv/" in str(path) or "node_modules" in str(path):
            continue
        for match in re.finditer(r"^\s*(?:from|import)\s+([a-z_][a-z0-9_]*)", path.read_text(
                encoding="utf-8", errors="ignore"), re.M):
            referenced.add(match.group(1))

    # DEV-ONLY ROOTS, excluded by name and on purpose. These are importable and are imported
    # from packaged code (tools.lint.*, tools.pytest_file_shard), and they are NOT runtime
    # dependencies of the artifact -- shipping them would put the linters and the test harness
    # in the wheel. Naming them here rather than pattern-matching keeps the list auditable: if a
    # genuinely runtime root is added to this set, that is a visible edit rather than a silent
    # widening of the exemption.
    dev_only = {"tools", "tests", "docs", "specs", "scripts", "mutants", "patches", "fleet"}
    orphaned = sorted(r for r in tree_roots & referenced
                      if r not in configured and r not in packaged and r not in dev_only)
    assert not orphaned, (
        f"{orphaned!r} exist as importable roots, are imported by packaged code, and are in "
        "NEITHER the wheel nor `packages`. The wheel will build and then fail at import time. "
        "This is exactly how `services/` was broken."
    )


def test_the_wheel_can_import_a_module_that_crosses_roots(built_wheel: Path, tmp_path: Path) -> None:
    """Import from the ARTIFACT, not the source tree.

    `interfaces/research/api/artifact_routes.py` imports `services.html_projection.context`, so it
    crosses the boundary that was broken. Running the import with the source tree on `sys.path`
    would pass either way, which is why the extraction directory is the only path given.
    """
    import os

    zipfile.ZipFile(built_wheel).extractall(tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONPATH"] = str(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-c",
         "import interfaces.research.api.artifact_routes as m; print('OK', m.__name__)"],
        cwd=tmp_path, capture_output=True, text=True, timeout=600, env=env,
    )
    assert proc.returncode == 0, (
        "a module inside the packaged roots cannot be imported from the built wheel:\n"
        f"{proc.stderr[-600:]}\nThis is the failure `services/` produced: the wheel builds and "
        "the import fails."
    )
    assert "OK" in proc.stdout
