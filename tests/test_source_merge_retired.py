"""The source-merge preview, apply and commit routes are retired: 410.

Under the operator's binding ruling T6 a merge never writes the source
document. It either adopts a reformulation as the project's reading version or
merges into a Write draft (THREAD-CONTRACT §1.11 "Source merge (corrected in
rev 8.8)"). ``commit`` rewrote a source document's body from a reviewed
twin-note merge, ``apply`` wrote the receipt and audit event that commit
consumed, and ``preview`` took the write lock and read the client-named draft
to compute the body commit would write. Each path stays registered so an old
client gets one stable answer, but its handler takes no body, so the reviewed
packet is never parsed, and it answers before opening the database, taking a
lock, reading a file, writing a receipt or emitting an event.

``restore`` is not retired: it undoes a merge already committed on prod, and
its route tests stay in ``test_artifact_routes.py``.
"""

from __future__ import annotations

import contextlib
import dataclasses
import os
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest
from fastapi.testclient import TestClient
from test_artifact_routes import (  # noqa: F401  (fixture)
    _source_merge_commit_payload,
    _source_merge_ready_packet,
    api_env,
)

import interfaces.research.api.artifact_routes as artifact_routes
import runtime.db_lock as db_lock
import substrate.research_artifact as research_artifact
import substrate.research_artifact.paths as artifact_paths
import substrate.research_artifact.source_merge as source_merge
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write

RETIRED = {"reason": "retired", "alternatives": ["adopt_reading_version", "merge_into_write"]}
SECRET = "ANTIEK_SECRET_TOKEN=do-not-exfiltrate"
SECRET_NAME = "retired-route-secret.env"
ROUTES = ("preview", "apply", "commit")
RECEIPT_TABLES = ("source_merge_revisions", "source_merge_body_commits", "source_merge_body_restores")
SUBSTRATE_ENTRYPOINTS = (
    "preview_source_merge_review",
    "apply_source_merge_review",
    "commit_source_merge_review",
    "read_reviewed_draft_merge",
)


# Opens are watched through an audit hook because it sees every ``open`` a
# handler could make (builtins.open, os.open, pathlib) whatever name it was
# imported under. The hook is process-wide and cannot be removed, so it stays
# inert unless a test is watching a basename.
_WATCHED: dict[str, list[str]] = {}
_HOOK_INSTALLED: list[bool] = []


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if event != "open" or not _WATCHED or not args or isinstance(args[0], int):
        return
    try:
        target = os.fsdecode(args[0])
    except TypeError:
        return
    hits = _WATCHED.get(os.path.basename(target))
    if hits is not None:
        hits.append(target)


@contextlib.contextmanager
def _watching_opens(*basenames: str) -> Iterator[list[str]]:
    if not _HOOK_INSTALLED:
        sys.addaudithook(_audit)
        _HOOK_INSTALLED.append(True)
    hits: list[str] = []
    for name in basenames:
        _WATCHED[name] = hits
    try:
        yield hits
    finally:
        _WATCHED.clear()


@contextlib.contextmanager
def _tripwire() -> Iterator[list[str]]:
    """Record (and pass through) every database, lock or source-merge entry
    point a handler reaches while the request runs."""
    touched: list[str] = []

    def recording(label: str, real: Any) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            touched.append(label)
            return real(*args, **kwargs)

        return call

    targets: list[tuple[str, Any, str]] = [
        ("duckdb.connect", duckdb, "connect"),
        ("runtime.db_lock.connect_write", db_lock, "connect_write"),
        ("runtime.db_lock.connect_read", db_lock, "connect_read"),
        ("artifact_routes._db", artifact_routes, "_db"),
        ("artifact_routes.connect_write", artifact_routes, "connect_write"),
    ]
    for name in SUBSTRATE_ENTRYPOINTS:
        for label, module in (
            ("source_merge", source_merge),
            ("research_artifact", research_artifact),
            ("paths", artifact_paths),
            ("artifact_routes", artifact_routes),
        ):
            if hasattr(module, name):
                targets.append((f"{label}.{name}", module, name))
    with pytest.MonkeyPatch.context() as mp:
        for label, module, attr in targets:
            mp.setattr(module, attr, recording(label, getattr(module, attr)))
        yield touched


