from __future__ import annotations

import pytest

from tools.pytest_file_shard import (
    parse_shard_config,
    partition_nodeids,
    pytest_collection_modifyitems,
    shard_for_nodeid,
)


def test_partition_is_complete_disjoint_and_stable() -> None:
    nodeids = tuple(f"tests/test_{index}.py::test_case" for index in range(200))
    first = partition_nodeids(nodeids, 3)
    second = partition_nodeids(nodeids, 3)
    assert first == second
    assert all(
        set(left).isdisjoint(right)
        for index, left in enumerate(first)
        for right in first[index + 1 :]
    )
    assert set().union(*map(set, first)) == set(nodeids)
    assert all(first)


def test_partition_balances_counts_without_splitting_files() -> None:
    nodeids = (
        *(f"tests/test_large.py::test_{index}" for index in range(7)),
        *(f"tests/test_medium.py::test_{index}" for index in range(5)),
        *(f"tests/test_small_a.py::test_{index}" for index in range(3)),
        *(f"tests/test_small_b.py::test_{index}" for index in range(1)),
    )

    shards = partition_nodeids(nodeids, 2)

    assert [len(shard) for shard in shards] == [8, 8]
    for source_file in {nodeid.split("::", maxsplit=1)[0] for nodeid in nodeids}:
        containing_shards = {
            shard_index
            for shard_index, shard in enumerate(shards)
            if any(nodeid.startswith(f"{source_file}::") for nodeid in shard)
        }
        assert len(containing_shards) == 1


def test_partition_assignment_is_independent_of_collection_order() -> None:
    nodeids = (
        "tests/test_b.py::test_two",
        "tests/test_a.py::test_one",
        "tests/test_b.py::test_one",
        "tests/test_c.py::test_one",
    )

    forward = partition_nodeids(nodeids, 2)
    reverse = partition_nodeids(tuple(reversed(nodeids)), 2)

    assert tuple(frozenset(shard) for shard in forward) == tuple(
        frozenset(shard) for shard in reverse
    )


def test_partition_rejects_non_positive_count() -> None:
    with pytest.raises(ValueError, match="count must be at least 1"):
        partition_nodeids(("tests/test_a.py::test_one",), 0)


def test_collection_hook_runs_after_marker_deselection() -> None:
    hook_options = pytest_collection_modifyitems.pytest_impl  # type: ignore[attr-defined]
    assert hook_options["trylast"] is True


def test_all_cases_from_one_file_stay_on_one_shard() -> None:
    first = shard_for_nodeid("tests/test_route.py::test_one", 2)
    second = shard_for_nodeid("tests/test_route.py::test_two[param]", 2)
    assert first == second


@pytest.mark.parametrize(
    ("count", "index"),
    [(None, None), ("one", "0"), ("1", "0"), ("2", "-1"), ("2", "2")],
)
def test_invalid_shard_configuration_fails_closed(
    count: str | None,
    index: str | None,
) -> None:
    with pytest.raises(pytest.UsageError):
        parse_shard_config(count, index)


def test_valid_shard_configuration() -> None:
    assert parse_shard_config("3", "0") == (3, 0)
    assert parse_shard_config("3", "1") == (3, 1)
    assert parse_shard_config("3", "2") == (3, 2)
