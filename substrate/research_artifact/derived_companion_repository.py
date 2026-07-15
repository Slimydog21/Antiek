"""Durable provider-free companion evidence outcomes."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from typing import Any, Final

from runtime.db_lock import connect_read, connect_write
from substrate.research_artifact.derived_asset_library import DerivedAssetLibrary
from substrate.research_artifact.derived_companion import (
    EVIDENCE_PACK_VERSION,
    build_derived_revision_evidence_pack,
    canonical_evidence_json,
)

MAX_QUESTION_BYTES: Final = 8 * 1024
_CLIENT_ID = re.compile(r"[A-Za-z0-9._:-]{8,128}")


class CompanionCommandError(RuntimeError):
    pass


class CompanionIdempotencyConflict(CompanionCommandError):
    pass


class CompanionStaleRevision(CompanionCommandError):
    def __init__(self, scope: dict[str, Any]):
        super().__init__("current derived revision changed")
        self.scope = scope


class DerivedCompanionRepository:
    def __init__(self, *, db_path: str):
        self.db_path = db_path

    def prepare_evidence(
        self,
        *,
        owner_user_id: str,
        asset_id: str,
        client_turn_id: str,
        question: str,
        revision_id: str | None = None,
        expected_revision_id: str | None = None,
        expected_content_sha256: str | None = None,
    ) -> dict[str, Any]:
        normalized = question.strip() if isinstance(question, str) else ""
        if (not normalized or len(normalized.encode("utf-8")) > MAX_QUESTION_BYTES
                or not _CLIENT_ID.fullmatch(client_turn_id)):
            raise ValueError("invalid companion command")
        reading = DerivedAssetLibrary(db_path=self.db_path).reading(
            owner_user_id, asset_id, revision_id
        )
        if revision_id is None and (expected_revision_id is not None
                or expected_content_sha256 is not None) and (
                    expected_revision_id != reading["revision_id"]
                    or expected_content_sha256 != reading["content_sha256"]
                ):
            raise CompanionStaleRevision(_scope(reading))
        request = {
            "version": EVIDENCE_PACK_VERSION,
            "derived_asset_id": asset_id,
            "revision_id": reading["revision_id"],
            "content_sha256": reading["content_sha256"],
            "question": normalized,
            "top_k": 6,
        }
        request_sha = _sha(_json(request))
        with connect_read(self.db_path) as con:
            replay = con.execute(
                "SELECT t.request_sha256,t.evidence_pack_json "
                "FROM derived_asset_companion_turns t "
                "JOIN derived_asset_companion_threads h USING (thread_id) "
                "JOIN derived_assets a USING (derived_asset_id) "
                "WHERE a.owner_user_id=? AND t.client_turn_id=?",
                [owner_user_id, client_turn_id],
            ).fetchone()
        if replay is not None:
            if replay[0] != request_sha:
                raise CompanionIdempotencyConflict
            return _public(json.loads(str(replay[1])), client_turn_id, replayed=True)
        pack = build_derived_revision_evidence_pack(
            db_path=self.db_path,
            owner_user_id=owner_user_id,
            asset_id=asset_id,
            revision_id=str(reading["revision_id"]),
            question=normalized,
        )
        thread_id = "dct_" + _sha(
            f"{owner_user_id}\0{asset_id}\0{reading['revision_id']}"
        )[:32]
        turn_id = "dturn_" + _sha(f"{owner_user_id}\0{client_turn_id}")[:32]
        state = "evidence_ready" if pack["citations"] else "insufficient_evidence"
        failure = None if pack["citations"] else "no_matching_revision_evidence"
        with connect_write(self.db_path, purpose="prepare-derived-companion-evidence") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                if revision_id is None:
                    current = con.execute(
                        "SELECT c.current_revision_id,c.current_content_sha256,c.generation "
                        "FROM derived_asset_current_revisions c JOIN derived_assets a "
                        "USING (derived_asset_id) WHERE a.owner_user_id=? "
                        "AND a.derived_asset_id=?",
                        [owner_user_id, asset_id],
                    ).fetchone()
                    if current != (
                        reading["revision_id"], reading["content_sha256"], reading["generation"]
                    ):
                        if current is None:
                            raise CompanionCommandError("current revision is unavailable")
                        raise CompanionStaleRevision({
                            "derived_asset_id": asset_id,
                            "revision_id": str(current[0]),
                            "content_sha256": str(current[1]),
                            "generation": int(current[2]),
                            "is_current": True,
                            "exact_reader_path": (
                                f"/read/derived/{asset_id}/revisions/{current[0]}"
                            ),
                        })
                replay = con.execute(
                    "SELECT t.request_sha256,t.evidence_pack_json "
                    "FROM derived_asset_companion_turns t "
                    "JOIN derived_asset_companion_threads h USING (thread_id) "
                    "JOIN derived_assets a USING (derived_asset_id) "
                    "WHERE a.owner_user_id=? AND t.client_turn_id=?",
                    [owner_user_id, client_turn_id],
                ).fetchone()
                if replay is not None:
                    if replay[0] != request_sha:
                        raise CompanionIdempotencyConflict
                    con.execute("ROLLBACK")
                    return _public(json.loads(str(replay[1])), client_turn_id, replayed=True)
                con.execute(
                    "INSERT INTO derived_asset_companion_threads "
                    "(thread_id,derived_asset_id,revision_id,"
                    "revision_content_sha256,revision_generation) VALUES (?,?,?,?,?) "
                    "ON CONFLICT DO NOTHING",
                    [thread_id, asset_id, reading["revision_id"],
                     reading["content_sha256"], reading["generation"]],
                )
                ordinal = int(con.execute(
                    "SELECT last_turn_ordinal FROM derived_asset_companion_threads "
                    "WHERE thread_id=?", [thread_id]
                ).fetchone()[0]) + 1
                evidence_json = canonical_evidence_json(pack)
                con.execute(
                    "INSERT INTO derived_asset_companion_turns VALUES "
                    "(?,?,?,?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                    [turn_id, thread_id, client_turn_id, ordinal, normalized,
                     _sha(normalized), request_sha, state, evidence_json,
                     pack["pack_sha256"], failure],
                )
                for order, citation in enumerate(pack["citations"]):
                    con.execute(
                        "INSERT INTO derived_asset_companion_turn_citations VALUES "
                        "(?,?,?,?,?,?,FALSE)",
                        [turn_id, thread_id, asset_id, reading["revision_id"], order,
                         citation["chunk_ordinal"]],
                    )
                con.execute(
                    "UPDATE derived_asset_companion_threads SET last_turn_ordinal=? "
                    "WHERE thread_id=?", [ordinal, thread_id]
                )
                con.execute("COMMIT")
            except Exception:
                with contextlib.suppress(Exception):
                    con.execute("ROLLBACK")
                raise
        return _public(pack, client_turn_id, replayed=False)

    def conversation(
        self, *, owner_user_id: str, asset_id: str, revision_id: str | None = None
    ) -> dict[str, Any]:
        reading = DerivedAssetLibrary(db_path=self.db_path).reading(
            owner_user_id, asset_id, revision_id
        )
        with connect_read(self.db_path) as con:
            rows = con.execute(
                "SELECT t.client_turn_id,t.question,t.state,t.failure_code,"
                "t.evidence_pack_json FROM derived_asset_companion_turns t "
                "JOIN derived_asset_companion_threads h ON h.thread_id=t.thread_id "
                "JOIN derived_assets a USING (derived_asset_id) "
                "WHERE a.owner_user_id=? AND h.derived_asset_id=? AND h.revision_id=? "
                "AND h.revision_content_sha256=? ORDER BY t.turn_ordinal",
                [owner_user_id, asset_id, reading["revision_id"], reading["content_sha256"]],
            ).fetchall()
        return {
            "scope": _scope(reading),
            "turns": [{
                "client_turn_id": str(row[0]),
                "question": str(row[1]),
                "state": str(row[2]),
                "failure_code": None if row[3] is None else str(row[3]),
                "evidence_pack": json.loads(str(row[4])),
            } for row in rows],
        }


def _public(pack: dict[str, Any], client_turn_id: str, *, replayed: bool) -> dict[str, Any]:
    evidence = bool(pack["citations"])
    return {
        "client_turn_id": client_turn_id,
        "state": "evidence_ready" if evidence else "insufficient_evidence",
        "failure_code": None if evidence else "no_matching_revision_evidence",
        "replayed": replayed,
        "scope": {
            "derived_asset_id": pack["derived_asset_id"],
            "revision_id": pack["revision_id"],
            "content_sha256": pack["content_sha256"],
            "generation": pack["generation"],
            "is_current": pack["is_current"],
        },
        "evidence_pack": pack,
        "execution": {
            "available": False,
            "reason": "paid_route_not_qualified",
            "pricing_status": "unknown",
        },
    }


def _scope(reading: dict[str, Any]) -> dict[str, Any]:
    return {key: reading[key] for key in (
        "derived_asset_id", "revision_id", "content_sha256", "generation",
        "is_current", "exact_reader_path",
    )}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["CompanionIdempotencyConflict", "CompanionStaleRevision",
           "DerivedCompanionRepository"]
