"""Challenger role — decides which claims deserve grounding checks.

Today the challenger is implicit (operator clicks "challenge this
claim" in the UI). This role module formalizes the wording + types
so the future autonomous challenger handler shares shape with the
manual path. Sprint 4 day 4-5 promotion per the operator's
"formalize roles/{challenger,grounder}/" direction.
"""

from .prompt import AUTONOMOUS_CHALLENGER_ROLE_PROMPT, DEFAULT_CHALLENGE_PROMPT
from .resolver import (
    RESOLVE_OR_DECLINE_PROMPT,
    ChallengeUnavailable,
    make_dispatch_resolver,
    parse_resolution,
)
from .types import Challenge, compose_challenge

__all__ = [
    "DEFAULT_CHALLENGE_PROMPT",
    "AUTONOMOUS_CHALLENGER_ROLE_PROMPT",
    "Challenge",
    "compose_challenge",
    # DRW SPR-03 — the resolver living_note.challenge_note drives
    "ChallengeUnavailable",
    "RESOLVE_OR_DECLINE_PROMPT",
    "make_dispatch_resolver",
    "parse_resolution",
]
