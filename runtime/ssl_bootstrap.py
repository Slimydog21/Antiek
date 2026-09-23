"""Point the process at a usable CA bundle when the interpreter ships none.

The 2026-05-17 arXiv failure (``tests/regression/agent_failures/
arxiv-missing-ssl-env.yaml``): a python.org-installed interpreter has no
system-wide certificate bundle, so every HTTPS handshake — arxiv.org, the OA
aggregators, Semantic Scholar — failed with an ``SSLCertVerificationError``
buried two stack frames deep, and the recovery loop retried to exhaustion.
``tools/run_corpus_ingest.py`` closed its own path by exporting
``SSL_CERT_FILE`` from certifi at import; the other four arXiv entrypoints
(``arxiv_oai_sync``, ``ingest_arxiv``, ``arxiv_verify``, ``arxiv_census``)
did not, and the systemd-scheduled sync was the busiest of them. This is the
one shared copy every entrypoint calls.

Priority order is the whole contract. When ``SSL_CERT_FILE`` is already set —
by the systemd unit's ``Environment=`` block, or by an operator pointing at the
Hetzner box's ``ca-certificates`` bundle — ``bootstrap()`` changes nothing, so
the system bundle keeps priority and this module is belt-and-braces there. It
acts only when the variable is unset or empty (the regression fixture's input
env is literally ``SSL_CERT_FILE: ""``, which a ``setdefault`` would have left
in place). It never touches the network or the DB.
"""

from __future__ import annotations

import os


def bootstrap() -> bool:
    """Export ``SSL_CERT_FILE`` (and ``SSL_CERT_DIR``) from certifi when unset.

    Returns ``True`` iff it set ``SSL_CERT_FILE``. A no-op — returning ``False``
    and leaving the environment untouched — when ``SSL_CERT_FILE`` already has a
    value, or when certifi is not importable (leave the interpreter default
    alone rather than point at nothing). Idempotent: a second call is a no-op
    because the first set the variable.
    """
    if os.environ.get("SSL_CERT_FILE"):
        return False
    try:
        import certifi
    except ImportError:
        return False
    bundle = certifi.where()
    os.environ["SSL_CERT_FILE"] = bundle
    if not os.environ.get("SSL_CERT_DIR"):
        os.environ["SSL_CERT_DIR"] = os.path.dirname(bundle)
    return True
