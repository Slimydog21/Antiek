"""Frozen W0 query dataset: load + validate queries_v1.json (never mutate it)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET_FILENAME = "queries_v1.json"
EXPECTED_QUERY_COUNT = 20


class DatasetValidationError(ValueError):
    """The frozen dataset failed a structural invariant. Fail closed — never repair."""


@dataclass(frozen=True)
class Query:
    query_id: str
    question: str
    provenance: str
    domain: str
    query_class: str
    # Claims/entities a competent report MUST address; judge-independent
    # regression anchors (case-insensitive substring match in the runner).
    expected_coverage: tuple[str, ...]


@dataclass(frozen=True)
class QueryDataset:
    dataset_id: str
    version: str
    frozen: bool
    queries: tuple[Query, ...]

    @property
    def dataset_key(self) -> str:
        """Identity component of the comparability key: id@version."""
        return f"{self.dataset_id}@{self.version}"


def default_dataset_path() -> Path:
    return Path(__file__).resolve().parent / DATASET_FILENAME


def _require_str(mapping: Mapping[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key!r} must be a non-empty string")
    return value


def load_dataset(path: Path | None = None) -> QueryDataset:
    """Load + validate the frozen dataset. Any structural deviation raises.

    Invariants (v1): exactly ``EXPECTED_QUERY_COUNT`` queries, unique ids,
    ``frozen`` is true, version string present, every query carries a
    non-empty ``expected_coverage`` anchor list.
    """
    dataset_path = path if path is not None else default_dataset_path()
    try:
        raw = dataset_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DatasetValidationError(f"cannot read dataset at {dataset_path}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise DatasetValidationError(f"dataset at {dataset_path} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise DatasetValidationError("dataset root must be a JSON object")

    dataset_id = _require_str(data, "dataset_id", "dataset")
    version = _require_str(data, "version", "dataset")
    if data.get("frozen") is not True:
        raise DatasetValidationError("dataset must declare frozen=true (v1 is frozen)")

    queries_raw = data.get("queries")
    if not isinstance(queries_raw, list):
        raise DatasetValidationError("dataset 'queries' must be a list")

    queries: list[Query] = []
    for index, entry in enumerate(queries_raw):
        context = f"query {index + 1}"
        if not isinstance(entry, dict):
            raise DatasetValidationError(f"{context}: must be a JSON object")
        coverage_raw = entry.get("expected_coverage")
        if not isinstance(coverage_raw, list) or not coverage_raw:
            raise DatasetValidationError(f"{context}: 'expected_coverage' must be a non-empty list")
        anchors: list[str] = []
        for anchor in coverage_raw:
            if not isinstance(anchor, str) or not anchor.strip():
                raise DatasetValidationError(
                    f"{context}: expected_coverage anchors must be non-empty strings"
                )
            anchors.append(anchor)
        queries.append(
            Query(
                query_id=_require_str(entry, "id", context),
                question=_require_str(entry, "question", context),
                provenance=_require_str(entry, "provenance", context),
                domain=_require_str(entry, "domain", context),
                query_class=_require_str(entry, "class", context),
                expected_coverage=tuple(anchors),
            )
        )

    if len(queries) != EXPECTED_QUERY_COUNT:
        raise DatasetValidationError(
            f"expected exactly {EXPECTED_QUERY_COUNT} queries, found {len(queries)}"
        )
    ids = [q.query_id for q in queries]
    if len(set(ids)) != len(ids):
        duplicates = sorted({qid for qid in ids if ids.count(qid) > 1})
        raise DatasetValidationError(f"duplicate query ids: {duplicates}")

    return QueryDataset(
        dataset_id=dataset_id,
        version=version,
        frozen=True,
        queries=tuple(queries),
    )
