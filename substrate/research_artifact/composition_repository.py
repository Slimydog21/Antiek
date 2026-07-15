"""Owner-scoped authority and authoritative launch for immutable compositions."""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final

from runtime.db_lock import connect_read, connect_write
from substrate.research_artifact.compose import (
    ComposeResult,
    VerifiedComposition,
    load_verified_composition,
)
from substrate.research_artifact.render import render_html
from substrate.schemas import ResearchCompositionMemberRef, ResearchCompositionProvenance

MAX_COMPOSITIONS: Final = 200
MAX_CONTEXT_BYTES: Final = 192 * 1024
LEASE_SECONDS: Final = 30


class ResearchCompositionUnavailable(LookupError):
    pass


class ResearchCompositionConflict(RuntimeError):
    pass


class ResearchCompositionPrecondition(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedCompositionLaunch:
    investigation_id: str
    delivery_event: dict[str, Any] | None = None
    lease_token: str | None = None
    replay_response: dict[str, Any] | None = None


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def composition_etag(composition_id: str, digest: str) -> str:
    return f'"rc-v1-{composition_id}-{digest}"'


class ResearchCompositionRepository:
    def __init__(self, *, db_path: str) -> None:
        self.db_path = db_path

    def bind_created(self, *, owner_user_id: str, result: ComposeResult) -> dict[str, Any]:
        """Verify published bytes, then transactionally grant owner authority."""
        verified = load_verified_composition(result.composition_id)
        self._context(verified)
        if verified.ordered_set_digest != result.ordered_set_digest:
            raise ResearchCompositionConflict("composition result digest conflict")
        result_members = [(member.investigation_id, member.content_hash,
                           member.rendered_sha256) for member in result.members]
        verified_members = [(member.investigation_id, member.content_hash,
                             member.rendered_sha256) for member in verified.members]
        expected_conflicts: list[tuple[str, str]] = []
        first_by_hash: dict[str, str] = {}
        for member in verified.members:
            prior = first_by_hash.get(member.content_hash)
            if prior is None:
                first_by_hash[member.content_hash] = member.investigation_id
            else:
                expected_conflicts.append((prior, member.investigation_id))
        if result_members != verified_members or result.hash_conflicts != expected_conflicts:
            raise ResearchCompositionConflict("composition result member conflict")
        etag = composition_etag(verified.composition_id, verified.ordered_set_digest)
        with connect_write(self.db_path, purpose="research-composition-bind") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                prior = con.execute(
                    "SELECT ordered_set_digest,composition_schema_version,member_count,"
                    "composition_etag FROM research_compositions WHERE owner_user_id=? "
                    "AND composition_id=?",
                    [owner_user_id, verified.composition_id],
                ).fetchone()
                if prior is None:
                    count = con.execute(
                        "SELECT count(*) FROM research_compositions WHERE owner_user_id=?",
                        [owner_user_id],
                    ).fetchone()
                    if count is None or int(count[0]) >= MAX_COMPOSITIONS:
                        raise ResearchCompositionConflict("composition capacity reached")
                    con.execute(
                        "INSERT INTO research_compositions VALUES (?,?,?,?,?,?,CURRENT_TIMESTAMP)",
                        [owner_user_id, verified.composition_id, verified.ordered_set_digest,
                         verified.schema_version, len(verified.members), etag],
                    )
                    for ordinal, member in enumerate(verified.members):
                        con.execute(
                            "INSERT INTO research_composition_members VALUES (?,?,?,?,?,?)",
                            [owner_user_id, verified.composition_id, ordinal,
                             member.investigation_id, member.content_hash,
                             member.rendered_sha256],
                        )
                elif prior != (verified.ordered_set_digest, verified.schema_version,
                               len(verified.members), etag):
                    raise ResearchCompositionConflict("composition authority conflict")
                self._verify_bindings(con, owner_user_id, verified)
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return {"etag": etag, "composition": verified}

    def read(self, *, owner_user_id: str, composition_id: str) -> dict[str, Any]:
        try:
            verified = load_verified_composition(composition_id)
        except (FileNotFoundError, NotADirectoryError, OSError, KeyError, ValueError,
                IndexError, json.JSONDecodeError) as exc:
            raise ResearchCompositionUnavailable from exc
        with connect_read(self.db_path) as con:
            row = con.execute(
                "SELECT ordered_set_digest,composition_schema_version,member_count,"
                "composition_etag FROM research_compositions WHERE owner_user_id=? "
                "AND composition_id=?",
                [owner_user_id, composition_id],
            ).fetchone()
            if row is None:
                raise ResearchCompositionUnavailable
            expected = (verified.ordered_set_digest, verified.schema_version,
                        len(verified.members),
                        composition_etag(composition_id, verified.ordered_set_digest))
            if row != expected:
                raise ResearchCompositionConflict("composition authority integrity conflict")
            self._verify_bindings(con, owner_user_id, verified)
        context = self._context(verified)
        return {"etag": row[3], "composition": verified, "context": context}

    def prepare_launch(
        self, *, owner_user_id: str, composition_id: str, if_match: str,
        idempotency_key: str, options: dict[str, Any],
    ) -> PreparedCompositionLaunch:
        self._validate_key(idempotency_key)
        authorized = self.read(owner_user_id=owner_user_id, composition_id=composition_id)
        if not 2 <= len(authorized["composition"].members) <= 8:
            raise ResearchCompositionConflict("collective launch requires 2-8 members")
        if authorized["etag"] != if_match:
            raise ResearchCompositionPrecondition("stale composition ETag")
        request_sha = _sha(_canonical({"kind": "launch", "composition_id": composition_id,
                                       "if_match": if_match, "options": options}))
        investigation_id = "inv-" + _sha(
            f"{owner_user_id}\0{idempotency_key}\0{request_sha}"
        )[:12]
        with connect_write(self.db_path, purpose="research-composition-launch-prepare") as con:
            con.execute("BEGIN TRANSACTION")
            try:
                prior = self._operation(con, owner_user_id, idempotency_key)
                if prior is not None:
                    replay = self._replay(prior, request_sha)
                    if replay is not None:
                        con.execute("COMMIT")
                        return PreparedCompositionLaunch(str(prior[3]), replay_response=replay)
                    token = uuid.uuid4().hex
                    claimed = con.execute(
                        "UPDATE research_composition_operations SET delivery_lease_token=?,"
                        "delivery_lease_expires_at=? WHERE owner_user_id=? AND idempotency_key=? "
                        "AND state='delivering' AND delivery_lease_expires_at<=CURRENT_TIMESTAMP "
                        "RETURNING investigation_id,delivery_event_json",
                        [token, datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS),
                         owner_user_id, idempotency_key],
                    ).fetchone()
                    if claimed is None:
                        raise ResearchCompositionConflict("launch delivery is already in progress")
                    con.execute("COMMIT")
                    return PreparedCompositionLaunch(str(claimed[0]), json.loads(str(claimed[1])),
                                                     token)

                from substrate.constants import ANTIEK_PARAM_VERSION
                from substrate.schemas import (
                    DEFAULT_POLICY_ID,
                    EVENT_SCHEMA_VERSION,
                    Event,
                    InvestigationStartRequestedPayload,
                )

                verified: VerifiedComposition = authorized["composition"]
                provenance = ResearchCompositionProvenance(
                    composition_id=verified.composition_id,
                    ordered_set_digest=verified.ordered_set_digest,
                    composition_schema_version=verified.schema_version,
                    members=tuple(
                        ResearchCompositionMemberRef(
                            investigation_id=member.investigation_id,
                            content_hash=member.content_hash,
                            rendered_sha256=member.rendered_sha256,
                            ordinal=ordinal,
                        ) for ordinal, member in enumerate(verified.members)
                    ),
                    member_count=len(verified.members),
                )
                context = str(authorized["context"])
                payload = InvestigationStartRequestedPayload(
                    **options, owner_user_id=owner_user_id, context=context,
                    research_composition=provenance,
                )
                event_id = "evt-rc-" + _sha(
                    f"{owner_user_id}\0{idempotency_key}\0{request_sha}"
                )[:24]
                event = Event(
                    event_id=event_id, investigation_id=investigation_id, role="operator",
                    action_type=payload.action_type, payload=payload,
                    policy_id=DEFAULT_POLICY_ID, param_version=ANTIEK_PARAM_VERSION,
                    schema_version=EVENT_SCHEMA_VERSION, emitted_at=datetime.now(UTC),
                )
                event_json = _canonical(event.model_dump(mode="json"))
                token = uuid.uuid4().hex
                con.execute(
                    "INSERT INTO research_composition_operations "
                    "(owner_user_id,idempotency_key,operation_kind,request_sha256,state,"
                    "composition_id,investigation_id,delivery_event_json,delivery_event_sha256,"
                    "delivery_lease_token,delivery_lease_expires_at) "
                    "VALUES (?,?,'launch',?,'delivering',?,?,?,?,?,?)",
                    [owner_user_id, idempotency_key, request_sha, composition_id,
                     investigation_id, event_json, _sha(event_json), token,
                     datetime.now(UTC) + timedelta(seconds=LEASE_SECONDS)],
                )
                con.execute("COMMIT")
                return PreparedCompositionLaunch(investigation_id,
                                                 event.model_dump(mode="json"), token)
            except Exception:
                con.execute("ROLLBACK")
                raise

    def complete_launch(self, *, owner_user_id: str, idempotency_key: str,
                        lease_token: str, response: dict[str, Any]) -> None:
        response_json = _canonical(response)
        digest = _sha(response_json)
        with connect_write(self.db_path, purpose="research-composition-launch-complete") as con:
            con.execute(
                "UPDATE research_composition_operations SET state='completed',response_json=?,"
                "response_sha256=?,delivery_lease_expires_at=NULL,completed_at=CURRENT_TIMESTAMP "
                "WHERE owner_user_id=? AND idempotency_key=? AND state='delivering' "
                "AND delivery_lease_token=?",
                [response_json, digest, owner_user_id, idempotency_key, lease_token],
            )
            row = con.execute(
                "SELECT state,response_sha256 FROM research_composition_operations "
                "WHERE owner_user_id=? AND idempotency_key=?",
                [owner_user_id, idempotency_key],
            ).fetchone()
            if row != ("completed", digest):
                raise ResearchCompositionConflict("launch delivery lease was lost")

    def verify_delivery(self, *, owner_user_id: str, idempotency_key: str,
                        lease_token: str) -> dict[str, Any]:
        """Revalidate authority, all immutable bytes, and the leased event."""
        with connect_read(self.db_path) as con:
            row = con.execute(
                "SELECT composition_id,delivery_event_json,delivery_event_sha256 FROM "
                "research_composition_operations WHERE owner_user_id=? AND idempotency_key=? "
                "AND state='delivering' AND delivery_lease_token=?",
                [owner_user_id, idempotency_key, lease_token],
            ).fetchone()
        if row is None or not isinstance(row[1], str) or _sha(row[1]) != row[2]:
            raise ResearchCompositionConflict("launch delivery integrity conflict")
        authorized = self.read(owner_user_id=owner_user_id, composition_id=str(row[0]))
        event = json.loads(row[1])
        if not isinstance(event, dict) or not isinstance(event.get("payload"), dict):
            raise ResearchCompositionConflict("launch event integrity conflict")
        payload = event["payload"]
        verified: VerifiedComposition = authorized["composition"]
        provenance = payload.get("research_composition")
        expected_members = [
            {"investigation_id": member.investigation_id,
             "content_hash": member.content_hash,
             "rendered_sha256": member.rendered_sha256, "ordinal": ordinal}
            for ordinal, member in enumerate(verified.members)
        ]
        if (not isinstance(provenance, dict)
                or provenance.get("composition_id") != verified.composition_id
                or provenance.get("ordered_set_digest") != verified.ordered_set_digest
                or provenance.get("composition_schema_version") != verified.schema_version
                or provenance.get("member_count") != len(verified.members)
                or provenance.get("members") != expected_members
                or payload.get("context") != authorized["context"]
                or payload.get("spawn_context") is not None):
            raise ResearchCompositionConflict("launch event provenance conflict")
        return event

    @staticmethod
    def _context(verified: VerifiedComposition) -> str:
        blocks: list[str] = []
        for ordinal, member in enumerate(verified.members):
            raw = render_html(member.body).encode("utf-8")
            if hashlib.sha256(raw).hexdigest() != member.rendered_sha256:
                raise ResearchCompositionConflict("composition member render conflict")
            blocks.extend((f"<<<RESEARCH_COMPOSITION_MEMBER {ordinal} "
                           f"{member.investigation_id}>>>", raw.decode("utf-8"),
                           "<<<END_RESEARCH_COMPOSITION_MEMBER>>>"))
        context = "\n".join(blocks)
        if len(context.encode("utf-8")) > MAX_CONTEXT_BYTES:
            raise ResearchCompositionConflict("composition context exceeds limit")
        return context

    @staticmethod
    def _verify_bindings(con: Any, owner: str, verified: VerifiedComposition) -> None:
        rows = con.execute(
            "SELECT member_ordinal,investigation_id,content_hash,rendered_sha256 FROM "
            "research_composition_members WHERE owner_user_id=? AND composition_id=? "
            "ORDER BY member_ordinal", [owner, verified.composition_id],
        ).fetchall()
        expected = [(ordinal, member.investigation_id, member.content_hash,
                     member.rendered_sha256) for ordinal, member in enumerate(verified.members)]
        if rows != expected:
            raise ResearchCompositionConflict("composition member binding conflict")

    @staticmethod
    def _validate_key(key: str) -> None:
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", key):
            raise ValueError("invalid idempotency key")

    @staticmethod
    def _operation(con: Any, owner: str, key: str) -> tuple[Any, ...] | None:
        return con.execute(
            "SELECT request_sha256,state,response_json,investigation_id,delivery_event_json,"
            "delivery_event_sha256,response_sha256 FROM research_composition_operations "
            "WHERE owner_user_id=? AND idempotency_key=?", [owner, key],
        ).fetchone()

    @staticmethod
    def _replay(row: tuple[Any, ...], request_sha: str) -> dict[str, Any] | None:
        if row[0] != request_sha:
            raise ResearchCompositionConflict("idempotency key reuse conflict")
        if row[1] == "delivering":
            if not isinstance(row[4], str) or _sha(row[4]) != row[5]:
                raise ResearchCompositionConflict("delivery event integrity conflict")
            return None
        if (row[1] != "completed" or not isinstance(row[2], str)
                or _sha(row[2]) != row[6]):
            raise ResearchCompositionConflict("operation receipt integrity conflict")
        value = json.loads(row[2])
        if not isinstance(value, dict):
            raise ResearchCompositionConflict("operation response integrity conflict")
        return value
