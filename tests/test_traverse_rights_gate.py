"""§9.0 traversal label projections: fail-safe defaults and owner parity (#711)."""

from __future__ import annotations

import importlib
import json

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path

traversal = importlib.import_module("substrate.graph.traverse")
SECRET = "SECRET-PERSONAL-READING-HEADLINE"


@pytest.fixture
def graph(tmp_path):
    path = str(tmp_path / "traverse-rights.duckdb")
    init_database_at_path(path)
    con = duckdb.connect(path)
    for name, content_class in (("pub", "public_domain"), ("priv", "personal_reading")):
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type, content_class) "
            "VALUES (?, ?, 1, 'paper', ?)",
            [name, name, content_class],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, token_count) "
            "VALUES (?, ?, 0, 'body', 1)",
            [name, name],
        )
    for node_id, label, chunk in (
        ("a", "public source", "pub"),
        ("secret-node", SECRET, "priv"),
        ("c", "public target", "pub"),
        ("d", "public waypoint", "pub"),
        ("orphan", "unresolved headline", None),
    ):
        con.execute(
            "INSERT INTO nodes (node_id, node_type, canonical_label, graph_scope, metadata) "
            "VALUES (?, 'claim', ?, 'cross_domain', ?)",
            [node_id, label, json.dumps({"chunk_id": chunk})],
        )
    for source, target in (("a", "secret-node"), ("secret-node", "c"), ("a", "d"), ("d", "c")):
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES (?, ?, ?, 'related_to', 'pub', 1, 0.9, 'cross_domain')",
            [source + target, source, target],
        )
    yield con, path
    con.close()


def test_default_projection_redacts_personal_path_label(graph):
    con, _ = graph
    result = traversal.traverse(con, source="a", target="c", normalize_degree=False)
    assert result["path_count"] == 2
    assert SECRET not in json.dumps(result)
    assert ["public source", "secret-node", "public target"] in [
        p["node_labels"] for p in result["paths"]
    ]


@pytest.mark.parametrize(
    "policy_tag", [None, "attribution_eligible", "unknown", "private_research", "operator_only"]
)
def test_labels_preserve_order_and_only_privileged_tags_reveal_secret(graph, policy_tag):
    con, _ = graph
    labels = traversal._resolve_labels(
        con, ["a", "secret-node", "orphan", "c", "secret-node"], policy_tag=policy_tag
    )
    privileged = policy_tag in {"private_research", "operator_only"}
    assert labels == [
        "public source",
        SECRET if privileged else "secret-node",
        "unresolved headline" if privileged else "orphan",
        "public target",
        SECRET if privileged else "secret-node",
    ]
    assert traversal._resolve_labels(con, [], policy_tag=policy_tag) == []


@pytest.mark.parametrize("query", ["secret-node", SECRET, "PERSONAL-READING"])
def test_resolution_does_not_disclose_gated_label_matches(graph, query):
    con, _ = graph
    with pytest.raises(ValueError, match="node not found"):
        traversal.resolve_node(con, query)
    assert traversal.resolve_node(con, query, policy_tag="private_research") == "secret-node"


@pytest.mark.parametrize(
    "algorithm", ["shortest_path", "top_n_paths", "dfs_with_depth", "bfs_semantic_stop"]
)
@pytest.mark.parametrize(
    "policy_tag", [None, "attribution_eligible", "private_research", "operator_only"]
)
def test_each_algorithm_projects_labels_under_the_callers_policy(graph, algorithm, policy_tag):
    con, _ = graph
    args = ("public waypoint",) if algorithm == "bfs_semantic_stop" else ()
    paths = getattr(traversal, algorithm)(con, "a", "c", *args, policy_tag=policy_tag)
    assert paths
    for path in paths:
        assert path["node_labels"] == traversal._resolve_labels(
            con, path["path_nodes"], policy_tag=policy_tag
        )
    if algorithm != "bfs_semantic_stop":
        # Force the personal node to be an endpoint, not an optional parallel path.
        paths = getattr(traversal, algorithm)(con, "a", "secret-node", policy_tag=policy_tag)
        assert paths[0]["node_labels"] == [
            "public source",
            SECRET if policy_tag in {"private_research", "operator_only"} else "secret-node",
        ]


