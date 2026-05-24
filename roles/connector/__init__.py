"""Cross-Domain Connector role (Sprint 7 day 4 — fourth orchestrate.py
role extraction).

The relational reasoning role. Confirms/corrects pre-resolved
keyword→node mappings, picks a traversal algorithm, and renders the
structured paths in natural language with cite-back so the
Synthesizer can ground its thesis components in the graph.

Two submodules:

- ``prompt`` — verbatim port of ``prompts/cross_domain_connector.md``
  plus ``render_mappings_block`` / ``render_paths_block`` helpers
  the bridge uses to turn typed input lists into the prompt's
  string blocks.
- ``parser`` — closed-vocabulary parser. Enforces the four
  algorithm Literals, the cite-back rule (NL relationship's
  ``source_path_index`` must reference an actual path), and the
  low-confidence flag discipline (anti-pattern #3).

Bridge: ``interfaces/research/api/connector.py``.
"""

from .parser import (
    LOW_CONFIDENCE_THRESHOLD,
    TRAVERSAL_ALGORITHMS,
    ConnectorResult,
    ConnectorValidationError,
    ParsedGraphPath,
    ParsedKeywordMapping,
    ParsedNlRelationship,
    parse_connector_response,
)
from .prompt import (
    CONNECTOR_PROMPT_VERSION,
    CONNECTOR_SYSTEM_PROMPT,
    CONNECTOR_TARGET_MODEL,
    CONNECTOR_TEMPERATURE,
    CONNECTOR_USER_TEMPLATE,
    render_full_prompt,
    render_mappings_block,
    render_paths_block,
    render_user_template,
)

__all__ = [
    # parser
    "TRAVERSAL_ALGORITHMS",
    "LOW_CONFIDENCE_THRESHOLD",
    "ConnectorValidationError",
    "ParsedKeywordMapping",
    "ParsedGraphPath",
    "ParsedNlRelationship",
    "ConnectorResult",
    "parse_connector_response",
    # prompt
    "CONNECTOR_PROMPT_VERSION",
    "CONNECTOR_TARGET_MODEL",
    "CONNECTOR_TEMPERATURE",
    "CONNECTOR_SYSTEM_PROMPT",
    "CONNECTOR_USER_TEMPLATE",
    "render_mappings_block",
    "render_paths_block",
    "render_user_template",
    "render_full_prompt",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=5000,
    expected_output_tokens=1200,
    spawn_pattern_doc=(
        'Pass a node + neighborhood subset. Returns a typed list of candidate connections to other nodes with confidence scores. Single-turn; the caller materializes the neighborhood from the graph.'
    ),
)
