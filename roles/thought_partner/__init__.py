"""Thought-partner role — Surface E Brainstorming Workstation (Sprint 18 polish).

The user selects a set of notes from their private graph + a prompt;
this role produces challenges, syntheses, or extensions. Same
recursive note-taking pattern as the autonomous chase, just initiated
by user selection rather than autonomous trigger.

Per master-spec §4.5 components ("thought-partner workflow") + §2.6
(curiosity-capture primitive). This is the role that turns the
brainstorming workstation from a passive parking lot into an active
thought partner.
"""

from .prompt import THOUGHT_PARTNER_SYSTEM_PROMPT, compose_thought_partner_prompt
from .parser import (
    VALID_SHAPES,
    Challenge,
    Extension,
    Synthesis,
    ThoughtPartnerResponse,
    parse_thought_partner_response,
)

__all__ = [
    "THOUGHT_PARTNER_SYSTEM_PROMPT",
    "VALID_SHAPES",
    "compose_thought_partner_prompt",
    "Challenge",
    "Extension",
    "Synthesis",
    "ThoughtPartnerResponse",
    "parse_thought_partner_response",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.crew(
    expected_input_tokens=12000,
    expected_output_tokens=3000,
    spawn_pattern_doc=(
        'Multi-turn design conversation. Pass current artifact + question; the role pushes back, asks clarifying questions, and helps the operator think. Not idempotent — the conversation IS the value.'
    ),
)
