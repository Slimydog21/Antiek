"""The §1.11 revise primitive: the sole writer of derived-asset revisions.

THREAD-CONTRACT §1.11 ("Store", "Atomicity") and the binding record
docs/decisions/safe-derived-asset-merge-boundary.md; the choices made here are
docs/decisions/derived-asset-revise-primitive.md.

Callers hold ``runtime.db_lock.connect_write`` and call :func:`revise` inside
one ``BEGIN … COMMIT`` (``substrate.write.event_outbox.eventful_transaction``).
That one transaction:

1. checks the caller's expected revision against the head it loaded;
2. checks the parent manifest against its member rows;
3. inserts the new revision, copying the parent's bytes, hashes and sanitizer
   identity (a revise never re-renders);
4. carries every per-revision child row forward under the new id, except the
   rows the caller's patch replaces (:data:`CHILD_TABLES`);
5. records the operation, which is both the idempotency record and the review
   receipt the revision's ``review_id`` names;
6. advances the pointer with ``UPDATE … RETURNING``, bound to the head's
   revision, content hash and generation. An empty result is a moved head;
   DuckDB's rowcount is not a CAS signal;
7. touches ``derived_assets.updated_at``.

A raise at any step rolls all of it back, so no committed revision is ever
unsealed. There is no DDL here and no update or delete of a revision row.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from runtime.db_lock import LockedConnection, ReadConnection

# The acknowledgement version of a revise the operator made directly, with no
# merge-draft review (A2). Its ``review_id`` is the operation receipt's id.
OPERATOR_DIRECT_ACKNOWLEDGEMENT = "operator_direct.v1"

_Connection = ReadConnection | LockedConnection
Checkpoint = Callable[[str], None]


class NotFound(Exception):
    """A missing asset, another owner's, or one with no revision: one answer."""


class RevisionMoved(Exception):
    """The expected revision is not the current one."""

    def __init__(self, current_revision_id: str) -> None:
        super().__init__(current_revision_id)
        self.current_revision_id = current_revision_id


class IdempotencyConflict(Exception):
    """The idempotency key was used for a different request."""


class RevisionIntegrityError(Exception):
    """Stored revision state disagrees with itself; nothing is written."""


@dataclass(frozen=True)
class Head:
    derived_asset_id: str
    revision_id: str
    content_sha256: str
    generation: int


@dataclass(frozen=True)
class StoredOperation:
    """A committed operation. ``response_json`` is the exact answer, so a
    replay returns the same bytes."""

    operation_id: str
    derived_asset_id: str
    revision_id: str
    operation: str
    request_sha256: str
    response_json: str


@dataclass(frozen=True)
class ChildPatch:
    """The rows of one child table that the new revision replaces.

    Parent rows matching every ``match`` column are not carried; ``rows`` are
    inserted in their place. Each row names every column except
    ``derived_asset_id`` and ``revision_id`` it sets, and must itself match.
    """

    match: Mapping[str, object]
    rows: Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class ChildTable:
    """How one per-revision table is carried into a new revision.

    ``patchable_by``: the columns a patch may match on (none: no patch).
    ``scoped_by``: ``(table, columns)`` — a row is carried only when the new
    revision holds a row of ``table`` with the same columns. Informs are
    scoped by the block inventory, so a block a revise removes loses its
    informs (R-LB8-4).
    ``before_carry``: a check run on the parent before its rows are copied.
    """

    table: str
    patchable_by: frozenset[str] = frozenset()
    scoped_by: tuple[str, tuple[str, ...]] | None = None
    before_carry: Callable[[LockedConnection, str, str], None] | None = None


def _members_legacy_rule(con: LockedConnection, asset_id: str, parent_revision_id: str) -> None:
    """§1.11 rev 7: the first revise after a legacy revision carries one
    ``legacy_unverified`` member per Write block. That rule needs the W3
    member rebuild (``member_origin``, ``block_id``), which main's member table
    does not have, so nothing is legacy today. Once the rebuild lands and a
    parent holds a legacy member, a revise refuses until the rule is built:
    carrying legacy evidence without it would clear the export hold."""
    columns = _columns(con, "derived_asset_revision_members")
    if "member_origin" not in columns:
        return
    legacy = con.execute(
        "SELECT 1 FROM derived_asset_revision_members WHERE derived_asset_id = ? "
        "AND revision_id = ? AND member_origin = 'legacy' LIMIT 1",
        [asset_id, parent_revision_id],
    ).fetchone()
    if legacy is not None:
        raise RevisionIntegrityError("a legacy parent needs the §1.11 legacy rule, which is not built")


