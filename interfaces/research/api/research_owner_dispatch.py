"""Task-local owner-model authority for the paid Loop One roles."""

from __future__ import annotations

import contextvars
import hashlib
import json
import os
import sqlite3
import stat
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from interfaces.research.api.owner_byot_dispatch import dispatch_talk_to_book_byot
from interfaces.research.api.settings_models_admin import UserModelChoice
from substrate.dispatch.router import DispatchResult

PAID_LOOP_ONE_ROLES = (
    "decomposer", "evidence_retriever", "parameter_extractor", "connector",
    "synthesizer", "knowledge_extractor",
)
OWNER_LAUNCH_VERSION = 1
MAX_CHILD_ATTEMPTS = 2


class OwnerLaunchConflict(RuntimeError):
    pass


def _claim_db_path() -> Path:
    configured = os.environ.get("ANTIEK_OWNER_LAUNCH_DB")
    if configured:
        return Path(configured).expanduser()
    events = Path(os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR", "~/.antiek/events")).expanduser()
    return events.parent / "owner-launches.sqlite3"


def _claim_owner_launch_locked(*, operation_id: str, owner_user_id: str,
                       launch_digest: str, investigation_id: str) -> tuple[str, bool, str]:
    """Atomically claim a globally unique operation id, restart-safely.

    Returns the canonical investigation id and whether this is an exact replay.
    Owner changes and request mutation are deliberately indistinguishable.
    """
    path = _claim_db_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    parent_meta = path.parent.lstat()
    if (not stat.S_ISDIR(parent_meta.st_mode) or parent_meta.st_uid != os.geteuid()
            or stat.S_IMODE(parent_meta.st_mode) & 0o077):
        raise OwnerLaunchConflict("owner_model_operation_conflict")
    if path.exists():
        meta = path.lstat()
        if (not stat.S_ISREG(meta.st_mode) or meta.st_uid != os.geteuid()
                or stat.S_IMODE(meta.st_mode) & 0o077):
            raise OwnerLaunchConflict("owner_model_operation_conflict")
    con = sqlite3.connect(path, timeout=30)
    try:
        os.chmod(path, 0o600)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA user_version = 1")
        con.execute("CREATE TABLE IF NOT EXISTS owner_launch_claims ("
                    "operation_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL, "
                    "launch_digest TEXT NOT NULL, investigation_id TEXT NOT NULL, "
                    "version INTEGER NOT NULL CHECK(version > 0), "
                    "state TEXT NOT NULL DEFAULT 'claimed' "
                    "CHECK(state IN ('claimed','appended','broadcasting','broadcast','terminal')), start_event_id TEXT)")
        columns = {r[1] for r in con.execute("PRAGMA table_info(owner_launch_claims)")}
        if "state" not in columns:
            con.execute("ALTER TABLE owner_launch_claims ADD COLUMN state TEXT NOT NULL DEFAULT 'claimed'")
        if "start_event_id" not in columns:
            con.execute("ALTER TABLE owner_launch_claims ADD COLUMN start_event_id TEXT")
        if con.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise OwnerLaunchConflict("owner_model_operation_conflict")
        con.execute("BEGIN IMMEDIATE")
        row = con.execute(
            "SELECT owner_user_id, launch_digest, investigation_id, version "
            "FROM owner_launch_claims WHERE operation_id = ?", (operation_id,),
        ).fetchone()
        if row is None:
            start_event_id = "evt-owner-" + hashlib.sha256(
                f"{operation_id}:{launch_digest}".encode()).hexdigest()[:24]
            con.execute("INSERT INTO owner_launch_claims "
                        "(operation_id, owner_user_id, launch_digest, investigation_id, version, start_event_id) "
                        "VALUES (?, ?, ?, ?, ?, ?)",
                        (operation_id, owner_user_id, launch_digest,
                         investigation_id, OWNER_LAUNCH_VERSION, start_event_id))
            con.commit()
            return investigation_id, False, start_event_id
        if row != (owner_user_id, launch_digest, investigation_id, OWNER_LAUNCH_VERSION):
            raise OwnerLaunchConflict("owner_model_operation_conflict")
        con.commit()
        event_id = con.execute("SELECT start_event_id FROM owner_launch_claims "
                               "WHERE operation_id = ?", (operation_id,)).fetchone()[0]
        return investigation_id, True, str(event_id)
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def claim_owner_launch(*, operation_id: str, owner_user_id: str,
                       launch_digest: str, investigation_id: str) -> tuple[str, bool, str]:
    """Claim using the same authority flock as every later state mutation."""
    from runtime.db_lock import authority_handoff_guard
    path = str(_claim_db_path())
    Path(path).parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    # 30s matches sqlite's busy timeout: 8-way concurrent identical launches
    # serialize on this flock, and a loaded CI/dev machine can hold it past
    # the default 5s (CI flake WriteLockTimeout on
    # test_exact_concurrent_owner_requests_are_one_event_and_one_response).
    with authority_handoff_guard(
        path, purpose="research-owner-authority-handoff", timeout_s=30.0,
    ):
        return _claim_owner_launch_locked(
            operation_id=operation_id, owner_user_id=owner_user_id,
            launch_digest=launch_digest, investigation_id=investigation_id,
        )


def owner_launch_state(operation_id: str) -> str | None:
    """Return durable delivery progress for an already claimed launch."""
    con = sqlite3.connect(_claim_db_path())
    try:
        row = con.execute(
            "SELECT state FROM owner_launch_claims WHERE operation_id = ?", (operation_id,),
        ).fetchone()
        return None if row is None else str(row[0])
    finally:
        con.close()


def advance_owner_launch(operation_id: str, expected: str, target: str) -> None:
    """CAS launch progress under the same authority flock used by dispatch."""
    from runtime.db_lock import authority_handoff_guard
    path = str(_claim_db_path())
    # Same 30s rationale as claim_owner_launch: concurrent twins serialize.
    with authority_handoff_guard(
        path, purpose="research-owner-authority-handoff", timeout_s=30.0,
    ):
        con = sqlite3.connect(path, timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE owner_launch_claims SET state = ? WHERE operation_id = ? AND state = ?",
                (target, operation_id, expected),
            ).rowcount
            if changed != 1:
                current = con.execute(
                    "SELECT state FROM owner_launch_claims WHERE operation_id = ?", (operation_id,),
                ).fetchone()
                if current is None or current[0] != target:
                    raise OwnerLaunchConflict("owner_model_operation_conflict")
            con.commit()
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def claim_owner_broadcast(operation_id: str) -> bool:
    """Elect exactly one broadcaster for an appended launch."""
    from runtime.db_lock import authority_handoff_guard
    path = str(_claim_db_path())
    # Same 30s rationale as claim_owner_launch: concurrent twins serialize.
    with authority_handoff_guard(
        path, purpose="research-owner-authority-handoff", timeout_s=30.0,
    ):
        con = sqlite3.connect(path, timeout=30)
        try:
            con.execute("BEGIN IMMEDIATE")
            changed = con.execute(
                "UPDATE owner_launch_claims SET state = 'broadcasting' "
                "WHERE operation_id = ? AND state = 'appended'",
                (operation_id,),
            ).rowcount
            con.commit()
            return changed == 1
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()


def _resource_digest(owner: str, investigation: str, version: int, state: str) -> str:
    return hashlib.sha256(json.dumps(
        {"owner": owner, "investigation": investigation, "version": version, "state": state},
        sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()


def launch_resource_digest(manifest: ResearchOwnerManifest) -> str:
    return _resource_digest(manifest.owner_user_id, manifest.investigation_id,
                            OWNER_LAUNCH_VERSION, "broadcast")


@contextmanager
def launch_authority_guard(manifest: ResearchOwnerManifest) -> Iterator[str]:
    from runtime.db_lock import authority_handoff_guard
    path = str(_claim_db_path())
    with authority_handoff_guard(path, purpose="research-owner-authority-handoff"):
        con = sqlite3.connect(path)
        try:
            row = con.execute(
                "SELECT owner_user_id, investigation_id, version, state "
                "FROM owner_launch_claims WHERE operation_id = ?", (manifest.operation_id,),
            ).fetchone()
        finally:
            con.close()
        yield "" if row is None else _resource_digest(*row)


@dataclass(frozen=True)
class ResearchOwnerManifest:
    app: FastAPI
    owner_user_id: str
    investigation_id: str
    operation_id: str
    choices: Mapping[str, UserModelChoice]
    launch_digest: str = ""


_CURRENT: contextvars.ContextVar[ResearchOwnerManifest | None] = contextvars.ContextVar(
    "research_owner_manifest", default=None
)


def install_manifest(manifest: ResearchOwnerManifest) -> contextvars.Token[ResearchOwnerManifest | None]:
    return _CURRENT.set(manifest)


def reset_manifest(token: contextvars.Token[ResearchOwnerManifest | None]) -> None:
    _CURRENT.reset(token)


def dispatch_loop_one(prompt: str, role: str, *, investigation_id: str,
                      semantic_call_id: str | None = None, attempt: int = 0,
                      parent_event_id: str | None = None, **legacy: object) -> DispatchResult | None:
    """Dispatch an owner-selected rung, or return None for the byte-stable legacy path."""
    manifest = _CURRENT.get()
    if manifest is None:
        return None
    choice = manifest.choices[role]
    # The durable requested-event identity is the stable call ordinal for the
    # fan-out roles. Prompt digest disambiguates same-event repair attempts.
    if attempt < 0 or attempt >= MAX_CHILD_ATTEMPTS:
        raise ValueError("owner model attempt limit exceeded")
    call_identity = semantic_call_id or f"{role}:legacy"
    child_id = f"{manifest.operation_id}:{role}:v{OWNER_LAUNCH_VERSION}:{call_identity}:attempt:{attempt}"
    fact_digest = launch_resource_digest(manifest)
    result, _authority = dispatch_talk_to_book_byot(
        app=manifest.app,
        request_owner_user_id=manifest.owner_user_id,
        resource_owner_user_id=manifest.owner_user_id,
        document_id=manifest.investigation_id,
        choice=choice,
        prompt=prompt,
        investigation_id=investigation_id,
        logical_operation_id=child_id,
        role=role,
        action=f"research.loop_one.{role}",
        resource_authority_digest=fact_digest,
        resource_authority_guard=lambda: launch_authority_guard(manifest),
    )
    return result
