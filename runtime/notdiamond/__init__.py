"""NotDiamond advisory model-router adapter (Antiek × NotDiamond, ANT-ND SPR-01).

ND is an **advisory** measured wedge scoped to the Deep Research Workspace's
research-runner role calls: it recommends a model, dispatch decides, and the
``cd602c9`` verify-tier fallback owns failure. This package is the SPR-01
bootstrap — an importable, smoke-tested adapter behind the optional
``antiek[notdiamond]`` extra with **no dispatch integration** (that is SPR-03).

Importing this package has no side effects and does not import the ND SDK; the
SDK is imported lazily inside :func:`select_model`. See
``~/specs/antiek-notdiamond/index.html``.
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
