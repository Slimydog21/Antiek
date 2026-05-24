"""Challenger role — decides which claims deserve grounding checks.

Today the challenger is implicit (operator clicks "challenge this
claim" in the UI). This role module formalizes the wording + types
so the future autonomous challenger handler shares shape with the
manual path. Sprint 4 day 4-5 promotion per the operator's
"formalize roles/{challenger,grounder}/" direction.
"""

from .prompt import AUTONOMOUS_CHALLENGER_ROLE_PROMPT, DEFAULT_CHALLENGE_PROMPT
from .types import Challenge, compose_challenge

__all__ = [
    "DEFAULT_CHALLENGE_PROMPT",
    "AUTONOMOUS_CHALLENGER_ROLE_PROMPT",
    "Challenge",
    "compose_challenge",
]


# SPR-03: role-shape metadata (see substrate/role_shape.py)
from substrate.role_shape import RoleMetadata

__role_metadata__ = RoleMetadata.polecat(
    expected_input_tokens=3000,
    expected_output_tokens=800,
    spawn_pattern_doc=(
        'Pass a structured claim plus its supporting evidence chunks. Returns a typed challenge (counter-claim + suggested probe). Single-turn, no cross-module reads — the caller hands in everything needed.'
    ),
)