@pytest.mark.parametrize("algorithm", ["shortest_path", "top_n", "dfs", "bfs_semantic_stop"])
def test_dispatcher_threads_policy_to_paths_and_endpoint_labels(graph, algorithm):
    con, _ = graph
    result = traversal.traverse(
        con,
        source="a",
        target="secret-node",
        algorithm=algorithm,
        waypoint="public waypoint",
        policy_tag="private_research",
    )
    assert result["target"]["label"] == SECRET
    if algorithm != "bfs_semantic_stop":
        assert result["paths"][0]["node_labels"][-1] == SECRET
    with pytest.raises(ValueError, match="node not found"):
        traversal.traverse(con, source="a", target="secret-node", algorithm=algorithm)


@pytest.mark.parametrize(
    "policy_tag", [None, "attribution_eligible", "private_research", "operator_only"]
)
def test_semantic_waypoint_resolution_is_gated(graph, policy_tag):
    con, _ = graph
    if policy_tag in {"private_research", "operator_only"}:
        paths = traversal.bfs_semantic_stop(con, "a", "c", SECRET, policy_tag=policy_tag)
        assert paths[0]["node_labels"] == ["public source", SECRET, "public target"]
    else:
        with pytest.raises(ValueError, match="node not found"):
            traversal.bfs_semantic_stop(con, "a", "c", SECRET, policy_tag=policy_tag)


@pytest.mark.parametrize(
    "tag", [None, "", " attribution_eligible ", " private_research ", "operator_only", "unknown"]
)
@pytest.mark.parametrize(
    "algorithm",
    ["top_n_shortest_paths", "shortest_simple_path", "depth_first_limited", "bfs_semantic_stop"],
)
def test_connector_uses_active_research_policy_for_delivered_paths(
    graph, monkeypatch, tag, algorithm
):
    from interfaces.research.api.connector import _traversal_for_request
    from substrate.schemas import ConnectorRequestedPayload, SeedPair

    con, path = graph
    # The connector opens its own read-only connection.
    con.close()
    if tag is None:
        monkeypatch.delenv("ANTIEK_RESEARCH_POLICY_TAG", raising=False)
    else:
        monkeypatch.setenv("ANTIEK_RESEARCH_POLICY_TAG", tag)
    req = ConnectorRequestedPayload(
        algorithm=algorithm,
        seed_pairs=[SeedPair(source_node_id="a", target_node_id="secret-node")],
        keyword_mappings=[],
        max_paths_per_pair=5,
    )
    paths = _traversal_for_request(path, req)
    assert len(paths) == 1
    privileged = (tag or "").strip() in {"private_research", "operator_only"}
    assert paths[0].node_labels == ["public source", SECRET if privileged else "secret-node"]


def test_privileged_tag_does_not_bypass_node_owner_isolation(graph):
    con, _ = graph
    con.execute(
        "INSERT INTO nodes (node_id, node_type, canonical_label, graph_scope, owner_user_id, metadata) "
        "VALUES ('owned', 'claim', ?, 'cross_domain', 'alice', ?)",
        [SECRET + " owned", json.dumps({"chunk_id": "priv"})],
    )
    assert traversal._resolve_labels(con, ["owned"], policy_tag="private_research") == ["owned"]
    assert traversal._resolve_labels(
        con, ["owned"], owner_user_id="alice", policy_tag="private_research"
    ) == [SECRET + " owned"]
    with pytest.raises(ValueError, match="node not found"):
        traversal.resolve_node(con, SECRET + " owned", policy_tag="private_research")
