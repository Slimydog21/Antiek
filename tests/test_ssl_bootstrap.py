"""SPR-05 task 3 — the certifi bootstrap is ONE implementation, reaching FIVE entrypoints.

This file is the executable form of the task's done-bar, with four repairs. The
spec's shell done-bar was:

    for m in <five modules>; do env -u SSL_CERT_FILE -u SSL_CERT_DIR python -c \\
      "import importlib,os,ssl;importlib.import_module('$m');
       print('$m', bool(os.environ.get('SSL_CERT_FILE')),
             len(ssl.create_default_context().get_ca_certs()))"; done

plus a no-op probe. That bar does fail against an unmodified tree — four of the
five lines print ``False`` — so it grips on the wiring. It is blind to four
things this file asserts instead:

1. **Duplication.** Five copy-pasted ``certifi.where()`` blocks satisfy the shell
   bar perfectly, and the task's central instruction is "one implementation,
   imported". ``test_the_bootstrap_is_not_duplicated_in_any_caller`` is the only
   check that can tell the two apart.
2. **A vacuous cert count.** ``ssl.create_default_context().get_ca_certs()``
   returns 128 on this repo's interpreter with *no* ``SSL_CERT_FILE`` set at all,
   so "a cert count well above zero" is satisfied before any fix is written and
   measures nothing. This file loads the bundle the bootstrap actually named and
   counts THAT, which is zero-or-error if the bootstrap installs a bad path.
3. **``SSL_CERT_DIR`` on the no-op path.** The spec's no-op probe only reads back
   ``SSL_CERT_FILE``. A bootstrap that honours a preset ``SSL_CERT_FILE`` while
   overwriting ``SSL_CERT_DIR`` with certifi's directory passes it, and leaves
   the two variables naming different trust stores.
4. **The systemd template.** The task requires ``SSL_CERT_FILE`` in the unit's
   ``Environment=`` block; nothing in the shell bar looks at it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

from runtime import ssl_bootstrap

_REPO = Path(__file__).resolve().parents[1]

# The five arXiv-reaching entrypoints. ``run_corpus_ingest`` is included even
# though it carried its own copy before SPR-05 task 3: the refactor that removed
# that copy could regress it, and a done-bar that stops checking the one
# entrypoint that already worked would not notice.
ENTRYPOINTS = (
    "tools.arxiv_oai_sync",
    "tools.ingest_arxiv",
    "tools.arxiv_verify",
    "tools.arxiv_census",
    "tools.run_corpus_ingest",
)

ENTRYPOINT_FILES = tuple(f"tools/{m.split('.')[1]}.py" for m in ENTRYPOINTS)

# Real certifi usage, not the word "certifi" in a comment: an ``import certifi``
# statement, or a ``certifi.where(`` call.
_CERTIFI_USE = re.compile(
    r"(?m)^\s*(?:from\s+certifi\b|import\s+certifi\b)|certifi\s*\.\s*where\s*\("
)


# ── unit: the bootstrap's own contract ───────────────────────────────────────


def test_bootstrap_installs_certifi_when_cert_file_is_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    certifi = pytest.importorskip("certifi")
    monkeypatch.delenv(ssl_bootstrap.CERT_FILE_VAR, raising=False)
    monkeypatch.delenv(ssl_bootstrap.CERT_DIR_VAR, raising=False)

    ssl_bootstrap.bootstrap()

    assert os.environ[ssl_bootstrap.CERT_FILE_VAR] == certifi.where()
    assert os.environ[ssl_bootstrap.CERT_DIR_VAR] == os.path.dirname(certifi.where())
    assert os.path.isfile(os.environ[ssl_bootstrap.CERT_FILE_VAR])


def test_bootstrap_is_a_no_op_when_cert_file_is_preset(monkeypatch: pytest.MonkeyPatch) -> None:
    """REPAIR 3. An operator / systemd / distro value wins — for BOTH variables.

    The spec's probe reads back only ``SSL_CERT_FILE``. Asserting ``SSL_CERT_DIR``
    is untouched is what stops a bootstrap from pairing a preset bundle with
    certifi's directory, which is a trust store nobody configured.
    """
    monkeypatch.setenv(ssl_bootstrap.CERT_FILE_VAR, "/tmp/sentinel.pem")
    monkeypatch.delenv(ssl_bootstrap.CERT_DIR_VAR, raising=False)

    ssl_bootstrap.bootstrap()

    assert os.environ[ssl_bootstrap.CERT_FILE_VAR] == "/tmp/sentinel.pem"
    assert ssl_bootstrap.CERT_DIR_VAR not in os.environ


def test_bootstrap_replaces_an_empty_cert_file(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty value is unset, not "already configured".

    The superseded ``run_corpus_ingest.py`` copy used ``os.environ.setdefault``,
    which leaves an empty string in place because the KEY exists. OpenSSL then
    loads no certificates at all — the very failure the bootstrap exists to
    prevent, reached through the code meant to prevent it.
    """
    pytest.importorskip("certifi")
    monkeypatch.setenv(ssl_bootstrap.CERT_FILE_VAR, "")
    monkeypatch.delenv(ssl_bootstrap.CERT_DIR_VAR, raising=False)

    ssl_bootstrap.bootstrap()

    assert os.environ[ssl_bootstrap.CERT_FILE_VAR]
    assert os.path.isfile(os.environ[ssl_bootstrap.CERT_FILE_VAR])


