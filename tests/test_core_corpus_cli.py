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

from acquisition.core_cache import CoreSnapshotError, CoreSnapshotStore
from acquisition.papers._pipeline import PaperRecord
from substrate.source_throttle import SourceThrottle
from tools.core_corpus import (
    EXIT_CACHE,
    EXIT_CONFIGURATION,
    EXIT_MISS,
    EXIT_OK,
    EXIT_PROVIDER,
    _live_search,
    main,
)

STAMP = 1_767_225_600.0
KEY = "operator-test-key"


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    yield


def _paper(id: str = "123", title: str = "Knowledge graph") -> PaperRecord:
    return PaperRecord(
        source="core",
        source_id=id,
        title=title,
        license="https://creativecommons.org/licenses/by/4.0/",
        doi="10.1/example",
        abstract="Research workstation evidence.",
        authors=("Ada",),
    )


def _record(id: str = "123", title: str = "Knowledge graph", at: float = STAMP) -> dict[str, object]:
    return {
        "id": id,
        "title": title,
        "abstract": "Research workstation evidence.",
        "doi": "10.1/example",
        "arxiv_id": None,
        "authors": ["Ada"],
        "declared_license": "https://creativecommons.org/licenses/by/4.0/",
        "fetched_at": at,
        "source": "core",
    }


def test_help_is_operator_usable() -> None:
    result = subprocess.run(
        [sys.executable, "tools/core_corpus.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert all(command in result.stdout for command in ("sync-search", "search", "fetch"))


def test_sync_requires_confirmation_and_key_before_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(query: str, limit: int) -> list[PaperRecord]:
        raise AssertionError((query, limit))

    base = ["--cache-dir", str(tmp_path / "cache"), "sync-search", "knowledge"]
    assert main(base, environ={}, search=forbidden) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "live_request_not_confirmed"
    assert main([*base, "--yes"], environ={}, search=forbidden) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "missing_or_invalid_core_api_key"


def test_sync_persists_before_success_and_preserves_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("acquisition.core_cache.client.time.time", lambda: STAMP)
    seen: list[tuple[str, int]] = []

    def search(query: str, limit: int) -> list[PaperRecord]:
        seen.append((query, limit))
        return [_paper()]

    cache = tmp_path / "cache"
    assert main(
        ["--cache-dir", str(cache), "sync-search", "knowledge", "--max-records", "1", "--yes"],
        environ={"ANTIEK_CORE_API_KEY": KEY},
        search=search,
    ) == EXIT_OK
    output = json.loads(capsys.readouterr().out)
    assert output == {"count": 1, "status": "persisted", "work_ids": ["123"]}
    assert seen == [("knowledge", 1)]
    stored = CoreSnapshotStore(cache).load()[0]
    assert stored["doi"] == "10.1/example" and stored["declared_license"]


def test_search_fetch_are_offline_and_rights_conservative(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "cache"
    CoreSnapshotStore(cache).publish((_record(),))
    assert main(["--cache-dir", str(cache), "search", "workstation"], environ={}) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["hits"][0]["id"] == "123"
    assert main(["--cache-dir", str(cache), "fetch", "123"], environ={}) == EXIT_OK
    fetched = json.loads(capsys.readouterr().out)
    assert fetched["license_class"] == "source_terms_governed_metadata"
    assert "Research workstation" in fetched["content"]
    assert main(["--cache-dir", str(cache), "fetch", "missing"], environ={}) == EXIT_MISS
    assert json.loads(capsys.readouterr().err)["error"] == "work_not_found"


@pytest.mark.parametrize("limit", ["0", "101"])
def test_limit_bounds_are_configuration_errors(
    limit: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(
        ["--cache-dir", str(tmp_path / "cache"), "sync-search", "q", "--max-records", limit, "--yes"],
        environ={"ANTIEK_CORE_API_KEY": KEY},
        search=lambda query, count: [_paper()],
    ) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err) == {"allowed": "1..100", "error": "invalid_max_records"}


def test_provider_error_redacts_key_and_body(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    attacker = "reflected provider body"
    assert main(
        ["--cache-dir", str(tmp_path / "cache"), "sync-search", "q", "--yes"],
        environ={"ANTIEK_CORE_API_KEY": KEY},
        search=lambda query, limit: (_ for _ in ()).throw(httpx.ReadError(attacker)),
    ) == EXIT_PROVIDER
    captured = capsys.readouterr()
    assert captured.err == '{"error":"provider_request_failed"}\n'
    assert KEY not in captured.err + captured.out and attacker not in captured.err + captured.out


def test_empty_provider_result_fails_as_cache_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(
        ["--cache-dir", str(tmp_path / "cache"), "sync-search", "q", "--yes"],
        environ={"ANTIEK_CORE_API_KEY": KEY},
        search=lambda query, limit: [],
    ) == EXIT_CACHE
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}


def test_live_transport_pins_endpoint_key_redirect_and_response_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_client = httpx.Client
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "id": "123",
                        "title": "Knowledge graph",
                        "abstract": "Evidence",
                        "authors": [{"name": "Ada"}],
                    }
                ]
            },
        )

    def factory(**kwargs: object) -> httpx.Client:
        assert kwargs["follow_redirects"] is False
        return original_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", factory)
    client, search = _live_search(KEY, CoreSnapshotStore(tmp_path / "cache"))
    try:
        assert search("knowledge", 1)[0].source_id == "123"
    finally:
        client.close()
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.core.ac.uk/v3/search/works"
    assert seen[0].headers["Authorization"] == f"Bearer {KEY}"
    assert json.loads(seen[0].content) == {"limit": 1, "q": "knowledge"}


