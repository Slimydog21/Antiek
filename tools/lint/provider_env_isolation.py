"""Require CI to blank every provider credential the dispatch code actually reads.

``substrate/dispatch`` registers a live provider whenever it finds a key — BYOK
first, then the environment. A test that reaches dispatch with an ambient key
therefore opens a real socket to a real vendor. That makes suite greenness depend
on the machine it ran on, and can spend real money.

CI already defends against this by setting the keys to ``""``. The defect this
lint closes is DRIFT: that list was maintained by hand and fell out of sync with
the code, so ``XIAOMI_API_KEY`` and ``Z_AI_API_KEY`` were read but never blanked.

The expected set is derived from source on every run, so adding a provider that
reads a new key fails here instead of silently reopening the hole.

Rules enforced:
  1. A step running the full suite (``pytest tests/``) must blank every key.
  2. A step that blanks SOME keys must blank ALL of them — partial isolation is
     how this drifted in the first place. Steps that never opted in are left
     alone; this lint does not force isolation onto narrowly-scoped jobs.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import NamedTuple

import yaml

ROOT = Path(__file__).resolve().parents[2]
DISPATCH = ROOT / "substrate/dispatch"
WORKFLOW = ROOT / ".github/workflows/ci.yml"
_KEY = re.compile(r"^[A-Z][A-Z0-9_]*_API_KEY$")


def provider_env_vars(package: Path | None = None) -> set[str]:
    """Every ``*_API_KEY`` environment name referenced by the dispatch package."""
    package = package or DISPATCH   # resolved late so tests can redirect the module attribute
    found: set[str] = set()
    for path in sorted(package.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and _KEY.match(node.value):
                found.add(node.value)
    return found


class Step(NamedTuple):
    """One workflow step that invokes pytest."""

    name: str
    env: dict[str, str]
    run: str

    @property
    def runs_repo_tests(self) -> bool:
        return "pytest tests/" in self.run


def _pytest_steps(workflow: Path | None = None) -> list[Step]:
    """Every workflow step that invokes pytest."""
    workflow = workflow or WORKFLOW   # resolved late so tests can redirect the module attribute
    document = yaml.safe_load(workflow.read_text())
    steps: list[Step] = []
    for job in (document.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            run = str(step.get("run") or "")
            if "pytest" in run:
                name = str(step.get("name") or run.strip().splitlines()[0])
                steps.append(Step(name=name, env=dict(step.get("env") or {}), run=run))
    return steps


def check() -> list[str]:
    expected = provider_env_vars()
    if not expected:
        return ["No provider env vars discovered — the lint lost its subject, which is itself a failure."]
    failures: list[str] = []
    for step in _pytest_steps():
        declared = {key for key in step.env if _KEY.match(key)}
        if not declared and not step.runs_repo_tests:
            continue  # never opted into isolation, and does not run the repo suite
        missing = sorted(expected - set(step.env))
        if missing:
            failures.append(f"{step.name!r} does not blank: {', '.join(missing)}")
        nonblank = sorted(key for key in declared if step.env.get(key) not in ("", None))
        if nonblank:
            failures.append(f"{step.name!r} declares a non-empty provider key: {', '.join(nonblank)}")
    return failures


if __name__ == "__main__":
    errors = check()
    print("\n".join(errors) if errors else "CI blanks every provider credential the dispatch code reads")
    raise SystemExit(bool(errors))