# Every table whose rows belong to one revision, in insertion order (a table
# that references another child comes after it). A revise copies each forward;
# tests/test_derived_asset_repository.py (T26) fails when a table bound to a
# revision is neither here nor named as not carried. LB-4b's fork and merge and
# LB-5's span ledger add their tables here and reuse :func:`revise`.
CHILD_TABLES: Mapping[str, ChildTable] = MappingProxyType(
    {
        "derived_asset_revision_members": ChildTable(
            "derived_asset_revision_members", before_carry=_members_legacy_rule
        ),
        "derived_asset_revision_blocks": ChildTable(
            "derived_asset_revision_blocks", patchable_by=frozenset({"block_id"})
        ),
        "derived_asset_block_informs": ChildTable(
            "derived_asset_block_informs",
            patchable_by=frozenset({"block_id"}),
            scoped_by=("derived_asset_revision_blocks", ("block_id",)),
        ),
    }
)


def canonical_json(value: object) -> str:
    """Sorted keys, no whitespace, UTF-8 text, no NaN."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _columns(con: LockedConnection, table: str) -> list[str]:
    """The live columns of a child table other than its revision key, in
    table order. Read from the catalog so a column added later is carried
    without a code change."""
    names = [
        str(row[0])
        for row in con.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'main' "
            "AND table_name = ? ORDER BY ordinal_position",
            [table],
        ).fetchall()
    ]
    if not {"derived_asset_id", "revision_id"} <= set(names):
        raise RevisionIntegrityError(f"{table} is not keyed by revision")
    return [name for name in names if name not in ("derived_asset_id", "revision_id")]


def _checkpoint(checkpoint: Checkpoint | None, name: str) -> None:
    if checkpoint is not None:
        checkpoint(name)


def _require_transaction(con: LockedConnection) -> None:
    if not getattr(con, "in_explicit_transaction", False):
        raise RuntimeError("revisions are written inside one explicit transaction")


def current_head(con: _Connection, asset_id: str) -> Head | None:
    row = con.execute(
        "SELECT current_revision_id, current_content_sha256, generation "
        "FROM derived_asset_current_revisions WHERE derived_asset_id = ?",
        [asset_id],
    ).fetchone()
    if row is None:
        return None
    return Head(asset_id, str(row[0]), str(row[1]), int(row[2]))


def load_owned_head(con: _Connection, asset_id: str, *, owner_user_id: str) -> Head:
    """The requester's asset at its current revision. A missing asset, another
    owner's, and one with no revision all raise the same :class:`NotFound`."""
    row = con.execute(
        "SELECT p.current_revision_id, p.current_content_sha256, p.generation "
        "FROM derived_asset_current_revisions AS p "
        "JOIN derived_assets AS a ON a.derived_asset_id = p.derived_asset_id "
        "WHERE p.derived_asset_id = ? AND a.owner_user_id = ?",
        [asset_id, owner_user_id],
    ).fetchone()
    if row is None:
        raise NotFound()
    return Head(asset_id, str(row[0]), str(row[1]), int(row[2]))


def find_operation(con: _Connection, *, owner_user_id: str, idempotency_key: str) -> StoredOperation | None:
    row = con.execute(
        "SELECT operation_id, derived_asset_id, revision_id, operation, request_sha256, response_json "
        "FROM derived_asset_operations WHERE owner_user_id = ? AND idempotency_key = ?",
        [owner_user_id, idempotency_key],
    ).fetchone()
    if row is None:
        return None
    return StoredOperation(*(str(value) for value in row))


