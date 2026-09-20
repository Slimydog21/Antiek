"""Durable, owner-bound snapshots of verified audio research intent."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from .verified_audio_playback import AudioEvidenceSourceMetadata, AudioLearnedClaimMetadata

_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_research_intents (
  intent_id TEXT PRIMARY KEY,
  owner_identity_digest TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  evidence_digest TEXT NOT NULL,
  record_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE(owner_identity_digest, idempotency_key)
)
"""
_COLUMNS = (
    "intent_id", "owner_identity_digest", "idempotency_key", "request_digest",
    "evidence_digest", "record_json", "created_at",
)
_OWNER_DIGEST_LENGTH = 64
_MAX_RECORD_BYTES = 128_000


class ResearchIntentError(RuntimeError):
    """The intent is unavailable or conflicts with immutable authority."""


class ResearchIntentUnavailableError(ResearchIntentError):
    """No owner-visible intent exists for the requested identity."""


@dataclass(frozen=True)
class ResearchIntent:
    intent_id: str
    state: str
    asset_id: str
    revision_id: str
    receipt_sha256: str
    audio_sha256: str
    chapter_id: str
    line_id: str
    question: str
    claim_text: str
    follow_up_prompt: str
    evidence_sources: tuple[AudioEvidenceSourceMetadata, ...]
    evidence_digest: str
    request_digest: str
    created_at: str
    plan_handoff_status: str = "blocked_unowned_plan_store"
    provider_launch_authorized: bool = False
    spend_authority_digest: None = None

    @property
    def plan_seed(self) -> dict[str, str]:
        return {
            "question": self.question,
            "intent_id": self.intent_id,
            "intent_digest": _digest(self._immutable_payload()),
            "evidence_digest": self.evidence_digest,
        }

    def _immutable_payload(self) -> dict[str, object]:
        return {
            key: value
            for key, value in asdict(self).items()
            if key not in {"plan_handoff_status", "provider_launch_authorized", "spend_authority_digest"}
        }


