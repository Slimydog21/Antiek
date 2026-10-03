"""Fork-merge route proofs (thread-merge + document fork SPR-02).

FastAPI TestClient against a REAL DuckDB fixture + REAL event log (the
api_env shape from tests/test_fork_routes.py). The spec's round trip:

  1. fork (SPR-01's path) → select outcome items from TWO threads →
     preview (receipt, honest after-hash) → commit → the fork body carries
     both items under provenance markers naming their threads; the
     ORIGINAL's body hash is unchanged end-to-end;
  2. one FORCED conflict: preview lists it; commit without a resolution is
     REFUSED (409, no partial write — body hash unchanged); commit with
     accept lands the incoming claim + the audit row; commit with keep_fork
     leaves the passage and still audits;
  3. anchor-based detection: with an anchor fixture on the passage, the
     differing-hash item is auto-LISTED; without anchors only (a)/(c) fire
     — the degradation asserted, not assumed;
  4. a withheld-source item merges only its own text, never source body —
     asserted on the committed fork body;
  5. audit completeness: every resolution row recomputes against the
     commit ledger (count + refs match).

Plus the boundary proofs: the multi-ack discipline (both acks), the
preview binding + staleness 409s, commit idempotency, the owner boundary,
and the shipped-contract gate — the retired source-merge routes still 410
and nothing new hangs off compose.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document, insert_node

PREVIEW = "/research/artifacts/fork-merge/preview"
COMMIT = "/research/artifacts/fork-merge/commit"


@pytest.fixture
def api_env(monkeypatch):
    # This is a substrate-free route fixture: ambient operator credentials on
    # a development workstation must not turn the hermetic TestClient into a
    # 401-only suite.
    for variable in (
        "ANTIEK_AUTH_SECRET",
        "ANTIEK_DEV_LOGIN_TOKEN",
        "ANTIEK_OPERATOR_EMAIL",
        "ANTIEK_OPERATOR_TOKEN",
        "ANTIEK_OPERATOR_SERVICE_TOKEN_CLIENT_ID",
        "CF_ACCESS_CLIENT_SECRET",
    ):
        monkeypatch.delenv(variable, raising=False)
    tmpdir = tempfile.mkdtemp(prefix="fork-merge-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed_book(
    db: str,
    document_id: str = "doc-parent",
    *,
    title: str = "Parent Book",
    raw_text: str = "The parent's full body.\n\nThe pinned passage stands here.",
    content_class: str = "public_domain",
) -> None:
    from substrate.books.model import upsert_book_asset

    with connect_write(db, purpose="test/seed-merge-book") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="book",
            title=title,
            raw_text=raw_text,
            content_class=content_class,
            on_conflict="ignore",
        )
        upsert_book_asset(con, document_id=document_id, page_count=1)


def _seed_thread(
    db: str,
    events: str,
    investigation_id: str,
    texts: list[str],
    *,
    source_document_id: str | None = None,
) -> list[str]:
    """Distilled insight nodes for a thread, event-logged so the distill
    read (the trajectory walk) sees them — exactly as a real research
    leaves them."""
    with connect_write(db, purpose="test/seed-thread") as con:
        return [
            insert_node(
                con,
                canonical_label=text,
                node_type="insight",
                graph_scope="depth",
                investigation_id=investigation_id,
                metadata=(
                    {"source_document_id": source_document_id}
                    if source_document_id
                    else None
                ),
                events_dir=events,
            )
            for text in texts
        ]


def _fork(client: TestClient, operation_id: str, parent: str = "doc-parent") -> dict:
    resp = client.post(f"/books/{parent}/forks", json={"operation_id": operation_id})
    assert resp.status_code == 201, resp.text
    return resp.json()


def _body(db: str, document_id: str) -> str:
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ? LIMIT 1",
            [document_id],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return str(row[0])


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _pin_anchor(
    db: str,
    document_id: str,
    *,
    passage: str,
    investigation_id: str | None,
) -> str:
    """Pin an active anchor on the fork document (unit-1 store), optionally
    linked to a thread — the anchor-based detection's fixture."""
    from substrate.books.highlights.store import (
        CreatePinCommand,
        HighlightSource,
        HighlightsStore,
        selection_sha256,
    )
    from substrate.feedback.domain import NodeTextAnchor

    with connect_write(db, purpose="test/pin-anchor") as con:
        row = HighlightsStore().create_pin(
            con,
            CreatePinCommand(
                owner_user_id="__operator__",
                document_id=document_id,
                anchor=NodeTextAnchor(
                    node_id=f"chunk-{document_id}-0",
                    node_text_sha256=selection_sha256(passage),
                    start_scalar=0,
                    end_scalar=len(passage),
                    quote=passage,
                    prefix="",
                    suffix="",
                ),
                servable_at_pin=True,
                source=HighlightSource.PIN,
                page_index_hint=0,
                investigation_id=investigation_id,
            ),
        )
    return row.anchor_id


