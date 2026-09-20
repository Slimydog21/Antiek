from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from nacl.signing import SigningKey
from PIL import Image
from PIL import __version__ as pillow_version

from substrate.multimedia.diagram_evidence_authority import DiagramEvidenceAuthority
from substrate.multimedia.local_source_card import (
    LocalSourceCardError,
    LocalSourceCardRegistry,
    LocalSourceCardRequest,
)
from substrate.multimedia.visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

NOW = datetime(2026, 7, 13, tzinfo=UTC)
KEY = b"local-source-card-integrity-key-32"
SEED = b"s" * 32
VERIFY = bytes(SigningKey(SEED).verify_key)
EVIDENCE_KEY = b"source-card-evidence-key-32-bytes"


@pytest.fixture
def state(tmp_path: Path):
    db = tmp_path / "graph.duckdb"
    with duckdb.connect(str(db)) as connection:
        connection.execute("DELETE FROM chunks")
        connection.execute("DELETE FROM documents")
        connection.executemany(
            "INSERT INTO documents(document_id, source_uri, title, source_tier, "
            "document_type, owner_user_id) VALUES (?, ?, ?, 1, 'research', ?)",
            [
                ("doc-a", "https://example.test/a", "Factory Systems", "owner-1"),
                ("doc-b", "https://example.test/b", "Wing Assembly", "owner-1"),
            ],
        )
        connection.executemany(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, section_path, text) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                (
                    "chunk-a",
                    "doc-a",
                    0,
                    "Moving line",
                    "Aircraft factories coordinate stations so work arrives in a controlled sequence.",
                ),
                (
                    "chunk-b",
                    "doc-b",
                    0,
                    "Wing mating",
                    "Wing and center fuselage structures are joined only after dimensional checks.",
                ),
            ],
        )
    output = tmp_path / "cards"
    output.mkdir(mode=0o700)
    font = Path(__file__).parents[1] / "acquisition/books/fonts/DejaVuSans.ttf"
    registry = LocalSourceCardRegistry(
        db_path=str(db),
        output_dir=str(output),
        font_path=str(font),
        integrity_key=KEY,
    )
    return db, registry, font


def _request() -> LocalSourceCardRequest:
    return LocalSourceCardRequest(
        asset_id="asset-1",
        revision_id="revision-1",
        chapter_id="chapter-1",
        scene_id="scene-00",
        title="How the moving assembly line coordinates work",
        information_purpose="Show why station order constrains aircraft production flow.",
        source_chunk_ids=("chunk-a", "chunk-b"),
    )


def _fallback(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id,
        visual_label=selection.visual_label,
        content_sha256=digest,
        evidence_digest="1" * 64,
        authority_key=EVIDENCE_KEY,
    )


def test_creates_private_readable_deterministic_png_and_exactly_replays(state) -> None:
    _db, registry, _font = state
    first = registry.create(_request(), owner_id="owner-1", now=NOW)
    replay = registry.create(_request(), owner_id="owner-1", now=NOW)
    assert replay == first
    assert first.renderer_version == f"antiek.source-card.v1+pillow-{pillow_version}"
    assert len(first.output_sha256) == 64 and set(first.output_sha256) <= set("0123456789abcdef")
    path = Path(first.output_path)
    assert path.stat().st_mode & 0o777 == 0o600
    assert hashlib.sha256(path.read_bytes()).hexdigest() == first.output_sha256
    with Image.open(path) as image:
        assert image.format == "PNG" and image.size == (1280, 720)
        assert image.getpixel((5, 100)) == (242, 201, 76)
        assert image.getpixel((100, 30)) == (24, 35, 47)
    assert first.selection().visual_label == "diagram"
    assert first.source_chunk_ids == ("chunk-a", "chunk-b")


