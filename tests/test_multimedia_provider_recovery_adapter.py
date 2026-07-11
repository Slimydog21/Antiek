from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime

import httpx
import pytest

from substrate.multimedia.provider_execution import (
    ProviderExecutionRecord,
    ProviderExecutionStatus,
)
from substrate.multimedia.provider_recovery_adapter import (
    HttpProviderRecoveryTransport,
    ProviderAccountRecoveryAdapter,
    ProviderRecoveryError,
    ProviderRecoveryLookup,
)
from substrate.multimedia.tts_reconciliation import sign_provider_recovery_evidence

NOW = datetime(2026, 7, 12, 9, tzinfo=UTC)
EVIDENCE_KEY = b"provider-recovery-evidence-key-32b"
ACCOUNT = hashlib.sha256(b"provider-account-1").hexdigest()
ANTIEK_OWNER = hashlib.sha256(b"operator-1").hexdigest()
AUDIO = b"RIFF-provider-recovered-audio"


def _execution() -> ProviderExecutionRecord:
    return ProviderExecutionRecord(
        execution_id="mmexec_recovery1",
        authorization_id="mmauth_recovery1",
        operator_id="operator-1",
        asset_id="asset-1",
        revision_id="tts-child-1",
        provider="elevenlabs",
        route_policy="balanced",
        model="narrator-v1",
        endpoint_capability="text-to-speech",
        catalog_version="catalog-v1",
        catalog_digest="a" * 64,
        quote_id="quote-1",
        approved_ceiling_microdollars=100_000,
        request_body_digest="b" * 64,
        status=ProviderExecutionStatus.OUTCOME_UNKNOWN,
        provider_job_id=None,
        created_at="2026-07-12T08:00:00.000000Z",
        updated_at="2026-07-12T08:30:00.000000Z",
        recovery_authority_id="recovery-1",
        recovery_verification_key_digest="c" * 64,
    )


def _match(**updates: object) -> dict[str, object]:
    execution = _execution()
    value: dict[str, object] = {
        "execution_id": execution.execution_id,
        "authorization_id": execution.authorization_id,
        "operator_identity_digest": hashlib.sha256(execution.operator_id.encode()).hexdigest(),
        "asset_id": execution.asset_id,
        "revision_id": execution.revision_id,
        "provider": execution.provider,
        "request_body_digest": execution.request_body_digest,
        "account_identity_digest": ACCOUNT,
        "provider_request_id": "provider-job-1",
        "evidence_source": "account-poll-1",
        "audio_base64": base64.b64encode(AUDIO).decode("ascii"),
        "audio_sha256": hashlib.sha256(AUDIO).hexdigest(),
        "recorded_at": "2026-07-12T08:45:00.000000Z",
    }
    value.update(updates)
    return value


