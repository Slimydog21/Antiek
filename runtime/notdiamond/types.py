"""NotDiamond advisory adapter types.

The exception hierarchy is adapter-owned so callers can catch
``NotDiamondError`` and fall through to Antiek's normal dispatch routing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class NotDiamondError(Exception):
    """Base for every adapter-raised NotDiamond error."""


class NotDiamondNotInstalled(NotDiamondError):
    """The optional ``notdiamond`` SDK is not installed."""


class NotDiamondAuthError(NotDiamondError):
    """``NOTDIAMOND_API_KEY`` is missing or unusable."""


class NotDiamondTimeout(NotDiamondError):
    """The advisory NotDiamond decision exceeded its latency budget."""


class NotDiamondAPIError(NotDiamondError):
    """The SDK/service errored or returned an unparseable recommendation."""


@dataclass(frozen=True)
class Recommendation:
    """A parsed NotDiamond recommendation.

    ``raw`` is diagnostic-only. Dispatch decisions must use the parsed
    ``provider`` and ``model`` fields, and only as an advisory primary hint.
    """

    provider: str
    model: str
    session_id: str
    decision_latency_ms: int
    raw: dict[str, Any] = field(default_factory=dict)
