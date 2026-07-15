"""Private append-only SQLite journal for live guard acquisition attempts."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import stat
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from substrate.multimedia.bedrock_live_guard_acquisition import (
    LiveGuardAcquisitionAttempt,
    LiveGuardAcquisitionCommand,
    LiveGuardAcquisitionReceipt,
)

_COMMAND_ID = re.compile(r"lgc_[0-9a-f]{32}")
_ATTEMPT_ID = re.compile(r"lga_[0-9a-f]{64}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_TIMESTAMP = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

_COMMAND_COLUMNS = ("command_id", "command_digest", "command_json")
_ATTEMPT_COLUMNS = (
    "attempt_id",
    "command_id",
    "command_digest",
    "attempt_digest",
    "attempt_json",
    "attempt_nonce",
    "trusted_start",
)
_COMPLETION_COLUMNS = ("attempt_id", "receipt_digest", "receipt_json")

_TABLE_SQL = (
    """
    CREATE TABLE live_guard_commands (
        command_id TEXT PRIMARY KEY,
        command_digest TEXT NOT NULL UNIQUE,
        command_json TEXT NOT NULL UNIQUE
    ) STRICT
    """,
    """
    CREATE TABLE live_guard_attempts (
        attempt_id TEXT PRIMARY KEY,
        command_id TEXT NOT NULL,
        command_digest TEXT NOT NULL,
        attempt_digest TEXT NOT NULL UNIQUE,
        attempt_json TEXT NOT NULL UNIQUE,
        attempt_nonce TEXT NOT NULL,
        trusted_start TEXT NOT NULL,
        FOREIGN KEY (command_id) REFERENCES live_guard_commands(command_id),
        FOREIGN KEY (command_digest) REFERENCES live_guard_commands(command_digest)
    ) STRICT
    """,
    """
    CREATE TABLE live_guard_completions (
        attempt_id TEXT PRIMARY KEY,
        receipt_digest TEXT NOT NULL UNIQUE,
        receipt_json TEXT NOT NULL UNIQUE,
        FOREIGN KEY (attempt_id) REFERENCES live_guard_attempts(attempt_id)
    ) STRICT
    """,
)
_INDEX_SQL = """
CREATE INDEX live_guard_attempts_by_command
ON live_guard_attempts(command_id, trusted_start, attempt_id)
"""


def _trigger_sql(table: str, operation: str) -> str:
    return f"""
    CREATE TRIGGER {table}_no_{operation.lower()}
    BEFORE {operation} ON {table}
    BEGIN
        SELECT RAISE(ABORT, '{table} is append-only');
    END
    """


_TRIGGER_SQL = tuple(
    _trigger_sql(table, operation)
    for table in ("live_guard_commands", "live_guard_attempts", "live_guard_completions")
    for operation in ("UPDATE", "DELETE")
)


class LiveGuardJournalError(RuntimeError):
    """The acquisition journal was unsafe, unavailable, or corrupt."""


class LiveGuardJournalConflict(LiveGuardJournalError):
    """An immutable journal identity was reused with different bytes."""


class LiveGuardJournalUnavailable(LiveGuardJournalError):
    """The requested command or attempt does not exist."""


@dataclass(frozen=True)
class LiveGuardAttemptStatus:
    command_id: str
    command_digest: str
    attempt_id: str
    attempt_digest: str
    trusted_start: str
    status: str
    receipt_digest: str | None
    production_eligible: bool = False
    bedrock_version_selected: bool = False
    bedrock_read_observed: bool = False

    def __post_init__(self) -> None:
        if _COMMAND_ID.fullmatch(self.command_id) is None:
            raise ValueError("status command_id is invalid")
        if _ATTEMPT_ID.fullmatch(self.attempt_id) is None:
            raise ValueError("status attempt_id is invalid")
        for name in ("command_digest", "attempt_digest"):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"status {name} is invalid")
        if self.status not in {"in_progress", "completed"}:
            raise ValueError("status must be in_progress or completed")
        if type(self.trusted_start) is not str or _TIMESTAMP.fullmatch(self.trusted_start) is None:
            raise ValueError("status trusted_start is invalid")
        if (self.status == "completed") != (self.receipt_digest is not None):
            raise ValueError("status and receipt digest conflict")
        if self.receipt_digest is not None and _SHA256.fullmatch(self.receipt_digest) is None:
            raise ValueError("status receipt_digest is invalid")
        if any(
            value is not False
            for value in (
                self.production_eligible,
                self.bedrock_version_selected,
                self.bedrock_read_observed,
            )
        ):
            raise ValueError("journal status cannot grant production authority")

    @property
    def canonical_json(self) -> str:
        return json.dumps(self.__dict__, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


@dataclass(frozen=True)
class LiveGuardJournalIntegrityReport:
    command_count: int
    attempt_count: int
    completion_count: int
    in_progress_count: int
    integrity_verified: bool = True
    production_eligible: bool = False

    def __post_init__(self) -> None:
        for name in (
            "command_count",
            "attempt_count",
            "completion_count",
            "in_progress_count",
        ):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.completion_count + self.in_progress_count != self.attempt_count:
            raise ValueError("journal integrity counts conflict")
        if self.integrity_verified is not True or self.production_eligible is not False:
            raise ValueError("journal report capability claims are invalid")


@dataclass(frozen=True)
class LiveGuardJournalIntent:
    command_json: str
    attempt_json: str
    completed: bool
    production_eligible: bool = False

    def __post_init__(self) -> None:
        command = LiveGuardAcquisitionCommand.from_json(self.command_json)
        attempt = LiveGuardAcquisitionAttempt.from_json(self.attempt_json)
        if attempt.command_digest != command.digest:
            raise ValueError("journal intent command binding conflicts")
        if type(self.completed) is not bool or self.production_eligible is not False:
            raise ValueError("journal intent capability claims are invalid")

    @property
    def command(self) -> LiveGuardAcquisitionCommand:
        return LiveGuardAcquisitionCommand.from_json(self.command_json)

    @property
    def attempt(self) -> LiveGuardAcquisitionAttempt:
        return LiveGuardAcquisitionAttempt.from_json(self.attempt_json)


class SqliteLiveGuardAcquisitionJournal:
    def __init__(
        self,
        store_root: str | os.PathLike[str],
        *,
        timeout_seconds: float = 5.0,
        failure_hook: Callable[[str], None] | None = None,
    ) -> None:
        root = Path(store_root)
        if type(timeout_seconds) not in {int, float} or not 0 <= timeout_seconds <= 30:
            raise ValueError("timeout_seconds must be between 0 and 30")
        self.root = self._validate_root(root)
        self.path = self.root / "live-guard-acquisition.sqlite3"
        self.timeout_seconds = float(timeout_seconds)
        self.failure_hook = failure_hook

    def record_intent(self, *, command_json: str, attempt_json: str) -> None:
        try:
            command = LiveGuardAcquisitionCommand.from_json(command_json)
            attempt = LiveGuardAcquisitionAttempt.from_json(attempt_json)
        except ValueError as exc:
            raise LiveGuardJournalConflict("intent artifacts are invalid") from exc
        if attempt.command_digest != command.digest:
            raise LiveGuardJournalConflict("attempt conflicts with command identity")
        connection = self._connect(create=True)
        try:
            self._initialize(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._assert_authority(connection)
            self._insert_or_reopen_command(connection, command)
            self._fail("after_command_insert")
            self._insert_or_reopen_attempt(connection, command, attempt)
            self._fail("after_attempt_insert")
            self._fail("before_intent_commit")
            connection.commit()
            self._fail("after_intent_commit")
        except Exception as exc:
            if connection.in_transaction:
                connection.rollback()
            if isinstance(exc, LiveGuardJournalError):
                raise
            raise LiveGuardJournalError("intent transaction failed") from exc
        finally:
            connection.close()

    def commit_attempt(self, *, attempt_id: str, receipt_json: str) -> None:
        self._validate_attempt_id(attempt_id)
        try:
            receipt = LiveGuardAcquisitionReceipt.from_json(receipt_json)
        except ValueError as exc:
            raise LiveGuardJournalConflict("completion receipt is invalid") from exc
        if receipt.attempt_id != attempt_id:
            raise LiveGuardJournalConflict("completion receipt has the wrong attempt")
        connection = self._connect(create=False)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._assert_authority(connection)
            command, attempt = self._load_attempt_chain(connection, attempt_id)
            self._verify_receipt_chain(command, attempt, receipt)
            row = connection.execute(
                "SELECT receipt_digest,receipt_json FROM live_guard_completions "
                "WHERE attempt_id=? OR receipt_digest=? OR receipt_json=?",
                (attempt_id, receipt.digest, receipt.canonical_json),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO live_guard_completions VALUES (?,?,?)",
                    (attempt_id, receipt.digest, receipt.canonical_json),
                )
            elif tuple(row) != (receipt.digest, receipt.canonical_json):
                raise LiveGuardJournalConflict("completion identity conflict")
            self._fail("after_completion_insert")
            self._fail("before_completion_commit")
            connection.commit()
            self._fail("after_completion_commit")
        except Exception as exc:
            if connection.in_transaction:
                connection.rollback()
            if isinstance(exc, LiveGuardJournalError):
                raise
            raise LiveGuardJournalError("completion transaction failed") from exc
        finally:
            connection.close()

    def read_attempt(self, *, attempt_id: str) -> str | None:
        self._validate_attempt_id(attempt_id)
        connection = self._connect(create=False)
        try:
            self._assert_authority(connection)
            command, attempt = self._load_attempt_chain(connection, attempt_id)
            row = connection.execute(
                "SELECT receipt_digest,receipt_json FROM live_guard_completions WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if row is None:
                return None
            receipt = self._decode_completion(row, command, attempt)
            return receipt.canonical_json
        except sqlite3.Error as exc:
            raise LiveGuardJournalError("journal read failed") from exc
        finally:
            connection.close()

    def inspect_attempt(self, *, attempt_id: str) -> LiveGuardAttemptStatus:
        self._validate_attempt_id(attempt_id)
        connection = self._connect(create=False)
        try:
            self._assert_authority(connection)
            command, attempt = self._load_attempt_chain(connection, attempt_id)
            row = connection.execute(
                "SELECT receipt_digest,receipt_json FROM live_guard_completions WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            receipt_digest = None
            if row is not None:
                receipt_digest = self._decode_completion(row, command, attempt).digest
            return self._status(command, attempt, receipt_digest)
        except sqlite3.Error as exc:
            raise LiveGuardJournalError("journal inspection failed") from exc
        finally:
            connection.close()

    def read_intent(self, *, attempt_id: str) -> LiveGuardJournalIntent:
        self._validate_attempt_id(attempt_id)
        connection = self._connect(create=False)
        try:
            self._assert_authority(connection)
            command, attempt = self._load_attempt_chain(connection, attempt_id)
            completion = connection.execute(
                "SELECT receipt_digest,receipt_json FROM live_guard_completions WHERE attempt_id=?",
                (attempt_id,),
            ).fetchone()
            if completion is not None:
                self._decode_completion(completion, command, attempt)
            return LiveGuardJournalIntent(
                command_json=command.canonical_json,
                attempt_json=attempt.canonical_json,
                completed=completion is not None,
            )
        except sqlite3.Error as exc:
            raise LiveGuardJournalError("journal intent read failed") from exc
        finally:
            connection.close()

    def list_attempts(
        self, *, command_id: str, limit: int = 100
    ) -> tuple[LiveGuardAttemptStatus, ...]:
        self._validate_command_id(command_id)
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        connection = self._connect(create=False)
        try:
            self._assert_authority(connection)
            command_row = connection.execute(
                "SELECT command_id,command_digest,command_json FROM live_guard_commands "
                "WHERE command_id=?",
                (command_id,),
            ).fetchone()
            if command_row is None:
                raise LiveGuardJournalUnavailable("journal command is unavailable")
            command = self._decode_command(command_row)
            rows = connection.execute(
                "SELECT a.attempt_id,a.command_id,a.command_digest,a.attempt_digest,"
                "a.attempt_json,a.attempt_nonce,a.trusted_start,c.receipt_digest,c.receipt_json "
                "FROM live_guard_attempts a LEFT JOIN live_guard_completions c "
                "ON c.attempt_id=a.attempt_id WHERE a.command_id=? "
                "ORDER BY a.trusted_start,a.attempt_id LIMIT ?",
                (command_id, limit),
            ).fetchall()
            result: list[LiveGuardAttemptStatus] = []
            for row in rows:
                attempt = self._decode_attempt(row[:7], command)
                receipt_digest = None
                if row[7] is not None:
                    receipt_digest = self._decode_completion(row[7:9], command, attempt).digest
                result.append(self._status(command, attempt, receipt_digest))
            return tuple(result)
        except sqlite3.Error as exc:
            raise LiveGuardJournalError("journal listing failed") from exc
        finally:
            connection.close()

    def verify_all(self) -> LiveGuardJournalIntegrityReport:
        connection = self._connect(create=False)
        try:
            self._assert_authority(connection)
            commands: dict[str, LiveGuardAcquisitionCommand] = {}
            for row in connection.execute(
                "SELECT command_id,command_digest,command_json FROM live_guard_commands "
                "ORDER BY command_id"
            ):
                command = self._decode_command(row)
                commands[command.command_id] = command
            attempts: dict[str, tuple[LiveGuardAcquisitionCommand, LiveGuardAcquisitionAttempt]] = {}
            for row in connection.execute(
                "SELECT attempt_id,command_id,command_digest,attempt_digest,attempt_json,"
                "attempt_nonce,trusted_start FROM live_guard_attempts ORDER BY attempt_id"
            ):
                command = commands.get(str(row[1]))
                if command is None:
                    raise LiveGuardJournalError("attempt references a missing command")
                attempt = self._decode_attempt(row, command)
                attempts[attempt.attempt_id] = (command, attempt)
            completion_count = 0
            for row in connection.execute(
                "SELECT attempt_id,receipt_digest,receipt_json FROM live_guard_completions "
                "ORDER BY attempt_id"
            ):
                pair = attempts.get(str(row[0]))
                if pair is None:
                    raise LiveGuardJournalError("completion references a missing attempt")
                self._decode_completion(row[1:3], pair[0], pair[1])
                completion_count += 1
            return LiveGuardJournalIntegrityReport(
                command_count=len(commands),
                attempt_count=len(attempts),
                completion_count=completion_count,
                in_progress_count=len(attempts) - completion_count,
            )
        except sqlite3.Error as exc:
            raise LiveGuardJournalError("journal integrity traversal failed") from exc
        finally:
            connection.close()

    def _connect(self, *, create: bool) -> sqlite3.Connection:
        self._validate_root(self.root)
        if self.path.is_symlink():
            raise LiveGuardJournalError("journal path is unsafe")
        if not self.path.exists():
            if not create:
                raise LiveGuardJournalUnavailable("journal is unavailable")
            try:
                descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            except OSError as exc:
                raise LiveGuardJournalError("journal creation failed") from exc
            else:
                os.close(descriptor)
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
        except OSError as exc:
            raise LiveGuardJournalError("journal path is unsafe") from exc
        try:
            metadata = os.fstat(descriptor)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1
                or stat.S_IMODE(metadata.st_mode) != 0o600
            ):
                raise LiveGuardJournalError("journal file is not private and regular")
            try:
                connection = sqlite3.connect(
                    self.path,
                    timeout=self.timeout_seconds,
                    isolation_level=None,
                )
            except sqlite3.Error as exc:
                raise LiveGuardJournalError("journal open failed") from exc
            reopened = self.path.stat(follow_symlinks=False)
            if (
                (reopened.st_dev, reopened.st_ino) != (metadata.st_dev, metadata.st_ino)
                or not stat.S_ISREG(reopened.st_mode)
            ):
                connection.close()
                raise LiveGuardJournalError("journal path changed during open")
            try:
                connection.execute("PRAGMA foreign_keys=ON")
                connection.execute("PRAGMA trusted_schema=OFF")
                connection.execute("PRAGMA synchronous=FULL")
                mode = connection.execute("PRAGMA journal_mode=DELETE").fetchone()
                if mode is None or str(mode[0]).lower() != "delete":
                    raise LiveGuardJournalError("journal mode is not rollback-delete")
            except LiveGuardJournalError:
                connection.close()
                raise
            except sqlite3.Error as exc:
                connection.close()
                raise LiveGuardJournalError("journal configuration failed") from exc
            return connection
        finally:
            os.close(descriptor)

    def _initialize(self, connection: sqlite3.Connection) -> None:
        try:
            connection.execute("BEGIN EXCLUSIVE")
            existing = connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='live_guard_commands'"
            ).fetchone()
            if existing is None:
                for statement in (*_TABLE_SQL, _INDEX_SQL, *_TRIGGER_SQL):
                    connection.execute(statement)
            self._assert_schema(connection)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise

    def _assert_authority(self, connection: sqlite3.Connection) -> None:
        self._assert_schema(connection)
        quick = connection.execute("PRAGMA quick_check").fetchall()
        if quick != [("ok",)]:
            raise LiveGuardJournalError("journal SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise LiveGuardJournalError("journal foreign-key integrity failed")

    @staticmethod
    def _assert_schema(connection: sqlite3.Connection) -> None:
        expected = {
            "live_guard_commands": (_COMMAND_COLUMNS, _TABLE_SQL[0]),
            "live_guard_attempts": (_ATTEMPT_COLUMNS, _TABLE_SQL[1]),
            "live_guard_completions": (_COMPLETION_COLUMNS, _TABLE_SQL[2]),
        }
        for table, (columns, expected_sql) in expected.items():
            actual = tuple(row[1] for row in connection.execute(f"PRAGMA table_info({table})"))
            if actual != columns:
                raise LiveGuardJournalError("journal schema conflicts")
            sql_row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone()
            normalized = "" if sql_row is None else "".join(str(sql_row[0]).lower().split())
            if normalized != "".join(expected_sql.lower().split()):
                raise LiveGuardJournalError("journal table definition conflicts")
        index = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' "
            "AND name='live_guard_attempts_by_command'"
        ).fetchone()
        if index is None or "".join(str(index[0]).lower().split()) != "".join(
            _INDEX_SQL.lower().split()
        ):
            raise LiveGuardJournalError("journal index conflicts")
        for statement in _TRIGGER_SQL:
            name = statement.split("CREATE TRIGGER", 1)[1].split(None, 1)[0]
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='trigger' AND name=?", (name,)
            ).fetchone()
            if row is None or "".join(str(row[0]).lower().split()) != "".join(
                statement.lower().split()
            ):
                raise LiveGuardJournalError("journal append-only trigger conflicts")

    def _insert_or_reopen_command(
        self, connection: sqlite3.Connection, command: LiveGuardAcquisitionCommand
    ) -> None:
        row = connection.execute(
            "SELECT command_id,command_digest,command_json FROM live_guard_commands "
            "WHERE command_id=? OR command_digest=? OR command_json=?",
            (command.command_id, command.digest, command.canonical_json),
        ).fetchone()
        expected = (command.command_id, command.digest, command.canonical_json)
        if row is None:
            connection.execute("INSERT INTO live_guard_commands VALUES (?,?,?)", expected)
        elif tuple(row) != expected:
            raise LiveGuardJournalConflict("command identity conflict")
        else:
            self._decode_command(row)

    def _insert_or_reopen_attempt(
        self,
        connection: sqlite3.Connection,
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
    ) -> None:
        row = connection.execute(
            "SELECT attempt_id,command_id,command_digest,attempt_digest,attempt_json,"
            "attempt_nonce,trusted_start FROM live_guard_attempts WHERE attempt_id=? "
            "OR attempt_digest=? OR attempt_json=?",
            (attempt.attempt_id, attempt.digest, attempt.canonical_json),
        ).fetchone()
        expected = (
            attempt.attempt_id,
            command.command_id,
            command.digest,
            attempt.digest,
            attempt.canonical_json,
            attempt.attempt_nonce,
            attempt.trusted_start,
        )
        if row is None:
            connection.execute("INSERT INTO live_guard_attempts VALUES (?,?,?,?,?,?,?)", expected)
        elif tuple(row) != expected:
            raise LiveGuardJournalConflict("attempt identity conflict")
        else:
            self._decode_attempt(row, command)

    def _load_attempt_chain(
        self, connection: sqlite3.Connection, attempt_id: str
    ) -> tuple[LiveGuardAcquisitionCommand, LiveGuardAcquisitionAttempt]:
        row = connection.execute(
            "SELECT a.attempt_id,a.command_id,a.command_digest,a.attempt_digest,a.attempt_json,"
            "a.attempt_nonce,a.trusted_start,c.command_json FROM live_guard_attempts a "
            "JOIN live_guard_commands c ON c.command_id=a.command_id WHERE a.attempt_id=?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise LiveGuardJournalUnavailable("journal attempt is unavailable")
        command_row = connection.execute(
            "SELECT command_id,command_digest,command_json FROM live_guard_commands "
            "WHERE command_id=?",
            (row[1],),
        ).fetchone()
        if command_row is None:
            raise LiveGuardJournalError("attempt command is unavailable")
        command = self._decode_command(command_row)
        attempt = self._decode_attempt(row[:7], command)
        return command, attempt

    @staticmethod
    def _decode_command(row: object) -> LiveGuardAcquisitionCommand:
        try:
            values = tuple(row)  # type: ignore[arg-type]
            command = LiveGuardAcquisitionCommand.from_json(values[2])
        except (TypeError, ValueError, IndexError) as exc:
            raise LiveGuardJournalError("stored command is corrupt") from exc
        if values != (command.command_id, command.digest, command.canonical_json):
            raise LiveGuardJournalError("stored command scalar integrity conflicts")
        return command

    @staticmethod
    def _decode_attempt(
        row: object, command: LiveGuardAcquisitionCommand
    ) -> LiveGuardAcquisitionAttempt:
        try:
            values = tuple(row)  # type: ignore[arg-type]
            attempt = LiveGuardAcquisitionAttempt.from_json(values[4])
        except (TypeError, ValueError, IndexError) as exc:
            raise LiveGuardJournalError("stored attempt is corrupt") from exc
        expected = (
            attempt.attempt_id,
            command.command_id,
            command.digest,
            attempt.digest,
            attempt.canonical_json,
            attempt.attempt_nonce,
            attempt.trusted_start,
        )
        if values != expected or attempt.command_digest != command.digest:
            raise LiveGuardJournalError("stored attempt scalar integrity conflicts")
        return attempt

    @classmethod
    def _decode_completion(
        cls,
        row: object,
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
    ) -> LiveGuardAcquisitionReceipt:
        try:
            values = tuple(row)  # type: ignore[arg-type]
            receipt = LiveGuardAcquisitionReceipt.from_json(values[1])
        except (TypeError, ValueError, IndexError) as exc:
            raise LiveGuardJournalError("stored completion is corrupt") from exc
        if values != (receipt.digest, receipt.canonical_json):
            raise LiveGuardJournalError("stored completion scalar integrity conflicts")
        cls._verify_receipt_chain(command, attempt, receipt)
        return receipt

    @staticmethod
    def _verify_receipt_chain(
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
        receipt: LiveGuardAcquisitionReceipt,
    ) -> None:
        if (
            receipt.command_digest != command.digest
            or receipt.cycle34_receipt_digest != command.cycle34_receipt_digest
            or receipt.predecessor_receipt_digest != command.predecessor_receipt_digest
            or receipt.attempt_id != attempt.attempt_id
            or receipt.attempt_digest != attempt.digest
            or receipt.attempt_nonce != attempt.attempt_nonce
            or receipt.trusted_start != attempt.trusted_start
        ):
            raise LiveGuardJournalConflict("completion conflicts with intent chain")

    @staticmethod
    def _status(
        command: LiveGuardAcquisitionCommand,
        attempt: LiveGuardAcquisitionAttempt,
        receipt_digest: str | None,
    ) -> LiveGuardAttemptStatus:
        return LiveGuardAttemptStatus(
            command_id=command.command_id,
            command_digest=command.digest,
            attempt_id=attempt.attempt_id,
            attempt_digest=attempt.digest,
            trusted_start=attempt.trusted_start,
            status="completed" if receipt_digest is not None else "in_progress",
            receipt_digest=receipt_digest,
        )

    @staticmethod
    def _validate_root(root: Path) -> Path:
        if not root.is_absolute() or root.is_symlink() or root.resolve() != root:
            raise ValueError("journal store root is unsafe")
        try:
            metadata = root.stat(follow_symlinks=False)
        except OSError as exc:
            raise ValueError("journal store root is unavailable") from exc
        if (
            not stat.S_ISDIR(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) != 0o700
        ):
            raise ValueError("journal store root must be private mode 0700")
        return root

    @staticmethod
    def _validate_command_id(value: object) -> None:
        if type(value) is not str or _COMMAND_ID.fullmatch(value) is None:
            raise ValueError("command_id is invalid")

    @staticmethod
    def _validate_attempt_id(value: object) -> None:
        if type(value) is not str or _ATTEMPT_ID.fullmatch(value) is None:
            raise ValueError("attempt_id is invalid")

    def _fail(self, stage: str) -> None:
        if self.failure_hook is not None:
            self.failure_hook(stage)


__all__ = [
    "LiveGuardAttemptStatus",
    "LiveGuardJournalConflict",
    "LiveGuardJournalError",
    "LiveGuardJournalIntegrityReport",
    "LiveGuardJournalIntent",
    "LiveGuardJournalUnavailable",
    "SqliteLiveGuardAcquisitionJournal",
]
