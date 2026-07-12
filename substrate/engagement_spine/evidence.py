"""Evidence pack product surface — citations + twins as HTML (residual as).

Competitors win on citation trust. Antiek composes shipped source_refs + twin
notes into a single HTML-first evidence pack for the research workstation.
Does not re-fetch publications (see hydrate) or invent sources.

Residual (air): multi-hop citation chain hops (insights → questions → sources)
for competitive claim→source navigation. Does **not** invent supported_by edges
when none exist — hops are sequential stages with stable anchors only.
"""

from __future__ import annotations

from typing import Any

from .project import project_to_html
from .source_refs import list_source_references, source_references_html
from .store import EngagementStore
from .twin import list_twin_notes


def build_citation_chain_hops(
    insights: list[str] | tuple[str, ...],
    questions: list[str] | tuple[str, ...],
    source_references: list[dict[str, Any]] | tuple[Any, ...],
) -> list[dict[str, Any]]:
    """Build ordered multi-hop citation chain stages for navigation.

    Residual (air): competitive multi-hop UX without inventing per-claim edges.
    Each hop is a stage (insights | questions | sources) with items that have
    stable ``anchor`` ids. ``chain_complete`` is true only when both insights and
    sources are non-empty (questions optional).
    """
    insight_items: list[dict[str, Any]] = []
    for i, text in enumerate(insights or ()):
        t = str(text or "").strip()
        if not t:
            continue
        insight_items.append(
            {
                "hop": "insight",
                "index": i,
                "text": t,
                "anchor": f"evidence-insight-{i}",
            }
        )
    question_items: list[dict[str, Any]] = []
    for i, text in enumerate(questions or ()):
        t = str(text or "").strip()
        if not t:
            continue
        question_items.append(
            {
                "hop": "question",
                "index": i,
                "text": t,
                "anchor": f"evidence-question-{i}",
            }
        )
    source_items: list[dict[str, Any]] = []
    for i, ref in enumerate(source_references or ()):
        if not isinstance(ref, dict):
            continue
        kind = str(ref.get("kind") or "source").strip() or "source"
        raw = str(ref.get("raw") or "").strip()
        url = str(ref.get("canonical_url") or "").strip()
        label = f"[{kind}] {url or raw}".strip()
        if not label or label == f"[{kind}]":
            continue
        source_items.append(
            {
                "hop": "source",
                "index": i,
                "text": label,
                "kind": kind,
                "raw": raw,
                "canonical_url": url,
                "anchor": f"evidence-source-{i}",
            }
        )
    hops: list[dict[str, Any]] = []
    if insight_items:
        hops.append(
            {
                "hop": "insights",
                "label": "Insights (claims)",
                "count": len(insight_items),
                "items": insight_items,
            }
        )
    if question_items:
        hops.append(
            {
                "hop": "questions",
                "label": "Open questions",
                "count": len(question_items),
                "items": question_items,
            }
        )
    if source_items:
        hops.append(
            {
                "hop": "sources",
                "label": "Source references",
                "count": len(source_items),
                "items": source_items,
            }
        )
    return hops


def citation_chain_complete(
    insight_count: int,
    ref_count: int,
) -> bool:
    """True when multi-hop path has both claims and sources (questions optional)."""
    return int(insight_count or 0) > 0 and int(ref_count or 0) > 0


# Residual (apz): closed hop pipeline stages (parity frontend CITATION_HOP_PIPELINE_STAGES).
CITATION_HOP_PIPELINE_STAGES: tuple[str, ...] = ("insights", "questions", "sources")


def citation_hop_pipeline_progress(
    *,
    insight_count: int = 0,
    question_count: int = 0,
    ref_count: int = 0,
    citation_chain: list[dict[str, Any]] | None = None,
    chain_complete: bool | None = None,
) -> dict[str, Any]:
    """Residual (apz): hop pipeline completeness for competitive citation bar.

    Mirrors frontend ``citationHopStageProgress`` — never invents empty hops.
    """
    present: list[str] = []
    chain = citation_chain or []
    for stage in CITATION_HOP_PIPELINE_STAGES:
        hop_row = next(
            (
                h
                for h in chain
                if isinstance(h, dict)
                and str(h.get("hop") or "").lower() == stage
            ),
            None,
        )
        if hop_row is not None:
            count = hop_row.get("count")
            items = hop_row.get("items") or []
            n = (
                int(count)
                if isinstance(count, (int, float)) and count == count
                else len(items)
            )
            if n > 0:
                present.append(stage)
                continue
        # Fall back to pack-level counts when chain omits empty hops.
        pack_counts = {
            "insights": insight_count,
            "questions": question_count,
            "sources": ref_count,
        }
        if int(pack_counts.get(stage) or 0) > 0:
            present.append(stage)
    missing = [s for s in CITATION_HOP_PIPELINE_STAGES if s not in present]
    total = len(CITATION_HOP_PIPELINE_STAGES)
    present_count = len(present)
    complete = (
        chain_complete is True
        or (int(insight_count or 0) > 0 and int(ref_count or 0) > 0)
    )
    return {
        "stages": list(CITATION_HOP_PIPELINE_STAGES),
        "present": present,
        "missing": missing,
        "present_count": present_count,
        "total": total,
        "coverage_ratio": (present_count / total) if total else 0.0,
        "chain_complete": bool(complete),
        "insight_count": int(insight_count or 0),
        "question_count": int(question_count or 0),
        "ref_count": int(ref_count or 0),
    }