def _claim_in_thread(events: str, investigation_id: str, node_id: str, text: str) -> None:
    """A second thread reaching the SAME claim: nodes are content-addressed
    and shared, so the second thread's claim is a note.emerged event naming
    the existing node id (the distill walk's note.emerged branch)."""
    from substrate.event_log import log_event
    from substrate.schemas.events import ActionType

    log_event(
        investigation_id,
        ActionType.NOTE_EMERGED.value,
        payload={"node_id": node_id, "note_text": text},
        role="note_taker",
        events_dir=events,
    )


def _items(pairs: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"investigation_id": iid, "node_id": nid} for iid, nid in pairs]


def _commit_body(
    fork_id: str,
    pairs: list[tuple[str, str]],
    preview: dict,
    *,
    resolutions: list[dict[str, str]] | None = None,
    flagged: list[tuple[str, str]] | None = None,
    ack_conflicts: bool = True,
) -> dict:
    return {
        "fork_id": fork_id,
        "items": _items(pairs),
        "flagged_conflicts": _items(flagged or []),
        "expected_merge_id": preview["merge_id"],
        "expected_before_fork_hash": preview["before_fork_hash"],
        "resolutions": resolutions or [],
        "acknowledge_fork_document_mutation": True,
        "acknowledge_conflicts": ack_conflicts,
        "operator_reviewer": "the-operator",
    }


# ── Proof 1: the round trip; the original is byte-identical ────────────────


def test_merge_round_trip_two_threads(api_env) -> None:
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    parent_hash_before = _sha(_body(db, "doc-parent"))
    [a1, a2] = _seed_thread(db, events, "inv-a", [
        "Alpha insight: the supply curve bends.",
        "Alpha's second insight stands alone.",
    ])
    [b1] = _seed_thread(db, events, "inv-b", ["Beta thread answers the open question."])
    client = _client()
    fork = _fork(client, "op-fork-1")

    pairs = [("inv-a", a1), ("inv-a", a2), ("inv-b", b1)]
    preview = client.post(PREVIEW, json={"fork_id": fork["fork_id"], "items": _items(pairs)})
    assert preview.status_code == 200, preview.text
    receipt = preview.json()
    assert receipt["status"] == "previewed"
    assert receipt["writes_performed"] is False
    assert receipt["conflicts"] == []  # zero-conflict merges pass preview
    assert receipt["before_fork_hash"] == _sha(_body(db, fork["fork_document_id"]))
    # The after-hash is honest: it recomputes against the would-be body.
    assert receipt["after_fork_hash"] != receipt["before_fork_hash"]
    assert receipt["fork_bytes_after"] > receipt["fork_bytes_before"]
    # Preview wrote nothing.
    assert _sha(_body(db, fork["fork_document_id"])) == receipt["before_fork_hash"]

    commit = client.post(COMMIT, json=_commit_body(fork["fork_id"], pairs, receipt))
    assert commit.status_code == 200, commit.text
    out = commit.json()
    assert out["status"] == "committed"
    assert out["writes_performed"] is True

    body = _body(db, fork["fork_document_id"])
    # Both threads' items land under provenance markers NAMING their threads.
    assert "Alpha insight: the supply curve bends." in body
    assert "Alpha's second insight stands alone." in body
    assert "Beta thread answers the open question." in body
    assert "from: investigation inv-a" in body
    assert "from: investigation inv-b" in body
    assert body.count("antiek-fork-merge-start") == 3
    assert _sha(body) == out["after_fork_hash"]

    # The ORIGINAL's body hash is byte-identical end-to-end.
    assert _sha(_body(db, "doc-parent")) == parent_hash_before

    # Commit idempotency: the same bound commit replays, never double-writes.
    replay = client.post(COMMIT, json=_commit_body(fork["fork_id"], pairs, receipt))
    assert replay.status_code == 200
    assert replay.json()["writes_performed"] is False
    assert replay.json()["commit_id"] == out["commit_id"]
    assert _sha(_body(db, fork["fork_document_id"])) == out["after_fork_hash"]


