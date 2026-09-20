"""Every test file must be collected by some runner.

Why this exists
---------------
On 2026-09-20 a sweep found nine ``test_*.py`` files — 115 test functions —
that NO runner collected. ``[tool.pytest.ini_options] testpaths`` lists
``tests`` and ``compounding/benchmark/tests``, but every CI invocation passes
explicit paths (``pytest tests/``, ``pytest services/... ``), and *explicit
paths override testpaths entirely*. So a test file outside those explicit
paths is not "covered by testpaths" — it is simply never run.

That is the vacuous-gate pattern applied to tests themselves: the file exists,
it is committed, it is cited in docs as evidence, and it executes zero times.
Two live defects were sitting in those unrun files at the time of the sweep:

  * ``tools/tests/test_fake_gate_detector.py`` failed on main with a stale
    mutant anchor (``connect_write`` no longer contains the matched line).
    That is the test suite for the tool that certifies other gates are not
    fake — unverified while the tool itself ran in CI.
  * ``interfaces/research/api/test_krea_stream.py`` failed because the /krea
    route surface grew a fourth route without the guard test ever objecting.

A one-time wiring fix would not stop the tenth file from drifting out. This
test makes the property enforceable: it parses the workflows, extracts the
path arguments of every pytest invocation, and asserts that each test file is
covered by one of them.

Fail-closed by construction: if the extraction breaks and finds no
invocations, every file reads as uncovered and this test fails loudly rather
than passing on an empty measurement.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"

# Files that match the ``test_*.py`` name but are TOOLS, not test modules.
# They contain no test functions, so pytest would collect nothing from them;
# they are listed explicitly so that if one ever gains a test function the
# coverage assertion below starts applying to it instead of silently skipping.
KNOWN_NON_TEST_MODULES = frozenset(
    {
        "tools/test_census.py",
        "tools/lint/test_desiderata_check.py",
        "runtime/test_store_guard.py",
    }
)

# Fixture corpora consumed BY the meta-tests. They are deliberately not
# collected — several are designed to fail — so they are excluded by path.
FIXTURE_PREFIXES = ("tools/tests/fixtures/",)


def _run_blocks() -> list[str]:
    """Every ``run:`` script body across all workflow files."""
    blocks: list[str] = []
    for wf in sorted(WORKFLOWS.glob("*.y*ml")):
        doc: Any = yaml.safe_load(wf.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            continue
        for job in (doc.get("jobs") or {}).values():
            if not isinstance(job, dict):
                continue
            for step in job.get("steps") or []:
                if isinstance(step, dict) and isinstance(step.get("run"), str):
                    blocks.append(step["run"])
    return blocks


def _join_continuations(block: str) -> list[str]:
    """Fold ``\\``-continued shell lines into single logical lines.

    CI steps wrap long pytest invocations across lines. Scanning raw lines
    would see ``interfaces/.../test_krea_stream.py \\`` on a line that does
    not contain the word "pytest" and drop that path -- reporting a file as
    uncollected while CI collects it every run.
    """
    logical: list[str] = []
    buf = ""
    for raw in block.splitlines():
        line = raw.strip()
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        logical.append(buf + line)
        buf = ""
    if buf:
        logical.append(buf)
    return logical


def _pytest_path_args() -> set[str]:
    """Path arguments handed to pytest anywhere in CI.

    A bare ``pytest`` with no path argument falls back to ``testpaths``; those
    fallbacks are added explicitly so the two mechanisms are treated alike.
    """
    paths: set[str] = set()
    for block in _run_blocks():
        for line in _join_continuations(block):
            if "pytest" not in line:
                continue
            tokens = line.split()
            try:
                start = next(
                    i
                    for i, t in enumerate(tokens)
                    if t == "pytest" or t.endswith("/pytest")
                )
            except StopIteration:
                continue
            args = tokens[start + 1 :]
            found = [
                a
                for a in args
                if not a.startswith("-") and ("/" in a or a.endswith(".py"))
            ]
            if found:
                paths.update(a.split("::", 1)[0] for a in found)
            elif not any(a.startswith("-") and "=" in a for a in args):
                # bare `pytest` -> testpaths from pyproject
                paths.update({"tests", "compounding/benchmark/tests"})
    return paths


def _is_test_module(path: Path) -> bool:
    """True when the file defines something pytest would actually collect.

    This mirrors pytest's real rules rather than the file name. A ``Test*``
    class only counts when it CONTAINS test methods: ``tools/test_census.py``
    defines ``class TestFnRecord`` (a frozen dataclass describing a test
    function), which pytest skips because it has an ``__init__``. Treating the
    name alone as proof would have mislabelled that tool as a test module.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return False
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith(
            "test_"
        ):
            return True
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            has_test_method = any(
                isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef))
                and m.name.startswith("test_")
                for m in node.body
            )
            if has_test_method:
                return True
    return False


def _all_test_files() -> list[str]:
    out: list[str] = []
    for p in REPO_ROOT.rglob("test_*.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if any(part in {".git", "node_modules", ".venv", "dist"} for part in p.parts):
            continue
        out.append(rel)
    for p in REPO_ROOT.rglob("*_test.py"):
        rel = p.relative_to(REPO_ROOT).as_posix()
        if any(part in {".git", "node_modules", ".venv", "dist"} for part in p.parts):
            continue
        out.append(rel)
    return sorted(set(out))


def _covered_by(rel: str, paths: set[str]) -> bool:
    return any(rel == p or rel.startswith(p.rstrip("/") + "/") for p in paths)


def test_pytest_invocations_are_actually_discoverable() -> None:
    """Guard the guard: the extraction must find real invocations.

    Without this, a parsing regression would yield an empty path set, every
    file would read as uncovered, and the failure would look like a hundred
    new orphans rather than a broken parser.
    """
    paths = _pytest_path_args()
    assert len(paths) >= 3, f"extracted implausibly few pytest paths: {sorted(paths)}"
    assert "tests/" in paths or "tests" in paths, (
        f"the main suite path is missing from the extraction: {sorted(paths)}"
    )


def test_every_test_file_is_collected_by_some_runner() -> None:
    paths = _pytest_path_args()
    orphans: list[str] = []
    for rel in _all_test_files():
        if rel.startswith(FIXTURE_PREFIXES) or rel in KNOWN_NON_TEST_MODULES:
            continue
        if not _is_test_module(REPO_ROOT / rel):
            continue
        if not _covered_by(rel, paths):
            orphans.append(rel)
    assert not orphans, (
        "these test files define tests but no CI pytest invocation collects "
        "them, so they execute zero times:\n  " + "\n  ".join(orphans)
    )


def test_known_non_test_modules_still_define_no_tests() -> None:
    """If one of these tools grows a real test, stop exempting it."""
    for rel in sorted(KNOWN_NON_TEST_MODULES):
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        assert not _is_test_module(path), (
            f"{rel} now defines tests but is exempted as a non-test module; "
            "remove it from KNOWN_NON_TEST_MODULES so coverage applies"
        )
