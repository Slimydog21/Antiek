"""Creative writer role — Sprint 13.

Inverse of the synthesizer. Takes operator-assembled blocks
(insights / claims / questions / notes) attached to a deliverable
section and produces publishable prose.

Two submodules:

- ``prompt`` — system prompt + user-template renderer + the
  ``CreativeWriterContext`` shape the bridge fills.
- ``parser`` — closed-vocabulary parser that validates
  ``{prose_text, prose_provenance, uncited_blocks}`` and enforces
  block_id consistency.
"""

from .parser import (
    CreativeWriterResult,
    CreativeWriterValidationError,
    parse_creative_writer_response,
)
from .prompt import (
    CREATIVE_WRITER_PROMPT_VERSION,
    CREATIVE_WRITER_SYSTEM_PROMPT,
    CREATIVE_WRITER_TEMPERATURE,
    CREATIVE_WRITER_TIER,
    CREATIVE_WRITER_USER_TEMPLATE,
    AdjacentSection,
    CreativeWriterBlock,
    CreativeWriterContext,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    "CREATIVE_WRITER_PROMPT_VERSION",
    "CREATIVE_WRITER_SYSTEM_PROMPT",
    "CREATIVE_WRITER_TEMPERATURE",
    "CREATIVE_WRITER_TIER",
    "CREATIVE_WRITER_USER_TEMPLATE",
    "AdjacentSection",
    "CreativeWriterBlock",
    "CreativeWriterContext",
    "CreativeWriterResult",
    "CreativeWriterValidationError",
    "parse_creative_writer_response",
    "render_full_prompt",
    "render_user_template",
]
