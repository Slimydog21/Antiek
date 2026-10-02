"""The typing census must take its scope from the gate, not from its own walk.

The document this replaces collected its own root set, and that set separated from the
targets the gate actually consumes -- 1254 files against 1056 -- with nothing to notice,
because a hand-written walk has no mechanism that fails when the two diverge.

This is that mechanism. It fails if the census stops importing the gate's definition.
"""

from __future__ import annotations

from tools.lints import declared_bar
from tools.typing_census import (
    _DEFAULT_BASELINE,
    _REPO_ROOT,
    build_census,
    read_baseline,
    target_python_files,
)


def _census():
    baseline = read_baseline(_REPO_ROOT / _DEFAULT_BASELINE)
    files = target_python_files(_REPO_ROOT, declared_bar.DECLARED_MYPY_TARGETS)
    return build_census(files, {violation.path for violation in baseline.violations})


def test_the_census_is_a_partition_and_not_a_guess() -> None:
    """Every file in scope is counted exactly once, in one of the two buckets."""
    result = _census()

    assert result.total_files > 0
    assert result.total_files == (
        result.empty_baseline_files + result.non_empty_baseline_files
    )


def test_the_gate_declares_the_targets_the_census_walks() -> None:
    """The property that makes the scope trustworthy, and the one that drifted before.

    The census does not carry its own root list; it walks what
    ``declared_bar.DECLARED_MYPY_TARGETS`` declares. If someone reintroduces a separate
    list, the two will disagree and this fails.
    """
    targets = getattr(declared_bar, "DECLARED_MYPY_TARGETS", None)

    assert targets, "the gate declares no targets for the census to import"

    walked = target_python_files(_REPO_ROOT, targets)
    top_level = {path.split("/", 1)[0] for path in walked}

    assert top_level == set(targets), (
        "the census walked roots that are not the gate's declared targets: "
        f"walked={sorted(top_level)} declared={sorted(targets)}"
    )
