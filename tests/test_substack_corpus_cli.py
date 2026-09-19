from __future__ import annotations

import json
import socket
import subprocess
import sys
import threading
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest

from acquisition.substack_cache import SubstackSnapshotError, SubstackSnapshotStore
from tools.substack_corpus import (
    EXIT_CACHE,
    EXIT_CONFIGURATION,
    EXIT_MISS,
    EXIT_OK,
    EXIT_PROVIDER,
    main,
)

STAMP = 1_767_225_600.0
FEED = """<rss xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>Open analysis</title><link>https://writer.substack.com/p/open</link>
<content:encoded><![CDATA[<p>Semiconductor evidence</p>]]></content:encoded></item>
<item><title>Metadata only</title><link>https://writer.substack.com/p/metadata</link></item>
</channel></rss>"""


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
    headers: dict[str, str] = {}

    def __init__(self, text: str = FEED) -> None:
        self.text = text

    def json(self) -> object:
        raise AssertionError("RSS sync must not call archive JSON")


def _persisted(url: str, title: str, *, accessible: bool = True) -> dict[str, object]:
    return {
        "url": url,
        "title": title,
        "body_html": "<p>Body</p>" if accessible else None,
        "accessible": accessible,
        "fetched_at": STAMP,
        "publication": "writer.substack.com",
    }


def test_help_is_operator_usable() -> None:
    result = subprocess.run(
        [sys.executable, "tools/substack_corpus.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert all(command in result.stdout for command in ("sync-feed", "search", "fetch"))


def test_sync_requires_confirmation_before_provider_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def forbidden(url: str) -> Response:
        raise AssertionError(url)

    assert (
        main(
            ["--cache-dir", str(tmp_path / "cache"), "sync-feed", "https://writer.substack.com"],
            environ={},
            get=forbidden,
        )
        == EXIT_CONFIGURATION
    )
    assert json.loads(capsys.readouterr().err)["error"] == "live_request_not_confirmed"


@pytest.mark.parametrize(
    "url",
    [
        "http://writer.substack.com",
        "https://writer.substack.com.evil.test",
        "https://user@writer.substack.com",
        "https://writer.substack.com:444",
        "https://writer.substack.com/path",
        "https://127.0.0.1",
    ],
)
def test_sync_refuses_noncanonical_or_ssrf_hosts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], url: str
) -> None:
    assert (
        main(
            ["--cache-dir", str(tmp_path / "cache"), "sync-feed", url, "--yes"],
            environ={},
            get=lambda target: (_ for _ in ()).throw(AssertionError(target)),
        )
        == EXIT_CACHE
    )
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}


def test_sync_persists_before_success_and_preserves_paywall_state(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    monkeypatch.setattr("acquisition.substack_feed.client.time.time", lambda: STAMP)
    cache = tmp_path / "cache"
    assert (
        main(
            [
                "--cache-dir",
                str(cache),
                "sync-feed",
                "https://writer.substack.com/",
                "--yes",
            ],
            environ={},
            get=lambda url: seen.append(url) or Response(),
        )
        == EXIT_OK
    )
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "accessible": 1,
        "count": 2,
        "publication": "writer.substack.com",
        "status": "persisted",
    }
    assert seen == ["https://writer.substack.com/feed"]
    reopened = SubstackSnapshotStore(cache).load()
    assert len(reopened) == 2
    assert next(item for item in reopened if item["url"].endswith("metadata"))["body_html"] is None


def test_search_and_fetch_are_offline_and_paywall_honest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cache = tmp_path / "cache"
    store = SubstackSnapshotStore(cache)
    store.publish(
        (
            _persisted("https://writer.substack.com/p/open", "Semiconductor research"),
            _persisted(
                "https://writer.substack.com/p/private", "Private AI analysis", accessible=False
            ),
        )
    )
    assert main(["--cache-dir", str(cache), "search", "Semiconductor"], environ={}) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["hits"][0]["id"].endswith("/open")
    assert (
        main(["--cache-dir", str(cache), "fetch", "https://writer.substack.com/p/open"], environ={})
        == EXIT_OK
    )
    assert json.loads(capsys.readouterr().out)["content"] == "Body"
    assert (
        main(
            ["--cache-dir", str(cache), "fetch", "https://writer.substack.com/p/private"],
            environ={},
        )
        == EXIT_MISS
    )
    assert json.loads(capsys.readouterr().err)["reason"] == "content unavailable by source policy"


def test_provider_failure_is_redacted_and_does_not_publish(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    attacker = "reflected-upstream-body"

    def fail(url: str) -> Response:
        raise httpx.ReadError(attacker)

    cache = tmp_path / "cache"
    assert (
        main(
            [
                "--cache-dir",
                str(cache),
                "sync-feed",
                "https://writer.substack.com",
                "--yes",
            ],
            environ={},
            get=fail,
        )
        == EXIT_PROVIDER
    )
    captured = capsys.readouterr()
    assert captured.err == '{"error":"provider_request_failed"}\n'
    assert attacker not in captured.err + captured.out
    assert SubstackSnapshotStore(cache).load() == ()


def test_transaction_rolls_back_and_concurrent_updates_keep_newest(tmp_path: Path) -> None:
    directory = tmp_path / "cache"
    first, second = SubstackSnapshotStore(directory), SubstackSnapshotStore(directory)
    first.publish((_persisted("https://writer.substack.com/p/a", "Old"),))
    newer = {**_persisted("https://writer.substack.com/p/a", "New"), "fetched_at": STAMP + 2}
    other = _persisted("https://writer.substack.com/p/b", "Other")
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def publish(store: SubstackSnapshotStore, record: dict[str, object]) -> None:
        try:
            barrier.wait()
            store.publish((record,))
        except BaseException as error:
            errors.append(error)

    threads = [
        threading.Thread(target=publish, args=(first, newer)),
        threading.Thread(target=publish, args=(second, other)),
    ]
    [thread.start() for thread in threads]
    [thread.join() for thread in threads]
    assert errors == []
    loaded = SubstackSnapshotStore(directory).load()
    assert [(item["url"], item["title"]) for item in loaded] == [
        ("https://writer.substack.com/p/a", "New"),
        ("https://writer.substack.com/p/b", "Other"),
    ]


def test_symlink_and_hostile_records_fail_closed(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(SubstackSnapshotError, match="real directory"):
        SubstackSnapshotStore(link)
    store = SubstackSnapshotStore(tmp_path / "cache")
    with pytest.raises(SubstackSnapshotError, match="inaccessible"):
        store.publish(
            (
                {
                    **_persisted("https://writer.substack.com/p/leak", "Leak", accessible=False),
                    "body_html": "subscriber-only content",
                },
            )
        )
    assert store.load() == ()
