"""Atomic quote and V2 authority for one server-derived Krea scene request."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from integrations.krea.catalog import (
    CATALOG_DIGEST,
    CATALOG_VERSION,
    Imagen3Request,
    KreaQuote,
    PreparedKreaRequest,
    issue_quote,
    prepare_request,
    verify_quote,
)
from runtime.db_lock import FlockWriteCoordinator

from .execution_authorization import (
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
    verify_async_execution_authorization,
)
from .read_model import MultimediaAssetStore

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_visual_authorizations (
 owner_identity_digest TEXT NOT NULL, request_id TEXT NOT NULL,
 request_hash TEXT NOT NULL, chapter_id TEXT NOT NULL, scene_id TEXT NOT NULL,
 prepared_digest TEXT NOT NULL, quote_json TEXT NOT NULL,
 authorization_json TEXT NOT NULL, row_mac TEXT NOT NULL,
 PRIMARY KEY(owner_identity_digest, request_id))
"""
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class VisualAuthorizationError(RuntimeError):
    """Visual generation authority is stale, unavailable, or conflicting."""


@dataclass(frozen=True)
class VisualAuthorizationRequest:
    request_id: str
    expected_revision_id: str
    chapter_id: str
    approved_ceiling_microdollars: int
    operator_acknowledged_spend: bool
    ttl_seconds: int = 900


@dataclass(frozen=True)
class VisualAuthorizationTerms:
    recovery_authority_id: str
    recovery_verification_key_digest: str
    maximum_ceiling_microdollars: int
    quote_ttl_seconds: int


@dataclass(frozen=True)
class VisualAuthorizationResult:
    chapter_id: str
    scene_id: str
    width: int
    height: int
    seed: int
    request_body_digest: str
    provider_request: Imagen3Request
    quote: KreaQuote
    authorization: MultimediaExecutionAuthorizationV2


@dataclass(frozen=True)
class VisualAuthorizationBinding:
    chapter_id: str
    scene_id: str
    authorization: MultimediaExecutionAuthorizationV2


