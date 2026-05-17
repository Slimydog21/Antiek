"""Tests for roles/connector/ (Sprint 7 day 4).

Coverage:

A. Prompt + render helpers:
   1. ``render_mappings_block`` empty + non-empty (includes
      similarity + low_confidence flag).
   2. ``render_paths_block`` empty + non-empty (interleaves
      labels and relations).
   3. ``render_full_prompt`` includes system + user;
      ``extra_user_prefix`` threads through.

B. Parser — happy path:
   4. Well-formed response parses into ConnectorResult with all
      four top-level sections.

C. Parser — validation failures:
   5. Garbage rejected.
   6. Bad ``selected_algorithm`` rejected.
   7. ``low_confidence=false`` with ``similarity<0.80`` rejected
      (anti-pattern #3).
   8. NL relationship's ``source_path_index`` out of range rejected.
   9. ``similarity`` out of [0, 1] rejected.
   10. Top-level keys missing / wrong type rejected.

D. Drift detection:
   11. TRAVERSAL_ALGORITHMS == schema TraversalAlgorithm Literal.
"""

from __future__ import annotations

import json
import os
import sys
import typing

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from roles.connector import (  # noqa: E402
    CONNECTOR_SYSTEM_PROMPT,
    ConnectorValidationError,
    LOW_CONFIDENCE_THRESHOLD,
    TRAVERSAL_ALGORITHMS,
    parse_connector_response,
    render_full_prompt,
    render_mappings_block,
    render_paths_block,
)
from substrate.schemas import TraversalAlgorithm  # noqa: E402


# ---------------------------------------------------------------------------
# A. Prompt + render helpers
# ---------------------------------------------------------------------------


def test_render_mappings_block_empty():
    assert render_mappings_block([]) == "(no pre-resolved mappings)"


def test_render_mappings_block_includes_similarity_and_flag():
    block = render_mappings_block([
        {
            "keyword": "quantum", "matched_node_id": "n-1",
            "matched_node_label": "Quantum Computing", "matched_node_type": "concept",
            "similarity": 0.92, "low_confidence": False,
        },
        {
            "keyword": "obscure", "matched_node_id": "n-2",
            "matched_node_label": "Edge Concept", "matched_node_type": "concept",
            "similarity": 0.45, "low_confidence": True,
        },
    ])
    assert "quantum" in block
    assert "0.920" in block
    assert "0.450" in block
    assert "low_confidence=true" in block
    assert "low_confidence=false" in block


def test_render_paths_block_empty():
    out = render_paths_block([])
    assert "graph may not connect" in out


def test_render_paths_block_interleaves_labels_and_relations():
    out = render_paths_block([{
        "path_nodes": ["n-1", "n-2", "n-3"],
        "node_labels": ["A", "B", "C"],
        "path_relations": ["rel-1", "rel-2"],
        "depth": 2,
        "avg_confidence": 0.85,
    }])
    assert "[0]" in out
    assert "depth=2" in out
    assert "A" in out and "B" in out and "C" in out
    assert "-[rel-1]->" in out and "-[rel-2]->" in out


def test_render_full_prompt_includes_system_and_user():
    p = render_full_prompt(
        mappings_block="MAPPINGS", paths_block="PATHS",
    )
    assert CONNECTOR_SYSTEM_PROMPT in p
    assert "MAPPINGS" in p
    assert "PATHS" in p


def test_render_full_prompt_extra_prefix_threads_into_user():
    p = render_full_prompt(
        mappings_block="M", paths_block="P",
        extra_user_prefix="REGEN",
    )
    sys_end = p.index(CONNECTOR_SYSTEM_PROMPT) + len(CONNECTOR_SYSTEM_PROMPT)
    regen_idx = p.index("REGEN")
    assert regen_idx > sys_end


# ---------------------------------------------------------------------------
# B-C. Parser
# ---------------------------------------------------------------------------


def _good_response() -> dict:
    return {
        "keyword_mappings": [
            {
                "keyword": "TSMC", "matched_node_id": "n-tsmc",
                "matched_node_label": "TSMC", "matched_node_type": "company",
                "similarity": 0.95, "low_confidence": False,
            },
        ],
        "selected_algorithm": "top_n_shortest_paths",
        "algorithm_rationale": "Enumerating mechanisms calls for top-N.",
        "paths": [
            {
                "path_nodes": ["n-tsmc", "n-asml"],
                "node_labels": ["TSMC", "ASML"],
                "path_relations": ["sources_from"],
                "depth": 1,
                "avg_confidence": 0.92,
                "edge_ids": ["e-1"],
            },
        ],
        "natural_language_relationships": [
            {
                "text": "TSMC sources EUV lithography systems from ASML.",
                "source_path_index": 0,
            },
        ],
    }


