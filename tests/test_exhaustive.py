"""Tests for substrate.exhaustive — the exhaustive-match helper + pattern."""

from __future__ import annotations

from typing import Any, cast

import pytest

from substrate.exhaustive import (
    ReferenceOutcome,
    assert_exhaustive,
    classify_reference_outcome,
)

# ---------------------------------------------------------------------- #
# classify_reference_outcome — the canonical pattern works               #
# ---------------------------------------------------------------------- #


def test_classify_allowed() -> None:
    assert classify_reference_outcome("allowed") == "proceed"


def test_classify_blocked() -> None:
    assert classify_reference_outcome("blocked") == "halt"


def test_classify_held() -> None:
    assert classify_reference_outcome("held") == "queue-for-review"


def test_classify_all_variants_covered() -> None:
    """Every declared variant maps to a non-empty result — i.e. the
    match handles them all (none fall through to assert_exhaustive)."""
    variants: list[ReferenceOutcome] = ["allowed", "blocked", "held"]
    for v in variants:
        assert classify_reference_outcome(v)


# ---------------------------------------------------------------------- #
# assert_exhaustive — runtime fallback behavior                          #
# ---------------------------------------------------------------------- #


def test_assert_exhaustive_raises_on_unexpected_value() -> None:
    """Simulate an untyped boundary sneaking a bad value past mypy by
    casting. The catch-all arm fires assert_exhaustive, which raises a
    clear error naming the value."""
    sneaky = cast(ReferenceOutcome, "escalated")  # not a real variant
    with pytest.raises(AssertionError) as exc_info:
        classify_reference_outcome(sneaky)
    msg = str(exc_info.value)
    assert "escalated" in msg
    assert "classify_reference_outcome" in msg
    assert "non-exhaustive match" in msg


def test_assert_exhaustive_message_mentions_mypy() -> None:
    """The error message should point the operator at the root cause:
    a variant added without updating the match, which mypy --strict
    would normally catch."""
    with pytest.raises(AssertionError) as exc_info:
        assert_exhaustive(cast(Any, "whatever"), context="my_match")
    msg = str(exc_info.value)
    assert "mypy --strict" in msg
    assert "my_match" in msg


def test_assert_exhaustive_no_context() -> None:
    """Without a context label, the message still works (no dangling
    'in ' fragment)."""
    with pytest.raises(AssertionError) as exc_info:
        assert_exhaustive(cast(Any, "x"))
    msg = str(exc_info.value)
    assert "non-exhaustive match:" in msg  # no " in " before the colon
    assert " in :" not in msg


def test_assert_exhaustive_suggests_boundary_validation() -> None:
    """The message coaches the fix for the untyped-boundary case:
    validate into the closed set at the boundary."""
    with pytest.raises(AssertionError) as exc_info:
        assert_exhaustive(cast(Any, "x"), context="c")
    assert "untyped boundary" in str(exc_info.value)
