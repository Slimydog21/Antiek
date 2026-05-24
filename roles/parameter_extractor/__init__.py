"""Parameter Extractor role (Sprint 7 day 2 — third orchestrate.py
role extraction, fully landed).

The constraint-producing role. Reads Evidence Retriever outputs;
emits design-critical parameters with strictness classifications.

Three submodules:

- ``prompt`` — verbatim port of ``prompts/parameter_extractor.md``.
- ``parser`` — closed-vocabulary JSON parser. Normalizes the
  upstream's three discipline rules (JSON-null vs literal "null",
  empty-string unit forbidden, value/value_type cross-consistency).
- ``converter`` — pure ``parameters_to_constraints`` function. The
  seam between this role's LLM output and the Sprint 4 day 3-4
  constraint-loop machinery. Called by the bridge at emit time so
  the Delivered payload carries both raw parameters AND derived
  ``ConstraintSpec`` records.

Bridge: ``interfaces/research/api/parameter_extractor.py``.
"""

from .converter import parameters_to_constraints
from .parser import (
    CONSTRAINT_STRICTNESS_VALUES,
    EVIDENCE_STATUS_VALUES,
    METRIC_VALUE_TYPES,
    ParameterExtractResult,
    ParameterValidationError,
    ParsedMetricValue,
    ParsedParameter,
    parse_parameter_extractor_response,
)
from .prompt import (
    PARAMETER_EXTRACTOR_PROMPT_VERSION,
    PARAMETER_EXTRACTOR_SYSTEM_PROMPT,
    PARAMETER_EXTRACTOR_TARGET_MODEL,
    PARAMETER_EXTRACTOR_TEMPERATURE,
    PARAMETER_EXTRACTOR_USER_TEMPLATE,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    # parser
    "METRIC_VALUE_TYPES",
    "EVIDENCE_STATUS_VALUES",
    "CONSTRAINT_STRICTNESS_VALUES",
    "ParameterValidationError",
    "ParsedMetricValue",
    "ParsedParameter",
    "ParameterExtractResult",
    "parse_parameter_extractor_response",
    # prompt
    "PARAMETER_EXTRACTOR_PROMPT_VERSION",
    "PARAMETER_EXTRACTOR_TARGET_MODEL",
    "PARAMETER_EXTRACTOR_TEMPERATURE",
    "PARAMETER_EXTRACTOR_SYSTEM_PROMPT",
    "PARAMETER_EXTRACTOR_USER_TEMPLATE",
    "render_user_template",
    "render_full_prompt",
    # converter
    "parameters_to_constraints",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=4000,
    expected_output_tokens=600,
    spawn_pattern_doc=(
        'Pass a sub-question plus its constraints. Returns extracted structured parameters for downstream retrieval. Single-turn; this is the role WP-A3 surfaced as the loky-semaphore failure site — kept polecat-shaped to keep fan-out cheap.'
    ),
)
