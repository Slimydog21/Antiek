"""Deterministically balance a pytest collection by source file.

Loaded only by CI with ``-p tools.pytest_file_shard``. Keeping every test from
one file on the same runner preserves file-scoped ordering and fixture behavior.
Files are assigned with deterministic longest-processing-time bin packing, using
their collected test count as the weight. This avoids the severe count skew that
a stable hash can produce as the suite grows while retaining reproducible shards.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence

import pytest

_COUNT_ENV = "ANTIEK_PYTEST_SHARD_COUNT"
_INDEX_ENV = "ANTIEK_PYTEST_SHARD_INDEX"


def parse_shard_config(count_raw: str | None, index_raw: str | None) -> tuple[int, int]:
    try:
        count = int(count_raw or "")
        index = int(index_raw or "")
    except ValueError as exc:
        raise pytest.UsageError(f"{_COUNT_ENV} and {_INDEX_ENV} must be integers") from exc
    if count < 2:
        raise pytest.UsageError(f"{_COUNT_ENV} must be at least 2")
    if not 0 <= index < count:
        raise pytest.UsageError(f"{_INDEX_ENV} must be between 0 and {count - 1}")
    return count, index


def shard_for_nodeid(nodeid: str, count: int) -> int:
    """Return the legacy stable-hash shard for one node id.

    Kept as a small public diagnostic helper. Collection uses
    :func:`partition_nodeids`, which can balance only with the full collection in
    hand.
    """
    source_file = nodeid.split("::", maxsplit=1)[0]
    digest = hashlib.sha256(source_file.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def partition_nodeids(nodeids: Sequence[str], count: int) -> tuple[tuple[str, ...], ...]:
    """Partition node ids into deterministic, whole-file balanced shards."""
    if count < 1:
        raise ValueError("count must be at least 1")

    by_file: dict[str, list[str]] = {}
    for nodeid in nodeids:
        source_file = nodeid.split("::", maxsplit=1)[0]
        by_file.setdefault(source_file, []).append(nodeid)

    shards: list[list[str]] = [[] for _ in range(count)]
    loads = [0] * count
    files = sorted(by_file.items(), key=lambda item: (-len(item[1]), item[0]))
    for _, file_nodeids in files:
        shard_index = min(range(count), key=lambda index: (loads[index], index))
        shards[shard_index].extend(file_nodeids)
        loads[shard_index] += len(file_nodeids)
    return tuple(tuple(shard) for shard in shards)


@pytest.hookimpl(trylast=True)  # type: ignore[untyped-decorator]
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    count, index = parse_shard_config(
        os.environ.get(_COUNT_ENV),
        os.environ.get(_INDEX_ENV),
    )
    partitions = partition_nodeids([item.nodeid for item in items], count)
    selected_nodeids = frozenset(partitions[index])
    selected = [item for item in items if item.nodeid in selected_nodeids]
    deselected = [item for item in items if item.nodeid not in selected_nodeids]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


__all__ = ["parse_shard_config", "partition_nodeids", "shard_for_nodeid"]
