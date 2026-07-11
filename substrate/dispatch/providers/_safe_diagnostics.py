"""Safe projections of provider-controlled diagnostic metadata."""

from __future__ import annotations

import hashlib
import hmac
import os

_CORRELATION_KEY = os.urandom(32)
_CORRELATION_DOMAIN = b"antiek/provider-correlation/v1\0"


def correlation_digest(value: str | None) -> str | None:
    """Keep local correlation without retaining provider-controlled bytes."""
    if not value:
        return None
    encoded = value.encode("utf-8", errors="replace")
    digest = hmac.new(
        _CORRELATION_KEY,
        _CORRELATION_DOMAIN + encoded,
        hashlib.sha256,
    ).hexdigest()
    return f"hmac-sha256:{digest}"
