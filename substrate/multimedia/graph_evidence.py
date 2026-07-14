"""Owner-scoped discovery and digest-bound resolution of multimedia evidence."""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from processing.embedding import EmbeddingProvider
from runtime.db_lock import connect_read
from substrate.graph.search import search

from .planner import CanonicalEvidenceChunk, EvidenceChunk

_MAX_CANDIDATES = 20
_MAX_OWNER_DOCUMENTS = 10_000
_MAX_CHUNK_BYTES = 1024 * 1024


class MultimediaGraphEvidenceUnavailable(RuntimeError):
    """Canonical graph search or snapshot storage cannot be read safely."""


class _EvidenceBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MultimediaEvidenceSearchRequest(_EvidenceBase):
    expected_revision_id: str = Field(min_length=1, max_length=128)
    limit: int = Field(default=12, ge=1, le=_MAX_CANDIDATES)


class MultimediaEvidenceCandidate(_EvidenceBase):
    chunk_id: str = Field(min_length=1, max_length=128)
    document_id: str = Field(min_length=1, max_length=128)
    document_title: str = Field(min_length=1, max_length=512)
    section_path: str | None = Field(default=None, max_length=512)
    excerpt: str = Field(min_length=1, max_length=500)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    similarity: float = Field(ge=-1, le=1)


class MultimediaEvidenceSearchResult(_EvidenceBase):
    asset_id: str
    revision_id: str
    query: str = Field(min_length=1, max_length=4096)
    candidates: tuple[MultimediaEvidenceCandidate, ...]


class MultimediaEvidenceSelection(_EvidenceBase):
    chunk_id: str = Field(min_length=1, max_length=128)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class CreateGroundedMultimediaDraftRequest(_EvidenceBase):
    expected_parent_revision_id: str = Field(min_length=1, max_length=128)
    selections: tuple[MultimediaEvidenceSelection, ...] = Field(
        min_length=1, max_length=_MAX_CANDIDATES
    )

    @model_validator(mode="after")
    def selections_are_unique(self) -> CreateGroundedMultimediaDraftRequest:
        ids = tuple(item.chunk_id for item in self.selections)
        if len(set(ids)) != len(ids):
            raise ValueError("multimedia evidence selections must be unique")
        return self


@dataclass(frozen=True)
class MultimediaGraphEvidence:
    db_path: str
    embedding_provider: EmbeddingProvider

    def search(
        self,
        *,
        owner_id: str,
        asset_id: str,
        revision_id: str,
        query: str,
        limit: int,
    ) -> MultimediaEvidenceSearchResult:
        query = " ".join(query.split())
        if not query or len(query) > 4096:
            raise ValueError("multimedia evidence query is invalid")
        if limit < 1 or limit > _MAX_CANDIDATES:
            raise ValueError("multimedia evidence result limit is invalid")
        try:
            with connect_read(self.db_path) as connection:
                document_rows = connection.execute(
                    "SELECT d.document_id FROM documents d "
                    "LEFT JOIN book_assets b ON b.document_id=d.document_id "
                    "WHERE d.owner_user_id=? AND COALESCE(b.taken_down,FALSE)=FALSE "
                    "ORDER BY d.document_id LIMIT ?",
                    [owner_id, _MAX_OWNER_DOCUMENTS + 1],
                ).fetchall()
                if len(document_rows) > _MAX_OWNER_DOCUMENTS:
                    raise MultimediaGraphEvidenceUnavailable(
                        "multimedia owner corpus exceeds its search bound"
                    )
                document_ids = tuple(str(row[0]) for row in document_rows)
                result = search(
                    connection,
                    query,
                    model=self.embedding_provider,
                    top_k=limit,
                    document_ids=document_ids,
                    policy_tag="operator_only",
                    owner_user_id=owner_id,
                )
                hit_ids = tuple(str(hit["chunk_id"]) for hit in result["results"])
                snapshots = _load_snapshots(connection, hit_ids, owner_id=owner_id)
        except MultimediaGraphEvidenceUnavailable:
            raise
        except Exception:
            raise MultimediaGraphEvidenceUnavailable(
                "canonical multimedia evidence search is unavailable"
            ) from None
        candidates = tuple(
            MultimediaEvidenceCandidate(
                chunk_id=chunk_id,
                document_id=snapshots[chunk_id][0],
                document_title=snapshots[chunk_id][1],
                section_path=snapshots[chunk_id][2],
                excerpt=" ".join(snapshots[chunk_id][3].split())[:500],
                text_sha256=_digest(snapshots[chunk_id][3]),
                similarity=float(hit["similarity"]),
            )
            for hit in result["results"]
            for chunk_id in (str(hit["chunk_id"]),)
        )
        return MultimediaEvidenceSearchResult(
            asset_id=asset_id,
            revision_id=revision_id,
            query=query,
            candidates=candidates,
        )

    def resolve(
        self,
        selections: tuple[MultimediaEvidenceSelection, ...],
        *,
        owner_id: str,
    ) -> tuple[EvidenceChunk, ...]:
        chunk_ids = tuple(item.chunk_id for item in selections)
        try:
            with connect_read(self.db_path) as connection:
                snapshots = _load_snapshots(connection, chunk_ids, owner_id=owner_id)
        except (MultimediaGraphEvidenceUnavailable, ValueError):
            raise
        except Exception:
            raise MultimediaGraphEvidenceUnavailable(
                "canonical multimedia evidence is unavailable"
            ) from None
        evidence: list[EvidenceChunk] = []
        for selection in selections:
            document_id, title, section_path, text = snapshots[selection.chunk_id]
            if not hmac.compare_digest(_digest(text), selection.text_sha256):
                raise ValueError("multimedia evidence changed after review")
            evidence.append(
                EvidenceChunk(
                    chunk_id=selection.chunk_id,
                    document_id=document_id,
                    title=title,
                    section_path=section_path or "source",
                    text=text,
                    authority_kind="canonical_graph",
                )
            )
        return tuple(evidence)


