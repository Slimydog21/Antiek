"""Runtime SSL certificate bootstrap.

The python.org macOS Python can run with an empty default CA store until the
operator runs its certificate installer. Acquisition paths should not discover
that two frames into an HTTPS request. This helper pins SSL_CERT_FILE /
SSL_CERT_DIR to certifi when the operator has not already configured them.
"""

from __future__ import annotations

import importlib
import os
from collections.abc import MutableMapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SslBootstrapResult:
    configured: bool
    source: str
    cert_file: str | None
    cert_dir: str | None
    reason: str | None = None


def ensure_ssl_cert_env(
    env: MutableMapping[str, str] | None = None,
) -> SslBootstrapResult:
    """Ensure certificate env vars are present for HTTPS clients.

    Existing operator-provided values win. When SSL_CERT_FILE is absent, import
    certifi and set SSL_CERT_FILE to its bundle and SSL_CERT_DIR to the bundle's
    directory if SSL_CERT_DIR is also absent. If certifi is unavailable, return a
    loud, inspectable result but do not raise at import time.
    """
    target = env if env is not None else os.environ
    existing_file = target.get("SSL_CERT_FILE")
    existing_dir = target.get("SSL_CERT_DIR")
    if existing_file:
        return SslBootstrapResult(
            configured=True,
            source="env",
            cert_file=existing_file,
            cert_dir=existing_dir,
        )

    try:
        certifi = importlib.import_module("certifi")
        cert_file = str(certifi.where())
    except Exception as exc:
        return SslBootstrapResult(
            configured=False,
            source="missing",
            cert_file=None,
            cert_dir=existing_dir,
            reason=f"certifi unavailable: {exc}",
        )

    target.setdefault("SSL_CERT_FILE", cert_file)
    target.setdefault("SSL_CERT_DIR", str(Path(cert_file).parent))
    return SslBootstrapResult(
        configured=True,
        source="certifi",
        cert_file=target.get("SSL_CERT_FILE"),
        cert_dir=target.get("SSL_CERT_DIR"),
    )
