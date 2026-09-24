"""The one certifi-backed SSL bootstrap, shared by every Antiek entrypoint.

A python.org / framework CPython on macOS ships without a system CA bundle, so
``ssl.create_default_context()`` verifies against an empty trust store and every
HTTPS handshake to ``export.arxiv.org`` or an open-access host dies two frames
deep with ``SSLCertVerificationError`` — the 2026-05-17 ``arxiv-missing-ssl-env``
failure. ``tools/run_corpus_ingest.py`` carried a private copy of the fix from
then until SPR-05 task 3; the other four arXiv entrypoints, including
``tools/arxiv_oai_sync.py`` (the systemd-scheduled, busiest, most ban-prone
channel), had none. The fix reached one entrypoint out of five.

This module is the single implementation. Callers import it and call
``bootstrap()`` once at import, before anything opens a socket. Copying the body
back into a caller silently re-opens the gap this closed, which is why
``tests/test_ssl_bootstrap.py::test_the_bootstrap_is_not_duplicated_in_any_caller``
fails if any file outside this one resolves ``certifi.where()``.

Precedence is deliberate: an operator-supplied ``SSL_CERT_FILE`` always wins, so
the systemd unit's ``Environment=`` line and the Hetzner box's ``ca-certificates``
package keep priority. The change is belt-and-braces for production and a real
fix for a developer Mac.

Scope: reads ``os.environ`` and writes at most two keys in the current process.
It touches no DuckDB path and takes no lock — ``runtime/db_lock.py`` and the
serialized single-writer funnel remain the sole graph writer.
"""

from __future__ import annotations

import os

__all__ = ["CERT_DIR_VAR", "CERT_FILE_VAR", "bootstrap"]

CERT_FILE_VAR = "SSL_CERT_FILE"
CERT_DIR_VAR = "SSL_CERT_DIR"


def bootstrap() -> None:
    """Point ``SSL_CERT_FILE`` / ``SSL_CERT_DIR`` at certifi's bundle when unset.

    A no-op when ``SSL_CERT_FILE`` already names something, so an operator, a
    systemd ``Environment=`` line or a distro CA package keeps priority — and a
    no-op when certifi is absent or its bundle is missing, so a caller falls
    through to whatever trust store the interpreter already has rather than
    failing at import. ``SSL_CERT_DIR`` is likewise left alone if already set,
    so the two never end up naming different bundles. Idempotent: calling it
    twice changes nothing.

    An empty ``SSL_CERT_FILE`` counts as unset and IS replaced. The superseded
    ``run_corpus_ingest.py`` copy used ``os.environ.setdefault``, which left an
    empty value in place because the key existed — an empty value makes OpenSSL
    load no certificates at all, which is the failure this exists to prevent.
    """
    if os.environ.get(CERT_FILE_VAR):
        return
    try:
        import certifi

        bundle = certifi.where()
    except Exception:
        return  # certifi absent or unusable -> leave env as-is, system default
    if not bundle or not os.path.isfile(bundle):
        return
    os.environ[CERT_FILE_VAR] = bundle
    if not os.environ.get(CERT_DIR_VAR):
        os.environ[CERT_DIR_VAR] = os.path.dirname(bundle)
