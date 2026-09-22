from __future__ import annotations

import pytest

from tools.pytest_file_shard import (
    load_duration_weights,
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
    for index in range(4):
        assert parse_shard_config("4", str(index)) == (4, index)


def test_four_way_partition_remains_complete_disjoint_and_nonempty() -> None:
    nodeids = tuple(
        f"tests/test_{file_index}.py::test_{case_index}"
        for file_index in range(20)
        for case_index in range(file_index % 5 + 1)
    )
    shards = partition_nodeids(nodeids, 4)

    assert all(shards)
    assert set().union(*map(set, shards)) == set(nodeids)
    assert all(
        set(left).isdisjoint(right)
        for index, left in enumerate(shards)
        for right in shards[index + 1 :]
    )


# ── duration-weighted packing ─────────────────────────────────────────────────


def _skewed_collection() -> tuple[list[str], dict[str, float]]:
    """A few slow files with few tests, many fast files with many tests.

    This is the real shape of the Antiek suite and the reason counting tests
    balances the wrong quantity.
    """
    counts: dict[str, int] = {}
    seconds: dict[str, float] = {}
    for i in range(3):
        counts[f"tests/slow_{i}.py"] = 6
        seconds[f"tests/slow_{i}.py"] = 300.0
    for i in range(12):
        counts[f"tests/fast_{i}.py"] = 40
        seconds[f"tests/fast_{i}.py"] = 25.0
    nodeids = [f"{f}::t{i}" for f, n in counts.items() for i in range(n)]
    return nodeids, seconds


def _real_loads(partitions, seconds: dict[str, float]) -> list[float]:
    """Wall seconds per shard — the only unit that matters.

    The `pytest` aggregator needs every shard, so a run cannot finish before its
    slowest one. Both weightings are judged by real seconds, never by the number
    each was optimising.
    """
    out = []
    for part in partitions:
        files = {nodeid.split("::")[0] for nodeid in part}
        out.append(sum(seconds[f] for f in files))
    return sorted(out, reverse=True)


def test_duration_weighting_beats_counting_on_the_slowest_shard() -> None:
    nodeids, seconds = _skewed_collection()

    by_count = _real_loads(partition_nodeids(nodeids, 4), seconds)
    by_time = _real_loads(partition_nodeids(nodeids, 4, weights=seconds), seconds)

    assert max(by_time) < max(by_count), (
        f"duration weighting did not shorten the critical path: count={by_count} duration={by_time}"
    )
    # Counting produces a real spread here; weighting removes it.
    assert max(by_count) / min(by_count) > 2.0, (
        f"the fixture stopped being skewed, so this test no longer proves anything: {by_count}"
    )
    assert max(by_time) / min(by_time) == pytest.approx(1.0, abs=0.01), by_time


def test_an_unmeasured_file_falls_back_to_its_test_count() -> None:
    """A new file must not sort as free and land everything on one shard."""
    nodeids = [f"tests/known.py::t{i}" for i in range(2)] + [
        f"tests/brand_new.py::t{i}" for i in range(50)
    ]
    partitions = partition_nodeids(nodeids, 2, weights={"tests/known.py": 10.0})
    assert all(partitions), f"a shard came out empty: {partitions}"


def test_weights_do_not_change_determinism() -> None:
    nodeids, seconds = _skewed_collection()
    first = partition_nodeids(nodeids, 4, weights=seconds)
    second = partition_nodeids(tuple(reversed(nodeids)), 4, weights=seconds)
    # Compare the ASSIGNMENT, not the within-shard ordering — that follows
    # collection order by design, same as the unweighted determinism test above.
    assert tuple(frozenset(shard) for shard in first) == tuple(frozenset(shard) for shard in second)


def test_a_missing_or_broken_map_degrades_to_counting(tmp_path) -> None:
    """The plugin must never fail collection over a stale data file."""
    assert load_duration_weights("/definitely/not/here.json") is None
    broken = tmp_path / "m.json"
    broken.write_text("not json", encoding="utf-8")
    assert load_duration_weights(str(broken)) is None
    broken.write_text("[1, 2, 3]", encoding="utf-8")
    assert load_duration_weights(str(broken)) is None
    broken.write_text('{"tests/a.py": 12.5, "tests/b.py": 0, "tests/c.py": "x"}', encoding="utf-8")
    assert load_duration_weights(str(broken)) == {"tests/a.py": 12.5}
