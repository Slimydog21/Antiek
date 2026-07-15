"""Durable provider-free companion evidence outcomes."""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from typing import Any, Final, cast

from runtime.db_lock import connect_read, connect_write
from substrate.research_artifact.derived_asset_library import DerivedAssetLibrary
from substrate.research_artifact.derived_companion import (
    EVIDENCE_PACK_VERSION,
    build_derived_revision_evidence_pack,
    canonical_evidence_json,
)
from substrate.research_artifact.derived_evidence_briefing import build_evidence_briefing
from substrate.research_artifact.grounded_companion_answer import (
    AnswerAdmissionExpectation,
    CompanionExecutionReceiptVerifier,
    GroundedAnswerCandidate,
    build_grounded_answer,
    candidate_digest,
    public_grounded_answer,
)

MAX_QUESTION_BYTES: Final = 8 * 1024
_CLIENT_ID = re.compile(r"[A-Za-z0-9._:-]{8,128}")
_ADMISSION_KEY = re.compile(r"[A-Za-z0-9._:-]{16,128}")


class CompanionCommandError(RuntimeError):
    pass


class CompanionIdempotencyConflict(CompanionCommandError):
    pass


class CompanionStaleRevision(CompanionCommandError):
    def __init__(self, scope: dict[str, Any]):
        super().__init__("current derived revision changed")
        self.scope = scope


class CompanionAnswerUnavailable(CompanionCommandError):
    pass


class CompanionAnswerConflict(CompanionCommandError):
    pass