# ── Proof 2: the forced conflict — refused unresolved, audited resolved ─────


def _forced_conflict_setup(api_env):
    """One fork, two threads, the operator flag forcing a conflict on b1."""
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [a1] = _seed_thread(db, events, "inv-a", ["The passage says the rate rose."])
    [b1] = _seed_thread(db, events, "inv-b", ["The passage says the rate FELL."])
    client = _client()
    fork = _fork(client, "op-fork-conflict")
    pairs = [("inv-a", a1), ("inv-b", b1)]
    flagged = [("inv-b", b1)]
    preview = client.post(
        PREVIEW,
        json={
            "fork_id": fork["fork_id"],
            "items": _items(pairs),
            "flagged_conflicts": _items(flagged),
        },
    )
    assert preview.status_code == 200, preview.text
    return db, client, fork, pairs, flagged, b1, preview.json()


def test_forced_conflict_listed_and_refused_unresolved(api_env) -> None:
    db, client, fork, pairs, flagged, b1, receipt = _forced_conflict_setup(api_env)

    # Preview LISTS the conflict.
    conflicts = receipt["conflicts"]
    assert [c["kind"] for c in conflicts] == ["operator_flag"]
    assert conflicts[0]["item_refs"] == [["inv-b", b1]]

    # The conflict-ack gate keys on the real preview, not the client's flag.
    no_ack = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], pairs, receipt, flagged=flagged,
                          ack_conflicts=False),
    )
    assert no_ack.status_code == 409
    assert "conflicts_acknowledgement_required" in no_ack.json()["detail"]

    # Commit without a resolution is REFUSED — 409, no partial write.
    before = _body(db, fork["fork_document_id"])
    refused = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], pairs, receipt, flagged=flagged),
    )
    assert refused.status_code == 409
    assert "fork_merge_unresolved_conflicts" in refused.json()["detail"]
    assert f"inv-b/{b1}" in refused.json()["detail"]
    assert _body(db, fork["fork_document_id"]) == before


def test_forced_conflict_accept_lands_and_audits(api_env) -> None:
    db, client, fork, pairs, flagged, b1, receipt = _forced_conflict_setup(api_env)
    commit = client.post(
        COMMIT,
        json=_commit_body(
            fork["fork_id"],
            pairs,
            receipt,
            flagged=flagged,
            resolutions=[
                {"investigation_id": "inv-b", "node_id": b1, "choice": "accept"}
            ],
        ),
    )
    assert commit.status_code == 200, commit.text
    body = _body(db, fork["fork_document_id"])
    assert "The passage says the rate FELL." in body  # the incoming claim landed
    assert "from: investigation inv-b" in body

    # The audit row: the choice, the item ref, the conflict ref, the operator.
    con = connect_read(db)
    try:
        rows = con.execute(
            "SELECT investigation_id, node_id, choice, conflict_refs_json, "
            "operator_reviewer, commit_id FROM fork_merge_resolutions"
        ).fetchall()
    finally:
        con.close()
    assert len(rows) == 1
    iid, nid, choice, refs_json, reviewer, commit_id = rows[0]
    assert (iid, nid, choice, reviewer) == ("inv-b", b1, "accept", "the-operator")
    assert json.loads(refs_json) == [receipt["conflicts"][0]["conflict_id"]]
    assert commit_id == commit.json()["commit_id"]


def test_forced_conflict_keep_fork_leaves_the_passage_and_audits(api_env) -> None:
    db, client, fork, pairs, flagged, b1, receipt = _forced_conflict_setup(api_env)
    before = _body(db, fork["fork_document_id"])
    commit = client.post(
        COMMIT,
        json=_commit_body(
            fork["fork_id"],
            pairs,
            receipt,
            flagged=flagged,
            resolutions=[
                {"investigation_id": "inv-b", "node_id": b1, "choice": "keep_fork"}
            ],
        ),
    )
    assert commit.status_code == 200, commit.text
    body = _body(db, fork["fork_document_id"])
    # The conflicting claim is refused; the non-conflicted item still merged.
    assert "The passage says the rate FELL." not in body
    assert "The passage says the rate rose." in body
    assert body != before  # the accepted half still landed
    con = connect_read(db)
    try:
        row = con.execute(
            "SELECT choice FROM fork_merge_resolutions LIMIT 1"
        ).fetchone()
    finally:
        con.close()
    assert row[0] == "keep_fork"  # audited anyway


