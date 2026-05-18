"""Antiek knowledge-graph substrate.

Four submodules:

- ``schema`` — DuckDB DDL for documents, chunks, nodes, edges.
- ``ops`` — typed insert helpers that emit GRAPH_NODE_INSERTED /
  GRAPH_EDGE_INSERTED events on commit.
- ``search`` — cosine-similarity vector search over chunks +
  ILIKE node-label search.
- ``traverse`` — recursive-CTE traversal (shortest_path, top_n,
  dfs, bfs_semantic_stop).

Sprint 3 Day 1-2 migration (ports + adaptations of Researchmaxx
search.py + traverse.py + a minimal init_db). Day 2-3 wires the
wrestling bridge to populate the graph organically; Day 3-4 lights up
the proto-grounder over these queries.
"""

import os as _os
from typing import Optional as _Optional


def default_db_path() -> str:
    """Resolved path to the Antiek graph DB. Resolution order:

    1. ``ANTIEK_DUCKDB_PATH`` env var (operator override; used by
       tests to point at a tmp file).
    2. ``substrate.constants.DUCKDB_PATH`` expanded via ``~``.
    """
    explicit = _os.environ.get("ANTIEK_DUCKDB_PATH")
    if explicit:
        return _os.path.expanduser(explicit)
    from ..constants import DUCKDB_PATH as _DUCKDB_PATH  # local import to avoid cycle
    return _os.path.expanduser(_DUCKDB_PATH)


def ensure_initialized(db_path: _Optional[str] = None) -> str:
    """Make sure the schema is present at ``db_path``. Returns the
    resolved path. Idempotent — CREATE IF NOT EXISTS is the workhorse.

    Used by the wrestling bridge before the first DB-touching event
    in a given process. Cheap (~1ms after first call) so we don't
    bother with a "has-this-been-called" memo.
    """
    resolved = db_path or default_db_path()
    from .schema import init_database_at_path
    init_database_at_path(resolved)
    return resolved


from .ops import (
    append_interview_turn,
    attach_block_to_section,
    complete_interview,
    content_addressed_id,
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_edge,
    insert_interview,
    insert_interview_project,
    insert_node,
    insert_section,
    new_random_id,
    update_section_prose,
)
from .schema import (
    ANTIEK_GRAPH_SCHEMA_V1_SQL,
    SCHEMA_TABLES,
    init_database,
    init_database_at_path,
    list_tables,
)
from .search import (
    EmbeddingModel,
    SentenceTransformerEmbedding,
    cosine_similarity_sql,
    open_read,
    search,
    search_nodes_by_label,
)
from .rlm_tools import (
    CATEGORY_TOOL_MAP,
    LLMCall,
    MAX_TOOL_OUTPUT_CHARS,
    MAX_TOOL_ROUNDS,
    SubLLMWithTools,
    equipped_llm_batch,
    extract_json,
    fetch_url,
    get_builtin_tool_names,
    get_tool_specs,
    search_graph,
    tools_for_category,
    web_search,
)
from .traverse import (
    TraversalAlgorithm,
    TraversalScope,
    bfs_semantic_stop,
    dfs_with_depth,
    resolve_node,
    shortest_path,
    top_n_paths,
    traverse,
)

__all__ = [
    # path helpers
    "default_db_path",
    "ensure_initialized",
    # schema
    "init_database",
    "init_database_at_path",
    "list_tables",
    "ANTIEK_GRAPH_SCHEMA_V1_SQL",
    "SCHEMA_TABLES",
    # ops
    "insert_document",
    "insert_chunk",
    "insert_node",
    "insert_edge",
    "insert_deliverable",
    "insert_section",
    "attach_block_to_section",
    "update_section_prose",
    "insert_interview_project",
    "insert_interview",
    "append_interview_turn",
    "complete_interview",
    "content_addressed_id",
    "new_random_id",
    # search
    "search",
    "search_nodes_by_label",
    "cosine_similarity_sql",
    "EmbeddingModel",
    "SentenceTransformerEmbedding",
    "open_read",
    # traverse
    "traverse",
    "shortest_path",
    "top_n_paths",
    "dfs_with_depth",
    "bfs_semantic_stop",
    "resolve_node",
    "TraversalAlgorithm",
    "TraversalScope",
    # rlm_tools (sub-LLM tool-calling)
    "SubLLMWithTools",
    "equipped_llm_batch",
    "LLMCall",
    "extract_json",
    "web_search",
    "fetch_url",
    "search_graph",
    "get_builtin_tool_names",
    "get_tool_specs",
    "CATEGORY_TOOL_MAP",
    "tools_for_category",
    "MAX_TOOL_ROUNDS",
    "MAX_TOOL_OUTPUT_CHARS",
]
