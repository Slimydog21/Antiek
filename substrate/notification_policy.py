"""Default-deny operator interruption chokepoint.

Production code must not call desktop notification APIs, open browser tabs, or
show modal dialogs directly. Route attempted interruptions through
``interrupt()`` so the policy decision is auditable and centrally testable.

The default policy is deliberately log-only: it records that attention was
requested, and it denies push delivery until a reviewed notifier adapter exists.
This module does not shell out, open browsers, or import desktop notification
packages.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

LOGGER = logging.getLogger(__name__)

InterruptionSeverity = Literal["info", "warning", "critical"]
InterruptionDecision = Literal["logged", "denied"]

_ALLOWED_SEVERITIES = frozenset({"info", "warning", "critical"})


@dataclass(frozen=True)
class InterruptionRequest:
    """A caller's request to push attention to the operator."""

    message: str
    title: str = "Antiek"
    severity: InterruptionSeverity = "info"
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        message = self.message.strip()
        title = self.title.strip()
        if not message:
            raise ValueError("message must not be empty")
        if not title:
            raise ValueError("title must not be empty")
        if self.severity not in _ALLOWED_SEVERITIES:
            allowed = ", ".join(sorted(_ALLOWED_SEVERITIES))
            raise ValueError(f"severity must be one of: {allowed}")
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class InterruptionResult:
    """The policy decision for a requested operator interruption."""

    request: InterruptionRequest
    decision: InterruptionDecision
    reason: str

    @property
    def allowed(self) -> bool:
        """Whether the request was accepted by the current log-only policy."""

        return self.decision == "logged"


def _log_for(severity: InterruptionSeverity) -> Callable[..., None]:
    return LOGGER.warning if severity in {"warning", "critical"} else LOGGER.info


def interrupt(
    message: str,
    *,
    title: str = "Antiek",
    severity: InterruptionSeverity = "info",
    metadata: Mapping[str, object] | None = None,
    allow_push: bool = False,
) -> InterruptionResult:
    """Evaluate an operator-interruption request.

    ``allow_push`` is intentionally a policy input, not an implementation path.
    Until a future sprint lands a reviewed notifier adapter, push requests are
    denied. Callers still get a truthful structured result instead of reaching
    around the policy.
    """

    request = InterruptionRequest(
        message=message,
        title=title,
        severity=severity,
        metadata=metadata or {},
    )
    if allow_push:
        _log_for(request.severity)(
            "operator interruption requested but no push adapter is installed: %s",
            request.message,
            extra={"antiek_notification_policy": dict(request.metadata)},
        )
        return InterruptionResult(
            request=request,
            decision="denied",
            reason="push_adapter_not_installed",
        )

    _log_for(request.severity)(
        "operator interruption logged: %s",
        request.message,
        extra={"antiek_notification_policy": dict(request.metadata)},
    )
    return InterruptionResult(
        request=request,
        decision="logged",
        reason="default_log_only_policy",
    )
