"""SPR-05 task 3 — one certifi bootstrap, five arXiv entrypoints, no copies.

Pins the priority contract (preset ``SSL_CERT_FILE`` wins; empty counts as
unset; certifi missing/broken is a quiet no-op), the wiring of all five
entrypoints, and the ban on inlined ``certifi.where()`` outside the shared
module. The shell done-bar's cert count is vacuous: ``ssl.create_default_context()``
loads ~128 system CAs with the env unset, so "a cert count well above zero"
passes before any fix. Count the CAs in the file the bootstrap actually named.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from typing import NamedTuple, cast

import pytest

from runtime import ssl_bootstrap

_REPO = Path(__file__).resolve().parents[1]

ENTRYPOINTS = (
    "tools.arxiv_oai_sync",
    "tools.ingest_arxiv",
    "tools.arxiv_verify",
    "tools.arxiv_census",
    "tools.run_corpus_ingest",
)

ENTRYPOINT_FILES = tuple(f"tools/{m.split('.')[1]}.py" for m in ENTRYPOINTS)

_CERTIFI_USE = re.compile(
    r"(?m)^\s*(?:from\s+certifi\b|import\s+certifi\b)|certifi\s*\.\s*where\s*\("
)


def _certifi_bundle() -> str:
    pytest.importorskip("certifi")
    import certifi

    return certifi.where()


def test_bootstrap_is_a_noop_when_ssl_cert_file_is_already_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SSL_CERT_FILE", "/tmp/sentinel.pem")
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    assert ssl_bootstrap.bootstrap() is False
    assert os.environ["SSL_CERT_FILE"] == "/tmp/sentinel.pem"
    assert "SSL_CERT_DIR" not in os.environ


@pytest.mark.parametrize("initial", [None, ""], ids=["unset", "empty"])
def test_bootstrap_exports_certifi_when_ssl_cert_file_is_unset_or_empty(
    monkeypatch: pytest.MonkeyPatch,
    initial: str | None,
) -> None:
    bundle = _certifi_bundle()
    if initial is None:
        monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    else:
        monkeypatch.setenv("SSL_CERT_FILE", initial)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)

    assert ssl_bootstrap.bootstrap() is True
    assert os.environ["SSL_CERT_FILE"] == bundle
    assert os.environ["SSL_CERT_DIR"] == os.path.dirname(bundle)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.load_verify_locations(cafile=bundle)
    assert len(ctx.get_ca_certs()) > 0
    assert ssl_bootstrap.bootstrap() is False


def test_bootstrap_leaves_env_alone_when_certifi_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    monkeypatch.setitem(sys.modules, "certifi", cast(ModuleType, None))

    assert ssl_bootstrap.bootstrap() is False
    assert "SSL_CERT_FILE" not in os.environ
    assert "SSL_CERT_DIR" not in os.environ


class _Probe(NamedTuple):
    cert_file: str
    ca_count: int
    cert_dir: str


def _import_probe(module: str) -> _Probe:
    env = {k: v for k, v in os.environ.items() if k not in ("SSL_CERT_FILE", "SSL_CERT_DIR")}
    env["PYTHONPATH"] = str(_REPO)
    code = (
        "import importlib, json, os, ssl\n"
        f"importlib.import_module({module!r})\n"
        'f = os.environ.get("SSL_CERT_FILE", "")\n'
        "n = 0\n"
        "if f and os.path.isfile(f):\n"
        "    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)\n"
        "    ctx.load_verify_locations(cafile=f)\n"
        "    n = len(ctx.get_ca_certs())\n"
        'print(json.dumps({"cert_file": f, "ca_count": n,\n'
        '                  "cert_dir": os.environ.get("SSL_CERT_DIR", "")}))\n'
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=_REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert proc.returncode == 0, f"importing {module} failed:\n{proc.stderr}"
    raw = json.loads((proc.stdout or "").strip().splitlines()[-1])
    return _Probe(str(raw["cert_file"]), int(raw["ca_count"]), str(raw["cert_dir"]))


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_every_arxiv_entrypoint_bootstraps_ssl_at_import(module: str) -> None:
    got = _import_probe(module)

    assert got.cert_file, f"{module} left SSL_CERT_FILE unset at import"
    assert os.path.isfile(got.cert_file), f"{module} named a nonexistent bundle: {got}"
    assert got.ca_count > 0, f"{module} named a bundle with no CAs: {got}"
    assert got.cert_dir, f"{module} left SSL_CERT_DIR unset at import"


def test_the_bootstrap_is_not_duplicated_in_any_caller() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "*.py"],
        cwd=_REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")

    allowed = {"runtime/ssl_bootstrap.py", "tests/test_ssl_bootstrap.py"}
    offenders = [
        rel
        for rel in tracked
        if rel
        and rel not in allowed
        and _CERTIFI_USE.search((_REPO / rel).read_text(encoding="utf-8", errors="replace"))
    ]
    assert offenders == [], (
        "certifi is resolved outside runtime/ssl_bootstrap.py: "
        f"{offenders}. Import runtime.ssl_bootstrap.bootstrap instead of inlining it."
    )

    missing = [
        rel
        for rel in ENTRYPOINT_FILES
        if "runtime.ssl_bootstrap" not in (_REPO / rel).read_text(encoding="utf-8")
    ]
    assert missing == [], f"entrypoints that never import the shared bootstrap: {missing}"


def test_the_systemd_unit_pins_ssl_cert_file() -> None:
    unit = (_REPO / "infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2").read_text(
        encoding="utf-8"
    )
    env_lines = [ln for ln in unit.splitlines() if ln.startswith("Environment=")]
    assert any("SSL_CERT_FILE=" in ln for ln in env_lines), (
        f"the arxiv-oai-sync unit's Environment= block does not pin SSL_CERT_FILE; got {env_lines}"
    )
