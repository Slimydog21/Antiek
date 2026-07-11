from __future__ import annotations

import datetime
import os
import socket
import threading
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

import pytest

from acquisition.corpus_bridge import AcquisitionCorpusAdapter, from_semantic_scholar
from acquisition.s2_cache import CachedS2Enricher, S2SnapshotError, S2SnapshotStore
from acquisition.s2_enrich import S2Client
from substrate.corpus_contract import CorpusDocument
from substrate.corpus_contract.conformance import FixtureDoc, assert_corpus_conformance

STAMP = 1_767_225_600.0


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    yield


class StubClient:
    def __init__(self, response: list[dict[str, object]]) -> None:
        self.response = response
        self.calls: list[tuple[list[str], tuple[str, ...]]] = []

    def enrich(
        self, ids: list[str], fields: tuple[str, ...] = ("title", "citationCount")
    ) -> list[dict[str, object]]:
        self.calls.append((ids, fields))
        return self.response


def _raw(paper_id: str, title: str, abstract: str | None = None) -> dict[str, object]:
    return {"paperId": paper_id, "title": title, "abstract": abstract}


def _persisted(paper_id: str, content: str) -> dict[str, object]:
    return {
        "paperId": paper_id,
        "requestedId": paper_id,
        "title": content,
        "abstract": None,
        "fetched_at": STAMP,
        "source": "semantic_scholar",
    }


def _factory(fixtures: tuple[FixtureDoc, ...]) -> AcquisitionCorpusAdapter:
    return from_semantic_scholar(
        tuple(_persisted(fixture.id, fixture.content) for fixture in fixtures)
    )


def test_persisted_semantic_scholar_passes_mandatory_corpus_conformance() -> None:
    assert_corpus_conformance(_factory)


def test_real_s2_client_contract_persists_before_return(tmp_path: Path) -> None:
    class Response:
        status_code = 200

        def json(self) -> list[dict[str, object]]:
            return [_raw("S2-1", "Durable research", "Evidence survives restart")]

    seen: list[tuple[str, dict[str, object]]] = []

    def post(url: str, headers: Mapping[str, str], body: dict[str, object]) -> Response:
        del headers
        seen.append((url, body))
        return Response()

    real_client = S2Client(
        post=post,
        now=lambda: 0.0,
    )
    store = S2SnapshotStore(tmp_path / "s2")
    result = CachedS2Enricher(real_client, store, now=lambda: STAMP).enrich(["S2-1"])
    assert result == store.load()
    assert result[0]["requestedId"] == "S2-1"
    assert seen[0][1] == {"ids": ["S2-1"]}
    assert "fields=title,abstract" in seen[0][0]
    reopened = S2SnapshotStore(tmp_path / "s2").load()
    document = from_semantic_scholar(reopened).fetch("S2-1")
    assert type(document) is CorpusDocument
    assert document.content == "Durable research\n\nEvidence survives restart"
    assert document.provenance.retrieved_at == datetime.datetime(2026, 1, 1, tzinfo=datetime.UTC)


def test_wrapper_requests_fixed_corpus_fields_and_detaches_response(tmp_path: Path) -> None:
    raw = _raw("S2-2", "Original", "Abstract")
    client = StubClient([raw])
    store = S2SnapshotStore(tmp_path / "s2")
    result = CachedS2Enricher(client, store, now=lambda: STAMP).enrich(["ARXIV:1"])
    assert client.calls == [(["ARXIV:1"], ("title", "abstract"))]
    raw["title"] = "Mutated"
    assert result[0]["title"] == "Original"
    assert S2SnapshotStore(tmp_path / "s2").load()[0]["title"] == "Original"


def test_second_batch_merges_and_replaces_by_canonical_paper_id(tmp_path: Path) -> None:
    store = S2SnapshotStore(tmp_path / "s2")
    first = CachedS2Enricher(StubClient([_raw("B", "Old B")]), store, now=lambda: STAMP)
    second = CachedS2Enricher(
        StubClient([_raw("A", "A"), _raw("B", "New B")]),
        store,
        now=lambda: STAMP + 1,
    )
    first.enrich(["input-b"])
    records = second.enrich(["input-a", "input-b"])
    assert [record["paperId"] for record in records] == ["A", "B"]
    assert records[1]["title"] == "New B"
    assert records[1]["requestedId"] == "input-b"
    assert records[1]["fetched_at"] == STAMP + 1
    assert len(list((tmp_path / "s2").glob("snapshot-*.json"))) == 1


