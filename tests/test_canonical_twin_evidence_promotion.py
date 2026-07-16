from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, replace

import duckdb
import pytest
from nacl.signing import SigningKey
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_canonical_twin_publication import _graph, _ready_parent

from runtime.db_lock import LockedConnection
from substrate.graph.ops import insert_chunk, insert_document, update_document_gate_columns
from substrate.twin_recursion import (
    EvidenceExcerptRequest,
    TwinEvidencePromotionError,
    TwinEvidencePromotionLedger,
    TwinPromotionReview,
    issue_owner_review_authorization,
    publish_canonical_twin,
)


def _setup(completed_parent, *, owner: str = "acct", content_class: str | None = None):
    twins, snapshot, tmp_path = _ready_parent(completed_parent)
    graph = _graph(tmp_path / "promotion-graph.duckdb")
    publication = publish_canonical_twin(graph, twins, binding_id=snapshot.binding_id)
    evidence_text = "The source record establishes the exact supported fact and its context."
    insert_document(
        graph,
        document_id="evidence-document",
        source_tier=1,
        document_type="research_source",
        title="Evidence source",
        raw_text=evidence_text,
        content_class=content_class or ("user_owned" if owner == "acct" else "personal_reading"),
        owner_user_id=owner,
    )
    evidence_chunk = insert_chunk(
        graph,
        document_id="evidence-document",
        chunk_index=0,
        text=evidence_text,
        section_path="Evidence",
        chunk_id="evidence-chunk",
    )
    signing = SigningKey.generate()
    authority = TwinEvidencePromotionLedger(
        tmp_path / "promotion.sqlite3",
        owner_id="acct",
        review_verify_key=bytes(signing.verify_key),
        clock=lambda: 100,
    )
    request = EvidenceExcerptRequest("evidence-document", evidence_chunk, 4, 44)
    return twins, snapshot, graph, publication, authority, request, bytes(signing)


