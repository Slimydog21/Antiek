"""Owner-scoped artifact identity and immutable render-version ledger."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.db_lock import FlockWriteCoordinator, connect_read
from substrate.research_artifact.paths import (
    artifact_version_path_for,
    atomic_write_nofollow,
    unlink_anchored,
)

_DDL = """
CREATE TABLE IF NOT EXISTS research_artifacts (
  artifact_id VARCHAR PRIMARY KEY,
  investigation_id VARCHAR NOT NULL,
  owner_user_id VARCHAR NOT NULL,
  source_path VARCHAR NOT NULL,
  source_hash VARCHAR,
  state VARCHAR NOT NULL DEFAULT 'ready',
  selected_style VARCHAR,
  latest_version INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
ALTER TABLE research_artifacts ADD COLUMN IF NOT EXISTS source_hash VARCHAR;
ALTER TABLE research_artifacts ADD COLUMN IF NOT EXISTS state VARCHAR DEFAULT 'ready';
CREATE TABLE IF NOT EXISTS research_artifact_versions (
  artifact_id VARCHAR NOT NULL,
  version INTEGER NOT NULL,
  owner_user_id VARCHAR NOT NULL,
  style_name VARCHAR NOT NULL,
  html_path VARCHAR NOT NULL,
  content_hash VARCHAR NOT NULL,
  created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (artifact_id, version)
)
"""


@dataclass(frozen=True)
class ArtifactRecord:
    artifact_id: str
    investigation_id: str
    owner_user_id: str
    source_path: Path
    source_hash: str | None
    selected_style: str | None
    latest_version: int


@dataclass(frozen=True)
class ArtifactVersion:
    artifact_id: str
    version: int
    owner_user_id: str
    style_name: str
    html_path: Path
    content_hash: str


class ResearchArtifactStore:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path

    def _ensure_schema(self) -> None:
        with FlockWriteCoordinator(self._db_path).acquire_write_context(
            "research_artifact.schema"
        ) as ctx:
            ctx.execute(_DDL)

    def save_source(
        self,
        artifact_id: str,
        investigation_id: str,
        owner_user_id: str,
        path: Path,
        data: bytes,
    ) -> None:
        """Commit ownership intent, publish immutable bytes, then CAS ready."""
        import hashlib

        expected_hash = hashlib.sha256(data).hexdigest()
        # Durable claim: cross-owner retries can neither publish nor adopt.
        with FlockWriteCoordinator(self._db_path).acquire_write_context(
            "research_artifact.source_claim"
        ) as ctx:
            ctx.execute(_DDL)
            existing = ctx.execute(
                "SELECT owner_user_id FROM research_artifacts WHERE artifact_id=?",
                [artifact_id],
            ).fetchone()
            if existing is not None and str(existing[0]) != owner_user_id:
                raise PermissionError("artifact is owned by another user")
            ctx.execute(
                "INSERT INTO research_artifacts "
                "(artifact_id, investigation_id, owner_user_id, source_path, source_hash, state) "
                "VALUES (?, ?, ?, ?, ?, 'pending') ON CONFLICT (artifact_id) DO UPDATE SET "
                "investigation_id=excluded.investigation_id, source_path=excluded.source_path, "
                "source_hash=excluded.source_hash, state='pending', updated_at=now()",
                [artifact_id, investigation_id, owner_user_id, str(path), expected_hash],
            )
        atomic_write_nofollow(path, data)
        # CAS prevents an older same-owner concurrent export from finalizing
        # after a newer claim superseded it.
        with FlockWriteCoordinator(self._db_path).acquire_write_context(
            "research_artifact.source_finalize"
        ) as ctx:
            row = ctx.execute(
                "SELECT owner_user_id, source_hash, source_path, state "
                "FROM research_artifacts WHERE artifact_id=?",
                [artifact_id],
            ).fetchone()
            identity = () if row is None else tuple(map(str, row[:3]))
            state = "" if row is None else str(row[3])
            expected_identity = (owner_user_id, expected_hash, str(path))
            if identity == expected_identity and state == "ready":
                return
            if identity != expected_identity or state != "pending":
                unlink_anchored(path)
                raise RuntimeError("source publication claim was superseded")
            ctx.execute(
                "UPDATE research_artifacts SET state='ready', updated_at=now() WHERE artifact_id=?",
                [artifact_id],
            )

    def get(self, artifact_id: str) -> ArtifactRecord | None:
        self._ensure_schema()
        con = connect_read(self._db_path)
        try:
            try:
                row = con.execute(
                    "SELECT artifact_id, investigation_id, owner_user_id, source_path, "
                    "source_hash, selected_style, latest_version FROM research_artifacts "
                    "WHERE artifact_id=? AND state='ready'",
                    [artifact_id],
                ).fetchone()
            except Exception as exc:  # legacy DB: table absent
                if "does not exist" in str(exc):
                    return None
                raise
            if row is None:
                return None
            return ArtifactRecord(
                str(row[0]),
                str(row[1]),
                str(row[2]),
                Path(str(row[3])),
                None if row[4] is None else str(row[4]),
                None if row[5] is None else str(row[5]),
                int(row[6]),
            )
        finally:
            con.close()

    def add_version(
        self,
        artifact_id: str,
        owner_user_id: str,
        style_name: str,
        html: str,
        content_hash: str,
    ) -> tuple[int, Path]:
        with FlockWriteCoordinator(self._db_path).acquire_write_context(
            "research_artifact.version"
        ) as ctx:
            ctx.execute(_DDL)
            row = ctx.execute(
                "SELECT owner_user_id, latest_version FROM research_artifacts "
                "WHERE artifact_id=? AND state='ready'",
                [artifact_id],
            ).fetchone()
            if row is None or str(row[0]) != owner_user_id:
                raise KeyError(artifact_id)
            version = int(row[1]) + 1
            if version > 1:
                latest = ctx.execute(
                    "SELECT style_name, html_path, content_hash FROM research_artifact_versions "
                    "WHERE artifact_id=? AND version=?",
                    [artifact_id, version - 1],
                ).fetchone()
                if (
                    latest is not None
                    and str(latest[0]) == style_name
                    and str(latest[2]) == content_hash
                ):
                    return version - 1, Path(str(latest[1]))
            html_path = artifact_version_path_for(artifact_id, version)
            # Orphan-only recovery: a crash after prior publication but before
            # metadata commit leaves exactly this unreferenced next-version.
            unlink_anchored(html_path)
            atomic_write_nofollow(html_path, html.encode("utf-8"))
            try:
                ctx.execute(
                    "INSERT INTO research_artifact_versions VALUES "
                    "(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
                    [artifact_id, version, owner_user_id, style_name, str(html_path), content_hash],
                )
                ctx.execute(
                    "UPDATE research_artifacts SET selected_style=?, latest_version=?, "
                    "updated_at=now() WHERE artifact_id=?",
                    [style_name, version, artifact_id],
                )
            except BaseException:
                unlink_anchored(html_path)
                raise
            return version, html_path

    def get_version(
        self, artifact_id: str, owner_user_id: str, version: int | None = None
    ) -> ArtifactVersion | None:
        self._ensure_schema()
        con = connect_read(self._db_path)
        try:
            selector = (
                "SELECT latest_version FROM research_artifacts WHERE artifact_id=? "
                "AND owner_user_id=?"
            )
            if version is None:
                row = con.execute(selector, [artifact_id, owner_user_id]).fetchone()
                if row is None or int(row[0]) < 1:
                    return None
                version = int(row[0])
            row = con.execute(
                "SELECT artifact_id, version, owner_user_id, style_name, html_path, content_hash "
                "FROM research_artifact_versions WHERE artifact_id=? AND version=? "
                "AND owner_user_id=?",
                [artifact_id, version, owner_user_id],
            ).fetchone()
            if row is None:
                return None
            return ArtifactVersion(
                str(row[0]), int(row[1]), str(row[2]), str(row[3]), Path(str(row[4])), str(row[5])
            )
        finally:
            con.close()

    def bind_source_hash(
        self, artifact_id: str, owner_user_id: str, path: Path, content_hash: str
    ) -> None:
        """One-time integrity binding for migrated pre-hash ready rows."""
        with FlockWriteCoordinator(self._db_path).acquire_write_context(
            "research_artifact.bind_hash"
        ) as ctx:
            ctx.execute(_DDL)
            row = ctx.execute(
                "SELECT source_hash FROM research_artifacts WHERE artifact_id=? "
                "AND owner_user_id=? AND source_path=? AND state='ready'",
                [artifact_id, owner_user_id, str(path)],
            ).fetchone()
            if row is None:
                raise KeyError(artifact_id)
            if row[0] is not None and str(row[0]) != content_hash:
                raise ValueError("artifact source hash changed during migration")
            ctx.execute(
                "UPDATE research_artifacts SET source_hash=?, updated_at=now() "
                "WHERE artifact_id=? AND source_hash IS NULL",
                [content_hash, artifact_id],
            )


__all__ = ["ArtifactRecord", "ArtifactVersion", "ResearchArtifactStore"]
