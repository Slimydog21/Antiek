from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest

from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore
from substrate.multimedia.reviewed_visual_registry import (
    RegisterReviewedVisualsRequest,
    ReviewedVisualRegistry,
    ReviewedVisualRegistryError,
    VisualCandidateBinding,
    get_reviewed_visuals,
    register_reviewed_visuals,
)
from substrate.multimedia.visual_selection import ReviewedVisualSelection

NOW = datetime(2026, 7, 12, tzinfo=UTC)


def _ready(tmp_path: Path, *, mode: str = "video", route: str = "balanced"):
    store = MultimediaAssetStore(str(tmp_path / "assets"))
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Reviewed visual authority",
            target_minutes=15,
            mode=mode,
            route_policy=route,
            sources=("Grounded evidence for every chapter.",),
        ),
        owner_id="owner-1",
    )
    return store, store.approve_dry_run(draft.asset.asset_id, owner_id="owner-1")


def _spoken(record):
    return tuple(
        chapter
        for chapter in record.plan.chapters
        if any(
            line.line_id.split("-line-", 1)[0] == chapter.chapter_id
            for line in record.plan.script_lines
        )
    )


def _resolver(root: Path):
    root.mkdir(parents=True, exist_ok=True)

    def resolve(record, owner_id: str, chapter_id: str, candidate_id: str):
        assert owner_id == "owner-1"
        chapter = next(row for row in record.plan.chapters if row.chapter_id == chapter_id)
        path = root / f"{candidate_id}.ppm"
        if not path.exists():
            path.write_bytes(f"P6\n1 1\n255\n{candidate_id}".encode())
        scene = next(row for row in record.plan.scenes if row.chapter_id == chapter_id)
        return ReviewedVisualSelection(
            scene_id=scene.scene_id,
            path=str(path),
            expected_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            visual_label="generated",
            source_chunk_ids=chapter.source_chunk_ids,
            execution_receipt_id=f"exec-{candidate_id}",
            artifact_receipt_id=f"artifact-{candidate_id}",
        )

    return resolve


def _request(record, *, request_id: str = "request-1", suffix: str = "a"):
    return RegisterReviewedVisualsRequest(
        request_id=request_id,
        expected_revision_id=record.asset.revision_id,
        bindings=tuple(
            VisualCandidateBinding(
                chapter_id=chapter.chapter_id,
                candidate_id=f"candidate-{index}-{suffix}",
            )
            for index, chapter in enumerate(_spoken(record))
        ),
    )


def test_registers_owner_revision_bound_set_and_exactly_replays(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"v" * 32
    )
    request = _request(ready)
    first = register_reviewed_visuals(
        ready.asset.asset_id,
        request,
        owner_id="owner-1",
        store=store,
        registry=registry,
        candidate_resolver=_resolver(tmp_path / "candidates"),
        clock=lambda: NOW,
    )
    replay = register_reviewed_visuals(
        ready.asset.asset_id,
        request,
        owner_id="owner-1",
        store=store,
        registry=registry,
        candidate_resolver=_resolver(tmp_path / "candidates"),
        clock=lambda: NOW,
    )
    assert replay == first
    assert first.chapter_ids == tuple(row.chapter_id for row in _spoken(ready))
    assert first.scene_ids == tuple(
        next(scene.scene_id for scene in ready.plan.scenes if scene.chapter_id == row.chapter_id)
        for row in _spoken(ready)
    )
    resolved = get_reviewed_visuals(
        ready.asset.asset_id,
        ready.asset.revision_id,
        owner_id="owner-1",
        store=store,
        registry=registry,
    )
    assert resolved.receipt == first
    assert len(resolved.selections) == len(_spoken(ready))


