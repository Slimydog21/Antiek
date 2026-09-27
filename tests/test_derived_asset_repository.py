"""The §1.11 revise primitive and its V23 schema (LB-8).

``substrate/derived_assets/repository.py`` is the sole writer of derived-asset
revisions. One ``connect_write`` transaction inserts the revision, carries
every per-revision child row forward, records the operation, and advances the
pointer with ``UPDATE … RETURNING`` (docs/decisions/safe-derived-asset-merge-
boundary.md). These tests hold that at the repository layer: fault injection
at every step leaves nothing behind (T25), the child-table registry covers
every table bound to a revision (T26), a revise keeps the parent's bytes
(T27), and V23 reaches existing databases through the warm probe (T28).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from runtime.db_lock import connect_read, connect_write, flush_warm_writers
from substrate.graph import schema as schema_mod
from substrate.graph.ops import insert_document
from substrate.graph.schema import SCHEMA_TABLES, _schema_is_present, init_database_at_path
from substrate.write.event_outbox import eventful_transaction

ROOT = Path(__file__).resolve().parents[1]
BODY_HTML = "<article><p>One.</p><p>Two.</p></article>"
ASSET = "write:dlv-1"
OWNER = "__operator__"
H1 = hashlib.sha256(b"source-one").hexdigest()
H2 = hashlib.sha256(b"hosted-one").hexdigest()
V23_TABLES = ("derived_asset_revision_blocks", "derived_asset_block_informs", "derived_asset_operations")
# A table bound to a revision that is deliberately NOT carried forward, with
# the reason. Anything else bound to a revision must have a copier.
NOT_CARRIED = {
    "derived_asset_operations": "one operation's receipt; it names the revision that operation produced",
}


@pytest.fixture
def db(tmp_path: Path) -> Iterator[str]:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="test/docs") as con:
        for document_id in ("docA", "docB", "docC"):
            insert_document(
                con, document_id=document_id, source_tier=2, document_type="paper",
                title=document_id, content_class="public_domain",
            )
    yield path
    flush_warm_writers(path)


def _members(n: int) -> list[dict[str, Any]]:
    return [
        {
            "projection_id": f"projection-{i}",
            "source_asset_id": f"source-{i}",
            "source_document_id": f"document-{i}",
            "source_sha256": H1,
            "hosted_html_sha256": H2,
            "investigation_id": None if i else "inv-1",
        }
        for i in range(n)
    ]


def _manifest(n: int) -> str:
    return json.dumps(
        [{"member_index": i, "projection_id": f"projection-{i}"} for i in range(n)],
        sort_keys=True, separators=(",", ":"),
    )


def _seed(db: str, *, members: int = 0, blocks: tuple[str, ...] = ("b-1", "b-2")) -> Any:
    from substrate.derived_assets.repository import create_revision

    with connect_write(db, purpose="test/seed") as con, con.transaction():
        return create_revision(
            con, asset_id=ASSET, owner_user_id=OWNER, asset_kind="document", title="Doc",
            canonical_html=BODY_HTML, manifest_json=_manifest(members), sanitizer_policy="antiek-write",
            sanitizer_version="7", review_id="seed-review", acknowledgement_version="operator_direct.v1",
            blocks=list(blocks), members=_members(members),
        )


def _informs_patch(block_id: str, *document_ids: str) -> Any:
    from substrate.derived_assets.repository import ChildPatch

    return {
        "derived_asset_block_informs": ChildPatch(
            match={"block_id": block_id},
            rows=[
                {"block_id": block_id, "ordinal": i, "document_id": d, "anchor": None}
                for i, d in enumerate(document_ids)
            ],
        )
    }


def _revise(
    con: Any,
    head: Any,
    *,
    key: str = "k-1",
    block_id: str = "b-1",
    docs: tuple[str, ...] = ("docA",),
    checkpoint: Callable[[str], None] | None = None,
) -> Any:
    from substrate.derived_assets.repository import revise

    return revise(
        con,
        head=head,
        expected_revision_id=head.revision_id,
        owner_user_id=OWNER,
        idempotency_key=key,
        request_sha256=hashlib.sha256(key.encode()).hexdigest(),
        operation="informs",
        patches=_informs_patch(block_id, *docs),
        block_ids=[block_id],
        build_answer=lambda revision_id: {"revision_id": revision_id, "block_id": block_id},
        checkpoint=checkpoint,
    )


_ALL = (
    "derived_assets", "derived_asset_revisions", "derived_asset_revision_members",
    "derived_asset_current_revisions", *V23_TABLES, "write_event_outbox",
)


def _state(db: str) -> dict[str, Any]:
    con = connect_read(db)
    try:
        out: dict[str, Any] = {t: con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in _ALL}
        out["pointer"] = con.execute(
            "SELECT current_revision_id, current_content_sha256, generation, updated_at "
            "FROM derived_asset_current_revisions WHERE derived_asset_id = ?", [ASSET]
        ).fetchall()
        out["asset_updated_at"] = con.execute(
            "SELECT updated_at FROM derived_assets WHERE derived_asset_id = ?", [ASSET]
        ).fetchall()
        return out
    finally:
        con.close()


class Boom(RuntimeError):
    pass


# ── T25: atomicity ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(  # type: ignore[untyped-decorator]
    "point",
    ["after_child_copy", "after_operation_insert", "before_pointer_update", "after_pointer_update",
     "after_asset_touch"],
)
def test_t25_a_fault_at_any_step_leaves_nothing_behind(db: str, point: str) -> None:
    """Kills M16 (the revision committed before the pointer)."""
    head = _seed(db)
    before = _state(db)
    reached: list[str] = []

    def fault(name: str) -> None:
        reached.append(name)
        if name == point:
            raise Boom(name)

    with connect_write(db, purpose="test/fault") as con, pytest.raises(Boom), eventful_transaction(con, "write-dlv-1"):
        _revise(con, head, checkpoint=fault)
    assert point in reached
    assert _state(db) == before


def test_t25_a_generation_bumped_under_the_writer_is_revision_moved(db: str) -> None:
    """Kills M17 (an empty RETURNING ignored) and the CAS half of M1."""
    from substrate.derived_assets.repository import RevisionMoved

    head = _seed(db)
    before = _state(db)

    with connect_write(db, purpose="test/bump") as con:

        def bump(name: str) -> None:
            if name == "before_pointer_update":
                con.execute(
                    "UPDATE derived_asset_current_revisions SET generation = generation + 1 "
                    "WHERE derived_asset_id = ?", [ASSET]
                )

        with pytest.raises(RevisionMoved) as moved, eventful_transaction(con, "write-dlv-1"):
            _revise(con, head, checkpoint=bump)
    assert moved.value.current_revision_id == head.revision_id
    assert _state(db) == before


def test_t25_a_head_that_moved_after_it_was_loaded_is_refused_by_the_cas(db: str) -> None:
    """The precheck passes here (the stale head agrees with itself), so only
    the pointer's ``UPDATE … RETURNING`` can refuse it. Kills M17 and the CAS
    half of M1."""
    from substrate.derived_assets.repository import RevisionMoved, load_owned_head

    head = _seed(db)
    with connect_write(db, purpose="test/moved") as con:
        with eventful_transaction(con, "write-dlv-1"):
            _revise(con, head, key="k-first")
        current = load_owned_head(con, ASSET, owner_user_id=OWNER)
    before = _state(db)
    with connect_write(db, purpose="test/moved-2") as con, pytest.raises(RevisionMoved) as moved, eventful_transaction(con, "write-dlv-1"):
        _revise(con, head, key="k-second")
    assert moved.value.current_revision_id == current.revision_id
    assert _state(db) == before


# ── T26: the carry-forward registry ─────────────────────────────────────────


def _revision_bound_tables(con: Any) -> dict[str, list[str]]:
    """table -> the tables its foreign keys reference, for every table whose
    foreign key names ``revision_id``."""
    rows = con.execute(
        "SELECT table_name, constraint_column_names, constraint_text FROM duckdb_constraints() "
        "WHERE schema_name = 'main' AND constraint_type = 'FOREIGN KEY'"
    ).fetchall()
    bound: dict[str, list[str]] = {}
    for table, columns, text in rows:
        if "revision_id" not in columns:
            continue
        referenced = re.search(r"REFERENCES\s+(\w+)\s*\(", text)
        assert referenced is not None, text
        bound.setdefault(table, []).append(referenced.group(1))
    return bound


def test_t26_every_table_bound_to_a_revision_is_carried_or_named(db: str) -> None:
    """Kills M18 (members left out of CHILD_TABLES)."""
    from substrate.derived_assets.repository import CHILD_TABLES

    con = connect_read(db)
    try:
        bound = _revision_bound_tables(con)
    finally:
        con.close()
    assert "derived_asset_revision_members" in bound
    order = list(CHILD_TABLES)
    for table, referenced in bound.items():
        assert table in SCHEMA_TABLES, table
        if table in NOT_CARRIED:
            assert table not in CHILD_TABLES
            continue
        assert table in CHILD_TABLES, f"{table} is bound to a revision but has no carry-forward copier"
        # A child that references another child is copied after it.
        for parent in referenced:
            if parent in CHILD_TABLES:
                assert order.index(parent) < order.index(table), (parent, table)
    assert set(CHILD_TABLES) <= set(bound)


def _member_rows(db: str, revision_id: str) -> list[tuple[Any, ...]]:
    con = connect_read(db)
    try:
        return con.execute(
            "SELECT member_index, projection_id, source_asset_id, source_document_id, source_sha256, "
            "hosted_html_sha256, investigation_id FROM derived_asset_revision_members "
            "WHERE derived_asset_id = ? AND revision_id = ? ORDER BY member_index",
            [ASSET, revision_id],
        ).fetchall()
    finally:
        con.close()


def _block_rows(db: str, revision_id: str) -> list[tuple[Any, ...]]:
    con = connect_read(db)
    try:
        return con.execute(
            "SELECT block_index, block_id FROM derived_asset_revision_blocks "
            "WHERE derived_asset_id = ? AND revision_id = ? ORDER BY block_index",
            [ASSET, revision_id],
        ).fetchall()
    finally:
        con.close()


def test_t26_members_and_blocks_are_copied_verbatim_and_the_parent_is_untouched(db: str) -> None:
    """Kills M18."""
    head = _seed(db, members=2, blocks=("b-1", "b-2", "b-3"))
    parent_members = _member_rows(db, head.revision_id)
    parent_blocks = _block_rows(db, head.revision_id)
    assert len(parent_members) == 2 and len(parent_blocks) == 3

    with connect_write(db, purpose="test/copy") as con, eventful_transaction(con, "write-dlv-1"):
        first = _revise(con, head)
    assert _member_rows(db, first.revision_id) == parent_members
    assert _block_rows(db, first.revision_id) == parent_blocks
    assert _member_rows(db, head.revision_id) == parent_members
    assert _block_rows(db, head.revision_id) == parent_blocks

    # A second revise off the first must pass the manifest check, which
    # needs the carried members to still match the carried manifest.
    from substrate.derived_assets.repository import load_owned_head

    with connect_write(db, purpose="test/copy-2") as con, eventful_transaction(con, "write-dlv-1"):
        second = _revise(con, load_owned_head(con, ASSET, owner_user_id=OWNER), key="k-2")
    assert _member_rows(db, second.revision_id) == parent_members


def test_t26_other_blocks_informs_are_carried_and_the_patched_block_replaced(db: str) -> None:
    from substrate.derived_assets.repository import load_owned_head

    head = _seed(db)
    with connect_write(db, purpose="test/carry") as con:
        with eventful_transaction(con, "w"):
            _revise(con, head, key="k-1", block_id="b-2", docs=("docC",))
        with eventful_transaction(con, "w"):
            _revise(con, load_owned_head(con, ASSET, owner_user_id=OWNER), key="k-2", docs=("docB", "docA"))
        with eventful_transaction(con, "w"):
            third = _revise(con, load_owned_head(con, ASSET, owner_user_id=OWNER), key="k-3", docs=("docA",))
        rows = con.execute(
            "SELECT block_id, ordinal, document_id FROM derived_asset_block_informs "
            "WHERE derived_asset_id = ? AND revision_id = ? ORDER BY block_id, ordinal",
            [ASSET, third.revision_id],
        ).fetchall()
    assert rows == [("b-1", 0, "docA"), ("b-2", 0, "docC")]


def test_a_block_a_revise_removes_loses_its_informs(db: str) -> None:
    """R-LB8-4: informs are carried only for blocks the new revision holds."""
    from substrate.derived_assets.repository import ChildPatch, load_owned_head, revise

    head = _seed(db)
    with connect_write(db, purpose="test/remove-block") as con:
        with eventful_transaction(con, "w"):
            with_b2 = _revise(con, head, key="k-1", block_id="b-2", docs=("docC",))
        current = load_owned_head(con, ASSET, owner_user_id=OWNER)
        with eventful_transaction(con, "w"):
            removed = revise(
                con, head=current, expected_revision_id=current.revision_id, owner_user_id=OWNER,
                idempotency_key="k-2", request_sha256=hashlib.sha256(b"k-2").hexdigest(), operation="test_remove",
                patches={"derived_asset_revision_blocks": ChildPatch(match={"block_id": "b-2"}, rows=[])},
                block_ids=["b-2"], build_answer=lambda revision_id: {"revision_id": revision_id},
            )
        blocks = con.execute(
            "SELECT block_id FROM derived_asset_revision_blocks WHERE revision_id = ? ORDER BY block_index",
            [removed.revision_id],
        ).fetchall()
        carried = con.execute(
            "SELECT count(*) FROM derived_asset_block_informs WHERE revision_id = ?", [removed.revision_id]
        ).fetchone()
        kept = con.execute(
            "SELECT document_id FROM derived_asset_block_informs WHERE revision_id = ? AND block_id = 'b-2'",
            [with_b2.revision_id],
        ).fetchall()
    assert blocks == [("b-1",)]
    assert carried == (0,)
    assert kept == [("docC",)]


def test_revise_refuses_to_run_outside_one_transaction(db: str) -> None:
    head = _seed(db)
    before = _state(db)
    with connect_write(db, purpose="test/no-transaction") as con, pytest.raises(RuntimeError):
        _revise(con, head)
    assert _state(db) == before


def test_a_patch_on_a_table_it_may_not_match_is_refused(db: str) -> None:
    from substrate.derived_assets.repository import ChildPatch, revise

    head = _seed(db, members=1)
    with connect_write(db, purpose="test/bad-patch") as con, pytest.raises(ValueError), eventful_transaction(con, "w"):
        revise(
            con, head=head, expected_revision_id=head.revision_id, owner_user_id=OWNER,
            idempotency_key="k", request_sha256=hashlib.sha256(b"k").hexdigest(), operation="informs",
            patches={"derived_asset_revision_members": ChildPatch(match={"member_index": 0}, rows=[])},
            block_ids=[], build_answer=lambda revision_id: {},
        )


# ── T27: a revise keeps the parent's bytes ──────────────────────────────────


def test_t27_the_new_revision_keeps_the_parents_bytes_and_records_the_operation(db: str) -> None:
    """Kills M20 (canonical_html re-rendered on revise)."""
    head = _seed(db, members=1)
    with connect_write(db, purpose="test/bytes") as con, eventful_transaction(con, "write-dlv-1"):
        stored = _revise(con, head)
    con = connect_read(db)
    try:
        cols = (
            "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
            "sanitizer_policy, sanitizer_version"
        )
        parent = con.execute(
            f"SELECT {cols} FROM derived_asset_revisions WHERE revision_id = ?", [head.revision_id]
        ).fetchone()
        child = con.execute(
            f"SELECT {cols} FROM derived_asset_revisions WHERE revision_id = ?", [stored.revision_id]
        ).fetchone()
        shape = con.execute(
            "SELECT operation_kind, parent_revision_id, restored_from_revision_id, review_id, "
            "acknowledgement_version, metadata_json FROM derived_asset_revisions WHERE revision_id = ?",
            [stored.revision_id],
        ).fetchone()
        operation = con.execute(
            "SELECT operation_id, owner_user_id, idempotency_key, derived_asset_id, revision_id, operation "
            "FROM derived_asset_operations WHERE operation_id = ?", [stored.operation_id]
        ).fetchone()
        pointer = con.execute(
            "SELECT current_revision_id, current_content_sha256, generation FROM derived_asset_current_revisions "
            "WHERE derived_asset_id = ?", [ASSET]
        ).fetchone()
    finally:
        con.close()
    assert child == parent
    assert shape[:3] == ("revise", head.revision_id, None)
    assert shape[3] == stored.operation_id and shape[3].startswith("dop-")
    assert shape[4] == "operator_direct.v1"
    assert json.loads(shape[5]) == {"operation": "informs", "block_ids": ["b-1"]}
    assert operation == (stored.operation_id, OWNER, "k-1", ASSET, stored.revision_id, "informs")
    assert pointer == (stored.revision_id, head.content_sha256, head.generation + 1)
    assert stored.revision_id.startswith("rev-") and stored.revision_id != head.revision_id


def test_a_manifest_that_disagrees_with_its_members_refuses_the_revise(db: str) -> None:
    from substrate.derived_assets.repository import RevisionIntegrityError

    head = _seed(db, members=1)
    with connect_write(db, purpose="test/drop-member") as con:
        con.execute("DELETE FROM derived_asset_revision_members WHERE derived_asset_id = ?", [ASSET])
    before = _state(db)
    with connect_write(db, purpose="test/integrity") as con, pytest.raises(RevisionIntegrityError), eventful_transaction(con, "write-dlv-1"):
        _revise(con, head)
    assert _state(db) == before


def test_create_refuses_a_manifest_that_disagrees_with_its_members(db: str) -> None:
    from substrate.derived_assets.repository import RevisionIntegrityError, create_revision

    with connect_write(db, purpose="test/create-integrity") as con, pytest.raises(RevisionIntegrityError), con.transaction():
        create_revision(
            con, asset_id=ASSET, owner_user_id=OWNER, asset_kind="document", title="Doc",
            canonical_html=BODY_HTML, manifest_json=_manifest(2), sanitizer_policy="p",
            sanitizer_version="1", review_id="r", acknowledgement_version="operator_direct.v1",
            blocks=["b-1"], members=_members(1),
        )
    assert _state(db)["derived_assets"] == 0


def test_a_legacy_member_fails_closed_until_the_legacy_rule_is_built(db: str) -> None:
    """§1.11 rev 7: the first revise after a legacy revision must carry
    ``legacy_unverified`` members. LB-8 does not build that rule, so once the
    W3 member rebuild gives members an origin, a legacy parent refuses."""
    from substrate.derived_assets.repository import RevisionIntegrityError

    head = _seed(db, members=1)
    with connect_write(db, purpose="test/legacy-column") as con:
        con.execute("ALTER TABLE derived_asset_revision_members ADD COLUMN member_origin TEXT")
        con.execute("UPDATE derived_asset_revision_members SET member_origin = 'legacy'")
    with connect_write(db, purpose="test/legacy") as con, pytest.raises(RevisionIntegrityError), eventful_transaction(con, "write-dlv-1"):
        _revise(con, head)


# ── T28: the V23 schema ─────────────────────────────────────────────────────


def test_t28_v23_exists_on_a_fresh_database(db: str) -> None:
    con = connect_read(db)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()}
    finally:
        con.close()
    assert set(V23_TABLES) <= tables
    assert set(V23_TABLES) <= set(SCHEMA_TABLES)


def test_t28_a_pre_v23_database_gets_v23_through_the_warm_probe(db: str) -> None:
    with connect_write(db, purpose="test/pre-v23") as con:
        for table in ("derived_asset_block_informs", "derived_asset_revision_blocks", "derived_asset_operations"):
            con.execute(f"DROP TABLE {table}")
    flush_warm_writers(db)
    schema_mod._INITIALIZED_PATHS.discard(db)
    assert _schema_is_present(db) is False
    init_database_at_path(db)
    schema_mod._INITIALIZED_PATHS.discard(db)
    assert _schema_is_present(db) is True


def test_t28_a_wrong_shaped_empty_v23_table_is_rebuilt(db: str) -> None:
    with connect_write(db, purpose="test/partial-v23") as con:
        con.execute("DROP TABLE derived_asset_operations")
        con.execute("CREATE TABLE derived_asset_operations (operation_id TEXT PRIMARY KEY)")
    flush_warm_writers(db)
    schema_mod._INITIALIZED_PATHS.discard(db)
    assert _schema_is_present(db) is False
    init_database_at_path(db)
    schema_mod._INITIALIZED_PATHS.discard(db)
    assert _schema_is_present(db) is True


def test_t28_a_populated_wrong_shaped_v23_table_is_never_dropped(db: str) -> None:
    with connect_write(db, purpose="test/populated-partial-v23") as con:
        con.execute("DROP TABLE derived_asset_operations")
        con.execute("CREATE TABLE derived_asset_operations (operation_id TEXT PRIMARY KEY)")
        con.execute("INSERT INTO derived_asset_operations VALUES ('dop-kept')")
    flush_warm_writers(db)
    schema_mod._INITIALIZED_PATHS.discard(db)
    with pytest.raises(schema_mod.SchemaCorruptionError):
        init_database_at_path(db)
    flush_warm_writers(db)
    con = duckdb.connect(db, read_only=True)
    try:
        assert con.execute("SELECT operation_id FROM derived_asset_operations").fetchall() == [("dop-kept",)]
    finally:
        con.close()


def test_t28_the_database_refuses_bad_informs_rows(db: str) -> None:
    head = _seed(db)
    with connect_write(db, purpose="test/constraints") as con:
        insert = (
            "INSERT INTO derived_asset_block_informs "
            "(derived_asset_id, revision_id, block_id, ordinal, document_id, anchor) VALUES (?, ?, ?, ?, ?, NULL)"
        )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(insert, [ASSET, head.revision_id, "b-not-in-revision", 0, "docA"])
        with pytest.raises(duckdb.ConstraintException):
            con.execute(insert, [ASSET, head.revision_id, "b-1", 50, "docA"])
        con.execute(insert, [ASSET, head.revision_id, "b-1", 0, "docA"])
        with pytest.raises(duckdb.ConstraintException):
            con.execute(insert, [ASSET, head.revision_id, "b-1", 1, "docA"])


# ── structural guards ───────────────────────────────────────────────────────

OWNED = (
    ROOT / "substrate/derived_assets/repository.py",
    ROOT / "substrate/derived_assets/informs.py",
    ROOT / "interfaces/research/api/derived_asset_routes.py",
)


def test_no_owned_file_uses_the_commit_boundary_validator() -> None:
    """The informs body is not the commit envelope; the validator would
    refuse it as unknown fields (spec §6.1)."""
    for path in OWNED:
        assert "validate_commit_boundary" not in path.read_text(encoding="utf-8"), path


def test_routes_and_repository_own_no_ddl() -> None:
    ddl = re.compile(r"\b(?:CREATE|ALTER|DROP)\s+(?:TABLE|INDEX|SEQUENCE)\b|\binit_database\b", re.IGNORECASE)
    for path in OWNED:
        assert not ddl.search(path.read_text(encoding="utf-8")), path


def test_the_repository_exposes_no_revision_update_or_delete() -> None:
    source = (ROOT / "substrate/derived_assets/repository.py").read_text(encoding="utf-8")
    assert not re.search(r"UPDATE\s+derived_asset_revisions\b", source, re.IGNORECASE)
    assert not re.search(r"DELETE\s+FROM\s+derived_asset", source, re.IGNORECASE)
    assert re.search(r"UPDATE\s+derived_asset_current_revisions\b.*RETURNING", source, re.IGNORECASE | re.DOTALL)
