"""Cross-Domain Connector role prompt.

Sprint 7 day 4 — fourth orchestrate.py role extraction. Verbatim
port of Researchmaxx ``prompts/cross_domain_connector.md``. The role
confirms/corrects pre-resolved keyword→node mappings, picks a
traversal algorithm, passes structured paths through verbatim, and
renders each path in natural language with cite-back to the path
index.

The two placeholders the bridge fills:

- ``{{mappings_block}}`` — rendered keyword candidate mappings
  (one per line: keyword + matched node + similarity + low_confidence
  flag).
- ``{{paths_block}}`` — rendered structured paths (one per line:
  path_nodes + relations + depth + confidence).

The bridge produces both blocks from the typed ``KeywordMapping`` /
``GraphPath`` lists on the Request payload, after running
``substrate.graph.traverse`` against the seed pairs.
"""

from __future__ import annotations

CONNECTOR_PROMPT_VERSION = "1.0.0"
CONNECTOR_TARGET_MODEL = "deepseek/deepseek-v4-pro"
CONNECTOR_TEMPERATURE = 0.0


CONNECTOR_SYSTEM_PROMPT = """
You are a relational reasoning analyst. You will receive the keywords surfaced by the Parameter Extractor and a small set of pre-resolved candidate node mappings. Your task is to:

1. **Confirm or correct each keyword→node mapping.** For each keyword, the system has supplied the closest-matching node by embedding similarity. If similarity is below 0.80, the mapping is flagged `low_confidence` — accept it but mark it. Never invent a node that is not in the candidate set.

2. **Select one traversal algorithm** based on the analytical task at hand:
   - `shortest_simple_path` — establishing connectivity between two concepts
   - `top_n_shortest_paths` — enumerating mechanisms by which one concept relates to another (N = 5 by default)
   - `depth_first_limited` — tracing causal chains (depth = 5 by default)
   - `bfs_semantic_stop` — when a specific constraint node must be honored on the path; the constraint serves as a waypoint

   State your choice in `selected_algorithm` and explain in `algorithm_rationale` why this task calls for that algorithm.

3. **Pass through the structured paths** the system supplies (under `paths`) verbatim. These are the citation substrate. Do not edit them.

4. **Render each path as natural-language relationships** in `natural_language_relationships`, one entry per path. Each NL rendering must reference its `source_path_index` so the Synthesizer can cite the underlying graph path.

## Anti-patterns to suppress

Before you respond, verify your draft does **not** exhibit any of these:

1. **Synthesizing.** You are not the Synthesizer. Do not draw conclusions, propose hypotheses, or interpret what the paths "mean" for the investment thesis. Render the relational substrate cleanly and stop.
2. **Inventing edges or nodes.** Every node and edge in your output must exist in the candidate set or in the supplied paths. The graph is the source of truth.
3. **Dropping low-confidence mappings.** A mapping with similarity below 0.80 still appears in the output, just with `low_confidence: true`. Silently dropping it hides the weakness from the Synthesizer.
4. **Producing prose paragraphs.** Each NL relationship is one or two sentences max. The Synthesizer aggregates; you do not.
""".strip()


CONNECTOR_USER_TEMPLATE = """
## Keyword candidate mappings (from embedding pre-resolution)

{{mappings_block}}

## Available algorithms

The supplied paths were produced by running the chosen algorithm. Confirm the choice in your output even though the traversal has already executed.

## Structured paths (from traversal — pass through verbatim)

{{paths_block}}

Produce a single JSON object conforming to the output schema. No prose outside the JSON.

## Output structure (MANDATORY — use these exact field names)

```json
{
  "keyword_mappings": [
    {
      "keyword": "the keyword string",
      "matched_node_id": "node-uuid-or-null",
      "matched_node_label": "node label or null",
      "matched_node_type": "constraint|metric|mechanism|etc or null",
      "similarity": 0.85,
      "low_confidence": false
    }
  ],
  "selected_algorithm": "top_n_shortest_paths",
  "algorithm_rationale": "why this algorithm",
  "paths": [
    {
      "path_nodes": ["node_id_1", "node_id_2"],
      "node_labels": ["Label 1", "Label 2"],
      "path_relations": ["relates_to"],
      "depth": 1,
      "avg_confidence": 0.9,
      "edge_ids": ["edge_id_1"]
    }
  ],
  "natural_language_relationships": [
    {
      "text": "Node A relates to Node B via mechanism X.",
      "source_path_index": 0
    }
  ]
}
```

Field rules:
- Top-level keys are EXACTLY `keyword_mappings`, `selected_algorithm`, `paths`, `natural_language_relationships` — plus optional `algorithm_rationale`.
- The mapping array is called `keyword_mappings` (NOT `mappings` or `node_mappings`).
- Each NL relationship MUST have `text` and `source_path_index`.
- Paths pass through verbatim from the system — do not edit them.
""".strip()


