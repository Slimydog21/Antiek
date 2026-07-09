"""Research↔reading engagement spine.

Vertical slice that unifies reading and research interaction:

1. **Spawn** deep-research work from a highlight / selection on any
   information asset (book, paper, research doc).
2. **Twin notes** — every asset has a twin side carrying LLM- and
   operator-recorded insights and questions.
3. **Merge** completed subagent outputs into the parent asset or a
   draft-combined document (before a full merge commit).

Pure logic + store protocol so tests drive shipped functions without
network. HTML view projection is via ``project_to_html`` (HTML-first;
PDF is never the canonical view surface).
"""

from __future__ import annotations

from .merge import MergeMode, MergeResult, merge_spawn_outputs
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
from .twin import TwinKind, TwinNote, list_twin_notes, record_twin_insight, record_twin_question

__all__ = [
    "EngagementStore",
    "FileEngagementStore",
    "HighlightSelection",
    "InMemoryEngagementStore",
    "MergeMode",
    "MergeResult",
    "ResearchSpawn",
    "SpawnStatus",
    "TwinKind",
    "TwinNote",
    "complete_spawn",
    "get_spawn",
    "list_spawns_for_asset",
    "list_twin_notes",
    "merge_spawn_outputs",
    "project_to_html",
    "record_twin_insight",
    "record_twin_question",
    "spawn_from_highlight",
]