# ── Proof 3: anchor-based detection, and the honest degradation ─────────────


def test_anchor_detection_lists_differing_hash(api_env) -> None:
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [a1] = _seed_thread(db, events, "inv-a", ["An unrelated insight."])
    [b1] = _seed_thread(db, events, "inv-b", ["The passage says the rate FELL."])
    client = _client()
    fork = _fork(client, "op-fork-anchor")
    fork_doc = fork["fork_document_id"]

    # The passage pinned on the fork, linked to inv-b: the SAME thread now
    # asserts a DIFFERENT text over it — auto-listed.
    _pin_anchor(
        db,
        fork_doc,
        passage="The pinned passage stands here.",
        investigation_id="inv-b",
    )
    preview = client.post(
        PREVIEW,
        json={"fork_id": fork["fork_id"], "items": _items([("inv-a", a1), ("inv-b", b1)])},
    )
    assert preview.status_code == 200, preview.text
    conflicts = preview.json()["conflicts"]
    assert [c["kind"] for c in conflicts] == ["anchor_passage"]
    assert conflicts[0]["item_refs"] == [["inv-b", b1]]
    assert conflicts[0]["anchor_id"] is not None

    # The degradation, asserted: with NO anchor linked, the same selection
    # lists nothing (only (a)/(c) fire — a pinned passage hash matching the
    # item is a restatement, not a conflict).
    fork2 = _fork(client, "op-fork-anchor-2")
    _pin_anchor(
        db,
        fork2["fork_document_id"],
        passage="The pinned passage stands here.",
        investigation_id=None,  # pinned, but no thread link
    )
    clean = client.post(
        PREVIEW,
        json={"fork_id": fork2["fork_id"], "items": _items([("inv-a", a1), ("inv-b", b1)])},
    )
    assert clean.status_code == 200
    assert clean.json()["conflicts"] == []

    # And a restatement (the item's text IS the pinned passage) never lists.
    [b_same] = _seed_thread(db, events, "inv-c", ["The pinned passage stands here."])
    fork3 = _fork(client, "op-fork-anchor-3")
    _pin_anchor(
        db,
        fork3["fork_document_id"],
        passage="The pinned passage stands here.",
        investigation_id="inv-c",
    )
    restatement = client.post(
        PREVIEW,
        json={"fork_id": fork3["fork_id"], "items": _items([("inv-c", b_same)])},
    )
    assert restatement.status_code == 200
    assert restatement.json()["conflicts"] == []


def test_cross_member_pair_detection(api_env) -> None:
    """Ladder rung (a): the same claim text surfacing in TWO threads is
    listed — compose's pair model retargeted to items."""
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [s1] = _seed_thread(db, events, "inv-a", ["Both threads reached the same claim."])
    _claim_in_thread(events, "inv-b", s1, "Both threads reached the same claim.")
    client = _client()
    fork = _fork(client, "op-fork-pair")
    preview = client.post(
        PREVIEW,
        json={"fork_id": fork["fork_id"], "items": _items([("inv-a", s1), ("inv-b", s1)])},
    )
    assert preview.status_code == 200
    conflicts = preview.json()["conflicts"]
    assert [c["kind"] for c in conflicts] == ["cross_member_pair"]
    assert conflicts[0]["item_refs"] == [["inv-a", s1], ["inv-b", s1]]


# ── Proof 4: a withheld-source item merges only its own text ────────────────


def test_withheld_source_item_merges_only_its_own_text(api_env) -> None:
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    # A non-servable document whose body must NEVER leak into the fork.
    _seed_book(
        db,
        "doc-withheld",
        title="Withheld",
        raw_text="SECRET WITHHELD BODY — never merged",
        content_class="personal_reading",
    )
    [w1] = _seed_thread(
        db,
        events,
        "inv-w",
        ["The gated book's thesis, as the artifact lawfully showed it."],
        source_document_id="doc-withheld",
    )
    client = _client()
    fork = _fork(client, "op-fork-withheld")
    pairs = [("inv-w", w1)]
    preview = client.post(PREVIEW, json={"fork_id": fork["fork_id"], "items": _items(pairs)})
    assert preview.status_code == 200, preview.text
    assert "SECRET WITHHELD BODY" not in json.dumps(preview.json())
    commit = client.post(COMMIT, json=_commit_body(fork["fork_id"], pairs, preview.json()))
    assert commit.status_code == 200, commit.text
    body = _body(db, fork["fork_document_id"])
    assert "The gated book's thesis, as the artifact lawfully showed it." in body
    assert "SECRET WITHHELD BODY" not in body


