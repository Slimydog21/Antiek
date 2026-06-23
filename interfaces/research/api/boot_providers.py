"""Provider registration boot visibility (DRW honest failure)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def log_zero_providers_warning_if_needed(registered_providers: set[str]) -> None:
    """Loud-but-running boot posture when no dispatch providers registered."""
    if registered_providers:
        return
    # Nothing auto-loads .env — operator must `source .env` then restart.
    logger.warning(
        "0 providers registered — LLM features will fail; "
        "load keys with `source .env` then restart",
    )