"""NotDiamond advisory adapter for Antiek.

Importing this package has no SDK side effects. The optional ``notdiamond``
package is imported lazily inside ``select_model`` only.
"""

from __future__ import annotations

from .adapter import select_model
from .types import (
    NotDiamondAPIError,
    NotDiamondAuthError,
    NotDiamondError,
    NotDiamondNotInstalled,
    NotDiamondTimeout,
    Recommendation,
)

__all__ = [
    "select_model",
    "Recommendation",
    "NotDiamondError",
    "NotDiamondNotInstalled",
    "NotDiamondAuthError",
    "NotDiamondTimeout",
    "NotDiamondAPIError",
]