# ── Proof 5: audit completeness against the commit ledger ───────────────────


def test_audit_completeness_recomputes(api_env) -> None:
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [s1] = _seed_thread(db, events, "inv-a", ["Shared claim, said once."])
    _claim_in_thread(events, "inv-b", s1, "Shared claim, said once.")
    [b2] = _seed_thread(db, events, "inv-b", ["Beta's own extra note."])
    client = _client()
    fork = _fork(client, "op-fork-audit")
    pairs = [("inv-a", s1), ("inv-b", s1), ("inv-b", b2)]
    flagged = [("inv-b", b2)]
    preview = client.post(
        PREVIEW,
        json={
            "fork_id": fork["fork_id"],
            "items": _items(pairs),
            "flagged_conflicts": _items(flagged),
        },
    ).json()
    # Two conflicts: the pair (a-side, b-side of the shared claim) and the
    # flag on b2 → three conflicted items, three resolutions, three rows.
    conflicted = sorted({tuple(ref) for c in preview["conflicts"] for ref in c["item_refs"]})
    assert conflicted == [("inv-a", s1), ("inv-b", b2), ("inv-b", s1)]
    resolutions = [
        {"investigation_id": iid, "node_id": nid, "choice": choice}
        for (iid, nid), choice in {
            ("inv-a", s1): "accept",
            ("inv-b", s1): "keep_fork",
            ("inv-b", b2): "skip",
        }.items()
    ]
    commit = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], pairs, preview, flagged=flagged,
                          resolutions=resolutions),
    )
    assert commit.status_code == 200, commit.text
    commit_id = commit.json()["commit_id"]

    con = connect_read(db)
    try:
        ledger = con.execute(
            "SELECT conflicts_json, resolutions_json, after_fork_hash, "
            "before_fork_body FROM fork_merge_commits WHERE commit_id = ?",
            [commit_id],
        ).fetchone()
        audit = con.execute(
            "SELECT investigation_id, node_id, choice, conflict_refs_json "
            "FROM fork_merge_resolutions WHERE commit_id = ? "
            "ORDER BY investigation_id, node_id",
            [commit_id],
        ).fetchall()
    finally:
        con.close()

    # Count + refs match, recomputed from the ledger.
    assert len(audit) == len(conflicted)
    by_ref = {(r[0], r[1]): r[2] for r in audit}
    assert by_ref == {
        ("inv-a", s1): "accept",
        ("inv-b", s1): "keep_fork",
        ("inv-b", b2): "skip",
    }
    ledger_conflict_ids = sorted(
        c["conflict_id"] for c in json.loads(ledger[0])
    )
    audit_conflict_ids = sorted(
        ref for row in audit for ref in json.loads(row[3])
    )
    # The pair conflict is audited on BOTH items' rows (each resolved it);
    # the flag on one. The multiset recomputes against the ledger's ids.
    pair_id = [c["conflict_id"] for c in json.loads(ledger[0]) if c["kind"] == "cross_member_pair"][0]
    flag_id = [c["conflict_id"] for c in json.loads(ledger[0]) if c["kind"] == "operator_flag"][0]
    assert audit_conflict_ids == sorted([pair_id, pair_id, flag_id])
    assert sorted(set(audit_conflict_ids)) == ledger_conflict_ids
    assert json.loads(ledger[1]) == resolutions
    # The ledger's after-hash recomputes against the stored fork body.
    assert ledger[2] == _sha(_body(db, fork["fork_document_id"]))
    # skip + keep_fork kept b2 and the b-side claim out; accept landed the
    # a-side once.
    body = _body(db, fork["fork_document_id"])
    assert body.count("Shared claim, said once.") == 1
    assert "Beta's own extra note." not in body


# ── The binding, staleness, ack and boundary proofs ──────────────────────────


