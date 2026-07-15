"""Durable, owner-scoped collections of exact derived evidence."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from runtime.db_lock import connect_read, connect_write
from substrate.research_artifact.derived_citation_source import (
    verify_derived_citation_sources_on_connection,
)
from substrate.schemas import DerivedCitationSource

MAX_COLLECTIONS: Final = 200


class EvidenceCollectionUnavailable(LookupError):
    pass


class EvidenceCollectionConflict(RuntimeError):
    pass


class EvidenceCollectionPrecondition(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedCollectionLaunch:
    investigation_id: str
    collection: dict[str, Any]
    delivery_event: dict[str, Any] | None = None
    lease_token: str | None = None
    replay_response: dict[str, Any] | None = None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _etag(collection_id: str, version: int, digest: str) -> str:
    return f'"dec-v1-{collection_id}-{version}-{digest}"'


class EvidenceCollectionRepository:
    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path

    def create(
        self, *, owner_user_id: str, idempotency_key: str, label: str,
        sources: tuple[DerivedCitationSource, ...],
    ) -> dict[str, Any]:
        self._validate_key(idempotency_key)
        if not isinstance(label, str) or not 1 <= len(label.encode("utf-8")) <= 2048:
            raise ValueError("invalid collection label")
        request_json = _canonical({
            "kind": "create", "label": label,
            "sources": [source.model_dump(mode="json") for source in sources],
        })
        request_sha = _sha(request_json)
        collection_id = "dec_" + _sha(f"{owner_user_id}\0{idempotency_key}\0{request_sha}")[:32]
        with connect_write(self.db_path, purpose="evidence-collection-create") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                prior = self._operation(con, owner_user_id, idempotency_key)
                if prior is not None:
                    result = self._replay(prior, "create", request_sha)
                    con.execute("COMMIT")
                    return result
                verified = verify_derived_citation_sources_on_connection(
                    con=con, owner_user_id=owner_user_id, sources=sources
                )
                envelope = self._digest_envelope(verified)
                digest = _sha(_canonical(envelope))
                first = verified[0]
                con.execute(
                    "INSERT INTO derived_evidence_collections "
                    "(collection_id,owner_user_id,label,derived_asset_id,revision_id,"
                    "revision_content_sha256,revision_generation,version,member_count,"
                    "collection_sha256) VALUES (?,?,?,?,?,?,?,1,?,?)",
                    [collection_id, owner_user_id, label, first.derived_asset_id,
                     first.revision_id, first.content_sha256, first.generation,
                     len(verified), digest],
                )
                for ordinal, source in enumerate(verified):
                    con.execute(
                        "INSERT INTO derived_evidence_collection_members VALUES "
                        "(?,?,?,?,?,?,?,?,?,?)",
                        [collection_id, ordinal, source.derived_asset_id, source.revision_id,
                         source.content_sha256, source.generation, source.citation_id,
                         source.chunk_ordinal, source.chunk_text_sha256, source.excerpt],
                    )
                result = self._read_on_connection(con, owner_user_id, collection_id)
                response_json = _canonical(result)
                con.execute(
                    "INSERT INTO derived_evidence_collection_operations "
                    "(owner_user_id,idempotency_key,operation_kind,request_sha256,state,"
                    "collection_id,response_json,response_sha256,completed_at) "
                    "VALUES (?,?, 'create',?,'completed',?,?,?,CURRENT_TIMESTAMP)",
                    [owner_user_id, idempotency_key, request_sha, collection_id,
                     response_json, _sha(response_json)],
                )
                con.execute("COMMIT")
                return result
            except Exception:
                con.execute("ROLLBACK")
                raise

    def list(
        self, *, owner_user_id: str, asset_id: str | None = None,
        revision_id: str | None = None,
    ) -> dict[str, Any]:
        with connect_read(self.db_path) as con:
            params: list[Any] = [owner_user_id]
            where = "owner_user_id=?"
            if asset_id is not None:
                where += " AND derived_asset_id=?"
                params.append(asset_id)
            if revision_id is not None:
                where += " AND revision_id=?"
                params.append(revision_id)
            rows = con.execute(
                "SELECT collection_id,label,derived_asset_id,revision_id,"
                "revision_content_sha256,revision_generation,version,member_count,"
                "collection_sha256,created_at,updated_at FROM derived_evidence_collections "
                f"WHERE {where} ORDER BY created_at DESC,collection_id LIMIT ?",
                [*params, MAX_COLLECTIONS + 1],
            ).fetchall()
        if len(rows) > MAX_COLLECTIONS:
            raise EvidenceCollectionConflict("collection list exceeds limit")
        return {"collections": [self._summary(row) for row in rows],
                "limits": {"collections": MAX_COLLECTIONS}}

    def read(self, *, owner_user_id: str, collection_id: str) -> dict[str, Any]:
        with connect_read(self.db_path) as con:
            return self._read_on_connection(con, owner_user_id, collection_id)

    def prepare_launch(
        self, *, owner_user_id: str, collection_id: str, if_match: str,
        idempotency_key: str, options: dict[str, Any],
    ) -> PreparedCollectionLaunch:
        self._validate_key(idempotency_key)
        request_sha = _sha(_canonical({"kind": "launch", "collection_id": collection_id,
                                      "if_match": if_match, "options": options}))
        investigation_id = "inv-" + _sha(
            f"{owner_user_id}\0{idempotency_key}\0{request_sha}"
        )[:12]
        with connect_write(self.db_path, purpose="evidence-collection-launch-prepare") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                collection = self._read_on_connection(con, owner_user_id, collection_id)
                if collection["etag"] != if_match:
                    raise EvidenceCollectionPrecondition("stale collection ETag")
                prior = self._operation(con, owner_user_id, idempotency_key)
                if prior is not None:
                    replay = self._replay(prior, "launch", request_sha, allow_prepared=True)
                    if replay is not None:
                        con.execute("COMMIT")
                        return PreparedCollectionLaunch(
                            investigation_id=str(prior[4]), collection=collection,
                            replay_response=replay,
                        )
                    lease_token = uuid.uuid4().hex
                    claimed = con.execute(
                        "UPDATE derived_evidence_collection_operations "
                        "SET delivery_lease_token=?,delivery_lease_expires_at=? "
                        "WHERE owner_user_id=? AND idempotency_key=? AND state='delivering' "
                        "AND delivery_lease_expires_at<=CURRENT_TIMESTAMP RETURNING "
                        "investigation_id,delivery_event_json",
                        [lease_token, datetime.now(UTC) + timedelta(seconds=30),
                         owner_user_id, idempotency_key],
                    ).fetchone()
                    if claimed is None:
                        raise EvidenceCollectionConflict("launch delivery is already in progress")
                    con.execute("COMMIT")
                    return PreparedCollectionLaunch(
                        investigation_id=str(claimed[0]), collection=collection,
                        delivery_event=json.loads(str(claimed[1])), lease_token=lease_token,
                    )
                from substrate.constants import ANTIEK_PARAM_VERSION
                from substrate.schemas import (
                    DEFAULT_POLICY_ID, EVENT_SCHEMA_VERSION, Event,
                    InvestigationStartRequestedPayload,
                )
                sources = tuple(DerivedCitationSource.model_validate(item)
                                for item in collection["sources"])
                from substrate.research_artifact.derived_citation_source import (
                    canonical_derived_sources_context,
                )
                context = canonical_derived_sources_context(sources)
                event_id = "evt-dec-" + _sha(
                    f"{owner_user_id}\0{idempotency_key}\0{request_sha}"
                )[:24]
                payload = InvestigationStartRequestedPayload(
                    **options, context=context, spawn_context=context,
                    derived_sources=sources,
                )
                event = Event(
                    event_id=event_id, investigation_id=investigation_id,
                    role="operator", action_type=payload.action_type, payload=payload,
                    policy_id=DEFAULT_POLICY_ID, param_version=ANTIEK_PARAM_VERSION,
                    schema_version=EVENT_SCHEMA_VERSION, emitted_at=datetime.now(UTC),
                )
                event_json = _canonical(event.model_dump(mode="json"))
                lease_token = uuid.uuid4().hex
                lease_expiry = datetime.now(UTC) + timedelta(seconds=30)
                con.execute(
                    "INSERT INTO derived_evidence_collection_operations "
                    "(owner_user_id,idempotency_key,operation_kind,request_sha256,state,"
                    "collection_id,investigation_id,delivery_event_json,delivery_event_sha256,"
                    "delivery_lease_token,delivery_lease_expires_at) "
                    "VALUES (?,?,'launch',?,'delivering',?,?,?,?,?,?)",
                    [owner_user_id, idempotency_key, request_sha, collection_id,
                     investigation_id, event_json, _sha(event_json), lease_token, lease_expiry],
                )
                # Revalidate after reservation, still on this transaction and connection.
                collection = self._read_on_connection(con, owner_user_id, collection_id)
                con.execute("COMMIT")
                return PreparedCollectionLaunch(
                    investigation_id, collection, event.model_dump(mode="json"), lease_token
                )
            except Exception:
                con.execute("ROLLBACK")
                raise

    def complete_launch(
        self, *, owner_user_id: str, idempotency_key: str, lease_token: str,
        response: dict[str, Any]
    ) -> None:
        response_json = _canonical(response)
        with connect_write(self.db_path, purpose="evidence-collection-launch-complete") as con:
            con.execute(
                "UPDATE derived_evidence_collection_operations SET state='completed',"
                "response_json=?,response_sha256=?,delivery_lease_expires_at=NULL,"
                "completed_at=CURRENT_TIMESTAMP "
                "WHERE owner_user_id=? AND idempotency_key=? AND operation_kind='launch' "
                "AND state='delivering' AND delivery_lease_token=?",
                [response_json, _sha(response_json), owner_user_id, idempotency_key,
                 lease_token],
            )
            row = con.execute(
                "SELECT state,response_sha256 FROM derived_evidence_collection_operations "
                "WHERE owner_user_id=? AND idempotency_key=?",
                [owner_user_id, idempotency_key],
            ).fetchone()
            if row != ("completed", _sha(response_json)):
                raise EvidenceCollectionConflict("launch delivery lease was lost")

    def _read_on_connection(
        self, con: Any, owner_user_id: str, collection_id: str
    ) -> dict[str, Any]:
        row = con.execute(
            "SELECT collection_id,label,derived_asset_id,revision_id,"
            "revision_content_sha256,revision_generation,version,member_count,"
            "collection_sha256,created_at,updated_at FROM derived_evidence_collections "
            "WHERE owner_user_id=? AND collection_id=?",
            [owner_user_id, collection_id],
        ).fetchone()
        if row is None:
            raise EvidenceCollectionUnavailable
        member_rows = con.execute(
            "SELECT member_ordinal,derived_asset_id,revision_id,revision_content_sha256,"
            "revision_generation,citation_id,chunk_ordinal,chunk_text_sha256,excerpt "
            "FROM derived_evidence_collection_members WHERE collection_id=? "
            "ORDER BY member_ordinal", [collection_id]
        ).fetchall()
        sources = tuple(DerivedCitationSource(
            derived_asset_id=item[1], revision_id=item[2], content_sha256=item[3],
            generation=item[4], citation_id=item[5], chunk_ordinal=item[6],
            chunk_text_sha256=item[7], excerpt=item[8],
        ) for item in member_rows)
        if not 2 <= len(sources) <= 6:
            raise EvidenceCollectionConflict("collection member cardinality conflict")
        if [item[0] for item in member_rows] != list(range(len(member_rows))):
            raise EvidenceCollectionConflict("collection member order integrity conflict")
        verify_derived_citation_sources_on_connection(
            con=con, owner_user_id=owner_user_id, sources=sources
        )
        location_rows = con.execute(
            "SELECT citation_id,chunk_ordinal,member_index,section_anchor,section_path FROM "
            "derived_asset_revision_chunks WHERE derived_asset_id=? AND revision_id=? "
            "AND revision_content_sha256=?",
            [row[2], row[3], row[4]],
        ).fetchall()
        locations_by_citation = {
            str(item[0]): {
                "citation_id": str(item[0]), "chunk_ordinal": int(item[1]),
                "member_index": int(item[2]), "section_anchor": str(item[3]),
                "section_path": str(item[4]),
            }
            for item in location_rows
        }
        try:
            locations = [locations_by_citation[source.citation_id] for source in sources]
        except KeyError as exc:
            raise EvidenceCollectionConflict(
                "collection location integrity conflict"
            ) from exc
        if any(location["chunk_ordinal"] != source.chunk_ordinal
               for source, location in zip(sources, locations, strict=True)):
            raise EvidenceCollectionConflict("collection location integrity conflict")
        if (row[7] != len(sources)
                or row[8] != _sha(_canonical(self._digest_envelope(sources)))):
            raise EvidenceCollectionConflict("collection digest integrity conflict")
        current = con.execute(
            "SELECT current_revision_id FROM derived_asset_current_revisions "
            "WHERE derived_asset_id=?", [row[2]]
        ).fetchone()
        result = self._summary(row)
        result.update({"sources": [source.model_dump(mode="json") for source in sources],
                       "locations": locations, "is_current": current == (row[3],)})
        return result

    @staticmethod
    def _digest_envelope(sources: tuple[DerivedCitationSource, ...]) -> dict[str, Any]:
        first = sources[0]
        return {"schema": "derived-evidence-collection.v1", "scope": {
            "derived_asset_id": first.derived_asset_id, "revision_id": first.revision_id,
            "content_sha256": first.content_sha256, "generation": first.generation,
        }, "members": [source.model_dump(mode="json") for source in sources]}

    @staticmethod
    def _summary(row: tuple[Any, ...]) -> dict[str, Any]:
        return {"collection_id": row[0], "label": row[1], "derived_asset_id": row[2],
                "revision_id": row[3], "content_sha256": row[4], "generation": row[5],
                "version": row[6], "member_count": row[7], "collection_sha256": row[8],
                "created_at": str(row[9]), "updated_at": str(row[10]),
                "etag": _etag(str(row[0]), int(row[6]), str(row[8]))}

    @staticmethod
    def _operation(con: Any, owner: str, key: str) -> tuple[Any, ...] | None:
        return con.execute(
            "SELECT operation_kind,request_sha256,state,response_json,investigation_id,"
            "delivery_event_json,delivery_lease_token,delivery_lease_expires_at "
            "FROM derived_evidence_collection_operations WHERE owner_user_id=? "
            "AND idempotency_key=?", [owner, key]
        ).fetchone()

    @staticmethod
    def _replay(
        row: tuple[Any, ...], kind: str, request_sha: str, *, allow_prepared: bool = False
    ) -> dict[str, Any] | None:
        if row[0] != kind or row[1] != request_sha:
            raise EvidenceCollectionConflict("idempotency key reuse conflict")
        if row[2] == "delivering" and allow_prepared:
            return None
        if row[2] != "completed" or not isinstance(row[3], str):
            raise EvidenceCollectionConflict("operation receipt integrity conflict")
        response = json.loads(row[3])
        if not isinstance(response, dict):
            raise EvidenceCollectionConflict("operation response integrity conflict")
        return response

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not 1 <= len(key.encode("utf-8")) <= 256 \
                or not re.fullmatch(r"[\x21-\x7e]+", key):
            raise ValueError("invalid idempotency key")


__all__ = ["EvidenceCollectionConflict", "EvidenceCollectionPrecondition",
           "EvidenceCollectionRepository", "EvidenceCollectionUnavailable",
           "PreparedCollectionLaunch"]
