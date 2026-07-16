from __future__ import annotations

# ruff: noqa: F811 - pytest fixture is intentionally imported.
import json
import os
import shutil
from dataclasses import replace

import pytest
from test_canonical_aggregate_projection import completed_parent  # noqa: F401
from test_canonical_twin_evidence_promotion import _authorization, _setup, _stage

import substrate.twin_recursion.promotion_writer as promotion_writer
from substrate.graph.insight_question import insight_node_id, question_node_id
from substrate.twin_recursion import (
    CanonicalTwinPromotionWriterError,
    TwinEvidencePromotionError,
    materialize_accepted_twin_promotion,
)


def _accepted(completed_parent, *, kind: str = "insight"):
    twins, snapshot, graph, _, promotions, request, signing = _setup(completed_parent)
    text = "Insight parent" if kind == "insight" else "Question parent?"
    candidate = _stage(promotions, graph, twins, snapshot, request, kind=kind, text=text)
    promotions.decide(graph, twins, authorization=_authorization(candidate, signing))
    return twins, graph, promotions, candidate


def test_exact_insight_materializes_private_hash_only_node_and_replays(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    try:
        first = materialize_accepted_twin_promotion(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        second = materialize_accepted_twin_promotion(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert first == second
        assert first.node_id == insight_node_id(candidate.text, identity_scope="acct")
        row = graph.execute(
            "SELECT canonical_label,node_type,embedding,graph_scope,metadata,owner_user_id "
            "FROM nodes WHERE node_id=?",
            [first.node_id],
        ).fetchone()
        assert row[:4] == (candidate.text, "insight", None, "depth")
        assert row[5] == "acct"
        metadata = json.loads(row[4])
        assert metadata["candidate_id"] == candidate.candidate_id
        assert metadata["review_id"] == first.review_id
        assert metadata["evidence"][0]["chunk_id"] == candidate.evidence[0].chunk_id
        assert "text" not in metadata["evidence"][0]
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (1,)
        assert graph.execute("SELECT count(*) FROM edges").fetchone() == (0,)
    finally:
        graph.close()


def test_exact_question_uses_owner_scoped_question_identity(completed_parent) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent, kind="question")
    try:
        result = materialize_accepted_twin_promotion(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        assert result.node_id == question_node_id(candidate.text, identity_scope="acct")
        assert result.kind == "question"
        assert graph.execute(
            "SELECT node_type,owner_user_id FROM nodes WHERE node_id=?", [result.node_id]
        ).fetchone() == ("question", "acct")
        assert graph.execute("SELECT count(*) FROM edges").fetchone() == (0,)
    finally:
        graph.close()


def test_rejected_or_stale_authority_writes_nothing(completed_parent) -> None:
    twins, snapshot, graph, _, promotions, request, signing = _setup(completed_parent)
    try:
        rejected = _stage(promotions, graph, twins, snapshot, request)
        promotions.decide(
            graph,
            twins,
            authorization=_authorization(rejected, signing, decision="rejected"),
        )
        with pytest.raises(TwinEvidencePromotionError):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=rejected.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_evidence_drift_and_conflicting_existing_node_fail_before_commit(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    try:
        graph.execute("UPDATE chunks SET text='changed' WHERE chunk_id='evidence-chunk'")
        with pytest.raises(TwinEvidencePromotionError, match="evidence excerpt is unavailable"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_post_insert_revalidation_failure_rolls_back(completed_parent, monkeypatch) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    original = promotion_writer.promote_insight

    def fail_after_insert(**kwargs):  # type: ignore[no-untyped-def]
        original(**kwargs)
        raise TwinEvidencePromotionError("late authority loss")

    monkeypatch.setattr(promotion_writer, "promote_insight", fail_after_insert)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="late authority loss"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_snapshot_rejects_a_different_returned_review(completed_parent, monkeypatch) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    authority = promotions.accepted(
        graph, twins, owner_id="acct", candidate_id=candidate.candidate_id
    )
    swapped = replace(
        authority,
        review=replace(authority.review, review_id="twin-review-" + "0" * 64),
    )
    monkeypatch.setattr(type(promotions), "accepted", lambda *args, **kwargs: swapped)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="snapshot changed"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_snapshot_rejects_forged_authority_discriminator(completed_parent, monkeypatch) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    authority = promotions.accepted(
        graph, twins, owner_id="acct", candidate_id=candidate.candidate_id
    )
    forged = replace(authority, authority="forged")  # type: ignore[arg-type]
    monkeypatch.setattr(type(promotions), "accepted", lambda *args, **kwargs: forged)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="snapshot changed"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_promotion_database_path_replacement_rolls_back_graph(
    completed_parent, monkeypatch, tmp_path
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    replacement = tmp_path / "replacement.sqlite3"
    shutil.copy2(promotions.path, replacement)
    original = promotion_writer.promote_insight

    def replace_after_insert(**kwargs):  # type: ignore[no-untyped-def]
        node_id = original(**kwargs)
        os.replace(replacement, promotions.path)
        return node_id

    monkeypatch.setattr(promotion_writer, "promote_insight", replace_after_insert)
    try:
        with pytest.raises(TwinEvidencePromotionError, match="snapshot path changed"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (0,)
    finally:
        graph.close()


def test_later_takedown_blocks_replay_but_retains_historical_private_node(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    try:
        result = materialize_accepted_twin_promotion(
            graph,
            promotions,
            twins,
            owner_id="acct",
            candidate_id=candidate.candidate_id,
        )
        graph.execute(
            "INSERT INTO book_assets(document_id,taken_down) VALUES ('evidence-document',TRUE)"
        )
        with pytest.raises(TwinEvidencePromotionError, match="evidence excerpt is unavailable"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        row = graph.execute(
            "SELECT metadata,owner_user_id FROM nodes WHERE node_id=?", [result.node_id]
        ).fetchone()
        assert row[1] == "acct"
        metadata = json.loads(row[0])
        assert metadata["authority_temporality"] == "materialization_time"
        assert metadata["reuse_policy"] == "revalidate_promotion_authority_before_use"
    finally:
        graph.close()


def test_existing_owner_scoped_node_with_other_metadata_fails_closed(
    completed_parent,
) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    node_id = insight_node_id(candidate.text, identity_scope="acct")
    graph.execute(
        "INSERT INTO nodes(node_id,canonical_label,node_type,graph_scope,metadata,owner_user_id) "
        "VALUES (?,?,?,'depth','{}','acct')",
        [node_id, candidate.text, "insight"],
    )
    try:
        with pytest.raises(ValueError, match="private promoted graph node conflicts"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        assert graph.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [node_id]
        ).fetchone() == ("{}",)
        assert graph.execute("SELECT count(*) FROM nodes").fetchone() == (1,)
    finally:
        graph.close()


def test_writer_refuses_a_caller_owned_outer_transaction(completed_parent) -> None:
    twins, graph, promotions, candidate = _accepted(completed_parent)
    try:
        graph.execute("BEGIN")
        with pytest.raises(CanonicalTwinPromotionWriterError, match="ownership"):
            materialize_accepted_twin_promotion(
                graph,
                promotions,
                twins,
                owner_id="acct",
                candidate_id=candidate.candidate_id,
            )
        graph.execute("ROLLBACK")
    finally:
        graph.close()
