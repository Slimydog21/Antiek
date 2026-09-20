from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime, timedelta

import pytest

from substrate.dispatch.request_authority import (
    ApprovedHousePayer,
    AuthorityRefusalCode,
    DispatchAuthorityRefused,
    HouseCredentialBinding,
    HouseCredentialCandidate,
    OwnerByotPayer,
    OwnerCredentialBinding,
    OwnerCredentialCandidate,
    PayerPolicy,
    ProposedRoute,
    RequestedModel,
    freeze_dispatch_authority,
)

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)
DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def _owner_candidate(
    *,
    owner: str = "user-a",
    record_owner: str | None = "user-a",
    credential_owner: str | None = "user-a",
    enabled: bool = True,
    matching_records: int = 1,
    binding_version: int = 3,
    fingerprint: str = DIGEST_A,
    current_fingerprint: str | None = DIGEST_A,
) -> OwnerCredentialCandidate:
    binding = OwnerCredentialBinding(
        owner_user_id=owner,
        user_model_id="model-record-a",
        credential_id="credential-surrogate-a",
        provider_id="deepseek",
        model_id="deepseek-chat",
        metadata_fingerprint=fingerprint,
        binding_version=binding_version,
    )
    return OwnerCredentialCandidate(
        binding=binding,
        record_owner_user_id=record_owner,
        credential_owner_user_id=credential_owner,
        enabled=enabled,
        matching_records=matching_records,
        current_metadata_fingerprint=current_fingerprint,
    )


def _byot_route(**candidate_overrides: object) -> ProposedRoute:
    return ProposedRoute(
        provider_id="deepseek",
        model_id="deepseek-chat",
        projected_max_cents=9,
        owner_credential=_owner_candidate(**candidate_overrides),
        payer=OwnerByotPayer(
            owner_user_id="user-a",
            credential_id="credential-surrogate-a",
            budget_envelope_digest=DIGEST_B,
        ),
    )


