from __future__ import annotations

import pytest

from tools.pytest_file_shard import (
    parse_shard_config,
    partition_nodeids,
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
