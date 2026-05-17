"""Grounder role — fact-checks a challenged claim against source chunks.

Subscribed to ``claim.challenge_raised`` events via the bridge handler
at ``interfaces/research/api/grounding.py``. The bridge does the
infrastructure work (chunk search, dispatch, broadcast); this role
module owns the role-specific logic — the prompt the model sees and
the parser that interprets its response.

Sprint 4 day 4-5 split the bridge from the role per the operator's
"formalize roles/{challenger,grounder}/ as proper role modules"
direction — same shape as the orchestrate.py roles arriving in
Sprint 5.
"""

from .parser import (
    GROUNDING_FAILURE_REASONS,
    GroundingFailureReason,
    GroundingVerdict,
    parse_grounder_response,
)
from .prompt import GROUNDER_ROLE_PROMPT

__all__ = [
    "GROUNDER_ROLE_PROMPT",
    "GROUNDING_FAILURE_REASONS",
    "GroundingFailureReason",
    "GroundingVerdict",
    "parse_grounder_response",
]
