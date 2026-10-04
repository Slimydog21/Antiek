"""Every console entry point this project declares must resolve and start.

An audit of this repository found two defects in one `pyproject.toml` block. One was the wheel
omitting `services/` -- **it built cleanly and could not import**. The other, fixed earlier the
same day, was **a console entry point pointing at a module that did not exist.**

An entry point is a string in a config file that nothing validates until a user types the command:

    [project.scripts]
    herdr-bridge = "infrastructure.connectors.herdr_bridge.cli:main"

The existing coverage does not catch a break in that string. `tests/test_herdr_bridge.py` imports
`submit_result` from the same module -- so **renaming or removing `main` would leave every test
green and every user with a command that fails at startup.** That is precisely the first defect's
shape, and it is why these tests resolve the target the declaration names rather than a neighbour.

## Why it walks the config instead of naming the script

A test asserting `herdr-bridge` works would keep passing while a newly declared command is broken on
arrival. These read `pyproject.toml` and check whatever is declared, so **a new entry point is covered
the moment it is written**, and an entry point removed from the config is not silently expected
either.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _config() -> dict:
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:  # pragma: no cover - older interpreters
        import tomli as tomllib  # type: ignore[no-redef]

    return tomllib.loads((_ROOT / "pyproject.toml").read_text(encoding="utf-8"))


def _declared_entry_points() -> list[tuple[str, str]]:
    """(name, "module:attr") for every console entry point the project declares."""
    project = _config().get("project", {})
    found = []
    for group in ("scripts", "gui-scripts"):
        found.extend((project.get(group) or {}).items())
    for group_values in (project.get("entry-points") or {}).values():
        found.extend((group_values or {}).items())
    return sorted(found)


def test_the_project_declares_at_least_one_entry_point() -> None:
    """Guard the walker.

    If the config shape changes so this returns nothing, every assertion below passes on an empty
    list and the file silently stops testing anything. That failure mode is the reason this test
    exists separately.
    """
    assert _declared_entry_points(), (
        "no console entry points were parsed out of pyproject.toml. Either the project declares "
        "none -- in which case delete this file rather than leave it vacuously green -- or the "
        "parser no longer matches the config's shape."
    )


@pytest.mark.parametrize("name,target", _declared_entry_points())
def test_the_declared_target_resolves(name: str, target: str) -> None:
    """THE test: import the module the declaration names, then get the attribute it names."""
    module_path, _, attr = target.partition(":")
    assert module_path and attr, (
        f"entry point {name!r} has target {target!r}, which is not in `module:attr` form. Setuptools "
        "would accept it and fail at run time."
    )
    module = importlib.import_module(module_path)
    assert hasattr(module, attr), (
        f"entry point {name!r} points at {module_path}:{attr}, but {module_path} has no attribute "
        f"{attr!r}. The command would fail the moment a user runs it, and nothing else in the suite "
        "would notice."
    )
    assert callable(getattr(module, attr)), (
        f"entry point {name!r} resolves {target!r}, which is not callable, so running it would raise."
    )


@pytest.mark.parametrize("name,target", _declared_entry_points())
def test_the_declared_command_starts(name: str, target: str) -> None:
    """Run it, rather than trusting the import.

    An entry point can resolve and still fail immediately -- argparse with a required flag, a
    config read at import time, a missing dependency. `--help` exercises the module's top level and
    its argument parser without performing the command, which is the shallowest way to prove the
    command is not dead on arrival.
    """
    module_path, _, _ = target.partition(":")
    proc = subprocess.run(
        [sys.executable, "-m", module_path, "--help"],
        cwd=_ROOT, capture_output=True, text=True, timeout=300,
    )
    assert proc.returncode == 0, (
        f"`python -m {module_path} --help` exited {proc.returncode} for entry point {name!r}. "
        f"stderr tail:\n{proc.stderr[-500:]}"
    )
