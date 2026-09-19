"""Approved worker identity for the Daytona protocol snapshot.

This remains fail-closed until the cascade supplies a reviewed browse worker.
Binding a different callable through environment or input is intentionally
unsupported.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any


async def run(
    plan: dict[str, Any], controls: Any
) -> AsyncIterator[dict[str, Any]]:
    del plan, controls
    if False:  # pragma: no cover - preserve async-generator protocol
        yield {}
    raise RuntimeError("approved Daytona research worker is not wired")