def test_live_transport_rejects_oversized_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"x" * (10 * 1024 * 1024 + 1))

    def factory(**kwargs: object) -> httpx.Client:
        return original_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", factory)
    client, search = _live_search(KEY, CoreSnapshotStore(tmp_path / "cache"))
    try:
        with pytest.raises(RuntimeError, match="exceeds local bound"):
            search("knowledge", 1)
    finally:
        client.close()


def test_live_transport_persists_provider_backoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_client = httpx.Client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "60"}, json={"error": "slow down"})

    def factory(**kwargs: object) -> httpx.Client:
        return original_client(transport=httpx.MockTransport(handler), **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(httpx, "Client", factory)
    cache = tmp_path / "cache"
    client, search = _live_search(KEY, CoreSnapshotStore(cache))
    try:
        with pytest.raises(httpx.HTTPStatusError):
            search("knowledge", 1)
    finally:
        client.close()
    assert SourceThrottle(state_path=str(cache / "throttle.json")).is_banned("core")


def test_store_rejects_duplicate_tamper_and_symlink(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    store = CoreSnapshotStore(directory)
    with pytest.raises(CoreSnapshotError, match="duplicate"):
        store.publish((_record(), _record()))
    store.publish((_record(),))
    connection = sqlite3.connect(directory / "works.sqlite3")
    connection.execute("UPDATE works SET payload = '{}' WHERE id = '123'")
    connection.commit()
    connection.close()
    with pytest.raises(CoreSnapshotError, match="digest"):
        store.load()
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(CoreSnapshotError):
        CoreSnapshotStore(link)


def test_concurrent_publish_and_newer_wins(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    first, second = CoreSnapshotStore(directory), CoreSnapshotStore(directory)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def publish(store: CoreSnapshotStore, record: dict[str, object]) -> None:
        try:
            barrier.wait()
            store.publish((record,))
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=publish, args=(first, _record("A", "Alpha"))),
        threading.Thread(target=publish, args=(second, _record("B", "Beta"))),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    store = CoreSnapshotStore(directory)
    assert [item["id"] for item in store.load()] == ["A", "B"]
    store.publish((_record("A", "New", STAMP + 1),))
    store.publish((_record("A", "Old", STAMP),))
    assert next(item for item in store.load() if item["id"] == "A")["title"] == "New"


def test_snapshot_failure_is_cache_not_provider(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(self: CoreSnapshotStore, records: object) -> tuple[dict[str, object], ...]:
        raise CoreSnapshotError("disk contract failed")

    monkeypatch.setattr(CoreSnapshotStore, "publish", fail)
    assert main(
        ["--cache-dir", str(tmp_path / "cache"), "sync-search", "q", "--yes"],
        environ={"ANTIEK_CORE_API_KEY": KEY},
        search=lambda query, limit: [_paper()],
    ) == EXIT_CACHE
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}
