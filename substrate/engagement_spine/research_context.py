"""Compose twin-derived units + spawn source refs into one research context pack.

After residual (o) twin promote and (p) source-ref attach, this is the
workstation moment: given a parent asset + optional spawn, assemble the
insight/question substrate and citeable publication handles for the next
prompt — pure, offline, HTML-first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from .source_refs import (
    SourceReference,
    filter_references,
    list_source_references,
    refs_from_rows,
    source_references_html,
)
from .store import EngagementStore
from .twin_promote import (
    TwinContextUnit,
    TwinPromoteContextResult,
    promote_and_context_for_asset,
    twin_context_html,
)


@dataclass(frozen=True)
class ResearchContextPack:
    """Assembled research context for an asset / spawn."""

    asset_id: str
    spawn_id: str | None
    investigation_id: str | None
    twin_units: tuple[TwinContextUnit, ...]
    source_references: tuple[SourceReference, ...]
    query: str | None = None
    view_format: str = "html"
    # Residual (kk): reserved spawn research_tier when spawn_id set (default deep).
    research_tier: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "spawn_id": self.spawn_id,
            "investigation_id": self.investigation_id,
            "twin_units": [u.to_dict() for u in self.twin_units],
            "source_references": [r.to_dict() for r in self.source_references],
            "query": self.query,
            "view_format": self.view_format,
            "twin_count": len(self.twin_units),
            "ref_count": len(self.source_references),
            "research_tier": self.research_tier,
        }

    def prompt_block(self, *, max_twins: int = 12, max_refs: int = 12) -> str:
        """Compact text block suitable for injection into a research prompt."""
        lines: list[str] = [
            f"# Research context for asset `{self.asset_id}`",
        ]
        if self.spawn_id:
            lines.append(f"spawn: {self.spawn_id}")
        if self.research_tier:
            lines.append(f"research_tier: {self.research_tier}")
        if self.investigation_id:
            lines.append(f"investigation: {self.investigation_id}")
        if self.query:
            lines.append(f"query filter: {self.query}")

        lines.append("")
        lines.append("## Twin-derived insights & questions")
        if not self.twin_units:
            lines.append("(none)")
        else:
            for u in self.twin_units[:max_twins]:
                lines.append(f"- [{u.kind}] ({u.unit_id}) {u.text}")

        lines.append("")
        lines.append("## Source references (arxiv / substack / url)")
        if not self.source_references:
            lines.append("(none)")
        else:
            for r in self.source_references[:max_refs]:
                cite = r.canonical_url or r.raw
                eid = f" id={r.external_id}" if r.external_id else ""
                lines.append(f"- [{r.kind}]{eid} {cite}")

        return "\n".join(lines) + "\n"


def assemble_research_context(
    asset_id: str,
    *,
    store: EngagementStore,
    spawn_id: str | None = None,
    query: str | None = None,
    investigation_id: str | None = None,
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
    embedding_provider: Any = None,
    con: Any = None,
    include_twin_promote: bool = True,
) -> ResearchContextPack:
    """Product entry: twin promote/search + spawn source refs → one pack.

    When ``include_twin_promote`` is True, promotes twin notes for the asset
    (injectable promote hooks supported). Source refs are always read from
    the spawn row when ``spawn_id`` is set.
    """
    if not asset_id or not asset_id.strip():
        raise ValueError("asset_id is required")
    aid = asset_id.strip()

    twin_units: tuple[TwinContextUnit, ...] = ()
    inv = investigation_id
    if include_twin_promote:
        pack: TwinPromoteContextResult = promote_and_context_for_asset(
            aid,
            store=store,
            query=query,
            investigation_id=investigation_id,
            promote_insight_fn=promote_insight_fn,
            promote_question_fn=promote_question_fn,
            embedding_provider=embedding_provider,
            con=con,
        )
        twin_units = pack.context_units
        if inv is None and pack.promoted:
            inv = pack.promoted[0].investigation_id

    refs: tuple[SourceReference, ...] = ()
    research_tier: str | None = None
    sid = (spawn_id or "").strip() or None
    if sid:
        from substrate.dispatch.research_tier import normalize_research_tier

        listed = list_source_references(sid, store=store)
        if query:
            listed = filter_references(listed, query=query)
        refs = tuple(listed)
        row = store.get_spawn(sid)
        if row:
            # Residual (kk): surface reserved spawn research_tier on pack.
            research_tier = normalize_research_tier(row.get("research_tier"))
            # Fall back to investigation from spawn row if still unknown
            if inv is None:
                inv = row.get("investigation_id")
                # If no filter applied above and row has refs, prefer row order
                if not refs and not query:
                    refs = refs_from_rows(row.get("source_references"))

    return ResearchContextPack(
        asset_id=aid,
        spawn_id=sid,
        investigation_id=inv,
        twin_units=twin_units,
        source_references=refs,
        query=query,
        view_format="html",
        research_tier=research_tier,
    )


def research_context_html(pack: ResearchContextPack) -> str:
    """HTML-first combined view of twin units + source references."""
    from .project import project_to_html

    # Prefer composed single document for the pack header + both sections
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [
                {
                    "type": "text",
                    "text": f"Research context — {pack.asset_id}",
                }
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"twins={len(pack.twin_units)} refs={len(pack.source_references)}"
                        + (
                            f" · tier={pack.research_tier}"
                            if pack.research_tier
                            else ""
                        )
                        + (f" query={pack.query}" if pack.query else "")
                    ),
                }
            ],
        },
    ]
    for u in pack.twin_units:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[twin:{u.kind}] {u.text}",
                    }
                ],
            }
        )
    for r in pack.source_references:
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"[ref:{r.kind}] {r.canonical_url or r.raw}",
                    }
                ],
            }
        )
    if not pack.twin_units and not pack.source_references:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(empty research context)"}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"research-ctx-{pack.asset_id}",
        creator="research_context",
    )


def research_context_sections_html(pack: ResearchContextPack) -> dict[str, str]:
    """Optional split projections (still HTML-first, never PDF)."""
    return {
        "combined": research_context_html(pack),
        "twins": twin_context_html(pack.twin_units),
        "references": source_references_html(pack.source_references),
    }