def evidence_pack_payload(
    asset_id: str,
    *,
    store: EngagementStore,
    spawn_id: str | None = None,
    include_html: bool = True,
    owner_id: str = "__operator__",
) -> dict[str, Any]:
    """Assemble evidence pack from twins + optional spawn source refs.

    Residual (kc): when ``spawn_id`` is set, include reserved ``research_tier``
    so citation-trust surfaces can show depth posture (default deep).
    Residual (air): includes ``citation_chain`` hops for multi-hop navigation.
    Residual (apz): includes ``citation_hop_pipeline`` completeness summary
    (parity frontend citationHopStageProgress · never invent empty hops).
    """
    from substrate.dispatch.research_tier import normalize_research_tier

    if not asset_id.strip():
        raise ValueError("asset_id is required")
    twins = list_twin_notes(asset_id, store=store, owner_id=owner_id)
    refs = (
        list_source_references(spawn_id, store=store, owner_id=owner_id)
        if spawn_id
        else []
    )
    # Also collect refs from any spawns if spawn_id omitted? keep explicit.
    insights = [t for t in twins if t.kind == "insight"]
    questions = [t for t in twins if t.kind == "question"]
    insight_texts = [t.text for t in insights]
    question_texts = [t.text for t in questions]
    ref_dicts = [r.to_dict() for r in refs]
    research_tier = None
    if spawn_id:
        row = store.get_owned_spawn(spawn_id, owner_id) or {}
        research_tier = normalize_research_tier(row.get("research_tier"))
    chain = build_citation_chain_hops(insight_texts, question_texts, ref_dicts)
    chain_complete = citation_chain_complete(len(insights), len(refs))
    hop_pipeline = citation_hop_pipeline_progress(
        insight_count=len(insights),
        question_count=len(questions),
        ref_count=len(refs),
        citation_chain=chain,
        chain_complete=chain_complete,
    )
    # Residual (aqg): world-class readiness from hops only (stages unknown
    # on evidence surface · never invent multi-stage coverage).
    world_class = competitive_dr_world_class_readiness(
        stage_coverage_ratio=None,
        hop_coverage_ratio=float(hop_pipeline.get("coverage_ratio") or 0),
        stage_is_terminal=None,
    )
    payload: dict[str, Any] = {
        "asset_id": asset_id,
        "spawn_id": spawn_id,
        "insight_count": len(insights),
        "question_count": len(questions),
        "ref_count": len(refs),
        "insights": insight_texts,
        "questions": question_texts,
        "source_references": ref_dicts,
        "citation_chain": chain,
        "chain_complete": chain_complete,
        # Residual (apz): hop pipeline completeness for competitive citation bar.
        "citation_hop_pipeline": hop_pipeline,
        # Residual (aqg): hops known · multi-stage unknown on evidence.
        "world_class_readiness": world_class,
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
    chain = payload.get("citation_chain")
    if not isinstance(chain, list):
        chain = build_citation_chain_hops(
            payload.get("insights") or [],
            payload.get("questions") or [],
            payload.get("source_references") or [],
        )
    chain_complete = bool(payload.get("chain_complete")) or citation_chain_complete(
        int(payload.get("insight_count") or 0),
        int(payload.get("ref_count") or 0),
    )
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
                        f"refs={payload.get('ref_count')}"
                        + (
                            f" · tier={payload.get('research_tier')}"
                            if payload.get("research_tier")
                            else ""
                        )
                        + f" · chain_complete={str(chain_complete).lower()}"
                        + " · view: HTML"
                    ),
                }
            ],
        },
    ]
    # Residual (air): multi-hop nav strip (stage labels only — no invented edges).
    if chain:
        hop_labels = " → ".join(
            f"{h.get('label')}({h.get('count')})"
            for h in chain
            if isinstance(h, dict)
        )
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": f"Citation chain hops: {hop_labels}",
                    }
                ],
            }
        )
    # Residual (aqb): competitive hop pipeline completeness line (parity frontend
    # evidence-citation-hop-pipeline · HostedHtml float apo detection).
    hop_pipe = payload.get("citation_hop_pipeline")
    if not isinstance(hop_pipe, dict):
        hop_pipe = citation_hop_pipeline_progress(
            insight_count=int(payload.get("insight_count") or 0),
            question_count=int(payload.get("question_count") or 0),
            ref_count=int(payload.get("ref_count") or 0),
            citation_chain=chain if isinstance(chain, list) else None,
            chain_complete=chain_complete,
        )
    present_n = int(hop_pipe.get("present_count") or 0)
    total_n = int(hop_pipe.get("total") or len(CITATION_HOP_PIPELINE_STAGES))
    missing = hop_pipe.get("missing") or []
    missing_s = (
        f" · missing={', '.join(str(m) for m in missing)}"
        if missing
        else ""
    )
    complete_s = (
        " · chain complete"
        if hop_pipe.get("chain_complete")
        else ""
    )
    blocks.append(
        {
            "type": "paragraph",
            "attrs": {
                "data-testid": "evidence-citation-hop-pipeline",
            },
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"Competitive citation hops · {present_n}/{total_n}"
                        f"{complete_s}{missing_s} · never invent sources"
                    ),
                }
            ],
        }
    )
    for hop in chain:
        if not isinstance(hop, dict):
            continue
        hop_label = str(hop.get("label") or hop.get("hop") or "hop")
        blocks.append(
            {
                "type": "heading",
                "attrs": {"level": 2},
                "content": [{"type": "text", "text": hop_label}],
            }
        )
        for item in hop.get("items") or []:
            if not isinstance(item, dict):
                continue
            anchor = str(item.get("anchor") or "").strip()
            text = str(item.get("text") or "").strip()
            if not text:
                continue
            prefix = {
                "insight": "Insight",
                "question": "Question",
                "source": "Source",
            }.get(str(item.get("hop") or ""), "Item")
            line = f"{prefix}: {text}"
            if anchor:
                line = f"[{anchor}] {line}"
            blocks.append(
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}],
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


