"""Research↔reading engagement spine primitives."""

from .merge import (
    MergeMode,
    MergeResult,
    merge_product_payload,
    merge_spawn_outputs,
    project_merge_html,
)
from .project import project_to_html
from .spawn import (
    HighlightSelection,
    ResearchSpawn,
    SpawnStatus,
    complete_spawn,
    get_spawn,
    list_spawns_for_asset,
    spawn_from_highlight,
)
from .store import EngagementStore, FileEngagementStore, InMemoryEngagementStore
from .twin import (
    TwinKind,
    TwinNote,
    list_twin_notes,
    project_twins_html,
    record_twin_insight,
    record_twin_product,
    record_twin_question,
    twins_product_payload,
)

__all__ = [
    "EngagementStore", "FileEngagementStore", "HighlightSelection",
    "InMemoryEngagementStore", "MergeMode", "MergeResult", "ResearchSpawn",
    "SpawnStatus", "TwinKind", "TwinNote", "complete_spawn", "get_spawn",
    "list_spawns_for_asset", "list_twin_notes", "merge_product_payload",
    "merge_spawn_outputs", "project_merge_html", "project_to_html",
    "project_twins_html", "record_twin_insight", "record_twin_product",
    "record_twin_question", "spawn_from_highlight", "twins_product_payload",
]