# ---------------------------------------------------------------------------
# Render helpers — the bridge calls these to turn typed inputs into the
# string blocks the prompt template substitutes.
# ---------------------------------------------------------------------------


LOW_CONFIDENCE_THRESHOLD = 0.80


def render_mappings_block(mappings: list) -> str:
    """Render a list of ``KeywordMapping`` (or compatible dicts) as
    a markdown bullet list the role reads. Each line:

        - keyword="X" → node_id=N (label="L", type=T, sim=0.85,
          low_confidence=false)
    """
    if not mappings:
        return "(no pre-resolved mappings)"
    lines: list[str] = []
    for m in mappings:
        kw = _get(m, "keyword", "(no keyword)")
        nid = _get(m, "matched_node_id") or "null"
        label = _get(m, "matched_node_label") or "null"
        ntype = _get(m, "matched_node_type") or "null"
        sim = _get(m, "similarity", 0.0)
        lc = bool(_get(m, "low_confidence", False))
        lines.append(
            f"- keyword={kw!r} → node_id={nid} (label={label!r}, "
            f"type={ntype}, sim={float(sim):.3f}, low_confidence={str(lc).lower()})"
        )
    return "\n".join(lines)


def render_paths_block(paths: list) -> str:
    """Render structured paths as a numbered markdown list. The
    index here is the ``source_path_index`` the role cites back to
    in ``natural_language_relationships``."""
    if not paths:
        return "(no paths surfaced — graph may not connect these concepts)"
    lines: list[str] = []
    for i, p in enumerate(paths):
        nodes = _get(p, "path_nodes", [])
        labels = _get(p, "node_labels", []) or nodes
        relations = _get(p, "path_relations", [])
        depth = _get(p, "depth", 0)
        avg_conf = _get(p, "avg_confidence", 0.0)
        # Interleave nodes and relations: node-1 -[rel-1]-> node-2 ...
        chain_parts = [str(labels[0])] if labels else []
        for j, rel in enumerate(relations):
            if j + 1 < len(labels):
                chain_parts.append(f" -[{rel}]-> {labels[j + 1]}")
        chain = "".join(chain_parts) if chain_parts else "(empty)"
        lines.append(
            f"[{i}] depth={depth}, avg_confidence={float(avg_conf):.3f}: {chain}"
        )
    return "\n".join(lines)


def _get(obj, key, default=None):
    """Tolerate dict OR pydantic-model inputs in render helpers."""
    if hasattr(obj, key):
        return getattr(obj, key)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return default


def render_user_template(
    *, mappings_block: str, paths_block: str,
) -> str:
    out = CONNECTOR_USER_TEMPLATE
    out = out.replace("{{mappings_block}}", mappings_block or "(empty)")
    out = out.replace("{{paths_block}}", paths_block or "(empty)")
    return out


def render_full_prompt(
    *,
    mappings_block: str,
    paths_block: str,
    extra_user_prefix: str = "",
) -> str:
    """Concatenate system + user prompt."""
    user = render_user_template(
        mappings_block=mappings_block, paths_block=paths_block,
    )
    if extra_user_prefix:
        user = extra_user_prefix.strip() + "\n\n" + user
    return CONNECTOR_SYSTEM_PROMPT + "\n\n" + user
