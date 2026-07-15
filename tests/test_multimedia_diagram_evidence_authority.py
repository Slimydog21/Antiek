from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import pytest
from nacl.signing import SigningKey

from substrate.multimedia.diagram_evidence_authority import (
    DiagramEvidenceAuthority,
    DiagramEvidenceAuthorityError,
    attest_diagram,
)
from substrate.multimedia.visual_selection import ReviewedVisualSelection, VerifiedVisualEvidence

SEED = b"diagram-operator-seed-32-bytes!!"
VERIFY = bytes(SigningKey(SEED).verify_key)
EKEY = b"diagram-evidence-key-is-32-bytes!"
NOW = datetime(2026, 7, 11, tzinfo=UTC)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def state(tmp_path: Path):
    db = tmp_path / "graph.duckdb"
    with duckdb.connect(str(db)) as connection:
        connection.execute("DELETE FROM chunks")
        connection.execute("DELETE FROM documents")
        connection.executemany(
            "INSERT INTO documents(document_id, source_uri, title, source_tier, document_type) "
            "VALUES (?, ?, ?, 1, 'research')",
            [
                ("doc-a", "https://example.test/a", "Lift"),
                ("doc-b", "https://example.test/b", "Drag"),
            ],
        )
        connection.executemany(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) VALUES (?, ?, ?, ?)",
            [
                ("chunk-a", "doc-a", 0, "Lift follows from pressure differences."),
                ("chunk-b", "doc-b", 0, "Wing geometry changes induced drag."),
            ],
        )
    diagram = tmp_path / "diagram.png"
    diagram.write_bytes(b"diagram-bytes")
    diagram.chmod(0o600)
    return db, diagram, tmp_path


def _selection(path: Path, chunks: tuple[str, ...] = ("chunk-a", "chunk-b")):
    return ReviewedVisualSelection(
        scene_id="scene-diagram",
        path=str(path),
        expected_sha256=_sha(path),
        visual_label="diagram",
        source_chunk_ids=chunks,
    )


def _fallback(selection: ReviewedVisualSelection, digest: str) -> VerifiedVisualEvidence:
    return VerifiedVisualEvidence.issue(
        scene_id=selection.scene_id,
        visual_label=selection.visual_label,
        content_sha256=digest,
        evidence_digest="1" * 64,
        authority_key=EKEY,
    )


def _authority(db: Path, reviewers=frozenset({"operator-1"})):
    return DiagramEvidenceAuthority(
        db_path=str(db),
        operator_verify_key=VERIFY,
        evidence_authority_key=EKEY,
        authorized_reviewer_ids=reviewers,
        fallback=_fallback,
    )


def _attest(db: Path, diagram: Path, chunks=("chunk-a", "chunk-b"), basis="operator-1"):
    return attest_diagram(
        db_path=str(db),
        diagram_path=str(diagram),
        content_sha256=_sha(diagram),
        source_chunk_ids=chunks,
        reviewer_id=basis,
        operator_signing_key=SEED,
        attested_at=NOW,
    )


def test_attested_diagram_resolves_and_non_diagram_delegates(state) -> None:
    db, diagram, _ = state
    _attest(db, diagram)
    verdict = _authority(db)(_selection(diagram), _sha(diagram))
    assert verdict.visual_label == "diagram" and verdict.evidence_digest != "1" * 64
    generated = ReviewedVisualSelection(
        scene_id="scene-g",
        path=str(diagram),
        expected_sha256=_sha(diagram),
        visual_label="generated",
        source_chunk_ids=("chunk-a",),
        execution_receipt_id="exec-1",
        artifact_receipt_id="artifact-1",
    )
    assert _authority(db)(generated, _sha(diagram)).evidence_digest == "1" * 64


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE chunks SET text='changed' WHERE chunk_id='chunk-a'",
        "UPDATE chunks SET document_id='doc-b' WHERE chunk_id='chunk-a'",
        "DELETE FROM chunks WHERE chunk_id='chunk-b'",
    ],
)
def test_graph_snapshot_drift_fails(state, sql: str) -> None:
    db, diagram, _ = state
    _attest(db, diagram)
    with duckdb.connect(str(db)) as connection:
        connection.execute(sql)
    with pytest.raises(DiagramEvidenceAuthorityError, match="snapshot|missing"):
        _authority(db)(_selection(diagram), _sha(diagram))


def test_chunk_structure_and_embedding_drift_fail(state) -> None:
    db, diagram, _ = state
    _attest(db, diagram)
    with duckdb.connect(str(db)) as connection:
        connection.execute(
            "UPDATE chunks SET chunk_index=99, section_path='attacker', token_count=999, "
            "embedding=[0.25, 0.75] WHERE chunk_id='chunk-a'"
        )
    with pytest.raises(DiagramEvidenceAuthorityError, match="snapshot"):
        _authority(db)(_selection(diagram), _sha(diagram))


