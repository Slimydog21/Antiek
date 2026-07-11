"""Load investigation question + synthesis excerpt from trajectory (read-only)."""

from __future__ import annotations

import duckdb

from substrate.event_log import trajectory
from substrate.schemas.events import ActionType

from .schema import (
    MAX_ARTIFACT_CLAIMS,
    MAX_CITATIONS_PER_CLAIM,
    ArtifactCitation,
    ArtifactClaim,
)


def problem_question_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> str:
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.INVESTIGATION_START_REQUESTED.value:
            continue
        payload = row.get("payload") or {}
        if isinstance(payload, dict):
            q = (payload.get("question") or "").strip()
            if q:
                return q
    return ""


def synthesis_from_events(
    investigation_id: str,
    *,
    events_dir: str | None = None,
) -> tuple[str | None, bool, list[str]]:
    """Return (excerpt, withheld_flag, source_event_ids).

    withheld_flag is True when we only have a completion event but no body
    should be shown (caller treats like §9.0 guard — excerpt stays None).
    """
    source_ids: list[str] = []
    excerpt: str | None = None
    for row in trajectory(investigation_id, events_dir=events_dir):
        at = row.get("action_type")
        eid = row.get("event_id")
        if eid:
            source_ids.append(str(eid))
        if at == ActionType.INVESTIGATION_COMPLETED.value:
            payload = row.get("payload") or {}
            if isinstance(payload, dict):
                summary = (payload.get("thesis_summary") or "").strip()
                if summary:
                    excerpt = summary
        if at == ActionType.SYNTHESIS_ARCHIVED.value:
            payload = row.get("payload") or {}
            if isinstance(payload, dict) and not excerpt:
                excerpt = (payload.get("thesis_summary") or payload.get("summary") or "").strip() or None
    # De-dupe while preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for x in source_ids:
        if x not in seen:
            seen.add(x)
            ordered.append(x)
    return excerpt, False, ordered[-20:]


def claims_from_events(
    investigation_id: str,
    *,
    db_path: str | None = None,
    events_dir: str | None = None,
) -> list[ArtifactClaim]:
    """Resolve the latest typed thesis components without source text."""
    components: object = None
    for row in trajectory(investigation_id, events_dir=events_dir):
        if row.get("action_type") != ActionType.SYNTHESIZE_DELIVERED.value:
            continue
        payload = row.get("payload")
        if type(payload) is dict and type(payload.get("thesis_components")) is list:
            components = payload["thesis_components"]
    if type(components) is not list:
        return []
    if len(components) > MAX_ARTIFACT_CLAIMS:
        raise ValueError("synthesis exceeds the ResearchArtifact claim bound")

    cited_ids: set[str] = set()
    for component in components:
        if type(component) is not dict:
            continue
        ids = component.get("supporting_chunk_ids")
        if type(ids) is list:
            if len(ids) > MAX_CITATIONS_PER_CLAIM:
                raise ValueError("synthesis claim exceeds the citation bound")
            if any(type(value) is not str or not value or len(value) > 512 for value in ids):
                raise ValueError("synthesis claim contains an invalid citation id")
            cited_ids.update(value for value in ids if type(value) is str)

    graph: dict[str, ArtifactCitation] = {}
    if cited_ids:
        from runtime.db_lock import connect_read
        from substrate.graph import default_db_path

        try:
            with connect_read(db_path or default_db_path()) as con:
                placeholders = ",".join("?" for _ in cited_ids)
                rows = con.execute(
                    "SELECT c.chunk_id,d.document_id,d.title,d.content_class,"
                    "d.source_tier FROM chunks c JOIN documents d "
                    "ON d.document_id=c.document_id "
                    f"WHERE c.chunk_id IN ({placeholders})",
                    sorted(cited_ids),
                ).fetchall()
            graph = {
                row[0]: ArtifactCitation(
                    citation_id=row[0],
                    resolution="graph",
                    document_id=row[1],
                    title=row[2],
                    rights_class=row[3],
                    source_tier=row[4],
                    locator=f"/read/{row[1]}",
                )
                for row in rows
            }
        except (duckdb.Error, OSError, RuntimeError):
            graph = {}

    from orchestration.loop_one.federated_span_registry import span_registry_from_trajectory

    spans = span_registry_from_trajectory(investigation_id, events_dir=events_dir)
    claims: list[ArtifactClaim] = []
    for component in components:
        if type(component) is not dict or type(component.get("claim")) is not str:
            continue
        raw_ids = component.get("supporting_chunk_ids")
        ids = [value for value in raw_ids if type(value) is str] if type(raw_ids) is list else []
        citations: list[ArtifactCitation] = []
        for citation_id in ids:
            graph_citation = graph.get(citation_id)
            if graph_citation is not None:
                citations.append(graph_citation)
                continue
            span = spans.get(citation_id)
            if span is not None:
                citations.append(
                    ArtifactCitation(
                        citation_id=citation_id,
                        resolution="federated",
                        external_source_id=span.corpus_id,
                        title=span.origin_ref,
                        source_kind=span.source_kind,
                        rights_class=span.license_class,
                        retrieved_at=span.retrieved_at,
                        source_tier=span.source_tier,
                    )
                )
            else:
                citations.append(
                    ArtifactCitation(citation_id=citation_id, resolution="unresolved")
                )
        claims.append(ArtifactClaim(statement=component["claim"], cited_ids=ids, citations=citations))
    return claims
