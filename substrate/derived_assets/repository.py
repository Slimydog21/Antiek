"""The §1.11 revise primitive: the sole writer of derived-asset revisions.

THREAD-CONTRACT §1.11 ("Store", "Atomicity") and the binding record
docs/decisions/safe-derived-asset-merge-boundary.md; the choices made here are
docs/decisions/derived-asset-revise-primitive.md.

Callers hold ``runtime.db_lock.connect_write`` and call :func:`revise` or
:func:`create_revision` inside the caller's one transaction, opened with the
re-entrant ``con.transaction()``; they dispatch outbox rows only after it
commits. A revise, in that transaction:

1. checks the caller's expected revision against the head it loaded;
2. checks the parent manifest against its member rows;
3. inserts the new revision: the parent's bytes, hashes and sanitizer identity
   unchanged, or, for a body revise, the caller's :class:`RevisionBody`;
4. carries every per-revision child row forward under the new id, except the
   rows the caller's patch replaces and the rows of blocks the new revision no
   longer holds (:data:`CHILD_TABLES`), then checks the new manifest against
   the new member rows;
5. records the operation, which is both the idempotency record and the review
   receipt the revision's ``review_id`` names;
6. advances the pointer with ``UPDATE … RETURNING``, bound to the head's
   revision, content hash and generation. An empty result is a moved head;
   DuckDB's rowcount is not a CAS signal;
7. touches ``derived_assets.updated_at``;
8. enqueues one ``derived_asset.revised`` event in ``write_event_outbox`` on
   the caller's event log (rev 8.11 D1). The caller dispatches after commit.

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
from substrate.schemas.events import DerivedAssetRevisedPayload
from substrate.write.event_outbox import build_typed_envelope, enqueue_event

# The acknowledgement version of a revise the operator made directly, with no
# merge-draft review (A2). Its ``review_id`` is the operation receipt's id.
OPERATOR_DIRECT_ACKNOWLEDGEMENT = "operator_direct.v1"
# Keys the primitive owns in a revision's ``metadata_json``.
_RESERVED_METADATA = frozenset({"operation", "block_ids"})

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
class RevisionBody:
    """New bytes for a revision. Hashes and the byte count are computed here;
    the database CHECKs recompute them."""

    canonical_html: str
    manifest_json: str
    sanitizer_policy: str
    sanitizer_version: str


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

    Parent rows matching every ``match`` column are not carried, and ``rows``
    are inserted in their place; each row must itself match. ``match=None``
    replaces every parent row of the table (a rebuild, as a body revise does
    for its block inventory and members). A row names the columns it sets,
    never ``derived_asset_id`` or ``revision_id``.
    """

    match: Mapping[str, object] | None
    rows: Sequence[Mapping[str, object]]


@dataclass(frozen=True)
class ChildTable:
    """How one per-revision table is carried into a new revision.

    ``patchable_by``: the columns a keyed patch may match on.
    ``scoped_by``: ``(table, columns)``. A row is carried only when the new
    revision holds a row of ``table`` with the same values, or when those
    columns are NULL on the row, or absent from its table. Informs and
    block-bound members are scoped by the block inventory, so a block a revise
    removes loses its informs and members (R-LB8-4).
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


_BLOCK_SCOPE = ("derived_asset_revision_blocks", ("block_id",))

# Every table whose rows belong to one revision, in insertion order. The block
# inventory comes first: the tables scoped by it, and informs' foreign key,
# read the new revision's inventory. A revise copies each forward;
# tests/test_derived_asset_repository.py (T26) fails when a table bound to a
# revision is neither here nor named as not carried. W3's writer, LB-4b's fork
# and merge and LB-5's span ledger add their tables here and reuse
# :func:`revise`.
CHILD_TABLES: Mapping[str, ChildTable] = MappingProxyType(
    {
        "derived_asset_revision_blocks": ChildTable(
            "derived_asset_revision_blocks", patchable_by=frozenset({"block_id"})
        ),
        "derived_asset_revision_members": ChildTable(
            "derived_asset_revision_members", scoped_by=_BLOCK_SCOPE, before_carry=_members_legacy_rule
        ),
        "derived_asset_block_informs": ChildTable(
            "derived_asset_block_informs", patchable_by=frozenset({"block_id"}), scoped_by=_BLOCK_SCOPE
        ),
    }
)


def canonical_json(value: object) -> str:
    """Sorted keys, no whitespace, UTF-8 text, no NaN."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _revision_metadata(base: dict[str, object], extra: Mapping[str, object] | None) -> str:
    if extra:
        clash = _RESERVED_METADATA & set(extra)
        if clash:
            raise ValueError(f"revision metadata may not set {sorted(clash)}")
        base = {**base, **extra}
    return canonical_json(base)


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


