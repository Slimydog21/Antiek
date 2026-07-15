"""CTW-01 — immutable compose to zero-spend Write workspace."""

from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import duckdb
import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_node
from substrate.research_artifact import delete_compose_draft
from substrate.research_artifact.schema import (
    ArtifactInsight,
    ArtifactQuestion,
    ResearchArtifactBody,
)
from substrate.write.promote_compose import ComposeIntegrityError, promote_compose_to_write


@pytest.fixture
def compose_write_env(tmp_path, monkeypatch):
    db = str(tmp_path / "antiek.duckdb")
    root = tmp_path / "artifacts"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(root))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(db)
    return db, root


def _write_compose(root, bodies: list[ResearchArtifactBody]) -> str:
    members = [[body.investigation_id, body.content_hash()] for body in bodies]
    fingerprint = hashlib.sha256(json.dumps(
        {"schema_version": 1, "members": members},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    compose_id = f"cmp-{fingerprint[:24]}"
    target = root / "composes" / compose_id
    (target / "members").mkdir(parents=True)
    manifest = {
        "schema_version": 1,
        "compose_id": compose_id,
        "selection_fingerprint": fingerprint,
        "members": [
            {"investigation_id": iid, "content_hash": content_hash}
            for iid, content_hash in members
        ],
        "hash_conflicts": [],
    }
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (target / "index.html").write_text("immutable compose", encoding="utf-8")
    for index, body in enumerate(bodies):
        payload = json.dumps(body.model_dump(mode="json"))
        (target / "members" / f"{index}.html").write_text(
            f'<script type="application/json" id="antiek-artifact-v1">{payload}</script>',
            encoding="utf-8",
        )
    return compose_id


def _bodies(node_a: str, node_b: str) -> list[ResearchArtifactBody]:
    return [
        ResearchArtifactBody(
            investigation_id="inv-a", problem_question="A?",
            insights=[ArtifactInsight(node_id=node_a, text="A")],
            open_questions=[ArtifactQuestion(node_id=node_b, text="B?")],
        ),
        ResearchArtifactBody(
            investigation_id="inv-b", problem_question="B?",
            insights=[ArtifactInsight(node_id=node_a, text="A repeated")],
            open_questions=[ArtifactQuestion(node_id=node_a, text="A conflicted")],
        ),
    ]


def _seed_nodes(db: str) -> tuple[str, str]:
    with connect_write(db, purpose="test/seed-compose-write") as con:
        node_a = insert_node(
            con, canonical_label="A", node_type="insight",
            graph_scope="cross_domain", investigation_id="inv-a",
        )
        node_b = insert_node(
            con, canonical_label="B", node_type="question",
            graph_scope="cross_domain", investigation_id="inv-a",
        )
    return node_a, node_b


def test_promote_preserves_snapshot_order_dedupes_and_reports_conflicts(compose_write_env):
    db, root = compose_write_env
    node_a, node_b = _seed_nodes(db)
    compose_id = _write_compose(root, _bodies(node_a, node_b))

    result = promote_compose_to_write(compose_id, db_path=db)

    assert result.snapshot_occurrence_count == 4
    assert result.unique_block_count == 2
    assert result.duplicate_count == 2
    assert result.kind_conflict_count == 1
    assert result.dangling_count == 0
    con = duckdb.connect(db, read_only=True)
    try:
        assert con.execute(
            "SELECT investigation_root_id FROM deliverables WHERE deliverable_id = ?",
            [result.deliverable_id],
        ).fetchone() == (None,)
        assert con.execute(
            "SELECT node_id, block_kind FROM outline_blocks WHERE section_id = ? ORDER BY block_index",
            [result.section_id],
        ).fetchall() == [(node_a, "insight"), (node_b, "open_question")]
    finally:
        con.close()


def test_promote_is_sequentially_and_concurrently_idempotent(compose_write_env):
    db, root = compose_write_env
    compose_id = _write_compose(root, _bodies(*_seed_nodes(db)))
    first = promote_compose_to_write(compose_id, db_path=db)
    second = promote_compose_to_write(compose_id, db_path=db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        concurrent = list(pool.map(lambda _: promote_compose_to_write(compose_id, db_path=db), range(2)))
    assert second.reused is True
    assert {item.deliverable_id for item in [first, second, *concurrent]} == {first.deliverable_id}
    assert {item.section_id for item in [first, second, *concurrent]} == {first.section_id}


def test_integrity_failure_happens_before_any_workspace_write(compose_write_env):
    db, root = compose_write_env
    compose_id = _write_compose(root, _bodies(*_seed_nodes(db)))
    member = root / "composes" / compose_id / "members" / "1.html"
    member.write_text(member.read_text().replace('"investigation_id": "inv-b"', '"investigation_id": "inv-swapped"'))
    with pytest.raises(ComposeIntegrityError):
        promote_compose_to_write(compose_id, db_path=db)
    con = duckdb.connect(db, read_only=True)
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM artifact_compose_write_workspaces").fetchone()[0] == 0
    finally:
        con.close()


def test_transaction_rolls_back_deliverable_section_and_blocks(compose_write_env, monkeypatch):
    db, root = compose_write_env
    compose_id = _write_compose(root, _bodies(*_seed_nodes(db)))
    import substrate.write.promote_compose as module

    real_place = module.place_block
    calls = 0

    def fail_second(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected placement failure")
        return real_place(*args, **kwargs)

    monkeypatch.setattr(module, "place_block", fail_second)
    with pytest.raises(RuntimeError, match="injected"):
        promote_compose_to_write(compose_id, db_path=db)
    con = duckdb.connect(db, read_only=True)
    try:
        for table in ("deliverables", "deliverable_sections", "outline_blocks", "artifact_compose_write_workspaces"):
            assert con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0
    finally:
        con.close()


def test_dangling_snapshot_node_is_retained(compose_write_env):
    db, root = compose_write_env
    node_a, node_b = _seed_nodes(db)
    compose_id = _write_compose(root, _bodies(node_a, node_b))
    with connect_write(db, purpose="test/delete-compose-node") as con:
        con.execute("DELETE FROM nodes WHERE node_id = ?", [node_b])
    result = promote_compose_to_write(compose_id, db_path=db)
    assert result.unique_block_count == 2
    assert result.dangling_count == 1


def test_delete_cannot_race_between_validation_and_mapping_commit(compose_write_env, monkeypatch):
    db, root = compose_write_env
    compose_id = _write_compose(root, _bodies(*_seed_nodes(db)))
    import substrate.write.promote_compose as module

    validated = Event()
    release = Event()
    real_validate = module._validated_occurrences

    def pause_after_validation(value: str):
        result = real_validate(value)
        validated.set()
        assert release.wait(timeout=5)
        return result

    monkeypatch.setattr(module, "_validated_occurrences", pause_after_validation)

    def may_delete() -> bool:
        with connect_read(db) as con:
            return con.execute(
                "SELECT 1 FROM artifact_compose_write_workspaces WHERE compose_id = ?",
                [compose_id],
            ).fetchone() is None

    with ThreadPoolExecutor(max_workers=2) as pool:
        promoted = pool.submit(promote_compose_to_write, compose_id, db_path=db)
        assert validated.wait(timeout=5)
        deleted = pool.submit(
            delete_compose_draft, compose_id, before_delete=may_delete,
        )
        release.set()
        result = promoted.result(timeout=10)
        with pytest.raises(PermissionError):
            deleted.result(timeout=10)
    assert result.compose_id == compose_id
    assert (root / "composes" / compose_id / "manifest.json").is_file()
