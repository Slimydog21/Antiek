"""Antiek-bench task registry — determinism, uniqueness, and fail-closed lookups."""

from __future__ import annotations

import pytest

from substrate.antiek_bench.task_registry import (
    BenchTask,
    TaskRegistry,
    TaskRegistryError,
    load_default_registry,
)


def test_default_registry_loads_deterministically() -> None:
    # Invariant: repeated loads return byte-identical task ids in the same order.
    first = load_default_registry().task_ids()
    second = load_default_registry().task_ids()
    assert first == second
    assert len(first) >= 6  # minimal seed breadth across families


def test_task_id_family_prefix_must_match_family() -> None:
    with pytest.raises(ValueError, match="family prefix"):
        BenchTask(
            task_id="reasoning::wrong_prefix",
            family="retrieval",
            prompt="p",
            scoring="exact",
            expected="e",
        )


def test_exact_task_requires_expected() -> None:
    with pytest.raises(ValueError, match="exact scoring requires"):
        BenchTask(
            task_id="code::no_expected",
            family="code",
            prompt="p",
            scoring="exact",
        )


def test_human_task_rejects_expected_and_rubric() -> None:
    with pytest.raises(ValueError, match="human scoring"):
        BenchTask(
            task_id="reading_comprehension::leaked",
            family="reading_comprehension",
            prompt="p",
            scoring="human",
            expected="should not be here",
        )


def test_duplicate_task_id_raises() -> None:
    task = BenchTask(
        task_id="code::dup",
        family="code",
        prompt="p",
        scoring="exact",
        expected="e",
    )
    with pytest.raises(TaskRegistryError, match="duplicate"):
        TaskRegistry([task, task])


def test_unknown_lookup_raises_not_none() -> None:
    reg = load_default_registry()
    with pytest.raises(TaskRegistryError, match="unknown"):
        reg.get("code::does_not_exist")


def test_families_preserves_first_appearance_order() -> None:
    reg = load_default_registry()
    families = reg.families()
    assert families == list(dict.fromkeys(families))  # stable, no duplicates
    assert "reasoning" in families


def test_len_and_contains() -> None:
    reg = load_default_registry()
    assert len(reg) == len(reg.task_ids())
    first_id = reg.task_ids()[0]
    assert first_id in reg
    assert "code::nonexistent" not in reg
