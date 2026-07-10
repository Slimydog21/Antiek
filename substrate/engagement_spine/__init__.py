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
    ensure_spawn,
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
    ANTIEK_TWIN_SEED_LIVE_ENV,
    clear_twin_seed_live,
    configure_twin_seed_live,
    twin_seed_live_fn_installed,
    seed_twins_for_asset,
    twin_seed_live_enabled,
    twins_product_payload,
)
from .twin_promote import (
    TwinContextUnit,
    TwinPromoteContextResult,
    TwinPromoteResult,
    depth_graph_honesty_fields,
    expected_graph_node_id,
    promote_and_context_for_asset,
    promote_twin_note,
    promote_twin_notes_for_asset,
    result_to_context_unit,
    search_twin_context,
    twin_context_html,
    twin_promote_context_payload,
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
from .research_context import (
    ResearchContextPack,
    assemble_research_context,
    research_context_html,
    research_context_sections_html,
)
from .collective import (
    CollectiveResearchUnit,
    collective_research_html,
    merge_spawns_collective,
)
from .hydrate import HydratedAsset, asset_id_for_ref, hydrate_reference, project_hydrated_html
from .hydrate_adapters import (
    arxiv_metadata_fetch_publication,
    compose_fetch_publication,
    hydrate_with_arxiv_adapter,
    hydrate_with_publication_adapters,
    substack_post_fetch_publication,
)
from .hydrate_live_wiring import (
    ANTIEK_HYDRATE_LIVE_ARXIV_ENV,
    ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV,
    configure_engagement_hydrate_injectors,
    env_flag,
    live_fetch_publication_from_env,
)
from .context_search import search_engagement_context, project_context_search_html
from .progress import (
    ProgressEvent,
    list_progress,
    progress_payload,
    project_progress_html,
    record_progress,
    seed_default_pipeline,
)
from .evidence import (
    CITATION_HOP_PIPELINE_STAGES,
    build_citation_chain_hops,
    citation_chain_complete,
    citation_hop_pipeline_progress,
    evidence_pack_payload,
    project_evidence_html,
)

__all__ = [
    "CollectiveResearchUnit",
    "EngagementStore",
    "FileEngagementStore",
    "HighlightSelection",
    "InMemoryEngagementStore",
    "MergeMode",
    "MergeResult",
    "ResearchContextPack",
    "ResearchSpawn",
    "SourceKind",
    "SourceReference",
    "SpawnStatus",
    "TwinContextUnit",
    "TwinKind",
    "TwinNote",
    "TwinPromoteContextResult",
    "TwinPromoteResult",
    "assemble_research_context",
    "attach_source_references",
    "collective_research_html",
    "complete_spawn",
    "detect_source_kind",
    "ensure_spawn",
    "depth_graph_honesty_fields",
    "expected_graph_node_id",
    "extract_arxiv_id",
    "filter_references",
    "HydratedAsset",
    "ProgressEvent",
    "ANTIEK_HYDRATE_LIVE_ARXIV_ENV",
    "ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV",
    "arxiv_metadata_fetch_publication",
    "asset_id_for_ref",
    "compose_fetch_publication",
    "configure_engagement_hydrate_injectors",
    "env_flag",
    "CITATION_HOP_PIPELINE_STAGES",
    "build_citation_chain_hops",
    "citation_chain_complete",
    "citation_hop_pipeline_progress",
    "evidence_pack_payload",
    "get_spawn",
    "hydrate_reference",
    "hydrate_with_arxiv_adapter",
    "hydrate_with_publication_adapters",
    "list_progress",
    "live_fetch_publication_from_env",
    "substack_post_fetch_publication",
    "list_source_references",
    "list_spawns_for_asset",
    "list_twin_notes",
    "merge_product_payload",
    "merge_spawn_outputs",
    "merge_spawns_collective",
    "parse_source_reference",
    "parse_source_references",
    "progress_payload",
    "project_context_search_html",
    "project_evidence_html",
    "project_hydrated_html",
    "project_merge_html",
    "project_progress_html",
    "project_to_html",
    "record_progress",
    "seed_default_pipeline",
    "promote_and_context_for_asset",
    "promote_twin_note",
    "promote_twin_notes_for_asset",
    "project_twins_html",
    "record_twin_insight",
    "record_twin_product",
    "record_twin_question",
    "ANTIEK_TWIN_SEED_LIVE_ENV",
    "clear_twin_seed_live",
    "configure_twin_seed_live",
    "seed_twins_for_asset",
    "twin_seed_live_fn_installed",
    "twin_seed_live_enabled",
    "research_context_html",
    "research_context_sections_html",
    "result_to_context_unit",
    "search_engagement_context",
    "search_twin_context",
    "source_references_html",
    "spawn_from_highlight",
    "spawn_from_highlight_with_references",
    "twin_context_html",
    "twin_promote_context_payload",
    "twins_product_payload",
]