def test_concurrent_publishers_do_not_lose_updates(tmp_path: Path) -> None:
    directory = tmp_path / "s2"
    first = S2SnapshotStore(directory)
    second = S2SnapshotStore(directory)
    barrier = threading.Barrier(2)
    errors: list[BaseException] = []

    def publish(store: S2SnapshotStore, record: dict[str, object]) -> None:
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
    assert [record["paperId"] for record in S2SnapshotStore(directory).load()] == ["A", "B"]


def test_failed_current_swap_leaves_previous_generation_authoritative(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = S2SnapshotStore(tmp_path / "s2")
    store.publish((_persisted("A", "Alpha"),))
    real_replace = os.replace

    def fail_current(source: Path, destination: Path) -> None:
        if Path(destination).name == "CURRENT":
            raise OSError("injected pointer swap failure")
        real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_current)
    with pytest.raises(OSError, match="pointer"):
        store.publish((_persisted("B", "Beta"),))
    assert [record["paperId"] for record in S2SnapshotStore(tmp_path / "s2").load()] == ["A"]
    assert len(list((tmp_path / "s2").glob("snapshot-*.json"))) == 1


def test_declared_size_short_read_fails_explicitly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "s2"
    store = S2SnapshotStore(directory)
    store.publish((_persisted("A", "Alpha"),))
    real_read = os.read
    calls = 0

    def truncate(fd: int, size: int) -> bytes:
        nonlocal calls
        calls += 1
        if calls == 1:
            return real_read(fd, max(1, size // 2))
        return b""

    monkeypatch.setattr(os, "read", truncate)
    with pytest.raises(S2SnapshotError, match="declared size"):
        store.load()


@pytest.mark.parametrize(
    "response",
    [
        [],
        [_raw("A", "A"), _raw("A", "duplicate")],
        [{"paperId": "A", "title": "missing abstract"}],
        [{"paperId": "A", "title": "A", "abstract": ""}],
    ],
)
def test_hostile_s2_responses_fail_before_publication(
    tmp_path: Path, response: list[dict[str, object]]
) -> None:
    store = S2SnapshotStore(tmp_path / "s2")
    ids = [f"input-{index}" for index in range(max(1, len(response)))]
    with pytest.raises(S2SnapshotError):
        CachedS2Enricher(StubClient(response), store, now=lambda: STAMP).enrich(ids)
    assert store.load() == ()


@pytest.mark.parametrize("clock", [None, True, "now", -1, float("nan"), float("inf")])
def test_hostile_clocks_fail_before_publication(tmp_path: Path, clock: Any) -> None:
    store = S2SnapshotStore(tmp_path / "s2")
    with pytest.raises(S2SnapshotError, match="clock"):
        CachedS2Enricher(StubClient([_raw("A", "A")]), store, now=lambda: clock).enrich(["A"])
    assert store.load() == ()


def test_publish_failure_is_not_returned_as_success(tmp_path: Path) -> None:
    class RejectingStore(S2SnapshotStore):
        def publish(
            self, records: tuple[Mapping[str, object], ...]
        ) -> tuple[dict[str, object], ...]:
            del records
            raise S2SnapshotError("disk unavailable")

    with pytest.raises(S2SnapshotError, match="disk unavailable"):
        CachedS2Enricher(
            StubClient([_raw("A", "A")]), RejectingStore(tmp_path / "s2"), now=lambda: STAMP
        ).enrich(["A"])


def test_tampered_snapshot_and_symlinked_current_fail_closed(tmp_path: Path) -> None:
    directory = tmp_path / "s2"
    store = S2SnapshotStore(directory)
    store.publish((_persisted("A", "Alpha"),))
    name = (directory / "CURRENT").read_text().strip()
    (directory / name).write_text("{}")
    with pytest.raises(S2SnapshotError, match="digest"):
        store.load()

    (directory / "CURRENT").unlink()
    (directory / "target").write_text(name)
    (directory / "CURRENT").symlink_to(directory / "target")
    with pytest.raises(S2SnapshotError, match="CURRENT"):
        store.load()


def test_non_private_or_symlink_cache_directory_rejected(tmp_path: Path) -> None:
    public = tmp_path / "public"
    public.mkdir(mode=0o755)
    with pytest.raises(S2SnapshotError, match="permissions"):
        S2SnapshotStore(public)
    target = tmp_path / "target"
    target.mkdir(mode=0o700)
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    with pytest.raises(S2SnapshotError, match="real directory"):
        S2SnapshotStore(link)