class DerivedCompanionRepository:
    def __init__(
        self, *, db_path: str,
        receipt_verifier: CompanionExecutionReceiptVerifier | None = None,
    ):
        self.db_path = db_path
        self._receipt_verifier = receipt_verifier

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
                "SELECT t.request_sha256,t.evidence_pack_json,t.evidence_pack_sha256,"
                "h.derived_asset_id,h.revision_id,h.revision_content_sha256,h.revision_generation,"
                "n.artifact_json,n.artifact_sha256 "
                "FROM derived_asset_companion_turns t "
                "JOIN derived_asset_companion_threads h USING (thread_id) "
                "JOIN derived_assets a USING (derived_asset_id) "
                "LEFT JOIN derived_asset_companion_answers n USING (turn_id) "
                "WHERE a.owner_user_id=? AND t.client_turn_id=?",
                [owner_user_id, client_turn_id],
            ).fetchone()
        if replay is not None:
            if replay[0] != request_sha:
                raise CompanionIdempotencyConflict
            return _public(_stored_pack(replay[1:7]), normalized, client_turn_id, replayed=True,
                           answer=_answer_from_row(replay[7], replay[8]))
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
                    "SELECT t.request_sha256,t.evidence_pack_json,t.evidence_pack_sha256,"
                    "h.derived_asset_id,h.revision_id,h.revision_content_sha256,"
                    "h.revision_generation,n.artifact_json,n.artifact_sha256 "
                    "FROM derived_asset_companion_turns t "
                    "JOIN derived_asset_companion_threads h USING (thread_id) "
                    "JOIN derived_assets a USING (derived_asset_id) "
                    "LEFT JOIN derived_asset_companion_answers n USING (turn_id) "
                    "WHERE a.owner_user_id=? AND t.client_turn_id=?",
                    [owner_user_id, client_turn_id],
                ).fetchone()
                if replay is not None:
                    if replay[0] != request_sha:
                        raise CompanionIdempotencyConflict
                    con.execute("ROLLBACK")
                    return _public(_stored_pack(replay[1:7]), normalized, client_turn_id,
                                   replayed=True,
                                   answer=_answer_from_row(replay[7], replay[8]))
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
        return _public(pack, normalized, client_turn_id, replayed=False)

    def conversation(
        self, *, owner_user_id: str, asset_id: str, revision_id: str | None = None
    ) -> dict[str, Any]:
        reading = DerivedAssetLibrary(db_path=self.db_path).reading(
            owner_user_id, asset_id, revision_id
        )
        with connect_read(self.db_path) as con:
            rows = con.execute(
                "SELECT t.client_turn_id,t.question,t.state,t.failure_code,"
                "t.evidence_pack_json,t.evidence_pack_sha256,h.derived_asset_id,h.revision_id,"
                "h.revision_content_sha256,h.revision_generation,n.artifact_json,n.artifact_sha256 "
                "FROM derived_asset_companion_turns t "
                "JOIN derived_asset_companion_threads h ON h.thread_id=t.thread_id "
                "JOIN derived_assets a USING (derived_asset_id) "
                "LEFT JOIN derived_asset_companion_answers n USING (turn_id) "
                "WHERE a.owner_user_id=? AND h.derived_asset_id=? AND h.revision_id=? "
                "AND h.revision_content_sha256=? ORDER BY t.turn_ordinal",
                [owner_user_id, asset_id, reading["revision_id"], reading["content_sha256"]],
            ).fetchall()
        return {
            "scope": _scope(reading),
            "turns": [_conversation_turn(row) for row in rows],
        }

    def admit_answer(
        self, *, owner_user_id: str, client_turn_id: str, admission_key: str,
        candidate: GroundedAnswerCandidate,
    ) -> dict[str, Any]:
        if not _CLIENT_ID.fullmatch(client_turn_id) or not _ADMISSION_KEY.fullmatch(admission_key):
            raise ValueError("invalid companion answer command")
        with connect_read(self.db_path) as con:
            row = con.execute(
                "SELECT t.turn_id,t.thread_id,t.evidence_pack_json,t.evidence_pack_sha256,"
                "n.admission_request_sha256,n.artifact_json,n.artifact_sha256 "
                "FROM derived_asset_companion_turns t JOIN derived_asset_companion_threads h "
                "USING (thread_id) JOIN derived_assets a USING (derived_asset_id) "
                "LEFT JOIN derived_asset_companion_answers n USING (turn_id) "
                "WHERE a.owner_user_id=? AND t.client_turn_id=?",
                [owner_user_id, client_turn_id],
            ).fetchone()
        if row is None:
            raise CompanionAnswerUnavailable("companion evidence turn is unavailable")
        turn_id, thread_id = str(row[0]), str(row[1])
        evidence_pack = json.loads(str(row[2]))
        output_digest = candidate_digest(candidate)
        request = {
            "admission_key": admission_key, "turn_id": turn_id,
            "evidence_pack_sha256": str(row[3]), "output_digest": output_digest,
        }
        request_sha = _sha(_json(request))
        if row[4] is not None:
            if str(row[4]) != request_sha:
                raise CompanionAnswerConflict("companion answer command conflicts")
            return {**public_grounded_answer(_artifact_from_row(row[5], row[6])),
                    "replayed": True}
        if self._receipt_verifier is None:
            raise CompanionAnswerUnavailable("companion answer verifier is unavailable")
        expectation = AnswerAdmissionExpectation(
            turn_id=turn_id, evidence_pack_sha256=str(row[3]), output_digest=output_digest
        )
        receipt = self._receipt_verifier(expectation)
        artifact = build_grounded_answer(
            turn_id=turn_id, evidence_pack=evidence_pack, candidate=candidate, receipt=receipt
        )
        stored_artifact = {key: value for key, value in artifact.items()
                           if key != "artifact_sha256"}
        artifact_json = _json(stored_artifact)
        with connect_write(self.db_path, purpose="admit-derived-companion-answer") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                existing = con.execute(
                    "SELECT admission_request_sha256,artifact_json,artifact_sha256 "
                    "FROM derived_asset_companion_answers WHERE turn_id=? OR admission_key=? "
                    "OR execution_receipt_id=?",
                    [turn_id, admission_key, receipt.receipt_id],
                ).fetchone()
                if existing is not None:
                    if existing[0] != request_sha:
                        raise CompanionAnswerConflict("companion answer command conflicts")
                    con.execute("ROLLBACK")
                    return {**public_grounded_answer(_artifact_from_row(existing[1], existing[2])),
                            "replayed": True}
                con.execute(
                    "INSERT INTO derived_asset_companion_answers "
                    "(answer_id,turn_id,thread_id,admission_key,admission_request_sha256,"
                    "evidence_pack_sha256,execution_receipt_id,execution_receipt_digest,"
                    "provider,model,output_digest,artifact_json,artifact_sha256) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    [artifact["answer_id"], turn_id, thread_id, admission_key, request_sha,
                     artifact["evidence_pack_sha256"], receipt.receipt_id,
                     receipt.receipt_digest, receipt.provider, receipt.model, output_digest,
                     artifact_json, artifact["artifact_sha256"]],
                )
                cited = artifact["cited_citation_ids"]
                if cited:
                    placeholders = ",".join("?" for _ in cited)
                    con.execute(
                        "UPDATE derived_asset_companion_turn_citations SET used_in_answer=TRUE "
                        "WHERE turn_id=? AND chunk_ordinal IN (SELECT chunk_ordinal FROM "
                        f"derived_asset_revision_chunks WHERE citation_id IN ({placeholders}))",
                        [turn_id, *cited],
                    )
                    marked = int(con.execute(
                        "SELECT count(*) FROM derived_asset_companion_turn_citations "
                        "WHERE turn_id=? AND used_in_answer=TRUE", [turn_id]
                    ).fetchone()[0])
                    if marked != len(cited):
                        raise CompanionAnswerConflict("answer citation admission mismatch")
                con.execute("COMMIT")
            except Exception:
                with contextlib.suppress(Exception):
                    con.execute("ROLLBACK")
                raise
        return {**public_grounded_answer(artifact), "replayed": False}