# Residual (aqe): world-class DR bar combining multi-stage × citation hops.
# Mirrors frontend competitiveDrWorldClassReadiness (apu).


def competitive_dr_world_class_readiness(
    *,
    stage_coverage_ratio: float | None = None,
    hop_coverage_ratio: float | None = None,
    stage_is_terminal: bool | None = None,
    stage_ready_threshold: float = 0.6,
    hop_ready_threshold: float = 2 / 3,
) -> dict[str, Any]:
    """Combine multi-stage + hop coverage without inventing unknown halves."""
    stage_ratio = (
        max(0.0, min(1.0, float(stage_coverage_ratio)))
        if stage_coverage_ratio is not None
        else 0.0
    )
    hop_ratio = (
        max(0.0, min(1.0, float(hop_coverage_ratio)))
        if hop_coverage_ratio is not None
        else None
    )
    multi_stage_ready = stage_ratio >= stage_ready_threshold or bool(
        stage_is_terminal
    )
    citation_hops_ready = (
        None if hop_ratio is None else hop_ratio >= hop_ready_threshold
    )
    if multi_stage_ready and citation_hops_ready is True:
        world_class_bar = "multi_stage_and_hops"
    elif multi_stage_ready:
        world_class_bar = "multi_stage"
    else:
        world_class_bar = "incomplete"
    notes: list[str] = []
    notes.append(
        "multi-stage pipeline ready"
        if multi_stage_ready
        else "multi-stage pipeline incomplete (plan→gather→synthesize→cite→terminal)"
    )
    if citation_hops_ready is None:
        notes.append(
            "citation hops unknown · open evidence pack (never invent hops)"
        )
    elif citation_hops_ready:
        notes.append("citation hop pipeline ready (insights→questions→sources)")
    else:
        notes.append("citation hop pipeline incomplete")
    return {
        "multi_stage_ready": multi_stage_ready,
        "citation_hops_ready": citation_hops_ready,
        "stage_coverage_ratio": stage_ratio,
        "hop_coverage_ratio": hop_ratio,
        "world_class_bar": world_class_bar,
        "notes": notes,
    }
