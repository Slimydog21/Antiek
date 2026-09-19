from __future__ import annotations

import hashlib
import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path

from runtime.db_lock import connect_write
from substrate.auth import mint_magic_link_token
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight_authorized
from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority
from substrate.multi_user.auth import account_user_id
from substrate.research_artifact.authority import ArtifactAuthority


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), _NoRedirect()
    )


def _request(
    opener: urllib.request.OpenerDirector,
    base: str,
    path: str,
    *,
    method: str = "GET",
    body: dict[str, object] | None = None,
) -> tuple[int, bytes]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(
        base + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"} if data is not None else {},
    )
    try:
        with opener.open(request, timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


@contextmanager
def _server(repo: Path, env: dict[str, str]):
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "interfaces.research.api.app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=repo,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise AssertionError(f"uvicorn exited early\n{stdout}\n{stderr}")
            try:
                urllib.request.urlopen(base + "/health", timeout=1).read()
                break
            # fmt: off -- project supports Python 3.11+.
            except (OSError, urllib.error.URLError):
                # fmt: on
                time.sleep(0.05)
        else:
            raise AssertionError("uvicorn did not become ready")
        yield base
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def _login(opener: urllib.request.OpenerDirector, base: str, email: str) -> None:
    status, _ = _request(
        opener,
        base,
        f"/auth/callback?token={mint_magic_link_token(email)}",
    )
    assert status == 302


def _tree_fingerprint(root: Path) -> list[tuple[str, str]]:
    if not root.exists():
        return []
    return [
        (str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest())
        for path in sorted(root.rglob("*"))
        if path.is_file()
    ]


def test_real_http_restart_restore_and_denial_canary(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    live = tmp_path / "live"
    live.mkdir()
    database = live / "graph.duckdb"
    events = live / "events"
    artifacts = live / "artifacts"
    secret = "w6-real-server-canary-" + "x" * 48
    emails = {
        "alice": "alice@example.test",
        "bob": "bob@example.test",
        "mallory": "mallory@example.test",
    }
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", secret)
    monkeypatch.setenv("ANTIEK_COOKIE_INSECURE", "1")
    monkeypatch.setenv("ANTIEK_OPERATOR_EMAIL", ",".join(emails.values()))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(database))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(str(database))
    authorities: dict[str, InvestigationAuthority] = {}
    for name in ("alice", "bob"):
        authority = InvestigationAuthority(account_user_id(emails[name]), "shared", root=events)
        authorities[name] = authority
        initialize_composite_stream(authority)
        promote_insight_authorized(authority, text=f"{name} restart-private insight")
    with connect_write(str(database), purpose="test-w6-real-server-shadow") as con:
        transition_graph_tenancy_state(
            con, expected=GraphTenancyState.UNSCOPED, desired=GraphTenancyState.COPYING
        )
        transition_graph_tenancy_state(
            con, expected=GraphTenancyState.COPYING, desired=GraphTenancyState.SHADOW
        )

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    clients = {name: _opener() for name in emails}
    with _server(repo, env) as base:
        for name, email in emails.items():
            _login(clients[name], base, email)
        for name in ("alice", "bob"):
            status, _ = _request(
                clients[name], base, "/research/shared/artifact/export", method="POST"
            )
            assert status == 200
            status, _ = _request(
                clients[name],
                base,
                "/research/shared/artifact/append-note",
                method="POST",
                body={"note": f"{name} restart-private note"},
            )
            assert status == 200

    # A fresh process with the same durable roots and existing cookies must agree.
    with _server(repo, env) as restarted_base:
        for name, peer in (("alice", "bob"), ("bob", "alice")):
            status, html = _request(clients[name], restarted_base, "/research/shared/artifact/view")
            assert status == 200
            text = html.decode()
            assert f"{name} restart-private insight" in text
            assert f"{name} restart-private note" in text
            assert f"{peer} restart-private insight" not in text
            assert f"{peer} restart-private note" not in text

        before_denial = _tree_fingerprint(live)
        foreign = _request(
            clients["mallory"],
            restarted_base,
            "/research/shared/artifact/import-notes",
            method="POST",
            body={},
        )
        missing = _request(
            clients["mallory"],
            restarted_base,
            "/research/absent/artifact/import-notes",
            method="POST",
            body={},
        )
        assert foreign == missing
        assert foreign[0] == 404
        assert _tree_fingerprint(live) == before_denial

    restored = tmp_path / "restored"
    shutil.copytree(live, restored, copy_function=shutil.copy2)
    restore_env = env | {
        "ANTIEK_DUCKDB_PATH": str(restored / "graph.duckdb"),
        "ANTIEK_RESEARCH_EVENTS_DIR": str(restored / "events"),
        "ANTIEK_RESEARCH_ARTIFACTS_DIR": str(restored / "artifacts"),
    }
    with _server(repo, restore_env) as restored_base:
        for name, peer in (("alice", "bob"), ("bob", "alice")):
            status, html = _request(clients[name], restored_base, "/research/shared/artifact/view")
            assert status == 200
            text = html.decode()
            assert f"{name} restart-private note" in text
            assert f"{peer} restart-private note" not in text

    for name in ("alice", "bob"):
        artifact = ArtifactAuthority(account_user_id(emails[name]), "shared")
        assert artifact.artifact_path(restored / "artifacts").exists()