def test_commit_binds_to_the_preview(api_env) -> None:
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [a1] = _seed_thread(db, events, "inv-a", ["A lonely insight."])
    [a2] = _seed_thread(db, events, "inv-a", ["A second insight, unselected."])
    client = _client()
    fork = _fork(client, "op-fork-bind")
    preview = client.post(
        PREVIEW, json={"fork_id": fork["fork_id"], "items": _items([("inv-a", a1)])}
    ).json()

    # A stale before-hash is a 409 (never a silent clobber).
    stale = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], [("inv-a", a1)], preview)
        | {"expected_before_fork_hash": "0" * 64},
    )
    assert stale.status_code == 409
    assert "fork_merge_stale" in stale.json()["detail"]

    # An edited selection no longer matches the bound merge id.
    edited = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], [("inv-a", a1), ("inv-a", a2)], preview),
    )
    assert edited.status_code == 409
    assert "fork_merge_preview_binding_mismatch" in edited.json()["detail"]

    # The fork-mutation ack is always required.
    no_ack = client.post(
        COMMIT,
        json=_commit_body(fork["fork_id"], [("inv-a", a1)], preview)
        | {"acknowledge_fork_document_mutation": False},
    )
    assert no_ack.status_code == 409
    assert "fork_merge_acknowledgement_required" in no_ack.json()["detail"]

    # Unknown item / unneeded resolution are honest 422s.
    unknown = client.post(
        PREVIEW,
        json={"fork_id": fork["fork_id"],
              "items": _items([("inv-a", a1), ("inv-a", "node-nope")])},
    )
    assert unknown.status_code == 422
    assert "fork_merge_item_unknown" in unknown.json()["detail"]
    unneeded = client.post(
        COMMIT,
        json=_commit_body(
            fork["fork_id"],
            [("inv-a", a1)],
            preview,
            resolutions=[
                {"investigation_id": "inv-a", "node_id": a1, "choice": "accept"}
            ],
        ),
    )
    assert unneeded.status_code == 422
    assert "fork_merge_resolution_unneeded" in unneeded.json()["detail"]


def test_merge_owner_boundary(api_env) -> None:
    """Another owner's fork is never a merge target: re-keyed lineage rows
    make preview and commit honest 404s."""
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [a1] = _seed_thread(db, events, "inv-a", ["A lonely insight."])
    client = _client()
    fork = _fork(client, "op-fork-owner")
    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute("UPDATE document_forks SET owner_user_id = 'someone-else'")
    assert (
        client.post(
            PREVIEW, json={"fork_id": fork["fork_id"], "items": _items([("inv-a", a1)])}
        ).status_code
        == 404
    )
    assert (
        client.post(
            COMMIT,
            json={
                "fork_id": fork["fork_id"],
                "items": _items([("inv-a", a1)]),
                "expected_merge_id": "x",
                "expected_before_fork_hash": "0" * 64,
                "acknowledge_fork_document_mutation": True,
            },
        ).status_code
        == 404
    )


def test_shipped_contracts_untouched(api_env) -> None:
    """The shipped-contract-integrity gate: the retired in-place merge stays
    retired (410), compose keeps its shape, and the fork-merge family adds
    exactly two paths — nothing hangs off compose."""
    client = _client()
    retired = client.post("/research/artifacts/source-merge/preview", json={})
    assert retired.status_code == 410
    retired = client.post("/research/artifacts/source-merge/commit", json={})
    assert retired.status_code == 410

    app = create_app(register_wrestling=False)
    fork_merge_paths = sorted(
        {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set()) or set()
            if "fork-merge" in route.path
        }
    )
    assert fork_merge_paths == [
        ("/research/artifacts/fork-merge/commit", "POST"),
        ("/research/artifacts/fork-merge/preview", "POST"),
    ]
    compose_paths = sorted(
        {
            (route.path, method)
            for route in app.routes
            for method in getattr(route, "methods", set()) or set()
            if "compose" in route.path
        }
    )
    assert all("fork" not in path for path, _ in compose_paths)


