"""Owner-scoped lexical retrieval over immutable derived HTML revisions."""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any, Final

from runtime.db_lock import connect_read
from substrate.research_artifact.derived_asset_library import DerivedAssetLibrary
from substrate.research_artifact.derived_html_index import (
    DerivedHtmlChunk,
    chunks_for_policy,
    index_sha256,
    revision_chunk_id,
)

MAX_QUERY_BYTES: Final = 8 * 1024
MAX_RESULTS: Final = 12
_TERM = re.compile(r"[\w]+", re.UNICODE)


class DerivedAssetRetrievalIntegrity(RuntimeError):
    pass


def search_derived_asset(
    *,
    db_path: str,
    owner_user_id: str,
    asset_id: str,
    query: str,
    revision_id: str | None = None,
    top_k: int = 6,
) -> dict[str, Any]:
    if (
        not isinstance(query, str)
        or not query.strip()
        or len(query.encode("utf-8")) > MAX_QUERY_BYTES
        or not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or not 1 <= top_k <= MAX_RESULTS
    ):
        raise ValueError("invalid derived asset retrieval request")
    reading = DerivedAssetLibrary(db_path=db_path).reading(
        owner_user_id, asset_id, revision_id
    )
    selected_revision = str(reading["revision_id"])
    content_sha256 = str(reading["content_sha256"])
    with connect_read(db_path) as con:
        rows = con.execute(
            "SELECT chunk_ordinal,citation_id,member_index,section_anchor,section_path,"
            "chunk_text,chunk_text_sha256,token_count,chunker_policy,chunker_version "
            "FROM derived_asset_revision_chunks WHERE derived_asset_id=? AND revision_id=? "
            "AND revision_content_sha256=? ORDER BY chunk_ordinal",
            [asset_id, selected_revision, content_sha256],
        ).fetchall()
        receipt = con.execute(
            "SELECT revision_content_sha256,chunk_count,index_sha256,chunker_policy,chunker_version "
            "FROM derived_asset_revision_indexes WHERE derived_asset_id=? AND revision_id=?",
            [asset_id, selected_revision],
        ).fetchone()
    chunks = tuple(
        DerivedHtmlChunk(
            ordinal=int(row[0]),
            member_index=int(row[2]),
            section_anchor=str(row[3]),
            section_path=str(row[4]),
            text=str(row[5]),
            text_sha256=str(row[6]),
            token_count=int(row[7]),
        )
        for row in rows
    )
    if receipt is None:
        raise DerivedAssetRetrievalIntegrity("derived revision index integrity conflict")
    stored_policy, stored_version = str(receipt[3]), str(receipt[4])
    try:
        expected_chunks = chunks_for_policy(
            stored_policy, stored_version, str(reading["canonical_html"])
        )
    except ValueError as exc:
        raise DerivedAssetRetrievalIntegrity(
            "derived revision index integrity conflict"
        ) from exc
    expected_receipt = (
        content_sha256,
        len(expected_chunks),
        index_sha256(expected_chunks),
        stored_policy,
        stored_version,
    )
    if (
        receipt != expected_receipt
        or chunks != expected_chunks
        or any(
            row[0] != index
            or row[1] != revision_chunk_id(
                asset_id=asset_id,
                revision_id=selected_revision,
                content_sha256=content_sha256,
                chunker_policy=stored_policy,
                chunker_version=stored_version,
                chunk=chunks[index],
            )
            or row[8] != stored_policy
            or row[9] != stored_version
            for index, row in enumerate(rows)
        )
    ):
        raise DerivedAssetRetrievalIntegrity("derived revision index integrity conflict")

    query_terms = Counter(_tokens(query))
    phrase = " ".join(_tokens(query))
    scored: list[tuple[float, int, tuple[Any, ...]]] = []
    for row in rows:
        text_terms = Counter(_tokens(str(row[5])))
        overlap = sum(min(count, text_terms[term]) for term, count in query_terms.items())
        if overlap == 0:
            continue
        score = overlap / math.sqrt(max(1, sum(text_terms.values())))
        if phrase and phrase in " ".join(_tokens(str(row[5]))):
            score += 1.0
        scored.append((score, int(row[0]), row))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return {
        "derived_asset_id": asset_id,
        "revision_id": selected_revision,
        "content_sha256": content_sha256,
        "generation": int(reading["generation"]),
        "is_current": bool(reading["is_current"]),
        "retrieval_mode": "deterministic_lexical_v1",
        "index_sha256": str(receipt[2]),
        "chunker_policy": stored_policy,
        "chunker_version": stored_version,
        "query": query.strip(),
        "results": [
            {
                "citation_id": str(row[1]),
                "chunk_ordinal": int(row[0]),
                "member_index": int(row[2]),
                "section_anchor": str(row[3]),
                "section_path": str(row[4]),
                "text": str(row[5]),
                "text_sha256": str(row[6]),
                "score": round(score, 8),
            }
            for score, _ordinal, row in scored[:top_k]
        ],
    }


def _tokens(value: str) -> list[str]:
    return [term.casefold() for term in _TERM.findall(value)]


__all__ = ["DerivedAssetRetrievalIntegrity", "search_derived_asset"]
