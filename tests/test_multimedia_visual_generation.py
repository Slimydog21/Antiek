from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

from integrations.krea.client import (
    KreaClient,
    KreaClientError,
    KreaJobObservation,
    KreaSubmissionResponse,
)
from substrate.multimedia.visual_authorization import VisualAuthorizationRegistry
from substrate.multimedia.visual_generation import (
    VisualGenerationError,
    poll_visual_generation,
    submit_visual_generation,
)
from tests.test_multimedia_visual_authorization import KEY, _ready, _request, _terms

NOW = datetime(2026, 7, 13, tzinfo=UTC)
JOB = "3c90c3cc-0d44-4b50-8888-8dd25736052a"
TOKEN = "visual-test-account:secret"


class FakeKreaClient(KreaClient):
    def __init__(self, *, submit_error: bool = False) -> None:
        super().__init__(TOKEN)
        self.submit_calls = 0
        self.poll_calls = 0
        self.submit_error = submit_error

    def submit(self, *, endpoint: str, body: bytes) -> KreaSubmissionResponse:
        self.submit_calls += 1
        if self.submit_error:
            raise KreaClientError("transport_ambiguous")
        assert endpoint == "/generate/image/google/imagen-3" and body
        return KreaSubmissionResponse(JOB, "queued", 200)

    def poll(self, job_id: str) -> KreaJobObservation:
        self.poll_calls += 1
        assert job_id == JOB
        return KreaJobObservation(
            JOB, "completed",
            ("https://assets.example/one.png", "https://assets.example/two.png"),
            hashlib.sha256(b"completed-poll").hexdigest(),
            self.account_identity_digest,
        )


def _authority(tmp_path: Path):
    store, ready = _ready(tmp_path)
    db = str(tmp_path / "authority.duckdb")
    registry = VisualAuthorizationRegistry(db_path=db, signing_key=KEY)
    registry.authorize(
        ready.asset.asset_id, _request(ready), owner_id="owner-1", store=store,
        terms=_terms(), now=NOW,
    )
    return store, ready, registry, str(tmp_path / "execution.duckdb")


def test_submit_reopens_exact_authority_and_never_posts_twice(tmp_path: Path) -> None:
    store, ready, registry, db = _authority(tmp_path)
    client = FakeKreaClient()
    kwargs = dict(
        asset_id=ready.asset.asset_id, request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, registry=registry, terms=_terms(), db_path=db,
        signing_key=KEY, client=client,
    )
    first = submit_visual_generation(**kwargs, now=NOW + timedelta(seconds=1))
    replay = submit_visual_generation(**kwargs, now=NOW + timedelta(minutes=2))
    assert first == replay
    assert first.status == "submitted" and first.provider_job_id == JOB
    assert client.submit_calls == 1


def test_ambiguous_submit_is_fully_terminal_to_automatic_replay(tmp_path: Path) -> None:
    store, ready, registry, db = _authority(tmp_path)
    client = FakeKreaClient(submit_error=True)
    kwargs = dict(
        asset_id=ready.asset.asset_id, request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, registry=registry, terms=_terms(), db_path=db,
        signing_key=KEY, client=client,
    )
    first = submit_visual_generation(**kwargs, now=NOW + timedelta(seconds=1))
    replay = submit_visual_generation(**kwargs, now=NOW + timedelta(minutes=2))
    assert first == replay and first.status == "outcome_unknown"
    assert client.submit_calls == 1


def test_one_authenticated_poll_reconciles_success_and_signed_candidates(tmp_path: Path) -> None:
    store, ready, registry, db = _authority(tmp_path)
    client = FakeKreaClient()
    submitted = submit_visual_generation(
        asset_id=ready.asset.asset_id, request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, registry=registry, terms=_terms(), db_path=db,
        signing_key=KEY, client=client, now=NOW + timedelta(seconds=1),
    )
    observed = poll_visual_generation(
        asset_id=ready.asset.asset_id, execution_id=submitted.execution_id,
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, db_path=db, signing_key=KEY, client=client,
        now=NOW + timedelta(seconds=2),
    )
    assert observed.status == "succeeded" and observed.candidate_count == 2
    assert client.poll_calls == 1


def test_candidate_mac_tampering_fails_instead_of_reporting_zero(tmp_path: Path) -> None:
    store, ready, registry, db = _authority(tmp_path)
    client = FakeKreaClient()
    submitted = submit_visual_generation(
        asset_id=ready.asset.asset_id, request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, registry=registry, terms=_terms(), db_path=db,
        signing_key=KEY, client=client, now=NOW + timedelta(seconds=1),
    )
    poll_visual_generation(
        asset_id=ready.asset.asset_id, execution_id=submitted.execution_id,
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, db_path=db, signing_key=KEY, client=client,
        now=NOW + timedelta(seconds=2),
    )
    with duckdb.connect(db) as connection:
        connection.execute(
            "UPDATE multimedia_provider_artifact_candidates SET candidate_mac='tampered'"
        )
    with pytest.raises(VisualGenerationError, match="integrity"):
        poll_visual_generation(
            asset_id=ready.asset.asset_id, execution_id=submitted.execution_id,
            expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
            store=store, db_path=db, signing_key=KEY, client=client,
            now=NOW + timedelta(seconds=3),
        )


@pytest.mark.parametrize(
    ("owner", "revision"), [("owner-2", "rev-1"), ("owner-1", "stale")]
)
def test_foreign_or_stale_poll_fails_before_provider(tmp_path: Path, owner: str, revision: str) -> None:
    store, ready, registry, db = _authority(tmp_path)
    client = FakeKreaClient()
    submitted = submit_visual_generation(
        asset_id=ready.asset.asset_id, request_id="visual-request-1",
        expected_revision_id=ready.asset.revision_id, owner_id="owner-1",
        store=store, registry=registry, terms=_terms(), db_path=db,
        signing_key=KEY, client=client, now=NOW + timedelta(seconds=1),
    )
    with pytest.raises(VisualGenerationError):
        poll_visual_generation(
            asset_id=ready.asset.asset_id, execution_id=submitted.execution_id,
            expected_revision_id=revision, owner_id=owner, store=store,
            db_path=db, signing_key=KEY, client=client,
            now=NOW + timedelta(seconds=2),
        )
    assert client.poll_calls == 0