def _house_route(
    *,
    approval_owner: str = "user-a",
    approval_action: str = "write.generate_section",
    approval_resource: str = "deliverable-a",
    approval_operation: str = "operation-a",
    approval_route_digest: str = DIGEST_C,
    current_platform_route_id: str = "platform-route-deepseek",
    expires_at: datetime | None = None,
    consumed: bool = False,
    ceiling_cents: int = 20,
    projected_max_cents: int = 9,
) -> ProposedRoute:
    credential = HouseCredentialBinding(
        platform_route_id="platform-route-deepseek",
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    current_credential = HouseCredentialBinding(
        platform_route_id=current_platform_route_id,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    payer = ApprovedHousePayer(
        approval_id="approval-a",
        approval_digest=DIGEST_B,
        owner_user_id=approval_owner,
        action=approval_action,
        resource_id=approval_resource,
        route_binding_digest=(
            credential.route_binding_digest
            if approval_route_digest == DIGEST_C
            else approval_route_digest
        ),
        logical_operation_id=approval_operation,
        ceiling_cents=ceiling_cents,
        expires_at=expires_at or NOW + timedelta(minutes=5),
        consumed=consumed,
    )
    return ProposedRoute(
        provider_id="deepseek",
        model_id="deepseek-chat",
        projected_max_cents=projected_max_cents,
        house_credential=HouseCredentialCandidate(
            binding=credential,
            current_binding=current_credential,
            enabled=True,
            matching_records=1,
        ),
        payer=payer,
    )


def _freeze(
    routes: tuple[ProposedRoute, ...],
    *,
    authenticated_owner: str = "user-a",
    resource_owner: str = "user-a",
    policy: PayerPolicy | str = PayerPolicy.HOUSE_EXPLICIT,
):
    return freeze_dispatch_authority(
        authenticated_owner_user_id=authenticated_owner,
        resource_owner_user_id=resource_owner,
        resource_id="deliverable-a",
        action="write.generate_section",
        logical_operation_id="operation-a",
        requested_model=RequestedModel("deepseek", "deepseek-chat"),
        payer_policy=policy,
        proposed_routes=routes,
        now=NOW,
    )


def _assert_refused(code: AuthorityRefusalCode, callback) -> None:
    with pytest.raises(DispatchAuthorityRefused) as exc:
        callback()
    assert exc.value.code is code
    assert str(exc.value) == code.value


def test_owner_byot_authority_is_frozen_canonical_and_deterministic() -> None:
    authority = _freeze((_byot_route(),), policy=PayerPolicy.BYOT_ONLY)
    same = _freeze((_byot_route(),), policy=PayerPolicy.BYOT_ONLY)

    assert authority == same
    assert authority.digest() == same.digest()
    assert len(authority.digest()) == 64
    assert authority.fallback_manifest[0].credential.kind == "owner_byot"
    assert authority.fallback_manifest[0].payer.kind == "owner_byot"
    assert '"payer_policy":"byot_only"' in authority.canonical_payload()
    assert '"kind":"owner_byot"' in authority.canonical_payload()
    with pytest.raises(dataclasses.FrozenInstanceError):
        authority.owner_user_id = "user-b"  # type: ignore[misc]


def test_house_authority_keeps_platform_credential_distinct_from_request_owner() -> None:
    authority = _freeze((_house_route(),))
    rung = authority.fallback_manifest[0]

    assert rung.credential.kind == "house"
    assert rung.payer.kind == "house"
    assert authority.canonical_payload().count('"kind":"house"') == 2
    assert not hasattr(rung.credential, "owner_user_id")
    assert rung.payer.owner_user_id == "user-a"


@pytest.mark.parametrize(
    ("authenticated_owner", "resource_owner", "code"),
    [
        ("", "user-a", AuthorityRefusalCode.AUTHENTICATED_OWNER_REQUIRED),
        ("user-a", "user-b", AuthorityRefusalCode.RESOURCE_OWNER_MISMATCH),
    ],
)
def test_request_and_resource_owner_must_match(
    authenticated_owner: str,
    resource_owner: str,
    code: AuthorityRefusalCode,
) -> None:
    _assert_refused(
        code,
        lambda: _freeze(
            (_byot_route(),),
            authenticated_owner=authenticated_owner,
            resource_owner=resource_owner,
        ),
    )


@pytest.mark.parametrize("field_name", ["resource_id", "action", "logical_operation_id"])
def test_authority_scope_must_be_explicit(field_name: str) -> None:
    kwargs = {
        "authenticated_owner_user_id": "user-a",
        "resource_owner_user_id": "user-a",
        "resource_id": "deliverable-a",
        "action": "write.generate_section",
        "logical_operation_id": "operation-a",
        "requested_model": None,
        "payer_policy": PayerPolicy.BYOT_ONLY,
        "proposed_routes": (_byot_route(),),
        "now": NOW,
    }
    kwargs[field_name] = ""
    _assert_refused(
        AuthorityRefusalCode.AUTHORITY_SCOPE_INVALID,
        lambda: freeze_dispatch_authority(**kwargs),  # type: ignore[arg-type]
    )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"matching_records": 0}, AuthorityRefusalCode.CREDENTIAL_MISSING),
        ({"matching_records": 2}, AuthorityRefusalCode.CREDENTIAL_AMBIGUOUS),
        ({"enabled": False}, AuthorityRefusalCode.CREDENTIAL_DISABLED),
        ({"owner": "user-b"}, AuthorityRefusalCode.CREDENTIAL_OWNER_MISMATCH),
        ({"record_owner": "user-b"}, AuthorityRefusalCode.CREDENTIAL_OWNER_MISMATCH),
        ({"credential_owner": "user-b"}, AuthorityRefusalCode.CREDENTIAL_OWNER_MISMATCH),
        ({"binding_version": 2}, AuthorityRefusalCode.CREDENTIAL_BINDING_VERSION_UNSUPPORTED),
        ({"current_fingerprint": DIGEST_B}, AuthorityRefusalCode.CREDENTIAL_BINDING_STALE),
        ({"fingerprint": "not-a-digest"}, AuthorityRefusalCode.CREDENTIAL_BINDING_STALE),
    ],
)
def test_owner_credential_metadata_fails_closed(
    overrides: dict[str, object],
    code: AuthorityRefusalCode,
) -> None:
    _assert_refused(code, lambda: _freeze((_byot_route(**overrides),)))


def test_byot_only_rejects_even_valid_house_approval() -> None:
    _assert_refused(
        AuthorityRefusalCode.BYOT_ONLY_HOUSE_FORBIDDEN,
        lambda: _freeze((_house_route(),), policy=PayerPolicy.BYOT_ONLY),
    )


def test_raw_policy_strings_cannot_bypass_byot_only() -> None:
    _assert_refused(
        AuthorityRefusalCode.BYOT_ONLY_HOUSE_FORBIDDEN,
        lambda: _freeze((_house_route(),), policy="byot_only"),
    )
    authority = _freeze((_house_route(),), policy="house_explicit")
    assert authority.payer_policy is PayerPolicy.HOUSE_EXPLICIT
    _assert_refused(
        AuthorityRefusalCode.PAYER_POLICY_INVALID,
        lambda: _freeze((_byot_route(),), policy="allow_everything"),
    )