def _digest(candidate) -> str:  # type: ignore[no-untyped-def]
    payload = json.dumps(
        asdict(candidate), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _stage(authority, graph, twins, snapshot, request, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "owner_id": "acct",
        "source_asset_id": "oversized",
        "source_hash": snapshot.source_hash,
        "kind": "insight",
        "text": "Insight parent",
        "evidence": (request,),
    }
    values.update(overrides)
    return authority.stage(graph, twins, **values)


def _authorization(candidate, signing, **overrides):  # type: ignore[no-untyped-def]
    values = {
        "owner_id": "acct",
        "candidate_id": candidate.candidate_id,
        "candidate_digest": _digest(candidate),
        "decision": "accepted",
        "rationale": "The excerpt directly supports this candidate.",
        "issued_at_unix": 90,
        "expires_at_unix": 110,
        "nonce": "review-once",
    }
    values.update(overrides)
    return issue_owner_review_authorization(signing, **values)


def test_exact_insight_acceptance_is_replayable_authority_without_graph_mutation(
    completed_parent,
) -> None:
    twins, snapshot, graph, publication, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        assert _stage(authority, graph, twins, snapshot, request) == candidate
        assert candidate.twin_document_id == publication.document_id
        assert candidate.evidence[0].text == "source record establishes the exact supp"
        review = authority.decide(
            graph,
            twins,
            authorization=_authorization(candidate, signing),
        )
        replay = authority.decide(
            graph,
            twins,
            authorization=_authorization(candidate, signing),
        )
        accepted = authority.accepted(
            graph, twins, owner_id="acct", candidate_id=candidate.candidate_id
        )
        assert replay == review == accepted.review
        assert accepted.candidate == candidate
        assert accepted.authority == "owner_reviewed_evidence_bound_candidate_v1"
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
        assert graph.execute("SELECT count(*) FROM edges").fetchone() == (0,)
        authority.verify_integrity()
    finally:
        graph.close()


def test_question_can_be_rejected_but_rejection_is_terminal(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(
            authority,
            graph,
            twins,
            snapshot,
            request,
            kind="question",
            text="Question parent?",
        )
        authority.decide(
            graph,
            twins,
            authorization=_authorization(
                candidate,
                signing,
                decision="rejected",
                rationale="The cited excerpt does not answer this question.",
            ),
        )
        with pytest.raises(TwinEvidencePromotionError, match="accepted.*unavailable"):
            authority.accepted(graph, twins, owner_id="acct", candidate_id=candidate.candidate_id)
        with pytest.raises(TwinEvidencePromotionError, match="another review"):
            authority.decide(
                graph,
                twins,
                authorization=_authorization(
                    candidate,
                    signing,
                    rationale="A later caller tried to reverse the decision.",
                    nonce="second-review",
                ),
            )
    finally:
        graph.close()


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("insight", "Synthesis parent"),
        ("insight", "Proposed insight: Insight parent"),
        ("question", "Insight parent"),
        ("finding", "Insight parent"),
    ],
)
def test_synthesis_labels_and_cross_kind_text_cannot_mint_candidates(
    completed_parent, kind, text
) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="not promotable|not one unique"):
            _stage(
                authority,
                graph,
                twins,
                snapshot,
                request,
                kind=kind,
                text=text,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_self_citation_and_foreign_private_evidence_are_refused(completed_parent) -> None:
    twins, snapshot, graph, publication, authority, request, _ = _setup(
        completed_parent, owner="other"
    )
    try:
        with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
            _stage(authority, graph, twins, snapshot, request)
        twin_request = EvidenceExcerptRequest(publication.document_id, publication.chunk_id, 0, 10)
        with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
            _stage(authority, graph, twins, snapshot, twin_request)
    finally:
        graph.close()


def test_excerpt_drift_blocks_review_and_current_accepted_authority(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        graph.execute(
            "UPDATE chunks SET text='substituted evidence' WHERE chunk_id='evidence-chunk'"
        )
        with pytest.raises(TwinEvidencePromotionError, match="changed|unavailable"):
            authority.decide(
                graph,
                twins,
                authorization=_authorization(
                    candidate,
                    signing,
                    rationale="This must not commit after evidence drift.",
                ),
            )
        graph.execute(
            "UPDATE chunks SET text=? WHERE chunk_id='evidence-chunk'",
            ["The source record establishes the exact supported fact and its context."],
        )
        authority.decide(
            graph,
            twins,
            authorization=_authorization(
                candidate, signing, rationale="Current evidence is exact."
            ),
        )
        graph.execute("DELETE FROM chunks WHERE chunk_id='evidence-chunk'")
        with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
            authority.accepted(graph, twins, owner_id="acct", candidate_id=candidate.candidate_id)
    finally:
        graph.close()


def test_owner_and_candidate_digest_are_review_authority(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        for owner, digest in (("other", _digest(candidate)), ("acct", "0" * 64)):
            with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
                authority.decide(
                    graph,
                    twins,
                    authorization=_authorization(
                        candidate,
                        signing,
                        owner_id=owner,
                        candidate_digest=digest,
                        rationale="Forged review authority.",
                    ),
                )
    finally:
        graph.close()


def test_schema_and_append_only_history_tampering_fail_integrity(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        _stage(authority, graph, twins, snapshot, request)
        raw = sqlite3.connect(authority.path)
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            raw.execute("UPDATE promotion_candidates SET owner_id='other'")
        raw.execute("DROP TRIGGER promotion_events_no_update")
        raw.commit()
        raw.close()
        with pytest.raises(TwinEvidencePromotionError, match="objects changed"):
            authority.verify_integrity()
    finally:
        graph.close()


def test_unsigned_expired_and_control_label_reviews_are_refused(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="control"):
            _stage(
                authority,
                graph,
                twins,
                snapshot,
                request,
                text="Insight parent\nProposed synthesis: escaped",
            )
        candidate = _stage(authority, graph, twins, snapshot, request)
        valid = _authorization(candidate, signing)
        for forged in (
            replace(valid, signature="00" * 64),
            _authorization(candidate, signing, issued_at_unix=1, expires_at_unix=2),
        ):
            with pytest.raises(TwinEvidencePromotionError, match="invalid"):
                authority.decide(graph, twins, authorization=forged)
    finally:
        graph.close()


def test_direct_projection_insert_without_review_event_is_not_authority(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        authorization = _authorization(
            candidate, signing, rationale="signed projection without event"
        )
        identity = asdict(authorization)
        review_id = (
            "twin-review-"
            + hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        review = TwinPromotionReview(
            review_id,
            authorization.candidate_id,
            authorization.owner_id,
            authorization.decision,
            authorization.rationale,
            authorization.candidate_digest,
            authorization.issued_at_unix,
            authorization.expires_at_unix,
            authorization.nonce,
            authorization.key_id,
            authorization.signature,
        )
        raw = sqlite3.connect(authority.path)
        raw.execute(
            "INSERT INTO promotion_reviews VALUES (?,?,?,?,?,?)",
            [
                review_id,
                candidate.candidate_id,
                "acct",
                "accepted",
                review.rationale,
                json.dumps(asdict(review), sort_keys=True, separators=(",", ":")),
            ],
        )
        raw.commit()
        raw.close()
        with pytest.raises(TwinEvidencePromotionError, match="review event projection changed"):
            authority.accepted(graph, twins, owner_id="acct", candidate_id=candidate.candidate_id)
        with pytest.raises(TwinEvidencePromotionError, match="projection changed"):
            authority.verify_integrity()
    finally:
        graph.close()


def test_takedown_and_rights_drift_revoke_evidence_freshness(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(
        completed_parent, owner="other", content_class="public_domain"
    )
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        graph.execute(
            "INSERT INTO book_assets(document_id,taken_down) VALUES ('evidence-document',TRUE)"
        )
        with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
            authority.decide(graph, twins, authorization=_authorization(candidate, signing))
        graph.execute("DELETE FROM book_assets WHERE document_id='evidence-document'")
        update_document_gate_columns(
            graph,
            "evidence-document",
            content_class="restricted_pending_opt_in",
            set_content_class=True,
        )
        with pytest.raises(TwinEvidencePromotionError, match="unavailable"):
            authority.decide(graph, twins, authorization=_authorization(candidate, signing))
    finally:
        graph.close()


def test_forged_review_and_matching_unkeyed_event_fail_signature(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        forged = replace(_authorization(candidate, signing), signature="00" * 64)
        identity = asdict(forged)
        review_id = (
            "twin-review-"
            + hashlib.sha256(
                json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
        )
        review = TwinPromotionReview(
            review_id,
            forged.candidate_id,
            forged.owner_id,
            forged.decision,
            forged.rationale,
            forged.candidate_digest,
            forged.issued_at_unix,
            forged.expires_at_unix,
            forged.nonce,
            forged.key_id,
            forged.signature,
        )
        payload = json.dumps(asdict(review), sort_keys=True, separators=(",", ":"))
        raw = sqlite3.connect(authority.path)
        previous = raw.execute(
            "SELECT event_hash FROM promotion_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]
        payload_sha = hashlib.sha256(payload.encode()).hexdigest()
        event_hash = hashlib.sha256(
            json.dumps(
                [2, "candidate_reviewed", review_id, payload_sha, previous],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        raw.execute(
            "INSERT INTO promotion_reviews VALUES (?,?,?,?,?,?)",
            [review_id, candidate.candidate_id, "acct", "accepted", review.rationale, payload],
        )
        raw.execute(
            "INSERT INTO promotion_events VALUES (?,?,?,?,?,?,?)",
            [2, "candidate_reviewed", review_id, payload, payload_sha, previous, event_hash],
        )
        raw.commit()
        raw.close()
        with pytest.raises(TwinEvidencePromotionError, match="signature is invalid"):
            authority.accepted(graph, twins, owner_id="acct", candidate_id=candidate.candidate_id)
        with pytest.raises(TwinEvidencePromotionError, match="signature is invalid"):
            authority.verify_integrity()
    finally:
        graph.close()


def test_signed_review_with_rewritten_id_fails_full_integrity(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        authorization = _authorization(candidate, signing)
        review_id = "twin-review-" + "0" * 64
        review = TwinPromotionReview(
            review_id,
            authorization.candidate_id,
            authorization.owner_id,
            authorization.decision,
            authorization.rationale,
            authorization.candidate_digest,
            authorization.issued_at_unix,
            authorization.expires_at_unix,
            authorization.nonce,
            authorization.key_id,
            authorization.signature,
        )
        payload = json.dumps(asdict(review), sort_keys=True, separators=(",", ":"))
        raw = sqlite3.connect(authority.path)
        previous = raw.execute(
            "SELECT event_hash FROM promotion_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()[0]
        payload_sha = hashlib.sha256(payload.encode()).hexdigest()
        event_hash = hashlib.sha256(
            json.dumps(
                [2, "candidate_reviewed", review_id, payload_sha, previous],
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        raw.execute(
            "INSERT INTO promotion_reviews VALUES (?,?,?,?,?,?)",
            [review_id, candidate.candidate_id, "acct", "accepted", review.rationale, payload],
        )
        raw.execute(
            "INSERT INTO promotion_events VALUES (?,?,?,?,?,?,?)",
            [2, "candidate_reviewed", review_id, payload, payload_sha, previous, event_hash],
        )
        raw.commit()
        raw.close()
        with pytest.raises(TwinEvidencePromotionError, match="review projection changed"):
            authority.verify_integrity()
    finally:
        graph.close()


def test_nominal_locked_connection_with_wrong_descriptor_is_refused(
    completed_parent, tmp_path
) -> None:
    twins, snapshot, graph, _, authority, request, _ = _setup(completed_parent)
    graph.close()
    first = tmp_path / "first.lock"
    second = tmp_path / "second.lock"
    fd = os.open(first, os.O_CREAT | os.O_WRONLY, 0o600)
    second.touch()
    forged = LockedConnection(
        duckdb.connect(str(tmp_path / "forged.duckdb")),
        fd,
        str(second),
        db_path=str(tmp_path / "forged.duckdb"),
    )
    try:
        with pytest.raises(TwinEvidencePromotionError, match="active graph write lock"):
            _stage(authority, forged, twins, snapshot, request)
    finally:
        forged.close()


def test_self_consistent_locked_connection_for_wrong_database_is_refused(
    completed_parent, tmp_path
) -> None:
    twins, snapshot, graph, _, authority, request, _ = _setup(completed_parent)
    graph.close()
    forged_db = str(tmp_path / "forged.duckdb")
    claimed_db = str(tmp_path / "claimed.duckdb")
    lock_path = claimed_db + ".write.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    forged = LockedConnection(
        duckdb.connect(forged_db),
        fd,
        lock_path,
        db_path=claimed_db,
    )
    try:
        with pytest.raises(TwinEvidencePromotionError, match="active graph write lock"):
            _stage(authority, forged, twins, snapshot, request)
    finally:
        forged.close()


def test_matching_but_unlocked_public_wrapper_is_not_coordinator_authority(
    completed_parent,
) -> None:
    twins, snapshot, graph, _, authority, request, _ = _setup(completed_parent)
    graph_path = graph.execute("PRAGMA database_list").fetchone()[2]
    graph.close()
    lock_path = graph_path + ".write.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_WRONLY, 0o600)
    forged = LockedConnection(duckdb.connect(graph_path), fd, lock_path, db_path=graph_path)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="active graph write lock"):
            _stage(authority, forged, twins, snapshot, request)
    finally:
        forged.close()


def test_ledger_pins_owner_and_review_key_identity(completed_parent) -> None:
    _, _, graph, _, authority, _, signing = _setup(completed_parent)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="metadata changed"):
            TwinEvidencePromotionLedger(
                authority.path,
                owner_id="victim",
                review_verify_key=bytes(SigningKey(signing).verify_key),
                clock=lambda: 100,
            )
        with pytest.raises(TwinEvidencePromotionError, match="metadata changed"):
            TwinEvidencePromotionLedger(
                authority.path,
                owner_id="acct",
                review_verify_key=bytes(SigningKey.generate().verify_key),
                clock=lambda: 100,
            )
    finally:
        graph.close()


def test_accepted_requires_the_complete_valid_event_chain(completed_parent) -> None:
    twins, snapshot, graph, _, authority, request, signing = _setup(completed_parent)
    try:
        candidate = _stage(authority, graph, twins, snapshot, request)
        authority.decide(graph, twins, authorization=_authorization(candidate, signing))
        raw = sqlite3.connect(authority.path)
        trigger_sql = raw.execute(
            "SELECT sql FROM sqlite_master WHERE name='promotion_events_no_update'"
        ).fetchone()[0]
        raw.execute("DROP TRIGGER promotion_events_no_update")
        raw.execute("UPDATE promotion_events SET event_hash=? WHERE sequence=1", ["0" * 64])
        raw.execute(trigger_sql)
        raw.commit()
        raw.close()
        with pytest.raises(TwinEvidencePromotionError, match="event chain changed"):
            authority.accepted(graph, twins, owner_id="acct", candidate_id=candidate.candidate_id)
    finally:
        graph.close()