def test_parser_happy_path():
    out = parse_connector_response(json.dumps(_good_response()))
    assert out.selected_algorithm == "top_n_shortest_paths"
    assert len(out.keyword_mappings) == 1
    assert len(out.paths) == 1
    assert len(out.natural_language_relationships) == 1
    assert out.natural_language_relationships[0].source_path_index == 0


def test_parser_garbage_rejected():
    with pytest.raises(ConnectorValidationError, match="parseable JSON"):
        parse_connector_response("not json")


def test_parser_bad_algorithm_rejected():
    payload = _good_response()
    payload["selected_algorithm"] = "made_up_algorithm"
    with pytest.raises(ConnectorValidationError, match="selected_algorithm"):
        parse_connector_response(json.dumps(payload))


def test_parser_low_confidence_discipline():
    """similarity<0.80 with low_confidence=false is the anti-pattern."""
    payload = _good_response()
    payload["keyword_mappings"][0]["similarity"] = 0.5
    payload["keyword_mappings"][0]["low_confidence"] = False
    with pytest.raises(ConnectorValidationError, match="low_confidence"):
        parse_connector_response(json.dumps(payload))


def test_parser_low_confidence_accepted_when_flagged():
    payload = _good_response()
    payload["keyword_mappings"][0]["similarity"] = 0.5
    payload["keyword_mappings"][0]["low_confidence"] = True
    out = parse_connector_response(json.dumps(payload))
    assert out.keyword_mappings[0].low_confidence is True


def test_parser_source_path_index_out_of_range_rejected():
    payload = _good_response()
    payload["natural_language_relationships"][0]["source_path_index"] = 5
    with pytest.raises(ConnectorValidationError, match="out of range"):
        parse_connector_response(json.dumps(payload))


def test_parser_negative_source_path_index_rejected():
    payload = _good_response()
    payload["natural_language_relationships"][0]["source_path_index"] = -1
    with pytest.raises(ConnectorValidationError, match="non-negative"):
        parse_connector_response(json.dumps(payload))


def test_parser_similarity_out_of_range_rejected():
    payload = _good_response()
    payload["keyword_mappings"][0]["similarity"] = 1.5
    with pytest.raises(ConnectorValidationError, match="outside"):
        parse_connector_response(json.dumps(payload))


def test_parser_missing_keyword_mappings_rejected():
    payload = _good_response()
    del payload["keyword_mappings"]
    with pytest.raises(ConnectorValidationError, match="keyword_mappings"):
        parse_connector_response(json.dumps(payload))


def test_parser_missing_paths_rejected():
    payload = _good_response()
    del payload["paths"]
    with pytest.raises(ConnectorValidationError, match="paths"):
        parse_connector_response(json.dumps(payload))


def test_parser_path_with_negative_depth_rejected():
    payload = _good_response()
    payload["paths"][0]["depth"] = -1
    with pytest.raises(ConnectorValidationError, match="non-negative"):
        parse_connector_response(json.dumps(payload))


def test_parser_path_with_out_of_range_avg_confidence_rejected():
    payload = _good_response()
    payload["paths"][0]["avg_confidence"] = 1.5
    with pytest.raises(ConnectorValidationError, match="outside"):
        parse_connector_response(json.dumps(payload))


def test_parser_optional_algorithm_rationale_absent_ok():
    payload = _good_response()
    del payload["algorithm_rationale"]
    out = parse_connector_response(json.dumps(payload))
    assert out.algorithm_rationale is None


def test_parser_empty_paths_with_empty_nl_relationships_ok():
    """A connector that finds no paths and produces no NL
    relationships is valid — the role is honest about empty
    output rather than fabricating."""
    payload = _good_response()
    payload["paths"] = []
    payload["natural_language_relationships"] = []
    out = parse_connector_response(json.dumps(payload))
    assert out.paths == ()
    assert out.natural_language_relationships == ()


# ---------------------------------------------------------------------------
# D. Drift detection
# ---------------------------------------------------------------------------


def test_traversal_algorithms_match_schema_literal():
    assert TRAVERSAL_ALGORITHMS == set(typing.get_args(TraversalAlgorithm))


def test_low_confidence_threshold_documented():
    """LOW_CONFIDENCE_THRESHOLD is the upstream constant the role
    prompt cites and the parser enforces. Test that they're equal."""
    from roles.connector.prompt import (
        LOW_CONFIDENCE_THRESHOLD as PROMPT_THRESHOLD,
    )
    assert LOW_CONFIDENCE_THRESHOLD == PROMPT_THRESHOLD