def _public(
    pack: dict[str, Any], question: str, client_turn_id: str, *, replayed: bool,
    answer: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        "briefing": _briefing_from_pack(question, pack),
        "answer": answer,
    }


def _briefing_from_pack(question: str, pack: dict[str, Any]) -> dict[str, Any] | None:
    return build_evidence_briefing(question, pack) if pack["citations"] else None


def _stored_pack(values: tuple[Any, ...]) -> dict[str, Any]:
    raw, digest, asset_id, revision_id, content_sha256, generation = values
    try:
        pack = json.loads(str(raw))
        payload = {key: value for key, value in pack.items() if key != "pack_sha256"}
        canonical_digest = _sha(_json(payload))
    except (AttributeError, TypeError, ValueError, UnicodeError, OverflowError) as exc:
        raise CompanionCommandError("stored companion evidence integrity conflict") from exc
    if (not isinstance(pack, dict) or pack.get("pack_sha256") != str(digest)
            or canonical_digest != str(digest)
            or pack.get("derived_asset_id") != str(asset_id)
            or pack.get("revision_id") != str(revision_id)
            or pack.get("content_sha256") != str(content_sha256)
            or pack.get("generation") != int(generation)):
        raise CompanionCommandError("stored companion evidence integrity conflict")
    return pack


def _conversation_turn(row: tuple[Any, ...]) -> dict[str, Any]:
    pack = _stored_pack(row[4:10])
    return {
        "client_turn_id": str(row[0]),
        "question": str(row[1]),
        "state": str(row[2]),
        "failure_code": None if row[3] is None else str(row[3]),
        "evidence_pack": pack,
        "briefing": _briefing_from_pack(str(row[1]), pack),
        "answer": _answer_from_row(row[10], row[11]),
    }


def _artifact_from_row(raw: object, digest: object) -> dict[str, Any]:
    artifact = json.loads(str(raw))
    if not isinstance(artifact, dict) or _sha(_json(artifact)) != str(digest):
        raise CompanionAnswerConflict("stored companion answer integrity conflict")
    artifact["artifact_sha256"] = str(digest)
    return artifact


def _answer_from_row(raw: object, digest: object) -> dict[str, Any] | None:
    if raw is None or digest is None:
        return None
    return cast(dict[str, Any], public_grounded_answer(_artifact_from_row(raw, digest)))


def _scope(reading: dict[str, Any]) -> dict[str, Any]:
    return {key: reading[key] for key in (
        "derived_asset_id", "revision_id", "content_sha256", "generation",
        "is_current", "exact_reader_path",
    )}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


__all__ = ["CompanionAnswerConflict", "CompanionAnswerUnavailable",
           "CompanionIdempotencyConflict", "CompanionStaleRevision",
           "DerivedCompanionRepository"]
