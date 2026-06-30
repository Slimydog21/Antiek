"""RDR SPR-07 M3 — persist the cascade synthesis artifact as a graph Document.

Invoked from ``cascade_session.join_and_merge`` after the promotion funnel
drains. Builds a structured SPR-02 ``Document`` with first-class
``CitationSpan`` markers, persists via the single sanctioned graph writer, and
returns the artifact id for ``cites`` edge wiring.

INERT-AI caveat: live synthesizer dispatch (``interfaces/research/api/synthesizer.py``)
awaits activation SPR-03 provider keys. The cassette / keyless path assembles a
deterministic report from promoted findings — persistence + edges are still real.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from substrate.constants import PERSONAL_READING_CONTENT_CLASS
from substrate.contracts.document_model import (
    CitationSpan,
    DOCUMENT_MODEL_SCHEMA_VERSION,
    Document,
    DocumentAttribution,
    HeadingBlock,
    ParagraphBlock,
    TextSpan,
)
from substrate.graph.ops import insert_document

from runtime.research_runner.provenance_ingest import (
    PromotionProvenanceState,
    ResolvedSource,
    write_artifact_cites_edges,
)


@dataclass(frozen=True)
class CascadeArtifactResult:
    artifact_document_id: str
    title: str
    cited_source_count: int


def cascade_artifact_document_id(session_id: str) -> str:
    """Stable artifact id for a cascade session."""
    h = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]
    return f"doc-cascade-artifact-{h}"


def _build_artifact_document(
    *,
    document_id: str,
    session_id: str,
    findings: list[dict[str, Any]],
    cited_sources: list[ResolvedSource],
) -> Document:
    """Build a structured Document with ``CitationSpan`` markers (SPR-03/07)."""
    title = f"Research synthesis — {session_id}"
    blocks: list = [
        HeadingBlock(level=1, spans=[TextSpan(text=title)]),
    ]
    marker_index = 0
    source_index: dict[tuple[str, str], int] = {}

    def _marker_for(src: ResolvedSource) -> str:
        nonlocal marker_index
        if not src.chunk_id:
            return ""
        key = (src.document_id, src.chunk_id)
        if key not in source_index:
            marker_index += 1
            source_index[key] = marker_index
        return f"[{source_index[key]}]"

    for i, finding in enumerate(findings, start=1):
        text = str(finding.get("text") or "").strip()
        if not text:
            continue
        spans: list = [TextSpan(text=text)]
        sources: list[ResolvedSource] = finding.get("sources") or []
        for src in sources:
            m = _marker_for(src)
            if m and src.chunk_id:
                spans.append(
                    CitationSpan(
                        source_document_id=src.document_id,
                        chunk_id=src.chunk_id,
                        marker=m,
                    )
                )
        blocks.append(HeadingBlock(level=2, spans=[TextSpan(text=f"Finding {i}")]))
        blocks.append(ParagraphBlock(spans=spans))

    if cited_sources:
        blocks.append(HeadingBlock(level=2, spans=[TextSpan(text="Sources")]))
        for src in cited_sources:
            if not src.chunk_id or src.ingest_skipped:
                continue
            m = _marker_for(src)
            label = src.url or src.document_id
            blocks.append(
                ParagraphBlock(spans=[
                    TextSpan(text=f"{m} "),
                    CitationSpan(
                        source_document_id=src.document_id,
                        chunk_id=src.chunk_id,
                        marker=m,
                    ),
                    TextSpan(text=f" {label}"),
                ]),
            )

    return Document(
        id=document_id,
        title=title,
        blocks=blocks,
        schema_version=DOCUMENT_MODEL_SCHEMA_VERSION,
        attribution=DocumentAttribution(
            source_url=f"cascade://{session_id}",
        ),
    )


def _flat_text(doc: Document) -> str:
    lines: list[str] = []
    for block in doc.blocks:
        if hasattr(block, "spans"):
            parts = []
            for span in block.spans:
                if hasattr(span, "text"):
                    parts.append(span.text)
                elif hasattr(span, "marker"):
                    parts.append(span.marker)
            lines.append("".join(parts))
    return "\n\n".join(lines)


def persist_cascade_synthesis_artifact(
    con: Any,
    *,
    session_id: str,
    investigation_id: str,
    provenance_state: PromotionProvenanceState,
    embedding_provider: Any | None = None,
    plan_title: str | None = None,
) -> CascadeArtifactResult | None:
    """Persist the session synthesis report + ``cites`` edges. Returns None when
    there is nothing to synthesize (no findings)."""
    findings = provenance_state.findings
    if not findings:
        return None

    all_sources: list[ResolvedSource] = []
    seen: set[tuple[str, str]] = set()
    for inv_sources in provenance_state.resolved_by_investigation.values():
        for src in inv_sources:
            if not src.chunk_id or src.ingest_skipped:
                continue
            key = (src.document_id, src.chunk_id)
            if key in seen:
                continue
            seen.add(key)
            all_sources.append(src)

    document_id = cascade_artifact_document_id(session_id)
    doc = _build_artifact_document(
        document_id=document_id,
        session_id=session_id,
        findings=findings,
        cited_sources=all_sources,
    )
    flat = _flat_text(doc)
    structured_json = doc.model_dump_json()

    insert_document(
        con,
        document_id=document_id,
        source_tier=3,
        document_type="research_memo",
        source_uri=f"cascade://{session_id}",
        title=doc.title,
        investigation_id=investigation_id,
        raw_text=flat,
        structured_blocks=structured_json,
        # Deny-by-default: synthesis over fetched web sources is owner-readable,
        # NOT public-servable until the operator resolves the legal gate.
        content_class=PERSONAL_READING_CONTENT_CLASS,
        metadata={
            "cascade_session_id": session_id,
            "finding_count": len(findings),
            "plan_title": plan_title,
        },
        on_conflict="ignore",
    )
    write_artifact_cites_edges(
        con,
        artifact_document_id=document_id,
        artifact_title=doc.title or document_id,
        cited_sources=all_sources,
        investigation_id=investigation_id,
        embedding_provider=embedding_provider,
    )
    return CascadeArtifactResult(
        artifact_document_id=document_id,
        title=doc.title or document_id,
        cited_source_count=len(all_sources),
    )