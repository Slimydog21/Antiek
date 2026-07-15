"""Server-side admission for derived citations entering recursive research."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from runtime.db_lock import connect_read
from substrate.research_artifact.derived_asset_library import (
    DerivedAssetLibrary,
    DerivedAssetUnavailable,
)
from substrate.research_artifact.derived_asset_retrieval import (
    DerivedAssetRetrievalIntegrity,
    search_derived_asset,
)
from substrate.research_artifact.derived_html_index import (
    DerivedHtmlChunk,
    chunks_for_policy,
    index_sha256,
    revision_chunk_id,
)
from substrate.schemas import DerivedCitationSource


class DerivedCitationConflict(RuntimeError):
    pass


MIN_DERIVED_SOURCES: Final = 2
MAX_DERIVED_SOURCES: Final = 6
MAX_DERIVED_CONTEXT_BYTES: Final = 32 * 1024


def canonical_derived_sources_context(
    sources: Sequence[DerivedCitationSource],
) -> str:
    """Validate and render one ordered, same-revision evidence collection."""
    if not MIN_DERIVED_SOURCES <= len(sources) <= MAX_DERIVED_SOURCES:
        raise DerivedCitationConflict("invalid derived citation set size")
    scope = {
        (source.derived_asset_id, source.revision_id, source.content_sha256,
         source.generation)
        for source in sources
    }
    citation_ids = {source.citation_id for source in sources}
    chunks = {(source.chunk_ordinal, source.chunk_text_sha256) for source in sources}
    if len(scope) != 1 or len(citation_ids) != len(sources) or len(chunks) != len(sources):
        raise DerivedCitationConflict("derived citation set identity conflict")
    count = len(sources)
    context = "\n\n".join(
        f"[Evidence {index} of {count}]\n{source.excerpt}"
        for index, source in enumerate(sources, 1)
    )
    if len(context.encode("utf-8")) > MAX_DERIVED_CONTEXT_BYTES:
        raise DerivedCitationConflict("derived citation set is too large")
    return context


def verify_derived_citation_sources(
    *, db_path: str, owner_user_id: str,
    sources: Sequence[DerivedCitationSource],
) -> tuple[DerivedCitationSource, ...]:
    """Verify the complete ordered set before returning any admitted member."""
    admitted = tuple(sources)
    canonical_derived_sources_context(admitted)
    first = admitted[0]
    library = DerivedAssetLibrary(db_path=db_path)
    with connect_read(db_path) as con:
        asset = library._asset_row(con, owner_user_id, first.derived_asset_id)
        current_id, current_hash = str(asset[3]), str(asset[4])
        revisions = library._verify_chain(
            con, first.derived_asset_id, current_id, current_hash
        )
        selected = next(
            (revision for revision in revisions
             if revision.revision_id == first.revision_id), None
        )
        if selected is None:
            raise DerivedAssetUnavailable
        generation = len(revisions) - revisions.index(selected)
        if (selected.content_sha256 != first.content_sha256
                or generation != first.generation):
            raise DerivedCitationConflict("derived citation revision identity conflict")
        rows = con.execute(
            "SELECT chunk_ordinal,citation_id,member_index,section_anchor,section_path,"
            "chunk_text,chunk_text_sha256,token_count,chunker_policy,chunker_version "
            "FROM derived_asset_revision_chunks WHERE derived_asset_id=? AND revision_id=? "
            "AND revision_content_sha256=? ORDER BY chunk_ordinal",
            [first.derived_asset_id, first.revision_id, first.content_sha256],
        ).fetchall()
        receipt = con.execute(
            "SELECT revision_content_sha256,chunk_count,index_sha256,chunker_policy,"
            "chunker_version FROM derived_asset_revision_indexes "
            "WHERE derived_asset_id=? AND revision_id=?",
            [first.derived_asset_id, first.revision_id],
        ).fetchone()
    if receipt is None:
        raise DerivedAssetRetrievalIntegrity("derived revision index integrity conflict")
    chunks = tuple(DerivedHtmlChunk(
        ordinal=int(row[0]), member_index=int(row[2]), section_anchor=str(row[3]),
        section_path=str(row[4]), text=str(row[5]), text_sha256=str(row[6]),
        token_count=int(row[7]),
    ) for row in rows)
    stored_policy, stored_version = str(receipt[3]), str(receipt[4])
    try:
        expected = chunks_for_policy(
            stored_policy, stored_version, selected.canonical_html
        )
    except ValueError as exc:
        raise DerivedAssetRetrievalIntegrity(
            "derived revision index integrity conflict"
        ) from exc
    if (receipt != (first.content_sha256, len(expected), index_sha256(expected),
                    stored_policy, stored_version)
            or chunks != expected
            or any(row[0] != index or row[8] != stored_policy
                or row[9] != stored_version or row[1] != revision_chunk_id(
                    asset_id=first.derived_asset_id, revision_id=first.revision_id,
                    content_sha256=first.content_sha256, chunker_policy=stored_policy,
                    chunker_version=stored_version, chunk=chunks[index],
                ) for index, row in enumerate(rows))):
        raise DerivedAssetRetrievalIntegrity("derived revision index integrity conflict")
    by_ordinal = {int(row[0]): (row[1], row[6], row[5]) for row in rows}
    for source in admitted:
        if by_ordinal.get(source.chunk_ordinal) != (
            source.citation_id, source.chunk_text_sha256, source.excerpt
        ):
            raise DerivedCitationConflict("derived citation set identity conflict")
    return admitted


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


__all__ = [
    "DerivedCitationConflict", "canonical_derived_sources_context",
    "verify_derived_citation_source", "verify_derived_citation_sources",
]
