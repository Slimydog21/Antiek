"""Twin substrate search → cross-asset merge compose (pure).

remote_index_queried, merge_executed, twin_written, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.recursive_twin_intelligent_search import (
    TwinIntelligentSearchError,
    TwinSearchResult,
    search_twin_substrate,
)
from substrate.twin_substrate_cross_asset_merge_compose import (
    TwinSubstrateCrossAssetMergeCompose,
    TwinSubstrateCrossAssetMergeComposeError,
    compose_twin_substrate_cross_asset_merge,
)


class TwinSubstrateSearchMergeComposeError(ValueError):
    """Fail-closed validation for twin search → merge pack."""


@dataclass(frozen=True)
class TwinSubstrateSearchMergeCompose:
    pack_id: str
    search: TwinSearchResult
    merge: TwinSubstrateCrossAssetMergeCompose | None
    pack_ready: bool
    remote_index_queried: bool
    merge_executed: bool
    twin_written: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "search": self.search.to_dict(),
            "merge": self.merge.to_dict() if self.merge else None,
            "pack_ready": self.pack_ready,
            "remote_index_queried": False,
            "merge_executed": False,
            "twin_written": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "twin_substrate_search_merge_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise TwinSubstrateSearchMergeComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _hits_to_slices(
    hits: tuple[Any, ...],
    corpus: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(r.get("twin_id")): r for r in corpus if isinstance(r, dict)}
    slices: list[dict[str, Any]] = []
    seen_parent: set[str] = set()
    for hit in hits:
        twin_id = hit.twin_id if hasattr(hit, "twin_id") else None
        if twin_id is None:
            continue
        rec = by_id.get(str(twin_id))
        if rec is None:
            continue
        parent = str(rec.get("parent_asset_id", "")).strip()
        if not parent or parent in seen_parent:
            continue
        seen_parent.add(parent)
        insights = rec.get("insights") or []
        questions = rec.get("questions") or []
        slices.append(
            {
                "parent_asset_id": parent,
                "twin_asset_id": twin_id,
                "insights": list(insights) if isinstance(insights, list) else [],
                "questions": list(questions) if isinstance(questions, list) else [],
            }
        )
    return slices


def compose_twin_substrate_search_merge(
    *,
    pack_id: object,
    search_query: object,
    twin_records: object,
    operator_ack: object,
    search_limit: object | None = None,
    min_parents_for_merge: object | None = None,
) -> TwinSubstrateSearchMergeCompose:
    """Search twin corpus then propose cross-asset merge. Never writes/merges."""
    if not isinstance(operator_ack, bool):
        raise TwinSubstrateSearchMergeComposeError(
            "operator_ack must be an explicit boolean"
        )
    pid = _require_nonempty(pack_id, field="pack_id")
    if not isinstance(twin_records, list):
        raise TwinSubstrateSearchMergeComposeError(
            "twin_records must be an array"
        )

    min_parents = 2 if min_parents_for_merge is None else min_parents_for_merge
    if not isinstance(min_parents, int) or isinstance(min_parents, bool) or min_parents < 2:
        raise TwinSubstrateSearchMergeComposeError(
            "min_parents_for_merge must be integer ≥ 2"
        )

    notes: list[str] = [
        "remote_index_queried=false — pure local twin corpus scan",
        "merge_executed=false — cross-asset merge is intent only",
        "twin_written=false · store_mutated=false",
    ]

    lim = 20 if search_limit is None else search_limit
    try:
        search = search_twin_substrate(
            query=search_query,
            records=twin_records,
            limit=lim,
        )
    except TwinIntelligentSearchError as e:
        raise TwinSubstrateSearchMergeComposeError(str(e)) from e
    notes.extend(f"[search] {n}" for n in search.notes)
    notes.append(f"search_hits={len(search.hits)}")

    corpus = [r for r in twin_records if isinstance(r, dict)]
    slices = _hits_to_slices(search.hits, corpus)
    notes.append(f"distinct_parent_slices_from_hits={len(slices)}")

    merge: TwinSubstrateCrossAssetMergeCompose | None = None
    if len(slices) >= min_parents:
        try:
            merge = compose_twin_substrate_cross_asset_merge(
                pack_id=pid,
                slices=slices,
                operator_ack=operator_ack,
            )
        except TwinSubstrateCrossAssetMergeComposeError as e:
            raise TwinSubstrateSearchMergeComposeError(str(e)) from e
        notes.extend(f"[merge] {n}" for n in merge.notes)
    elif len(search.hits) > 0:
        notes.append(
            f"merge skipped — need ≥{min_parents} distinct parents among hits "
            f"(got {len(slices)})"
        )
    else:
        notes.append("merge skipped — no search hits")

    if operator_ack and merge is not None:
        pack_ready = merge.merge_ready is True
    elif operator_ack and len(search.hits) > 0:
        pack_ready = True
    else:
        pack_ready = False

    if pack_ready:
        notes.append(
            "pack_ready=true — search+merge intent ready; still pure"
            if merge is not None
            else "pack_ready=true — search hits ready (merge deferred, insufficient parents)"
        )
    else:
        notes.append(
            "pack_ready=false — no hits, merge not ready, or operator_ack missing"
        )

    if search.remote_index_queried is not False:
        raise TwinSubstrateSearchMergeComposeError(
            "invariant: remote_index_queried must remain false"
        )
    if merge is not None and (
        merge.merge_executed is not False
        or merge.twin_written is not False
        or merge.store_mutated is not False
    ):
        raise TwinSubstrateSearchMergeComposeError(
            "invariant: merge honesty flags must remain false"
        )

    notes.extend(
        (
            "remote_index_queried=false",
            "merge_executed=false",
            "twin_written=false",
            "store_mutated=false",
        )
    )

    return TwinSubstrateSearchMergeCompose(
        pack_id=pid,
        search=search,
        merge=merge,
        pack_ready=pack_ready,
        remote_index_queried=False,
        merge_executed=False,
        twin_written=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="twin_substrate_search_merge_compose_advisory",
    )


def format_twin_substrate_search_merge_summary(
    c: TwinSubstrateSearchMergeCompose,
) -> str:
    mr = c.merge.merge_ready if c.merge is not None else False
    return (
        f"pack_ready={c.pack_ready} · hits={len(c.search.hits)} · "
        f"merge_ready={mr} · "
        f"remote_index_queried=false · merge_executed=false · twin_written=false"
    )


__all__ = [
    "TwinSubstrateSearchMergeCompose",
    "TwinSubstrateSearchMergeComposeError",
    "compose_twin_substrate_search_merge",
    "format_twin_substrate_search_merge_summary",
]
