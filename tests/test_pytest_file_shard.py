from __future__ import annotations

import pytest

from tools.pytest_file_shard import (
    parse_shard_config,
    partition_nodeids,
    shard_for_nodeid,
)


def test_partition_is_complete_disjoint_and_stable() -> None:
    nodeids = tuple(f"tests/test_{index}.py::test_case" for index in range(200))
    first = partition_nodeids(nodeids, 2)
    second = partition_nodeids(nodeids, 2)
    assert first == second
    assert set(first[0]).isdisjoint(first[1])
    assert set(first[0]) | set(first[1]) == set(nodeids)
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
    assert parse_shard_config("2", "0") == (2, 0)
    assert parse_shard_config("2", "1") == (2, 1)
