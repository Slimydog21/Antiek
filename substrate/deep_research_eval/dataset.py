"""Frozen W0 query dataset: load + validate queries_v1.json (never mutate it)."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DATASET_FILENAME = "queries_v1.json"
EXPECTED_QUERY_COUNT = 20

# Content pin for the frozen v1 file: sha256 of the exact file bytes. Editing
# queries_v1.json without a version bump (and a new pin) fails loading closed —
# the comparability key alone cannot see a same-version content edit.
QUERIES_V1_SHA256 = "c329d9152ea84875befa7dc33ecc89b60c6f6b987fcefba7a555b1eca0cd832e"

# TEST-ONLY escape hatch: pass as ``expected_sha256`` to load a synthetic
# dataset variant (structural validation still applies in full). Module-private
# and NOT exported from the package: tests import it from this module directly.
# Bypassing the pin is NOT an identity bypass — the loaded file's real content
# digest still lands in ``QueryDataset.content_digest`` and therefore in the
# comparability key, so altered content can never impersonate the frozen set.
_TEST_ONLY_UNPINNED_DIGEST = "unpinned-digest-test-only"


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
    # sha256 hex of the exact file bytes this dataset was loaded from —
    # computed at load time for EVERY load path, pinned or not.
    content_digest: str
    queries: tuple[Query, ...]

    @property
    def dataset_key(self) -> str:
        """Identity component of the comparability key: id@version+digest12.

        Carrying the content digest means two same-version files with
        different bytes can never share a comparability key, regardless of
        which load path produced them (fail closed by construction)."""
        return f"{self.dataset_id}@{self.version}+{self.content_digest[:12]}"


def default_dataset_path() -> Path:
    return Path(__file__).resolve().parent / DATASET_FILENAME


def _require_str(mapping: Mapping[str, Any], key: str, context: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DatasetValidationError(f"{context}: {key!r} must be a non-empty string")
    return value


def load_dataset(
    path: Path | None = None,
    *,
    expected_sha256: str = QUERIES_V1_SHA256,
) -> QueryDataset:
    """Load + validate the frozen dataset. Any structural deviation raises.

    Invariants (v1): exactly ``EXPECTED_QUERY_COUNT`` queries, unique ids,
    ``frozen`` is true, version string present, every query carries a
    non-empty ``expected_coverage`` anchor list. The file bytes must match
    ``expected_sha256`` (default: the pinned ``QUERIES_V1_SHA256``) — a
    same-version content edit fails closed. Tests loading synthetic variants
    may import the module-private ``_TEST_ONLY_UNPINNED_DIGEST`` sentinel (or
    pass a recomputed digest); nothing else may. Either way the ACTUAL content
    digest is recorded on the returned dataset and enters the comparability key.
    """
    dataset_path = path if path is not None else default_dataset_path()
    try:
        raw_bytes = dataset_path.read_bytes()
    except OSError as exc:
        raise DatasetValidationError(f"cannot read dataset at {dataset_path}") from exc
    content_digest = hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha256 != _TEST_ONLY_UNPINNED_DIGEST and content_digest != expected_sha256:
        raise DatasetValidationError(
            f"dataset digest mismatch at {dataset_path}: sha256={content_digest} "
            f"expected={expected_sha256} (frozen content changed without a pin bump)"
        )
    try:
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
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
        content_digest=content_digest,
        queries=tuple(queries),
    )