def test_document_provenance_replacement_fails(state) -> None:
    db, diagram, _ = state
    _attest(db, diagram)
    with duckdb.connect(str(db)) as connection:
        connection.execute("DELETE FROM chunks WHERE chunk_id='chunk-a'")
        connection.execute("DELETE FROM documents WHERE document_id='doc-a'")
        connection.execute(
            "INSERT INTO documents(document_id, source_uri, title, source_tier, document_type) "
            "VALUES ('doc-a','https://attacker.invalid','Replacement',5,'replacement')"
        )
        connection.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) VALUES "
            "('chunk-a','doc-a',0,'Lift follows from pressure differences.')"
        )
    with pytest.raises(DiagramEvidenceAuthorityError, match="snapshot"):
        _authority(db)(_selection(diagram), _sha(diagram))


def test_document_payload_and_metadata_drift_fail(state) -> None:
    db, diagram, _ = state
    with duckdb.connect(str(db)) as connection:
        connection.execute("DELETE FROM chunks WHERE chunk_id='chunk-a'")
        connection.execute(
            "UPDATE documents SET investigation_id='original', raw_text='source body', "
            "metadata='{\"source\":\"original\"}' WHERE document_id='doc-a'"
        )
        connection.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) VALUES "
            "('chunk-a','doc-a',0,'Lift follows from pressure differences.')"
        )
    _attest(db, diagram)
    with duckdb.connect(str(db)) as connection:
        connection.execute("DELETE FROM chunks WHERE chunk_id='chunk-a'")
        connection.execute(
            "UPDATE documents SET investigation_id='replacement', raw_text='replacement', "
            "metadata='{\"source\":\"attacker\"}' WHERE document_id='doc-a'"
        )
        connection.execute(
            "INSERT INTO chunks(chunk_id, document_id, chunk_index, text) VALUES "
            "('chunk-a','doc-a',0,'Lift follows from pressure differences.')"
        )
    with pytest.raises(DiagramEvidenceAuthorityError, match="snapshot"):
        _authority(db)(_selection(diagram), _sha(diagram))


def test_chunk_order_duplicates_missing_and_empty_fail(state) -> None:
    db, diagram, _ = state
    with pytest.raises(ValueError, match="unique"):
        _attest(db, diagram, ("chunk-a", "chunk-a"))
    with pytest.raises(DiagramEvidenceAuthorityError, match="missing"):
        _attest(db, diagram, ("chunk-missing",))
    with duckdb.connect(str(db)) as connection:
        connection.execute("UPDATE chunks SET text=' ' WHERE chunk_id='chunk-a'")
    with pytest.raises(DiagramEvidenceAuthorityError, match="text"):
        _attest(db, diagram, ("chunk-a",))


def test_signature_reviewer_record_and_selection_tamper_fail(state) -> None:
    db, diagram, _ = state
    _attest(db, diagram)
    with pytest.raises(DiagramEvidenceAuthorityError, match="not authorized"):
        _authority(db, frozenset({"operator-2"}))(_selection(diagram), _sha(diagram))
    with duckdb.connect(str(db)) as connection:
        connection.execute("UPDATE multimedia_diagram_attestations SET reviewer_id='operator-2'")
    with pytest.raises(DiagramEvidenceAuthorityError, match="not authorized"):
        _authority(db)(_selection(diagram), _sha(diagram))
    changed = _selection(diagram).model_copy(update={"source_chunk_ids": ("chunk-b", "chunk-a")})
    with pytest.raises(DiagramEvidenceAuthorityError, match="unavailable"):
        _authority(db)(changed, _sha(diagram))


def test_file_copy_symlink_and_drift_fail(state) -> None:
    db, diagram, root = state
    _attest(db, diagram)
    authority = _authority(db)
    copy = root / "copy.png"
    copy.write_bytes(diagram.read_bytes())
    copy.chmod(0o600)
    with pytest.raises(DiagramEvidenceAuthorityError, match="path"):
        authority(_selection(copy), _sha(copy))
    link = root / "link.png"
    link.symlink_to(diagram)
    with pytest.raises(ValueError, match="symlinks"):
        authority(_selection(link), _sha(diagram))
    diagram.write_bytes(b"drift")
    with pytest.raises(DiagramEvidenceAuthorityError, match="unavailable|digest"):
        authority(
            _selection(diagram).model_copy(update={"expected_sha256": _sha(diagram)}), _sha(diagram)
        )


def test_exact_concurrent_replay_and_conflict(state) -> None:
    db, diagram, _ = state
    with ThreadPoolExecutor(max_workers=2) as pool:
        rows = tuple(pool.map(lambda _: _attest(db, diagram), range(2)))
    assert len({row.signature for row in rows}) == 1
    with duckdb.connect(str(db)) as connection:
        assert (
            connection.execute("SELECT count(*) FROM multimedia_diagram_attestations").fetchone()[0]
            == 1
        )
        connection.execute("UPDATE chunks SET text='changed' WHERE chunk_id='chunk-a'")
    with pytest.raises(DiagramEvidenceAuthorityError, match="conflicts"):
        _attest(db, diagram)


def test_python_boundary_inputs_fail(state) -> None:
    db, diagram, _ = state
    with pytest.raises(ValueError, match="timezone-aware"):
        attest_diagram(
            db_path=str(db),
            diagram_path=str(diagram),
            content_sha256=_sha(diagram),
            source_chunk_ids=("chunk-a",),
            reviewer_id="operator-1",
            operator_signing_key=SEED,
            attested_at=datetime(2026, 7, 11),
        )
    with pytest.raises(ValueError, match="non-empty"):
        _authority(db, frozenset())
