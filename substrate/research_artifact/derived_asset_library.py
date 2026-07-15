"""Owner-scoped verified read model for committed derived assets."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Final

from runtime.db_lock import connect_read
from services.html_projection.canonical_merge import POLICY, VERSION
from substrate.research_artifact.merge_draft import ACKNOWLEDGEMENT_VERSION

MAX_DERIVED_ASSETS: Final = 200
MAX_REVISIONS_PER_ASSET: Final = 400
MAX_CANONICAL_HTML_BYTES: Final = 8 * 1024 * 1024
MAX_TITLE_BYTES: Final = 2 * 1024


class DerivedAssetUnavailable(LookupError):
    pass


class DerivedAssetIntegrity(RuntimeError):
    pass


@dataclass(frozen=True)
class VerifiedDerivedRevision:
    revision_id: str
    operation_kind: str
    canonical_html: str
    content_sha256: str
    parent_revision_id: str | None
    restored_from_revision_id: str | None
    member_count: int

    def public(self, *, asset_id: str, current_revision_id: str) -> dict[str, Any]:
        return {
            "revision_id": self.revision_id,
            "operation_kind": self.operation_kind,
            "content_sha256": self.content_sha256,
            "parent_revision_id": self.parent_revision_id,
            "restored_from_revision_id": self.restored_from_revision_id,
            "member_count": self.member_count,
            "is_current": self.revision_id == current_revision_id,
            "preview_url": (
                f"/research/derived-assets/assets/{asset_id}/revisions/"
                f"{self.revision_id}/frame-preview"
            ),
        }


class DerivedAssetLibrary:
    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path

    def discover(self, owner_user_id: str) -> dict[str, Any]:
        if not owner_user_id:
            raise DerivedAssetUnavailable
        with connect_read(self.db_path) as con:
            owned_count = int(con.execute(
                "SELECT count(*) FROM derived_assets WHERE owner_user_id=?", [owner_user_id]
            ).fetchone()[0])
            if owned_count > MAX_DERIVED_ASSETS:
                raise DerivedAssetIntegrity
            rows = con.execute(
                "SELECT a.derived_asset_id,a.title,a.asset_kind,c.current_revision_id,"
                "c.current_content_sha256,c.generation FROM derived_assets a "
                "JOIN derived_asset_current_revisions c USING (derived_asset_id) "
                "WHERE a.owner_user_id=? ORDER BY a.derived_asset_id LIMIT ?",
                [owner_user_id, MAX_DERIVED_ASSETS + 1],
            ).fetchall()
            if len(rows) != owned_count:
                raise DerivedAssetIntegrity
            assets = [self._verified_asset(con, owner_user_id, row, include_history=False)
                      for row in rows]
        return {"assets": assets, "limits": {"assets": MAX_DERIVED_ASSETS,
                                               "revisions_per_asset": MAX_REVISIONS_PER_ASSET}}

    def history(self, owner_user_id: str, asset_id: str) -> dict[str, Any]:
        with connect_read(self.db_path) as con:
            row = self._asset_row(con, owner_user_id, asset_id)
            return self._verified_asset(con, owner_user_id, row, include_history=True)

    def current_preview(self, owner_user_id: str, asset_id: str) -> bytes:
        with connect_read(self.db_path) as con:
            row = self._asset_row(con, owner_user_id, asset_id)
            verified = self._verify_chain(con, asset_id, str(row[3]), str(row[4]))
            return verified[0].canonical_html.encode("utf-8")

    def revision_preview(self, owner_user_id: str, asset_id: str, revision_id: str) -> bytes:
        with connect_read(self.db_path) as con:
            row = self._asset_row(con, owner_user_id, asset_id)
            verified = self._verify_chain(con, asset_id, str(row[3]), str(row[4]))
            revision = next((item for item in verified if item.revision_id == revision_id), None)
            if revision is None:
                raise DerivedAssetUnavailable
            return revision.canonical_html.encode("utf-8")

    def _asset_row(self, con: Any, owner_user_id: str, asset_id: str) -> tuple[Any, ...]:
        owned = con.execute(
            "SELECT EXISTS (SELECT 1 FROM derived_assets WHERE owner_user_id=? "
            "AND derived_asset_id=?)", [owner_user_id, asset_id]
        ).fetchone() == (True,)
        if not owned:
            raise DerivedAssetUnavailable
        row = con.execute(
            "SELECT a.derived_asset_id,a.title,a.asset_kind,c.current_revision_id,"
            "c.current_content_sha256,c.generation FROM derived_assets a "
            "JOIN derived_asset_current_revisions c USING (derived_asset_id) "
            "WHERE a.owner_user_id=? AND a.derived_asset_id=?",
            [owner_user_id, asset_id],
        ).fetchone()
        if row is None:
            raise DerivedAssetIntegrity
        return row

    def _verified_asset(
        self, con: Any, owner_user_id: str, row: tuple[Any, ...], *, include_history: bool
    ) -> dict[str, Any]:
        del owner_user_id
        asset_id, title, kind, current_id, current_hash, generation = row
        if (not re.fullmatch(r"ast_[0-9a-f]{32}", str(asset_id))
                or not isinstance(title, str) or not title
                or len(title.encode("utf-8")) > MAX_TITLE_BYTES or kind not in {
            "document", "analysis", "synthesis", "composite"
        } or not isinstance(generation, int) or generation < 1):
            raise DerivedAssetIntegrity
        revisions = self._verify_chain(con, str(asset_id), str(current_id), str(current_hash))
        if generation != len(revisions):
            raise DerivedAssetIntegrity
        current = revisions[0]
        result: dict[str, Any] = {
            "derived_asset_id": str(asset_id),
            "title": title,
            "asset_kind": str(kind),
            "current": {
                "revision_id": current.revision_id,
                "content_sha256": current.content_sha256,
                "generation": generation,
                "member_count": current.member_count,
                "preview_url": (
                    f"/research/derived-assets/assets/{asset_id}/current/frame-preview"
                ),
            },
            "revision_count": len(revisions),
        }
        if include_history:
            result["revisions"] = [item.public(
                asset_id=str(asset_id), current_revision_id=current.revision_id
            ) for item in revisions]
        return result

    def _verify_chain(
        self, con: Any, asset_id: str, current_revision_id: str, current_hash: str
    ) -> tuple[VerifiedDerivedRevision, ...]:
        total = int(con.execute(
            "SELECT count(*) FROM derived_asset_revisions WHERE derived_asset_id=?", [asset_id]
        ).fetchone()[0])
        if total < 1 or total > MAX_REVISIONS_PER_ASSET:
            raise DerivedAssetIntegrity
        revisions: list[VerifiedDerivedRevision] = []
        seen: set[str] = set()
        revision_id: str | None = current_revision_id
        while revision_id is not None:
            if revision_id in seen or len(revisions) >= MAX_REVISIONS_PER_ASSET:
                raise DerivedAssetIntegrity
            seen.add(revision_id)
            revision = self._verify_revision(con, asset_id, revision_id)
            revisions.append(revision)
            revision_id = revision.parent_revision_id
        if (len(revisions) != total or revisions[0].content_sha256 != current_hash
                or not re.fullmatch(r"[0-9a-f]{64}", current_hash)):
            raise DerivedAssetIntegrity
        positions = {revision.revision_id: index for index, revision in enumerate(revisions)}
        for index, revision in enumerate(revisions):
            if index == len(revisions) - 1:
                if revision.operation_kind != "create" or revision.parent_revision_id is not None:
                    raise DerivedAssetIntegrity
            elif revision.parent_revision_id != revisions[index + 1].revision_id:
                raise DerivedAssetIntegrity
            if revision.operation_kind == "restore":
                restored_position = positions.get(revision.restored_from_revision_id or "")
                if restored_position is None or restored_position <= index:
                    raise DerivedAssetIntegrity
            elif revision.restored_from_revision_id is not None:
                raise DerivedAssetIntegrity
        return tuple(revisions)

    def _verify_revision(self, con: Any, asset_id: str, revision_id: str) -> VerifiedDerivedRevision:
        row = con.execute(
            "SELECT revision_id,operation_kind,canonical_html,canonical_byte_count,content_sha256,"
            "manifest_json,manifest_sha256,sanitizer_policy,sanitizer_version,"
            "acknowledgement_version,parent_revision_id,restored_from_revision_id "
            "FROM derived_asset_revisions WHERE derived_asset_id=? AND revision_id=?",
            [asset_id, revision_id],
        ).fetchone()
        if (row is None or str(row[0]) != revision_id
                or not re.fullmatch(r"rev_[0-9a-f]{32}", revision_id)):
            raise DerivedAssetIntegrity
        html = str(row[2])
        encoded = html.encode("utf-8")
        if (len(encoded) > MAX_CANONICAL_HTML_BYTES or row[3] != len(encoded)
                or _sha(html) != str(row[4]) or (str(row[7]), str(row[8])) != (POLICY, VERSION)
                or str(row[9]) != ACKNOWLEDGEMENT_VERSION):
            raise DerivedAssetIntegrity
        manifest = _manifest(str(row[5]), str(row[6]))
        members = con.execute(
            "SELECT member_index,projection_id,source_asset_id,source_document_id,source_sha256,"
            "hosted_html_sha256 FROM derived_asset_revision_members "
            "WHERE derived_asset_id=? AND revision_id=? ORDER BY member_index",
            [asset_id, revision_id],
        ).fetchall()
        expected = [(
            item["member_index"], item["projection_id"], item["source_asset_id"],
            item["source_document_id"], item["source_sha256"], item["hosted_html_sha256"]
        ) for item in manifest]
        if members != expected:
            raise DerivedAssetIntegrity
        kind = str(row[1])
        parent = None if row[10] is None else str(row[10])
        restored = None if row[11] is None else str(row[11])
        if kind not in {"create", "revise", "restore"}:
            raise DerivedAssetIntegrity
        return VerifiedDerivedRevision(revision_id, kind, html, str(row[4]), parent, restored,
                                       len(members))


def _manifest(text: str, digest: str) -> list[dict[str, Any]]:
    try:
        value = json.loads(text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise DerivedAssetIntegrity from exc
    required = {
        "converter_id", "converter_version", "hosted_html_sha256", "member_index",
        "projection_id", "projection_sanitizer_policy", "projection_sanitizer_version",
        "source_asset_id", "source_document_id", "source_sha256",
    }
    if (_json(value) != text or _sha(text) != digest or not isinstance(value, list) or not value
            or any(not isinstance(item, dict) or set(item) != required
                   or item["member_index"] != index
                   or any(not isinstance(item[field], str) or not item[field]
                          for field in required - {"member_index"})
                   or not re.fullmatch(r"[0-9a-f]{64}", item["hosted_html_sha256"])
                   or not re.fullmatch(r"[0-9a-f]{64}", item["source_sha256"])
                   for index, item in enumerate(value))):
        raise DerivedAssetIntegrity
    return value


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()