def test_changed_request_terms_and_second_set_conflict(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"v" * 32
    )
    resolver = _resolver(tmp_path / "candidates")
    register_reviewed_visuals(
        ready.asset.asset_id,
        _request(ready),
        owner_id="owner-1",
        store=store,
        registry=registry,
        candidate_resolver=resolver,
        clock=lambda: NOW,
    )
    with pytest.raises(ReviewedVisualRegistryError, match="different terms"):
        register_reviewed_visuals(
            ready.asset.asset_id,
            _request(ready, suffix="changed"),
            owner_id="owner-1",
            store=store,
            registry=registry,
            candidate_resolver=resolver,
            clock=lambda: NOW,
        )
    with pytest.raises(ReviewedVisualRegistryError, match="already exists"):
        register_reviewed_visuals(
            ready.asset.asset_id,
            _request(ready, request_id="request-2", suffix="changed"),
            owner_id="owner-1",
            store=store,
            registry=registry,
            candidate_resolver=resolver,
            clock=lambda: NOW,
        )


@pytest.mark.parametrize("kind", ["foreign", "stale", "incomplete", "duplicate"])
def test_invalid_authority_fails_before_registry_write(tmp_path: Path, kind: str) -> None:
    store, ready = _ready(tmp_path)
    request = _request(ready)
    owner = "owner-1"
    if kind == "foreign":
        owner = "owner-2"
    elif kind == "stale":
        request = RegisterReviewedVisualsRequest(
            request_id=request.request_id,
            expected_revision_id="rev-old",
            bindings=request.bindings,
        )
    elif kind == "incomplete":
        request = RegisterReviewedVisualsRequest(
            request_id=request.request_id,
            expected_revision_id=request.expected_revision_id,
            bindings=request.bindings[:-1],
        )
    else:
        request = RegisterReviewedVisualsRequest(
            request_id=request.request_id,
            expected_revision_id=request.expected_revision_id,
            bindings=tuple(
                VisualCandidateBinding(row.chapter_id, "same-candidate")
                for row in request.bindings
            ),
        )
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "visuals.duckdb"), integrity_key=b"v" * 32
    )
    with pytest.raises(ReviewedVisualRegistryError):
        register_reviewed_visuals(
            ready.asset.asset_id,
            request,
            owner_id=owner,
            store=store,
            registry=registry,
            candidate_resolver=_resolver(tmp_path / "candidates"),
            clock=lambda: NOW,
        )
    with pytest.raises(ReviewedVisualRegistryError, match="unavailable"):
        registry.get(
            owner_identity_digest=ready.asset.owner_user_id,
            asset_id=ready.asset.asset_id,
            revision_id=ready.asset.revision_id,
        )


