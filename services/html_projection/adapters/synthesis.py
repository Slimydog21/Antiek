"""Synthesis → doc-model adapter (HPRJ SPR-05 M2 + M4).

Maps a resolved synthesis (its metadata + claims, each claim carrying its
claim→chunk→document provenance) into the doc-model JSON the SPR-02
renderer accepts. Two responsibilities the master spec puts HERE and
nowhere else:

1. **Rights filtering (M2).** The filter lives in this adapter, so no caller
   can bypass it by handing unfiltered third-party text to the renderer. A
   source's chunk text is EMBEDDED (as an ``antiek_note`` block) only when
   ``content_class in substrate.constants.SERVABLE_CONTENT_CLASSES`` — the
   exact allowlist the read-side ``graph/search.py`` gate uses; we REUSE it,
   we do not reimplement the rights vocabulary. Everything else
   (``personal_reading``, ``restricted_pending_opt_in``, NULL, unrecognised)
   is **cite-only**: a structured pointer (title · ip_holder · locator) with
   the chunk text **absent from the serialized doc-model entirely** — not
   merely hidden in the rendered HTML (the island would otherwise carry the
   leaked text). An export IS public serving; cite-only is the default on
   any doubt. A synthesis-level restriction raises ``RightsRefusal`` (the
   route turns it into a 403 with reason) rather than shipping a 200 with
   silently omitted content, because a silent omission reads as "this is the
   whole synthesis" and that is a lie.

2. **Provenance-completeness gate (M4).** Older rows may predate full
   provenance. The adapter counts how many claims are fully sourced and, when
   incomplete, emits an honest "provenance incomplete — N of M claims fully
   sourced" banner; an unsourced claim renders with a visible "(unsourced)"
   marker rather than fabricated citation density.

The synthesis's own output (target question, thesis, recommendation,
attribution manifest, model + parameter versions) is operator-authored
research and rides in the doc-model ``metadata`` (preserved in the island);
it is NOT third-party text and is not rights-filtered. The attribution
manifest carries only ip_holder identity (never chunk text or embeddings).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from substrate.constants import SERVABLE_CONTENT_CLASSES


class RightsRefusal(Exception):
    """A synthesis-level restriction denies the whole export. The route maps
    this to a 403 with a structured reason — never a 200 with omitted text."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


@dataclass(frozen=True)
class SourceRef:
    """One resolved claim→chunk→document link. ``chunk_text`` is the quoted
    passage; it is embedded ONLY when the document is servable."""

    document_id: str | None
    document_title: str | None
    content_class: str | None
    ip_holder_id: str | None
    locator: str | None = None
    chunk_text: str | None = None

    @property
    def servable(self) -> bool:
        # REUSED allowlist — the single source of rights truth.
        return self.content_class in SERVABLE_CONTENT_CLASSES

    @property
    def resolved(self) -> bool:
        # Ties to a real document → counts toward provenance completeness.
        return bool(self.document_id)


@dataclass(frozen=True)
class Claim:
    statement: str
    sources: list[SourceRef] = field(default_factory=list)

    @property
    def fully_sourced(self) -> bool:
        return bool(self.sources) and all(s.resolved for s in self.sources)


@dataclass(frozen=True)
class SynthesisExport:
    """The resolved synthesis the adapter consumes. The M3 route builds this
    from the live graph (reusing ``compute_attribution_for_synthesis`` +
    chunk/document resolution); the adapter stays pure + DB-free + testable."""

    synthesis_id: str
    target_question: str
    thesis_text: str | None = None
    recommendation: str | None = None
    restricted: bool = False
    restriction_reason: str | None = None
    model_versions: dict[str, Any] = field(default_factory=dict)
    parameters: dict[str, Any] = field(default_factory=dict)
    attribution_manifest: dict[str, Any] = field(default_factory=dict)
    claims: list[Claim] = field(default_factory=list)


# ── doc-model node builders (existing SPR-02 renderer node types) ──


