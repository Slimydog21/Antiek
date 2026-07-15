from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

import pytest

from substrate.multimedia.artifact_quarantine import TransportResponse
from substrate.multimedia.visual_candidate_materialization import (
    VisualCandidateMaterializationError,
    materialize_visual_candidates,
)
from substrate.multimedia.visual_generation import poll_visual_generation, submit_visual_generation
from tests.test_multimedia_artifact_quarantine import PNG
from tests.test_multimedia_visual_authorization import KEY, _terms
from tests.test_multimedia_visual_generation import NOW, FakeKreaClient, _authority


@dataclass
class Resolver:
    def resolve(self, hostname: str):
        assert hostname == "assets.example"
        return ("93.184.216.34",)


@dataclass
class Transport:
    calls: int = 0
    def get(self, **kwargs):
        self.calls += 1
        assert kwargs["tls_hostname"] == "assets.example"
        return TransportResponse(
            200, {"Content-Type": "image/png", "Content-Length": str(len(PNG))},
            "93.184.216.34", (PNG,),
        )


def _succeeded(tmp_path: Path):
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
    quarantine = tmp_path / "quarantine"
    quarantine.mkdir(mode=0o700)
    return store, ready, registry, db, client, submitted.execution_id, quarantine


def test_materializes_exact_locators_and_replay_does_not_redownload(tmp_path: Path) -> None:
    store, ready, registry, db, client, execution_id, quarantine = _succeeded(tmp_path)
    transport = Transport()
    kwargs = dict(
        asset_id=ready.asset.asset_id, execution_id=execution_id,
        authority_request_id="visual-request-1", expected_revision_id=ready.asset.revision_id,
        owner_id="owner-1", store=store, registry=registry, terms=_terms(),
        db_path=db, signing_key=KEY, client=client, resolver=Resolver(),
        transport=transport, allowlisted_hosts=frozenset({"assets.example"}),
        quarantine_dir=str(quarantine), now=NOW + timedelta(seconds=3),
    )
    first = materialize_visual_candidates(**kwargs)
    replay = materialize_visual_candidates(**kwargs)
    assert replay == first and len(first) == 2
    assert transport.calls == 2
    assert all(row.media_type == "image/png" and row.byte_count == len(PNG) for row in first)
    assert all(Path(path).stat().st_mode & 0o777 == 0o600 for path in quarantine.iterdir())


def test_locator_order_drift_fails_before_download(tmp_path: Path) -> None:
    store, ready, registry, db, client, execution_id, quarantine = _succeeded(tmp_path)
    original_poll = client.poll
    client.poll = lambda job_id: original_poll(job_id).__class__(
        job_id, "completed", tuple(reversed(original_poll(job_id).results)),
        original_poll(job_id).raw_digest, client.account_identity_digest,
    )
    transport = Transport()
    with pytest.raises(VisualCandidateMaterializationError, match="digest"):
        materialize_visual_candidates(
            asset_id=ready.asset.asset_id, execution_id=execution_id,
            authority_request_id="visual-request-1", expected_revision_id=ready.asset.revision_id,
            owner_id="owner-1", store=store, registry=registry, terms=_terms(),
            db_path=db, signing_key=KEY, client=client, resolver=Resolver(),
            transport=transport, allowlisted_hosts=frozenset({"assets.example"}),
            quarantine_dir=str(quarantine), now=NOW + timedelta(seconds=3),
        )
    assert transport.calls == 0