def test_audio_cheapest_scene_grounding_symlink_and_file_drift_fail_closed(
    tmp_path: Path,
) -> None:
    for index, (mode, route, message) in enumerate(
        (("audio", "balanced", "video"), ("video", "cheapest", "cheapest"))
    ):
        store, ready = _ready(tmp_path / str(index), mode=mode, route=route)
        registry = ReviewedVisualRegistry(
            db_path=str(tmp_path / f"visuals-{index}.duckdb"), integrity_key=b"v" * 32
        )
        with pytest.raises(ReviewedVisualRegistryError, match=message):
            register_reviewed_visuals(
                ready.asset.asset_id,
                _request(ready),
                owner_id="owner-1",
                store=store,
                registry=registry,
                candidate_resolver=_resolver(tmp_path / f"candidates-{index}"),
                clock=lambda: NOW,
            )

    store, ready = _ready(tmp_path / "drift")
    registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "drift.duckdb"), integrity_key=b"v" * 32
    )
    good = _resolver(tmp_path / "drift-candidates")

    def wrong_scene(record, owner_id, chapter_id, candidate_id):
        return good(record, owner_id, chapter_id, candidate_id).model_copy(
            update={"scene_id": "scene-wrong"}
        )

    with pytest.raises(ReviewedVisualRegistryError, match="scene"):
        register_reviewed_visuals(
            ready.asset.asset_id,
            _request(ready),
            owner_id="owner-1",
            store=store,
            registry=registry,
            candidate_resolver=wrong_scene,
            clock=lambda: NOW,
        )

    def symlinked(record, owner_id, chapter_id, candidate_id):
        selection = good(record, owner_id, chapter_id, candidate_id)
        target = Path(selection.path)
        link = target.with_name(f"link-{target.name}")
        if not link.exists():
            link.symlink_to(target)
        return selection.model_copy(update={"path": str(link)})

    with pytest.raises(ReviewedVisualRegistryError, match="regular file"):
        register_reviewed_visuals(
            ready.asset.asset_id,
            _request(ready, request_id="symlink"),
            owner_id="owner-1",
            store=store,
            registry=registry,
            candidate_resolver=symlinked,
            clock=lambda: NOW,
        )

    receipt = register_reviewed_visuals(
        ready.asset.asset_id,
        _request(ready, request_id="good"),
        owner_id="owner-1",
        store=store,
        registry=registry,
        candidate_resolver=good,
        clock=lambda: NOW,
    )
    first = registry.get(
        owner_identity_digest=ready.asset.owner_user_id,
        asset_id=ready.asset.asset_id,
        revision_id=ready.asset.revision_id,
    ).selections[0]
    Path(first.path).write_bytes(b"changed")
    with pytest.raises(ReviewedVisualRegistryError, match="changed"):
        get_reviewed_visuals(
            ready.asset.asset_id,
            receipt.revision_id,
            owner_id="owner-1",
            store=store,
            registry=registry,
        )


def test_database_mac_tamper_and_revision_race_fail_closed(tmp_path: Path) -> None:
    store, ready = _ready(tmp_path)
    db_path = tmp_path / "visuals.duckdb"
    registry = ReviewedVisualRegistry(db_path=str(db_path), integrity_key=b"v" * 32)
    register_reviewed_visuals(
        ready.asset.asset_id,
        _request(ready),
        owner_id="owner-1",
        store=store,
        registry=registry,
        candidate_resolver=_resolver(tmp_path / "candidates"),
        clock=lambda: NOW,
    )
    connection = duckdb.connect(str(db_path))
    connection.execute(
        "UPDATE multimedia_reviewed_visual_sets SET candidate_ids_json='[\"tampered\"]'"
    )
    connection.close()
    with pytest.raises(ReviewedVisualRegistryError, match="MAC"):
        registry.get(
            owner_identity_digest=ready.asset.owner_user_id,
            asset_id=ready.asset.asset_id,
            revision_id=ready.asset.revision_id,
        )

    race_store, race_ready = _ready(tmp_path / "race")

    class RacingStore:
        def __init__(self):
            self.calls = 0

        def get(self, asset_id, *, owner_id):
            self.calls += 1
            record = race_store.get(asset_id, owner_id=owner_id)
            if self.calls >= 2:
                return record.model_copy(
                    update={
                        "asset": record.asset.model_copy(update={"revision_id": "rev-2"})
                    }
                )
            return record

    race_registry = ReviewedVisualRegistry(
        db_path=str(tmp_path / "race.duckdb"), integrity_key=b"v" * 32
    )
    with pytest.raises(ReviewedVisualRegistryError, match="changed during review"):
        register_reviewed_visuals(
            race_ready.asset.asset_id,
            _request(race_ready),
            owner_id="owner-1",
            store=RacingStore(),  # type: ignore[arg-type]
            registry=race_registry,
            candidate_resolver=_resolver(tmp_path / "race-candidates"),
            clock=lambda: NOW,
        )
    with pytest.raises(ReviewedVisualRegistryError, match="unavailable"):
        race_registry.get(
            owner_identity_digest=race_ready.asset.owner_user_id,
            asset_id=race_ready.asset.asset_id,
            revision_id=race_ready.asset.revision_id,
        )
