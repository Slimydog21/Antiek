from __future__ import annotations

import hashlib

import duckdb
import pytest
from fastapi import HTTPException

from interfaces.research.api.hosted_document_routes import (
    _legal_citation_payload,
    resolve_citation_evidence_groups,
    resolve_legal_citation_insertion_source,
)
from substrate.legal_gate import read as legal_read


class _Connection:
    def close(self) -> None:
        pass


class _HintConnection(_Connection):
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _query, _params):
        return self

    def fetchall(self):
        return self.rows


def test_legal_citation_projection_uses_sealed_reader_and_opaque_anchor(monkeypatch):
    monkeypatch.setattr(duckdb, "connect", lambda *_args, **_kwargs: _Connection())
    monkeypatch.setattr(legal_read, "document_investigation_hint", lambda *_: "inv-1")
    monkeypatch.setattr(legal_read, "read_document", lambda *_: {
        "raw_text": "first second", "title": "Source", "author": "A", "document_type": "note"
    })
    monkeypatch.setattr(legal_read, "read_chunks", lambda *_: (
        {"chunk_id": "chunk-1", "chunk_index": 0, "section_path": None, "text": "first", "token_count": 1},
        {"chunk_id": "chunk-2", "chunk_index": 1, "section_path": None, "text": "second", "token_count": 1},
    ))
    out = _legal_citation_payload("doc-1", ["chunk-2"], owner_id="alice")
    anchor = "antiek-chunk-" + hashlib.sha256(b"chunk-2").hexdigest()
    assert out["chunk_anchors"] == [{"chunk_id": "chunk-2", "anchor_id": anchor}]
    assert f'id="{anchor}" data-antiek-chunk-anchor="true"' in out["html"]
    assert '"chunk_id":"chunk-2"' not in out["html"]

    with pytest.raises(HTTPException) as caught:
        _legal_citation_payload("doc-1", ["foreign"], owner_id="alice")
    assert caught.value.status_code == 404

    title, source_sha, excerpt = resolve_legal_citation_insertion_source(
        "doc-1", ["chunk-2", "chunk-1"], owner_id="alice",
    )
    assert title == "Source"
    assert source_sha == hashlib.sha256(b"first second").hexdigest()
    assert excerpt == "second\n\nfirst"


def test_resolve_citation_evidence_groups_preserves_document_and_chunk_order(monkeypatch):
    rows = [
        ("a-1", "doc-a", "inv-a"),
        ("b-1", "doc-b", "inv-b"),
        ("a-2", "doc-a", "inv-a"),
    ]
    monkeypatch.setattr(duckdb, "connect", lambda *_args, **_kwargs: _HintConnection(rows))

    def readable(_con, authority, document_id):
        assert authority.account_id == "alice"
        if document_id == "doc-a":
            return ({"chunk_id": "a-1"}, {"chunk_id": "a-2"})
        return ({"chunk_id": "b-1"},)

    monkeypatch.setattr(legal_read, "read_chunks", readable)
    groups = resolve_citation_evidence_groups(
        ["a-1", "b-1", "a-2"],
        owner_id="alice",
        source_asset_id="root-investigation",
        claim_id="artifact-v2:" + "a" * 64 + ":0",
    )
    assert [(item.document_id, item.chunk_ids) for item in groups] == [
        ("doc-a", ("a-1", "a-2")),
        ("doc-b", ("b-1",)),
    ]
    assert all(item.source_asset_id == "root-investigation" for item in groups)
    assert len({item.receipt_sha256 for item in groups}) == 2


def test_resolve_citation_evidence_groups_fails_whole_set_on_denied_chunk(monkeypatch):
    monkeypatch.setattr(
        duckdb,
        "connect",
        lambda *_args, **_kwargs: _HintConnection([
            ("allowed", "doc-a", "inv-a"),
            ("denied", "doc-b", "inv-b"),
        ]),
    )

    def readable(_con, _authority, document_id):
        if document_id == "doc-b":
            raise legal_read.LegalPolicyDenied("denied")
        return ({"chunk_id": "allowed"},)

    monkeypatch.setattr(legal_read, "read_chunks", readable)
    with pytest.raises(HTTPException) as caught:
        resolve_citation_evidence_groups(
            ["allowed", "denied"],
            owner_id="alice",
            source_asset_id="root",
            claim_id="claim",
        )
    assert caught.value.status_code == 404
    assert caught.value.headers == {"Cache-Control": "no-store"}
