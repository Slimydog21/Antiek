"""Evidence-bound owner review authority for canonical twin proposals."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import stat
import time
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from runtime.db_lock import LockedConnection, _lock_path_for, is_active_write_connection
from substrate.constants import SERVABLE_CONTENT_CLASSES
from substrate.research_artifact.schema import ResearchArtifactBody

from .canonical_reader import CanonicalTwinReader, CanonicalTwinReaderNotFound
from .ledger import TwinRecursionLedger

PROMOTION_SCHEMA = "antiek.canonical-twin-evidence-promotion.v1"
APPLICATION_ID = 0x41545052
SCHEMA_VERSION = 1
MAX_CANDIDATE_CHARS = 8_000
MAX_EXCERPT_CHARS = 2_000
MAX_EXCERPTS = 16
CandidateKind = Literal["insight", "question"]
Decision = Literal["accepted", "rejected"]


class TwinEvidencePromotionError(RuntimeError):
    """Candidate, evidence, review, or persisted authority is contradictory."""


@dataclass(frozen=True)
class EvidenceExcerptRequest:
    document_id: str
    chunk_id: str
    start: int
    end: int


@dataclass(frozen=True)
class EvidenceExcerpt:
    document_id: str
    chunk_id: str
    start: int
    end: int
    text: str
    text_sha256: str
    chunk_sha256: str
    document_sha256: str
    source_envelope_sha256: str
    content_class: str


@dataclass(frozen=True)
class TwinPromotionCandidate:
    candidate_id: str
    schema: str
    owner_id: str
    source_asset_id: str
    source_hash: str
    binding_id: str
    twin_document_id: str
    twin_chunk_id: str
    twin_chunk_sha256: str
    body_hash: str
    completion_digest: str
    kind: CandidateKind
    text: str
    evidence: tuple[EvidenceExcerpt, ...]


@dataclass(frozen=True)
class TwinPromotionReview:
    review_id: str
    candidate_id: str
    owner_id: str
    decision: Decision
    rationale: str
    candidate_digest: str
    issued_at_unix: int
    expires_at_unix: int
    nonce: str
    key_id: str
    signature: str


@dataclass(frozen=True)
class OwnerReviewAuthorization:
    owner_id: str
    candidate_id: str
    candidate_digest: str
    decision: Decision
    rationale: str
    issued_at_unix: int
    expires_at_unix: int
    nonce: str
    key_id: str
    signature: str


@dataclass(frozen=True)
class AcceptedTwinPromotionAuthority:
    candidate: TwinPromotionCandidate
    review: TwinPromotionReview
    authority: Literal["owner_reviewed_evidence_bound_candidate_v1"] = (
        "owner_reviewed_evidence_bound_candidate_v1"
    )


_DDL = (
    "CREATE TABLE promotion_meta (singleton INTEGER PRIMARY KEY CHECK(singleton=1), "
    "schema TEXT NOT NULL, schema_digest TEXT NOT NULL, owner_id TEXT NOT NULL, "
    "review_key_id TEXT NOT NULL)",
    "CREATE TABLE promotion_candidates (candidate_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, "
    "candidate_json TEXT NOT NULL, candidate_digest TEXT NOT NULL UNIQUE)",
    "CREATE TABLE promotion_reviews (review_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL UNIQUE, "
    "owner_id TEXT NOT NULL, decision TEXT NOT NULL CHECK(decision IN ('accepted','rejected')), "
    "rationale TEXT NOT NULL, review_json TEXT NOT NULL, FOREIGN KEY(candidate_id) "
    "REFERENCES promotion_candidates(candidate_id))",
    "CREATE TABLE promotion_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, "
    "subject_id TEXT NOT NULL, payload_json TEXT NOT NULL, payload_sha256 TEXT NOT NULL, "
    "previous_hash TEXT NOT NULL, "
    "event_hash TEXT NOT NULL UNIQUE)",
    "CREATE TRIGGER promotion_candidates_no_update BEFORE UPDATE ON promotion_candidates BEGIN "
    "SELECT RAISE(ABORT,'promotion candidates are immutable'); END",
    "CREATE TRIGGER promotion_meta_no_update BEFORE UPDATE ON promotion_meta BEGIN "
    "SELECT RAISE(ABORT,'promotion metadata is immutable'); END",
    "CREATE TRIGGER promotion_meta_no_delete BEFORE DELETE ON promotion_meta BEGIN "
    "SELECT RAISE(ABORT,'promotion metadata is immutable'); END",
    "CREATE TRIGGER promotion_candidates_no_delete BEFORE DELETE ON promotion_candidates BEGIN "
    "SELECT RAISE(ABORT,'promotion candidates are immutable'); END",
    "CREATE TRIGGER promotion_reviews_no_update BEFORE UPDATE ON promotion_reviews BEGIN "
    "SELECT RAISE(ABORT,'promotion reviews are immutable'); END",
    "CREATE TRIGGER promotion_reviews_no_delete BEFORE DELETE ON promotion_reviews BEGIN "
    "SELECT RAISE(ABORT,'promotion reviews are immutable'); END",
    "CREATE TRIGGER promotion_events_no_update BEFORE UPDATE ON promotion_events BEGIN "
    "SELECT RAISE(ABORT,'promotion events are immutable'); END",
    "CREATE TRIGGER promotion_events_no_delete BEFORE DELETE ON promotion_events BEGIN "
    "SELECT RAISE(ABORT,'promotion events are immutable'); END",
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _schema_digest() -> str:
    return _sha(_canonical(_DDL))


def _text(value: object, name: str, maximum: int = 512) -> str:
    if type(value) is not str or not value or value.strip() != value or len(value) > maximum:
        raise TwinEvidencePromotionError(f"{name} must be exact bounded non-empty text")
    return value


def _safe_candidate_text(value: object) -> str:
    text = _text(value, "candidate text", MAX_CANDIDATE_CHARS)
    if any(unicodedata.category(character).startswith("C") for character in text):
        raise TwinEvidencePromotionError("candidate text contains control characters")
    return text


def _authorization_payload(value: OwnerReviewAuthorization) -> str:
    return _canonical({key: item for key, item in asdict(value).items() if key != "signature"})


def issue_owner_review_authorization(
    signing_seed: bytes,
    *,
    owner_id: str,
    candidate_id: str,
    candidate_digest: str,
    decision: Decision,
    rationale: str,
    issued_at_unix: int,
    expires_at_unix: int,
    nonce: str,
) -> OwnerReviewAuthorization:
    signing = SigningKey(signing_seed)
    key_id = "review-key-" + hashlib.sha256(bytes(signing.verify_key)).hexdigest()
    unsigned = OwnerReviewAuthorization(
        owner_id,
        candidate_id,
        candidate_digest,
        decision,
        rationale,
        issued_at_unix,
        expires_at_unix,
        nonce,
        key_id,
        "",
    )
    signature = signing.sign(_authorization_payload(unsigned).encode()).signature.hex()
    return OwnerReviewAuthorization(**{**asdict(unsigned), "signature": signature})


def _candidate_payload(candidate: TwinPromotionCandidate) -> dict[str, object]:
    return asdict(candidate)


def _require_graph_lock(con: LockedConnection) -> None:
    if not is_active_write_connection(con):
        raise TwinEvidencePromotionError("active graph write lock is required")
    fd = getattr(con, "_lock_fd", None)
    lock_path = getattr(con, "_lock_path", None)
    db_path = getattr(con, "_db_path", None)
    if (
        isinstance(fd, bool)
        or not isinstance(fd, int)
        or not isinstance(lock_path, str)
        or not lock_path
        or not isinstance(db_path, str)
        or not db_path
    ):
        raise TwinEvidencePromotionError("graph lock identity is unavailable")
    try:
        canonical_db_path = os.path.realpath(os.path.abspath(db_path))
        canonical_lock_path = os.path.realpath(os.path.abspath(lock_path))
        expected_lock_path = os.path.realpath(os.path.abspath(_lock_path_for(canonical_db_path)))
        database_rows = con.execute("PRAGMA database_list").fetchall()
        if (
            canonical_lock_path != expected_lock_path
            or not database_rows
            or len(database_rows[0]) < 3
            or not database_rows[0][2]
            or os.path.realpath(os.path.abspath(database_rows[0][2])) != canonical_db_path
        ):
            raise TwinEvidencePromotionError("graph lock target changed")
        descriptor = os.fstat(fd)
        path = os.stat(lock_path, follow_symlinks=False)
        if (
            not stat.S_ISREG(descriptor.st_mode)
            or not stat.S_ISREG(path.st_mode)
            or (descriptor.st_dev, descriptor.st_ino) != (path.st_dev, path.st_ino)
        ):
            raise TwinEvidencePromotionError("graph lock identity changed")
    except (OSError, ValueError) as exc:
        raise TwinEvidencePromotionError("exclusive graph lock is unavailable") from exc


def _candidate_from_json(value: str) -> TwinPromotionCandidate:
    try:
        raw = json.loads(value)
        evidence = tuple(EvidenceExcerpt(**item) for item in raw.pop("evidence"))
        candidate = TwinPromotionCandidate(**raw, evidence=evidence)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TwinEvidencePromotionError("stored promotion candidate is malformed") from exc
    if _canonical(_candidate_payload(candidate)) != value:
        raise TwinEvidencePromotionError("stored promotion candidate is noncanonical")
    return candidate


class TwinEvidencePromotionLedger:
    """Stage exact evidence and record owner review without mutating the graph."""

    def __init__(
        self,
        path: str | Path,
        *,
        owner_id: str,
        review_verify_key: bytes,
        clock: object = time.time,
    ):
        self.path = str(path)
        self._owner_id = _text(owner_id, "owner_id")
        if type(review_verify_key) is not bytes or len(review_verify_key) != 32:
            raise TwinEvidencePromotionError("review verification key is invalid")
        self._review_key = VerifyKey(review_verify_key)
        self._review_key_id = "review-key-" + hashlib.sha256(review_verify_key).hexdigest()
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._clock = clock
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.execute("PRAGMA foreign_keys=ON")
        con.row_factory = sqlite3.Row
        return con

    def _verify_signed_review(self, review: TwinPromotionReview) -> None:
        authorization = OwnerReviewAuthorization(
            review.owner_id,
            review.candidate_id,
            review.candidate_digest,
            review.decision,
            review.rationale,
            review.issued_at_unix,
            review.expires_at_unix,
            review.nonce,
            review.key_id,
            review.signature,
        )
        if review.key_id != self._review_key_id:
            raise TwinEvidencePromotionError("stored review key is invalid")
        try:
            self._review_key.verify(
                _authorization_payload(authorization).encode(),
                bytes.fromhex(review.signature),
            )
        except (BadSignatureError, ValueError) as exc:
            raise TwinEvidencePromotionError("stored review signature is invalid") from exc

    def _initialize(self) -> None:
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            application_id = int(con.execute("PRAGMA application_id").fetchone()[0])
            version = int(con.execute("PRAGMA user_version").fetchone()[0])
            if application_id not in (0, APPLICATION_ID) or version not in (0, SCHEMA_VERSION):
                raise TwinEvidencePromotionError("promotion database authority is incompatible")
            if version == 0:
                con.execute(f"PRAGMA application_id={APPLICATION_ID}")
                for statement in _DDL:
                    con.execute(statement)
                con.execute(
                    "INSERT INTO promotion_meta VALUES (1,?,?,?,?)",
                    [PROMOTION_SCHEMA, _schema_digest(), self._owner_id, self._review_key_id],
                )
                con.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            self._verify_schema(con)
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        finally:
            con.close()

    def _verify_schema(self, con: sqlite3.Connection) -> None:
        if int(con.execute("PRAGMA application_id").fetchone()[0]) != APPLICATION_ID:
            raise TwinEvidencePromotionError("promotion database application id changed")
        if int(con.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
            raise TwinEvidencePromotionError("promotion database schema changed")
        expected = {
            statement.split()[2]: statement
            for statement in _DDL
            if statement.startswith("CREATE TABLE")
        }
        expected.update(
            {
                statement.split()[2]: statement
                for statement in _DDL
                if statement.startswith("CREATE TRIGGER")
            }
        )
        rows = con.execute(
            "SELECT name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        if set(expected) != {row["name"] for row in rows}:
            raise TwinEvidencePromotionError("promotion database objects changed")

        def normalized(value: str) -> str:
            return " ".join(value.replace("IF NOT EXISTS ", "").split())

        if any(normalized(row["sql"]) != normalized(expected[row["name"]]) for row in rows):
            raise TwinEvidencePromotionError("promotion database definitions changed")
        meta = con.execute(
            "SELECT singleton,schema,schema_digest,owner_id,review_key_id FROM promotion_meta"
        ).fetchall()
        if [tuple(row) for row in meta] != [
            (1, PROMOTION_SCHEMA, _schema_digest(), self._owner_id, self._review_key_id)
        ]:
            raise TwinEvidencePromotionError("promotion database metadata changed")

    @staticmethod
    def _append_event(
        con: sqlite3.Connection, event_type: str, subject_id: str, payload: str
    ) -> None:
        row = con.execute(
            "SELECT sequence,event_hash FROM promotion_events ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous = row["event_hash"] if row else "0" * 64
        sequence = (int(row["sequence"]) + 1) if row else 1
        payload_sha = _sha(payload)
        event_hash = _sha(_canonical([sequence, event_type, subject_id, payload_sha, previous]))
        con.execute(
            "INSERT INTO promotion_events(event_type,subject_id,payload_json,payload_sha256,"
            "previous_hash,event_hash) VALUES (?,?,?,?,?,?)",
            [event_type, subject_id, payload, payload_sha, previous, event_hash],
        )

    @staticmethod
    def _origin(
        con: LockedConnection,
        twins: TwinRecursionLedger,
        *,
        owner_id: str,
        source_asset_id: str,
        source_hash: str,
        kind: CandidateKind,
        text: str,
    ) -> tuple[str, str, str, str, str, str]:
        _require_graph_lock(con)
        if type(twins) is not TwinRecursionLedger:
            raise TypeError("promotion requires exact locked graph and canonical twin authorities")
        if kind not in ("insight", "question"):
            raise TwinEvidencePromotionError("candidate kind is not promotable")
        try:
            view = CanonicalTwinReader(con, twins).read_by_source(
                owner_id=owner_id,
                source_asset_id=source_asset_id,
                source_hash=source_hash,
            )
        except CanonicalTwinReaderNotFound as exc:
            raise TwinEvidencePromotionError("canonical twin is unavailable") from exc
        row = con.execute(
            "SELECT metadata FROM documents WHERE document_id=?", [view.document_id]
        ).fetchone()
        try:
            metadata = json.loads(row[0])
            binding_id = metadata["binding_id"]
            twin_chunk_id = metadata["chunk_id"]
            with twins.canonical_publication(binding_id) as publication:
                body = ResearchArtifactBody.model_validate_json(publication.body_json)
                prefix = "Proposed insight: " if kind == "insight" else "Proposed question: "
                matches = [
                    note[len(prefix) :] for note in body.agent_notes if note.startswith(prefix)
                ]
                if matches.count(text) != 1:
                    raise TwinEvidencePromotionError(
                        "candidate is not one unique structured twin proposal"
                    )
                if (
                    publication.account_id != owner_id
                    or publication.source_asset_id != source_asset_id
                    or publication.source_hash != source_hash
                    or publication.twin_id != view.document_id
                    or publication.body_hash != metadata["body_hash"]
                    or publication.completion_digest != metadata["completion_digest"]
                ):
                    raise TwinEvidencePromotionError("canonical proposal origin changed")
                return (
                    binding_id,
                    view.document_id,
                    twin_chunk_id,
                    metadata["chunk_sha256"],
                    publication.body_hash,
                    publication.completion_digest,
                )
        except TwinEvidencePromotionError:
            raise
        except Exception as exc:
            raise TwinEvidencePromotionError("canonical proposal origin is malformed") from exc

    @staticmethod
    def _evidence(
        con: LockedConnection,
        *,
        owner_id: str,
        twin_document_id: str,
        requests: tuple[EvidenceExcerptRequest, ...],
    ) -> tuple[EvidenceExcerpt, ...]:
        if type(requests) is not tuple or not 1 <= len(requests) <= MAX_EXCERPTS:
            raise TwinEvidencePromotionError("evidence must be a bounded immutable tuple")
        resolved: list[EvidenceExcerpt] = []
        seen: set[tuple[str, str, int, int]] = set()
        for request in requests:
            if type(request) is not EvidenceExcerptRequest:
                raise TwinEvidencePromotionError("evidence request type is invalid")
            document_id = _text(request.document_id, "document_id")
            chunk_id = _text(request.chunk_id, "chunk_id")
            if (
                isinstance(request.start, bool)
                or isinstance(request.end, bool)
                or not isinstance(request.start, int)
                or not isinstance(request.end, int)
                or not 0 <= request.start < request.end
                or request.end - request.start > MAX_EXCERPT_CHARS
            ):
                raise TwinEvidencePromotionError("evidence range is invalid")
            identity = (document_id, chunk_id, request.start, request.end)
            if identity in seen:
                raise TwinEvidencePromotionError("duplicate evidence excerpt")
            seen.add(identity)
            row = con.execute(
                "SELECT c.document_id,c.text,d.document_type,d.content_class,d.owner_user_id,"
                "d.raw_text,d.twin_source_envelope,COALESCE(b.taken_down,FALSE) "
                "FROM chunks c JOIN documents d ON d.document_id=c.document_id "
                "LEFT JOIN book_assets b ON b.document_id=d.document_id "
                "WHERE c.chunk_id=? AND d.document_id=?",
                [chunk_id, document_id],
            ).fetchone()
            if (
                row is None
                or row[0] != document_id
                or document_id == twin_document_id
                or row[2] == "canonical_twin"
                or row[7] is True
                or not (row[4] == owner_id or row[3] in SERVABLE_CONTENT_CLASSES)
                or request.end > len(row[1])
            ):
                raise TwinEvidencePromotionError("evidence excerpt is unavailable")
            excerpt = row[1][request.start : request.end]
            if not excerpt.strip():
                raise TwinEvidencePromotionError("evidence excerpt is empty")
            resolved.append(
                EvidenceExcerpt(
                    document_id,
                    chunk_id,
                    request.start,
                    request.end,
                    excerpt,
                    _sha(excerpt),
                    _sha(row[1]),
                    _sha(row[5]),
                    _sha(row[6] or ""),
                    row[3],
                )
            )
        return tuple(resolved)

    def stage(
        self,
        con: LockedConnection,
        twins: TwinRecursionLedger,
        *,
        owner_id: str,
        source_asset_id: str,
        source_hash: str,
        kind: CandidateKind,
        text: str,
        evidence: tuple[EvidenceExcerptRequest, ...],
    ) -> TwinPromotionCandidate:
        owner_id = _text(owner_id, "owner_id")
        if owner_id != self._owner_id:
            raise TwinEvidencePromotionError("promotion ledger owner is unavailable")
        source_asset_id = _text(source_asset_id, "source_asset_id")
        source_hash = _text(source_hash, "source_hash")
        text = _safe_candidate_text(text)
        (
            binding_id,
            twin_document_id,
            twin_chunk_id,
            twin_chunk_sha256,
            body_hash,
            completion,
        ) = self._origin(
            con,
            twins,
            owner_id=owner_id,
            source_asset_id=source_asset_id,
            source_hash=source_hash,
            kind=kind,
            text=text,
        )
        excerpts = self._evidence(
            con,
            owner_id=owner_id,
            twin_document_id=twin_document_id,
            requests=evidence,
        )
        if sum(len(item.text) for item in excerpts) > MAX_EXCERPT_CHARS * 4:
            raise TwinEvidencePromotionError("aggregate evidence exceeds the bounded contract")
        identity = {
            "schema": PROMOTION_SCHEMA,
            "owner_id": owner_id,
            "source_asset_id": source_asset_id,
            "source_hash": source_hash,
            "binding_id": binding_id,
            "twin_document_id": twin_document_id,
            "twin_chunk_id": twin_chunk_id,
            "twin_chunk_sha256": twin_chunk_sha256,
            "body_hash": body_hash,
            "completion_digest": completion,
            "kind": kind,
            "text": text,
            "evidence": [asdict(item) for item in excerpts],
        }
        candidate_id = "twin-promotion-" + _sha(_canonical(identity))
        candidate = TwinPromotionCandidate(
            candidate_id,
            PROMOTION_SCHEMA,
            owner_id,
            source_asset_id,
            source_hash,
            binding_id,
            twin_document_id,
            twin_chunk_id,
            twin_chunk_sha256,
            body_hash,
            completion,
            kind,
            text,
            excerpts,
        )
        payload = _canonical(_candidate_payload(candidate))
        digest = _sha(payload)
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            self._verify_schema(db)
            row = db.execute(
                "SELECT candidate_json,candidate_digest FROM promotion_candidates WHERE candidate_id=?",
                [candidate_id],
            ).fetchone()
            if row is None:
                db.execute(
                    "INSERT INTO promotion_candidates VALUES (?,?,?,?)",
                    [candidate_id, owner_id, payload, digest],
                )
                self._append_event(db, "candidate_staged", candidate_id, payload)
            elif row["candidate_json"] != payload or row["candidate_digest"] != digest:
                raise TwinEvidencePromotionError("candidate identity conflicts")
            db.execute("COMMIT")
            return candidate
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def _revalidate(
        self,
        con: LockedConnection,
        twins: TwinRecursionLedger,
        candidate: TwinPromotionCandidate,
    ) -> None:
        origin = self._origin(
            con,
            twins,
            owner_id=candidate.owner_id,
            source_asset_id=candidate.source_asset_id,
            source_hash=candidate.source_hash,
            kind=candidate.kind,
            text=candidate.text,
        )
        if origin != (
            candidate.binding_id,
            candidate.twin_document_id,
            candidate.twin_chunk_id,
            candidate.twin_chunk_sha256,
            candidate.body_hash,
            candidate.completion_digest,
        ):
            raise TwinEvidencePromotionError("candidate origin changed")
        requests = tuple(
            EvidenceExcerptRequest(item.document_id, item.chunk_id, item.start, item.end)
            for item in candidate.evidence
        )
        if (
            self._evidence(
                con,
                owner_id=candidate.owner_id,
                twin_document_id=candidate.twin_document_id,
                requests=requests,
            )
            != candidate.evidence
        ):
            raise TwinEvidencePromotionError("candidate evidence changed")

    def decide(
        self,
        con: LockedConnection,
        twins: TwinRecursionLedger,
        *,
        authorization: OwnerReviewAuthorization,
    ) -> TwinPromotionReview:
        if type(authorization) is not OwnerReviewAuthorization:
            raise TwinEvidencePromotionError("owner review authorization is required")
        owner_id = _text(authorization.owner_id, "owner_id")
        if owner_id != self._owner_id:
            raise TwinEvidencePromotionError("promotion ledger owner is unavailable")
        candidate_id = _text(authorization.candidate_id, "candidate_id")
        candidate_digest = _text(authorization.candidate_digest, "candidate_digest", 64)
        rationale = _text(authorization.rationale, "rationale", 2_000)
        decision = authorization.decision
        if (
            decision not in ("accepted", "rejected")
            or authorization.key_id != self._review_key_id
            or isinstance(authorization.issued_at_unix, bool)
            or isinstance(authorization.expires_at_unix, bool)
            or not isinstance(authorization.issued_at_unix, int)
            or not isinstance(authorization.expires_at_unix, int)
            or not authorization.issued_at_unix
            <= int(self._clock())
            <= authorization.expires_at_unix
            or authorization.expires_at_unix - authorization.issued_at_unix > 900
        ):
            raise TwinEvidencePromotionError("review decision is invalid")
        _text(authorization.nonce, "review nonce", 128)
        try:
            self._review_key.verify(
                _authorization_payload(authorization).encode(),
                bytes.fromhex(authorization.signature),
            )
        except (BadSignatureError, ValueError) as exc:
            raise TwinEvidencePromotionError("owner review signature is invalid") from exc
        db = self._connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            self._verify_schema(db)
            row = db.execute(
                "SELECT owner_id,candidate_json,candidate_digest FROM promotion_candidates "
                "WHERE candidate_id=?",
                [candidate_id],
            ).fetchone()
            if (
                row is None
                or row["owner_id"] != owner_id
                or row["candidate_digest"] != candidate_digest
            ):
                raise TwinEvidencePromotionError("candidate review authority is unavailable")
            candidate = _candidate_from_json(row["candidate_json"])
            self._revalidate(con, twins, candidate)
            review_identity = {
                "candidate_id": candidate_id,
                "owner_id": owner_id,
                "decision": decision,
                "rationale": rationale,
                "candidate_digest": candidate_digest,
                "issued_at_unix": authorization.issued_at_unix,
                "expires_at_unix": authorization.expires_at_unix,
                "nonce": authorization.nonce,
                "key_id": authorization.key_id,
                "signature": authorization.signature,
            }
            review_id = "twin-review-" + _sha(_canonical(review_identity))
            review = TwinPromotionReview(
                review_id,
                candidate_id,
                owner_id,
                decision,
                rationale,
                candidate_digest,
                authorization.issued_at_unix,
                authorization.expires_at_unix,
                authorization.nonce,
                authorization.key_id,
                authorization.signature,
            )
            payload = _canonical(asdict(review))
            existing = db.execute(
                "SELECT review_json FROM promotion_reviews WHERE candidate_id=?", [candidate_id]
            ).fetchone()
            if existing is None:
                db.execute(
                    "INSERT INTO promotion_reviews VALUES (?,?,?,?,?,?)",
                    [review_id, candidate_id, owner_id, decision, rationale, payload],
                )
                self._append_event(db, "candidate_reviewed", review_id, payload)
            elif existing["review_json"] != payload:
                raise TwinEvidencePromotionError("candidate already has another review")
            self._revalidate(con, twins, candidate)
            db.execute("COMMIT")
            return review
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def accepted(
        self,
        con: LockedConnection,
        twins: TwinRecursionLedger,
        *,
        owner_id: str,
        candidate_id: str,
    ) -> AcceptedTwinPromotionAuthority:
        owner_id = _text(owner_id, "owner_id")
        if owner_id != self._owner_id:
            raise TwinEvidencePromotionError("promotion ledger owner is unavailable")
        candidate_id = _text(candidate_id, "candidate_id")
        db = self._connect()
        try:
            db.execute("BEGIN")
            self._verify_schema(db)
            self.verify_integrity()
            row = db.execute(
                "SELECT c.candidate_json,c.candidate_digest,r.review_json,r.decision "
                "FROM promotion_candidates c JOIN promotion_reviews r USING(candidate_id) "
                "WHERE c.candidate_id=? AND c.owner_id=? AND r.owner_id=?",
                [candidate_id, owner_id, owner_id],
            ).fetchone()
            if row is None or row["decision"] != "accepted":
                raise TwinEvidencePromotionError("accepted promotion authority is unavailable")
            candidate = _candidate_from_json(row["candidate_json"])
            try:
                review = TwinPromotionReview(**json.loads(row["review_json"]))
            except (TypeError, ValueError, json.JSONDecodeError) as exc:
                raise TwinEvidencePromotionError("stored promotion review is malformed") from exc
            if (
                _sha(row["candidate_json"]) != row["candidate_digest"]
                or review.candidate_digest != row["candidate_digest"]
                or review.candidate_id != candidate.candidate_id
                or review.owner_id != owner_id
                or review.decision != "accepted"
                or review.review_id
                != "twin-review-"
                + _sha(
                    _canonical(
                        {key: value for key, value in asdict(review).items() if key != "review_id"}
                    )
                )
                or _canonical(asdict(review)) != row["review_json"]
            ):
                raise TwinEvidencePromotionError("accepted promotion authority conflicts")
            self._verify_signed_review(review)
            stage_event = db.execute(
                "SELECT payload_json FROM promotion_events WHERE event_type='candidate_staged' "
                "AND subject_id=?",
                [candidate_id],
            ).fetchall()
            review_event = db.execute(
                "SELECT payload_json FROM promotion_events WHERE event_type='candidate_reviewed' "
                "AND subject_id=?",
                [review.review_id],
            ).fetchall()
            if [item["payload_json"] for item in stage_event] != [row["candidate_json"]] or [
                item["payload_json"] for item in review_event
            ] != [row["review_json"]]:
                raise TwinEvidencePromotionError("accepted promotion history is incomplete")
            self._revalidate(con, twins, candidate)
            db.execute("COMMIT")
            return AcceptedTwinPromotionAuthority(candidate, review)
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()

    def verify_integrity(self) -> None:
        db = self._connect()
        try:
            db.execute("BEGIN")
            self._verify_schema(db)
            candidates: dict[str, str] = {}
            reviews: dict[str, str] = {}
            previous = "0" * 64
            for expected_sequence, row in enumerate(
                db.execute("SELECT * FROM promotion_events ORDER BY sequence"), start=1
            ):
                if _canonical(json.loads(row["payload_json"])) != row["payload_json"]:
                    raise TwinEvidencePromotionError("promotion event payload is noncanonical")
                event_hash = _sha(
                    _canonical(
                        [
                            expected_sequence,
                            row["event_type"],
                            row["subject_id"],
                            row["payload_sha256"],
                            previous,
                        ]
                    )
                )
                if (
                    row["sequence"] != expected_sequence
                    or _sha(row["payload_json"]) != row["payload_sha256"]
                    or row["previous_hash"] != previous
                    or row["event_hash"] != event_hash
                ):
                    raise TwinEvidencePromotionError("promotion event chain changed")
                previous = event_hash
                if row["event_type"] == "candidate_staged":
                    if row["subject_id"] in candidates:
                        raise TwinEvidencePromotionError("candidate has duplicate staging events")
                    candidates[row["subject_id"]] = row["payload_json"]
                elif row["event_type"] == "candidate_reviewed":
                    payload = json.loads(row["payload_json"])
                    candidate_id = payload.get("candidate_id")
                    if (
                        type(candidate_id) is not str
                        or candidate_id not in candidates
                        or candidate_id in reviews
                    ):
                        raise TwinEvidencePromotionError("candidate review event order is invalid")
                    reviews[candidate_id] = row["payload_json"]
                else:
                    raise TwinEvidencePromotionError("promotion event type changed")
            for row in db.execute(
                "SELECT candidate_id,owner_id,candidate_json,candidate_digest "
                "FROM promotion_candidates"
            ):
                candidate = _candidate_from_json(row["candidate_json"])
                if (
                    _sha(row["candidate_json"]) != row["candidate_digest"]
                    or candidate.owner_id != row["owner_id"]
                    or candidate.candidate_id
                    != "twin-promotion-"
                    + _sha(
                        _canonical(
                            {
                                key: value
                                for key, value in _candidate_payload(candidate).items()
                                if key != "candidate_id"
                            }
                        )
                    )
                ):
                    raise TwinEvidencePromotionError("promotion candidate digest changed")
                if candidates.pop(row["candidate_id"], None) != row["candidate_json"]:
                    raise TwinEvidencePromotionError("candidate event projection changed")
            if candidates:
                raise TwinEvidencePromotionError("orphan candidate events exist")
            for row in db.execute(
                "SELECT review_id,candidate_id,owner_id,decision,rationale,review_json "
                "FROM promotion_reviews"
            ):
                try:
                    review = TwinPromotionReview(**json.loads(row["review_json"]))
                except (TypeError, ValueError, json.JSONDecodeError) as exc:
                    raise TwinEvidencePromotionError("stored review is malformed") from exc
                if (
                    _canonical(asdict(review)) != row["review_json"]
                    or (
                        review.review_id,
                        review.candidate_id,
                        review.owner_id,
                        review.decision,
                        review.rationale,
                    )
                    != (
                        row["review_id"],
                        row["candidate_id"],
                        row["owner_id"],
                        row["decision"],
                        row["rationale"],
                    )
                    or review.review_id
                    != "twin-review-"
                    + _sha(
                        _canonical(
                            {
                                key: value
                                for key, value in asdict(review).items()
                                if key != "review_id"
                            }
                        )
                    )
                ):
                    raise TwinEvidencePromotionError("review projection changed")
                self._verify_signed_review(review)
                if reviews.pop(row["candidate_id"], None) != row["review_json"]:
                    raise TwinEvidencePromotionError("review event projection changed")
            if reviews:
                raise TwinEvidencePromotionError("orphan review events exist")
            db.execute("COMMIT")
        except Exception:
            db.execute("ROLLBACK")
            raise
        finally:
            db.close()


__all__ = [
    "AcceptedTwinPromotionAuthority",
    "EvidenceExcerpt",
    "EvidenceExcerptRequest",
    "OwnerReviewAuthorization",
    "PROMOTION_SCHEMA",
    "TwinEvidencePromotionError",
    "TwinEvidencePromotionLedger",
    "TwinPromotionCandidate",
    "TwinPromotionReview",
    "issue_owner_review_authorization",
]
