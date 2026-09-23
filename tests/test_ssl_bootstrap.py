"""SPR-05 arXiv task 3 — the shared certifi bootstrap and its priority contract.

Hermetic: every test scopes the SSL env vars with ``monkeypatch`` and never
opens a socket. The contract worth pinning is the NO-OP half — the systemd
unit exports ``SSL_CERT_FILE`` from the box's ``ca-certificates`` bundle, and
the helper must never override that with the venv's certifi copy.
"""

from __future__ import annotations

import importlib
import os
import ssl

import pytest

from runtime import ssl_bootstrap

_ARXIV_ENTRYPOINTS = (
    "tools.arxiv_oai_sync",
    "tools.ingest_arxiv",
    "tools.arxiv_verify",
    "tools.arxiv_census",
    "tools.run_corpus_ingest",
)


def test_bootstrap_is_a_noop_when_ssl_cert_file_is_already_set(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/sentinel.pem")
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    assert ssl_bootstrap.bootstrap() is False
    assert os.environ["SSL_CERT_FILE"] == "/tmp/sentinel.pem"
    assert "SSL_CERT_DIR" not in os.environ


@pytest.mark.parametrize("initial", [None, ""], ids=["unset", "empty"])
def test_bootstrap_exports_certifi_when_ssl_cert_file_is_unset_or_empty(
    monkeypatch, initial
):
    """The regression fixture's input env is literally ``SSL_CERT_FILE: ""`` —
    an empty string must count as unset, which a ``setdefault`` got wrong."""
    certifi = pytest.importorskip("certifi")
    if initial is None:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    else:
        monkeypatch.setenv("SSL_CERT_FILE", initial)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    assert ssl_bootstrap.bootstrap() is True
    assert os.environ["SSL_CERT_FILE"] == certifi.where()
    assert os.environ["SSL_CERT_DIR"] == os.path.dirname(certifi.where())
    assert os.path.isfile(os.environ["SSL_CERT_FILE"])
    # And the bundle it points at actually loads.
    ctx = ssl.create_default_context(cafile=os.environ["SSL_CERT_FILE"])
    assert len(ctx.get_ca_certs()) > 0
    # Idempotent: the second call sees the value it set and stands down.
    assert ssl_bootstrap.bootstrap() is False


@pytest.mark.parametrize("module", _ARXIV_ENTRYPOINTS)
def test_every_arxiv_entrypoint_calls_the_shared_bootstrap_at_import(
    monkeypatch, module
):
    """Each of the five arXiv entrypoints runs ``bootstrap()`` at import — the
    same seam the done-bar's five subprocesses probe, here as one in-process
    proof per module so a sixth entrypoint that forgets it is caught by name.
    The module is re-executed under a spy so an earlier import in the same
    pytest process cannot mask a missing call."""
    calls: list[str] = []
    real = ssl_bootstrap.bootstrap

    def _spy() -> bool:
        calls.append(module)
        return real()

    monkeypatch.setattr(ssl_bootstrap, "bootstrap", _spy)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    mod = importlib.import_module(module)
    importlib.reload(mod)

    assert calls == [module], calls
    assert os.environ.get("SSL_CERT_FILE"), "the entrypoint imported without exporting a bundle"