def _payload(*matches: dict[str, object]) -> bytes:
    return json.dumps(
        {"schema_version": "antiek.provider-recovery-response.v1", "matches": matches},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _adapter(raw: bytes) -> ProviderAccountRecoveryAdapter:
    return ProviderAccountRecoveryAdapter(
        transport=lambda lookup: raw,
        antiek_owner_identity_digest=ANTIEK_OWNER,
        account_identity_digest=ACCOUNT,
        evidence_key=EVIDENCE_KEY,
    )


def test_provider_account_recovery_binds_exact_execution_and_signs_normalized_audio() -> None:
    recovered = _adapter(_payload(_match())).resolve(_execution(), verified_at=NOW)
    assert recovered.provider_request_id == "provider-job-1"
    assert recovered.audio_bytes == AUDIO
    assert recovered.recorded_at == datetime(2026, 7, 12, 8, 45, tzinfo=UTC)
    assert recovered.external_signature == sign_provider_recovery_evidence(
        evidence_key=EVIDENCE_KEY,
        execution_id=_execution().execution_id,
        provider_request_id=recovered.provider_request_id,
        evidence_source=recovered.evidence_source,
        audio_bytes=AUDIO,
        recorded_at=recovered.recorded_at,
    )


def test_provider_recovery_owner_binding_denies_before_transport() -> None:
    calls = 0

    def transport(lookup: ProviderRecoveryLookup) -> bytes:
        nonlocal calls
        calls += 1
        return _payload(_match())

    adapter = ProviderAccountRecoveryAdapter(
        transport=transport,
        antiek_owner_identity_digest=ANTIEK_OWNER,
        account_identity_digest=ACCOUNT,
        evidence_key=EVIDENCE_KEY,
    )
    foreign = _execution().__class__(**{**_execution().__dict__, "operator_id": "operator-2"})
    with pytest.raises(ProviderRecoveryError, match="unavailable"):
        adapter.resolve(foreign, verified_at=NOW)
    assert calls == 0

    recovered = adapter.resolve(_execution(), verified_at=NOW)
    assert recovered.audio_bytes == AUDIO
    assert calls == 1


@pytest.mark.parametrize("digest", ["", "A" * 64, "a" * 63, "a" * 65])
def test_provider_recovery_requires_canonical_antiek_owner_digest(digest: str) -> None:
    with pytest.raises(ValueError, match="owner identity"):
        ProviderAccountRecoveryAdapter(
            transport=lambda lookup: _payload(_match()),
            antiek_owner_identity_digest=digest,
            account_identity_digest=ACCOUNT,
            evidence_key=EVIDENCE_KEY,
        )


@pytest.mark.parametrize(
    "raw",
    [
        _payload(),
        _payload(_match(), _match(provider_request_id="provider-job-2")),
        _payload(_match(account_identity_digest="d" * 64)),
        _payload(_match(operator_identity_digest=hashlib.sha256(b"other").hexdigest())),
        _payload(_match(request_body_digest="e" * 64)),
        _payload(_match(audio_sha256="f" * 64)),
        _payload(_match(recorded_at="2026-07-12T10:00:00.000000Z")),
        _payload(_match(recorded_at="2026-07-12T08:00:00.000000Z")),
    ],
)
def test_provider_account_recovery_rejects_absent_ambiguous_or_conflicting_evidence(
    raw: bytes,
) -> None:
    with pytest.raises(ProviderRecoveryError):
        _adapter(raw).resolve(_execution(), verified_at=NOW)


def test_provider_account_recovery_rejects_duplicate_fields_and_ineligible_execution() -> None:
    duplicate = (
        b'{"schema_version":"antiek.provider-recovery-response.v1",'
        b'"schema_version":"antiek.provider-recovery-response.v1","matches":[]}'
    )
    with pytest.raises(ProviderRecoveryError, match="invalid"):
        _adapter(duplicate).resolve(_execution(), verified_at=NOW)
    submitted = _execution().__class__(
        **{**_execution().__dict__, "status": ProviderExecutionStatus.SUBMITTED}
    )
    with pytest.raises(ProviderRecoveryError, match="eligible"):
        _adapter(_payload(_match())).resolve(submitted, verified_at=NOW)


def test_http_recovery_transport_uses_fixed_https_host_and_bearer_without_redirects() -> None:
    observed: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["authorization"] = request.headers.get("authorization")
        observed["body"] = json.loads(request.content)
        return httpx.Response(200, content=_payload(_match()))

    transport = HttpProviderRecoveryTransport(
        endpoint="https://recovery.example.test/v1/lookup",
        bearer_token="secret-token",
        allowed_host="recovery.example.test",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(handler)),
    )
    lookup = ProviderRecoveryLookup(
        execution_id="mmexec_recovery1",
        authorization_id="mmauth_recovery1",
        operator_identity_digest=hashlib.sha256(b"operator-1").hexdigest(),
        asset_id="asset-1",
        revision_id="tts-child-1",
        provider="elevenlabs",
        request_body_digest="b" * 64,
    )
    assert transport(lookup) == _payload(_match())
    assert observed == {
        "url": "https://recovery.example.test/v1/lookup",
        "authorization": "Bearer secret-token",
        "body": lookup.to_dict(),
    }
    for endpoint in (
        "http://recovery.example.test/v1/lookup",
        "https://other.example.test/v1/lookup",
        "https://recovery.example.test/v1/lookup?target=other",
        "https://127.0.0.1/v1/lookup",
        "https://localhost/v1/lookup",
        "https://recovery.internal/v1/lookup",
    ):
        with pytest.raises(ValueError, match="endpoint"):
            HttpProviderRecoveryTransport(
                endpoint=endpoint,
                bearer_token="token",
                allowed_host=(
                    "127.0.0.1" if "127" in endpoint
                    else "localhost" if "localhost" in endpoint
                    else "recovery.internal" if "internal" in endpoint
                    else "recovery.example.test"
                ),
            )


def test_http_recovery_transport_maps_gateway_failures_without_leaking_body() -> None:
    def factory() -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(500, text="secret upstream detail")
            )
        )

    transport = HttpProviderRecoveryTransport(
        endpoint="https://recovery.example.test/v1/lookup",
        bearer_token="secret-token",
        allowed_host="recovery.example.test",
        client_factory=factory,
    )
    with pytest.raises(ProviderRecoveryError) as caught:
        transport(
            ProviderRecoveryLookup(
                execution_id="x",
                authorization_id="a",
                operator_identity_digest=hashlib.sha256(b"o").hexdigest(),
                asset_id="asset",
                revision_id="rev",
                provider="provider",
                request_body_digest="b" * 64,
            )
        )
    assert "secret" not in str(caught.value)
