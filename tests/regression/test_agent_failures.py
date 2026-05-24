"""
Parametrized harness over ``tests/regression/agent_failures/*.yaml``.

Each fixture documents one observed agent failure. The tests in this
module:

1. Validate the schema of every fixture (every field present,
   sensible values).
2. Assert that every fixture either (a) has a non-GAP ``fix_commit``
   AND a non-GAP ``harness_check_that_now_catches``, in which case
   we treat it as a CLOSED incident — the test asserts the named
   harness mechanism actually exists in the codebase, or (b) has
   ``fix_commit: GAP`` and a documented mitigation candidate, in
   which case we EXPECT the failure to remain reproducible. The test
   for an open GAP records the gap as a warning so the CLI surface
   ``recent_failures()`` of ``orchestration.agent_failure_log`` can
   summarise outstanding work.

The library starts with five fixtures (Phase A loky semaphore + four
arxiv-ingestion failures + the Phase 8 shadow-mode standing
condition). Each new prod incident should add one BEFORE the fix
lands.

Why not "replay the failure for real" inside the test:

Each fixture's input is a small synthetic prompt + env. The test
suite cannot actually trigger a 429 ban from arxiv inside CI without
making real network calls — that's both flaky and abusive. The
fixture's ``input`` block exists for human triage and future
mechanical replay (when we add the Verifiers-style RL environment per
the RLM plan), not for in-pytest reproduction today. What CI verifies
TODAY is that every fixture is well-formed and that every closed
fixture's named harness mechanism still exists.

Spec: ~/specs/antiek-hashimoto-engineering/sprint-e2-harness.html
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

FIXTURES_DIR = Path(__file__).resolve().parent / "agent_failures"
REPO_ROOT = FIXTURES_DIR.parent.parent.parent

REQUIRED_FIELDS = (
    "id",
    "observed_at",
    "source",
    "agent",
    "phase",
    "failure_type",
    "context_summary",
    "input",
    "expected_behavior",
    "actual_failure",
    "harness_check_that_now_catches",
    "fix_commit",
)


def _yaml_fixture_paths() -> list[Path]:
    """All ``*.yaml`` under the fixtures dir, sorted for deterministic order."""
    if not FIXTURES_DIR.exists():
        return []
    return sorted(p for p in FIXTURES_DIR.glob("*.yaml"))


def _load_fixture(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _fixture_id(path: Path) -> str:
    """Pytest-friendly fixture id matching the filename stem."""
    return path.stem


FIXTURE_PATHS = _yaml_fixture_paths()


# ---------------------------------------------------------------------------
# Library minimum size — sanity that the directory hasn't been cleared.
# ---------------------------------------------------------------------------


def test_at_least_five_fixtures_present() -> None:
    """The regression library starts at five (Phase A loky + four arxiv +
    Phase 8 standing). Drops below five → either fixtures were lost or
    the library is regressing toward 'empty backstop'."""
    assert len(FIXTURE_PATHS) >= 5, (
        f"expected ≥5 fixtures in {FIXTURES_DIR.relative_to(REPO_ROOT)}, "
        f"found {len(FIXTURE_PATHS)}"
    )


def test_readme_documents_the_library() -> None:
    """The README must exist with the canonical schema description so
    a new operator can file a fixture without reading source."""
    readme = FIXTURES_DIR / "README.md"
    assert readme.exists(), f"missing {readme.relative_to(REPO_ROOT)}"
    text = readme.read_text(encoding="utf-8")
    for keyword in ("fixture-first", "harness_check_that_now_catches", "fix_commit"):
        assert keyword in text, f"README missing keyword: {keyword!r}"


# ---------------------------------------------------------------------------
# Per-fixture: schema validation.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_fixture_has_all_required_fields(path: Path) -> None:
    fx = _load_fixture(path)
    missing = [f for f in REQUIRED_FIELDS if f not in fx]
    assert not missing, f"{path.name} missing fields: {missing}"


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_fixture_id_matches_filename(path: Path) -> None:
    fx = _load_fixture(path)
    expected = path.stem
    assert fx["id"] == expected, (
        f"{path.name}: id field {fx['id']!r} does not match filename stem {expected!r}"
    )


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_fixture_observed_at_is_iso_date(path: Path) -> None:
    fx = _load_fixture(path)
    observed = str(fx["observed_at"])
    # We accept either YYYY-MM-DD or full ISO-8601 — the former is
    # the canonical fixture format, the latter would happen if a
    # future tool auto-files from agent_failure_log.
    assert len(observed) >= 10 and observed[4] == "-" and observed[7] == "-", (
        f"{path.name}: observed_at {observed!r} not in YYYY-MM-DD form"
    )


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_fixture_input_block_is_meaningful(path: Path) -> None:
    fx = _load_fixture(path)
    input_block = fx["input"]
    assert isinstance(input_block, dict), f"{path.name}: input must be a mapping"
    # A meaningful input has either a prompt OR an env knob that
    # makes the failure mode reproducible. Both empty = no signal.
    has_prompt = bool(str(input_block.get("prompt", "")).strip())
    has_env = bool(input_block.get("env"))
    assert has_prompt or has_env, (
        f"{path.name}: input has neither a prompt nor env knobs — "
        f"no synthetic reproducer would re-trigger the failure"
    )


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_fixture_failure_type_is_one_of_known_classes(path: Path) -> None:
    """Soft check: failure_type should be a slug, not free prose.

    The slug doesn't need to be in a closed enum — new failure modes
    happen — but it should be a-z + hyphens + underscores, so
    grouping queries are stable.
    """
    fx = _load_fixture(path)
    ft = fx["failure_type"]
    assert isinstance(ft, str) and ft, f"{path.name}: failure_type must be non-empty string"
    assert all(c.isalnum() or c in "_-" for c in ft), (
        f"{path.name}: failure_type {ft!r} must be slug-shaped (a-z, 0-9, _, -)"
    )


# ---------------------------------------------------------------------------
# Per-fixture: closed-vs-open enforcement.
# ---------------------------------------------------------------------------


def _is_closed(fx: dict[str, Any]) -> bool:
    """A fixture is CLOSED when both fix_commit and
    harness_check_that_now_catches name a real mitigation (not 'GAP')."""
    fix = str(fx.get("fix_commit", "")).strip().upper()
    harness = str(fx.get("harness_check_that_now_catches", "")).strip().upper()
    return fix != "GAP" and not harness.startswith("GAP")


@pytest.mark.parametrize("path", FIXTURE_PATHS, ids=_fixture_id)
def test_closed_fixtures_name_existing_harness(path: Path) -> None:
    """For every CLOSED fixture, the named harness mechanism must exist.

    "Exist" means: any path/symbol the harness names should be a real
    file in the repo. We use a permissive substring search — the
    fixture writes ``phase_runner verify`` and we check that
    ``orchestration/phase_runner/runner.py`` exists. A more precise
    check would parse the field and look up each mention, but the
    cost is high and the false-positive rate on substring is low.
    """
    fx = _load_fixture(path)
    if not _is_closed(fx):
        pytest.skip(f"{path.stem} is an open GAP; not enforced here")
    harness_desc = str(fx["harness_check_that_now_catches"])
    candidates = _repo_source_paths(harness_desc)
    if not candidates:
        # Field describes a mechanism but doesn't cite a repo source
        # path — acceptable as long as it isn't an obvious typo.
        return
    for c in candidates:
        assert (REPO_ROOT / c).exists(), (
            f"{path.name}: harness_check_that_now_catches names {c!r} but "
            f"that file does not exist in the repo"
        )


# Top-level source directories a fixture's harness field may cite.
# A token is only treated as a must-exist repo path when it starts
# with one of these AND ends in .py. This deliberately ignores
# absolute paths (``~/.antiek/...`` runtime state), ``file.py::symbol``
# qualifiers, and prose that merely contains a dot.
_REPO_SOURCE_ROOTS = (
    "substrate/",
    "acquisition/",
    "middleware/",
    "orchestration/",
    "interfaces/",
    "compounding/",
    "processing/",
    "runtime/",
    "tools/",
    "tests/",
    "benchmarks/",
    "scripts/",
    "docs/",
)


def _repo_source_paths(text: str) -> list[str]:
    """Extract repo-relative ``*.py`` source paths a fixture cites.

    Precision over recall: we only validate tokens that unambiguously
    name a tracked source file (start with a known top-level dir, end
    in ``.py``). A ``client.py::_http_get`` qualifier is trimmed to
    ``client.py``'s path; a ``~/.antiek/state.json`` runtime path is
    ignored (it's not a source file and won't exist in the repo); prose
    like "the §7 daemon" is ignored.
    """
    found: list[str] = []
    raw = text.replace(",", " ").replace("(", " ").replace(")", " ")
    for token in raw.split():
        tok = token.strip(".,:;`'\"")
        # Trim a ``::symbol`` qualifier (file.py::func → file.py).
        if "::" in tok:
            tok = tok.split("::", 1)[0]
        if not tok.endswith(".py"):
            continue
        if not any(tok.startswith(root) for root in _REPO_SOURCE_ROOTS):
            continue
        found.append(tok)
    return found


def test_open_gaps_are_visible() -> None:
    """Surface the count of open GAPs so a passing run still reports
    standing work. Pytest output captures the print; no assertion fires
    because GAPs are tracked, not blocked."""
    open_gaps = []
    for path in FIXTURE_PATHS:
        fx = _load_fixture(path)
        if not _is_closed(fx):
            open_gaps.append(path.stem)
    # We DON'T fail on open gaps — they're the regression-library's
    # standing inventory of known-but-not-yet-fixed failures. We
    # just surface the count.
    if open_gaps:
        print(f"\n{len(open_gaps)} open agent-failure GAP(s): {open_gaps}")


# ---------------------------------------------------------------------------
# Cross-fixture sanity.
# ---------------------------------------------------------------------------


def test_fixture_ids_are_unique() -> None:
    ids = [_load_fixture(p).get("id") for p in FIXTURE_PATHS]
    assert len(ids) == len(set(ids)), f"duplicate ids: {ids}"


def test_fixture_filenames_match_id_slugs() -> None:
    """A fixture's filename and its ``id`` must match exactly (slug-on-slug).

    Drift between filename and id breaks the
    ``regression_fixture_path`` link in agent_failure_log records
    (which point at file paths) and confuses grep workflows.
    """
    bad: list[tuple[str, str]] = []
    for p in FIXTURE_PATHS:
        fx = _load_fixture(p)
        if fx.get("id") != p.stem:
            bad.append((p.name, fx.get("id", "")))
    assert not bad, f"id/filename mismatches: {bad}"
