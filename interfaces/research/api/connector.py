"""Cross-Domain Connector role bridge (Sprint 7 day 4 — fourth
orchestrate.py role bridge).

Subscribes to ``connector.requested`` events. Per request:

1. Reads the request's ``seed_pairs`` and runs the matching
   ``substrate.graph.traverse`` algorithm against each pair to
   produce candidate paths (top-N per pair, configurable).
2. Renders ``mappings_block`` + ``paths_block`` strings from the
   typed request mappings and the freshly traversed paths.
3. Dispatches the ``connector`` role (Pro tier per
   ``substrate/dispatch/config.yaml``).
4. Parses + validates the response with the closed-vocabulary
   parser. The parser enforces the cite-back rule and the
   low_confidence-flag discipline; structural failures fall back
   to an empty Delivered with the same algorithm-echo as the
   bridge ran (so the trajectory still records what was attempted).
5. Emits ``CONNECTOR_DELIVERED``.

The bridge holds a graph-read connection per request via
``substrate.graph.default_db_path`` (overrideable for tests).
``ANTIEK_DUCKDB_PATH`` env-var honored.

Failure-mode discipline (mirrors decomposer / evidence_retriever /
parameter_extractor):

- Provider unavailable → fallback Delivered, paths from traversal
  preserved (so the operator sees what the graph could surface even
  if the LLM never confirmed), policy stamped
  ``connector-fallback/no-provider``.
- Parse failure → fallback Delivered with paths preserved and
  ``natural_language_relationships=[]``.
- Graph unavailable / traversal raises → fallback Delivered with
  empty paths AND empty NL relationships; logs to stderr.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.connector import (  # noqa: E402
    ConnectorResult,
    ConnectorValidationError,
    parse_connector_response,
    render_full_prompt,
    render_mappings_block,
    render_paths_block,
)
from runtime.db_lock import connect_read  # noqa: E402
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.traverse import (  # noqa: E402
    dfs_with_depth,
    shortest_path,
    top_n_paths,
)
from substrate.schemas import (  # noqa: E402
    ActionType,
    ConnectorDeliveredPayload,
    ConnectorRequestedPayload,
    Event,
    GraphPath,
    KeywordMapping,
    NaturalLanguageRelationship,
    SeedPair,
)

from .broadcast import EventBroadcaster  # noqa: E402 — after the sys.path bootstrap above
from .research_tier_routing import persisted_research_tier_override  # noqa: E402

# ---------------------------------------------------------------------------
# Traversal dispatch
# ---------------------------------------------------------------------------


def _run_traversal(
    con: Any,
    *,
    algorithm: str,
    seed: SeedPair,
    max_paths_per_pair: int,
) -> list[dict[str, Any]]:
    """Run the requested algorithm against one seed pair. Returns
    the list of raw path dicts (the ``substrate.graph.traverse``
    output shape)."""
    if algorithm == "top_n_shortest_paths":
        return top_n_paths(
            con, seed.source_node_id, seed.target_node_id,
            n=max_paths_per_pair,
        )
    if algorithm == "shortest_simple_path":
        # shortest_path already returns [path_dict] (or [] when no path) —
        # wrapping it again produced list[list[dict]] and crashed _paths_to_typed.
        return shortest_path(con, seed.source_node_id, seed.target_node_id)
    if algorithm == "depth_first_limited":
        return dfs_with_depth(
            con, seed.source_node_id, seed.target_node_id,
        )
    if algorithm == "bfs_semantic_stop":
        # bfs_semantic_stop requires a waypoint; the bridge falls
        # back to top_n when the request didn't supply one. The
        # role's selected_algorithm in the response can correct
        # this in retrospect.
        return top_n_paths(
            con, seed.source_node_id, seed.target_node_id,
            n=max_paths_per_pair,
        )
    return []


def _paths_to_typed(raw_paths: list[dict[str, Any]]) -> list[GraphPath]:
    out: list[GraphPath] = []
    for p in raw_paths:
        out.append(GraphPath(
            path_nodes=list(p.get("path_nodes", [])),
            path_relations=list(p.get("path_relations", [])),
            depth=int(p.get("depth", 0)),
            avg_confidence=float(p.get("avg_confidence", 0.0)),
            node_labels=list(p.get("node_labels", [])),
            edge_ids=list(p.get("edge_ids", [])),
        ))
    return out


def _canonical_refs_for_connector(
    req: ConnectorRequestedPayload,
    paths: list[GraphPath],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    node_ids: list[str] = []
    edge_ids: list[str] = []
    seen_nodes: set[str] = set()
    seen_edges: set[str] = set()

    def add_node(value: str | None) -> None:
        if isinstance(value, str) and value.strip() and value not in seen_nodes:
            node_ids.append(value)
            seen_nodes.add(value)

    def add_edge(value: str | None) -> None:
        if isinstance(value, str) and value.strip() and value not in seen_edges:
            edge_ids.append(value)
            seen_edges.add(value)

    for mapping in req.keyword_mappings:
        add_node(mapping.matched_node_id)
    for path in paths:
        for node_id in path.path_nodes:
            add_node(node_id)
        for edge_id in path.edge_ids:
            add_edge(edge_id)

    return tuple(node_ids), tuple(edge_ids)


def _traversal_for_request(
    db_path: str,
    req: ConnectorRequestedPayload,
) -> list[GraphPath]:
    """Run the requested algorithm against every seed pair and
    concatenate the results. Returns an empty list when the graph
    layer raises (the bridge logs and continues — the operator sees
    an empty paths list rather than a dropped Delivered event)."""
    if not req.seed_pairs:
        return []
    try:
        ensure_initialized(db_path)
    except Exception as exc:  # pragma: no cover — diagnostic
        print(
            f"connector.handle: ensure_initialized failed — {exc!r}",
            flush=True,
        )
        return []
    try:
        con = connect_read(db_path)
    except Exception as exc:  # pragma: no cover — diagnostic
        print(
            f"connector.handle: connect_read failed — {exc!r}",
            flush=True,
        )
        return []
    raw_paths: list[dict[str, Any]] = []
    try:
        for seed in req.seed_pairs:
            try:
                raw_paths.extend(_run_traversal(
                    con, algorithm=req.algorithm, seed=seed,
                    max_paths_per_pair=req.max_paths_per_pair,
                ))
            except Exception as exc:  # pragma: no cover — diagnostic
                print(
                    f"connector.handle: traversal failed for "
                    f"({seed.source_node_id} → {seed.target_node_id}): "
                    f"{exc!r}",
                    flush=True,
                )
    finally:
        con.close()
    return _paths_to_typed(raw_paths)


# ---------------------------------------------------------------------------
# Dispatch + parse
# ---------------------------------------------------------------------------


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    canonical_node_ids: tuple[str, ...] = (),
    canonical_edge_ids: tuple[str, ...] = (),
) -> tuple[ConnectorResult | None, str]:
    provider_override, model_override = persisted_research_tier_override(
        event.investigation_id,
    )
    try:
        result = dispatch(
            prompt,
            "connector",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
            provider_override=provider_override,
            model_override=model_override,
        )
        response_text = result.text
        policy_id = f"{result.provider}/{result.model}"
    except (ProviderError, KeyError) as exc:
        print(
            f"connector.handle: dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, "connector-fallback/no-provider"

    try:
        parsed = parse_connector_response(
            response_text,
            canonical_node_ids=canonical_node_ids,
            canonical_edge_ids=canonical_edge_ids,
        )
        return parsed, policy_id
    except ConnectorValidationError as exc:
        print(
            f"connector.handle: parse failed — {exc}",
            flush=True,
        )
        return None, policy_id


def _result_to_payload_lists(
    result: ConnectorResult,
) -> tuple[
    list[KeywordMapping],
    list[GraphPath],
    list[NaturalLanguageRelationship],
]:
    mappings = [
        KeywordMapping(
            keyword=m.keyword,
            similarity=m.similarity,
            low_confidence=m.low_confidence,
            matched_node_id=m.matched_node_id,
            matched_node_label=m.matched_node_label,
            matched_node_type=m.matched_node_type,
        )
        for m in result.keyword_mappings
    ]
    paths = [
        GraphPath(
            path_nodes=list(p.path_nodes),
            path_relations=list(p.path_relations),
            depth=p.depth,
            avg_confidence=p.avg_confidence,
            node_labels=list(p.node_labels),
            edge_ids=list(p.edge_ids),
        )
        for p in result.paths
    ]
    nl = [
        NaturalLanguageRelationship(
            text=n.text, source_path_index=n.source_path_index,
        )
        for n in result.natural_language_relationships
    ]
    return mappings, paths, nl


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_connector_handler(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
) -> Callable[[Event], Awaitable[None]]:
    """Build the connector handler. Closed over a broadcaster + db
    path. Registered against ``ActionType.CONNECTOR_REQUESTED``."""
    resolved_db = db_path or default_db_path()

    async def handle_connector_request(event: Event) -> None:
        if not isinstance(event.payload, ConnectorRequestedPayload):
            return  # defensive — handler keyed on action_type
        req = event.payload

        # ── 1. Run traversal against the seed pairs ──
        traversed_paths = _traversal_for_request(resolved_db, req)
        canonical_node_ids, canonical_edge_ids = _canonical_refs_for_connector(
            req,
            traversed_paths,
        )

        # ── 2. Render prompt blocks ──
        mappings_block = render_mappings_block(list(req.keyword_mappings))
        paths_block = render_paths_block(list(traversed_paths))
        prompt = render_full_prompt(
            mappings_block=mappings_block,
            paths_block=paths_block,
        )

        # ── 3. Dispatch + parse ──
        result, policy_id = _dispatch_and_parse(
            prompt,
            event,
            canonical_node_ids=canonical_node_ids,
            canonical_edge_ids=canonical_edge_ids,
        )

        if result is None:
            # Fallback: surface the traversed paths even though the
            # role didn't confirm. NL relationships stay empty —
            # the role's natural-language rendering is what we
            # failed to get.
            await _emit_delivered(
                event,
                payload=ConnectorDeliveredPayload(
                    keyword_mappings=list(req.keyword_mappings),
                    selected_algorithm=req.algorithm,
                    algorithm_rationale=None,
                    paths=traversed_paths,
                    natural_language_relationships=[],
                ),
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
            return

        mappings_payload, paths_payload, nl_payload = (
            _result_to_payload_lists(result)
        )
        await _emit_delivered(
            event,
            payload=ConnectorDeliveredPayload(
                keyword_mappings=mappings_payload,
                selected_algorithm=result.selected_algorithm,  # type: ignore[arg-type]
                algorithm_rationale=result.algorithm_rationale,
                paths=paths_payload,
                natural_language_relationships=nl_payload,
            ),
            policy_id=policy_id,
            broadcaster=broadcaster,
        )

    return handle_connector_request


# ---------------------------------------------------------------------------
# Emit + broadcast
# ---------------------------------------------------------------------------


async def _emit_delivered(
    event: Event,
    *,
    payload: ConnectorDeliveredPayload,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        payload,
        parent_event_id=event.event_id,
        role="connector",
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: str | None,
    broadcaster: EventBroadcaster,
) -> None:
    if emitted_event_id is None:
        return
    for row in reversed(trajectory(event.investigation_id)):
        if row.get("event_id") == emitted_event_id:
            try:
                emitted = Event.model_validate(row)
                await broadcaster.broadcast(emitted)
            except Exception:  # pragma: no cover — never block on broadcast
                pass
            return


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
) -> None:
    """Wire the connector handler into the broadcaster. Called once
    at app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.CONNECTOR_REQUESTED.value,
        make_connector_handler(broadcaster, db_path=db_path),
    )