def test_explicit_attestation_resolves_through_graph_evidence_authority(state) -> None:
    db, registry, _font = state
    artifact = registry.create(_request(), owner_id="owner-1", now=NOW)
    registry.attest(
        artifact.card_id,
        _request(),
        owner_id="owner-1",
        reviewer_id="owner-1",
        operator_signing_key=SEED,
        attested_at=NOW,
    )
    authority = DiagramEvidenceAuthority(
        db_path=str(db),
        operator_verify_key=VERIFY,
        evidence_authority_key=EVIDENCE_KEY,
        authorized_reviewer_ids=frozenset({"owner-1"}),
        fallback=_fallback,
    )
    verdict = authority(artifact.selection(), artifact.output_sha256)
    assert verdict.visual_label == "diagram" and verdict.evidence_digest != "1" * 64


@pytest.mark.parametrize(
    "mutation",
    [
        "UPDATE chunks SET text='changed' WHERE chunk_id='chunk-a'",
        "UPDATE documents SET title='Replacement' WHERE document_id='doc-a'",
        "UPDATE documents SET owner_user_id='owner-2' WHERE document_id='doc-a'",
        "DELETE FROM chunks WHERE chunk_id='chunk-b'",
    ],
)
def test_graph_or_owner_drift_invalidates_reopen(state, mutation: str) -> None:
    db, registry, _font = state
    artifact = registry.create(_request(), owner_id="owner-1", now=NOW)
    with duckdb.connect(str(db)) as connection:
        connection.execute(mutation)
    with pytest.raises(LocalSourceCardError):
        registry.reopen(artifact.card_id, _request(), owner_id="owner-1")


def test_file_registry_font_and_request_tamper_fail_closed(state, tmp_path: Path) -> None:
    db, registry, font = state
    artifact = registry.create(_request(), owner_id="owner-1", now=NOW)
    Path(artifact.output_path).write_bytes(b"not-png")
    with pytest.raises(LocalSourceCardError):
        registry.reopen(artifact.card_id, _request(), owner_id="owner-1")

    clean = LocalSourceCardRegistry(
        db_path=str(db),
        output_dir=str(Path(artifact.output_path).parent),
        font_path=str(font),
        integrity_key=KEY,
    )
    with duckdb.connect(str(db)) as connection:
        connection.execute("UPDATE multimedia_local_source_cards SET scene_id='tampered'")
    with pytest.raises(LocalSourceCardError, match="integrity"):
        clean.reopen(artifact.card_id, _request(), owner_id="owner-1")

    with pytest.raises(LocalSourceCardError):
        clean.reopen(
            artifact.card_id,
            LocalSourceCardRequest(**{**_request().__dict__, "title": "Changed title"}),
            owner_id="owner-1",
        )

    font_copy = tmp_path / "font.ttf"
    font_copy.write_bytes(font.read_bytes())
    font_registry = LocalSourceCardRegistry(
        db_path=str(db),
        output_dir=str(Path(artifact.output_path).parent),
        font_path=str(font_copy),
        integrity_key=KEY,
    )
    font_copy.write_bytes(font_copy.read_bytes() + b"changed")
    with pytest.raises(LocalSourceCardError, match="font"):
        font_registry.create(_request(), owner_id="owner-1", now=NOW)


def test_concurrent_create_elects_one_identical_card(state) -> None:
    _db, registry, _font = state
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = tuple(
            pool.map(
                lambda _index: registry.create(_request(), owner_id="owner-1", now=NOW),
                range(2),
            )
        )
    assert rows[0] == rows[1]
    assert len(tuple(Path(rows[0].output_path).parent.glob("*.png"))) == 1


def test_foreign_owner_duplicate_chunks_and_reviewer_conflict_fail(state) -> None:
    _db, registry, _font = state
    with pytest.raises(LocalSourceCardError, match="evidence"):
        registry.create(_request(), owner_id="owner-2", now=NOW)
    duplicate = LocalSourceCardRequest(
        **{**_request().__dict__, "source_chunk_ids": ("chunk-a", "chunk-a")}
    )
    with pytest.raises(ValueError, match="unique"):
        registry.create(duplicate, owner_id="owner-1", now=NOW)
    artifact = registry.create(_request(), owner_id="owner-1", now=NOW)
    with pytest.raises(LocalSourceCardError, match="own"):
        registry.attest(
            artifact.card_id,
            _request(),
            owner_id="owner-1",
            reviewer_id="owner-2",
            operator_signing_key=SEED,
            attested_at=NOW,
        )
