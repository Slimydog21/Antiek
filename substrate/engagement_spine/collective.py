"""Collective deep-research: merge multiple spawns into one cohesive unit.

Workstation vision: select several subagent / floating deep-research
instances and prompt them as a single research unit — merging twin
substrate signals and attached arxiv/substack refs without live fan-out.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Sequence

from .research_context import ResearchContextPack, assemble_research_context
from .source_refs import SourceReference, merge_references
from .store import EngagementStore
from .twin_promote import TwinContextUnit


def _max_research_tier(tiers: Sequence[str]) -> str:
    """Residual (ke): depth-max of closed set for continue-as-unit default."""
    from substrate.dispatch.research_tier import normalize_research_tier

    order = {"fast": 0, "deep": 1, "wrestle": 2}
    best = "deep"
    best_rank = -1
    for raw in tiers:
        t = normalize_research_tier(raw)
        rank = order.get(t, 1)
        if rank > best_rank:
            best = t
            best_rank = rank
    return best


@dataclass(frozen=True)
class CollectiveResearchUnit:
    """Merged multi-spawn research unit for cohesive prompting."""

    collective_id: str
    spawn_ids: tuple[str, ...]
    asset_ids: tuple[str, ...]
    investigation_ids: tuple[str, ...]
    twin_units: tuple[TwinContextUnit, ...]
    source_references: tuple[SourceReference, ...]
    view_format: str = "html"
    # Residual (ke): per-spawn tiers + depth-max for continue-as-unit budget.
    research_tiers: tuple[str, ...] = ()
    recommended_research_tier: str = "deep"

    def to_dict(self) -> dict[str, Any]:
        return {
            "collective_id": self.collective_id,
            "spawn_ids": list(self.spawn_ids),
            "asset_ids": list(self.asset_ids),
            "investigation_ids": list(self.investigation_ids),
            "twin_units": [u.to_dict() for u in self.twin_units],
            "source_references": [r.to_dict() for r in self.source_references],
            "view_format": self.view_format,
            "spawn_count": len(self.spawn_ids),
            "twin_count": len(self.twin_units),
            "ref_count": len(self.source_references),
            "research_tiers": list(self.research_tiers),
            "recommended_research_tier": self.recommended_research_tier,
        }

    def prompt_block(self, *, max_twins: int = 20, max_refs: int = 20) -> str:
        lines = [
            f"# Collective deep-research unit `{self.collective_id}`",
            f"spawns ({len(self.spawn_ids)}): {', '.join(self.spawn_ids)}",
            f"assets: {', '.join(self.asset_ids)}",
            f"research_tiers: {', '.join(self.research_tiers) or 'deep'}",
            f"recommended_research_tier: {self.recommended_research_tier}",
            "",
            "## Merged twin-derived insights & questions",
        ]
        if not self.twin_units:
            lines.append("(none)")
        else:
            for u in self.twin_units[:max_twins]:
                lines.append(f"- [{u.kind}|{u.asset_id}] ({u.unit_id}) {u.text}")
        lines.append("")
        lines.append("## Merged source references")
        if not self.source_references:
            lines.append("(none)")
        else:
            for r in self.source_references[:max_refs]:
                cite = r.canonical_url or r.raw
                lines.append(f"- [{r.kind}] {cite}")
        return "\n".join(lines) + "\n"


def _collective_id(spawn_ids: Sequence[str]) -> str:
    ordered = sorted({s.strip() for s in spawn_ids if s and s.strip()})
    raw = "collective:v1:" + "|".join(ordered)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"col_{digest}"


def _dedupe_twin_units(units: Sequence[TwinContextUnit]) -> tuple[TwinContextUnit, ...]:
    seen: set[str] = set()
    out: list[TwinContextUnit] = []
    for u in units:
        if u.unit_id in seen:
            continue
        seen.add(u.unit_id)
        out.append(u)
    return tuple(out)


def merge_spawns_collective(
    spawn_ids: Sequence[str],
    *,
    store: EngagementStore,
    query: str | None = None,
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
    embedding_provider: Any = None,
    con: Any = None,
    include_twin_promote: bool = True,
) -> CollectiveResearchUnit:
    """Merge multiple reserved/complete spawns into one collective unit.

    Stable ``collective_id`` from sorted spawn ids. Twin units and source
    refs are unioned (de-duped by unit_id / ref_id). No network.
    """
    ids = [s.strip() for s in spawn_ids if s and str(s).strip()]
    if len(ids) < 1:
        raise ValueError("at least one spawn_id is required")
    # Allow single spawn (degenerate collective) for uniform API.
    missing = [s for s in ids if store.get_spawn(s) is None]
    if missing:
        raise KeyError(f"unknown spawn_id(s): {missing}")

    from substrate.dispatch.research_tier import normalize_research_tier

    packs: list[ResearchContextPack] = []
    asset_ids: list[str] = []
    inv_ids: list[str] = []
    all_twins: list[TwinContextUnit] = []
    all_refs: list[SourceReference] = []
    tier_list: list[str] = []

    for sid in ids:
        row = store.get_spawn(sid)
        assert row is not None
        asset = str(row.get("parent_asset_id") or "").strip()
        if not asset:
            raise ValueError(f"spawn {sid} missing parent_asset_id")
        asset_ids.append(asset)
        inv = row.get("investigation_id")
        if inv:
            inv_ids.append(str(inv))
        # Residual (ke): capture each spawn's closed research_tier.
        tier_list.append(normalize_research_tier(row.get("research_tier")))
        pack = assemble_research_context(
            asset,
            store=store,
            spawn_id=sid,
            query=query,
            investigation_id=str(inv) if inv else None,
            promote_insight_fn=promote_insight_fn,
            promote_question_fn=promote_question_fn,
            embedding_provider=embedding_provider,
            con=con,
            include_twin_promote=include_twin_promote,
        )
        packs.append(pack)
        all_twins.extend(pack.twin_units)
        all_refs = list(merge_references(all_refs, pack.source_references))

    # Stable order of spawn ids in output preserves caller order (not sorted)
    # but collective_id is sorted for identity stability.
    unique_assets = tuple(dict.fromkeys(asset_ids))
    unique_invs = tuple(dict.fromkeys(inv_ids))
    tiers = tuple(tier_list)

    return CollectiveResearchUnit(
        collective_id=_collective_id(ids),
        spawn_ids=tuple(ids),
        asset_ids=unique_assets,
        investigation_ids=unique_invs,
        twin_units=_dedupe_twin_units(all_twins),
        source_references=tuple(all_refs),
        view_format="html",
        research_tiers=tiers,
        recommended_research_tier=_max_research_tier(tiers),
    )


def collective_research_html(unit: CollectiveResearchUnit) -> str:
    """HTML-first view of a collective multi-spawn research unit."""
    from .project import project_to_html

    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [
                {
                    "type": "text",
                    "text": f"Collective research — {unit.collective_id}",
                }
            ],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": (
                        f"spawns={len(unit.spawn_ids)} "
                        f"twins={len(unit.twin_units)} "
                        f"refs={len(unit.source_references)}"
                        + (
                            f" · recommended_tier={unit.recommended_research_tier}"
                            if unit.recommended_research_tier
                            else ""
                        )
                        + (
                            f" · tiers={','.join(unit.research_tiers)}"
                            if unit.research_tiers
                            else ""
                        )
                    ),
                }
            ],
        },
    ]
    for sid in unit.spawn_ids:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": f"spawn: {sid}"}],
            }
        )
    for u in unit.twin_units:
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
    for r in unit.source_references:
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
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id=unit.collective_id,
        creator="collective_research",
    )