def block_in_revision(con: _Connection, head: Head, block_id: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM derived_asset_revision_blocks "
        "WHERE derived_asset_id = ? AND revision_id = ? AND block_id = ?",
        [head.derived_asset_id, head.revision_id, block_id],
    ).fetchone()
    return row is not None


def check_expected(head: Head, expected_revision_id: str) -> None:
    """The compare half of compare-and-set: the caller's base is the head."""
    if expected_revision_id != head.revision_id:
        raise RevisionMoved(head.revision_id)


def _verify_manifest(con: LockedConnection, asset_id: str, revision_id: str, manifest_json: str) -> None:
    """The manifest lists exactly the revision's member rows, in order (the
    binding record: "validate the canonical manifest's member count/order
    against its materialized member rows")."""
    try:
        manifest = json.loads(manifest_json)
    except ValueError as exc:
        raise RevisionIntegrityError("the manifest is not JSON") from exc
    if not isinstance(manifest, list):
        raise RevisionIntegrityError("the manifest is not a list")
    rows = con.execute(
        "SELECT member_index, projection_id FROM derived_asset_revision_members "
        "WHERE derived_asset_id = ? AND revision_id = ? ORDER BY member_index",
        [asset_id, revision_id],
    ).fetchall()
    if len(manifest) != len(rows):
        raise RevisionIntegrityError("the manifest's member count disagrees with its member rows")
    for entry, (member_index, projection_id) in zip(manifest, rows, strict=True):
        if not isinstance(entry, dict):
            raise RevisionIntegrityError("a manifest entry is not an object")
        index = entry.get("member_index")
        if type(index) is not int or index != member_index:
            raise RevisionIntegrityError("the manifest's member order disagrees with its member rows")
        if "projection_id" in entry and entry["projection_id"] != projection_id:
            raise RevisionIntegrityError("a manifest entry names another projection")


def _carry_forward(
    con: LockedConnection,
    child: ChildTable,
    asset_id: str,
    parent_revision_id: str,
    revision_id: str,
    patch: ChildPatch | None,
) -> list[str]:
    columns = _columns(con, child.table)
    if child.before_carry is not None:
        child.before_carry(con, asset_id, parent_revision_id)
    listed = ", ".join(_quote(column) for column in columns)
    selected = ", ".join(f"p.{_quote(column)}" for column in columns)
    sql = (
        f"INSERT INTO {child.table} (derived_asset_id, revision_id, {listed}) "
        f"SELECT p.derived_asset_id, ?, {selected} FROM {child.table} AS p "
        "WHERE p.derived_asset_id = ? AND p.revision_id = ?"
    )
    params: list[Any] = [revision_id, asset_id, parent_revision_id]
    if child.scoped_by is not None:
        scope_table, scope_columns = child.scoped_by
        joined = " AND ".join(f"s.{_quote(c)} = p.{_quote(c)}" for c in scope_columns)
        sql += (
            f" AND EXISTS (SELECT 1 FROM {scope_table} AS s WHERE s.derived_asset_id = p.derived_asset_id "
            f"AND s.revision_id = ? AND {joined})"
        )
        params.append(revision_id)
    if patch is not None:
        replaced = " AND ".join(f"p.{_quote(column)} IS NOT DISTINCT FROM ?" for column in patch.match)
        sql += f" AND NOT ({replaced})"
        params.extend(patch.match.values())
    con.execute(sql, params)
    return columns


def _insert_patch_rows(
    con: LockedConnection,
    child: ChildTable,
    columns: Sequence[str],
    asset_id: str,
    revision_id: str,
    patch: ChildPatch,
) -> None:
    for row in patch.rows:
        unknown = set(row) - set(columns)
        if unknown:
            raise ValueError(f"{child.table} has no column(s) {sorted(unknown)}")
        if any(row.get(column) != value for column, value in patch.match.items()):
            raise ValueError(f"a {child.table} patch row falls outside what the patch replaces")
        names = list(row)
        placeholders = ", ".join("?" for _ in range(len(names) + 2))
        con.execute(
            f"INSERT INTO {child.table} (derived_asset_id, revision_id, "
            f"{', '.join(_quote(name) for name in names)}) VALUES ({placeholders})",
            [asset_id, revision_id, *(row[name] for name in names)],
        )


