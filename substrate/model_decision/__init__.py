"""Advisory model decision tree (operator model-choice substrate).

Never production dispatch authority — see ``tree.AUTHORITY``.
"""

from .tree import (
    AUTHORITY,
    DecisionTreeResult,
    ModelCandidate,
    RankedModel,
    rank_models_for_task,
    result_to_dict,
)

__all__ = [
    "AUTHORITY",
    "DecisionTreeResult",
    "ModelCandidate",
    "RankedModel",
    "rank_models_for_task",
    "result_to_dict",
]
