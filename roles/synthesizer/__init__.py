"""Synthesizer role (Sprint 7 day 5 — last orchestrate.py role
extraction; the largest and most state-heavy of the four).

The thesis-producing role. Reads the outputs of all four upstream
roles (decomposer + evidence_retriever + parameter_extractor +
connector) and synthesizes a defensible thesis under the tier-hedging
discipline (spec §C.3, ``substrate.constants.TIER_HEDGING_POLICY``).

The bridge handler is the ONLY one in Loop 1 that wires the
constraint loop (Sprint 7 day 3 machinery): synthesizer output →
constraint check → if hard violations, re-dispatch with violation
context prefix → terminate with ``ConstraintLoopStatus``.

Two submodules:

- ``prompt`` — verbatim port of ``prompts/synthesizer.md`` +
  ``build_revision_prefix`` helper the bridge uses to prepend
  violation context on constraint-loop re-dispatches.
- ``parser`` — closed-vocabulary parser enforcing:
  - 4-value confidence + recommendation enums (NOT "medium",
    NOT "uncertain")
  - tier-hedging discipline (Tier 5 excluded; null treated as Tier 5;
    Tier 4 caps confidence at low; Tier 3 requires hedging_required)
  - ``support_summary`` ≥ 20 chars
  - provenance-is-structural (every component cites chunks OR paths,
    except when insufficient_evidence)
  - ``effective_source_tier`` ∈ [1, 5] OR null (NEVER 0)
"""

from .parser import (
    CONFIDENCE_LEVELS,
    EXECUTION_RISK_SEVERITIES,
    IMPLICIT_RECOMMENDATIONS,
    SUPPORT_SUMMARY_MIN_LENGTH,
    TIER_THAT_EXCLUDES,
    TIER_THAT_LIMITS_CONFIDENCE_LOW,
    TIER_THAT_REQUIRES_HEDGING_FLAG,
    ParsedConstraintCompliance,
    ParsedExecutionRisk,
    ParsedFalsificationCondition,
    ParsedReasoningPath,
    ParsedThesisComponent,
    ParsedViolationJustification,
    SynthesizerValidationError,
    ThesisResult,
    parse_synthesizer_response,
)
from .prompt import (
    SYNTHESIZER_PROMPT_VERSION,
    SYNTHESIZER_SYSTEM_PROMPT,
    SYNTHESIZER_TARGET_MODEL,
    SYNTHESIZER_TEMPERATURE,
    SYNTHESIZER_USER_TEMPLATE,
    build_revision_prefix,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    # parser
    "CONFIDENCE_LEVELS",
    "IMPLICIT_RECOMMENDATIONS",
    "EXECUTION_RISK_SEVERITIES",
    "SUPPORT_SUMMARY_MIN_LENGTH",
    "TIER_THAT_REQUIRES_HEDGING_FLAG",
    "TIER_THAT_LIMITS_CONFIDENCE_LOW",
    "TIER_THAT_EXCLUDES",
    "SynthesizerValidationError",
    "ParsedThesisComponent",
    "ParsedFalsificationCondition",
    "ParsedExecutionRisk",
    "ParsedViolationJustification",
    "ParsedConstraintCompliance",
    "ParsedReasoningPath",
    "ThesisResult",
    "parse_synthesizer_response",
    # prompt
    "SYNTHESIZER_PROMPT_VERSION",
    "SYNTHESIZER_TARGET_MODEL",
    "SYNTHESIZER_TEMPERATURE",
    "SYNTHESIZER_SYSTEM_PROMPT",
    "SYNTHESIZER_USER_TEMPLATE",
    "render_user_template",
    "render_full_prompt",
    "build_revision_prefix",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.crew(
    expected_input_tokens=16000,
    expected_output_tokens=4000,
    spawn_pattern_doc=(
        'Pass a constraint-checked evidence set plus the target question. Returns synthesis prose. May iterate with the caller across rubric-driven revision cycles.'
    ),
)