def revise(
    con: LockedConnection,
    *,
    head: Head,
    expected_revision_id: str,
    owner_user_id: str,
    idempotency_key: str,
    request_sha256: str,
    operation: str,
    patches: Mapping[str, ChildPatch],
    block_ids: Sequence[str],
    build_answer: Callable[[str], Mapping[str, object]],
    checkpoint: Checkpoint | None = None,
) -> StoredOperation:
    """Commit one ``revise`` of ``head`` inside the caller's transaction.

    Raises :class:`RevisionMoved` when ``expected_revision_id`` is not the
    head or the pointer moved after the head was loaded, and
    :class:`RevisionIntegrityError` when the parent disagrees with itself.
    ``build_answer(revision_id)`` is the operation's answer, stored as its
    canonical JSON so a replay is byte-identical. ``checkpoint`` is a test
    seam called between steps.
    """
    _require_transaction(con)
    check_expected(head, expected_revision_id)
    for table, requested in patches.items():
        child = CHILD_TABLES.get(table)
        if child is None:
            raise ValueError(f"{table} is not a per-revision child table")
        if not requested.match or not set(requested.match) <= child.patchable_by:
            raise ValueError(f"a {table} patch may match only on {sorted(child.patchable_by)}")
    asset_id = head.derived_asset_id
    parent = con.execute(
        "SELECT manifest_json, content_sha256 FROM derived_asset_revisions "
        "WHERE derived_asset_id = ? AND revision_id = ?",
        [asset_id, head.revision_id],
    ).fetchone()
    if parent is None:
        raise RevisionIntegrityError("the current pointer names no revision")
    _verify_manifest(con, asset_id, head.revision_id, str(parent[0]))

    revision_id = f"rev-{uuid.uuid4().hex}"
    operation_id = f"dop-{uuid.uuid4().hex}"
    inserted = con.execute(
        "INSERT INTO derived_asset_revisions (derived_asset_id, revision_id, operation_kind, "
        "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
        "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, "
        "parent_revision_id, restored_from_revision_id, metadata_json) "
        "SELECT derived_asset_id, ?, 'revise', canonical_html, canonical_byte_count, content_sha256, "
        "manifest_json, manifest_sha256, sanitizer_policy, sanitizer_version, ?, ?, revision_id, NULL, ? "
        "FROM derived_asset_revisions WHERE derived_asset_id = ? AND revision_id = ? RETURNING revision_id",
        [
            revision_id,
            operation_id,
            OPERATOR_DIRECT_ACKNOWLEDGEMENT,
            canonical_json({"operation": operation, "block_ids": list(block_ids)}),
            asset_id,
            head.revision_id,
        ],
    ).fetchall()
    if len(inserted) != 1:
        raise RevisionIntegrityError("the parent revision could not be copied")

    for table, child in CHILD_TABLES.items():
        patch = patches.get(table)
        columns = _carry_forward(con, child, asset_id, head.revision_id, revision_id, patch)
        if patch is not None:
            _insert_patch_rows(con, child, columns, asset_id, revision_id, patch)
    _checkpoint(checkpoint, "after_child_copy")

    response_json = canonical_json(build_answer(revision_id))
    con.execute(
        "INSERT INTO derived_asset_operations (operation_id, owner_user_id, idempotency_key, "
        "derived_asset_id, revision_id, operation, request_sha256, response_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [operation_id, owner_user_id, idempotency_key, asset_id, revision_id, operation,
         request_sha256, response_json],
    )
    _checkpoint(checkpoint, "after_operation_insert")

    _checkpoint(checkpoint, "before_pointer_update")
    advanced = con.execute(
        "UPDATE derived_asset_current_revisions SET current_revision_id = ?, "
        "current_content_sha256 = ?, generation = generation + 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE derived_asset_id = ? AND current_revision_id = ? AND current_content_sha256 = ? "
        "AND generation = ? RETURNING generation",
        [revision_id, str(parent[1]), asset_id, head.revision_id, head.content_sha256, head.generation],
    ).fetchall()
    if len(advanced) != 1:
        moved = current_head(con, asset_id)
        raise RevisionMoved(moved.revision_id if moved is not None else head.revision_id)
    _checkpoint(checkpoint, "after_pointer_update")

    # No RETURNING here: DuckDB 1.5 plans ``UPDATE … RETURNING`` on a row
    # other tables reference as a delete and insert, and refuses it. The row
    # exists: the pointer just advanced references it. This is a timestamp,
    # not a compare-and-set; the pointer above is the CAS.
    con.execute("UPDATE derived_assets SET updated_at = CURRENT_TIMESTAMP WHERE derived_asset_id = ?", [asset_id])
    _checkpoint(checkpoint, "after_asset_touch")
    return StoredOperation(operation_id, asset_id, revision_id, operation, request_sha256, response_json)


