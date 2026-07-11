from __future__ import annotations

import ast
import hashlib
import hmac
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.multimedia.execution_authorization import (
    ExecutionAuthorizationConsumed,
    ExecutionAuthorizationIntegrityError,
    ExecutionAuthorizationRevoked,
    MultimediaExecutionAuthorizationV2,
    issue_async_execution_authorization,
    revoke_async_execution_authorization,
    verify_async_execution_authorization,
)
from substrate.multimedia.execution_authorization_issuer import (
    AsyncExecutionAuthorizationIssueRequest,
    ExecutionAuthorizationIssueConflict,
    ExecutionAuthorizationIssuer,
)
from substrate.multimedia.provider_execution import (
    _ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    ProviderExecutionIntegrityError,
    ProviderExecutionStatus,
    begin_provider_submission,
    begin_reserved_provider_submission_set,
    bind_provider_job,
    get_provider_execution,
    mark_submission_outcome_unknown,
    record_external_recovery_evidence,
    record_provider_observation,
)

KEY = b"multimedia-async-provider-contract-key"
EVIDENCE_KEY = b"independent-external-evidence-key!!"
EVIDENCE_KEY_DIGEST = hashlib.sha256(EVIDENCE_KEY).hexdigest()
OTHER_EVIDENCE_KEY = b"attacker-chosen-external-evidence-key"
ISSUED = datetime(2026, 7, 11, 3, 0, tzinfo=UTC)
NOW = ISSUED + timedelta(minutes=1)
CATALOG_DIGEST = hashlib.sha256(b"catalog-v1").hexdigest()
BODY_DIGEST = hashlib.sha256(b'{"prompt":"aircraft"}').hexdigest()
EVIDENCE_DIGEST = hashlib.sha256(b"provider-observation").hexdigest()


def _external_signature(
    execution_id: str,
    provider_job_id: str,
    source: str,
    evidence_digest: str,
    recorded_at: datetime,
) -> str:
    timestamp = recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
    payload = json.dumps(
        [execution_id, provider_job_id, source, evidence_digest, timestamp],
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    return hmac.new(EVIDENCE_KEY, payload, hashlib.sha256).hexdigest()


def _authorization(**overrides: object) -> MultimediaExecutionAuthorizationV2:
    values: dict[str, object] = {
        "signing_key": KEY,
        "request_id": "approval-async-1",
        "operator_id": "alice",
        "asset_id": "asset-1",
        "revision_id": "revision-2",
        "provider": "krea",
        "route_policy": "balanced",
        "model": "runway-gen-4.5",
        "endpoint_capability": "text-to-video",
        "catalog_version": "2026-07-11",
        "catalog_digest": CATALOG_DIGEST,
        "quote_id": "quote-1",
        "quote_expires_at": ISSUED + timedelta(minutes=10),
        "recovery_authority_id": "operator-krea-account-audit",
        "recovery_verification_key_digest": EVIDENCE_KEY_DIGEST,
        "approved_ceiling_microdollars": 250_000,
        "request_body_digest": BODY_DIGEST,
        "issued_at": ISSUED,
        "expires_at": ISSUED + timedelta(hours=1),
    }
    values.update(overrides)
    return issue_async_execution_authorization(**values)  # type: ignore[arg-type]


def _verify(authorization: MultimediaExecutionAuthorizationV2, **overrides: object) -> None:
    values: dict[str, object] = {
        "signing_key": KEY,
        "operator_id": "alice",
        "asset_id": "asset-1",
        "revision_id": "revision-2",
        "provider": "krea",
        "route_policy": "balanced",
        "model": "runway-gen-4.5",
        "endpoint_capability": "text-to-video",
        "catalog_version": "2026-07-11",
        "catalog_digest": CATALOG_DIGEST,
        "quote_id": "quote-1",
        "recovery_authority_id": "operator-krea-account-audit",
        "recovery_verification_key_digest": EVIDENCE_KEY_DIGEST,
        "approved_ceiling_microdollars": 250_000,
        "request_body_digest": BODY_DIGEST,
        "now": NOW,
    }
    values.update(overrides)
    verify_async_execution_authorization(authorization, **values)  # type: ignore[arg-type]


def test_v2_receipt_is_deterministic_round_trippable_and_fully_bound() -> None:
    authorization = _authorization()
    assert authorization.authorization_id == (
        "mmauth2_132e1b77a22918bfab98d846d09bfdd2a787c943aa83bbba26d36241222946ce"
    )
    assert authorization == _authorization()
    assert MultimediaExecutionAuthorizationV2.from_dict(authorization.to_dict()) == authorization
    _verify(authorization)
    for field, value in (
        ("operator_id", "bob"),
        ("asset_id", "asset-elsewhere"),
        ("revision_id", "revision-stale"),
        ("provider", "other"),
        ("route_policy", "highest_quality"),
        ("model", "different-model"),
        ("endpoint_capability", "image"),
        ("catalog_version", "later"),
        ("catalog_digest", "0" * 64),
        ("quote_id", "quote-elsewhere"),
        ("recovery_authority_id", "other-audit-authority"),
        ("recovery_verification_key_digest", "8" * 64),
        ("approved_ceiling_microdollars", 250_001),
        ("request_body_digest", "1" * 64),
    ):
        with pytest.raises(ExecutionAuthorizationIntegrityError, match=field):
            _verify(authorization, **{field: value})


@pytest.mark.parametrize("bad", [True, 0, -1, 1.5, "250", 2**100])
def test_v2_microdollars_are_strict_positive_bigint(bad: object) -> None:
    with pytest.raises(ValueError, match="microdollars"):
        _authorization(approved_ceiling_microdollars=bad)


def test_v2_rejects_digest_tamper_expired_quote_and_v1_shape() -> None:
    authorization = _authorization()
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="identity|signature"):
        _verify(replace(authorization, request_body_digest="2" * 64))
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="quote has expired"):
        _verify(authorization, now=ISSUED + timedelta(minutes=10))
    legacy_shape = authorization.to_dict()
    del legacy_shape["model"]
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="malformed asynchronous"):
        MultimediaExecutionAuthorizationV2.from_dict(legacy_shape)