def _manifest_members(manifest_json: str) -> list[Any]:
    """The member list a manifest declares: the ``members`` array of a JSON
    object (the W3 Write manifest), or a bare JSON array (the SPR-00 shape)."""
    try:
        manifest = json.loads(manifest_json)
    except ValueError as exc:
        raise RevisionIntegrityError("the manifest is not JSON") from exc
    if isinstance(manifest, dict):
        manifest = manifest.get("members")
    if not isinstance(manifest, list):
        raise RevisionIntegrityError("the manifest declares no member list")
    return manifest


def _verify_manifest(con: LockedConnection, asset_id: str, revision_id: str, manifest_json: str) -> None:
    """The manifest lists exactly the revision's member rows, in order (the
    binding record: "validate the canonical manifest's member count/order
    against its materialized member rows")."""
    declared = _manifest_members(manifest_json)
    rows = con.execute(
        "SELECT member_index, projection_id FROM derived_asset_revision_members "
        "WHERE derived_asset_id = ? AND revision_id = ? ORDER BY member_index",
        [asset_id, revision_id],
    ).fetchall()
    if len(declared) != len(rows):
        raise RevisionIntegrityError("the manifest's member count disagrees with its member rows")
    for entry, (member_index, projection_id) in zip(declared, rows, strict=True):
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
    if patch is not None and patch.match is None:
        return columns  # a rebuild: nothing of the parent's is carried
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
        if set(scope_columns) <= set(columns):
            unbound = " AND ".join(f"p.{_quote(c)} IS NULL" for c in scope_columns)
            joined = " AND ".join(f"s.{_quote(c)} = p.{_quote(c)}" for c in scope_columns)
            sql += (
                f" AND (({unbound}) OR EXISTS (SELECT 1 FROM {scope_table} AS s "
                f"WHERE s.derived_asset_id = p.derived_asset_id AND s.revision_id = ? AND {joined}))"
            )
            params.append(revision_id)
    if patch is not None and patch.match is not None:
        replaced = " AND ".join(f"p.{_quote(column)} IS NOT DISTINCT FROM ?" for column in patch.match)
        sql += f" AND NOT ({replaced})"
        params.extend(patch.match.values())
    con.execute(sql, params)
    return columns


def _insert_rows(
    con: LockedConnection,
    table: str,
    columns: Sequence[str],
    asset_id: str,
    revision_id: str,
    rows: Sequence[Mapping[str, object]],
    match: Mapping[str, object] | None = None,
) -> None:
    for row in rows:
        unknown = set(row) - set(columns)
        if unknown:
            raise ValueError(f"{table} has no column(s) {sorted(unknown)}")
        if match is not None and any(row.get(column) != value for column, value in match.items()):
            raise ValueError(f"a {table} patch row falls outside what the patch replaces")
        names = list(row)
        placeholders = ", ".join("?" for _ in range(len(names) + 2))
        con.execute(
            f"INSERT INTO {table} (derived_asset_id, revision_id, "
            f"{', '.join(_quote(name) for name in names)}) VALUES ({placeholders})",
            [asset_id, revision_id, *(row[name] for name in names)],
        )


def _record_operation(
    con: LockedConnection,
    *,
    operation_id: str,
    owner_user_id: str,
    idempotency_key: str,
    asset_id: str,
    revision_id: str,
    operation: str,
    request_sha256: str,
    response_json: str,
) -> None:
    con.execute(
        "INSERT INTO derived_asset_operations (operation_id, owner_user_id, idempotency_key, "
        "derived_asset_id, revision_id, operation, request_sha256, response_json) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [operation_id, owner_user_id, idempotency_key, asset_id, revision_id, operation,
         request_sha256, response_json],
    )