def create_revision(
    con: LockedConnection,
    *,
    asset_id: str,
    owner_user_id: str,
    asset_kind: str,
    title: str,
    canonical_html: str,
    manifest_json: str,
    sanitizer_policy: str,
    sanitizer_version: str,
    review_id: str,
    acknowledgement_version: str,
    blocks: Sequence[str],
    members: Sequence[Mapping[str, object]] = (),
) -> Head:
    """Revision 1 of a new asset (§1.11 ``create``), inside the caller's
    transaction: the asset, the revision, its members and block inventory,
    and the pointer at generation 1.

    LB-8 gives this no production caller; it seeds test fixtures. The W3
    Write revision writer owns revision 1 of ``write:<deliverable_id>``.
    """
    _require_transaction(con)
    body = canonical_html.encode("utf-8")
    content_sha256 = hashlib.sha256(body).hexdigest()
    revision_id = f"rev-{uuid.uuid4().hex}"
    con.execute(
        "INSERT INTO derived_assets (derived_asset_id, title, asset_kind, owner_user_id) VALUES (?, ?, ?, ?)",
        [asset_id, title, asset_kind, owner_user_id],
    )
    con.execute(
        "INSERT INTO derived_asset_revisions (derived_asset_id, revision_id, operation_kind, "
        "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
        "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version) "
        "VALUES (?, ?, 'create', ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [asset_id, revision_id, canonical_html, len(body), content_sha256, manifest_json,
         hashlib.sha256(manifest_json.encode("utf-8")).hexdigest(), sanitizer_policy,
         sanitizer_version, review_id, acknowledgement_version],
    )
    for member_index, member in enumerate(members):
        con.execute(
            "INSERT INTO derived_asset_revision_members (derived_asset_id, revision_id, member_index, "
            "projection_id, source_asset_id, source_document_id, source_sha256, hosted_html_sha256, "
            "investigation_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [asset_id, revision_id, member_index, member["projection_id"], member["source_asset_id"],
             member["source_document_id"], member["source_sha256"], member["hosted_html_sha256"],
             member.get("investigation_id")],
        )
    for block_index, block_id in enumerate(blocks):
        con.execute(
            "INSERT INTO derived_asset_revision_blocks (derived_asset_id, revision_id, block_index, block_id) "
            "VALUES (?, ?, ?, ?)",
            [asset_id, revision_id, block_index, block_id],
        )
    _verify_manifest(con, asset_id, revision_id, manifest_json)
    con.execute(
        "INSERT INTO derived_asset_current_revisions (derived_asset_id, current_revision_id, "
        "current_content_sha256, generation) VALUES (?, ?, ?, 1)",
        [asset_id, revision_id, content_sha256],
    )
    return Head(asset_id, revision_id, content_sha256, 1)


__all__ = [
    "CHILD_TABLES",
    "OPERATOR_DIRECT_ACKNOWLEDGEMENT",
    "ChildPatch",
    "ChildTable",
    "Head",
    "IdempotencyConflict",
    "NotFound",
    "RevisionIntegrityError",
    "RevisionMoved",
    "StoredOperation",
    "block_in_revision",
    "canonical_json",
    "check_expected",
    "create_revision",
    "current_head",
    "find_operation",
    "load_owned_head",
    "revise",
]