def test_reserved_submission_set_is_all_or_none(tmp_path: Path) -> None:
    db_path = str(tmp_path / "batch.duckdb")
    first = _authorization()
    second = _authorization(
        request_id="approval-async-2",
        revision_id="revision-3",
        quote_id="quote-2",
        request_body_digest=hashlib.sha256(b"second").hexdigest(),
    )
    reserved = begin_reserved_provider_submission_set(
        db_path=db_path,
        authorizations=(first, second),
        signing_key=KEY,
        now=NOW,
    )
    assert tuple(row.authorization_id for row, _ in reserved) == (
        first.authorization_id,
        second.authorization_id,
    )
    assert all(hold.projected_max_cents == 25 for _, hold in reserved)

    rollback_db = str(tmp_path / "rollback.duckdb")
    expired = _authorization(
        request_id="approval-expired",
        revision_id="revision-expired",
        quote_id="quote-expired",
        request_body_digest=hashlib.sha256(b"expired").hexdigest(),
        quote_expires_at=ISSUED + timedelta(seconds=30),
    )
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="quote has expired"):
        begin_reserved_provider_submission_set(
            db_path=rollback_db,
            authorizations=(first, expired),
            signing_key=KEY,
            now=NOW,
        )
    execution_id = "mmexec_" + hashlib.sha256(
        f"{first.authorization_id}:{first.request_body_digest}".encode()
    ).hexdigest()
    with pytest.raises(ProviderExecutionIntegrityError, match="does not exist"):
        get_provider_execution(
            db_path=rollback_db, execution_id=execution_id, signing_key=KEY
        )