class ResearchIntentLedger:
    def __init__(self, store_root: str | os.PathLike[str]) -> None:
        root = Path(store_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("multimedia store root is invalid")
        root_metadata = root.stat()
        if root_metadata.st_uid != os.getuid() or stat.S_IMODE(root_metadata.st_mode) & 0o022:
            raise ValueError("multimedia store root is not privately controlled")
        self.path = root / "research-intents.sqlite3"

    def create(
        self,
        *,
        owner_identity_digest: str,
        idempotency_key: str,
        asset_id: str,
        revision_id: str,
        receipt_sha256: str,
        audio_sha256: str,
        question: str,
        claim: AudioLearnedClaimMetadata,
    ) -> tuple[ResearchIntent, bool]:
        _validate_create_input(
            owner_identity_digest=owner_identity_digest,
            idempotency_key=idempotency_key,
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=receipt_sha256,
            audio_sha256=audio_sha256,
            question=question,
            claim=claim,
        )
        evidence = {
            "asset_id": asset_id,
            "revision_id": revision_id,
            "receipt_sha256": receipt_sha256,
            "audio_sha256": audio_sha256,
            "chapter_id": claim.chapter_id,
            "line_id": claim.line_id,
            "claim_text": claim.claim_text,
            "follow_up_prompt": claim.follow_up_prompt,
            "evidence_sources": [asdict(source) for source in claim.evidence_sources],
        }
        evidence_digest = _digest(evidence)
        request_digest = _digest({**evidence, "question": question})
        created_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        intent = ResearchIntent(
            intent_id="mmri_" + secrets.token_hex(24),
            state="prepared",
            asset_id=asset_id,
            revision_id=revision_id,
            receipt_sha256=receipt_sha256,
            audio_sha256=audio_sha256,
            chapter_id=claim.chapter_id,
            line_id=claim.line_id,
            question=question,
            claim_text=claim.claim_text,
            follow_up_prompt=claim.follow_up_prompt,
            evidence_sources=claim.evidence_sources,
            evidence_digest=evidence_digest,
            request_digest=request_digest,
            created_at=created_at,
        )
        record_json = _canonical({
            "owner_identity_digest": owner_identity_digest,
            "idempotency_key": idempotency_key,
            "intent": asdict(intent),
        })
        if len(record_json.encode("utf-8")) > _MAX_RECORD_BYTES:
            raise ResearchIntentError("research intent evidence is too large")
        connection = self._connect()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT request_digest, evidence_digest, record_json FROM multimedia_research_intents "
                "WHERE owner_identity_digest=? AND idempotency_key=?",
                (owner_identity_digest, idempotency_key),
            ).fetchone()
            if row is not None:
                if row[0] != request_digest or row[1] != evidence_digest:
                    raise ResearchIntentError("research intent idempotency conflict")
                reopened = self._decode(
                    row[2],
                    expected_owner_identity_digest=owner_identity_digest,
                    expected_idempotency_key=idempotency_key,
                )
                if (
                    reopened.request_digest != row[0]
                    or reopened.evidence_digest != row[1]
                ):
                    raise ResearchIntentError("stored research intent integrity conflicts")
                connection.commit()
                return reopened, False
            connection.execute(
                "INSERT INTO multimedia_research_intents VALUES (?, ?, ?, ?, ?, ?, ?)",
                (intent.intent_id, owner_identity_digest, idempotency_key, request_digest,
                 evidence_digest, record_json, created_at),
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return intent, True

    def get(self, *, owner_identity_digest: str, intent_id: str) -> ResearchIntent:
        if not self.path.is_file() or self.path.is_symlink():
            raise ResearchIntentUnavailableError("research intent is unavailable")
        connection = self._connect()
        try:
            self._assert_schema(connection)
            row = connection.execute(
                "SELECT idempotency_key, request_digest, evidence_digest, record_json "
                "FROM multimedia_research_intents "
                "WHERE owner_identity_digest=? AND intent_id=?",
                (owner_identity_digest, intent_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise ResearchIntentError("research intent ledger is unavailable") from exc
        finally:
            connection.close()
        if row is None:
            raise ResearchIntentUnavailableError("research intent is unavailable")
        intent = self._decode(
            row[3],
            expected_owner_identity_digest=owner_identity_digest,
            expected_idempotency_key=row[0],
        )
        if intent.request_digest != row[1] or intent.evidence_digest != row[2]:
            raise ResearchIntentError("stored research intent integrity conflicts")
        return intent

    def _connect(self) -> sqlite3.Connection:
        if self.path.is_symlink():
            raise ResearchIntentError("research intent ledger path is unsafe")
        if not self.path.exists():
            try:
                descriptor = os.open(
                    self.path,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                    0o600,
                )
            except FileExistsError:
                pass
            else:
                os.close(descriptor)
        try:
            descriptor = os.open(self.path, os.O_RDWR | os.O_NOFOLLOW)
        except OSError as exc:
            raise ResearchIntentError("research intent ledger path is unsafe") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) & 0o077
            ):
                raise ResearchIntentError("research intent ledger path is unsafe")
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            reopened = self.path.stat(follow_symlinks=False)
            if (
                reopened.st_dev != metadata.st_dev
                or reopened.st_ino != metadata.st_ino
                or not stat.S_ISREG(reopened.st_mode)
            ):
                connection.close()
                raise ResearchIntentError("research intent ledger path changed during open")
            return connection
        finally:
            os.close(descriptor)

    def _initialize(self, connection: sqlite3.Connection) -> None:
        existing = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='multimedia_research_intents'"
        ).fetchone()
        if existing is None:
            connection.execute(_SCHEMA)
        self._assert_schema(connection)

    def _assert_schema(self, connection: sqlite3.Connection) -> None:
        columns = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(multimedia_research_intents)"
        ).fetchall())
        if columns != _COLUMNS:
            raise ResearchIntentError("research intent ledger schema conflicts")
        schema_row = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' "
            "AND name='multimedia_research_intents'"
        ).fetchone()
        normalized = "" if schema_row is None else "".join(str(schema_row[0]).lower().split())
        if "unique(owner_identity_digest,idempotency_key)" not in normalized:
            raise ResearchIntentError("research intent ledger schema conflicts")

    @staticmethod
    def _decode(
        raw: object,
        *,
        expected_owner_identity_digest: str,
        expected_idempotency_key: str,
    ) -> ResearchIntent:
        try:
            envelope = json.loads(str(raw))
            if (
                set(envelope) != {"owner_identity_digest", "idempotency_key", "intent"}
                or envelope["owner_identity_digest"] != expected_owner_identity_digest
                or envelope["idempotency_key"] != expected_idempotency_key
            ):
                raise ResearchIntentError("stored research intent binding conflicts")
            values = envelope["intent"]
            values["evidence_sources"] = tuple(
                AudioEvidenceSourceMetadata(**source) for source in values["evidence_sources"]
            )
            intent = ResearchIntent(**values)
        except ResearchIntentError:
            raise
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchIntentError("stored research intent is malformed") from exc
        evidence = {
            "asset_id": intent.asset_id, "revision_id": intent.revision_id,
            "receipt_sha256": intent.receipt_sha256, "audio_sha256": intent.audio_sha256,
            "chapter_id": intent.chapter_id, "line_id": intent.line_id,
            "claim_text": intent.claim_text, "follow_up_prompt": intent.follow_up_prompt,
            "evidence_sources": [asdict(source) for source in intent.evidence_sources],
        }
        if (
            intent.state != "prepared"
            or intent.plan_handoff_status != "blocked_unowned_plan_store"
            or intent.provider_launch_authorized is not False
            or intent.spend_authority_digest is not None
            or intent.evidence_digest != _digest(evidence)
            or intent.request_digest != _digest({**evidence, "question": intent.question})
        ):
            raise ResearchIntentError("stored research intent integrity conflicts")
        return intent


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _validate_create_input(
    *,
    owner_identity_digest: str,
    idempotency_key: str,
    asset_id: str,
    revision_id: str,
    receipt_sha256: str,
    audio_sha256: str,
    question: str,
    claim: AudioLearnedClaimMetadata,
) -> None:
    if (
        len(owner_identity_digest) != _OWNER_DIGEST_LENGTH
        or any(character not in "0123456789abcdef" for character in owner_identity_digest)
    ):
        raise ResearchIntentError("research intent owner identity is invalid")
    for name, value, minimum, maximum in (
        ("idempotency key", idempotency_key, 16, 128),
        ("asset id", asset_id, 1, 128),
        ("revision id", revision_id, 1, 128),
        ("question", question, 3, 2000),
    ):
        if not isinstance(value, str) or value != value.strip() or not minimum <= len(value) <= maximum:
            raise ResearchIntentError(f"research intent {name} is invalid")
    for name, value in (("receipt", receipt_sha256), ("audio", audio_sha256)):
        if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
            raise ResearchIntentError(f"research intent {name} digest is invalid")
    if claim.evidence_status != "verified_exact" or not claim.evidence_sources:
        raise ResearchIntentError("exact claim evidence is unavailable")
    if len(claim.evidence_sources) != claim.source_count:
        raise ResearchIntentError("research intent evidence count conflicts")


__all__ = [
    "ResearchIntent",
    "ResearchIntentError",
    "ResearchIntentLedger",
    "ResearchIntentUnavailableError",
]
