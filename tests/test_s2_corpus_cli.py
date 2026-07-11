from __future__ import annotations

import json
import socket
import subprocess
import sys
from collections.abc import Iterator, Mapping
from pathlib import Path

import httpx
import pytest

from acquisition.s2_cache import S2SnapshotStore
from tools.s2_corpus import (
    EXIT_CACHE,
    EXIT_CONFIGURATION,
    EXIT_MISS,
    EXIT_OK,
    EXIT_PROVIDER,
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

    def __init__(self, records: list[dict[str, object]]) -> None:
        self.records = records

    def json(self) -> list[dict[str, object]]:
        return self.records


def _record(paper_id: str = "S2-1") -> dict[str, object]:
    return {
        "paperId": paper_id,
        "requestedId": "ARXIV:2401.1",
        "title": "Durable research graph",
        "abstract": "Knowledge survives process restart.",
        "fetched_at": STAMP,
        "source": "semantic_scholar",
    }


def test_help_is_operator_usable() -> None:
    result = subprocess.run(
        [sys.executable, "tools/s2_corpus.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "enrich" in result.stdout and "search" in result.stdout and "fetch" in result.stdout


def test_enrich_requires_explicit_confirmation_and_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(*args: object, **kwargs: object) -> Response:
        raise AssertionError("provider must not be called")

    cache = tmp_path / "s2"
    assert main(["--cache-dir", str(cache), "enrich", "S2-1"], environ={}, post=forbidden) == 3
    assert json.loads(capsys.readouterr().err)["error"] == "live_request_not_confirmed"
    assert (
        main(
            ["--cache-dir", str(cache), "enrich", "S2-1", "--yes"],
            environ={},
            post=forbidden,
        )
        == EXIT_CONFIGURATION
    )
    assert json.loads(capsys.readouterr().err) == {"error": "missing_s2_api_key"}


def test_enrich_uses_governed_request_and_persists_without_printing_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "never-print-this-s2-key"
    seen: list[tuple[str, Mapping[str, str], dict[str, object]]] = []

    def post(url: str, headers: Mapping[str, str], body: dict[str, object]) -> Response:
        seen.append((url, headers, body))
        return Response(
            [{"paperId": "S2-1", "title": "Durable research graph", "abstract": "Evidence"}]
        )

    monkeypatch.setattr("acquisition.s2_cache.client.time.time", lambda: STAMP)
    cache = tmp_path / "s2"
    assert (
        main(
            ["--cache-dir", str(cache), "enrich", "ARXIV:2401.1", "--yes"],
            environ={"S2_API_KEY": secret},
            post=post,
        )
        == EXIT_OK
    )
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    assert seen[0][1] == {"x-api-key": secret}
    assert seen[0][2] == {"ids": ["ARXIV:2401.1"]}
    output = json.loads(captured.out)
    assert output["status"] == "persisted" and output["paper_ids"] == ["S2-1"]
    assert S2SnapshotStore(cache).load()[0]["requestedId"] == "ARXIV:2401.1"


def test_search_and_fetch_are_offline_machine_readable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "s2"
    S2SnapshotStore(cache).publish((_record(),))
    assert main(["--cache-dir", str(cache), "search", "process restart"], environ={}) == EXIT_OK
    search = json.loads(capsys.readouterr().out)
    assert search["count"] == 1 and search["hits"][0]["id"] == "S2-1"
    assert main(["--cache-dir", str(cache), "fetch", "S2-1"], environ={}) == EXIT_OK
    fetched = json.loads(capsys.readouterr().out)
    assert fetched["content"] == "Durable research graph\n\nKnowledge survives process restart."
    assert fetched["source_kind"] == "semantic_scholar"


def test_fetch_miss_has_stable_exit_and_json_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--cache-dir", str(tmp_path / "s2"), "fetch", "missing"], environ={}) == EXIT_MISS
    assert json.loads(capsys.readouterr().err) == {
        "error": "paper_not_found",
        "paper_id": "missing",
    }


def test_provider_failure_never_echoes_attacker_body_or_secret(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    secret = "s2-secret-reflected"

    def fail(*args: object, **kwargs: object) -> Response:
        raise httpx.ReadError(f"attacker body contains {secret}")

    assert (
        main(
            ["--cache-dir", str(tmp_path / "s2"), "enrich", "S2-1", "--yes"],
            environ={"S2_API_KEY": secret},
            post=fail,
        )
        == EXIT_PROVIDER
    )
    captured = capsys.readouterr()
    assert json.loads(captured.err) == {"error": "provider_request_failed"}
    assert secret not in captured.err + captured.out


def test_invalid_batch_and_cache_fail_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "s2"
    assert (
        main(
            ["--cache-dir", str(cache), "enrich", "same", "same", "--yes"],
            environ={"S2_API_KEY": "secret"},
            post=lambda *args: Response([]),
        )
        == EXIT_CONFIGURATION
    )
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_batch"
    too_many = [f"id-{index}" for index in range(101)]
    assert (
        main(
            ["--cache-dir", str(cache), "enrich", *too_many, "--yes"],
            environ={"S2_API_KEY": "secret"},
            post=lambda *args: Response([]),
        )
        == EXIT_CONFIGURATION
    )
    assert json.loads(capsys.readouterr().err) == {
        "error": "invalid_batch",
        "max_ids": 100,
        "unique_required": True,
    }
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    assert main(["--cache-dir", str(link), "search", "x"], environ={}) == EXIT_CACHE
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}
