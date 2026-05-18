"""Interviewer role — Sprint 16 (master spec §11.3).

Multi-turn conversational role used by Loop 4 (interviews). Differs
from every other role in that the bridge calls it repeatedly with
the growing transcript as user-template input until the role signals
``should_end``.

Two submodules:

- ``prompt`` — system prompt + user-template renderer + ``InterviewerContext``
- ``parser`` — JSON parser enforcing utterance length, indices shape,
  and the should_end signal.
"""

from .parser import (
    InterviewerResult,
    InterviewerValidationError,
    parse_interviewer_response,
)
from .prompt import (
    INTERVIEWER_PROMPT_VERSION,
    INTERVIEWER_SYSTEM_PROMPT,
    INTERVIEWER_TEMPERATURE,
    INTERVIEWER_TIER,
    INTERVIEWER_USER_TEMPLATE,
    InterviewerContext,
    TranscriptTurn,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    "INTERVIEWER_PROMPT_VERSION",
    "INTERVIEWER_SYSTEM_PROMPT",
    "INTERVIEWER_TEMPERATURE",
    "INTERVIEWER_TIER",
    "INTERVIEWER_USER_TEMPLATE",
    "InterviewerContext",
    "InterviewerResult",
    "InterviewerValidationError",
    "TranscriptTurn",
    "parse_interviewer_response",
    "render_full_prompt",
    "render_user_template",
]