# The fork may become unservable after creation or after a successful preview.
# These fixtures model stored rights drift without weakening the write-time guard.
_BODY_REFUSALS = [
    pytest.param("user_owned", "http://creativecommons.org/licenses/by-nc/4.0/", "2601.00001", False, False, "T2", "license_tier_blocked", id="t2-class-drift"),
    pytest.param("user_owned", "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "2601.00001", False, False, "T3", "license_tier_blocked", id="t3-class-drift"),
    pytest.param("personal_reading", "http://creativecommons.org/licenses/by-nc/4.0/", "2601.00001", False, False, "T2", "license_tier_blocked", id="t2-owner-path"),
    pytest.param("personal_reading", "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "2601.00001", False, False, "T3", "license_tier_blocked", id="t3-owner-path"),
    pytest.param("restricted_pending_opt_in", "http://arxiv.org/licenses/nonexclusive-distrib/1.0/", "2601.00001", False, False, "T3", "gated_metadata_only", id="content-class-withheld"),
    pytest.param(None, None, None, False, False, "none", "gated_metadata_only", id="unknown-content-class"),
    pytest.param("user_owned", "http://creativecommons.org/licenses/by/4.0/", None, False, False, "T1", "link_back_missing", id="missing-link-back"),
    pytest.param("user_owned", None, None, True, False, "none", "taken_down", id="taken-down"),
    pytest.param("user_owned", None, None, False, True, "none", "body_missing", id="null-body"),
]


def _merge_storage_state(db: str, events: str) -> tuple:
    from pathlib import Path

    with connect_read(db) as con:
        documents = con.execute(
            "SELECT document_id, raw_text, metadata, content_class FROM documents "
            "ORDER BY document_id"
        ).fetchall()
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
        ledger = {
            table: con.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
            if table in tables else []
            for table in ("fork_merge_commits", "fork_merge_resolutions")
        }
    logs = {
        str(path.relative_to(events)): path.read_bytes()
        for path in Path(events).rglob("*") if path.is_file()
    }
    return documents, ledger, logs


@pytest.mark.parametrize("endpoint", [PREVIEW, COMMIT], ids=["preview", "commit"])
@pytest.mark.parametrize(
    "content_class,license_uri,arxiv_id,taken_down,null_body,tier,reason",
    _BODY_REFUSALS,
)
def test_merge_body_gate_refuses_without_writes(
    api_env, endpoint, content_class, license_uri, arxiv_id,
    taken_down, null_body, tier, reason,
) -> None:
    db, events = api_env["db"], api_env["events"]
    original = "PRIVATE FORK BODY SENTINEL. " * 40
    _seed_book(db, raw_text=original)
    [node] = _seed_thread(db, events, "inv-gate", ["A selected, lawful outcome."])
    client = _client()
    fork = _fork(client, "op-body-gate")
    pairs = [("inv-gate", node)]
    preview_request = {"fork_id": fork["fork_id"], "items": _items(pairs)}
    allowed = client.post(PREVIEW, json=preview_request)
    assert allowed.status_code == 200, allowed.text
    assert "PRIVATE FORK BODY SENTINEL" not in allowed.text
    metadata = {"private_holder_note": "DO NOT ECHO HOLDER DETAIL"}
    if license_uri is not None:
        metadata["license_uri"] = license_uri
    if arxiv_id is not None:
        metadata["arxiv_id"] = arxiv_id
    with connect_write(db, purpose="test/fork-rights-drift") as con:
        con.execute(
            "UPDATE documents SET content_class = ?, metadata = ?, raw_text = ? "
            "WHERE document_id = ?",
            [content_class, json.dumps(metadata), None if null_body else original,
             fork["fork_document_id"]],
        )
        if taken_down:
            con.execute(
                "UPDATE book_assets SET taken_down = TRUE WHERE document_id = ?",
                [fork["fork_document_id"]],
            )
    before = _merge_storage_state(db, events)
    request = preview_request if endpoint == PREVIEW else _commit_body(
        fork["fork_id"], pairs, allowed.json()
    )
    refused = client.post(endpoint, json=request)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == (
        f"fork_merge_body_unavailable: document={fork['fork_document_id']}; "
        f"tier={tier}; reason={reason}"
    )
    assert "PRIVATE FORK BODY SENTINEL" not in refused.text
    assert "DO NOT ECHO HOLDER DETAIL" not in refused.text
    assert db not in refused.text
    assert _merge_storage_state(db, events) == before


@pytest.mark.parametrize(
    "content_class,license_uri,body",
    [
        pytest.param("source_declared_open", "http://creativecommons.org/licenses/by/4.0/", "Allowed T1 body.", id="t1"),
        pytest.param("personal_reading", None, "Owner's personal body.", id="non-arxiv-owner"),
        pytest.param("user_owned", None, "", id="empty-not-withheld"),
    ],
)
def test_merge_body_gate_preserves_allowed_bodies(api_env, content_class, license_uri, body):
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [node] = _seed_thread(db, events, "inv-allowed", ["Permitted appended outcome."])
    client = _client()
    fork = _fork(client, "op-allowed-body")
    metadata = {"license_uri": license_uri, "arxiv_id": "2601.00001"} if license_uri else {}
    with connect_write(db, purpose="test/allowed-fork-body") as con:
        con.execute(
            "UPDATE documents SET content_class = ?, metadata = ?, raw_text = ? "
            "WHERE document_id = ?",
            [content_class, json.dumps(metadata), body, fork["fork_document_id"]],
        )
    pairs = [("inv-allowed", node)]
    preview = client.post(PREVIEW, json={"fork_id": fork["fork_id"], "items": _items(pairs)})
    assert preview.status_code == 200, preview.text
    assert preview.json()["before_fork_hash"] == _sha(body)
    commit = client.post(COMMIT, json=_commit_body(fork["fork_id"], pairs, preview.json()))
    assert commit.status_code == 200, commit.text
    stored = _body(db, fork["fork_document_id"])
    assert stored.startswith(body)
    assert "Permitted appended outcome." in stored
    assert _sha(stored) == commit.json()["after_fork_hash"]


@pytest.mark.parametrize("operation", ["preview", "commit"])
def test_merge_body_gate_has_a_typed_substrate_refusal(api_env, operation):
    from substrate.research_artifact.fork_merge import commit_fork_merge, preview_fork_merge

    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [node] = _seed_thread(db, events, "inv-typed", ["A lawful outcome."])
    client = _client()
    fork = _fork(client, "op-typed-refusal")
    pairs = [("inv-typed", node)]
    preview = client.post(PREVIEW, json={"fork_id": fork["fork_id"], "items": _items(pairs)})
    assert preview.status_code == 200, preview.text
    with connect_write(db, purpose="test/typed-refusal") as con:
        con.execute(
            "UPDATE documents SET metadata = ? WHERE document_id = ?",
            [json.dumps({"license_uri": "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
                         "arxiv_id": "2601.00001"}), fork["fork_document_id"]],
        )
        kwargs = dict(owner_user_id="__operator__", fork_id=fork["fork_id"],
                      item_refs=pairs, events_dir=events)
        before = con.execute("SELECT raw_text FROM documents WHERE document_id = ?", [fork["fork_document_id"]]).fetchone()
        with pytest.raises(ValueError, match="fork_merge_body_unavailable") as refused:
            if operation == "preview":
                preview_fork_merge(con, **kwargs)
            else:
                commit_fork_merge(
                    con, **kwargs, resolutions=[],
                    expected_merge_id=preview.json()["merge_id"],
                    expected_before_fork_hash=preview.json()["before_fork_hash"],
                )
        assert type(refused.value).__name__ == "ForkMergeBodyUnavailableError"
        assert refused.value.document_id == fork["fork_document_id"]
        assert refused.value.tier == "T3"
        assert refused.value.reason == "license_tier_blocked"
        assert con.execute("SELECT raw_text FROM documents WHERE document_id = ?", [fork["fork_document_id"]]).fetchone() == before


@pytest.mark.parametrize("endpoint", [PREVIEW, COMMIT])
def test_merge_body_gate_preserves_document_owner_boundary(api_env, endpoint):
    db, events = api_env["db"], api_env["events"]
    _seed_book(db)
    [node] = _seed_thread(db, events, "inv-owner", ["A lawful outcome."])
    client = _client()
    fork = _fork(client, "op-document-owner")
    pairs = [("inv-owner", node)]
    payload = {"fork_id": fork["fork_id"], "items": _items(pairs)}
    preview = client.post(PREVIEW, json=payload)
    assert preview.status_code == 200, preview.text
    with connect_write(db, purpose="test/document-owner-drift") as con:
        con.execute(
            "UPDATE documents SET owner_user_id = 'another-owner' WHERE document_id = ?",
            [fork["fork_document_id"]],
        )
    before = _merge_storage_state(db, events)
    response = client.post(endpoint, json=payload if endpoint == PREVIEW else
                           _commit_body(fork["fork_id"], pairs, preview.json()))
    assert response.status_code == 404, response.text
    assert response.json()["detail"] == "fork_not_found"
    assert _merge_storage_state(db, events) == before
