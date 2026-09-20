"""Read-only exclusion of provider executions from a local-zero claim scope."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from runtime.db_lock import connect_read


class LocalZeroEvidenceUnavailable(RuntimeError):
    """The persisted state cannot support a local-zero assertion."""

    code = "evidence_unavailable"


class LocalZeroEvidenceConflict(LocalZeroEvidenceUnavailable):
    """Persisted state contradicts a local-zero assertion."""

    code = "evidence_conflict"


@dataclass(frozen=True)
class ProviderExecutionExclusion:
    revision_ids: tuple[str, ...]
    provider_execution_count: int = 0


def exclude_provider_executions(
    *,
    db_path: str,
    owner_id: str,
    asset_id: str,
    revision_ids: tuple[str, ...],
) -> ProviderExecutionExclusion:
    """Prove that no provider execution row exists in the exact local scope."""
    owner = _identity("owner_id", owner_id)
    asset = _identity("asset_id", asset_id)
    scope = tuple(sorted(_identity("revision_id", value) for value in revision_ids))
    if not scope or len(scope) != len(set(scope)) or len(scope) > 257:
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    path = Path(db_path)
    if not path.exists() or not path.is_file():
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    placeholders = ",".join("?" for _ in scope)
    try:
        with connect_read(str(path)) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM multimedia_provider_executions "
                f"WHERE operator_id=? AND asset_id=? AND revision_id IN ({placeholders})",
                [owner, asset, *scope],
            ).fetchone()
    except duckdb.CatalogException as exc:
        raise LocalZeroEvidenceUnavailable("evidence_unavailable") from exc
    except LocalZeroEvidenceUnavailable:
        raise
    except Exception as exc:
        raise LocalZeroEvidenceUnavailable("evidence_unavailable") from exc
    if count is None or len(count) != 1 or type(count[0]) is not int:
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    if count[0] != 0:
        raise LocalZeroEvidenceConflict("evidence_conflict")
    return ProviderExecutionExclusion(revision_ids=scope)


def _identity(name: str, value: str) -> str:
    if not isinstance(value, str):
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    normalized = value.strip()
    encoded = normalized.encode("utf-8")
    if (
        not encoded
        or len(encoded) > 512
        or any(byte < 32 or byte == 127 for byte in encoded)
    ):
        raise LocalZeroEvidenceUnavailable("evidence_unavailable")
    return normalized


__all__ = [
    "LocalZeroEvidenceConflict",
    "LocalZeroEvidenceUnavailable",
    "ProviderExecutionExclusion",
    "exclude_provider_executions",
]
