"""Tamper-evident visual assessments and owner-scoped routing advice.

The module is deliberately advisory. It does not import or call the multimedia
router, provider transports, or execution authorization issuers.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

from runtime.db_lock import FlockWriteCoordinator, connect_read

from .artifact_quarantine import (
    ArtifactQuarantineError,
    ArtifactQuarantineReceipt,
    reopen_quarantined_artifact,
)
from .artifact_quarantine import (
    _mac as _artifact_mac,
)
from .provider_execution import (
    ProviderExecutionIntegrityError,
    ProviderExecutionRecord,
    ProviderExecutionStatus,
    _evidence_mac,
    _record,
    _timestamp,
)
from .read_model import MultimediaAssetStore

RUBRIC_VERSION = "visual-quality-v1"
FORMULA_VERSION = "visual-routing-advisory-v1"
MIN_ASSESSED_CANDIDATES = 20
MIN_EXECUTIONS = 10
MIN_ASSETS = 3
MIN_COVERAGE = 0.80
_MAX_ASSESSMENTS = 100_000

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CAPABILITY_KIND: dict[str, Literal["image", "video"]] = {
    "text-to-image": "image",
    "text-to-video": "video",
}
_REASON_CODES = frozenset(
    {
        "prompt_mismatch",
        "technical_artifact",
        "visual_incoherence",
        "not_production_usable",
        "unsafe_or_misleading",
        "other",
    }
)

_DDL = """
CREATE TABLE IF NOT EXISTS multimedia_visual_quality_assessments (
    assessment_id TEXT PRIMARY KEY,
    owner_identity_digest TEXT NOT NULL,
    request_id TEXT NOT NULL,
    execution_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    asset_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    rubric_version TEXT NOT NULL,
    prompt_fidelity INTEGER NOT NULL,
    technical_acceptability INTEGER NOT NULL,
    visual_coherence INTEGER NOT NULL,
    production_usable INTEGER NOT NULL,
    disposition TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    assessed_at TEXT NOT NULL,
    assessment_mac TEXT NOT NULL,
    UNIQUE(owner_identity_digest, request_id),
    UNIQUE(candidate_id, rubric_version)
)
"""


class VisualQualityAdvisoryError(RuntimeError):
    """Assessment or report evidence is unavailable or contradictory."""


class VisualQualityAdvisoryIntegrityError(VisualQualityAdvisoryError):
    """Persisted assessment, execution, artifact, or accounting evidence is corrupt."""


RubricAnswer = Literal["pass", "fail"]
Disposition = Literal["accepted", "rejected"]
GenerationKind = Literal["image", "video"]


@dataclass(frozen=True)
class VisualQualityAssessmentRequest:
    request_id: str
    expected_revision_id: str
    disposition: Disposition
    prompt_fidelity: RubricAnswer
    technical_acceptability: RubricAnswer
    visual_coherence: RubricAnswer
    production_usable: RubricAnswer
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class VisualQualityAssessment:
    assessment_id: str
    request_id: str
    execution_id: str
    candidate_id: str
    asset_id: str
    revision_id: str
    artifact_sha256: str
    rubric_version: str
    disposition: Disposition
    prompt_fidelity: RubricAnswer
    technical_acceptability: RubricAnswer
    visual_coherence: RubricAnswer
    production_usable: RubricAnswer
    reason_codes: tuple[str, ...]
    assessed_at: str
    quality_score: float


@dataclass(frozen=True, order=True)
class VisualRoutingCohortKey:
    generation_kind: GenerationKind
    provider: str
    model: str
    route_policy: str
    catalog_version: str
    catalog_digest: str
    rubric_version: str


@dataclass(frozen=True)
class VisualRoutingCohort:
    key: VisualRoutingCohortKey
    n_executions: int
    n_assets: int
    n_materialized_candidates: int
    n_assessed_candidates: int
    n_accepted: int
    assessment_coverage: float
    mean_quality: float | None
    acceptance_rate: float | None
    quality_lower_bound: float | None
    charged_cents_total: int | None
    charged_cents_per_assessed_candidate: float | None
    charged_cents_per_accepted_candidate: float | None
    efficiency_score: float | None
    eligible: bool
    ineligibility_reasons: tuple[str, ...]


@dataclass(frozen=True)
class VisualRoutingRecommendation:
    cohort: VisualRoutingCohortKey
    efficiency_score: float


@dataclass(frozen=True)
class VisualRoutingAdvisory:
    formula_version: str
    rubric_version: str
    as_of: str
    cohorts: tuple[VisualRoutingCohort, ...]
    exclusions: dict[str, int]
    recommendation: VisualRoutingRecommendation | None


@dataclass
class _CohortAccumulator:
    execution_ids: set[str]
    asset_ids: set[str]
    candidate_ids: set[str]
    assessment_ids: set[str]
    accepted: int
    quality_total: int
    charged_by_execution: dict[str, int]
    unresolved_accounting: int


class VisualQualityAdvisoryRegistry:
    """Own append-only assessments and deterministic report projection."""

    def __init__(self, *, db_path: str, signing_key: bytes) -> None:
        if not db_path or not isinstance(signing_key, bytes) or len(signing_key) < 16:
            raise ValueError("visual quality advisory configuration is invalid")
        self._db_path = db_path
        self._key = signing_key
        self._coordinator = FlockWriteCoordinator(db_path)
        with self._coordinator.acquire_write_context("multimedia.visual_quality.schema") as ctx:
            ctx.execute(_DDL)

    def assess(
        self,
        *,
        asset_id: str,
        candidate_id: str,
        request: VisualQualityAssessmentRequest,
        owner_id: str,
        store: MultimediaAssetStore,
        now: datetime,
    ) -> VisualQualityAssessment:
        """Append one immutable candidate assessment after reopening every authority."""
        normalized = _normalize_request(request)
        _identifier("asset_id", asset_id)
        _identifier("candidate_id", candidate_id)
        owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
        replay = self._replay_request(
            owner_digest=owner_digest,
            asset_id=asset_id,
            candidate_id=candidate_id,
            request=normalized,
        )
        if replay is not None:
            return replay
        try:
            current = store.get(asset_id, owner_id=owner_id)
        except (KeyError, ValueError, RuntimeError) as exc:
            raise VisualQualityAdvisoryError("visual quality asset is unavailable") from exc
        if current.asset.revision_id != normalized.expected_revision_id:
            raise VisualQualityAdvisoryError("visual quality revision is stale")

        receipt, execution, charged_cents = self._reopen_candidate_authority(
            asset_id=asset_id,
            candidate_id=candidate_id,
            revision_id=normalized.expected_revision_id,
            owner_id=owner_id,
        )
        del charged_cents  # Accounting proof is required, but is never copied into an assessment.
        timestamp = _timestamp(now)
        assessment_id = "mmquality_" + hashlib.sha256(
            f"{candidate_id}\0{RUBRIC_VERSION}".encode()
        ).hexdigest()
        values: list[object] = [
            assessment_id,
            owner_digest,
            normalized.request_id,
            execution.execution_id,
            candidate_id,
            asset_id,
            normalized.expected_revision_id,
            receipt.sha256,
            RUBRIC_VERSION,
            _answer_value(normalized.prompt_fidelity),
            _answer_value(normalized.technical_acceptability),
            _answer_value(normalized.visual_coherence),
            _answer_value(normalized.production_usable),
            normalized.disposition,
            _canonical_reason_codes(normalized.reason_codes),
            timestamp,
        ]
        mac = _mac(self._key, values)

        try:
            revision_guard = store.guard_revision(
                asset_id,
                normalized.expected_revision_id,
                owner_id=owner_id,
            )
            with revision_guard, self._coordinator.acquire_write_context(
                "multimedia.visual_quality.assess"
            ) as ctx:
                ctx.execute(_DDL)
                ctx.execute("BEGIN TRANSACTION")
                try:
                    rows = ctx.execute(
                        "SELECT * FROM multimedia_visual_quality_assessments "
                        "ORDER BY assessment_id LIMIT ?",
                        [_MAX_ASSESSMENTS + 1],
                    ).fetchall()
                    if len(rows) > _MAX_ASSESSMENTS:
                        raise VisualQualityAdvisoryError(
                            "visual quality assessment capacity is exhausted"
                        )
                    verified = [(row, _assessment_from_row(row, self._key)) for row in rows]
                    by_request = next(
                        (
                            row
                            for row, _ in verified
                            if row[1] == owner_digest and row[2] == normalized.request_id
                        ),
                        None,
                    )
                    by_candidate = next(
                        (
                            row
                            for row, _ in verified
                            if row[4] == candidate_id and row[8] == RUBRIC_VERSION
                        ),
                        None,
                    )
                    existing = by_request or by_candidate
                    if existing is not None:
                        result = _assessment_from_row(existing, self._key)
                        if list(existing[:15]) != values[:15]:
                            raise VisualQualityAdvisoryError("visual quality assessment conflicts")
                        if (
                            by_request is not None
                            and by_candidate is not None
                            and by_request != by_candidate
                        ):
                            raise VisualQualityAdvisoryIntegrityError(
                                "visual quality assessment identities conflict"
                            )
                        ctx.execute("COMMIT")
                        return result
                    if len(rows) >= _MAX_ASSESSMENTS:
                        raise VisualQualityAdvisoryError(
                            "visual quality assessment capacity is exhausted"
                        )
                    # Recheck all database-backed proof while holding both locks.
                    self._verify_candidate_rows_in_context(
                        ctx,
                        candidate_id=candidate_id,
                        receipt_id=receipt.receipt_id,
                        artifact_sha256=receipt.sha256,
                        execution=execution,
                    )
                    _verify_receipt_bytes(receipt)
                    ctx.execute(
                        "INSERT INTO multimedia_visual_quality_assessments VALUES "
                        "(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        [*values, mac],
                    )
                    inserted = ctx.execute(
                        "SELECT * FROM multimedia_visual_quality_assessments "
                        "WHERE assessment_id=?",
                        [assessment_id],
                    ).fetchone()
                    if inserted is None:
                        raise VisualQualityAdvisoryIntegrityError(
                            "visual quality assessment disappeared"
                        )
                    result = _assessment_from_row(inserted, self._key)
                    ctx.execute("COMMIT")
                    return result
                except Exception:
                    ctx.execute("ROLLBACK")
                    raise
        except ValueError as exc:
            raise VisualQualityAdvisoryError("visual quality revision is stale") from exc

    def _replay_request(
        self,
        *,
        owner_digest: str,
        asset_id: str,
        candidate_id: str,
        request: VisualQualityAssessmentRequest,
    ) -> VisualQualityAssessment | None:
        try:
            with connect_read(self._db_path) as connection:
                rows = connection.execute(
                    "SELECT * FROM multimedia_visual_quality_assessments "
                    "ORDER BY assessment_id LIMIT ?",
                    [_MAX_ASSESSMENTS + 1],
                ).fetchall()
        except Exception as exc:
            raise VisualQualityAdvisoryError("visual quality assessment is unavailable") from exc
        if len(rows) > _MAX_ASSESSMENTS:
            raise VisualQualityAdvisoryError("visual quality assessment capacity is exhausted")
        matches = []
        for row in rows:
            assessment = _assessment_from_row(row, self._key)
            if row[1] == owner_digest and assessment.request_id == request.request_id:
                matches.append(assessment)
        if not matches:
            return None
        if len(matches) != 1:
            raise VisualQualityAdvisoryIntegrityError(
                "visual quality request identity is ambiguous"
            )
        assessment = matches[0]
        expected = (
            assessment.asset_id == asset_id
            and assessment.candidate_id == candidate_id
            and assessment.revision_id == request.expected_revision_id
            and assessment.disposition == request.disposition
            and assessment.prompt_fidelity == request.prompt_fidelity
            and assessment.technical_acceptability == request.technical_acceptability
            and assessment.visual_coherence == request.visual_coherence
            and assessment.production_usable == request.production_usable
            and assessment.reason_codes == request.reason_codes
        )
        if not expected:
            raise VisualQualityAdvisoryError("visual quality assessment conflicts")
        return assessment

    def report(
        self,
        *,
        owner_id: str,
        as_of: datetime,
        generation_kind: GenerationKind | None = None,
        rubric_version: str = RUBRIC_VERSION,
    ) -> VisualRoutingAdvisory:
        """Project a read-only advisory from authoritative evidence as of one cutoff."""
        if rubric_version != RUBRIC_VERSION:
            raise VisualQualityAdvisoryError("visual quality rubric version is unsupported")
        if generation_kind not in {None, "image", "video"}:
            raise VisualQualityAdvisoryError("visual generation kind is unsupported")
        cutoff = _utc_datetime(as_of)
        cutoff_text = _timestamp(cutoff)
        owner_digest = hashlib.sha256(owner_id.encode()).hexdigest()
        exclusions = {
            "after_cutoff": 0,
            "non_krea": 0,
            "not_succeeded": 0,
            "unknown_capability": 0,
            "without_materialized_candidates": 0,
            "unresolved_accounting": 0,
        }
        accumulators: dict[VisualRoutingCohortKey, _CohortAccumulator] = {}
        assessments_by_candidate: dict[str, VisualQualityAssessment] = {}

        try:
            with connect_read(self._db_path) as connection:
                connection.execute("BEGIN TRANSACTION")
                assessment_rows = connection.execute(
                    "SELECT * FROM multimedia_visual_quality_assessments "
                    "ORDER BY assessed_at, assessment_id LIMIT ?",
                    [_MAX_ASSESSMENTS + 1],
                ).fetchall()
                if len(assessment_rows) > _MAX_ASSESSMENTS:
                    raise VisualQualityAdvisoryError(
                        "visual quality assessment capacity is exhausted"
                    )
                for row in assessment_rows:
                    assessment = _assessment_from_row(row, self._key)
                    if row[1] != owner_digest or _parse_timestamp(assessment.assessed_at) > cutoff:
                        continue
                    assessments_by_candidate[assessment.candidate_id] = assessment

                candidates_by_execution: dict[str, list[tuple[object, ...]]] = {}
                all_candidate_rows = connection.execute(
                    "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                    "declared_media_type, candidate_mac FROM "
                    "multimedia_provider_artifact_candidates ORDER BY candidate_id"
                ).fetchall()
                for candidate_row in all_candidate_rows:
                    candidate_execution_id = str(candidate_row[1])
                    _verify_candidate_row(candidate_row, candidate_execution_id, self._key)
                    candidates_by_execution.setdefault(candidate_execution_id, []).append(
                        candidate_row
                    )

                receipts_by_candidate: dict[str, tuple[object, ...]] = {}
                all_receipt_rows = connection.execute(
                    "SELECT * FROM multimedia_artifact_quarantine_receipts "
                    "ORDER BY candidate_id"
                ).fetchall()
                for receipt_row in all_receipt_rows:
                    if (
                        len(receipt_row) != 9
                        or not isinstance(receipt_row[8], str)
                        or not hmac.compare_digest(
                            receipt_row[8],
                            _artifact_mac(self._key, list(receipt_row[:8])),
                        )
                    ):
                        raise VisualQualityAdvisoryIntegrityError(
                            "visual routing artifact receipt integrity failed"
                        )
                    receipt_candidate_id = str(receipt_row[2])
                    if receipt_candidate_id in receipts_by_candidate:
                        raise VisualQualityAdvisoryIntegrityError(
                            "visual routing artifact receipt identity conflicts"
                        )
                    receipts_by_candidate[receipt_candidate_id] = receipt_row

                execution_rows = connection.execute(
                    "SELECT * FROM multimedia_provider_executions ORDER BY execution_id"
                ).fetchall()
                for row in execution_rows:
                    execution = _record(row, signing_key=self._key)
                    if (
                        execution.operator_id != owner_id
                        or _parse_timestamp(execution.created_at) > cutoff
                        or _parse_timestamp(execution.updated_at) > cutoff
                    ):
                        continue
                    if execution.provider != "krea":
                        exclusions["non_krea"] += 1
                        continue
                    if execution.status is not ProviderExecutionStatus.SUCCEEDED:
                        exclusions["not_succeeded"] += 1
                        continue
                    kind = _CAPABILITY_KIND.get(execution.endpoint_capability)
                    if kind is None:
                        exclusions["unknown_capability"] += 1
                        continue
                    if generation_kind is not None and kind != generation_kind:
                        continue
                    candidate_rows = sorted(
                        candidates_by_execution.get(execution.execution_id, []),
                        key=lambda candidate: int(candidate[2]),
                    )
                    materialized: list[str] = []
                    for candidate_row in candidate_rows:
                        receipt_row = receipts_by_candidate.get(str(candidate_row[0]))
                        if receipt_row is None:
                            continue
                        if _parse_timestamp(str(receipt_row[7])) > cutoff:
                            continue
                        # Validate bytes against the receipt already read in this snapshot.
                        _verify_receipt_bytes(_receipt_from_row(receipt_row, self._key))
                        materialized.append(str(candidate_row[0]))
                    if not materialized:
                        exclusions["without_materialized_candidates"] += 1
                        continue
                    key = VisualRoutingCohortKey(
                        generation_kind=kind,
                        provider=execution.provider,
                        model=execution.model,
                        route_policy=execution.route_policy,
                        catalog_version=execution.catalog_version,
                        catalog_digest=execution.catalog_digest,
                        rubric_version=RUBRIC_VERSION,
                    )
                    acc = accumulators.setdefault(
                        key,
                        _CohortAccumulator(set(), set(), set(), set(), 0, 0, {}, 0),
                    )
                    acc.execution_ids.add(execution.execution_id)
                    acc.asset_ids.add(execution.asset_id)
                    acc.candidate_ids.update(materialized)
                    try:
                        charged = _charged_cents(connection, execution, as_of=cutoff)
                    except VisualQualityAdvisoryIntegrityError:
                        raise
                    except VisualQualityAdvisoryError:
                        charged = None
                    if charged is None:
                        acc.unresolved_accounting += 1
                        exclusions["unresolved_accounting"] += 1
                    else:
                        acc.charged_by_execution[execution.execution_id] = charged
                    for candidate_id in materialized:
                        candidate_assessment = assessments_by_candidate.get(candidate_id)
                        if candidate_assessment is None:
                            continue
                        if (
                            candidate_assessment.execution_id != execution.execution_id
                            or candidate_assessment.asset_id != execution.asset_id
                            or candidate_assessment.revision_id != execution.revision_id
                            or candidate_assessment.rubric_version != RUBRIC_VERSION
                        ):
                            raise VisualQualityAdvisoryIntegrityError(
                                "visual quality assessment attribution conflicts"
                            )
                        acc.assessment_ids.add(candidate_assessment.assessment_id)
                        acc.quality_total += round(candidate_assessment.quality_score * 4)
                        if candidate_assessment.disposition == "accepted":
                            acc.accepted += 1
                connection.execute("COMMIT")
        except VisualQualityAdvisoryError:
            raise
        except (ArtifactQuarantineError, ProviderExecutionIntegrityError) as exc:
            raise VisualQualityAdvisoryIntegrityError(
                "visual routing advisory evidence failed integrity"
            ) from exc
        except Exception as exc:
            raise VisualQualityAdvisoryError("visual routing advisory is unavailable") from exc

        cohorts = tuple(_finalize_cohort(key, accumulators[key]) for key in sorted(accumulators))
        eligible = [cohort for cohort in cohorts if cohort.eligible]
        eligible.sort(
            key=lambda cohort: (
                -(cohort.efficiency_score or 0.0),
                -cohort.n_assessed_candidates,
                cohort.key,
            )
        )
        recommendation = None
        if eligible:
            winner = eligible[0]
            assert winner.efficiency_score is not None
            recommendation = VisualRoutingRecommendation(winner.key, winner.efficiency_score)
        return VisualRoutingAdvisory(
            formula_version=FORMULA_VERSION,
            rubric_version=RUBRIC_VERSION,
            as_of=cutoff_text,
            cohorts=cohorts,
            exclusions=exclusions,
            recommendation=recommendation,
        )

    def _reopen_candidate_authority(
        self,
        *,
        asset_id: str,
        candidate_id: str,
        revision_id: str,
        owner_id: str,
    ) -> tuple[ArtifactQuarantineReceipt, ProviderExecutionRecord, int]:
        try:
            receipt = reopen_quarantined_artifact(
                db_path=self._db_path, candidate_id=candidate_id, signing_key=self._key
            )
            with connect_read(self._db_path) as connection:
                row = connection.execute(
                    "SELECT * FROM multimedia_provider_executions WHERE execution_id=?",
                    [receipt.execution_id],
                ).fetchone()
                if row is None:
                    raise VisualQualityAdvisoryIntegrityError(
                        "visual quality execution is unavailable"
                    )
                execution = _record(row, signing_key=self._key)
                candidate_row = connection.execute(
                    "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
                    "declared_media_type, candidate_mac FROM "
                    "multimedia_provider_artifact_candidates WHERE candidate_id=?",
                    [candidate_id],
                ).fetchone()
                _verify_candidate_row(candidate_row, execution.execution_id, self._key)
                charged = _charged_cents(connection, execution)
        except VisualQualityAdvisoryError:
            raise
        except (ArtifactQuarantineError, ProviderExecutionIntegrityError) as exc:
            raise VisualQualityAdvisoryIntegrityError(
                "visual quality candidate failed integrity"
            ) from exc
        except Exception as exc:
            raise VisualQualityAdvisoryError("visual quality candidate is unavailable") from exc
        if (
            receipt.candidate_id != candidate_id
            or receipt.execution_id != execution.execution_id
            or execution.operator_id != owner_id
            or execution.asset_id != asset_id
            or execution.revision_id != revision_id
            or execution.provider != "krea"
            or execution.status is not ProviderExecutionStatus.SUCCEEDED
            or execution.endpoint_capability not in _CAPABILITY_KIND
            or charged is None
        ):
            raise VisualQualityAdvisoryError("visual quality candidate authority conflicts")
        return receipt, execution, charged

    def _verify_candidate_rows_in_context(
        self,
        ctx: Any,
        *,
        candidate_id: str,
        receipt_id: str,
        artifact_sha256: str,
        execution: ProviderExecutionRecord,
    ) -> None:
        candidate = ctx.execute(
            "SELECT candidate_id, execution_id, ordinal, source_locator_digest, "
            "declared_media_type, candidate_mac FROM "
            "multimedia_provider_artifact_candidates WHERE candidate_id=?",
            [candidate_id],
        ).fetchone()
        _verify_candidate_row(candidate, execution.execution_id, self._key)
        receipt = ctx.execute(
            "SELECT receipt_id, execution_id, candidate_id, sha256 FROM "
            "multimedia_artifact_quarantine_receipts WHERE candidate_id=?",
            [candidate_id],
        ).fetchone()
        if receipt != (receipt_id, execution.execution_id, candidate_id, artifact_sha256):
            raise VisualQualityAdvisoryIntegrityError("visual quality artifact binding conflicts")
        charged = _charged_cents(ctx, execution)
        if charged is None:
            raise VisualQualityAdvisoryError("visual quality accounting is unresolved")


def _normalize_request(request: VisualQualityAssessmentRequest) -> VisualQualityAssessmentRequest:
    request_id = _identifier("request_id", request.request_id)
    revision = _identifier("expected_revision_id", request.expected_revision_id)
    if request.disposition not in {"accepted", "rejected"}:
        raise VisualQualityAdvisoryError("visual quality disposition is invalid")
    answers = (
        request.prompt_fidelity,
        request.technical_acceptability,
        request.visual_coherence,
        request.production_usable,
    )
    if any(answer not in {"pass", "fail"} for answer in answers):
        raise VisualQualityAdvisoryError("visual quality rubric answer is invalid")
    if request.disposition == "accepted" and request.production_usable != "pass":
        raise VisualQualityAdvisoryError(
            "accepted visual quality requires production usability"
        )
    reasons = tuple(sorted(request.reason_codes))
    if (
        len(reasons) > 8
        or len(set(reasons)) != len(reasons)
        or any(reason not in _REASON_CODES for reason in reasons)
    ):
        raise VisualQualityAdvisoryError("visual quality reason codes are invalid")
    return VisualQualityAssessmentRequest(
        request_id=request_id,
        expected_revision_id=revision,
        disposition=request.disposition,
        prompt_fidelity=request.prompt_fidelity,
        technical_acceptability=request.technical_acceptability,
        visual_coherence=request.visual_coherence,
        production_usable=request.production_usable,
        reason_codes=reasons,
    )


def _charged_cents(
    connection: Any,
    execution: ProviderExecutionRecord,
    *,
    as_of: datetime | None = None,
) -> int | None:
    execution_row = connection.execute(
        "SELECT authorization_signature FROM multimedia_provider_executions "
        "WHERE execution_id=?",
        [execution.execution_id],
    ).fetchone()
    claim = connection.execute(
        "SELECT signature, status, actual_cents, settled_at FROM "
        "multimedia_execution_authorization_claims WHERE authorization_id=?",
        [execution.authorization_id],
    ).fetchone()
    hold = connection.execute(
        "SELECT projected_max_cents, state FROM midnight_oil_call_holds WHERE run_id=?",
        [execution.authorization_id],
    ).fetchone()
    reservation = connection.execute(
        "SELECT ceiling_cents, spent_cents, held_cents, status FROM "
        "midnight_oil_reservations WHERE run_id=?",
        [execution.authorization_id],
    ).fetchone()
    expected = (execution.approved_ceiling_microdollars + 9_999) // 10_000
    if execution_row is None or claim is None or hold is None or reservation is None:
        return None
    settled_at = claim[3]
    if isinstance(settled_at, datetime):
        settled = settled_at.replace(tzinfo=UTC) if settled_at.tzinfo is None else settled_at
    elif isinstance(settled_at, str):
        settled = _parse_timestamp(settled_at)
    else:
        settled = None
    if as_of is not None and (settled is None or settled.astimezone(UTC) > as_of):
        return None
    if (
        claim[0] != execution_row[0]
        or claim[1] != "settled"
        or claim[2] != expected
        or settled is None
        or hold != (expected, "settled")
        or reservation != (expected, expected, 0, "exhausted")
    ):
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality charged-cent accounting conflicts"
        )
    return int(expected)


def _verify_candidate_row(row: Any, execution_id: str, key: bytes) -> None:
    if (
        row is None
        or len(row) != 6
        or row[1] != execution_id
        or not isinstance(row[5], str)
        or not hmac.compare_digest(row[5], _evidence_mac(key, list(row[:5])))
    ):
        raise VisualQualityAdvisoryIntegrityError("visual quality candidate integrity failed")


def _receipt_from_row(row: Any, key: bytes) -> ArtifactQuarantineReceipt:
    if (
        row is None
        or len(row) != 9
        or not isinstance(row[8], str)
        or not hmac.compare_digest(row[8], _artifact_mac(key, list(row[:8])))
    ):
        raise VisualQualityAdvisoryIntegrityError(
            "visual routing artifact receipt integrity failed"
        )
    return ArtifactQuarantineReceipt(
        receipt_id=str(row[0]),
        execution_id=str(row[1]),
        candidate_id=str(row[2]),
        media_type=str(row[3]),
        byte_count=int(row[4]),
        sha256=str(row[5]),
        quarantine_path=str(row[6]),
        receipt_mac=str(row[8]),
    )


def _verify_receipt_bytes(receipt: ArtifactQuarantineReceipt) -> None:
    path = Path(receipt.quarantine_path)
    try:
        metadata = path.lstat()
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise VisualQualityAdvisoryIntegrityError(
                "visual quality artifact failed commit-time integrity"
            )
        data = path.read_bytes()
    except OSError as exc:
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality artifact failed commit-time integrity"
        ) from exc
    if len(data) != receipt.byte_count or hashlib.sha256(data).hexdigest() != receipt.sha256:
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality artifact failed commit-time integrity"
        )


def _assessment_from_row(row: Any, key: bytes) -> VisualQualityAssessment:
    if row is None or len(row) != 17 or not isinstance(row[16], str):
        raise VisualQualityAdvisoryIntegrityError("visual quality assessment is invalid")
    values = list(row[:16])
    if not hmac.compare_digest(row[16], _mac(key, values)):
        raise VisualQualityAdvisoryIntegrityError("visual quality assessment integrity failed")
    if (
        not _DIGEST.fullmatch(str(row[1]))
        or not _DIGEST.fullmatch(str(row[7]))
        or row[8] != RUBRIC_VERSION
        or any(value not in (0, 1) for value in row[9:13])
        or row[13] not in {"accepted", "rejected"}
    ):
        raise VisualQualityAdvisoryIntegrityError("visual quality assessment is invalid")
    try:
        reasons_value = json.loads(str(row[14]))
        reasons = tuple(str(value) for value in reasons_value)
    except Exception as exc:
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality assessment reason codes are invalid"
        ) from exc
    if _canonical_reason_codes(reasons) != row[14]:
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality assessment reason codes are invalid"
        )
    answers = tuple("pass" if int(value) else "fail" for value in row[9:13])
    if row[13] == "accepted" and answers[3] != "pass":
        raise VisualQualityAdvisoryIntegrityError("visual quality disposition conflicts")
    return VisualQualityAssessment(
        assessment_id=str(row[0]),
        request_id=str(row[2]),
        execution_id=str(row[3]),
        candidate_id=str(row[4]),
        asset_id=str(row[5]),
        revision_id=str(row[6]),
        artifact_sha256=str(row[7]),
        rubric_version=str(row[8]),
        prompt_fidelity=cast(RubricAnswer, answers[0]),
        technical_acceptability=cast(RubricAnswer, answers[1]),
        visual_coherence=cast(RubricAnswer, answers[2]),
        production_usable=cast(RubricAnswer, answers[3]),
        disposition=cast(Disposition, str(row[13])),
        reason_codes=reasons,
        assessed_at=str(row[15]),
        quality_score=sum(int(value) for value in row[9:13]) / 4,
    )


def _finalize_cohort(
    key: VisualRoutingCohortKey, acc: _CohortAccumulator
) -> VisualRoutingCohort:
    assessed = len(acc.assessment_ids)
    materialized = len(acc.candidate_ids)
    executions = len(acc.execution_ids)
    assets = len(acc.asset_ids)
    coverage = assessed / materialized if materialized else 0.0
    acceptance = acc.accepted / assessed if assessed else None
    mean_quality = acc.quality_total / (4 * assessed) if assessed else None
    lower = _wilson_lower_bound(acc.accepted, assessed) if assessed else None
    charges_complete = acc.unresolved_accounting == 0 and len(acc.charged_by_execution) == executions
    charged_total = sum(acc.charged_by_execution.values()) if charges_complete else None
    per_assessed = charged_total / assessed if charged_total is not None and assessed else None
    per_accepted = charged_total / acc.accepted if charged_total is not None and acc.accepted else None
    efficiency = None
    if lower is not None and per_assessed is not None and per_assessed > 0:
        efficiency = lower / (per_assessed / 100)
    reasons: list[str] = []
    if assessed < MIN_ASSESSED_CANDIDATES:
        reasons.append("minimum_assessed_candidates")
    if executions < MIN_EXECUTIONS:
        reasons.append("minimum_distinct_executions")
    if assets < MIN_ASSETS:
        reasons.append("minimum_distinct_assets")
    if coverage < MIN_COVERAGE:
        reasons.append("minimum_assessment_coverage")
    if not charges_complete:
        reasons.append("unresolved_accounting")
    if charged_total is None or charged_total <= 0:
        reasons.append("nonzero_charged_cost")
    return VisualRoutingCohort(
        key=key,
        n_executions=executions,
        n_assets=assets,
        n_materialized_candidates=materialized,
        n_assessed_candidates=assessed,
        n_accepted=acc.accepted,
        assessment_coverage=_rounded(coverage),
        mean_quality=_rounded_optional(mean_quality),
        acceptance_rate=_rounded_optional(acceptance),
        quality_lower_bound=_rounded_optional(lower),
        charged_cents_total=charged_total,
        charged_cents_per_assessed_candidate=_rounded_optional(per_assessed),
        charged_cents_per_accepted_candidate=_rounded_optional(per_accepted),
        efficiency_score=_rounded_optional(efficiency),
        eligible=not reasons,
        ineligibility_reasons=tuple(reasons),
    )


def _wilson_lower_bound(successes: int, total: int) -> float:
    if total <= 0 or successes < 0 or successes > total:
        raise ValueError("Wilson inputs are invalid")
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = proportion + z * z / (2 * total)
    margin = z * math.sqrt(
        (proportion * (1 - proportion) + z * z / (4 * total)) / total
    )
    return max(0.0, (centre - margin) / denominator)


def _canonical_reason_codes(values: tuple[str, ...]) -> str:
    ordered = tuple(sorted(values))
    if (
        len(ordered) > 8
        or len(set(ordered)) != len(ordered)
        or any(value not in _REASON_CODES for value in ordered)
    ):
        raise VisualQualityAdvisoryIntegrityError(
            "visual quality assessment reason codes are invalid"
        )
    return json.dumps(ordered, ensure_ascii=True, separators=(",", ":"))


def _identifier(name: str, value: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not _ID.fullmatch(normalized):
        raise VisualQualityAdvisoryError(f"visual quality {name} is invalid")
    return normalized


def _answer_value(value: RubricAnswer) -> int:
    return 1 if value == "pass" else 0


def _mac(key: bytes, values: list[object]) -> str:
    payload = json.dumps(
        values, ensure_ascii=True, allow_nan=False, separators=(",", ":")
    ).encode("ascii")
    return hmac.new(key, payload, hashlib.sha256).hexdigest()


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise VisualQualityAdvisoryIntegrityError("visual quality timestamp is invalid") from exc
    return _utc_datetime(parsed)


def _utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise VisualQualityAdvisoryError("visual quality timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _rounded(value: float) -> float:
    return round(value, 8)


def _rounded_optional(value: float | None) -> float | None:
    return None if value is None else _rounded(value)


__all__ = [
    "FORMULA_VERSION",
    "RUBRIC_VERSION",
    "VisualQualityAdvisoryError",
    "VisualQualityAdvisoryIntegrityError",
    "VisualQualityAdvisoryRegistry",
    "VisualQualityAssessment",
    "VisualQualityAssessmentRequest",
    "VisualRoutingAdvisory",
    "VisualRoutingCohort",
    "VisualRoutingCohortKey",
    "VisualRoutingRecommendation",
]
