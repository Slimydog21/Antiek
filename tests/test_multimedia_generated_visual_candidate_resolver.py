from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import duckdb
import pytest
from nacl.signing import SigningKey

from substrate.multimedia.generated_visual_candidate_resolver import (
    GeneratedVisualCandidateError,
    GeneratedVisualCandidateResolver,
)
from substrate.multimedia.visual_candidate_materialization import materialize_visual_candidates
from substrate.multimedia.visual_candidate_review import attest_visual_candidate
from substrate.multimedia.visual_evidence_authority import VisualEvidenceAuthority
from tests.test_multimedia_visual_authorization import KEY, _terms
from tests.test_multimedia_visual_candidate_materialization import (
    NOW,
    Resolver,
    Transport,
    _succeeded,
)

OPERATOR_KEY = b"o" * 32
EVIDENCE_KEY = b"e" * 32


def _resolved(tmp_path: Path):
    store, ready, registry, db, client, execution_id, quarantine = _succeeded(tmp_path)
    candidates = materialize_visual_candidates(
        asset_id=ready.asset.asset_id,
        execution_id=execution_id,
        authority_request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id,
        owner_id="owner-1",
        store=store,
        registry=registry,
        terms=_terms(),
        db_path=db,
        signing_key=KEY,
        client=client,
        resolver=Resolver(),
        transport=Transport(),
        allowlisted_hosts=frozenset({"assets.example"}),
        quarantine_dir=str(quarantine),
        now=NOW + timedelta(seconds=3),
    )
    candidate_id = candidates[0].candidate_id
    attest_visual_candidate(
        asset_id=ready.asset.asset_id,
        candidate_id=candidate_id,
        expected_revision_id=ready.asset.revision_id,
        owner_id="owner-1",
        operator_acknowledged_generated_provenance=True,
        store=store,
        db_path=db,
        quarantine_signing_key=KEY,
        operator_signing_key=OPERATOR_KEY,
        now=NOW + timedelta(seconds=4),
    )
    resolver = GeneratedVisualCandidateResolver(
        execution_db_path=db,
        execution_signing_key=KEY,
        authorization_registry=registry,
        evidence_authority=VisualEvidenceAuthority(
            db_path=db,
            operator_verify_key=bytes(SigningKey(OPERATOR_KEY).verify_key),
            evidence_authority_key=EVIDENCE_KEY,
            authorized_reviewer_ids=frozenset({"owner-1"}),
        ),
    )
    chapter_id = ready.plan.chapters[0].chapter_id
    return ready, resolver, chapter_id, candidate_id, db


def test_resolves_only_the_complete_signed_generated_chain(tmp_path: Path) -> None:
    ready, resolver, chapter_id, candidate_id, _db = _resolved(tmp_path)
    selection = resolver(ready, "owner-1", chapter_id, candidate_id)
    assert selection.scene_id == next(
        scene.scene_id for scene in ready.plan.scenes if scene.chapter_id == chapter_id
    )
    assert selection.visual_label == "generated"
    assert selection.artifact_receipt_id.startswith("mmartifact_")
    assert Path(selection.path).is_file()


@pytest.mark.parametrize("failure", ["owner", "chapter", "candidate", "execution", "authority", "attestation"])
def test_foreign_or_tampered_chain_is_opaque(tmp_path: Path, failure: str) -> None:
    ready, resolver, chapter_id, candidate_id, db = _resolved(tmp_path)
    owner = "owner-1"
    if failure == "owner":
        owner = "owner-2"
    elif failure == "chapter":
        chapter_id = "chapter-wrong"
    elif failure == "candidate":
        with duckdb.connect(db) as connection:
            connection.execute(
                "UPDATE multimedia_provider_artifact_candidates SET candidate_mac='tampered' "
                "WHERE candidate_id=?",
                [candidate_id],
            )
    elif failure == "execution":
        with duckdb.connect(db) as connection:
            connection.execute(
                "UPDATE multimedia_provider_executions SET revision_id='tampered'"
            )
    elif failure == "authority":
        with duckdb.connect(str(tmp_path / "authority.duckdb")) as connection:
            connection.execute(
                "UPDATE multimedia_visual_authorizations SET scene_id='tampered'"
            )
    else:
        with duckdb.connect(db) as connection:
            connection.execute(
                "UPDATE multimedia_generated_visual_attestations SET signature='tampered'"
            )
    with pytest.raises(GeneratedVisualCandidateError, match="unavailable"):
        resolver(ready, owner, chapter_id, candidate_id)


def test_unattested_candidate_is_unavailable(tmp_path: Path) -> None:
    ready, resolver, chapter_id, candidate_id, db = _resolved(tmp_path)
    with duckdb.connect(db) as connection:
        connection.execute("DELETE FROM multimedia_generated_visual_attestations")
    with pytest.raises(GeneratedVisualCandidateError, match="unavailable"):
        resolver(ready, "owner-1", chapter_id, candidate_id)
