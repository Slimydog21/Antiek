"""Deterministically balance a pytest collection by source file.

Loaded only by CI with ``-p tools.pytest_file_shard``. Keeping every test from
one file on the same runner preserves file-scoped ordering and fixture behavior.
Files are assigned with deterministic longest-processing-time bin packing, using
their collected test count as the weight. This avoids the severe count skew that
a stable hash can produce as the suite grows while retaining reproducible shards.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from pathlib import Path

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


def partition_nodeids(
    nodeids: Sequence[str],
    count: int,
    weights: Mapping[str, float] | None = None,
) -> tuple[tuple[str, ...], ...]:
    """Partition node ids into deterministic, whole-file balanced shards.

    ``weights`` maps a source file to its measured cost in seconds. Without it
    each file weighs its TEST COUNT, which is what this packer did originally
    and is kept as the fallback so behaviour is unchanged when no measurement
    exists.

    Counting tests balances the wrong quantity: five slow integration tests
    weigh the same as five fast unit tests. Measured on CI over ten runs, that
    produced a 1.90x spread — shard 2 of 4 ran a median 29.0 min against shard
    3's 15.3 min, and shard 2 was the slowest in 7 of those 10 runs while shard
    3 was never slowest. The skew is systematic, not noise, so it is fixable by
    weighting with the right number.

    That spread is the whole CI critical path: the `pytest` aggregator needs
    every shard, so a run cannot finish before its slowest one. Balanced shards
    move the floor from 29.0 min to about 21.1.
    """
    if count < 1:
        raise ValueError("count must be at least 1")

    by_file: dict[str, list[str]] = {}
    for nodeid in nodeids:
        source_file = nodeid.split("::", maxsplit=1)[0]
        by_file.setdefault(source_file, []).append(nodeid)

    def cost(source_file: str, file_nodeids: list[str]) -> float:
        if weights is not None:
            measured = weights.get(source_file)
            if measured is not None and measured > 0:
                return float(measured)
        # Unmeasured (new file, or no map): fall back to test count. Mixing the
        # two units is deliberate — a new file should not sort as free and land
        # everything on one shard.
        return float(len(file_nodeids))

    shards: list[list[str]] = [[] for _ in range(count)]
    loads = [0.0] * count
    # Longest-processing-time first; the file name breaks ties so the partition
    # stays reproducible for a given collection.
    files = sorted(by_file.items(), key=lambda item: (-cost(item[0], item[1]), item[0]))
    for source_file, file_nodeids in files:
        shard_index = min(range(count), key=lambda index: (loads[index], index))
        shards[shard_index].extend(file_nodeids)
        loads[shard_index] += cost(source_file, file_nodeids)
    return tuple(tuple(shard) for shard in shards)


# Measured per-file runtime in seconds, committed next to this plugin. Absent or
# unreadable is FINE — the packer falls back to test counts, which is what it
# always did. Refresh with: pytest tests/ --durations=0 and re-aggregate.
_DURATIONS_FILENAME = "pytest_shard_durations.json"
_DURATIONS_ENV = "ANTIEK_PYTEST_SHARD_DURATIONS"


def load_duration_weights(path: str | None = None) -> dict[str, float] | None:
    """Per-file seconds, or None when unavailable.

    Never raises. A malformed or missing map must degrade to count-weighting
    rather than break collection — a sharding plugin that can fail closed would
    take the whole suite down for a stale data file.
    """
    candidate = path or os.environ.get(_DURATIONS_ENV)
    resolved = (
        Path(candidate) if candidate else Path(__file__).resolve().parent / _DURATIONS_FILENAME
    )
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    weights = {
        str(k): float(v) for k, v in raw.items() if isinstance(v, (int, float)) and float(v) > 0
    }
    return weights or None


@pytest.hookimpl(trylast=True)  # type: ignore[untyped-decorator]
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    count, index = parse_shard_config(
        os.environ.get(_COUNT_ENV),
        os.environ.get(_INDEX_ENV),
    )
    partitions = partition_nodeids(
        [item.nodeid for item in items], count, weights=load_duration_weights()
    )
    selected_nodeids = frozenset(partitions[index])
    selected = [item for item in items if item.nodeid in selected_nodeids]
    deselected = [item for item in items if item.nodeid not in selected_nodeids]
    config.hook.pytest_deselected(items=deselected)
    items[:] = selected


__all__ = [
    "load_duration_weights",
    "parse_shard_config",
    "partition_nodeids",
    "shard_for_nodeid",
]
