"""Server-side admission for derived citations entering recursive research."""

from __future__ import annotations

from runtime.db_lock import connect_read
from substrate.research_artifact.derived_asset_retrieval import search_derived_asset
from substrate.schemas import DerivedCitationSource


class DerivedCitationConflict(RuntimeError):
    pass


def verify_derived_citation_source(
    *, db_path: str, owner_user_id: str, source: DerivedCitationSource
) -> DerivedCitationSource:
    """Reopen the complete immutable index, then resolve one exact chunk."""
    try:
        verified = search_derived_asset(
            db_path=db_path,
            owner_user_id=owner_user_id,
            asset_id=source.derived_asset_id,
            revision_id=source.revision_id,
            query=source.excerpt,
            top_k=1,
        )
    except ValueError as exc:
        raise DerivedCitationConflict("derived citation excerpt is invalid") from exc
    if (verified["revision_id"] != source.revision_id
            or verified["content_sha256"] != source.content_sha256
            or verified["generation"] != source.generation):
        raise DerivedCitationConflict("derived citation revision identity conflict")
    with connect_read(db_path) as con:
        row = con.execute(
            "SELECT citation_id,chunk_text_sha256,chunk_text FROM "
            "derived_asset_revision_chunks WHERE derived_asset_id=? AND revision_id=? "
            "AND revision_content_sha256=? AND chunk_ordinal=?",
            [source.derived_asset_id, source.revision_id, source.content_sha256,
             source.chunk_ordinal],
        ).fetchone()
    if row != (source.citation_id, source.chunk_text_sha256, source.excerpt):
        raise DerivedCitationConflict("derived citation identity conflict")
    return source


__all__ = ["DerivedCitationConflict", "verify_derived_citation_source"]