class VisualAuthorizationRegistry:
    def __init__(self, *, db_path: str, signing_key: bytes) -> None:
        if not db_path or not isinstance(signing_key, bytes) or len(signing_key) < 32:
            raise ValueError("visual authorization registry configuration is invalid")
        self._db_path = db_path
        self._key = signing_key

    def authorize(
        self,
        asset_id: str,
        request: VisualAuthorizationRequest,
        *, owner_id: str,
        store: MultimediaAssetStore,
        terms: VisualAuthorizationTerms,
        now: datetime,
    ) -> VisualAuthorizationResult:
        if not _ID.fullmatch(request.request_id) or not _ID.fullmatch(request.chapter_id):
            raise VisualAuthorizationError("visual authorization identifier is invalid")
        try:
            record = store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError) as exc:
            raise VisualAuthorizationError("multimedia asset is unavailable") from exc
        if record.asset.revision_id != request.expected_revision_id:
            raise VisualAuthorizationError("visual authorization revision is not current")
        if str(record.asset.status) != "ready":
            raise VisualAuthorizationError("visual authorization requires a ready asset")
        if record.mode == "audio" or str(record.asset.kind) == "audio_experience":
            raise VisualAuthorizationError("audio assets cannot authorize visual generation")
        if record.asset.route_policy == "cheapest":
            raise VisualAuthorizationError("cheapest route cannot authorize paid visuals")
        if not request.operator_acknowledged_spend:
            raise VisualAuthorizationError("operator spend acknowledgement is required")
        ceiling = request.approved_ceiling_microdollars
        if (
            isinstance(ceiling, bool) or not isinstance(ceiling, int) or ceiling <= 0
            or ceiling > terms.maximum_ceiling_microdollars
        ):
            raise VisualAuthorizationError("approved visual ceiling is invalid")
        if request.ttl_seconds < 60 or request.ttl_seconds > 3600:
            raise VisualAuthorizationError("visual authorization TTL is invalid")
        chapters = [row for row in record.plan.chapters if row.chapter_id == request.chapter_id]
        scenes = [row for row in record.plan.scenes if row.chapter_id == request.chapter_id]
        if len(chapters) != 1 or len(scenes) != 1:
            raise VisualAuthorizationError("visual chapter or scene is unavailable")
        chapter, scene = chapters[0], scenes[0]
        if tuple(scene.source_chunk_ids) != tuple(chapter.source_chunk_ids):
            raise VisualAuthorizationError("visual scene grounding conflicts")
        width, height = (
            (1920, 1080) if record.asset.route_policy == "highest_quality" else (1280, 720)
        )
        seed = int.from_bytes(
            hashlib.sha256(
                f"{owner_id}\0{asset_id}\0{request.expected_revision_id}\0{chapter.chapter_id}\0{scene.scene_id}".encode()
            ).digest()[:4],
            "big",
        ) & 0x7FFFFFFF
        prompt = (
            f"Generated educational documentary visual. Clearly generated, not archival. "
            f"Chapter: {chapter.title}. Visual intent: {scene.visual_intent}. "
            f"Information purpose: {scene.information_purpose}. Avoid decorative filler."
        )
        image_request = Imagen3Request(prompt=prompt, width=width, height=height, seed=seed)
        prepared = prepare_request(image_request)
        owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
        request_terms = {
            "approved_ceiling_microdollars": ceiling,
            "asset_id": asset_id,
            "chapter_id": chapter.chapter_id,
            "expected_revision_id": request.expected_revision_id,
            "height": height,
            "prepared_digest": prepared.body_digest,
            "quote_ttl_seconds": terms.quote_ttl_seconds,
            "recovery_authority_id": terms.recovery_authority_id,
            "recovery_verification_key_digest": terms.recovery_verification_key_digest,
            "request_id": request.request_id,
            "route_policy": record.asset.route_policy,
            "scene_id": scene.scene_id,
            "seed": seed,
            "ttl_seconds": request.ttl_seconds,
            "width": width,
        }
        request_hash = hashlib.sha256(_canonical(request_terms)).hexdigest()
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.visual_authorization.issue") as ctx:
            ctx.execute(_DDL)
            ctx.execute("BEGIN TRANSACTION")
            try:
                existing = ctx.execute(
                    "SELECT * FROM multimedia_visual_authorizations WHERE owner_identity_digest=? AND request_id=?",
                    [owner_digest, request.request_id],
                ).fetchone()
                if existing is not None:
                    result = self._replay(existing, request_hash, prepared, request_terms, now)
                    ctx.execute("COMMIT")
                    return result
                quote_ttl = min(terms.quote_ttl_seconds, request.ttl_seconds)
                quote = issue_quote(
                    signing_key=self._key, prepared=prepared,
                    ceiling_microdollars=ceiling, issued_at=now,
                    expires_at=now + timedelta(seconds=quote_ttl),
                )
                authorization = issue_async_execution_authorization(
                    signing_key=self._key, request_id=request.request_id, operator_id=owner_id,
                    asset_id=asset_id, revision_id=request.expected_revision_id, provider="krea",
                    route_policy=record.asset.route_policy, model=prepared.model,
                    endpoint_capability=prepared.endpoint_capability,
                    catalog_version=CATALOG_VERSION, catalog_digest=CATALOG_DIGEST,
                    quote_id=quote.quote_id,
                    quote_expires_at=now + timedelta(seconds=quote_ttl),
                    recovery_authority_id=terms.recovery_authority_id,
                    recovery_verification_key_digest=terms.recovery_verification_key_digest,
                    approved_ceiling_microdollars=ceiling,
                    request_body_digest=prepared.body_digest, issued_at=now,
                    expires_at=now + timedelta(seconds=request.ttl_seconds),
                )
                values = [
                    owner_digest, request.request_id, request_hash, chapter.chapter_id,
                    scene.scene_id, prepared.body_digest, _json(asdict(quote)),
                    _json(asdict(authorization)),
                ]
                ctx.execute(
                    "INSERT INTO multimedia_visual_authorizations VALUES (?,?,?,?,?,?,?,?,?)",
                    [*values, _mac(values, self._key)],
                )
                ctx.execute("COMMIT")
            except Exception:
                ctx.execute("ROLLBACK")
                raise
        return VisualAuthorizationResult(
            chapter.chapter_id, scene.scene_id, width, height, seed,
            prepared.body_digest, image_request, quote, authorization,
        )

    def reopen(
        self,
        *,
        asset_id: str,
        request_id: str,
        expected_revision_id: str,
        owner_id: str,
        store: MultimediaAssetStore,
        terms: VisualAuthorizationTerms,
        now: datetime,
    ) -> VisualAuthorizationResult:
        if not _ID.fullmatch(request_id):
            raise VisualAuthorizationError("visual authorization identifier is invalid")
        owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.visual_authorization.reopen") as ctx:
            ctx.execute(_DDL)
            row = ctx.execute(
                "SELECT * FROM multimedia_visual_authorizations "
                "WHERE owner_identity_digest=? AND request_id=?",
                [owner_digest, request_id],
            ).fetchone()
        if row is None or len(row) != 9 or not isinstance(row[8], str) or not hmac.compare_digest(
            row[8], _mac(list(row[:8]), self._key)
        ):
            raise VisualAuthorizationError("visual authorization is unavailable")
        try:
            authorization = MultimediaExecutionAuthorizationV2.from_dict(json.loads(row[7]))
            issued = datetime.fromisoformat(authorization.issued_at.replace("Z", "+00:00"))
            expires = datetime.fromisoformat(authorization.expires_at.replace("Z", "+00:00"))
            ttl_seconds = int((expires - issued).total_seconds())
        except Exception as exc:
            raise VisualAuthorizationError("stored visual authorization integrity failed") from exc
        if (
            authorization.operator_id != owner_id or authorization.asset_id != asset_id
            or authorization.revision_id != expected_revision_id
        ):
            raise VisualAuthorizationError("visual authorization authority conflicts")
        return self.authorize(
            asset_id,
            VisualAuthorizationRequest(
                request_id=request_id,
                expected_revision_id=expected_revision_id,
                chapter_id=str(row[3]),
                approved_ceiling_microdollars=authorization.approved_ceiling_microdollars,
                operator_acknowledged_spend=True,
                ttl_seconds=ttl_seconds,
            ),
            owner_id=owner_id,
            store=store,
            terms=terms,
            now=now,
        )

    def resolve_binding(
        self,
        *,
        authorization_id: str,
        owner_id: str,
        asset_id: str,
        revision_id: str,
    ) -> VisualAuthorizationBinding:
        """Resolve one signed authority row without reissuing or extending it."""
        if not _ID.fullmatch(authorization_id):
            raise VisualAuthorizationError("visual authorization identifier is invalid")
        owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
        coordinator = FlockWriteCoordinator(self._db_path)
        with coordinator.acquire_write_context("multimedia.visual_authorization.resolve") as ctx:
            ctx.execute(_DDL)
            rows = ctx.execute(
                "SELECT * FROM multimedia_visual_authorizations "
                "WHERE owner_identity_digest=? ORDER BY request_id LIMIT 4097",
                [owner_digest],
            ).fetchall()
        if len(rows) > 4096:
            raise VisualAuthorizationError("visual authorization lookup is unavailable")
        matched: list[VisualAuthorizationBinding] = []
        for row in rows:
            if len(row) != 9 or not isinstance(row[8], str) or not hmac.compare_digest(
                row[8], _mac(list(row[:8]), self._key)
            ):
                raise VisualAuthorizationError("stored visual authorization integrity failed")
            try:
                authorization = MultimediaExecutionAuthorizationV2.from_dict(json.loads(row[7]))
                verify_async_execution_authorization(
                    authorization,
                    signing_key=self._key,
                    operator_id=authorization.operator_id,
                    asset_id=authorization.asset_id,
                    revision_id=authorization.revision_id,
                    provider="krea",
                    route_policy=authorization.route_policy,
                    model=authorization.model,
                    endpoint_capability=authorization.endpoint_capability,
                    catalog_version=authorization.catalog_version,
                    catalog_digest=authorization.catalog_digest,
                    quote_id=authorization.quote_id,
                    recovery_authority_id=authorization.recovery_authority_id,
                    recovery_verification_key_digest=(
                        authorization.recovery_verification_key_digest
                    ),
                    approved_ceiling_microdollars=(
                        authorization.approved_ceiling_microdollars
                    ),
                    request_body_digest=authorization.request_body_digest,
                    # This is retrospective provenance verification. A completed
                    # execution must remain usable after its spend authority expires.
                    now=datetime.fromisoformat(
                        authorization.issued_at.replace("Z", "+00:00")
                    ),
                )
            except Exception as exc:
                raise VisualAuthorizationError(
                    "stored visual authorization integrity failed"
                ) from exc
            if authorization.authorization_id == authorization_id:
                matched.append(
                    VisualAuthorizationBinding(str(row[3]), str(row[4]), authorization)
                )
        if len(matched) != 1:
            raise VisualAuthorizationError("visual authorization is unavailable")
        binding = matched[0]
        if (
            binding.authorization.operator_id != owner_id
            or binding.authorization.asset_id != asset_id
            or binding.authorization.revision_id != revision_id
        ):
            raise VisualAuthorizationError("visual authorization authority conflicts")
        return binding

    def _replay(
        self,
        row: Sequence[object],
        request_hash: str,
        prepared: PreparedKreaRequest,
        terms: Mapping[str, object],
        now: datetime,
    ) -> VisualAuthorizationResult:
        if len(row) != 9 or not isinstance(row[8], str) or not hmac.compare_digest(
            row[8], _mac(list(row[:8]), self._key)
        ):
            raise VisualAuthorizationError("stored visual authorization integrity failed")
        if row[2] != request_hash or row[5] != prepared.body_digest:
            raise VisualAuthorizationError("visual authorization request id already has different terms")
        quote_json, authorization_json = row[6], row[7]
        route_policy = terms.get("route_policy")
        ceiling = terms.get("approved_ceiling_microdollars")
        width, height, seed = terms.get("width"), terms.get("height"), terms.get("seed")
        if (
            not isinstance(quote_json, str)
            or not isinstance(authorization_json, str)
            or not isinstance(route_policy, str)
            or not isinstance(ceiling, int)
            or not isinstance(width, int)
            or not isinstance(height, int)
            or not isinstance(seed, int)
        ):
            raise VisualAuthorizationError("stored visual authorization terms are invalid")
        try:
            quote = KreaQuote(**json.loads(quote_json))
            authorization = MultimediaExecutionAuthorizationV2.from_dict(json.loads(authorization_json))
            issued = datetime.fromisoformat(authorization.issued_at.replace("Z", "+00:00"))
            verify_quote(
                quote, signing_key=self._key, prepared=prepared,
                expected_quote_id=authorization.quote_id,
                expected_expires_at=authorization.quote_expires_at,
                expected_ceiling_microdollars=authorization.approved_ceiling_microdollars,
                now=issued,
            )
            verify_async_execution_authorization(
                authorization, signing_key=self._key,
                operator_id=authorization.operator_id, asset_id=authorization.asset_id,
                revision_id=authorization.revision_id, provider="krea",
                route_policy=route_policy, model=prepared.model,
                endpoint_capability=prepared.endpoint_capability,
                catalog_version=CATALOG_VERSION, catalog_digest=CATALOG_DIGEST,
                quote_id=quote.quote_id,
                recovery_authority_id=authorization.recovery_authority_id,
                recovery_verification_key_digest=authorization.recovery_verification_key_digest,
                approved_ceiling_microdollars=ceiling,
                request_body_digest=prepared.body_digest, now=issued,
            )
        except Exception as exc:
            raise VisualAuthorizationError("stored visual authorization integrity failed") from exc
        return VisualAuthorizationResult(
            str(row[3]), str(row[4]), width, height, seed,
            prepared.body_digest,
            Imagen3Request(**json.loads(prepared.body)),
            quote, authorization,
        )


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _json(value: object) -> str:
    return _canonical(value).decode("ascii")


def _mac(values: Sequence[object], key: bytes) -> str:
    return hmac.new(key, _canonical(values), hashlib.sha256).hexdigest()


__all__ = [
    "VisualAuthorizationBinding", "VisualAuthorizationError", "VisualAuthorizationRegistry",
    "VisualAuthorizationRequest", "VisualAuthorizationResult", "VisualAuthorizationTerms",
]
