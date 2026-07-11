from __future__ import annotations

import datetime
import json
import socket
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from acquisition.core_cache import CoreSnapshotStore
from acquisition.openalex_cache import OpenAlexSnapshotStore
from acquisition.s2_cache import S2SnapshotStore
from substrate.corpus_contract import (
    CorpusContractError,
    CorpusDocument,
    CorpusHit,
    CorpusMiss,
    Provenance,
)
from substrate.corpus_federation import FederatedCorpus, MountedCorpus
from tools.research_corpus import EXIT_CACHE, EXIT_CONFIGURATION, EXIT_MISS, EXIT_OK, main

STAMP = 1_767_225_600.0


@pytest.fixture(autouse=True)
def socket_guard(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network forbidden")),
    )
    yield


def _s2(id: str = "same") -> dict[str, object]:
    return {"paperId": id, "requestedId": "REQ", "title": "Knowledge graph", "abstract": "Shared evidence", "fetched_at": STAMP, "source": "semantic_scholar"}


def _openalex(id: str = "same") -> dict[str, object]:
    return {"id": id, "title": "Knowledge graph", "abstract_inverted_index": {"Shared": [0], "evidence": [1]}, "fetched_at": STAMP}


def _core(id: str = "same") -> dict[str, object]:
    return {"id": id, "title": "Knowledge graph", "abstract": "Shared evidence", "doi": None, "arxiv_id": None, "authors": ["Ada"], "declared_license": None, "fetched_at": STAMP, "source": "core"}


def _mount_args(tmp_path: Path) -> list[str]:
    s2, openalex, core = tmp_path / "s2", tmp_path / "openalex", tmp_path / "core"
    S2SnapshotStore(s2).publish((_s2(),))
    OpenAlexSnapshotStore(openalex).publish((_openalex(),))
    CoreSnapshotStore(core).publish((_core(),))
    return ["--mount", f"s2={s2}", "--mount", f"openalex={openalex}", "--mount", f"core={core}"]


def test_help_is_operator_usable() -> None:
    result = subprocess.run([sys.executable, "tools/research_corpus.py", "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0 and "--mount" in result.stdout


def test_search_qualifies_cross_source_collisions_and_fetch_preserves_provenance(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    mounts = _mount_args(tmp_path)
    assert main([*mounts, "search", "Shared evidence"]) == EXIT_OK
    output = json.loads(capsys.readouterr().out)
    assert [hit["id"] for hit in output["hits"]] == ["core:same", "openalex:same", "s2:same"]
    assert len({hit["score"] for hit in output["hits"]}) == 1
    expected = {"core": "core", "openalex": "openalex", "s2": "semantic_scholar"}
    for mount, source_kind in expected.items():
        assert main([*mounts, "fetch", f"{mount}:same"]) == EXIT_OK
        fetched = json.loads(capsys.readouterr().out)
        assert fetched["work_id"] == f"{mount}:same"
        assert fetched["origin_ref"] == "same" and fetched["source_kind"] == source_kind
        assert fetched["license_class"] == "source_terms_governed_metadata"


class Adapter:
    def __init__(self, hits: tuple[CorpusHit, ...], *, fail: bool = False) -> None:
        self.hits, self.fail = hits, fail

    def search(self, query: str) -> tuple[CorpusHit, ...]:
        if self.fail:
            raise CorpusContractError("source failed")
        return self.hits

    def fetch(self, id: str) -> CorpusDocument | CorpusMiss:
        return CorpusDocument("body", Provenance("fake", id, datetime.datetime.fromtimestamp(STAMP, tz=datetime.UTC), "terms"))


def test_rrf_uses_rank_not_incomparable_raw_score() -> None:
    federation = FederatedCorpus((
        MountedCorpus("a", Adapter((CorpusHit("first", 0.01, "one"), CorpusHit("second", 999.0, "two")))),
        MountedCorpus("b", Adapter((CorpusHit("only", 0.5, "three"),))),
    ))
    hits = federation.search("q")
    assert [hit.id for hit in hits] == ["a:first", "b:only", "a:second"]
    assert hits[0].score == hits[1].score > hits[2].score


def test_federation_never_silently_omits_failed_mount() -> None:
    federation = FederatedCorpus((
        MountedCorpus("good", Adapter((CorpusHit("x", 1.0, "x"),))),
        MountedCorpus("bad", Adapter((), fail=True)),
    ))
    with pytest.raises(CorpusContractError, match="source failed"):
        federation.search("q")


@pytest.mark.parametrize("limit", ["0", "301"])
def test_limit_bounds_are_configuration_errors(
    limit: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main([*_mount_args(tmp_path), "search", "q", "--limit", limit]) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_limit"


@pytest.mark.parametrize(
    ("command", "error"),
    [(["search", " padded"], "invalid_query"), (["fetch", "unqualified"], "invalid_qualified_id")],
)
def test_invalid_operator_input_fails_before_mount_open(
    command: list[str], error: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # The mount is deliberately invalid: input validation must win before any
    # authority inspection, so operator mistakes are not reported as cache faults.
    assert main(["--mount", f"core={tmp_path / 'missing'}", *command]) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err) == {"error": error}


def test_mount_configuration_and_unknown_fetch_are_stable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--mount", f"bad={tmp_path}", "search", "q"]) == EXIT_CONFIGURATION
    assert json.loads(capsys.readouterr().err)["error"] == "invalid_mount_configuration"
    mounts = _mount_args(tmp_path)
    assert main([*mounts, "fetch", "unknown:id"]) == EXIT_MISS
    assert json.loads(capsys.readouterr().err) == {"error": "work_not_found", "reason": "unknown corpus mount", "work_id": "unknown:id"}


def test_corrupt_authority_fails_as_cache_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    core = tmp_path / "core"
    CoreSnapshotStore(core).publish((_core(),))
    connection = sqlite3.connect(core / "works.sqlite3")
    connection.execute("UPDATE works SET payload = '{}' WHERE id = 'same'")
    connection.commit()
    connection.close()
    assert main(["--mount", f"core={core}", "search", "q"]) == EXIT_CACHE
    assert json.loads(capsys.readouterr().err) == {"error": "cache_contract_failed"}


def test_qualified_fetch_preserves_colons_inside_opaque_url_id(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    work_id = "https://openalex.org/W1"
    cache = tmp_path / "openalex"
    OpenAlexSnapshotStore(cache).publish((_openalex(work_id),))
    assert main(["--mount", f"openalex={cache}", "fetch", f"openalex:{work_id}"]) == EXIT_OK
    fetched = json.loads(capsys.readouterr().out)
    assert fetched["work_id"] == f"openalex:{work_id}"
    assert fetched["origin_ref"] == work_id
