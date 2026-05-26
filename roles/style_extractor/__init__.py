"""Style Extractor role (Sprint 11 — implements the designed-but-unbuilt
role from ``docs/strategy/voice-and-style-discipline.md`` §"Change 3").

The role reads the top-K corpus chunks for an investigation and produces
a 150-300 word sector-specific style guide. That guide is injected into
the synthesizer's context pack as a new ``kind="style_guide"`` layer so
the synthesis absorbs the corpus's own register/vocabulary instead of
generic AI English (master-spec §5).

It is feature-flagged OFF by default and runs ONLY for qualitative
investigations. The skip heuristic + the feature flag both live in
``substrate/context_pack/style_guide.py``:

- Flag: ``ANTIEK_STYLE_EXTRACTOR_ENABLED`` (default OFF). With the flag
  OFF, no ``style_guide`` layer is added and the assembled pack is
  byte-identical to today.
- Heuristic: ``should_run_style_extractor`` skips the extractor when
  >50% of the decomposer's sub-questions are pure-quantitative.

Module layout matches the other roles:

- ``prompt`` — system prompt + ``{{placeholder}}`` user template +
  ``render_full_prompt``.
- ``parser`` — closed-vocabulary JSON parser → ``StyleGuide`` dataclass.
  Malformed responses raise ``StyleExtractorValidationError``, which the
  wiring catches to degrade gracefully (skip injection, never crash).

Deferred / operator-bound:

- The bridge handler (subscribe → dispatch → parse → inject) lands when
  the operator turns the flag on. There are no provider keys in the
  worktree, so the role cannot be exercised against a live model here;
  the keyed first-run is operator-bound (see ``program.md``).
"""

from .parser import (
    FORBIDDEN_MAX_PATTERNS,
    FORBIDDEN_MIN_PATTERNS,
    REQUIRED_KEYS,
    VOCABULARY_MAX_TERMS,
    VOCABULARY_MIN_TERMS,
    StyleExtractorValidationError,
    StyleGuide,
    parse_style_extractor_response,
)
from .prompt import (
    STYLE_EXTRACTOR_PROMPT_VERSION,
    STYLE_EXTRACTOR_SYSTEM_PROMPT,
    STYLE_EXTRACTOR_TARGET_MODEL,
    STYLE_EXTRACTOR_TEMPERATURE,
    STYLE_EXTRACTOR_USER_TEMPLATE,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    # parser
    "StyleGuide",
    "StyleExtractorValidationError",
    "parse_style_extractor_response",
    "REQUIRED_KEYS",
    "VOCABULARY_MIN_TERMS",
    "VOCABULARY_MAX_TERMS",
    "FORBIDDEN_MIN_PATTERNS",
    "FORBIDDEN_MAX_PATTERNS",
    # prompt
    "STYLE_EXTRACTOR_PROMPT_VERSION",
    "STYLE_EXTRACTOR_TARGET_MODEL",
    "STYLE_EXTRACTOR_TEMPERATURE",
    "STYLE_EXTRACTOR_SYSTEM_PROMPT",
    "STYLE_EXTRACTOR_USER_TEMPLATE",
    "render_user_template",
    "render_full_prompt",
]
