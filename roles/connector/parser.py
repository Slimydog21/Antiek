"""Connector JSON response parser.

Sprint 7 day 4. Closed-vocabulary validation. The role's output
schema has four top-level keys; structural drift is rejected
loudly.

Parser-side rules:

- ``selected_algorithm`` ∈ ``TRAVERSAL_ALGORITHMS`` (matches the
  schema's ``TraversalAlgorithm`` Literal).
- ``keyword_mappings[*]`` must carry a ``keyword`` + ``similarity``
  in [0, 1]. ``low_confidence`` is True when ``similarity < 0.80``;
  the parser checks that the role hasn't silently dropped flagged
  mappings (the upstream's anti-pattern #3).
- ``natural_language_relationships[*].source_path_index`` must
  reference an actual path index (0 ≤ idx < len(paths)). The
  upstream's prompt rule "cite the underlying graph path" is
  enforced structurally here.
- ``paths`` is pass-through — the parser does light validation
  (path_nodes is a list, depth is non-negative, etc.) but doesn't
  enforce length parity between nodes and relations because the
  traversal output the bridge fed in is already validated upstream.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

try:
    from .._json_decode import extract_json_object as _extract_json_object
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from roles._json_decode import (
        extract_json_object as _extract_json_object,
    )

try:
    from substrate.provenance.validate_refs import validate_ref, validate_refs
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.provenance.validate_refs import (
        validate_ref,
        validate_refs,
    )


TRAVERSAL_ALGORITHMS: frozenset[str] = frozenset({
    "shortest_simple_path",
    "top_n_shortest_paths",
    "depth_first_limited",
    "bfs_semantic_stop",
})

# The upstream threshold that flips a mapping to low_confidence. Must
# match ``roles.connector.prompt.LOW_CONFIDENCE_THRESHOLD``.
LOW_CONFIDENCE_THRESHOLD = 0.80


class ConnectorValidationError(ValueError):
    """Raised on any structural / vocabulary / cite-back failure."""


@dataclass(frozen=True)
class ParsedKeywordMapping:
    keyword: str
    similarity: float
    low_confidence: bool
    matched_node_id: str | None = None
    matched_node_label: str | None = None
    matched_node_type: str | None = None


@dataclass(frozen=True)
class ParsedGraphPath:
    path_nodes: tuple[str, ...]
    path_relations: tuple[str, ...]
    depth: int
    avg_confidence: float
    node_labels: tuple[str, ...] = field(default_factory=tuple)
    edge_ids: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ParsedNlRelationship:
    text: str
    source_path_index: int


@dataclass(frozen=True)
class ConnectorResult:
    keyword_mappings: tuple[ParsedKeywordMapping, ...]
    selected_algorithm: str
    algorithm_rationale: str | None
    paths: tuple[ParsedGraphPath, ...]
    natural_language_relationships: tuple[ParsedNlRelationship, ...]
    raw: dict[str, Any]


def _require_str(obj: Any, field_name: str, ctx: str, *, allow_empty: bool = False) -> str:
    if not isinstance(obj, str):
        raise ConnectorValidationError(
            f"{ctx}: {field_name!r} must be a string (got {type(obj).__name__})"
        )
    if not allow_empty and not obj.strip():
        raise ConnectorValidationError(
            f"{ctx}: {field_name!r} must be a non-empty string"
        )
    return obj


def _opt_str(obj: Any, field_name: str, ctx: str) -> str | None:
    if obj is None:
        return None
    if not isinstance(obj, str):
        raise ConnectorValidationError(
            f"{ctx}: {field_name!r} must be a string or null"
        )
    return obj if obj else None


def _opt_str_list(obj: Any, field_name: str, ctx: str) -> list[str]:
    if obj is None:
        return []
    if not isinstance(obj, list):
        raise ConnectorValidationError(
            f"{ctx}: {field_name!r} must be a list (got {type(obj).__name__})"
        )
    out: list[str] = []
    for i, v in enumerate(obj):
        if not isinstance(v, str):
            raise ConnectorValidationError(
                f"{ctx}.{field_name}[{i}]: must be a string"
            )
        out.append(v)
    return out


def _parse_keyword_mapping(
    obj: Any,
    idx: int,
    canonical_node_ids: Iterable[str] | None = None,
) -> ParsedKeywordMapping:
    ctx = f"keyword_mappings[{idx}]"
    if not isinstance(obj, dict):
        raise ConnectorValidationError(f"{ctx}: expected an object")
    keyword = _require_str(obj.get("keyword"), "keyword", ctx)
    sim_raw = obj.get("similarity")
    if not isinstance(sim_raw, (int, float)) or isinstance(sim_raw, bool):
        raise ConnectorValidationError(
            f"{ctx}: similarity must be a number in [0, 1]"
        )
    sim = float(sim_raw)
    if not 0.0 <= sim <= 1.0:
        raise ConnectorValidationError(
            f"{ctx}: similarity={sim} outside [0, 1]"
        )
    low_conf = bool(obj.get("low_confidence", False))
    # Discipline check: low_confidence must agree with the threshold.
    # The upstream anti-pattern #3 is "dropping low-confidence
    # mappings"; if the role marks something low_confidence=false
    # despite similarity < threshold, the structural check fails
    # loudly so a downstream consumer doesn't trust the flag.
    if sim < LOW_CONFIDENCE_THRESHOLD and not low_conf:
        raise ConnectorValidationError(
            f"{ctx}: similarity={sim} < {LOW_CONFIDENCE_THRESHOLD} but "
            f"low_confidence=false — the upstream threshold mandates the "
            "flag (anti-pattern #3: dropping low-confidence mappings)"
        )

    matched_node_id = _opt_str(obj.get("matched_node_id"), "matched_node_id", ctx)
    if canonical_node_ids is not None:
        matched_node_id = validate_ref(matched_node_id, canonical_node_ids)

    return ParsedKeywordMapping(
        keyword=keyword,
        similarity=sim,
        low_confidence=low_conf,
        matched_node_id=matched_node_id,
        matched_node_label=_opt_str(obj.get("matched_node_label"), "matched_node_label", ctx),
        matched_node_type=_opt_str(obj.get("matched_node_type"), "matched_node_type", ctx),
    )


def _parse_path(
    obj: Any,
    idx: int,
    canonical_node_ids: Iterable[str] | None = None,
    canonical_edge_ids: Iterable[str] | None = None,
) -> ParsedGraphPath:
    ctx = f"paths[{idx}]"
    if not isinstance(obj, dict):
        raise ConnectorValidationError(f"{ctx}: expected an object")
    raw_nodes = _opt_str_list(obj.get("path_nodes"), "path_nodes", ctx)
    if canonical_node_ids is None:
        nodes = tuple(raw_nodes)
    else:
        nodes = validate_refs(raw_nodes, canonical_node_ids)
        if raw_nodes and not nodes:
            raise ConnectorValidationError(
                f"{ctx}: path_nodes resolved to empty after canonical validation"
            )
    relations = tuple(_opt_str_list(obj.get("path_relations"), "path_relations", ctx))
    labels = tuple(_opt_str_list(obj.get("node_labels"), "node_labels", ctx))
    raw_edge_ids = _opt_str_list(obj.get("edge_ids"), "edge_ids", ctx)
    if canonical_edge_ids is None:
        edge_ids = tuple(raw_edge_ids)
    else:
        edge_ids = validate_refs(raw_edge_ids, canonical_edge_ids)
    depth_raw = obj.get("depth")
    if not isinstance(depth_raw, int) or isinstance(depth_raw, bool) or depth_raw < 0:
        raise ConnectorValidationError(
            f"{ctx}: depth must be a non-negative integer"
        )
    conf_raw = obj.get("avg_confidence")
    if not isinstance(conf_raw, (int, float)) or isinstance(conf_raw, bool):
        raise ConnectorValidationError(
            f"{ctx}: avg_confidence must be a number"
        )
    conf = float(conf_raw)
    if not 0.0 <= conf <= 1.0:
        raise ConnectorValidationError(
            f"{ctx}: avg_confidence={conf} outside [0, 1]"
        )
    return ParsedGraphPath(
        path_nodes=nodes,
        path_relations=relations,
        depth=depth_raw,
        avg_confidence=conf,
        node_labels=labels,
        edge_ids=edge_ids,
    )


def _parse_nl_relationship(obj: Any, idx: int, n_paths: int) -> ParsedNlRelationship:
    ctx = f"natural_language_relationships[{idx}]"
    if not isinstance(obj, dict):
        raise ConnectorValidationError(f"{ctx}: expected an object")
    text = _require_str(obj.get("text"), "text", ctx)
    spi_raw = obj.get("source_path_index")
    if not isinstance(spi_raw, int) or isinstance(spi_raw, bool) or spi_raw < 0:
        raise ConnectorValidationError(
            f"{ctx}: source_path_index must be a non-negative integer"
        )
    if spi_raw >= n_paths:
        raise ConnectorValidationError(
            f"{ctx}: source_path_index={spi_raw} out of range "
            f"(only {n_paths} paths supplied) — the role must cite an "
            "actual path (anti-pattern: NL relationships without cite-back)"
        )
    return ParsedNlRelationship(text=text, source_path_index=spi_raw)


def parse_connector_response(
    text: str,
    *,
    canonical_node_ids: Iterable[str] | None = None,
    canonical_edge_ids: Iterable[str] | None = None,
) -> ConnectorResult:
    """Parse + validate a Connector role's raw response."""
    obj = _extract_json_object(text)
    if not isinstance(obj, dict):
        raise ConnectorValidationError(
            "response did not contain a parseable JSON object"
        )

    mappings_raw = obj.get("keyword_mappings")
    if not isinstance(mappings_raw, list):
        raise ConnectorValidationError("top: keyword_mappings must be a list")
    keyword_mappings = tuple(
        _parse_keyword_mapping(m, i, canonical_node_ids)
        for i, m in enumerate(mappings_raw)
    )

    algorithm = _require_str(
        obj.get("selected_algorithm"), "selected_algorithm", "top",
    )
    if algorithm not in TRAVERSAL_ALGORITHMS:
        raise ConnectorValidationError(
            f"top: selected_algorithm {algorithm!r} not in "
            f"{sorted(TRAVERSAL_ALGORITHMS)}"
        )
    rationale = _opt_str(
        obj.get("algorithm_rationale"), "algorithm_rationale", "top",
    )

    paths_raw = obj.get("paths")
    if not isinstance(paths_raw, list):
        raise ConnectorValidationError("top: paths must be a list")
    paths = tuple(
        _parse_path(p, i, canonical_node_ids, canonical_edge_ids)
        for i, p in enumerate(paths_raw)
    )

    nl_raw = obj.get("natural_language_relationships")
    if not isinstance(nl_raw, list):
        raise ConnectorValidationError(
            "top: natural_language_relationships must be a list"
        )
    nl = tuple(
        _parse_nl_relationship(n, i, n_paths=len(paths))
        for i, n in enumerate(nl_raw)
    )

    return ConnectorResult(
        keyword_mappings=keyword_mappings,
        selected_algorithm=algorithm,
        algorithm_rationale=rationale,
        paths=paths,
        natural_language_relationships=nl,
        raw=obj,
    )
