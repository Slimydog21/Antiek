"""Durable ordered composition of verified evidence collections."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from runtime.db_lock import connect_read, connect_write
from substrate.research_artifact.evidence_collection_repository import (
    EvidenceCollectionRepository,
    EvidenceCollectionUnavailable,
)
from substrate.schemas import EvidenceManifestCollectionRef, EvidenceManifestProvenance

MAX_MANIFESTS: Final = 200
MAX_CONTEXT_BYTES: Final = 96 * 1024


class EvidenceManifestUnavailable(LookupError):
    pass


class EvidenceManifestConflict(RuntimeError):
    pass


class EvidenceManifestPrecondition(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedManifestLaunch:
    investigation_id: str
    manifest: dict[str, Any]
    delivery_event: dict[str, Any] | None = None
    lease_token: str | None = None
    replay_response: dict[str, Any] | None = None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _etag(manifest_id: str, version: int, digest: str) -> str:
    return f'"dem-v1-{manifest_id}-{version}-{digest}"'


class EvidenceManifestRepository:
    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path
        self._collections = EvidenceCollectionRepository(db_path=db_path)

    def create(
        self,
        *,
        owner_user_id: str,
        idempotency_key: str,
        label: str,
        collection_ids: tuple[str, ...],
    ) -> dict[str, Any]:
        self._validate_key(idempotency_key)
        if not isinstance(label, str) or not 1 <= len(label.encode()) <= 2048:
            raise ValueError("invalid manifest label")
        if not 2 <= len(collection_ids) <= 8 or len(set(collection_ids)) != len(collection_ids):
            raise ValueError("invalid manifest collections")
        if any(not re.fullmatch(r"dec_[0-9a-f]{32}", item) for item in collection_ids):
            raise ValueError("invalid collection id")
        request_sha = _sha(
            _canonical({"kind": "create", "label": label, "collection_ids": collection_ids})
        )
        manifest_id = "dem_" + _sha(f"{owner_user_id}\0{idempotency_key}\0{request_sha}")[:32]
        with connect_write(self.db_path, purpose="evidence-manifest-create") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                prior = self._operation(con, owner_user_id, idempotency_key)
                if prior is not None:
                    result = self._replay(prior, "create", request_sha)
                    con.execute("COMMIT")
                    return result
                count = con.execute(
                    "SELECT count(*) FROM derived_evidence_manifests WHERE owner_user_id=?",
                    [owner_user_id],
                ).fetchone()
                if count is None or int(count[0]) >= MAX_MANIFESTS:
                    raise EvidenceManifestConflict("manifest capacity reached")
                collections = [
                    self._read_collection(con, owner_user_id, item) for item in collection_ids
                ]
                total = sum(int(item["member_count"]) for item in collections)
                if not 4 <= total <= 32:
                    raise ValueError("manifest passage count is outside limits")
                refs = self._refs(collections)
                digest = _sha(_canonical(self._digest_envelope(refs)))
                con.execute(
                    "INSERT INTO derived_evidence_manifests "
                    "(manifest_id,owner_user_id,label,version,collection_count,"
                    "total_passage_count,manifest_sha256) VALUES (?,?,?,1,?,?,?)",
                    [manifest_id, owner_user_id, label, len(refs), total, digest],
                )
                for ref, collection in zip(refs, collections, strict=True):
                    con.execute(
                        "INSERT INTO derived_evidence_manifest_collections VALUES (?,?,?,?,?,?)",
                        [
                            manifest_id,
                            ref.ordinal,
                            ref.collection_id,
                            ref.version,
                            ref.collection_sha256,
                            collection["etag"],
                        ],
                    )
                result = self._read_on_connection(con, owner_user_id, manifest_id)
                response_json = _canonical(result)
                con.execute(
                    "INSERT INTO derived_evidence_manifest_operations "
                    "(owner_user_id,idempotency_key,operation_kind,request_sha256,state,"
                    "manifest_id,response_json,response_sha256,completed_at) "
                    "VALUES (?,?,'create',?,'completed',?,?,?,CURRENT_TIMESTAMP)",
                    [
                        owner_user_id,
                        idempotency_key,
                        request_sha,
                        manifest_id,
                        response_json,
                        _sha(response_json),
                    ],
                )
                con.execute("COMMIT")
                return result
            except Exception:
                con.execute("ROLLBACK")
                raise

    def list(self, *, owner_user_id: str) -> dict[str, Any]:
        with connect_read(self.db_path) as con:
            rows = con.execute(
                "SELECT manifest_id,label,version,collection_count,total_passage_count,"
                "manifest_sha256,created_at,updated_at FROM derived_evidence_manifests "
                "WHERE owner_user_id=? ORDER BY created_at DESC,manifest_id LIMIT ?",
                [owner_user_id, MAX_MANIFESTS + 1],
            ).fetchall()
        if len(rows) > MAX_MANIFESTS:
            raise EvidenceManifestConflict("manifest list exceeds limit")
        return {
            "manifests": [self._summary(row) for row in rows],
            "limits": {"manifests": MAX_MANIFESTS},
        }

    def read(self, *, owner_user_id: str, manifest_id: str) -> dict[str, Any]:
        with connect_read(self.db_path) as con:
            return self._read_on_connection(con, owner_user_id, manifest_id)

    def prepare_launch(
        self,
        *,
        owner_user_id: str,
        manifest_id: str,
        if_match: str,
        idempotency_key: str,
        options: dict[str, Any],
    ) -> PreparedManifestLaunch:
        self._validate_key(idempotency_key)
        request_sha = _sha(
            _canonical(
                {
                    "kind": "launch",
                    "manifest_id": manifest_id,
                    "if_match": if_match,
                    "options": options,
                }
            )
        )
        investigation_id = "inv-" + _sha(f"{owner_user_id}\0{idempotency_key}\0{request_sha}")[:12]
        with connect_write(self.db_path, purpose="evidence-manifest-launch-prepare") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                manifest = self._read_on_connection(con, owner_user_id, manifest_id)
                if manifest["etag"] != if_match:
                    raise EvidenceManifestPrecondition("stale manifest ETag")
                prior = self._operation(con, owner_user_id, idempotency_key)
                if prior is not None:
                    replay = self._replay(prior, "launch", request_sha, allow_prepared=True)
                    if replay is not None:
                        con.execute("COMMIT")
                        return PreparedManifestLaunch(
                            str(prior[4]), manifest, replay_response=replay
                        )
                    token = uuid.uuid4().hex
                    claimed = con.execute(
                        "UPDATE derived_evidence_manifest_operations SET "
                        "delivery_lease_token=?,delivery_lease_expires_at=? WHERE "
                        "owner_user_id=? AND idempotency_key=? AND state='delivering' AND "
                        "delivery_lease_expires_at<=CURRENT_TIMESTAMP RETURNING "
                        "investigation_id,delivery_event_json",
                        [
                            token,
                            datetime.now(UTC) + timedelta(seconds=30),
                            owner_user_id,
                            idempotency_key,
                        ],
                    ).fetchone()
                    if claimed is None:
                        raise EvidenceManifestConflict("launch delivery is already in progress")
                    con.execute("COMMIT")
                    return PreparedManifestLaunch(
                        str(claimed[0]), manifest, json.loads(str(claimed[1])), token
                    )
                from substrate.constants import ANTIEK_PARAM_VERSION
                from substrate.schemas import (
                    DEFAULT_POLICY_ID,
                    EVENT_SCHEMA_VERSION,
                    Event,
                    InvestigationStartRequestedPayload,
                )

                context = self._context(manifest["collections"])
                provenance = EvidenceManifestProvenance.model_validate(
                    {
                        "manifest_id": manifest["manifest_id"],
                        "version": manifest["version"],
                        "manifest_sha256": manifest["manifest_sha256"],
                        "collections": manifest["collection_refs"],
                        "collection_count": manifest["collection_count"],
                        "total_passage_count": manifest["total_passage_count"],
                    }
                )
                payload = InvestigationStartRequestedPayload(
                    **options,
                    context=context,
                    spawn_context=context,
                    evidence_manifest=provenance,
                )
                event_id = (
                    "evt-dem-" + _sha(f"{owner_user_id}\0{idempotency_key}\0{request_sha}")[:24]
                )
                event = Event(
                    event_id=event_id,
                    investigation_id=investigation_id,
                    role="operator",
                    action_type=payload.action_type,
                    payload=payload,
                    policy_id=DEFAULT_POLICY_ID,
                    param_version=ANTIEK_PARAM_VERSION,
                    schema_version=EVENT_SCHEMA_VERSION,
                    emitted_at=datetime.now(UTC),
                )
                event_json = _canonical(event.model_dump(mode="json"))
                token = uuid.uuid4().hex
                con.execute(
                    "INSERT INTO derived_evidence_manifest_operations "
                    "(owner_user_id,idempotency_key,operation_kind,request_sha256,state,"
                    "manifest_id,investigation_id,delivery_event_json,delivery_event_sha256,"
                    "delivery_lease_token,delivery_lease_expires_at) "
                    "VALUES (?,?,'launch',?,'delivering',?,?,?,?,?,?)",
                    [
                        owner_user_id,
                        idempotency_key,
                        request_sha,
                        manifest_id,
                        investigation_id,
                        event_json,
                        _sha(event_json),
                        token,
                        datetime.now(UTC) + timedelta(seconds=30),
                    ],
                )
                manifest = self._read_on_connection(con, owner_user_id, manifest_id)
                con.execute("COMMIT")
                return PreparedManifestLaunch(
                    investigation_id, manifest, event.model_dump(mode="json"), token
                )
            except Exception:
                con.execute("ROLLBACK")
                raise

    def complete_launch(
        self,
        *,
        owner_user_id: str,
        idempotency_key: str,
        lease_token: str,
        response: dict[str, Any],
    ) -> None:
        response_json = _canonical(response)
        with connect_write(self.db_path, purpose="evidence-manifest-launch-complete") as con:
            con.execute(
                "UPDATE derived_evidence_manifest_operations SET state='completed',"
                "response_json=?,response_sha256=?,delivery_lease_expires_at=NULL,"
                "completed_at=CURRENT_TIMESTAMP WHERE owner_user_id=? AND idempotency_key=? "
                "AND operation_kind='launch' AND state='delivering' AND delivery_lease_token=?",
                [response_json, _sha(response_json), owner_user_id, idempotency_key, lease_token],
            )
            row = con.execute(
                "SELECT state,response_sha256 FROM derived_evidence_manifest_operations "
                "WHERE owner_user_id=? AND idempotency_key=?",
                [owner_user_id, idempotency_key],
            ).fetchone()
            if row != ("completed", _sha(response_json)):
                raise EvidenceManifestConflict("launch delivery lease was lost")

    def _read_collection(self, con: Any, owner: str, collection_id: str) -> dict[str, Any]:
        try:
            return self._collections._read_on_connection(con, owner, collection_id)
        except EvidenceCollectionUnavailable as exc:
            raise EvidenceManifestUnavailable from exc

    def _read_on_connection(self, con: Any, owner: str, manifest_id: str) -> dict[str, Any]:
        row = con.execute(
            "SELECT manifest_id,label,version,collection_count,total_passage_count,"
            "manifest_sha256,created_at,updated_at FROM derived_evidence_manifests "
            "WHERE owner_user_id=? AND manifest_id=?",
            [owner, manifest_id],
        ).fetchone()
        if row is None:
            raise EvidenceManifestUnavailable
        bindings = con.execute(
            "SELECT manifest_ordinal,collection_id,collection_version,collection_sha256,"
            "collection_etag FROM derived_evidence_manifest_collections WHERE manifest_id=? "
            "ORDER BY manifest_ordinal",
            [manifest_id],
        ).fetchall()
        if [item[0] for item in bindings] != list(range(len(bindings))):
            raise EvidenceManifestConflict("manifest collection order conflict")
        collections = [self._read_collection(con, owner, str(item[1])) for item in bindings]
        for binding, collection in zip(bindings, collections, strict=True):
            if (binding[2], binding[3], binding[4]) != (
                collection["version"],
                collection["collection_sha256"],
                collection["etag"],
            ):
                raise EvidenceManifestConflict("manifest collection binding conflict")
        refs = self._refs(collections)
        total = sum(int(item["member_count"]) for item in collections)
        digest = _sha(_canonical(self._digest_envelope(refs)))
        if (row[3], row[4], row[5]) != (len(refs), total, digest):
            raise EvidenceManifestConflict("manifest digest integrity conflict")
        self._context(collections)
        result = self._summary(row)
        result.update(
            {
                "collection_refs": [ref.model_dump(mode="json") for ref in refs],
                "collections": collections,
            }
        )
        return result

    @staticmethod
    def _refs(collections: list[dict[str, Any]]) -> tuple[EvidenceManifestCollectionRef, ...]:
        return tuple(
            EvidenceManifestCollectionRef(
                collection_id=item["collection_id"],
                version=item["version"],
                collection_sha256=item["collection_sha256"],
                ordinal=ordinal,
            )
            for ordinal, item in enumerate(collections)
        )

    @staticmethod
    def _digest_envelope(refs: tuple[EvidenceManifestCollectionRef, ...]) -> dict[str, Any]:
        return {
            "schema": "derived-evidence-manifest.v1",
            "collections": [item.model_dump(mode="json") for item in refs],
        }

    @staticmethod
    def _context(collections: list[dict[str, Any]]) -> str:
        blocks: list[str] = []
        for index, collection in enumerate(collections):
            blocks.append(f"<<<EVIDENCE_COLLECTION {index} {collection['collection_id']}>>>")
            for ordinal, source in enumerate(collection["sources"]):
                blocks.extend(
                    (
                        f"<<<EVIDENCE {ordinal} {source['citation_id']}>>>",
                        source["excerpt"],
                        "<<<END_EVIDENCE>>>",
                    )
                )
            blocks.append("<<<END_EVIDENCE_COLLECTION>>>")
        context = "\n".join(blocks)
        if len(context.encode()) > MAX_CONTEXT_BYTES:
            raise EvidenceManifestConflict("manifest context exceeds limit")
        return context

    @staticmethod
    def _summary(row: tuple[Any, ...]) -> dict[str, Any]:
        return {
            "manifest_id": row[0],
            "label": row[1],
            "version": row[2],
            "collection_count": row[3],
            "total_passage_count": row[4],
            "manifest_sha256": row[5],
            "created_at": str(row[6]),
            "updated_at": str(row[7]),
            "etag": _etag(str(row[0]), int(row[2]), str(row[5])),
        }

    @staticmethod
    def _operation(con: Any, owner: str, key: str) -> tuple[Any, ...] | None:
        return con.execute(
            "SELECT operation_kind,request_sha256,state,response_json,investigation_id,"
            "delivery_event_json,delivery_lease_token,delivery_lease_expires_at FROM "
            "derived_evidence_manifest_operations WHERE owner_user_id=? AND idempotency_key=?",
            [owner, key],
        ).fetchone()

    @staticmethod
    def _replay(
        row: tuple[Any, ...], kind: str, request_sha: str, *, allow_prepared: bool = False
    ) -> dict[str, Any] | None:
        if row[0] != kind or row[1] != request_sha:
            raise EvidenceManifestConflict("idempotency key reuse conflict")
        if row[2] == "delivering" and allow_prepared:
            return None
        if row[2] != "completed" or not isinstance(row[3], str):
            raise EvidenceManifestConflict("operation receipt integrity conflict")
        value = json.loads(row[3])
        if not isinstance(value, dict):
            raise EvidenceManifestConflict("operation response integrity conflict")
        return value

    @staticmethod
    def _validate_key(key: str) -> None:
        if (
            not isinstance(key, str)
            or not 1 <= len(key.encode()) <= 256
            or not re.fullmatch(r"[\x21-\x7e]+", key)
        ):
            raise ValueError("invalid idempotency key")


__all__ = [
    "EvidenceManifestConflict",
    "EvidenceManifestPrecondition",
    "EvidenceManifestRepository",
    "EvidenceManifestUnavailable",
    "PreparedManifestLaunch",
]
