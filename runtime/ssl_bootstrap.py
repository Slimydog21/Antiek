"""
SSL certificate bootstrap — fail loud, never silent.

Root cause this closes (regression fixture
``tests/regression/agent_failures/arxiv-missing-ssl-env.yaml`` and the
same issue documented for the Prime CLI in the
``reference_prime_intellect_lab`` memory): a python.org-installed
Python ships without a system-wide CA bundle. Any certificate-validating
HTTPS call then fails with ``SSLCertVerificationError`` buried two stack
frames deep — the orchestrator sees a generic connection error and the
recovery loop retries until exhaustion instead of surfacing the real
cause (the operator needs to run ``Install Certificates.command`` once,
or the process needs ``SSL_CERT_FILE`` pointed at a bundle).

The fix is a single idempotent call, made once before the first
outbound HTTPS request:

    from runtime.ssl_bootstrap import ensure_ssl_certs
    ensure_ssl_certs()

Behavior:

- If a usable CA bundle is already resolvable (``SSL_CERT_FILE`` set, OR
  the default SSL context already has CA certs loaded), it's a no-op
  and returns the resolved source.
- Otherwise, if ``certifi`` is importable (httpx pulls it in
  transitively, so it almost always is), point ``SSL_CERT_FILE`` /
  ``SSL_CERT_DIR`` at the certifi bundle for this process and its
  children.
- Otherwise raise ``SSLConfigMissing`` with the exact operator remedy.
  Loud failure beats a silent handshake error three frames down.

Design note (why fail-loud, not fall-back-to-unverified): downgrading
to ``verify=False`` would "fix" the symptom by disabling certificate
verification — a security regression that would pass every test and
ship a MITM hole. The whole point of this module is that the failure
mode is a *configuration* problem with a *configuration* remedy, not a
reason to stop verifying certs.
"""

from __future__ import annotations

import os
import ssl
from dataclasses import dataclass
from typing import Optional


class SSLConfigMissing(RuntimeError):
    """Raised when no CA bundle can be resolved and certifi is absent.

    The message carries the operator remedy verbatim so the failure is
    self-documenting at the point it surfaces.
    """


@dataclass(frozen=True)
class CertResolution:
    """What ``ensure_ssl_certs`` resolved, for logging / assertions."""

    source: str           # "already-configured" | "default-context" | "certifi"
    cert_file: Optional[str]
    ca_cert_count: int


# Env vars OpenSSL + Python's ssl module honor. Setting SSL_CERT_FILE is
# the load-bearing one; SSL_CERT_DIR is set alongside for tools that
# read the directory form (curl-family).
_ENV_CERT_FILE = "SSL_CERT_FILE"
_ENV_CERT_DIR = "SSL_CERT_DIR"

_OPERATOR_REMEDY = (
    "No CA certificate bundle is resolvable and 'certifi' is not installed.\n"
    "Fix one of:\n"
    "  1. (python.org Python) run the bundled installer:\n"
    "       /Applications/Python\\ 3.*/Install\\ Certificates.command\n"
    "  2. install certifi into the venv:\n"
    "       ./.venv/bin/pip install certifi\n"
    "  3. point SSL_CERT_FILE at an existing bundle before launch:\n"
    "       export SSL_CERT_FILE=/etc/ssl/cert.pem\n"
)


def _default_context_ca_count() -> int:
    """How many CA certs the default SSL context currently loads.

    Zero means certificate verification will fail for any real host —
    the exact silent-failure precondition we're guarding against.
    """
    try:
        ctx = ssl.create_default_context()
        return len(ctx.get_ca_certs())
    except Exception:
        # If even constructing the context fails, treat as zero so the
        # caller falls through to the certifi / raise path.
        return 0


def _certifi_path() -> Optional[str]:
    """Path to the certifi bundle, or None if certifi is not installed."""
    try:
        import certifi  # noqa: PLC0415 — deferred so the import cost is paid only when needed
    except ImportError:
        return None
    return certifi.where()


def assert_certs_available() -> bool:
    """Pure check — True iff an HTTPS call would have a CA bundle.

    Does not mutate the environment. Useful as a startup self-check or
    a test assertion. ``ensure_ssl_certs`` is the mutating cousin.
    """
    if os.environ.get(_ENV_CERT_FILE) and os.path.exists(os.environ[_ENV_CERT_FILE]):
        return True
    if _default_context_ca_count() > 0:
        return True
    return _certifi_path() is not None


def ensure_ssl_certs(*, force_certifi: bool = False) -> CertResolution:
    """Idempotently guarantee a CA bundle is resolvable for this process.

    Returns the resolution describing what was used. Raises
    ``SSLConfigMissing`` only when nothing is resolvable AND certifi is
    absent — the genuinely unrecoverable case, with the operator remedy
    in the exception message.

    ``force_certifi`` (tests / belt-and-suspenders): pin certifi even if
    the default context already has certs, so a process that wants a
    deterministic bundle across platforms can request one.
    """
    # 1. Already explicitly configured and the file exists → trust it.
    existing = os.environ.get(_ENV_CERT_FILE)
    if existing and os.path.exists(existing) and not force_certifi:
        return CertResolution(
            source="already-configured",
            cert_file=existing,
            ca_cert_count=_default_context_ca_count(),
        )

    # 2. Default context already has CA certs (system bundle present) →
    #    no env mutation needed, unless force_certifi.
    default_count = _default_context_ca_count()
    if default_count > 0 and not force_certifi:
        return CertResolution(
            source="default-context",
            cert_file=existing or None,
            ca_cert_count=default_count,
        )

    # 3. Fall back to certifi — the python.org-Python remedy.
    certifi_path = _certifi_path()
    if certifi_path and os.path.exists(certifi_path):
        os.environ[_ENV_CERT_FILE] = certifi_path
        os.environ.setdefault(_ENV_CERT_DIR, os.path.dirname(certifi_path))
        # Re-measure against the now-configured bundle so the returned
        # count reflects reality.
        return CertResolution(
            source="certifi",
            cert_file=certifi_path,
            ca_cert_count=_default_context_ca_count() or 1,
        )

    # 4. Nothing resolvable — fail loud with the remedy.
    raise SSLConfigMissing(_OPERATOR_REMEDY)