def _load_snapshots(
    connection: Any, chunk_ids: tuple[str, ...], *, owner_id: str
) -> dict[str, tuple[str, str, str | None, str]]:
    if not chunk_ids:
        return {}
    if len(set(chunk_ids)) != len(chunk_ids) or len(chunk_ids) > _MAX_CANDIDATES:
        raise ValueError("multimedia evidence chunk identities are invalid")
    placeholders = ",".join("?" for _ in chunk_ids)
    rows = connection.execute(
        "SELECT c.chunk_id,c.document_id,d.title,c.section_path,c.text "
        "FROM chunks c JOIN documents d ON d.document_id=c.document_id "
        "LEFT JOIN book_assets b ON b.document_id=d.document_id "
        f"WHERE c.chunk_id IN ({placeholders}) AND d.owner_user_id=? "
        "AND COALESCE(b.taken_down,FALSE)=FALSE",
        [*chunk_ids, owner_id],
    ).fetchall()
    by_id = {
        str(row[0]): (
            str(row[1]),
            str(row[2] or row[1]),
            None if row[3] is None else str(row[3]),
            str(row[4]),
        )
        for row in rows
    }
    if set(by_id) != set(chunk_ids):
        raise ValueError("multimedia evidence is unavailable for this owner")
    for _document_id, _title, _section, text in by_id.values():
        if not text.strip() or len(text.encode()) > _MAX_CHUNK_BYTES:
            raise ValueError("multimedia evidence text is invalid")
    return by_id


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def load_canonical_multimedia_chunks(
    db_path: str,
    chunk_ids: tuple[str, ...],
    *,
    owner_id: str,
) -> dict[str, CanonicalEvidenceChunk]:
    """Reopen exact owner-scoped graph bytes for a production boundary."""

    try:
        with connect_read(db_path) as connection:
            snapshots = _load_snapshots(connection, chunk_ids, owner_id=owner_id)
    except (MultimediaGraphEvidenceUnavailable, ValueError):
        raise
    except Exception:
        raise MultimediaGraphEvidenceUnavailable(
            "canonical multimedia evidence is unavailable"
        ) from None
    return {
        chunk_id: (snapshots[chunk_id][0], snapshots[chunk_id][3])
        for chunk_id in chunk_ids
    }


__all__ = [
    "CreateGroundedMultimediaDraftRequest",
    "MultimediaEvidenceCandidate",
    "MultimediaEvidenceSearchRequest",
    "MultimediaEvidenceSearchResult",
    "MultimediaEvidenceSelection",
    "MultimediaGraphEvidence",
    "MultimediaGraphEvidenceUnavailable",
    "load_canonical_multimedia_chunks",
]
