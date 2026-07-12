"""Shared operator email allowlist from ``ANTIEK_OPERATOR_EMAIL``.

Magic-link routes (``auth.py``) and the operator-auth middleware (``app.py``)
must parse comma-separated addresses identically. A single env string like
``alice@x.com,bob@y.com`` is a list of operators, not one malformed address.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

_DEFAULT_ENV = "ANTIEK_OPERATOR_EMAIL"


def operator_allowlist_from_env(
    env_key: str = _DEFAULT_ENV,
    *,
    environ: Mapping[str, str] | None = None,
) -> frozenset[str]:
    """Lowercased frozenset from a comma-separated env value.

    Empty or unset env → empty frozenset (deny magic-link sends; middleware
    treats email-based paths as disabled when combined with no token/ST id).
    """
    environment = os.environ if environ is None else environ
    raw = environment.get(env_key, "").strip()
    if not raw:
        return frozenset()
    return frozenset(
        part.strip().lower() for part in raw.split(",") if part.strip()
    )
