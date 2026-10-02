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
import os
import re
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


# ─────────────────────────── TypeScript half ────────────────────────────
#
# The same defect exists on the TS side, with a sharper edge: apps/reading/e2e
# holds BOTH Playwright specs (*.spec.ts) and pure-function unit calibrations
# (*.test.ts). Playwright's testMatch is /\.spec\.ts$/ and vitest's include was
# src/**, so a *.test.ts file inside e2e/ matched NEITHER runner.
#
# e2e/_ams/visible.pixel.test.ts sat in exactly that gap: 14 tests whose stated
# purpose is proving assertSceneVisible FAILS on an occluded/empty scene rather
# than passing vacuously. The calibration that proves a gate is not vacuous was
# itself never executed. Both runners confirm it in their own words -- vitest
# reported "No test files found" for an explicit path, and `playwright test
# --list` printed 92 tests in 28 files without it.

READING = REPO_ROOT / "apps" / "reading"

# TS test files that no runner collects and that cannot simply be globbed in.
#
# EMPTY, and that is the point. It briefly held tools/agent/verify_handoff
# .test.ts and tools/specs/verify_spec_refs.test.ts, on the finding that
# vitest "cannot reach above its root" -- including ../../tools/**/*.test.ts
# collected them and then failed every one with "Cannot find module
# '/@fs/...'". That diagnosis was incomplete: the barrier was vite's fs.allow
# boundary, not the root, and widening it collects all 26 tests. The register
# emptied instead of being explained away.
#
# It stays as a NO-GROWTH register: entries must LEAVE when fixed
# (test_registered_ts_files_are_still_uncollected fails if one becomes
# collected), and a new orphan cannot be added without saying why here.
KNOWN_UNCOLLECTED_TS: dict[str, str] = {}


def _expand_braces(pattern: str) -> list[str]:
    """``a.{ts,tsx}`` -> ``[a.ts, a.tsx]`` (single level, which is all we use)."""
    start = pattern.find("{")
    if start == -1:
        return [pattern]
    end = pattern.find("}", start)
    if end == -1:
        return [pattern]
    head, body, tail = pattern[:start], pattern[start + 1 : end], pattern[end + 1 :]
    out: list[str] = []
    for alt in body.split(","):
        out.extend(_expand_braces(head + alt + tail))
    return out


def _glob_to_regex(pattern: str) -> str:
    """Translate a vitest include glob to a regex.

    ``**`` crosses directory separators, ``*`` does not. Hand-rolled rather
    than using fnmatch (whose ``*`` matches ``/``, so ``src/*.test.ts`` would
    wrongly match nested files) or PurePath.full_match (3.13+, while the local
    venv is 3.12).
    """
    i, out = 0, ["^"]
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    out.append("$")
    return "".join(out)


def _vitest_includes() -> list[str]:
    """The include globs declared in apps/reading/vitest.config.ts."""
    cfg = (READING / "vitest.config.ts").read_text(encoding="utf-8")
    m = re.search(r"include:\s*\[(.*?)\]", cfg, re.DOTALL)
    assert m, "could not find the vitest include array"
    globs = re.findall(r'"([^"]+)"', m.group(1))
    assert globs, "vitest include array parsed as empty"
    expanded: list[str] = []
    for g in globs:
        expanded.extend(_expand_braces(g))
    return expanded


def _playwright_spec_suffix() -> str:
    """Playwright's testMatch, which selects by suffix."""
    cfg = (READING / "playwright.config.ts").read_text(encoding="utf-8")
    m = re.search(r"testMatch:\s*/\\\.(\w+)\\\.ts\$/", cfg)
    assert m, "could not parse the top-level playwright testMatch"
    return f".{m.group(1)}.ts"


def _ts_test_files() -> list[str]:
    out: list[str] = []
    for suffix in ("*.test.ts", "*.test.tsx", "*.spec.ts"):
        for f in REPO_ROOT.rglob(suffix):
            if any(
                part in {".git", "node_modules", "dist", "storybook-static", ".venv"}
                for part in f.parts
            ):
                continue
            out.append(f.relative_to(REPO_ROOT).as_posix())
    return sorted(set(out))



def _vitest_collects(rel: str) -> bool:
    """Does vitest's include glob match this repo-relative path?

    Globs are relative to apps/reading (vite's root) and may escape it with
    ``../../``. Matching on the repo-relative path and a startswith check was
    VACUOUS for exactly the register entries it guarded: every entry begins
    with ``tools/``, so an ``apps/reading/`` prefix test skipped them all and
    a stale register could never be detected. Comparing paths relative to the
    vite root handles both shapes uniformly.
    """
    rel_to_root = os.path.relpath(REPO_ROOT / rel, READING).replace(os.sep, "/")
    return any(
        re.compile(_glob_to_regex(g)).match(rel_to_root) for g in _vitest_includes()
    )


def test_vitest_and_playwright_patterns_are_parseable() -> None:
    """Guard the guard: a config reshuffle must fail loudly, not silently."""
    includes = _vitest_includes()
    assert len(includes) >= 2, f"implausibly few vitest includes: {includes}"
    assert _playwright_spec_suffix() == ".spec.ts"


def test_every_ts_test_file_is_collected_or_registered() -> None:
    spec_suffix = _playwright_spec_suffix()
    orphans: list[str] = []
    for rel in _ts_test_files():
        if rel in KNOWN_UNCOLLECTED_TS:
            continue
        if rel.endswith(spec_suffix) and rel.startswith("apps/reading/e2e/"):
            continue  # Playwright's testDir
        if _vitest_collects(rel):
            continue
        orphans.append(rel)
    assert not orphans, (
        "these TypeScript test files are collected by neither vitest nor "
        "Playwright, so they execute zero times:\n  " + "\n  ".join(orphans)
    )


def test_registered_ts_files_are_still_uncollected() -> None:
    """The register must shrink. If an entry is now collected, delete it."""
    for rel in sorted(KNOWN_UNCOLLECTED_TS):
        if not (REPO_ROOT / rel).exists():
            continue
        assert not _vitest_collects(rel), (
            f"{rel} is now collected by vitest -- remove it from "
            "KNOWN_UNCOLLECTED_TS so it is covered by the assertion above"
        )
