import hashlib
from datetime import UTC, datetime
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.event_log import Event, append_persisted_event, trajectory
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.compose import (
    ComposeMember,
    ComposeResult,
    VerifiedComposition,
    VerifiedCompositionMember,
)
from substrate.research_artifact.composition_repository import (
    ResearchCompositionConflict,
    ResearchCompositionPrecondition,
    ResearchCompositionRepository,
    ResearchCompositionUnavailable,
)
from substrate.research_artifact.render import render_html
from substrate.research_artifact.schema import ResearchArtifactBody


def _body(investigation_id: str) -> ResearchArtifactBody:
    return ResearchArtifactBody(
        investigation_id=investigation_id,
        problem_question=f"Question {investigation_id}",
        synthesis_excerpt="Synthesis",
    )


def _verified() -> VerifiedComposition:
    first = _body("inv-a")
    second = _body("inv-b")
    members = [
        VerifiedCompositionMember(
            "inv-a", first.content_hash(), hashlib.sha256(render_html(first).encode()).hexdigest(), first
        ),
        VerifiedCompositionMember(
            "inv-b", second.content_hash(), hashlib.sha256(render_html(second).encode()).hexdigest(), second
        ),
    ]
    return VerifiedComposition("cmp-" + "a" * 64, "a" * 64, 1, members)


def _result(verified: VerifiedComposition) -> ComposeResult:
    return ComposeResult(
        verified.composition_id,
        verified.ordered_set_digest,
        Path("unused"),
        [ComposeMember(m.investigation_id, m.content_hash, m.rendered_sha256)
         for m in verified.members],
        [],
    )


@pytest.fixture
def repository(monkeypatch, tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    verified = _verified()
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.load_verified_composition",
        lambda _composition_id: verified,
    )
    return ResearchCompositionRepository(db_path=db_path), verified


def test_owner_authority_preserves_order_and_is_opaque(repository):
    repo, verified = repository
    created = repo.bind_created(owner_user_id="owner-a", result=_result(verified))
    assert created["etag"].startswith('"rc-v1-cmp-')
    read = repo.read(owner_user_id="owner-a", composition_id=verified.composition_id)
    assert [m.investigation_id for m in read["composition"].members] == ["inv-a", "inv-b"]
    with pytest.raises(ResearchCompositionUnavailable):
        repo.read(owner_user_id="owner-b", composition_id=verified.composition_id)


def test_binding_tamper_and_idempotency_conflict(repository):
    repo, verified = repository
    authority = repo.bind_created(owner_user_id="owner", result=_result(verified))
    options = {"question": "What follows?", "parent_investigation_id": None,
               "research_tier": "fast"}
    prepared = repo.prepare_launch(
        owner_user_id="owner", composition_id=verified.composition_id,
        if_match=authority["etag"], idempotency_key="launch-key-1", options=options,
    )
    assert prepared.delivery_event is not None
    assert prepared.delivery_event["payload"]["research_composition"]["member_count"] == 2
    assert prepared.lease_token is not None
    assert repo.verify_delivery(
        owner_user_id="owner", idempotency_key="launch-key-1",
        lease_token=prepared.lease_token,
    )["event_id"] == prepared.delivery_event["event_id"]
    with pytest.raises(ResearchCompositionConflict, match="idempotency"):
        repo.prepare_launch(
            owner_user_id="owner", composition_id=verified.composition_id,
            if_match=authority["etag"], idempotency_key="launch-key-1",
            options={**options, "question": "Different question"},
        )


def test_stale_etag_tamper_and_capacity_are_rejected(repository, monkeypatch):
    repo, verified = repository
    repo.bind_created(owner_user_id="owner", result=_result(verified))
    with pytest.raises(ResearchCompositionPrecondition):
        repo.prepare_launch(
            owner_user_id="owner", composition_id=verified.composition_id,
            if_match='"stale"', idempotency_key="stale-key",
            options={"question": "What follows?"},
        )
    with connect_write(repo.db_path, purpose="tamper-composition-member") as con:
        con.execute(
            "UPDATE research_composition_members SET content_hash=? WHERE owner_user_id=?",
            ["f" * 64, "owner"],
        )
    with pytest.raises(ResearchCompositionConflict, match="binding"):
        repo.read(owner_user_id="owner", composition_id=verified.composition_id)

    repo.bind_created(owner_user_id="another-owner", result=_result(verified))
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.MAX_COMPOSITIONS", 1
    )
    other = VerifiedComposition(
        "cmp-" + "b" * 64, "b" * 64, 1, verified.members,
    )
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.load_verified_composition",
        lambda _composition_id: other,
    )
    with pytest.raises(ResearchCompositionConflict, match="capacity"):
        repo.bind_created(owner_user_id="another-owner", result=_result(other))


def test_context_ceiling_and_collective_launch_member_limit(repository, monkeypatch):
    repo, verified = repository
    repo.bind_created(owner_user_id="owner", result=_result(verified))
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.MAX_CONTEXT_BYTES", 1
    )
    with pytest.raises(ResearchCompositionConflict, match="context exceeds"):
        repo.read(owner_user_id="owner", composition_id=verified.composition_id)

    members = []
    for index in range(9):
        body = _body(f"inv-{index}")
        rendered = render_html(body).encode()
        members.append(
            VerifiedCompositionMember(
                f"inv-{index}",
                body.content_hash(),
                hashlib.sha256(rendered).hexdigest(),
                body,
            )
        )
    oversized = VerifiedComposition("cmp-" + "c" * 64, "c" * 64, 1, members)
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.MAX_CONTEXT_BYTES",
        192 * 1024,
    )
    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.load_verified_composition",
        lambda _composition_id: oversized,
    )
    oversized_authority = repo.bind_created(
        owner_user_id="owner", result=_result(oversized)
    )
    with pytest.raises(ResearchCompositionConflict, match="2-8 members"):
        repo.prepare_launch(
            owner_user_id="owner",
            composition_id=oversized.composition_id,
            if_match=oversized_authority["etag"],
            idempotency_key="oversized-launch",
            options={"question": "What follows?"},
        )


def test_completed_launch_replays_and_expired_lease_redelivers_once(
    repository, monkeypatch, tmp_path,
):
    repo, verified = repository
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    authority = repo.bind_created(owner_user_id="owner", result=_result(verified))
    options = {"question": "What follows?"}

    class ExpiredDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return datetime(2000, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(
        "substrate.research_artifact.composition_repository.datetime", ExpiredDatetime,
    )
    first = repo.prepare_launch(
        owner_user_id="owner", composition_id=verified.composition_id,
        if_match=authority["etag"], idempotency_key="recovery-key", options=options,
    )
    event = Event.model_validate(first.delivery_event)
    assert append_persisted_event(event) is True
    recovered = repo.prepare_launch(
        owner_user_id="owner", composition_id=verified.composition_id,
        if_match=authority["etag"], idempotency_key="recovery-key", options=options,
    )
    assert recovered.delivery_event == first.delivery_event
    assert recovered.lease_token != first.lease_token
    assert append_persisted_event(Event.model_validate(recovered.delivery_event)) is False
    assert len(trajectory(first.investigation_id)) == 1
    response = {"investigation_id": first.investigation_id, "status": "started",
                "start_event_id": event.event_id}
    repo.complete_launch(
        owner_user_id="owner", idempotency_key="recovery-key",
        lease_token=recovered.lease_token, response=response,
    )
    replay = repo.prepare_launch(
        owner_user_id="owner", composition_id=verified.composition_id,
        if_match=authority["etag"], idempotency_key="recovery-key", options=options,
    )
    assert replay.replay_response == response
