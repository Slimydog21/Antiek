from __future__ import annotations

import json
import socket
import sqlite3
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from acquisition.openalex_cache import OpenAlexSnapshotError, OpenAlexSnapshotStore
from tools.openalex_corpus import (
    EXIT_CACHE,
    EXIT_CONFIGURATION,
    EXIT_MISS,
    EXIT_OK,
    EXIT_PROVIDER,
    _http_get,
    main,
)

STAMP = 1_767_225_600.0


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    yield


class Response:
    status_code = 200

    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def json(self) -> dict[str, object]:
        return self.payload


def _raw(id: str = "https://openalex.org/W1", title: str = "Research graph") -> dict[str, object]:
    return {
        "id": id,
        "title": title,
        "abstract_inverted_index": {"knowledge": [0], "graph": [1]},
    }


def _persisted(
    id: str = "https://openalex.org/W1", title: str = "Research graph"
) -> dict[str, object]:
    return {**_raw(id, title), "fetched_at": STAMP}


def test_help_is_operator_usable() -> None:
    result = subprocess.run(
        [sys.executable, "tools/openalex_corpus.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert all(command in result.stdout for command in ("sync-search", "search", "fetch"))


def test_sync_requires_confirmation_and_mailto_before_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(url: str) -> Response:
        raise AssertionError(url)

    cache = tmp_path / "cache"
    base = ["--cache-dir", str(cache), "sync-search", "knowledge graph"]
    assert main(base, environ={}, get=forbidden) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "live_request_not_confirmed"
    assert main([*base, "--yes"], environ={}, get=forbidden) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "missing_or_invalid_openalex_mailto"


def test_sync_uses_real_cursor_client_and_persists_before_success(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("acquisition.openalex.client.time.time", lambda: STAMP)
    seen: list[str] = []

    def get(url: str) -> Response:
        seen.append(url)
        return Response({"results": [_raw()], "meta": {"next_cursor": None}})

    cache = tmp_path / "cache"
    assert (
        main(
            ["--cache-dir", str(cache), "sync-search", "knowledge graph", "--yes"],
            environ={"OPENALEX_MAILTO": "operator@example.com"},
            get=get,
        )
        == EXIT_OK
    )
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == "persisted" and output["work_ids"] == ["https://openalex.org/W1"]
    assert "api.openalex.org/works" in seen[0] and "mailto=operator%40example.com" in seen[0]
    assert OpenAlexSnapshotStore(cache).load()[0]["title"] == "Research graph"


def test_max_records_bounds_paged_results(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    calls = 0

    def get(url: str) -> Response:
        nonlocal calls
        calls += 1
        return Response(
            {
                "results": [_raw(f"https://openalex.org/W{calls}", f"Title {calls}")],
                "meta": {"next_cursor": "next"},
            }
        )

    assert (
        main(
            [
                "--cache-dir",
                str(tmp_path / "cache"),
                "sync-search",
                "query",
                "--max-records",
                "2",
                "--yes",
            ],
            environ={"OPENALEX_MAILTO": "operator@example.com"},
            get=get,
        )
        == EXIT_OK
    )
    assert json.loads(capsys.readouterr().out)["count"] == 2 and calls == 2


def test_search_fetch_offline_and_miss_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "cache"
    OpenAlexSnapshotStore(cache).publish((_persisted(),))
    assert main(["--cache-dir", str(cache), "search", "knowledge"], environ={}) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["hits"][0]["id"].endswith("W1")
    assert (
        main(["--cache-dir", str(cache), "fetch", "https://openalex.org/W1"], environ={}) == EXIT_OK
    )
    assert "knowledge graph" in json.loads(capsys.readouterr().out)["content"]
    assert main(["--cache-dir", str(cache), "fetch", "missing"], environ={}) == EXIT_MISS
    assert json.loads(capsys.readouterr().err) == {"error": "work_not_found", "work_id": "missing"}


def test_provider_error_redacts_mailto_and_attacker_body(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "private-mail@example.com"
    attacker = "reflected provider body"
    assert (
        main(
            ["--cache-dir", str(tmp_path / "cache"), "sync-search", "query", "--yes"],
            environ={"OPENALEX_MAILTO": secret},
            get=lambda url: (_ for _ in ()).throw(httpx.ReadError(attacker)),
        )
        == EXIT_PROVIDER
    )
    captured = capsys.readouterr()
    assert captured.err == '{"error":"provider_request_failed"}\n'
    assert secret not in captured.err + captured.out and attacker not in captured.err + captured.out


def test_store_rejects_tamper_symlink_and_duplicate(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    store = OpenAlexSnapshotStore(directory)
    with pytest.raises(OpenAlexSnapshotError, match="duplicate"):
        store.publish((_persisted(), _persisted()))
    store.publish((_persisted(),))
    connection = sqlite3.connect(directory / "works.sqlite3")
    connection.execute("UPDATE works SET payload = '{}' WHERE id = ?", ["https://openalex.org/W1"])
    connection.commit()
    connection.close()
    with pytest.raises(OpenAlexSnapshotError, match="digest"):
        store.load()
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(OpenAlexSnapshotError, match="real directory"):
        OpenAlexSnapshotStore(link)


def test_concurrent_distinct_publishes_keep_both_records(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    first, second = OpenAlexSnapshotStore(directory), OpenAlexSnapshotStore(directory)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def publish(store: OpenAlexSnapshotStore, record: dict[str, object]) -> None:
        try:
            barrier.wait()
            store.publish((record,))
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=publish, args=(first, _persisted("A", "Alpha"))),
        threading.Thread(target=publish, args=(second, _persisted("B", "Beta"))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert [item["id"] for item in OpenAlexSnapshotStore(directory).load()] == ["A", "B"]


@pytest.mark.parametrize("limit", ["0", "101"])
def test_invalid_limit_and_cache_return_stable_errors(
    limit: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert (
        main(
            [
                "--cache-dir",
                str(tmp_path / "cache"),
                "sync-search",
                "query",
                "--max-records",
                limit,
                "--yes",
            ],
            environ={"OPENALEX_MAILTO": "operator@example.com"},
            get=lambda url: Response({}),
        )
        == EXIT_CONFIGURATION
    )
    assert json.loads(capsys.readouterr().err) == {
        "allowed": "1..100",
        "error": "invalid_max_records",
    }
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert main(["--cache-dir", str(link), "search", "x"], environ={}) == EXIT_CACHE
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}


def test_default_http_transport_rejects_oversized_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class OversizedClient:
        def __init__(self, **kwargs: object) -> None:
            assert kwargs["follow_redirects"] is False

        def get(self, url: str) -> httpx.Response:
            return httpx.Response(200, content=b"x" * (10 * 1024 * 1024 + 1))

        def close(self) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", OversizedClient)
    client, get = _http_get()
    with pytest.raises(RuntimeError, match="exceeds local bound"):
        get("https://api.openalex.org/works")
    client.close()


def test_sync_snapshot_failure_is_cache_not_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_publish(
        self: OpenAlexSnapshotStore, records: object
    ) -> tuple[dict[str, object], ...]:
        raise OpenAlexSnapshotError("disk contract failed")

    monkeypatch.setattr(OpenAlexSnapshotStore, "publish", fail_publish)
    assert (
        main(
            ["--cache-dir", str(tmp_path / "cache"), "sync-search", "query", "--yes"],
            environ={"OPENALEX_MAILTO": "operator@example.com"},
            get=lambda url: Response({"results": [_raw()], "meta": {"next_cursor": None}}),
        )
        == EXIT_CACHE
    )
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}