def _prose(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def _claim_card(statement: str) -> dict[str, Any]:
    return {"type": "antiek_claim_card", "attrs": {"statement": statement}}


def _cite_link(label: str, target: str | None) -> dict[str, Any]:
    attrs: dict[str, Any] = {"label": label}
    if target:
        attrs["target_url"] = target
    return {"type": "antiek_cite_link", "attrs": attrs}


def _note(body: str) -> dict[str, Any]:
    return {"type": "antiek_note", "attrs": {"body": body}}


_RECOMMENDATION_TONE = {
    "proceed": "success",
    "pass": "danger",
    "conditional": "warning",
    "undetermined": "neutral",
    "insufficient_evidence": "neutral",
}


def _stat_chip(label: str, value: str, tone: str) -> dict[str, Any]:
    # An SPR-03 widget via the wired antiek_widget seam.
    return {
        "type": "antiek_widget",
        "attrs": {"kind": "stat_chip", "label": label, "value": value, "tone": tone},
    }


def _recommendation_tone(rec: str) -> str:
    return _RECOMMENDATION_TONE.get(str(rec).lower(), "neutral")


def _source_label(src: SourceRef) -> str:
    """A citation label built ONLY from non-text provenance — title, owner,
    locator. NEVER the chunk text (that would defeat cite-only)."""
    parts = [src.document_title or src.document_id or "unknown source"]
    if src.ip_holder_id:
        parts.append(src.ip_holder_id)
    if src.locator:
        parts.append(src.locator)
    return " · ".join(parts)


# ── adapter ──


def adapt_synthesis(export: SynthesisExport) -> dict[str, Any]:
    """Adapt a resolved synthesis to the doc-model. Raises ``RightsRefusal``
    on a synthesis-level restriction."""
    if export.restricted:
        raise RightsRefusal(
            export.restriction_reason or "synthesis is restricted from export"
        )

    total = len(export.claims)
    fully = sum(1 for c in export.claims if c.fully_sourced)
    complete = total > 0 and fully == total

    content: list[dict[str, Any]] = []

    # M4: honest provenance banner at the top when incomplete.
    if not complete and total > 0:
        content.append(
            _prose(f"Provenance incomplete — {fully} of {total} claims fully sourced.")
        )

    # A recommendation stat-chip (SPR-03 widget via the wired antiek_widget
    # seam) — the synthesis's OWN output, rights-safe (metadata, never
    # third-party passage text).
    if export.recommendation:
        content.append(
            _stat_chip(
                "Recommendation",
                export.recommendation,
                _recommendation_tone(export.recommendation),
            )
        )

    # The synthesis's own output (operator-authored; not third-party text).
    if export.thesis_text:
        content.append(_claim_card(export.thesis_text))

    for claim in export.claims:
        content.append(_claim_card(claim.statement))
        if not claim.sources:
            content.append(_prose("(unsourced)"))
            continue
        for src in claim.sources:
            content.append(_cite_link(_source_label(src), src.locator))
            if src.servable and src.chunk_text:
                # EMBED the quoted passage — servable only.
                content.append(_note(src.chunk_text))
            elif not src.servable:
                # CITE-ONLY: visible marker; the chunk text is NEVER emitted.
                content.append(
                    _prose("(cite-only — full text withheld under the source's rights)")
                )
            if not src.resolved:
                content.append(_prose("(unsourced)"))

    # Knowledge-graph edges: this synthesis CITES each unique source document.
    # Rights-safe — a citation (document id + title), NEVER the passage text;
    # the same title/id the cite-only marker already shows for a non-servable
    # source. The graph_widget_node visualizes these in the artifact.
    cited: dict[str, tuple[str, bool]] = {}
    for claim in export.claims:
        for src in claim.sources:
            if src.document_id and src.document_id not in cited:
                cited[src.document_id] = (
                    src.document_title or src.document_id,
                    src.servable,
                )

    return {
        "title": export.target_question,
        "content": content,
        "edges": [
            {
                "kind": "cites",
                "to_document_id": doc_id,
                "to_title": title,
                # Rights-aware tone: a servable source reads green, a cite-only
                # one amber — the graph is a visual rights map.
                "tone": "success" if servable else "warning",
            }
            for doc_id, (title, servable) in cited.items()
        ],
        "metadata": {
            "synthesis_id": export.synthesis_id,
            "recommendation": export.recommendation,
            "model_versions": export.model_versions,
            "parameters": export.parameters,
            "attribution_manifest": export.attribution_manifest,
            "provenance": {
                "fully_sourced": fully,
                "total": total,
                "complete": complete,
            },
        },
    }


__all__ = [
    "Claim",
    "RightsRefusal",
    "SourceRef",
    "SynthesisExport",
    "adapt_synthesis",
]
