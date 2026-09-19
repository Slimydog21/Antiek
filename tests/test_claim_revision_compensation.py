import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError

from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.claim_revision_compensation import (
    ClaimRevisionCompensationConflict,
    accept_claim_revision_compensation,
    build_claim_revision_compensation_preview,
    replay_claim_revision_compensation,
)
from substrate.research_artifact.import_notes import parse_body_from_html
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import (
    ArtifactOwnerClaimRevision,
    ResearchArtifactBody,
)
from substrate.research_artifact.storage import FilesystemArtifactStore

OWNER = "a" * 64


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path))
    authority = ArtifactAuthority("alice", "compensation")
    base = ResearchArtifactBody(
        investigation_id="compensation",
        problem_question="What is current?",
        synthesis_event_id="archived-synthesis",
        claim_support=[{
            "claim": "Archived terminal wording.",
            "supporting_chunk_ids": ["archived-chunk"],
        }],
    )
    payload = {
        "schema_version": 1,
        "status": "owner_accepted_claim_revision",
        "owner_account_digest": OWNER,
        "artifact_account_digest": authority.account_digest,
        "artifact_investigation_digest": authority.investigation_digest,
        "prior_artifact_content_hash": base.content_hash(),
        "claim_index": 0,
        "claim_id": f"artifact-v2:{base.content_hash()}:0",
        "original_claim_sha256": hashlib.sha256(
            base.claim_support[0].claim.encode()
        ).hexdigest(),
        "original_claim": base.claim_support[0].claim,
        "revised_claim": "Initial owner revision.",
        "rationale": "Initial accepted analysis.",
        "proposal_receipt_sha256": "b" * 64,
        "selected_acceptance_receipt_sha256s": ("c" * 64,),
        "mutation_key_sha256": "d" * 64,
        "archive_grounded": False,
        "grants_authority": False,
    }
    root = ArtifactOwnerClaimRevision(
        **payload, transition_sha256=_digest(payload)
    )
    current = ResearchArtifactBody.model_validate({
        **base.model_dump(mode="json"),
        "schema_version": 3,
        "owner_claim_revisions": [root.model_dump(mode="json")],
    })
    store = FilesystemArtifactStore(tmp_path)
    store.write(authority, render_html(current))
    return authority, base, root, current, store


def test_restore_preview_is_server_authored_additive_and_zero_write(
    tmp_path, monkeypatch
):
    authority, base, root, current, store = _fixture(tmp_path, monkeypatch)
    preview = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="restore_archived_terminal",
        replacement_claim=None,
        rationale="Return to the archived wording while retaining history.  ",
        mutation_key="restore-one",
    )
    assert preview.compensation.replacement_claim == base.claim_support[0].claim
    assert preview.prospective_body.claim_support == current.claim_support
    assert preview.prospective_body.owner_claim_revisions == current.owner_claim_revisions
    assert preview.prospective_body.schema_version == 4
    assert preview.prospective_body.effective_owner_claim(0) == (
        base.claim_support[0].claim,
        preview.compensation.transition_sha256,
    )
    assert "<script>" not in preview.public_dict()["html"]
    assert parse_body_from_html(store.read(authority)) == current
    with pytest.raises(ValueError, match="server-authored"):
        build_claim_revision_compensation_preview(
            authority=authority,
            owner_account_digest=OWNER,
            prior_body=current,
            claim_index=0,
            supersedes_transition_sha256=root.transition_sha256,
            operation="restore_archived_terminal",
            replacement_claim="Forged restore wording.",
            rationale="r",
            mutation_key="k",
        )


def test_accept_preserves_current_history_and_supports_exact_replay(
    tmp_path, monkeypatch
):
    authority, base, root, current, store = _fixture(tmp_path, monkeypatch)
    prior_html = store.read(authority)
    preview = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="A narrower current owner claim.  ",
        rationale="New owner judgment.  ",
        mutation_key="supersede-one",
    )
    accepted = accept_claim_revision_compensation(
        authority=authority,
        owner_account_digest=OWNER,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="A narrower current owner claim.  ",
        rationale="New owner judgment.  ",
        mutation_key="supersede-one",
        expected_preview_sha256=preview.preview_sha256,
        expected_transition_sha256=preview.compensation.transition_sha256,
        store=store,
    )
    final = parse_body_from_html(store.read(authority))
    assert final.claim_support == base.claim_support
    assert final.synthesis_event_id == "archived-synthesis"
    assert store.read_history(
        authority, body_content_hash=current.content_hash()
    ) == prior_html
    assert replay_claim_revision_compensation(
        body=final,
        prior_artifact_content_hash=current.content_hash(),
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="A narrower current owner claim.  ",
        rationale="New owner judgment.  ",
        mutation_key="supersede-one",
    ) == accepted
    with pytest.raises(ClaimRevisionCompensationConflict, match="another command"):
        replay_claim_revision_compensation(
            body=final,
            prior_artifact_content_hash=current.content_hash(),
            claim_index=0,
            supersedes_transition_sha256=root.transition_sha256,
            operation="supersede_owner_revision",
            replacement_claim="Changed replay.",
            rationale="New owner judgment.  ",
            mutation_key="supersede-one",
        )