def test_transition_table_is_closed_and_terminal_states_are_immutable() -> None:
    assert set(_ALLOWED_TRANSITIONS) == set(ProviderExecutionStatus)
    assert {
        ProviderExecutionStatus.SUCCEEDED,
        ProviderExecutionStatus.FAILED,
        ProviderExecutionStatus.CANCELLED,
    } == TERMINAL_STATUSES
    assert all(not _ALLOWED_TRANSITIONS[status] for status in TERMINAL_STATUSES)
    assert _ALLOWED_TRANSITIONS[ProviderExecutionStatus.SUBMITTING] == {
        ProviderExecutionStatus.SUBMITTED,
        ProviderExecutionStatus.OUTCOME_UNKNOWN,
    }
    assert ProviderExecutionStatus.SUBMITTING not in {
        target for targets in _ALLOWED_TRANSITIONS.values() for target in targets
    }


def test_async_issuer_replays_exactly_and_conflicts_with_any_changed_term(
    tmp_path: Path,
) -> None:
    issuer = ExecutionAuthorizationIssuer(db_path=str(tmp_path / "issuer.duckdb"), signing_key=KEY)
    request = AsyncExecutionAuthorizationIssueRequest(
        request_id="approval-1",
        operator_id="alice",
        asset_id="asset-1",
        revision_id="revision-2",
        provider="krea",
        route_policy="balanced",
        model="runway-gen-4.5",
        endpoint_capability="text-to-video",
        catalog_version="2026-07-11",
        catalog_digest=CATALOG_DIGEST,
        quote_id="quote-1",
        quote_ttl_seconds=600,
        recovery_authority_id="operator-krea-account-audit",
        recovery_verification_key_digest=EVIDENCE_KEY_DIGEST,
        approved_ceiling_microdollars=250_000,
        request_body_digest=BODY_DIGEST,
        ttl_seconds=900,
    )
    first = issuer.issue_async(request, now=ISSUED)
    assert issuer.issue_async(request, now=ISSUED + timedelta(minutes=5)) == first
    changed = replace(request, model="another-model")
    with pytest.raises(ExecutionAuthorizationIssueConflict):
        issuer.issue_async(changed, now=ISSUED)


def test_begin_submission_atomically_claims_and_exactly_replays(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = str(tmp_path / "execution.duckdb")
    first = begin_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    replay = begin_provider_submission(
        db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
    )
    assert replay == first
    assert first.status is ProviderExecutionStatus.SUBMITTING
    assert first.provider_job_id is None
    assert first.request_body_digest == BODY_DIGEST
    assert (
        get_provider_execution(db_path=db_path, execution_id=first.execution_id, signing_key=KEY)
        == first
    )
    expired_replay = begin_provider_submission(
        db_path=db_path,
        authorization=authorization,
        signing_key=KEY,
        now=ISSUED + timedelta(days=1),
    )
    assert expired_replay == first


def test_job_binding_observations_and_terminal_state_are_idempotent(tmp_path: Path) -> None:
    db_path = str(tmp_path / "execution.duckdb")
    execution = begin_provider_submission(
        db_path=db_path, authorization=_authorization(), signing_key=KEY, now=NOW
    )
    submitted = bind_provider_job(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    assert submitted.status is ProviderExecutionStatus.SUBMITTED
    assert (
        bind_provider_job(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-123",
            signing_key=KEY,
            now=NOW + timedelta(seconds=2),
        )
        == submitted
    )
    with pytest.raises(ProviderExecutionIntegrityError, match="binding conflicts"):
        bind_provider_job(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-other",
            signing_key=KEY,
            now=NOW,
        )
    running = record_provider_observation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        status=ProviderExecutionStatus.RUNNING,
        evidence_digest=EVIDENCE_DIGEST,
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=3),
    )
    assert running.status is ProviderExecutionStatus.RUNNING
    replay = record_provider_observation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        status=ProviderExecutionStatus.RUNNING,
        evidence_digest=EVIDENCE_DIGEST,
        signing_key=KEY,
        observed_at=NOW + timedelta(minutes=1),
    )
    assert replay == running
    progressed = record_provider_observation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        status=ProviderExecutionStatus.RUNNING,
        evidence_digest="2" * 64,
        signing_key=KEY,
        observed_at=NOW + timedelta(minutes=1),
    )
    assert progressed.status is ProviderExecutionStatus.RUNNING
    assert progressed.updated_at != running.updated_at
    with pytest.raises(ProviderExecutionIntegrityError, match="predates"):
        record_provider_observation(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-123",
            status=ProviderExecutionStatus.RUNNING,
            evidence_digest="5" * 64,
            signing_key=KEY,
            observed_at=NOW,
        )
    succeeded = record_provider_observation(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        status=ProviderExecutionStatus.SUCCEEDED,
        evidence_digest="3" * 64,
        signing_key=KEY,
        observed_at=NOW + timedelta(minutes=2),
    )
    assert succeeded.status is ProviderExecutionStatus.SUCCEEDED
    with pytest.raises(ProviderExecutionIntegrityError, match="transition"):
        record_provider_observation(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-123",
            status=ProviderExecutionStatus.RUNNING,
            evidence_digest="4" * 64,
            signing_key=KEY,
            observed_at=NOW + timedelta(minutes=3),
        )


