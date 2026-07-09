"""Evidence pack product surface — citations + twins as HTML (residual as).

Competitors win on citation trust. Antiek composes shipped source_refs + twin
notes into a single HTML-first evidence pack for the research workstation.
Does not re-fetch publications (see hydrate) or invent sources.
"""

from __future__ import annotations

from typing import Any

from .project import project_to_html
from .source_refs import list_source_references, source_references_html
from .store import EngagementStore
from .twin import list_twin_notes


def evidence_pack_payload(
    asset_id: str,
    *,
    store: EngagementStore,
    spawn_id: str | None = None,
    include_html: bool = True,
) -> dict[str, Any]:
    """Assemble evidence pack from twins + optional spawn source refs.

    Residual (kc): when ``spawn_id`` is set, include reserved ``research_tier``
    so citation-trust surfaces can show depth posture (default deep).
    """
    from substrate.dispatch.research_tier import normalize_research_tier

    if not asset_id.strip():
        raise ValueError("asset_id is required")
    twins = list_twin_notes(asset_id, store=store)
    refs = list_source_references(spawn_id, store=store) if spawn_id else []
    # Also collect refs from any spawns if spawn_id omitted? keep explicit.
    insights = [t for t in twins if t.kind == "insight"]
    questions = [t for t in twins if t.kind == "question"]
    research_tier = None
    if spawn_id:
        row = store.get_spawn(spawn_id) or {}
        research_tier = normalize_research_tier(row.get("research_tier"))
    payload: dict[str, Any] = {
        "asset_id": asset_id,
        "spawn_id": spawn_id,
        "insight_count": len(insights),
        "question_count": len(questions),
        "ref_count": len(refs),
        "insights": [t.text for t in insights],
        "questions": [t.text for t in questions],
        "source_references": [r.to_dict() for r in refs],
        "research_tier": research_tier,
        "view_format": "html",
        "product_panel": "evidence_pack",
        "source": "engagement_spine.evidence",
        "notes": [],
    }
    if not twins and not refs:
        payload["notes"] = [
            "Empty evidence pack — record twin notes or attach arxiv/substack refs."
        ]
    if include_html:
        payload["html"] = project_evidence_html(payload, refs_html_fn=lambda: (
            source_references_html(refs) if refs else ""
        ))
    return payload


def project_evidence_html(
    payload: dict[str, Any],
    *,
    refs_html_fn: Any = None,
) -> str:
    asset_id = str(payload.get("asset_id") or "")
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Evidence pack"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Asset {asset_id} · insights={payload.get('insight_count')} · "
                        f"questions={payload.get('question_count')} · "
                        f"refs={payload.get('ref_count')} · view: HTML"
                    ),
                }
            ],
        },
    ]
    for text in payload.get("insights") or []:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Insight: {text}"}],
            }
        )
    for text in payload.get("questions") or []:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Question: {text}"}],
            }
        )
    for ref in payload.get("source_references") or []:
        if not isinstance(ref, dict):
            continue
        label = f"[{ref.get('kind')}] {ref.get('canonical_url') or ref.get('raw')}"
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"Source: {label}"}],
            }
        )
    if len(blocks) == 2:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(no evidence items yet)"}],
            }
        )
    html = project_to_html(
        {"type": "doc", "content": blocks},
        document_id=f"evidence-{asset_id}",
        creator="engagement_spine.evidence",
    )
    if html.lstrip().lower().startswith("%pdf"):
        raise RuntimeError("PDF is not a valid evidence view surface")
    # Optional append of existing source_refs HTML fragment is skipped to keep
    # one coherent document; refs are already listed above.
    _ = refs_html_fn
    return html