def _enqueue_revised(
    con: LockedConnection,
    *,
    operation_id: str,
    event_log_id: str,
    asset_id: str,
    revision_id: str,
    parent_revision_id: str | None,
    operation: str,
    block_ids: Sequence[str],
) -> None:
    """One ``derived_asset.revised`` outbox row in the caller's transaction,
    keyed by the operation receipt. It names no document."""
    payload = DerivedAssetRevisedPayload(
        derived_asset_id=asset_id,
        revision_id=revision_id,
        parent_revision_id=parent_revision_id,
        operation=operation,  # type: ignore[arg-type]  # validated by the payload's Literal
        block_ids=list(block_ids),
    )
    event = build_typed_envelope(event_log_id, payload, role="creation_surface")
    enqueue_event(con, operation_id=operation_id, aggregate_kind="derived_asset", aggregate_id=asset_id, event=event)


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
    event_log_id: str,
    body: RevisionBody | None = None,
    revision_metadata: Mapping[str, object] | None = None,
    checkpoint: Checkpoint | None = None,
) -> StoredOperation:
    """Commit one ``revise`` of ``head`` inside the caller's transaction.

    ``body=None`` keeps the parent's bytes, hashes and manifest (informs);
    a :class:`RevisionBody` writes new ones (a body edit). Raises
    :class:`RevisionMoved` when ``expected_revision_id`` is not the head or
    the pointer moved after the head was loaded, and
    :class:`RevisionIntegrityError` when a manifest disagrees with its
    members. ``build_answer(revision_id)`` is the operation's answer, stored as
    canonical JSON so a replay is byte-identical. The ``derived_asset.revised``
    event goes to ``event_log_id``. ``checkpoint`` is a test seam called
    between steps.
    """
    _require_transaction(con)
    check_expected(head, expected_revision_id)
    for table, requested in patches.items():
        child = CHILD_TABLES.get(table)
        if child is None:
            raise ValueError(f"{table} is not a per-revision child table")
        if requested.match is not None and (not requested.match or not set(requested.match) <= child.patchable_by):
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
    metadata = _revision_metadata({"operation": operation, "block_ids": list(block_ids)}, revision_metadata)
    if body is None:
        content_sha256 = str(parent[1])
        manifest_json = str(parent[0])
        inserted = con.execute(
            "INSERT INTO derived_asset_revisions (derived_asset_id, revision_id, operation_kind, "
            "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
            "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, "
            "parent_revision_id, restored_from_revision_id, metadata_json) "
            "SELECT derived_asset_id, ?, 'revise', canonical_html, canonical_byte_count, content_sha256, "
            "manifest_json, manifest_sha256, sanitizer_policy, sanitizer_version, ?, ?, revision_id, NULL, ? "
            "FROM derived_asset_revisions WHERE derived_asset_id = ? AND revision_id = ? RETURNING revision_id",
            [revision_id, operation_id, OPERATOR_DIRECT_ACKNOWLEDGEMENT, metadata, asset_id, head.revision_id],
        ).fetchall()
    else:
        content_sha256 = _sha256(body.canonical_html)
        manifest_json = body.manifest_json
        inserted = con.execute(
            "INSERT INTO derived_asset_revisions (derived_asset_id, revision_id, operation_kind, "
            "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
            "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, "
            "parent_revision_id, restored_from_revision_id, metadata_json) "
            "VALUES (?, ?, 'revise', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?) RETURNING revision_id",
            [asset_id, revision_id, body.canonical_html, len(body.canonical_html.encode("utf-8")),
             content_sha256, body.manifest_json, _sha256(body.manifest_json), body.sanitizer_policy,
             body.sanitizer_version, operation_id, OPERATOR_DIRECT_ACKNOWLEDGEMENT, head.revision_id,
             metadata],
        ).fetchall()
    if len(inserted) != 1:
        raise RevisionIntegrityError("the new revision could not be written")

    for table, child in CHILD_TABLES.items():
        patch = patches.get(table)
        columns = _carry_forward(con, child, asset_id, head.revision_id, revision_id, patch)
        if patch is not None:
            _insert_rows(con, child.table, columns, asset_id, revision_id, patch.rows, patch.match)
    _verify_manifest(con, asset_id, revision_id, manifest_json)
    _checkpoint(checkpoint, "after_child_copy")

    response_json = canonical_json(build_answer(revision_id))
    _record_operation(
        con, operation_id=operation_id, owner_user_id=owner_user_id, idempotency_key=idempotency_key,
        asset_id=asset_id, revision_id=revision_id, operation=operation, request_sha256=request_sha256,
        response_json=response_json,
    )
    _checkpoint(checkpoint, "after_operation_insert")

    _checkpoint(checkpoint, "before_pointer_update")
    advanced = con.execute(
        "UPDATE derived_asset_current_revisions SET current_revision_id = ?, "
        "current_content_sha256 = ?, generation = generation + 1, updated_at = CURRENT_TIMESTAMP "
        "WHERE derived_asset_id = ? AND current_revision_id = ? AND current_content_sha256 = ? "
        "AND generation = ? RETURNING generation",
        [revision_id, content_sha256, asset_id, head.revision_id, head.content_sha256, head.generation],
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
    _enqueue_revised(
        con, operation_id=operation_id, event_log_id=event_log_id, asset_id=asset_id, revision_id=revision_id,
        parent_revision_id=head.revision_id, operation=operation, block_ids=block_ids,
    )
    _checkpoint(checkpoint, "after_enqueue")
    return StoredOperation(operation_id, asset_id, revision_id, operation, request_sha256, response_json)


def create_revision(
    con: LockedConnection,
    *,
    asset_id: str,
    owner_user_id: str,
    asset_kind: str,
    title: str,
    body: RevisionBody,
    blocks: Sequence[str],
    members: Sequence[Mapping[str, object]],
    idempotency_key: str,
    request_sha256: str,
    event_log_id: str,
    asset_metadata_json: str | None = None,
    revision_metadata: Mapping[str, object] | None = None,
    build_answer: Callable[[str], Mapping[str, object]] | None = None,
) -> Head:
    """Revision 1 of a new asset (§1.11 ``create``), inside the caller's
    transaction: the asset row, the revision (no parent), its block inventory
    and members, the operation receipt, the pointer at generation 1, and the
    ``derived_asset.revised`` create event (no parent) on ``event_log_id``.

    ``members`` rows are written column for column into the live member
    table, with ``member_index`` defaulting to the row's position. On main's
    V16 table that means evidence rows only (projection, source asset,
    document and both hashes are NOT NULL); ``user`` and ``unresolved`` rows
    need the W3 member rebuild. The key must differ from any later revise's.

    LB-8 gives this no production caller; its tests seed fixtures with it.
    The W3 Write revision writer owns revision 1 of ``write:<deliverable_id>``.
    """
    _require_transaction(con)
    content_sha256 = _sha256(body.canonical_html)
    revision_id = f"rev-{uuid.uuid4().hex}"
    operation_id = f"dop-{uuid.uuid4().hex}"
    con.execute(
        "INSERT INTO derived_assets (derived_asset_id, title, asset_kind, owner_user_id, metadata_json) "
        "VALUES (?, ?, ?, ?, ?)",
        [asset_id, title, asset_kind, owner_user_id, asset_metadata_json],
    )
    con.execute(
        "INSERT INTO derived_asset_revisions (derived_asset_id, revision_id, operation_kind, "
        "canonical_html, canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
        "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, metadata_json) "
        "VALUES (?, ?, 'create', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [asset_id, revision_id, body.canonical_html, len(body.canonical_html.encode("utf-8")),
         content_sha256, body.manifest_json, _sha256(body.manifest_json), body.sanitizer_policy,
         body.sanitizer_version, operation_id, OPERATOR_DIRECT_ACKNOWLEDGEMENT,
         _revision_metadata({"operation": "create"}, revision_metadata)],
    )
    _insert_rows(
        con, "derived_asset_revision_blocks", _columns(con, "derived_asset_revision_blocks"), asset_id,
        revision_id, [{"block_index": index, "block_id": block_id} for index, block_id in enumerate(blocks)],
    )
    _insert_rows(
        con, "derived_asset_revision_members", _columns(con, "derived_asset_revision_members"), asset_id,
        revision_id, [{"member_index": index, **member} for index, member in enumerate(members)],
    )
    _verify_manifest(con, asset_id, revision_id, body.manifest_json)
    answer = (build_answer or (lambda rid: {"derived_asset_id": asset_id, "revision_id": rid}))(revision_id)
    _record_operation(
        con, operation_id=operation_id, owner_user_id=owner_user_id, idempotency_key=idempotency_key,
        asset_id=asset_id, revision_id=revision_id, operation="create", request_sha256=request_sha256,
        response_json=canonical_json(answer),
    )
    con.execute(
        "INSERT INTO derived_asset_current_revisions (derived_asset_id, current_revision_id, "
        "current_content_sha256, generation) VALUES (?, ?, ?, 1)",
        [asset_id, revision_id, content_sha256],
    )
    _enqueue_revised(
        con, operation_id=operation_id, event_log_id=event_log_id, asset_id=asset_id, revision_id=revision_id,
        parent_revision_id=None, operation="create", block_ids=blocks,
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
    "RevisionBody",
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