def test_stale_submission_becomes_unknown_without_retry_authority(tmp_path: Path) -> None:
    db_path = str(tmp_path / "execution.duckdb")
    execution = begin_provider_submission(
        db_path=db_path, authorization=_authorization(), signing_key=KEY, now=NOW
    )
    unknown = mark_submission_outcome_unknown(
        db_path=db_path,
        execution_id=execution.execution_id,
        signing_key=KEY,
        now=NOW + timedelta(minutes=5),
    )
    assert unknown.status is ProviderExecutionStatus.OUTCOME_UNKNOWN
    assert unknown.provider_job_id is None
    assert (
        mark_submission_outcome_unknown(
            db_path=db_path,
            execution_id=execution.execution_id,
            signing_key=KEY,
            now=NOW + timedelta(minutes=6),
        )
        == unknown
    )
    with pytest.raises(ProviderExecutionIntegrityError, match="external evidence"):
        bind_provider_job(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="invented-job",
            signing_key=KEY,
            now=NOW + timedelta(minutes=7),
        )
    evidence_recorded_at = NOW + timedelta(minutes=7)
    external_signature = _external_signature(
        execution.execution_id,
        "job-found-by-external-evidence",
        "operator-krea-account-audit",
        "6" * 64,
        evidence_recorded_at,
    )
    evidence = record_external_recovery_evidence(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-found-by-external-evidence",
        source="operator-krea-account-audit",
        evidence_digest="6" * 64,
        signing_key=KEY,
        evidence_verification_key=EVIDENCE_KEY,
        external_signature=external_signature,
        recorded_at=evidence_recorded_at,
    )
    assert evidence.provider_job_id == "job-found-by-external-evidence"
    assert (
        record_external_recovery_evidence(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-found-by-external-evidence",
            source="operator-krea-account-audit",
            evidence_digest="6" * 64,
            signing_key=KEY,
            evidence_verification_key=EVIDENCE_KEY,
            external_signature=external_signature,
            recorded_at=evidence_recorded_at,
        )
        == evidence
    )
    recovered = bind_provider_job(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-found-by-external-evidence",
        signing_key=KEY,
        now=NOW + timedelta(minutes=8),
    )
    assert recovered.status is ProviderExecutionStatus.SUBMITTED
    assert recovered.provider_job_id == "job-found-by-external-evidence"


def test_persisted_execution_tamper_and_wrong_key_fail_closed(tmp_path: Path) -> None:
    db_path = str(tmp_path / "execution.duckdb")
    execution = begin_provider_submission(
        db_path=db_path, authorization=_authorization(), signing_key=KEY, now=NOW
    )
    with pytest.raises(ProviderExecutionIntegrityError, match="corrupt"):
        get_provider_execution(
            db_path=db_path,
            execution_id=execution.execution_id,
            signing_key=b"different-provider-execution-key!!",
        )
    with connect_write(db_path, purpose="test-provider-execution-tamper") as con:
        con.execute(
            "UPDATE multimedia_provider_executions SET operator_id = 'mallory' "
            "WHERE execution_id = ?",
            [execution.execution_id],
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="corrupt"):
        get_provider_execution(
            db_path=db_path, execution_id=execution.execution_id, signing_key=KEY
        )


