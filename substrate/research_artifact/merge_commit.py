"""Atomic, idempotent commit of reviewed derived-asset revisions."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

from runtime.db_lock import connect_write
from services.html_projection.canonical_merge import POLICY, VERSION
from substrate.research_artifact.merge_draft import ACKNOWLEDGEMENT_VERSION

FaultHook = Callable[[str], None]
_EVENT: Final = "derived_asset.revision_committed.v1"


class MergeCommitError(ValueError):
    """Stable fail-closed merge refusal."""


class MergeCommitNotFound(KeyError):
    """Owner-scoped command authority was not found."""


@dataclass(frozen=True)
class MergeCommitResult:
    operation_id: str
    derived_asset_id: str
    revision_id: str
    content_sha256: str
    generation: int
    replayed: bool = False


def apply_review(
    *,
    review_id: str,
    operation_id: str,
    owner_user_id: str,
    db_path: str,
    expected_generation: int | None = None,
    fault_hook: FaultHook | None = None,
) -> MergeCommitResult:
    command = {
        "expected_generation": expected_generation,
        "operation_id": operation_id,
        "owner_user_id": owner_user_id,
        "review_id": review_id,
    }
    with connect_write(db_path, purpose="apply-reviewed-derived-asset") as con:
        return _transaction(con, command, fault_hook, _apply_review)


def restore(
    *,
    derived_asset_id: str,
    selected_revision_id: str,
    expected_revision_id: str,
    expected_content_sha256: str,
    expected_generation: int,
    operation_id: str,
    owner_user_id: str,
    db_path: str,
    fault_hook: FaultHook | None = None,
) -> MergeCommitResult:
    command = {
        "derived_asset_id": derived_asset_id,
        "expected_content_sha256": expected_content_sha256,
        "expected_generation": expected_generation,
        "expected_revision_id": expected_revision_id,
        "operation_id": operation_id,
        "owner_user_id": owner_user_id,
        "selected_revision_id": selected_revision_id,
    }
    with connect_write(db_path, purpose="restore-derived-asset") as con:
        return _transaction(con, command, fault_hook, _restore)


def _transaction(
    con: Any, command: dict[str, Any], hook: FaultHook | None, worker: Any
) -> MergeCommitResult:
    _validate_command(command)
    digest = _sha(_json(command))
    con.execute("BEGIN TRANSACTION")
    try:
        replay = _replay(con, command)
        if replay is not None:
            con.execute("COMMIT")
            return replay
        result = worker(con, command, digest, hook or (lambda _stage: None))
        con.execute("COMMIT")
        return result
    except MergeCommitError:
        con.execute("ROLLBACK")
        raise
    except MergeCommitNotFound:
        con.execute("ROLLBACK")
        raise
    except Exception as exc:
        con.execute("ROLLBACK")
        raise MergeCommitError("derived asset merge failed") from exc


def _apply_review(
    con: Any, command: dict[str, Any], digest: str, hook: FaultHook
) -> MergeCommitResult:
    row = con.execute(
        "SELECT d.intent,d.target_asset_id,d.expected_parent_revision_id,d.expected_parent_sha256,"
        "d.title,d.asset_kind,d.canonical_html,d.canonical_sha256,d.manifest_json,d.manifest_sha256,"
        "d.sanitizer_policy,d.sanitizer_version,r.acknowledgement_version "
        "FROM derived_asset_merge_reviews r JOIN derived_asset_merge_drafts d ON "
        "d.draft_id=r.draft_id AND d.owner_user_id=r.owner_user_id AND "
        "d.canonical_sha256=r.canonical_sha256 AND d.manifest_sha256=r.manifest_sha256 AND "
        "d.sanitizer_policy=r.sanitizer_policy AND d.sanitizer_version=r.sanitizer_version "
        "WHERE r.review_id=? AND r.owner_user_id=?",
        [command["review_id"], command["owner_user_id"]],
    ).fetchone()
    if row is None:
        raise MergeCommitNotFound("review unavailable")
    intent = str(row[0])
    asset_id = (
        _id("ast", command["owner_user_id"], command["operation_id"])
        if intent == "create"
        else str(row[1])
    )
    revision_id = _id("rev", command["owner_user_id"], command["operation_id"])
    manifest = _manifest(str(row[8]), str(row[9]))
    if (
        _sha(str(row[6])) != str(row[7])
        or (str(row[10]), str(row[11])) != (POLICY, VERSION)
        or str(row[12]) != ACKNOWLEDGEMENT_VERSION
    ):
        raise MergeCommitError("reviewed draft is invalid")
    if intent == "create":
        if command["expected_generation"] is not None:
            raise MergeCommitError("create command cannot name a generation")
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id,title,asset_kind,owner_user_id) VALUES (?,?,?,?)",
            [asset_id, row[4], row[5], command["owner_user_id"]],
        )
        generation, parent = 1, None
    else:
        if (
            not isinstance(command["expected_generation"], int)
            or command["expected_generation"] < 1
        ):
            raise MergeCommitError("revise command requires exact generation")
        pointer = con.execute(
            "SELECT c.current_revision_id,c.current_content_sha256,c.generation FROM derived_assets a "
            "JOIN derived_asset_current_revisions c USING (derived_asset_id) "
            "WHERE a.derived_asset_id=? AND a.owner_user_id=?",
            [asset_id, command["owner_user_id"]],
        ).fetchone()
        if pointer != (row[2], row[3], command["expected_generation"]):
            raise MergeCommitError("derived asset command is stale")
        generation, parent = int(pointer[2]) + 1, str(row[2])
        command.update(expected_revision_id=str(row[2]), expected_content_sha256=str(row[3]))
        digest = _sha(_json(command))
        # DuckDB refuses updates of referenced parent rows even when no key
        # column changes. V16 therefore treats container title/kind as stable;
        # the reviewed revision remains the sole content/kind authority.
    hook("asset")
    _insert_revision(
        con,
        asset_id,
        revision_id,
        intent,
        row[6:13],
        parent,
        None,
        review_id=command["review_id"],
    )
    hook("revision")
    _insert_members(con, asset_id, revision_id, manifest)
    hook("members")
    if intent == "create":
        con.execute(
            "INSERT INTO derived_asset_current_revisions "
            "(derived_asset_id,current_revision_id,current_content_sha256,generation) VALUES (?,?,?,1)",
            [asset_id, revision_id, row[7]],
        )
    else:
        changed = con.execute(
            "UPDATE derived_asset_current_revisions SET current_revision_id=?,current_content_sha256=?,"
            "generation=?,updated_at=CURRENT_TIMESTAMP WHERE derived_asset_id=? AND current_revision_id=? "
            "AND current_content_sha256=? AND generation=? RETURNING generation",
            [revision_id, row[7], generation, asset_id, row[2], row[3], generation - 1],
        ).fetchall()
        if changed != [(generation,)]:
            raise MergeCommitError("derived asset command is stale")
    con.execute(
        "UPDATE derived_assets SET updated_at=CURRENT_TIMESTAMP WHERE derived_asset_id=?",
        [asset_id],
    )
    hook("pointer")
    return _finish(
        con, command, digest, intent, asset_id, revision_id, str(row[7]), generation, hook
    )


def _restore(con: Any, command: dict[str, Any], digest: str, hook: FaultHook) -> MergeCommitResult:
    asset_id = command["derived_asset_id"]
    pointer = con.execute(
        "SELECT c.current_revision_id,c.current_content_sha256,c.generation FROM derived_assets a "
        "JOIN derived_asset_current_revisions c USING (derived_asset_id) "
        "WHERE a.derived_asset_id=? AND a.owner_user_id=?",
        [asset_id, command["owner_user_id"]],
    ).fetchone()
    if pointer is None:
        raise MergeCommitNotFound("asset unavailable")
    if pointer != (
        command["expected_revision_id"],
        command["expected_content_sha256"],
        command["expected_generation"],
    ):
        raise MergeCommitError("derived asset command is stale")
    if command["selected_revision_id"] == pointer[0]:
        raise MergeCommitError("restore source must be historical")
    selected = con.execute(
        "SELECT canonical_html,content_sha256,manifest_json,manifest_sha256,sanitizer_policy,"
        "sanitizer_version,review_id,acknowledgement_version FROM derived_asset_revisions "
        "WHERE derived_asset_id=? AND revision_id=?",
        [asset_id, command["selected_revision_id"]],
    ).fetchone()
    if selected is None:
        raise MergeCommitNotFound("revision unavailable")
    manifest = _manifest(str(selected[2]), str(selected[3]))
    if (_sha(str(selected[0])) != str(selected[1])
            or (str(selected[4]), str(selected[5])) != (POLICY, VERSION)
            or str(selected[7]) != ACKNOWLEDGEMENT_VERSION
            or not isinstance(selected[6], str) or not selected[6]):
        raise MergeCommitError("stored revision is invalid")
    revision_id = _id("rev", command["owner_user_id"], command["operation_id"])
    generation = int(pointer[2]) + 1
    hook("asset")
    values = (
        selected[0],
        selected[1],
        selected[2],
        selected[3],
        selected[4],
        selected[5],
        selected[7],
    )
    _insert_revision(
        con,
        asset_id,
        revision_id,
        "restore",
        values,
        str(pointer[0]),
        command["selected_revision_id"],
        review_id=str(selected[6]),
    )
    hook("revision")
    _insert_members(con, asset_id, revision_id, manifest)
    hook("members")
    changed = con.execute(
        "UPDATE derived_asset_current_revisions SET current_revision_id=?,current_content_sha256=?,"
        "generation=?,updated_at=CURRENT_TIMESTAMP WHERE derived_asset_id=? AND current_revision_id=? "
        "AND current_content_sha256=? AND generation=? RETURNING generation",
        [revision_id, selected[1], generation, asset_id, *pointer],
    ).fetchall()
    if changed != [(generation,)]:
        raise MergeCommitError("derived asset command is stale")
    con.execute(
        "UPDATE derived_assets SET updated_at=CURRENT_TIMESTAMP WHERE derived_asset_id=?",
        [asset_id],
    )
    hook("pointer")
    return _finish(
        con, command, digest, "restore", asset_id, revision_id, str(selected[1]), generation, hook
    )


def _insert_revision(
    con: Any,
    asset: str,
    revision: str,
    kind: str,
    values: Any,
    parent: str | None,
    restored: str | None,
    review_id: str | None = None,
) -> None:
    html, content_hash, manifest, manifest_hash, policy, version, acknowledgement = values
    con.execute(
        "INSERT INTO derived_asset_revisions (derived_asset_id,revision_id,operation_kind,canonical_html,"
        "canonical_byte_count,content_sha256,manifest_json,manifest_sha256,sanitizer_policy,sanitizer_version,"
        "review_id,acknowledgement_version,parent_revision_id,restored_from_revision_id) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            asset,
            revision,
            kind,
            html,
            len(str(html).encode()),
            content_hash,
            manifest,
            manifest_hash,
            policy,
            version,
            review_id,
            acknowledgement,
            parent,
            restored,
        ],
    )


def _insert_members(con: Any, asset: str, revision: str, manifest: list[dict[str, Any]]) -> None:
    for entry in manifest:
        con.execute(
            "INSERT INTO derived_asset_revision_members VALUES (?,?,?,?,?,?,?,?,?)",
            [
                asset,
                revision,
                entry["member_index"],
                entry["projection_id"],
                entry["source_asset_id"],
                entry["source_document_id"],
                entry["source_sha256"],
                entry["hosted_html_sha256"],
                None,
            ],
        )


def _finish(
    con: Any,
    command: dict[str, Any],
    digest: str,
    kind: str,
    asset: str,
    revision: str,
    content_hash: str,
    generation: int,
    hook: FaultHook,
) -> MergeCommitResult:
    result = {
        "content_sha256": content_hash,
        "derived_asset_id": asset,
        "generation": generation,
        "operation_id": command["operation_id"],
        "revision_id": revision,
    }
    receipt = _json({"command": command, "result": result})
    con.execute(
        "INSERT INTO derived_asset_merge_operations "
        "(operation_id,owner_user_id,operation_kind,review_id,derived_asset_id,"
        "selected_revision_id,expected_revision_id,expected_content_sha256,expected_generation,"
        "command_sha256,result_revision_id,result_content_sha256,result_generation,receipt_json,"
        "receipt_sha256) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            command["operation_id"],
            command["owner_user_id"],
            kind,
            command.get("review_id"),
            asset,
            command.get("selected_revision_id"),
            command.get("expected_revision_id"),
            command.get("expected_content_sha256"),
            command.get("expected_generation"),
            digest,
            revision,
            content_hash,
            generation,
            receipt,
            _sha(receipt),
        ],
    )
    hook("receipt")
    payload = _json(result)
    con.execute(
        "INSERT INTO derived_asset_merge_outbox "
        "(outbox_id,owner_user_id,operation_id,event_kind,payload_json,payload_sha256) "
        "VALUES (?,?,?,?,?,?)",
        [
            _id("out", command["owner_user_id"], command["operation_id"]),
            command["owner_user_id"],
            command["operation_id"],
            _EVENT,
            payload,
            _sha(payload),
        ],
    )
    hook("outbox")
    return MergeCommitResult(command["operation_id"], asset, revision, content_hash, generation)


def _replay(con: Any, command: dict[str, Any]) -> MergeCommitResult | None:
    operation_id = command["operation_id"]
    row = con.execute(
        "SELECT derived_asset_id,result_revision_id,result_content_sha256,result_generation,command_sha256,"
        "receipt_json,receipt_sha256 FROM derived_asset_merge_operations "
        "WHERE owner_user_id=? AND operation_id=?",
        [command["owner_user_id"], operation_id],
    ).fetchone()
    if row is None:
        return None
    try:
        receipt = json.loads(str(row[5]))
        stored_command = receipt["command"]
        stored_result = receipt["result"]
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise MergeCommitError("operation replay state drifted") from exc
    if (
        not isinstance(stored_command, dict)
        or not isinstance(stored_result, dict)
        or any(stored_command.get(key) != value for key, value in command.items())
        or str(row[4]) != _sha(_json(stored_command))
        or _sha(str(row[5])) != str(row[6])
    ):
        raise MergeCommitError("operation replay does not match")
    revision = con.execute(
        "SELECT canonical_html,canonical_byte_count,content_sha256,manifest_json,manifest_sha256,"
        "sanitizer_policy,sanitizer_version,acknowledgement_version "
        "FROM derived_asset_revisions "
        "WHERE derived_asset_id=? AND revision_id=?",
        [row[0], row[1]],
    ).fetchone()
    outbox = con.execute(
        "SELECT payload_json,payload_sha256 FROM derived_asset_merge_outbox "
        "WHERE owner_user_id=? AND operation_id=?",
        [command["owner_user_id"], operation_id],
    ).fetchall()
    expected_result = {
        "content_sha256": str(row[2]),
        "derived_asset_id": str(row[0]),
        "generation": int(row[3]),
        "operation_id": operation_id,
        "revision_id": str(row[1]),
    }
    if (
        stored_result != expected_result
        or revision is None
        or revision[2] != row[2]
        or len(str(revision[0]).encode()) != revision[1]
        or _sha(str(revision[0])) != str(revision[2])
        or (str(revision[5]), str(revision[6])) != (POLICY, VERSION)
        or str(revision[7]) != ACKNOWLEDGEMENT_VERSION
        or len(outbox) != 1
        or _sha(str(outbox[0][0])) != str(outbox[0][1])
        or str(outbox[0][0]) != _json(expected_result)
    ):
        raise MergeCommitError("operation replay state drifted")
    manifest = _manifest(str(revision[3]), str(revision[4]))
    members = con.execute(
        "SELECT member_index,projection_id,source_asset_id,source_document_id,source_sha256,"
        "hosted_html_sha256 FROM derived_asset_revision_members "
        "WHERE derived_asset_id=? AND revision_id=? ORDER BY member_index",
        [row[0], row[1]],
    ).fetchall()
    expected_members = [
        (
            item["member_index"],
            item["projection_id"],
            item["source_asset_id"],
            item["source_document_id"],
            item["source_sha256"],
            item["hosted_html_sha256"],
        )
        for item in manifest
    ]
    if members != expected_members:
        raise MergeCommitError("operation replay state drifted")
    return MergeCommitResult(operation_id, str(row[0]), str(row[1]), str(row[2]), int(row[3]), True)


def _manifest(text: str, digest: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise MergeCommitError("stored manifest is invalid") from exc
    required = {
        "converter_id",
        "converter_version",
        "hosted_html_sha256",
        "member_index",
        "projection_id",
        "projection_sanitizer_policy",
        "projection_sanitizer_version",
        "source_asset_id",
        "source_document_id",
        "source_sha256",
    }
    if (
        _json(value) != text
        or _sha(text) != digest
        or not isinstance(value, list)
        or not value
        or any(
            not isinstance(v, dict)
            or set(v) != required
            or v["member_index"] != i
            or any(
                not isinstance(v[field], str) or not v[field]
                for field in required - {"member_index"}
            )
            or not re.fullmatch(r"[0-9a-f]{64}", v["hosted_html_sha256"])
            or not re.fullmatch(r"[0-9a-f]{64}", v["source_sha256"])
            for i, v in enumerate(value)
        )
    ):
        raise MergeCommitError("stored manifest is invalid")
    return value


def _validate_command(command: dict[str, Any]) -> None:
    if not re.fullmatch(r"op_[0-9a-f]{32}", str(command.get("operation_id", ""))):
        raise MergeCommitError("invalid merge command")
    if not command.get("owner_user_id"):
        raise MergeCommitError("invalid merge command")


def _id(prefix: str, owner_user_id: str, operation_id: str) -> str:
    basis = f"{prefix}:{owner_user_id}:{operation_id}"
    return prefix + "_" + hashlib.sha256(basis.encode()).hexdigest()[:32]


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


__all__ = [
    "MergeCommitError",
    "MergeCommitNotFound",
    "MergeCommitResult",
    "apply_review",
    "restore",
]
