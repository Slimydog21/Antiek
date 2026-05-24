"""Decomposer role (Sprint 5 day 4-5 — paraphrase + seeds shipped).

Top-level question → sub-questions. This package will eventually own
the role's prompt, parser, and bridge handler; Sprint 5 day 4-5
lands the two helpers the role's quality bar depends on:

- ``paraphrase`` — sub-question similarity check vs the top-level
  question (spec §A.1 mitigation).
- ``seeds`` — mining of admitted few-shot examples from past
  trajectories that the human reviewer can promote into
  ``examples.jsonl``.

What's deferred (Sprint 6+):

- ``prompt.py`` + ``parser.py`` + ``types.py`` (the role itself).
- Bridge handler (subscribes to question.identified / sub-question
  events).
- The DB loader path on top of ``propose_examples_from_rows`` — wires
  in when ``substrate/init_db.py`` extends to syntheses + outcomes
  tables. The pure mining function ships now so the criteria can be
  validated against fixtures.
"""

from .paraphrase import (
    ParaphraseFlag,
    check_paraphrases,
    regenerate_instruction,
)
from .parser import (
    DECOMPOSER_CATEGORIES,
    DECOMPOSER_EVIDENCE_TYPES,
    MAX_SYNONYMS_PER_KEYWORD,
    DecomposerValidationError,
    DecompositionResult,
    ParsedKeyword,
    ParsedSubQuestion,
    parse_decomposer_response,
)
from .prompt import (
    DECOMPOSER_PROMPT_VERSION,
    DECOMPOSER_SYSTEM_PROMPT,
    DECOMPOSER_TARGET_MODEL,
    DECOMPOSER_TEMPERATURE,
    DECOMPOSER_USER_TEMPLATE,
    render_full_prompt,
    render_user_template,
)
from .seeds import (
    CandidateRow,
    DecomposerExampleProposal,
    count_confirmed,
    extract_decomposer_io,
    paraphrase_clean,
    propose_examples_from_rows,
)

__all__ = [
    # paraphrase
    "ParaphraseFlag",
    "check_paraphrases",
    "regenerate_instruction",
    # parser
    "DECOMPOSER_CATEGORIES",
    "DECOMPOSER_EVIDENCE_TYPES",
    "MAX_SYNONYMS_PER_KEYWORD",
    "DecomposerValidationError",
    "DecompositionResult",
    "ParsedSubQuestion",
    "ParsedKeyword",
    "parse_decomposer_response",
    # prompt
    "DECOMPOSER_PROMPT_VERSION",
    "DECOMPOSER_TARGET_MODEL",
    "DECOMPOSER_TEMPERATURE",
    "DECOMPOSER_SYSTEM_PROMPT",
    "DECOMPOSER_USER_TEMPLATE",
    "render_user_template",
    "render_full_prompt",
    # seeds
    "CandidateRow",
    "DecomposerExampleProposal",
    "count_confirmed",
    "extract_decomposer_io",
    "paraphrase_clean",
    "propose_examples_from_rows",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=4000,
    expected_output_tokens=1500,
    spawn_pattern_doc=(
        'Pass a top-level research question plus the domain frame. Returns typed sub-questions (ParsedSubQuestion). Single-turn; parser + paraphrase check guarantee a stable shape.'
    ),
)
