from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest

from substrate.multimedia.visual_candidate_materialization import materialize_visual_candidates
from substrate.multimedia.visual_candidate_review import (
    VisualCandidateReviewError,
    attest_visual_candidate,
    preview_visual_candidate,
)
from tests.test_multimedia_artifact_quarantine import PNG
from tests.test_multimedia_visual_authorization import KEY, _terms
from tests.test_multimedia_visual_candidate_materialization import (
    NOW,
    Resolver,
    Transport,
    _succeeded,
)

OPERATOR_KEY = b"o" * 32


def _candidate(tmp_path: Path):
    store, ready, registry, db, client, execution_id, quarantine = _succeeded(tmp_path)
    rows = materialize_visual_candidates(
        asset_id=ready.asset.asset_id, execution_id=execution_id,
        authority_request_id="visual-request-1", expected_revision_id=ready.asset.revision_id,
        owner_id="owner-1", store=store, registry=registry, terms=_terms(),
        db_path=db, signing_key=KEY, client=client, resolver=Resolver(),
        transport=Transport(), allowlisted_hosts=frozenset({"assets.example"}),
        quarantine_dir=str(quarantine), now=NOW,
    )
    return store, ready, db, rows[0].candidate_id


def test_preview_returns_exact_verified_bytes_and_no_authority_path(tmp_path: Path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    preview = preview_visual_candidate(
        asset_id=ready.asset.asset_id, candidate_id=candidate_id,
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, db_path=db, quarantine_signing_key=KEY,
    )
    assert preview.content == PNG and preview.media_type == "image/png"
    assert not hasattr(preview, "path") and not hasattr(preview, "sha256")


def test_explicit_attestation_replays_original_timestamp(tmp_path: Path) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    kwargs = dict(
        asset_id=ready.asset.asset_id, candidate_id=candidate_id,
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        operator_acknowledged_generated_provenance=True, store=store, db_path=db,
        quarantine_signing_key=KEY, operator_signing_key=OPERATOR_KEY,
    )
    first = attest_visual_candidate(**kwargs, now=NOW)
    replay = attest_visual_candidate(**kwargs, now=NOW + timedelta(minutes=5))
    assert replay == first and first.reviewer_id == "owner-1"
    assert not hasattr(first, "signature") and not hasattr(first, "receipt_digest")


@pytest.mark.parametrize(
    ("owner", "revision", "ack"),
    [("owner-2", "rev-1", True), ("owner-1", "stale", True), ("owner-1", "rev-1", False)],
)
def test_foreign_stale_or_unacknowledged_attestation_fails(
    tmp_path: Path, owner: str, revision: str, ack: bool
) -> None:
    store, ready, db, candidate_id = _candidate(tmp_path)
    with pytest.raises(VisualCandidateReviewError):
        attest_visual_candidate(
            asset_id=ready.asset.asset_id, candidate_id=candidate_id,
            expected_revision_id=revision, owner_id=owner,
            operator_acknowledged_generated_provenance=ack,
            store=store, db_path=db, quarantine_signing_key=KEY,
            operator_signing_key=OPERATOR_KEY, now=NOW,
        )
