"""Production composition for the marketplace host store.

The application factory remains explicit and testable. Only the module-level
uvicorn entry point consults this environment contract.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path

from substrate.marketplace_host import SQLiteHostStore
from substrate.marketplace_host.library import HostStore

MARKETPLACE_HOST_DB_PATH_ENV = "ANTIEK_MARKETPLACE_HOST_DB_PATH"


def marketplace_host_store_from_env(
    environ: Mapping[str, str] | None = None,
) -> HostStore | None:
    """Build the durable host store when production explicitly configures it.

    An absent or empty value preserves the offline in-memory development
    default. Any non-empty value is an explicit durability claim, so malformed
    paths and database failures abort startup instead of silently losing data.
    """

    source = os.environ if environ is None else environ
    raw = source.get(MARKETPLACE_HOST_DB_PATH_ENV)
    if raw is None or raw == "":
        return None
    if raw != raw.strip():
        raise RuntimeError(
            f"{MARKETPLACE_HOST_DB_PATH_ENV} must not contain surrounding whitespace"
        )
    path = Path(raw)
    if not path.is_absolute():
        raise RuntimeError(f"{MARKETPLACE_HOST_DB_PATH_ENV} must be an absolute path")
    try:
        return SQLiteHostStore(path)
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(
            f"failed to initialize {MARKETPLACE_HOST_DB_PATH_ENV}: {exc}"
        ) from exc
