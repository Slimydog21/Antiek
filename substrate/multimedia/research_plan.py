"""Owner-private research plans seeded from verified multimedia intents."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import sqlite3
import stat
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

from .research_intent import ResearchIntent

_SCHEMA = """
CREATE TABLE IF NOT EXISTS multimedia_research_plans (
  plan_id TEXT PRIMARY KEY,
  owner_identity_digest TEXT NOT NULL,
  source_intent_id TEXT NOT NULL,
  source_intent_digest TEXT NOT NULL,
  source_evidence_digest TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  request_digest TEXT NOT NULL,
  plan_version INTEGER NOT NULL,
  plan_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  UNIQUE(owner_identity_digest, idempotency_key),
  UNIQUE(owner_identity_digest, source_intent_id)
)
"""
_COLUMNS = (
    "plan_id", "owner_identity_digest", "source_intent_id", "source_intent_digest",
    "source_evidence_digest", "idempotency_key", "request_digest", "plan_version",
    "plan_json", "created_at", "updated_at",
)
_MAX_RECORD_BYTES = 128_000


class ResearchPlanError(RuntimeError):
    """The plan is unavailable or conflicts with immutable authority."""


class ResearchPlanUnavailableError(ResearchPlanError):
    """No owner-visible plan exists for the requested identity."""


class ResearchPlanStorageError(ResearchPlanError):
    """The private plan authority cannot be read or written safely."""


@dataclass(frozen=True)
class ResearchPlan:
    plan_id: str
    source_intent_id: str
    source_intent_digest: str
    source_evidence_digest: str
    request_digest: str
    state: str
    plan_version: int
    tree: dict[str, object]
    created_at: str
    updated_at: str
    approved_at: str | None = None
    approved_by_owner_digest: str | None = None
    research_launched: bool = False
    provider_launch_authorized: bool = False
    spend_authority_digest: None = None


class ResearchPlanLedger:
    def __init__(self, store_root: str | os.PathLike[str]) -> None:
        root = Path(store_root)
        if not root.is_dir() or root.is_symlink():
            raise ValueError("multimedia store root is invalid")
        metadata = root.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o022:
            raise ValueError("multimedia store root is not privately controlled")
        self.path = root / "research-plans.sqlite3"

    def handoff(
        self, *, owner_identity_digest: str, idempotency_key: str, intent: ResearchIntent
    ) -> tuple[ResearchPlan, bool]:
        _validate_owner(owner_identity_digest)
        if not isinstance(idempotency_key, str) or not 16 <= len(idempotency_key) <= 128:
            raise ResearchPlanError("research plan idempotency key is invalid")
        seed = intent.plan_seed
        request_digest = _digest({
            "source_intent_id": intent.intent_id,
            "source_intent_digest": seed["intent_digest"],
            "source_evidence_digest": intent.evidence_digest,
            "question": intent.question,
        })
        now = _now()
        plan = ResearchPlan(
            plan_id="mrp_" + secrets.token_hex(24),
            source_intent_id=intent.intent_id,
            source_intent_digest=seed["intent_digest"],
            source_evidence_digest=intent.evidence_digest,
            request_digest=request_digest,
            state="draft",
            plan_version=1,
            tree={
                "root": {
                    "kind": "research_question",
                    "question": intent.question,
                    "source_intent_id": intent.intent_id,
                    "source_intent_digest": seed["intent_digest"],
                    "source_evidence_digest": intent.evidence_digest,
                    "children": [],
                }
            },
            created_at=now,
            updated_at=now,
        )
        raw = _canonical({
            "owner_identity_digest": owner_identity_digest,
            "idempotency_key": idempotency_key,
            "plan": asdict(plan),
        })
        if len(raw.encode()) > _MAX_RECORD_BYTES:
            raise ResearchPlanError("research plan is too large")
        connection = self._connect()
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT idempotency_key, request_digest, source_intent_id, "
                "source_intent_digest, source_evidence_digest, plan_version, plan_json, "
                "plan_id, created_at, updated_at "
                "FROM multimedia_research_plans "
                "WHERE owner_identity_digest=? AND "
                "(idempotency_key=? OR source_intent_id=?)",
                (owner_identity_digest, idempotency_key, intent.intent_id),
            ).fetchone()
            if row is not None:
                if row[0] != idempotency_key or row[1] != request_digest:
                    raise ResearchPlanError("research plan idempotency conflict")
                reopened = self._decode(
                    row[6], owner_identity_digest=owner_identity_digest,
                    idempotency_key=idempotency_key,
                )
                self._assert_row(reopened, row_request_digest=row[1], row=row[2:])
                connection.commit()
                return reopened, False
            connection.execute(
                "INSERT INTO multimedia_research_plans VALUES "
                "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (plan.plan_id, owner_identity_digest, plan.source_intent_id,
                 plan.source_intent_digest, plan.source_evidence_digest, idempotency_key,
                 plan.request_digest, plan.plan_version, raw, plan.created_at, plan.updated_at),
            )
            connection.commit()
            return plan, True
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, *, owner_identity_digest: str, plan_id: str) -> ResearchPlan:
        _validate_owner(owner_identity_digest)
        row = self._read_row(owner_identity_digest=owner_identity_digest, plan_id=plan_id)
        plan = self._decode(row[6], owner_identity_digest=owner_identity_digest, idempotency_key=row[0])
        self._assert_row(plan, row_request_digest=row[1], row=row[2:])
        return plan

    def approve(
        self, *, owner_identity_digest: str, plan_id: str, expected_plan_version: int
    ) -> ResearchPlan:
        _validate_owner(owner_identity_digest)
        if type(expected_plan_version) is not int or expected_plan_version < 1:
            raise ResearchPlanError("research plan version is invalid")
        connection = self._connect_existing()
        try:
            self._assert_schema(connection)
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT idempotency_key, request_digest, source_intent_id, "
                "source_intent_digest, source_evidence_digest, plan_version, plan_json, "
                "plan_id, created_at, updated_at "
                "FROM multimedia_research_plans WHERE owner_identity_digest=? AND plan_id=?",
                (owner_identity_digest, plan_id),
            ).fetchone()
            if row is None:
                raise ResearchPlanUnavailableError("research plan is unavailable")
            plan = self._decode(row[6], owner_identity_digest=owner_identity_digest, idempotency_key=row[0])
            self._assert_row(plan, row_request_digest=row[1], row=row[2:])
            if plan.plan_version != expected_plan_version:
                raise ResearchPlanError("research plan version conflict")
            if plan.state == "approved":
                connection.commit()
                return plan
            now = _now()
            approved = replace(
                plan, state="approved", approved_at=now,
                approved_by_owner_digest=owner_identity_digest, updated_at=now,
            )
            raw = _canonical({
                "owner_identity_digest": owner_identity_digest,
                "idempotency_key": row[0],
                "plan": asdict(approved),
            })
            changed = connection.execute(
                "UPDATE multimedia_research_plans SET plan_json=?, updated_at=? "
                "WHERE owner_identity_digest=? AND plan_id=? AND plan_version=?",
                (raw, now, owner_identity_digest, plan_id, expected_plan_version),
            ).rowcount
            if changed != 1:
                raise ResearchPlanError("research plan version conflict")
            connection.commit()
            return approved
        except sqlite3.Error as exc:
            connection.rollback()
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _read_row(self, *, owner_identity_digest: str, plan_id: str) -> tuple[object, ...]:
        connection = self._connect_existing()
        try:
            self._assert_schema(connection)
            row = connection.execute(
                "SELECT idempotency_key, request_digest, source_intent_id, "
                "source_intent_digest, source_evidence_digest, plan_version, plan_json, "
                "plan_id, created_at, updated_at "
                "FROM multimedia_research_plans WHERE owner_identity_digest=? AND plan_id=?",
                (owner_identity_digest, plan_id),
            ).fetchone()
        except sqlite3.Error as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        finally:
            connection.close()
        if row is None:
            raise ResearchPlanUnavailableError("research plan is unavailable")
        return row

    def _connect_existing(self) -> sqlite3.Connection:
        if not self.path.is_file() or self.path.is_symlink():
            raise ResearchPlanUnavailableError("research plan is unavailable")
        return self._connect()

    def _connect(self) -> sqlite3.Connection:
        if self.path.is_symlink():
            raise ResearchPlanError("research plan ledger path is unsafe")
        if not self.path.exists():
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            except OSError as exc:
                raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
            else:
                os.close(fd)
        try:
            fd = os.open(self.path, os.O_RDWR | getattr(os, "O_NOFOLLOW", 0))
        except OSError as exc:
            raise ResearchPlanStorageError("research plan ledger is unavailable") from exc
        try:
            metadata = os.fstat(fd)
            if (not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1
                    or stat.S_IMODE(metadata.st_mode) & 0o077):
                raise ResearchPlanError("research plan ledger path is unsafe")
            connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
            reopened = self.path.stat(follow_symlinks=False)
            if (reopened.st_dev, reopened.st_ino) != (metadata.st_dev, metadata.st_ino):
                connection.close()
                raise ResearchPlanError("research plan ledger path changed during open")
            return connection
        finally:
            os.close(fd)

    def _initialize(self, connection: sqlite3.Connection) -> None:
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='multimedia_research_plans'"
        ).fetchone() is None:
            connection.execute(_SCHEMA)
        self._assert_schema(connection)

    def _assert_schema(self, connection: sqlite3.Connection) -> None:
        columns = tuple(row[1] for row in connection.execute(
            "PRAGMA table_info(multimedia_research_plans)"
        ))
        schema = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='multimedia_research_plans'"
        ).fetchone()
        normalized = "" if schema is None else "".join(str(schema[0]).lower().split())
        required = (
            "unique(owner_identity_digest,idempotency_key)",
            "unique(owner_identity_digest,source_intent_id)",
        )
        if columns != _COLUMNS or not all(item in normalized for item in required):
            raise ResearchPlanError("research plan ledger schema conflicts")

    @staticmethod
    def _decode(raw: object, *, owner_identity_digest: str, idempotency_key: str) -> ResearchPlan:
        try:
            envelope = json.loads(str(raw))
            if (set(envelope) != {"owner_identity_digest", "idempotency_key", "plan"}
                    or envelope["owner_identity_digest"] != owner_identity_digest
                    or envelope["idempotency_key"] != idempotency_key):
                raise ResearchPlanError("stored research plan binding conflicts")
            plan = ResearchPlan(**envelope["plan"])
        except ResearchPlanError:
            raise
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ResearchPlanError("stored research plan is malformed") from exc
        if len(str(raw).encode()) > _MAX_RECORD_BYTES:
            raise ResearchPlanError("stored research plan is too large")
        try:
            _assert_plan_integrity(plan, owner_identity_digest)
        except ResearchPlanError:
            raise
        except (AttributeError, TypeError, ValueError) as exc:
            raise ResearchPlanError("stored research plan is malformed") from exc
        return plan

    @staticmethod
    def _assert_row(
        plan: ResearchPlan, *, row_request_digest: object,
        row: tuple[object, ...] | None = None,
    ) -> None:
        if plan.request_digest != row_request_digest:
            raise ResearchPlanError("stored research plan integrity conflicts")
        if row is not None:
            expected = (
                plan.source_intent_id, plan.source_intent_digest,
                plan.source_evidence_digest, plan.plan_version,
            )
            row_identity = (plan.plan_id, plan.created_at, plan.updated_at)
            if expected != tuple(row[:4]) or row_identity != tuple(row[5:8]):
                raise ResearchPlanError("stored research plan integrity conflicts")


def _assert_plan_integrity(plan: ResearchPlan, owner_identity_digest: str) -> None:
    root = plan.tree.get("root") if isinstance(plan.tree, dict) else None
    expected_request = _digest({
        "source_intent_id": plan.source_intent_id,
        "source_intent_digest": plan.source_intent_digest,
        "source_evidence_digest": plan.source_evidence_digest,
        "question": root.get("question") if isinstance(root, dict) else None,
    })
    if (
        not plan.plan_id.startswith("mrp_") or len(plan.plan_id) != 52
        or any(character not in "0123456789abcdef" for character in plan.plan_id[4:])
        or not _opaque_id(plan.source_intent_id, prefix="mmri_", hex_length=48)
        or not _hex_digest(plan.source_intent_digest)
        or not _hex_digest(plan.source_evidence_digest)
        or not _hex_digest(plan.request_digest)
        or not _timestamp(plan.created_at) or not _timestamp(plan.updated_at)
        or plan.plan_version != 1 or plan.state not in {"draft", "approved"}
        or not isinstance(root, dict)
        or set(plan.tree) != {"root"}
        or set(root) != {
            "kind", "question", "source_intent_id", "source_intent_digest",
            "source_evidence_digest", "children",
        }
        or not isinstance(root.get("question"), str)
        or not 3 <= len(root["question"]) <= 2000
        or root.get("source_intent_id") != plan.source_intent_id
        or root.get("source_intent_digest") != plan.source_intent_digest
        or root.get("source_evidence_digest") != plan.source_evidence_digest
        or root.get("children") != [] or root.get("kind") != "research_question"
        or plan.request_digest != expected_request
        or plan.research_launched is not False
        or plan.provider_launch_authorized is not False
        or plan.spend_authority_digest is not None
        or (plan.state == "draft" and (plan.approved_at is not None or plan.approved_by_owner_digest is not None))
        or (plan.state == "approved" and (
            not _timestamp(plan.approved_at)
            or plan.approved_by_owner_digest != owner_identity_digest
        ))
    ):
        raise ResearchPlanError("stored research plan integrity conflicts")


def _validate_owner(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ResearchPlanError("research plan owner identity is invalid")


def _hex_digest(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _opaque_id(value: object, *, prefix: str, hex_length: int) -> bool:
    return (
        isinstance(value, str)
        and value.startswith(prefix)
        and len(value) == len(prefix) + hex_length
        and all(character in "0123456789abcdef" for character in value[len(prefix):])
    )


def _timestamp(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        parsed = datetime.fromisoformat(value.removesuffix("Z") + "+00:00")
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode()).hexdigest()


def _now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


__all__ = [
    "ResearchPlan", "ResearchPlanError", "ResearchPlanLedger", "ResearchPlanStorageError",
    "ResearchPlanUnavailableError",
]