def test_stale_head_and_concurrency_allow_one_append(tmp_path, monkeypatch):
    authority, _, root, current, store = _fixture(tmp_path, monkeypatch)
    preview = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="restore_archived_terminal",
        replacement_claim=None,
        rationale="Restore with history.",
        mutation_key="restore-race",
    )

    def accept():
        try:
            return accept_claim_revision_compensation(
                authority=authority,
                owner_account_digest=OWNER,
                claim_index=0,
                supersedes_transition_sha256=root.transition_sha256,
                operation="restore_archived_terminal",
                replacement_claim=None,
                rationale="Restore with history.",
                mutation_key="restore-race",
                expected_preview_sha256=preview.preview_sha256,
                expected_transition_sha256=preview.compensation.transition_sha256,
                store=store,
            )["status"]
        except (ClaimRevisionCompensationConflict, ValueError):
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: accept(), range(2)))
    assert results.count("accepted") == 1
    assert results.count("conflict") == 1


def test_schema_v3_hash_stays_stable_and_chain_corruption_fails(
    tmp_path, monkeypatch
):
    _, _, root, current, _ = _fixture(tmp_path, monkeypatch)
    historical = current.model_dump(mode="json", exclude={"owner_claim_compensations"})
    assert ResearchArtifactBody.model_validate(historical).content_hash() == current.content_hash()
    preview = build_claim_revision_compensation_preview(
        authority=ArtifactAuthority("alice", "compensation"),
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="restore_archived_terminal",
        replacement_claim=None,
        rationale="Restore.",
        mutation_key="restore",
    )
    broken = preview.prospective_body.model_dump(mode="json")
    broken["owner_claim_compensations"][0]["supersedes_transition_sha256"] = "9" * 64
    with pytest.raises(ValidationError):
        ResearchArtifactBody.model_validate(broken)


def test_v4_empty_predecessor_and_sequential_replay_keep_exact_historical_result(
    tmp_path, monkeypatch
):
    authority, _, root, current, store = _fixture(tmp_path, monkeypatch)
    empty_v4 = ResearchArtifactBody.model_validate(
        {**current.model_dump(mode="json"), "schema_version": 4}
    )
    store.write(authority, render_html(empty_v4))
    first = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=empty_v4,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="First compensated wording.",
        rationale="First rationale.",
        mutation_key="first",
    )
    first_result = accept_claim_revision_compensation(
        authority=authority,
        owner_account_digest=OWNER,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="First compensated wording.",
        rationale="First rationale.",
        mutation_key="first",
        expected_preview_sha256=first.preview_sha256,
        expected_transition_sha256=first.compensation.transition_sha256,
        store=store,
    )
    after_first = parse_body_from_html(store.read(authority))
    second = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=after_first,
        claim_index=0,
        supersedes_transition_sha256=first.compensation.transition_sha256,
        operation="restore_archived_terminal",
        replacement_claim=None,
        rationale="Second rationale.",
        mutation_key="second",
    )
    accept_claim_revision_compensation(
        authority=authority,
        owner_account_digest=OWNER,
        claim_index=0,
        supersedes_transition_sha256=first.compensation.transition_sha256,
        operation="restore_archived_terminal",
        replacement_claim=None,
        rationale="Second rationale.",
        mutation_key="second",
        expected_preview_sha256=second.preview_sha256,
        expected_transition_sha256=second.compensation.transition_sha256,
        store=store,
    )
    final = parse_body_from_html(store.read(authority))
    replay = replay_claim_revision_compensation(
        body=final,
        prior_artifact_content_hash=empty_v4.content_hash(),
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="First compensated wording.",
        rationale="First rationale.",
        mutation_key="first",
    )
    assert replay == first_result
    assert replay["artifact_content_hash"] == after_first.content_hash()
    assert replay["artifact_content_hash"] != final.content_hash()

    foreign = after_first.model_dump(mode="json")
    foreign["owner_claim_compensations"][0]["owner_account_digest"] = "f" * 64
    payload = foreign["owner_claim_compensations"][0]
    payload["transition_sha256"] = _digest(
        {key: value for key, value in payload.items() if key != "transition_sha256"}
    )
    with pytest.raises(ValidationError, match="lineage"):
        ResearchArtifactBody.model_validate(foreign)


def test_proposal_compensation_is_discriminated_without_changing_v1_bytes(
    tmp_path, monkeypatch
):
    authority, _, root, current, _ = _fixture(tmp_path, monkeypatch)
    legacy = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="Legacy v1 wording.",
        rationale="Legacy rationale.",
        mutation_key="legacy",
    )
    legacy_payload = legacy.compensation.model_dump(mode="json")
    assert legacy_payload["schema_version"] == 1
    assert not any(key.startswith("source_") for key in legacy_payload)

    proposal = build_claim_revision_compensation_preview(
        authority=authority,
        owner_account_digest=OWNER,
        prior_body=current,
        claim_index=0,
        supersedes_transition_sha256=root.transition_sha256,
        operation="supersede_owner_revision",
        replacement_claim="Proposal wording.",
        rationale="Reviewed proposal rationale.",
        mutation_key="proposal",
        source_context_receipt_sha256="1" * 64,
        source_review_receipt_sha256="2" * 64,
        source_proposal_receipt_sha256="3" * 64,
    )
    assert proposal.compensation.schema_version == 2
    round_trip = ResearchArtifactBody.model_validate(
        proposal.prospective_body.model_dump(mode="json")
    )
    assert round_trip.content_hash() == proposal.prospective_body.content_hash()

    with pytest.raises(ValidationError, match="consumed more than once"):
        build_claim_revision_compensation_preview(
            authority=authority,
            owner_account_digest=OWNER,
            prior_body=proposal.prospective_body,
            claim_index=0,
            supersedes_transition_sha256=proposal.compensation.transition_sha256,
            operation="supersede_owner_revision",
            replacement_claim="A second wording.",
            rationale="Attempt duplicate consumption.",
            mutation_key="proposal-two",
            source_context_receipt_sha256="1" * 64,
            source_review_receipt_sha256="2" * 64,
            source_proposal_receipt_sha256="3" * 64,
        )