def test_observation_tamper_fails_closed(tmp_path: Path) -> None:
    db_path = str(tmp_path / "execution.duckdb")
    execution = begin_provider_submission(
        db_path=db_path, authorization=_authorization(), signing_key=KEY, now=NOW
    )
    submitted = bind_provider_job(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-123",
        signing_key=KEY,
        now=NOW + timedelta(seconds=1),
    )
    record_provider_observation(
        db_path=db_path,
        execution_id=submitted.execution_id,
        provider_job_id="job-123",
        status=ProviderExecutionStatus.RUNNING,
        evidence_digest=EVIDENCE_DIGEST,
        signing_key=KEY,
        observed_at=NOW + timedelta(seconds=2),
    )
    with connect_write(db_path, purpose="test-provider-observation-tamper") as con:
        con.execute(
            "UPDATE multimedia_provider_execution_observations "
            "SET observation_mac = 'forged' WHERE execution_id = ?",
            [execution.execution_id],
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="observation identity"):
        record_provider_observation(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-123",
            status=ProviderExecutionStatus.RUNNING,
            evidence_digest=EVIDENCE_DIGEST,
            signing_key=KEY,
            observed_at=NOW + timedelta(seconds=3),
        )


def test_external_recovery_evidence_tamper_fails_closed(tmp_path: Path) -> None:
    db_path = str(tmp_path / "execution.duckdb")
    execution = begin_provider_submission(
        db_path=db_path,
        authorization=_authorization(request_id="evidence-tamper"),
        signing_key=KEY,
        now=NOW,
    )
    mark_submission_outcome_unknown(
        db_path=db_path,
        execution_id=execution.execution_id,
        signing_key=KEY,
        now=NOW + timedelta(minutes=1),
    )
    with pytest.raises(ProviderExecutionIntegrityError, match="signature"):
        record_external_recovery_evidence(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-recovered",
            source="operator-krea-account-audit",
            evidence_digest="7" * 64,
            signing_key=KEY,
            evidence_verification_key=EVIDENCE_KEY,
            external_signature="0" * 64,
            recorded_at=NOW + timedelta(minutes=2),
        )
    attacker_recorded_at = NOW + timedelta(minutes=2)
    attacker_payload = json.dumps(
        [
            execution.execution_id,
            "job-recovered",
            "operator-krea-account-audit",
            "7" * 64,
            attacker_recorded_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        ],
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("ascii")
    with pytest.raises(ProviderExecutionIntegrityError, match="authority"):
        record_external_recovery_evidence(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-recovered",
            source="operator-krea-account-audit",
            evidence_digest="7" * 64,
            signing_key=KEY,
            evidence_verification_key=OTHER_EVIDENCE_KEY,
            external_signature=hmac.new(
                OTHER_EVIDENCE_KEY, attacker_payload, hashlib.sha256
            ).hexdigest(),
            recorded_at=attacker_recorded_at,
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="predates"):
        record_external_recovery_evidence(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-recovered",
            source="operator-krea-account-audit",
            evidence_digest="7" * 64,
            signing_key=KEY,
            evidence_verification_key=EVIDENCE_KEY,
            external_signature=_external_signature(
                execution.execution_id,
                "job-recovered",
                "operator-krea-account-audit",
                "7" * 64,
                NOW,
            ),
            recorded_at=NOW,
        )
    evidence_recorded_at = NOW + timedelta(minutes=2)
    record_external_recovery_evidence(
        db_path=db_path,
        execution_id=execution.execution_id,
        provider_job_id="job-recovered",
        source="operator-krea-account-audit",
        evidence_digest="7" * 64,
        signing_key=KEY,
        evidence_verification_key=EVIDENCE_KEY,
        external_signature=_external_signature(
            execution.execution_id,
            "job-recovered",
            "operator-krea-account-audit",
            "7" * 64,
            evidence_recorded_at,
        ),
        recorded_at=evidence_recorded_at,
    )
    with connect_write(db_path, purpose="test-external-evidence-tamper") as con:
        con.execute(
            "UPDATE multimedia_provider_external_recovery_evidence "
            "SET evidence_mac = 'forged' WHERE execution_id = ?",
            [execution.execution_id],
        )
    with pytest.raises(ProviderExecutionIntegrityError, match="corrupt"):
        bind_provider_job(
            db_path=db_path,
            execution_id=execution.execution_id,
            provider_job_id="job-recovered",
            signing_key=KEY,
            now=NOW + timedelta(minutes=3),
        )


def test_async_revocation_tamper_fails_closed_on_replay(tmp_path: Path) -> None:
    authorization = _authorization(request_id="revocation-tamper")
    db_path = str(tmp_path / "execution.duckdb")
    revoke_async_execution_authorization(
        authorization,
        signing_key=KEY,
        db_path=db_path,
        operator_id="alice",
        now=NOW,
    )
    with connect_write(db_path, purpose="test-async-revocation-tamper") as con:
        con.execute(
            "UPDATE multimedia_async_execution_authorization_revocations "
            "SET revoked_at = '2099-01-01T00:00:00Z' WHERE authorization_id = ?",
            [authorization.authorization_id],
        )
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="corrupt"):
        begin_provider_submission(
            db_path=db_path,
            authorization=authorization,
            signing_key=KEY,
            now=NOW,
        )
    with pytest.raises(ExecutionAuthorizationIntegrityError, match="corrupt"):
        revoke_async_execution_authorization(
            authorization,
            signing_key=KEY,
            db_path=db_path,
            operator_id="alice",
            now=NOW + timedelta(minutes=1),
        )