def _tree(root: Path) -> dict[str, bytes | str]:
    """Every entry under ``root``: file bytes, symlink targets, directories."""
    entries: dict[str, bytes | str] = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for name in dirnames + filenames:
            path = Path(dirpath) / name
            key = str(path.relative_to(root))
            if path.is_symlink():
                entries[key] = "symlink:" + os.readlink(path)
            elif path.is_file():
                entries[key] = path.read_bytes()
            else:
                entries[key] = "dir"
    return entries


def _db_state() -> dict[str, Any]:
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/retired_source_merge_state") as con:
        (source_body,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", ["doc-source-merge"]
        ).fetchone()
        tables = {row[0] for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
        receipts = {
            table: con.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in RECEIPT_TABLES
            if table in tables
        }
    return {"source_body": source_body, "receipts": receipts}


def _secret_file(api_env: dict[str, str]) -> Path:  # noqa: F811
    secret = Path(api_env["arts"]).parent / SECRET_NAME
    secret.write_text(SECRET + "\n")
    return secret


def _full_body(route: str, packet: dict, hashes: dict[str, str]) -> dict:
    """A body the pre-retirement route accepted and acted on."""
    if route != "commit":
        return {
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
            "operator_reviewer": "pytest",
        }
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/retired_commit_evidence") as con:
        evidence = source_merge.preview_source_merge_review(
            con,
            document_id=packet["document_id"],
            draft_merge_path=packet["draft_merge_path"],
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=hashes,
            hash_conflicts=packet["hash_conflicts"],
        )
    return _source_merge_commit_payload(packet, hashes, dataclasses.asdict(evidence))


def _post(client: TestClient, route: str, variant: str, body: dict):
    url = f"/research/artifacts/source-merge/{route}"
    if variant == "empty":
        return client.post(url)
    return client.post(url, json=body)


@pytest.mark.parametrize("variant", ["full", "secret-draft", "empty"])
@pytest.mark.parametrize("route", ROUTES)
def test_retired_route_answers_410_and_touches_nothing(api_env, route, variant):  # noqa: F811
    client = TestClient(create_app(register_wrestling=False), raise_server_exceptions=False)
    packet, hashes = _source_merge_ready_packet(client)
    draft_name = Path(packet["draft_merge_path"]).name
    secret = _secret_file(api_env)
    body = _full_body(route, packet, hashes)
    if variant == "secret-draft":
        body["reviewed_packet"] = {**packet, "draft_merge_path": str(secret)}
    events, arts = Path(api_env["events"]), Path(api_env["arts"])
    before = (_db_state(), _tree(events), _tree(arts))

    with _tripwire() as touched, _watching_opens(draft_name, SECRET_NAME) as opened:
        resp = _post(client, route, variant, body)

    db_after, events_after, arts_after = _db_state(), _tree(events), _tree(arts)
    assert touched == [], f"retired {route} reached the database, the lock or the substrate: {touched}"
    assert opened == [], f"retired {route} opened a client-named file: {opened}"
    assert resp.status_code == 410, resp.text
    assert resp.json() == RETIRED
    assert SECRET not in resp.text
    assert db_after["source_body"] == before[0]["source_body"], "the source document body changed"
    assert db_after["receipts"] == before[0]["receipts"], "a source-merge receipt was written"
    assert events_after == before[1], "the event log changed"
    assert arts_after == before[2], "the artifacts directory changed"


def test_the_open_watcher_sees_the_reads_it_guards_against(api_env):  # noqa: F811
    # Positive control, so "opened == []" above cannot pass vacuously: the
    # confined reader opens the draft by a bare name relative to a directory
    # descriptor, and a plain read opens the secret by its absolute path.
    packet, _ = _source_merge_ready_packet(TestClient(create_app(register_wrestling=False)))
    draft = Path(packet["draft_merge_path"])
    secret = _secret_file(api_env)
    with _watching_opens(draft.name, SECRET_NAME) as opened:
        artifact_paths.read_reviewed_draft_merge(str(draft))
        secret.read_text()
    assert [os.path.basename(hit) for hit in opened] == [draft.name, SECRET_NAME], opened


@pytest.mark.parametrize("route", ROUTES)
def test_retired_route_declares_no_request_body(route):
    # FastAPI reads and validates a body only for a declared body parameter;
    # the schema is where a reintroduced one would show.
    operation = create_app(register_wrestling=False).openapi()["paths"][
        f"/research/artifacts/source-merge/{route}"
    ]["post"]
    assert "requestBody" not in operation, operation
    assert operation.get("deprecated") is True, operation
    assert list(operation["responses"]) == ["410"], operation["responses"]
    assert "T6" in operation["responses"]["410"]["description"], operation["responses"]