@pytest.mark.parametrize(
    ("route", "code"),
    [
        (_house_route(approval_owner="user-b"), AuthorityRefusalCode.HOUSE_APPROVAL_OWNER_MISMATCH),
        (_house_route(approval_action="research.run"), AuthorityRefusalCode.HOUSE_APPROVAL_SCOPE_MISMATCH),
        (_house_route(approval_resource="deliverable-b"), AuthorityRefusalCode.HOUSE_APPROVAL_SCOPE_MISMATCH),
        (_house_route(approval_operation="operation-b"), AuthorityRefusalCode.HOUSE_APPROVAL_SCOPE_MISMATCH),
        (_house_route(approval_route_digest=DIGEST_B), AuthorityRefusalCode.HOUSE_APPROVAL_ROUTE_MISMATCH),
        (
            _house_route(current_platform_route_id="tampered-platform-route"),
            AuthorityRefusalCode.CREDENTIAL_BINDING_STALE,
        ),
        (_house_route(expires_at=NOW), AuthorityRefusalCode.HOUSE_APPROVAL_EXPIRED),
        (_house_route(consumed=True), AuthorityRefusalCode.HOUSE_APPROVAL_REPLAYED),
        (
            _house_route(ceiling_cents=8, projected_max_cents=9),
            AuthorityRefusalCode.HOUSE_APPROVAL_CEILING_EXCEEDED,
        ),
    ],
)
def test_house_approval_is_exact_owner_scope_route_and_single_use(
    route: ProposedRoute,
    code: AuthorityRefusalCode,
) -> None:
    _assert_refused(code, lambda: _freeze((route,)))


def test_house_route_requires_approval_and_byot_requires_byot_payer() -> None:
    house_without_approval = dataclasses.replace(_house_route(), payer=None)
    _assert_refused(
        AuthorityRefusalCode.HOUSE_APPROVAL_REQUIRED,
        lambda: _freeze((house_without_approval,)),
    )
    wrong_payer = dataclasses.replace(_byot_route(), payer=_house_route().payer)
    _assert_refused(
        AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH,
        lambda: _freeze((wrong_payer,)),
    )


def test_credential_route_and_byot_usage_attribution_are_exact() -> None:
    wrong_route_binding = dataclasses.replace(
        _owner_candidate().binding,
        model_id="deepseek-reasoner",
    )
    assert wrong_route_binding is not None
    wrong_route = dataclasses.replace(
        _byot_route(),
        owner_credential=dataclasses.replace(
            _owner_candidate(),
            binding=wrong_route_binding,
        ),
    )
    _assert_refused(
        AuthorityRefusalCode.CREDENTIAL_ROUTE_MISMATCH,
        lambda: _freeze((wrong_route,)),
    )
    wrong_usage_payer = dataclasses.replace(
        _byot_route(),
        payer=OwnerByotPayer("user-a", "credential-surrogate-b", DIGEST_B),
    )
    _assert_refused(
        AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH,
        lambda: _freeze((wrong_usage_payer,)),
    )


def test_ordered_manifest_cannot_gain_ambient_fallback_after_freeze() -> None:
    proposed = [_byot_route(), _house_route()]
    authority = _freeze(tuple(proposed))
    proposed.append(_house_route(approval_operation="operation-b"))

    assert [r.credential.kind for r in authority.fallback_manifest] == ["owner_byot", "house"]
    assert len(authority.fallback_manifest) == 2
    assert isinstance(authority.fallback_manifest, tuple)


def test_one_house_approval_cannot_authorize_two_manifest_rungs() -> None:
    _assert_refused(
        AuthorityRefusalCode.HOUSE_APPROVAL_REPLAYED,
        lambda: _freeze((_house_route(), _house_route())),
    )


def test_ambient_environment_key_is_never_a_route(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-ambient-house-secret")
    missing = ProposedRoute(
        provider_id="deepseek",
        model_id="deepseek-chat",
        projected_max_cents=9,
        payer=OwnerByotPayer("user-a", "credential-surrogate-a", DIGEST_B),
    )
    _assert_refused(
        AuthorityRefusalCode.CREDENTIAL_MISSING,
        lambda: _freeze((missing,), policy=PayerPolicy.BYOT_ONLY),
    )
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-ambient-house-secret"


def test_contract_has_no_plaintext_secret_or_endpoint_fields() -> None:
    contract_types = (
        OwnerCredentialBinding,
        HouseCredentialBinding,
        OwnerByotPayer,
        ApprovedHousePayer,
        ProposedRoute,
    )
    forbidden = {"api_key", "secret", "token", "plaintext", "endpoint", "raw_evidence"}
    for contract_type in contract_types:
        names = {field.name for field in dataclasses.fields(contract_type)}
        assert names.isdisjoint(forbidden)


def test_refusal_message_contains_no_submitted_identity_or_surrogate() -> None:
    candidate = _owner_candidate(owner="private-user-b")
    route = dataclasses.replace(_byot_route(), owner_credential=candidate)
    with pytest.raises(DispatchAuthorityRefused) as exc:
        _freeze((route,))
    rendered = repr(exc.value) + str(exc.value)
    assert "private-user-b" not in rendered
    assert "credential-surrogate-a" not in rendered