def test_concurrent_begin_has_one_claim_and_one_execution(tmp_path: Path) -> None:
    authorization = _authorization()
    db_path = str(tmp_path / "execution.duckdb")

    def begin(_: int):  # type: ignore[no-untyped-def]
        return begin_provider_submission(
            db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        records = list(pool.map(begin, range(16)))
    assert len({record.execution_id for record in records}) == 1
    assert records.count(records[0]) == 16


def test_revoke_and_begin_have_exactly_one_winner(tmp_path: Path) -> None:
    for index in range(12):
        authorization = _authorization(request_id=f"race-{index}")
        root = tmp_path / str(index)
        root.mkdir()
        db_path = str(root / "execution.duckdb")

        def begin(
            authorization: MultimediaExecutionAuthorizationV2 = authorization,
            db_path: str = db_path,
        ) -> str:
            try:
                begin_provider_submission(
                    db_path=db_path, authorization=authorization, signing_key=KEY, now=NOW
                )
                return "began"
            except ExecutionAuthorizationRevoked:
                return "revoked"

        def revoke(
            authorization: MultimediaExecutionAuthorizationV2 = authorization,
            db_path: str = db_path,
        ) -> str:
            try:
                revoke_async_execution_authorization(
                    authorization,
                    signing_key=KEY,
                    db_path=db_path,
                    operator_id="alice",
                    now=NOW,
                )
                return "revoked"
            except ExecutionAuthorizationConsumed:
                return "began"

        with ThreadPoolExecutor(max_workers=2) as pool:
            begin_future = pool.submit(begin)
            revoke_future = pool.submit(revoke)
            outcomes = {begin_future.result(), revoke_future.result()}
        assert outcomes in ({"began"}, {"revoked"})


def test_async_contract_has_no_network_secret_or_environment_import() -> None:
    root = Path(__file__).parents[1]
    paths = (
        root / "substrate" / "multimedia" / "execution_authorization.py",
        root / "substrate" / "multimedia" / "execution_authorization_issuer.py",
        root / "substrate" / "multimedia" / "provider_execution.py",
    )
    imported: set[str] = set()
    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".", 1)[0])
    assert imported.isdisjoint(
        {"httpx", "requests", "urllib", "socket", "subprocess", "os", "krea"}
    )
