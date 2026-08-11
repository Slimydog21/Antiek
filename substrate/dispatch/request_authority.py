"""Pure request-scoped authority contract for paid model dispatch.

This module deliberately performs no credential loading, reservation, provider
I/O, or persistence.  It freezes the security decision those later seams must
honour: one authenticated resource owner, an exact ordered route manifest, and
one credential/payer binding per rung.  Account UI state is only a proposal;
``freeze_dispatch_authority`` is the server-side authorization boundary.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from datetime import UTC, datetime
from enum import Enum, StrEnum
from typing import Literal, NoReturn

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_SUPPORTED_CREDENTIAL_BINDING_VERSION = 3


class AuthorityRefusalCode(StrEnum):
    AUTHENTICATED_OWNER_REQUIRED = "authenticated_owner_required"
    AUTHORITY_SCOPE_INVALID = "authority_scope_invalid"
    RESOURCE_OWNER_MISMATCH = "resource_owner_mismatch"
    ROUTE_REQUIRED = "route_required"
    CREDENTIAL_MISSING = "credential_missing"
    CREDENTIAL_AMBIGUOUS = "credential_ambiguous"
    CREDENTIAL_DISABLED = "credential_disabled"
    CREDENTIAL_OWNER_MISMATCH = "credential_owner_mismatch"
    CREDENTIAL_BINDING_VERSION_UNSUPPORTED = "credential_binding_version_unsupported"
    CREDENTIAL_BINDING_STALE = "credential_binding_stale"
    CREDENTIAL_ROUTE_MISMATCH = "credential_route_mismatch"
    PAYER_CREDENTIAL_MISMATCH = "payer_credential_mismatch"
    PAYER_POLICY_INVALID = "payer_policy_invalid"
    BYOT_ONLY_HOUSE_FORBIDDEN = "byot_only_house_forbidden"
    HOUSE_APPROVAL_REQUIRED = "house_approval_required"
    HOUSE_APPROVAL_OWNER_MISMATCH = "house_approval_owner_mismatch"
    HOUSE_APPROVAL_SCOPE_MISMATCH = "house_approval_scope_mismatch"
    HOUSE_APPROVAL_ROUTE_MISMATCH = "house_approval_route_mismatch"
    HOUSE_APPROVAL_CEILING_EXCEEDED = "house_approval_ceiling_exceeded"
    HOUSE_APPROVAL_EXPIRED = "house_approval_expired"
    HOUSE_APPROVAL_REPLAYED = "house_approval_replayed"


class DispatchAuthorityRefused(ValueError):
    """Stable, value-free refusal suitable for an API error mapping."""

    def __init__(self, code: AuthorityRefusalCode):
        self.code = code
        super().__init__(code.value)


class PayerPolicy(StrEnum):
    BYOT_ONLY = "byot_only"
    HOUSE_EXPLICIT = "house_explicit"


@dataclass(frozen=True, slots=True)
class RequestedModel:
    """Advisory model choice captured for requested-versus-actual receipts."""

    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class OwnerCredentialBinding:
    """Non-secret surrogate for a credential owned by the request owner."""

    owner_user_id: str
    user_model_id: str
    credential_id: str
    provider_id: str
    model_id: str
    metadata_fingerprint: str
    binding_version: int = _SUPPORTED_CREDENTIAL_BINDING_VERSION
    kind: Literal["owner_byot"] = field(default="owner_byot", init=False)


@dataclass(frozen=True, slots=True)
class HouseCredentialBinding:
    """Platform-owned route surrogate authorized by a separate approval."""

    platform_route_id: str
    provider_id: str
    model_id: str
    route_binding_digest: str = field(init=False)
    kind: Literal["house"] = field(default="house", init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "route_binding_digest",
            house_route_binding_digest(
                platform_route_id=self.platform_route_id,
                provider_id=self.provider_id,
                model_id=self.model_id,
            ),
        )


CredentialBinding = OwnerCredentialBinding | HouseCredentialBinding


@dataclass(frozen=True, slots=True)
class OwnerByotPayer:
    owner_user_id: str
    credential_id: str
    budget_envelope_digest: str
    kind: Literal["owner_byot"] = field(default="owner_byot", init=False)


@dataclass(frozen=True, slots=True)
class ApprovedHousePayer:
    approval_id: str
    approval_digest: str
    owner_user_id: str
    action: str
    resource_id: str
    route_binding_digest: str
    logical_operation_id: str
    ceiling_cents: int
    expires_at: datetime
    consumed: bool = False
    kind: Literal["house"] = field(default="house", init=False)


PayerBinding = OwnerByotPayer | ApprovedHousePayer


@dataclass(frozen=True, slots=True)
class RouteRung:
    provider_id: str
    model_id: str
    credential: CredentialBinding
    payer: PayerBinding
    projected_max_cents: int


@dataclass(frozen=True, slots=True)
class DispatchAuthority:
    authority_version: int
    owner_user_id: str
    resource_id: str
    action: str
    logical_operation_id: str
    requested_model: RequestedModel | None
    payer_policy: PayerPolicy
    fallback_manifest: tuple[RouteRung, ...]

    def canonical_payload(self) -> str:
        return canonical_payload(self)

    def digest(self) -> str:
        return hashlib.sha256(self.canonical_payload().encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OwnerCredentialCandidate:
    """Current non-secret registry facts used to authorize one BYOT rung."""

    binding: OwnerCredentialBinding | None
    record_owner_user_id: str | None
    credential_owner_user_id: str | None
    enabled: bool
    matching_records: int
    current_metadata_fingerprint: str | None


@dataclass(frozen=True, slots=True)
class HouseCredentialCandidate:
    """Selected platform route plus independently resolved current facts."""

    binding: HouseCredentialBinding | None
    current_binding: HouseCredentialBinding | None
    enabled: bool
    matching_records: int


@dataclass(frozen=True, slots=True)
class ProposedRoute:
    provider_id: str
    model_id: str
    projected_max_cents: int
    owner_credential: OwnerCredentialCandidate | None = None
    house_credential: HouseCredentialCandidate | None = None
    payer: PayerBinding | None = None


def _refuse(code: AuthorityRefusalCode) -> NoReturn:
    raise DispatchAuthorityRefused(code)


def _valid_digest(value: str) -> bool:
    return bool(_SHA256_RE.fullmatch(value))


def house_route_binding_digest(
    *,
    platform_route_id: str,
    provider_id: str,
    model_id: str,
) -> str:
    payload = json.dumps(
        {
            "model_id": model_id,
            "namespace": "antiek.house-route.v1",
            "platform_route_id": platform_route_id,
            "provider_id": provider_id,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _validate_owner_candidate(
    candidate: OwnerCredentialCandidate,
    *,
    owner_user_id: str,
) -> OwnerCredentialBinding:
    if candidate.matching_records == 0 or candidate.binding is None:
        _refuse(AuthorityRefusalCode.CREDENTIAL_MISSING)
    if candidate.matching_records != 1:
        _refuse(AuthorityRefusalCode.CREDENTIAL_AMBIGUOUS)
    if not candidate.enabled:
        _refuse(AuthorityRefusalCode.CREDENTIAL_DISABLED)
    binding = candidate.binding
    if binding.binding_version != _SUPPORTED_CREDENTIAL_BINDING_VERSION:
        _refuse(AuthorityRefusalCode.CREDENTIAL_BINDING_VERSION_UNSUPPORTED)
    if (
        binding.owner_user_id != owner_user_id
        or candidate.record_owner_user_id != owner_user_id
        or candidate.credential_owner_user_id != owner_user_id
    ):
        _refuse(AuthorityRefusalCode.CREDENTIAL_OWNER_MISMATCH)
    if (
        candidate.current_metadata_fingerprint != binding.metadata_fingerprint
        or not _valid_digest(binding.metadata_fingerprint)
    ):
        _refuse(AuthorityRefusalCode.CREDENTIAL_BINDING_STALE)
    if not all(
        (
            binding.user_model_id,
            binding.credential_id,
            binding.provider_id,
            binding.model_id,
        )
    ):
        _refuse(AuthorityRefusalCode.CREDENTIAL_ROUTE_MISMATCH)
    return binding


def _validate_house_candidate(
    candidate: HouseCredentialCandidate,
) -> HouseCredentialBinding:
    if candidate.matching_records == 0 or candidate.binding is None:
        _refuse(AuthorityRefusalCode.CREDENTIAL_MISSING)
    if candidate.matching_records != 1:
        _refuse(AuthorityRefusalCode.CREDENTIAL_AMBIGUOUS)
    if not candidate.enabled:
        _refuse(AuthorityRefusalCode.CREDENTIAL_DISABLED)
    if candidate.current_binding is None or candidate.current_binding != candidate.binding:
        _refuse(AuthorityRefusalCode.CREDENTIAL_BINDING_STALE)
    if not all(
        (
            candidate.binding.platform_route_id,
            candidate.binding.provider_id,
            candidate.binding.model_id,
        )
    ):
        _refuse(AuthorityRefusalCode.CREDENTIAL_ROUTE_MISMATCH)
    return candidate.binding


def _validate_house_payer(
    payer: ApprovedHousePayer,
    credential: HouseCredentialBinding,
    *,
    owner_user_id: str,
    action: str,
    resource_id: str,
    logical_operation_id: str,
    projected_max_cents: int,
    now: datetime,
) -> None:
    if payer.owner_user_id != owner_user_id:
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_OWNER_MISMATCH)
    if (
        payer.action != action
        or payer.resource_id != resource_id
        or payer.logical_operation_id != logical_operation_id
    ):
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_SCOPE_MISMATCH)
    if payer.route_binding_digest != credential.route_binding_digest:
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_ROUTE_MISMATCH)
    if payer.consumed:
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_REPLAYED)
    if projected_max_cents > payer.ceiling_cents:
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_CEILING_EXCEEDED)
    if payer.expires_at.tzinfo is None or payer.expires_at <= now:
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_EXPIRED)
    if payer.ceiling_cents < 0 or not (
        payer.approval_id
        and
        _valid_digest(payer.approval_digest)
        and _valid_digest(payer.route_binding_digest)
        and _valid_digest(credential.route_binding_digest)
    ):
        _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_SCOPE_MISMATCH)


def freeze_dispatch_authority(
    *,
    authenticated_owner_user_id: str,
    resource_owner_user_id: str,
    resource_id: str,
    action: str,
    logical_operation_id: str,
    requested_model: RequestedModel | None,
    payer_policy: PayerPolicy | str,
    proposed_routes: tuple[ProposedRoute, ...],
    now: datetime,
) -> DispatchAuthority:
    """Validate and freeze an exact route/payer manifest.

    ``proposed_routes`` must already be in routing-precedence order.  Returning
    a tuple makes later config changes incapable of appending ambient fallback.
    """

    owner_user_id = authenticated_owner_user_id.strip()
    if not owner_user_id:
        _refuse(AuthorityRefusalCode.AUTHENTICATED_OWNER_REQUIRED)
    if resource_owner_user_id != owner_user_id:
        _refuse(AuthorityRefusalCode.RESOURCE_OWNER_MISMATCH)
    if not resource_id or not action or not logical_operation_id:
        _refuse(AuthorityRefusalCode.AUTHORITY_SCOPE_INVALID)
    if not proposed_routes:
        _refuse(AuthorityRefusalCode.ROUTE_REQUIRED)
    try:
        normalized_payer_policy = PayerPolicy(payer_policy)
    except (TypeError, ValueError):
        _refuse(AuthorityRefusalCode.PAYER_POLICY_INVALID)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)

    frozen_routes: list[RouteRung] = []
    house_approval_ids: set[str] = set()
    for proposed in proposed_routes:
        credential: CredentialBinding
        payer: PayerBinding
        if proposed.owner_credential is not None and proposed.house_credential is not None:
            _refuse(AuthorityRefusalCode.CREDENTIAL_AMBIGUOUS)
        if proposed.owner_credential is not None:
            credential = _validate_owner_candidate(
                proposed.owner_credential,
                owner_user_id=owner_user_id,
            )
            if not isinstance(proposed.payer, OwnerByotPayer):
                _refuse(AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH)
            if (
                proposed.payer.owner_user_id != owner_user_id
                or proposed.payer.credential_id != credential.credential_id
                or not proposed.payer.credential_id
                or not _valid_digest(proposed.payer.budget_envelope_digest)
            ):
                _refuse(AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH)
            payer = proposed.payer
        elif proposed.house_credential is not None:
            if normalized_payer_policy is PayerPolicy.BYOT_ONLY:
                _refuse(AuthorityRefusalCode.BYOT_ONLY_HOUSE_FORBIDDEN)
            credential = _validate_house_candidate(proposed.house_credential)
            if proposed.payer is None:
                _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_REQUIRED)
            if not isinstance(proposed.payer, ApprovedHousePayer):
                _refuse(AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH)
            if proposed.payer.approval_id in house_approval_ids:
                _refuse(AuthorityRefusalCode.HOUSE_APPROVAL_REPLAYED)
            house_approval_ids.add(proposed.payer.approval_id)
            _validate_house_payer(
                proposed.payer,
                credential,
                owner_user_id=owner_user_id,
                action=action,
                resource_id=resource_id,
                logical_operation_id=logical_operation_id,
                projected_max_cents=proposed.projected_max_cents,
                now=now,
            )
            payer = proposed.payer
        else:
            _refuse(AuthorityRefusalCode.CREDENTIAL_MISSING)
        if credential.provider_id != proposed.provider_id or credential.model_id != proposed.model_id:
            _refuse(AuthorityRefusalCode.CREDENTIAL_ROUTE_MISMATCH)
        if not proposed.provider_id or not proposed.model_id:
            _refuse(AuthorityRefusalCode.CREDENTIAL_ROUTE_MISMATCH)
        if proposed.projected_max_cents < 0:
            _refuse(AuthorityRefusalCode.PAYER_CREDENTIAL_MISMATCH)
        frozen_routes.append(
            RouteRung(
                provider_id=proposed.provider_id,
                model_id=proposed.model_id,
                credential=credential,
                payer=payer,
                projected_max_cents=proposed.projected_max_cents,
            )
        )

    return DispatchAuthority(
        authority_version=1,
        owner_user_id=owner_user_id,
        resource_id=resource_id,
        action=action,
        logical_operation_id=logical_operation_id,
        requested_model=requested_model,
        payer_policy=normalized_payer_policy,
        fallback_manifest=tuple(frozen_routes),
    )


def _canonical_value(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValueError("canonical datetime must be timezone-aware")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical authority value: {type(value).__name__}")


def canonical_payload(authority: DispatchAuthority) -> str:
    return json.dumps(
        _canonical_value(authority),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


__all__ = [
    "ApprovedHousePayer",
    "AuthorityRefusalCode",
    "DispatchAuthority",
    "DispatchAuthorityRefused",
    "HouseCredentialBinding",
    "HouseCredentialCandidate",
    "OwnerByotPayer",
    "OwnerCredentialBinding",
    "OwnerCredentialCandidate",
    "PayerPolicy",
    "ProposedRoute",
    "RequestedModel",
    "RouteRung",
    "canonical_payload",
    "freeze_dispatch_authority",
    "house_route_binding_digest",
]
