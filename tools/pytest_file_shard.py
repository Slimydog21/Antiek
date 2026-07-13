"""Deterministically split a pytest collection by source file.

Loaded only by CI with ``-p tools.pytest_file_shard``. Keeping every test from
one file on the same runner preserves file-scoped ordering and fixture behavior.
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
    source_file = nodeid.split("::", maxsplit=1)[0]
    digest = hashlib.sha256(source_file.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % count


def partition_nodeids(nodeids: Sequence[str], count: int) -> tuple[tuple[str, ...], ...]:
    shards: list[list[str]] = [[] for _ in range(count)]
    for nodeid in nodeids:
        shards[shard_for_nodeid(nodeid, count)].append(nodeid)
    return tuple(tuple(shard) for shard in shards)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    count, index = parse_shard_config(
        os.environ.get(_COUNT_ENV),
        os.environ.get(_INDEX_ENV),
    )
    selected = [item for item in items if shard_for_nodeid(item.nodeid, count) == index]
    deselected = [item for item in items if shard_for_nodeid(item.nodeid, count) != index]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


__all__ = ["parse_shard_config", "partition_nodeids", "shard_for_nodeid"]
