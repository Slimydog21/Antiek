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
    ensure_spawn,
    get_spawn,
    list_spawns_for_asset,
    spawn_from_highlight,
)
from .store import EngagementStore, FileEngagementStore, InMemoryEngagementStore
from .twin import TwinKind, TwinNote, list_twin_notes, record_twin_insight, record_twin_question
from .twin_promote import (
    TwinContextUnit,
    TwinPromoteContextResult,
    TwinPromoteResult,
    expected_graph_node_id,
    promote_and_context_for_asset,
    promote_twin_note,
    promote_twin_notes_for_asset,
    result_to_context_unit,
    search_twin_context,
    twin_context_html,
)
from .source_refs import (
    SourceKind,
    SourceReference,
    attach_source_references,
    detect_source_kind,
    extract_arxiv_id,
    filter_references,
    list_source_references,
    parse_source_reference,
    parse_source_references,
    source_references_html,
    spawn_from_highlight_with_references,
)

__all__ = [
    "EngagementStore",
    "FileEngagementStore",
    "HighlightSelection",
    "InMemoryEngagementStore",
    "MergeMode",
    "MergeResult",
    "ResearchSpawn",
    "SourceKind",
    "SourceReference",
    "SpawnStatus",
    "TwinContextUnit",
    "TwinKind",
    "TwinNote",
    "TwinPromoteContextResult",
    "TwinPromoteResult",
    "attach_source_references",
    "complete_spawn",
    "detect_source_kind",
    "ensure_spawn",
    "expected_graph_node_id",
    "extract_arxiv_id",
    "filter_references",
    "get_spawn",
    "list_source_references",
    "list_spawns_for_asset",
    "list_twin_notes",
    "merge_spawn_outputs",
    "parse_source_reference",
    "parse_source_references",
    "project_to_html",
    "promote_and_context_for_asset",
    "promote_twin_note",
    "promote_twin_notes_for_asset",
    "record_twin_insight",
    "record_twin_question",
    "result_to_context_unit",
    "search_twin_context",
    "source_references_html",
    "spawn_from_highlight",
    "spawn_from_highlight_with_references",
    "twin_context_html",
]
