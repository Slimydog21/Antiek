"""Verifier-shaped environments for the Antiek roles.

Each role gets its own ``<role>_env.py`` module wrapping the role as a
training-task harness with the
``Task / Rollout / Reward / Environment`` quartet. The shapes mirror
``verifiers.Environment`` so the future import-of-verifiers refactor is
mechanical, not architectural.

Sprint 9 day 5 port of ``researchmaxx/environments/decomposer_env.py``.
"""

from .decomposer_env import (
    DecomposerEnvironment,
    DecomposerReward,
    DecomposerRollout,
    DecomposerTask,
)

__all__ = [
    "DecomposerEnvironment",
    "DecomposerReward",
    "DecomposerRollout",
    "DecomposerTask",
]