def test_bootstrap_leaves_env_alone_when_certifi_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """certifi absent must fall through to the system trust store, never raise.

    Every entrypoint calls this at import; an exception here is an import-time
    crash of the whole CLI over a soft dependency.
    """
    monkeypatch.delenv(ssl_bootstrap.CERT_FILE_VAR, raising=False)
    monkeypatch.delenv(ssl_bootstrap.CERT_DIR_VAR, raising=False)
    monkeypatch.setitem(sys.modules, "certifi", None)  # import certifi -> ImportError

    ssl_bootstrap.bootstrap()

    assert ssl_bootstrap.CERT_FILE_VAR not in os.environ
    assert ssl_bootstrap.CERT_DIR_VAR not in os.environ


# ── wiring: every entrypoint, in its own interpreter ─────────────────────────


class _Probe(NamedTuple):
    """What one entrypoint left in the environment after importing."""

    cert_file: str
    ca_count: int
    cert_dir: str


def _import_probe(module: str) -> _Probe:
    """Import ``module`` in a clean subprocess with the CA env scrubbed.

    One subprocess per module, exactly as the spec demands, so one entrypoint's
    import side effects cannot make another look wired when it is not.
    """
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
    raw = json.loads(proc.stdout.strip().splitlines()[-1])
    return _Probe(str(raw["cert_file"]), int(raw["ca_count"]), str(raw["cert_dir"]))


@pytest.mark.parametrize("module", ENTRYPOINTS)
def test_every_arxiv_entrypoint_bootstraps_ssl_at_import(module: str) -> None:
    """REPAIR 2. Importing the module must leave a LOADABLE bundle in the env.

    ``bool(os.environ.get("SSL_CERT_FILE"))`` alone would accept
    ``SSL_CERT_FILE=/does/not/exist``. Counting the certs OpenSSL actually reads
    out of the named file is what makes the assertion about trust rather than
    about a string being non-empty — and unlike the spec's
    ``create_default_context()`` count, it is zero when the bootstrap is absent
    or wrong instead of 128 from the interpreter's own fallback.
    """
    got = _import_probe(module)

    assert got.cert_file, f"{module} left SSL_CERT_FILE unset at import"
    assert os.path.isfile(got.cert_file), f"{module} named a nonexistent bundle: {got}"
    assert got.ca_count > 0, f"{module} named a bundle with no CAs: {got}"
    assert got.cert_dir, f"{module} left SSL_CERT_DIR unset at import"


def test_the_bootstrap_is_not_duplicated_in_any_caller() -> None:
    """REPAIR 1. Five copy-pasted blocks satisfy the spec's shell bar exactly.

    The task's instruction — "Do not duplicate the bootstrap — one
    implementation, imported" — has no representation in that bar at all. This
    is the check that has it: ``runtime/ssl_bootstrap.py`` is the only tracked
    Python file allowed to reach for certifi, and every entrypoint must import
    it rather than inline it.
    """
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
        f"{offenders}. SPR-05 task 3 exists because the bootstrap was copied "
        "into one entrypoint and never reached the other four. Import "
        "runtime.ssl_bootstrap.bootstrap instead of inlining it."
    )

    missing = [
        rel
        for rel in ENTRYPOINT_FILES
        if "runtime.ssl_bootstrap" not in (_REPO / rel).read_text(encoding="utf-8")
    ]
    assert missing == [], f"entrypoints that never import the shared bootstrap: {missing}"


def test_the_systemd_unit_pins_ssl_cert_file() -> None:
    """REPAIR 4. The task requires the template edit; the shell bar never looks.

    Production does not depend on this — ``ca-certificates`` on the Hetzner box
    already covers the handshake — but pinning it is what keeps the unit's value
    ahead of the certifi fallback, and an unpinned unit is a silent regression
    of that precedence.
    """
    unit = (_REPO / "infrastructure/ansible/templates/antiek-arxiv-oai-sync.service.j2").read_text(
        encoding="utf-8"
    )
    env_lines = [ln for ln in unit.splitlines() if ln.startswith("Environment=")]
    assert any("SSL_CERT_FILE=" in ln for ln in env_lines), (
        f"the arxiv-oai-sync unit's Environment= block does not pin SSL_CERT_FILE; got {env_lines}"
    )
