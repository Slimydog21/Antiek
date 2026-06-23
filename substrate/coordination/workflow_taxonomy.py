"""Dispatch role → product workflow map (§10 matrix).

Single source for :mod:`cost_view` and :mod:`substrate.analytics.dispatch_rows`.
Mirrors apps/reading workflow taxonomy; do not fork this map elsewhere.
"""

from __future__ import annotations

from enum import Enum

REMOTE_EXEC_PROVIDERS: frozenset[str] = frozenset({"remote_exec", "daytona"})


class Workflow(str, Enum):
    RESEARCH = "research"
    READ = "read"
    WRITE = "write"
    SPEAK = "speak"
    UNMAPPED = "unmapped"


_ROLE_WORKFLOW: dict[str, Workflow] = {
    "decomposer": Workflow.RESEARCH,
    "evidence_retriever": Workflow.RESEARCH,
    "parameter_extractor": Workflow.RESEARCH,
    "connector": Workflow.RESEARCH,
    "synthesizer": Workflow.RESEARCH,
    "user_agent": Workflow.RESEARCH,
    "tier_assigner": Workflow.RESEARCH,
    "constraint_checker": Workflow.RESEARCH,
    "verifier": Workflow.RESEARCH,
    "note_taker": Workflow.READ,
    "challenger": Workflow.READ,
    "grounder": Workflow.READ,
    "interviewer": Workflow.SPEAK,
}


def workflow_for_role(role: str | None) -> Workflow:
    if role is None:
        return Workflow.UNMAPPED
    return _ROLE_WORKFLOW.get(role, Workflow.UNMAPPED)


def is_remote_exec_provider(provider: str | None) -> bool:
    return bool(provider) and provider in REMOTE_EXEC_PROVIDERS