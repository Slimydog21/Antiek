"""Model routing advisory contracts."""

from .notdiamond_advisor import (
    NotDiamondAdvisorCandidate,
    NotDiamondAdvisorRecommendation,
    NotDiamondExternalRecommendation,
    NotDiamondPromotionGate,
    advisor_mode_from_env,
    resolve_notdiamond_advisor,
)

__all__ = [
    "NotDiamondAdvisorCandidate",
    "NotDiamondAdvisorRecommendation",
    "NotDiamondExternalRecommendation",
    "NotDiamondPromotionGate",
    "advisor_mode_from_env",
    "resolve_notdiamond_advisor",
]
