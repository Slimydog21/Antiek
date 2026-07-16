"""Canonical, transport-free protocol for the durable provider broker."""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping
from dataclasses import asdict, dataclass, is_dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from urllib.parse import urlsplit

from runtime.research_runner.protocol import BillingUnit

SCHEMA_VERSION = 1
BROKER_AUDIENCE = "antiek-provider-broker"
MAX_RECEIPT_LIFETIME = timedelta(hours=24)

_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_IDENTITY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")
_DNS_HOST = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)*"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$"
)
_UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_BASE64URL_64 = re.compile(r"^[A-Za-z0-9_-]{86}$")


class BrokerReceiptState(StrEnum):
    AUTHORIZED = "authorized"
    DISPATCH_POSSIBLE = "dispatch_possible"
    UPSTREAM_BOUND = "upstream_bound"
    UNKNOWN = "unknown"
    CHARGED = "charged"
    NOT_FOUND = "not_found"


class ReceiptAlgorithm(StrEnum):
    ED25519_V1 = "ed25519-v1"


def _text(name: str, value: object, *, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value.encode("utf-8")) > maximum
        or not value.isascii()
        or not _IDENTITY.fullmatch(value)
    ):
        raise ValueError(f"{name} must be a bounded ASCII identity")
    return value


def _digest(name: str, value: object) -> str:
    if not isinstance(value, str) or _DIGEST.fullmatch(value) is None:
        raise ValueError(f"{name} must be a canonical SHA-256 digest")
    return value


def _cents(name: str, value: object, *, allow_zero: bool) -> int:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < (0 if allow_zero else 1)
        or value > (1 << 62) - 1
    ):
        raise ValueError(f"{name} must be bounded integer cents")
    return value


def _utc(name: str, value: object) -> datetime:
    if not isinstance(value, str) or _UTC_SECOND.fullmatch(value) is None:
        raise ValueError(f"{name} must be UTC with whole-second precision")
    parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError(f"{name} is not canonical UTC")
    return parsed


def _is_ip_literal(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return False
    return True


def _exact(raw: object, fields: frozenset[str], name: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping) or set(raw) != fields:
        raise ValueError(f"{name} has an invalid field set")
    if not all(isinstance(key, str) for key in raw):
        raise ValueError(f"{name} keys must be strings")
    return raw


@dataclass(frozen=True, slots=True)
class BrokerUsageBound:
    unit: BillingUnit
    maximum: int

    def __post_init__(self) -> None:
        if not isinstance(self.unit, BillingUnit):
            raise TypeError("usage unit must be BillingUnit")
        if isinstance(self.maximum, bool) or not isinstance(self.maximum, int):
            raise TypeError("usage maximum must be an integer")
        if self.maximum <= 0 or self.maximum > (1 << 62) - 1:
            raise ValueError("usage maximum must be positive and bounded")


@dataclass(frozen=True, slots=True)
class BrokerRoute:
    provider_kind: str
    provider: str
    model: str
    operation: str
    region: str
    endpoint: str
    billing_units: tuple[BillingUnit, ...]

    def __post_init__(self) -> None:
        for name in ("provider_kind", "provider", "model", "operation", "region"):
            _text(name, getattr(self, name))
        if not isinstance(self.endpoint, str) or not self.endpoint.isascii():
            raise ValueError("endpoint must be one canonical HTTPS DNS origin")
        parsed = urlsplit(self.endpoint)
        try:
            port = parsed.port
        except ValueError as exc:
            raise ValueError("endpoint must contain a valid port") from exc
        host = parsed.hostname
        canonical_endpoint = (
            f"https://{host}:{port}" if port is not None else f"https://{host}"
        )
        if (
            parsed.scheme != "https"
            or host is None
            or _DNS_HOST.fullmatch(host) is None
            or _is_ip_literal(host)
            or port == 0
            or port == 443
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path
            or self.endpoint != canonical_endpoint
        ):
            raise ValueError("endpoint must be one canonical HTTPS DNS origin")
        if not isinstance(self.billing_units, tuple) or not self.billing_units or any(
            not isinstance(unit, BillingUnit) for unit in self.billing_units
        ):
            raise ValueError("route requires an immutable tuple of closed billing units")
        values = tuple(unit.value for unit in self.billing_units)
        if values != tuple(sorted(set(values))):
            raise ValueError("billing units must be unique and canonically ordered")


@dataclass(frozen=True, slots=True)
class BrokerAuthorization:
    schema_version: int
    tenant_id: str
    idempotency_key: str
    operation_digest: str
    route: BrokerRoute
    bounded_usage: tuple[BrokerUsageBound, ...]
    maximum_charge_cents: int
    currency: str
    pricing_snapshot: str
    issued_at: str
    not_before: str
    expires_at: str

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported broker authorization schema")
        _text("tenant_id", self.tenant_id)
        _text("idempotency_key", self.idempotency_key)
        _digest("operation_digest", self.operation_digest)
        if not isinstance(self.route, BrokerRoute):
            raise TypeError("route must be BrokerRoute")
        if not isinstance(self.bounded_usage, tuple) or not self.bounded_usage or any(
            not isinstance(bound, BrokerUsageBound) for bound in self.bounded_usage
        ):
            raise ValueError("authorization requires an immutable tuple of usage bounds")
        usage_units = tuple(bound.unit.value for bound in self.bounded_usage)
        if usage_units != tuple(sorted(set(usage_units))):
            raise ValueError("usage bounds must be unique and canonically ordered")
        if set(usage_units) != {unit.value for unit in self.route.billing_units}:
            raise ValueError("usage bounds must exactly match route billing units")
        _cents("maximum_charge_cents", self.maximum_charge_cents, allow_zero=False)
        if self.currency != "USD":
            raise ValueError("broker authorization currency must be USD")
        _text("pricing_snapshot", self.pricing_snapshot)
        not_before = _utc("not_before", self.not_before)
        issued_at = _utc("issued_at", self.issued_at)
        expires_at = _utc("expires_at", self.expires_at)
        if not (not_before <= issued_at < expires_at):
            raise ValueError("authorization validity interval is inconsistent")
        if expires_at - not_before > MAX_RECEIPT_LIFETIME:
            raise ValueError("authorization validity exceeds maximum lifetime")


@dataclass(frozen=True, slots=True)
class BrokerReceipt:
    schema_version: int
    issuer: str
    audience: str
    tenant_id: str
    idempotency_key: str
    operation_digest: str
    route_digest: str
    authorization_digest: str
    maximum_charge_cents: int
    currency: str
    pricing_snapshot: str
    state: BrokerReceiptState
    charge_cents: int | None
    evidence_digest: str | None
    output_digest: str | None
    issued_at: str
    not_before: str
    expires_at: str
    nonce: str
    key_id: str
    algorithm: ReceiptAlgorithm

    def __post_init__(self) -> None:
        if type(self.schema_version) is not int or self.schema_version != SCHEMA_VERSION:
            raise ValueError("unsupported broker receipt schema")
        for name in (
            "issuer",
            "tenant_id",
            "idempotency_key",
            "pricing_snapshot",
            "nonce",
            "key_id",
        ):
            _text(name, getattr(self, name))
        if self.audience != BROKER_AUDIENCE:
            raise ValueError("broker receipt audience is invalid")
        for name in ("operation_digest", "route_digest", "authorization_digest"):
            _digest(name, getattr(self, name))
        _cents("maximum_charge_cents", self.maximum_charge_cents, allow_zero=False)
        if self.currency != "USD":
            raise ValueError("broker receipt currency must be USD")
        if not isinstance(self.state, BrokerReceiptState):
            raise TypeError("receipt state must be BrokerReceiptState")
        if not isinstance(self.algorithm, ReceiptAlgorithm):
            raise TypeError("receipt algorithm must be ReceiptAlgorithm")
        for name in ("evidence_digest", "output_digest"):
            value = getattr(self, name)
            if value is not None:
                _digest(name, value)
        if self.state is BrokerReceiptState.CHARGED:
            charge = _cents("charge_cents", self.charge_cents, allow_zero=True)
            if (
                charge > self.maximum_charge_cents
                or self.evidence_digest is None
                or self.output_digest is None
            ):
                raise ValueError(
                    "charged receipt exceeds authority or lacks evidence or output"
                )
        elif self.state is BrokerReceiptState.NOT_FOUND:
            charge = _cents("charge_cents", self.charge_cents, allow_zero=True)
            if charge != 0 or self.evidence_digest is None or self.output_digest:
                raise ValueError("not-found receipt must prove zero charge without output")
        elif self.charge_cents is not None:
            raise ValueError("nonterminal receipt cannot claim charge cents")
        if self.state in (
            BrokerReceiptState.AUTHORIZED,
            BrokerReceiptState.DISPATCH_POSSIBLE,
        ) and (self.evidence_digest is not None or self.output_digest is not None):
            raise ValueError("pre-upstream receipt cannot claim evidence or output")
        if self.state is BrokerReceiptState.UPSTREAM_BOUND and (
            self.evidence_digest is None or self.output_digest is not None
        ):
            raise ValueError("upstream-bound receipt requires identity evidence only")
        if self.state is BrokerReceiptState.UNKNOWN and self.output_digest is not None:
            raise ValueError("unknown receipt cannot claim output")
        not_before = _utc("not_before", self.not_before)
        issued_at = _utc("issued_at", self.issued_at)
        expires_at = _utc("expires_at", self.expires_at)
        if not (not_before <= issued_at < expires_at):
            raise ValueError("receipt validity interval is inconsistent")
        if expires_at - not_before > MAX_RECEIPT_LIFETIME:
            raise ValueError("receipt validity exceeds maximum lifetime")


@dataclass(frozen=True, slots=True)
class SignedBrokerReceipt:
    receipt: BrokerReceipt
    signature: str

    def __post_init__(self) -> None:
        if not isinstance(self.receipt, BrokerReceipt):
            raise TypeError("receipt must be BrokerReceipt")
        if not isinstance(self.signature, str) or _BASE64URL_64.fullmatch(self.signature) is None:
            raise ValueError("signature must be unpadded base64url Ed25519 bytes")
        try:
            decoded = base64.urlsafe_b64decode(self.signature + "==")
        except ValueError as exc:
            raise ValueError("signature is not canonical base64url") from exc
        if len(decoded) != 64 or base64.urlsafe_b64encode(decoded).decode().rstrip("=") != self.signature:
            raise ValueError("signature is not canonical base64url")


def _json_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise TypeError("canonical JSON mapping keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise TypeError(f"unsupported canonical JSON value: {type(value).__name__}")


def canonical_json_bytes(value: object) -> bytes:
    return json.dumps(
        _json_value(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def route_digest(route: BrokerRoute) -> str:
    if not isinstance(route, BrokerRoute):
        raise TypeError("route digest requires BrokerRoute")
    return hashlib.sha256(canonical_json_bytes(route)).hexdigest()


def authorization_digest(authorization: BrokerAuthorization) -> str:
    if not isinstance(authorization, BrokerAuthorization):
        raise TypeError("authorization digest requires BrokerAuthorization")
    return hashlib.sha256(canonical_json_bytes(authorization)).hexdigest()


def receipt_signing_bytes(receipt: BrokerReceipt) -> bytes:
    if not isinstance(receipt, BrokerReceipt):
        raise TypeError("receipt signing payload requires BrokerReceipt")
    return canonical_json_bytes(receipt)


def assert_receipt_authority(
    receipt: BrokerReceipt,
    authorization: BrokerAuthorization,
) -> None:
    if not isinstance(receipt, BrokerReceipt) or not isinstance(
        authorization, BrokerAuthorization
    ):
        raise TypeError("receipt authority requires protocol objects")
    if (
        receipt.tenant_id != authorization.tenant_id
        or receipt.idempotency_key != authorization.idempotency_key
        or receipt.operation_digest != authorization.operation_digest
        or receipt.route_digest != route_digest(authorization.route)
        or receipt.authorization_digest != authorization_digest(authorization)
        or receipt.maximum_charge_cents != authorization.maximum_charge_cents
        or receipt.currency != authorization.currency
        or receipt.pricing_snapshot != authorization.pricing_snapshot
        or _utc("receipt.not_before", receipt.not_before)
        < _utc("authorization.not_before", authorization.not_before)
        or _utc("receipt.expires_at", receipt.expires_at)
        > _utc("authorization.expires_at", authorization.expires_at)
    ):
        raise ValueError("receipt differs from exact broker authorization")


def _usage_from_mapping(raw: object) -> BrokerUsageBound:
    item = _exact(raw, frozenset({"unit", "maximum"}), "usage bound")
    return BrokerUsageBound(BillingUnit(item["unit"]), item["maximum"])  # type: ignore[arg-type]


def _route_from_mapping(raw: object) -> BrokerRoute:
    item = _exact(
        raw,
        frozenset(
            {
                "provider_kind",
                "provider",
                "model",
                "operation",
                "region",
                "endpoint",
                "billing_units",
            }
        ),
        "broker route",
    )
    raw_units = item["billing_units"]
    if not isinstance(raw_units, list):
        raise ValueError("billing_units must be a JSON array")
    return BrokerRoute(
        provider_kind=item["provider_kind"],  # type: ignore[arg-type]
        provider=item["provider"],  # type: ignore[arg-type]
        model=item["model"],  # type: ignore[arg-type]
        operation=item["operation"],  # type: ignore[arg-type]
        region=item["region"],  # type: ignore[arg-type]
        endpoint=item["endpoint"],  # type: ignore[arg-type]
        billing_units=tuple(BillingUnit(unit) for unit in raw_units),
    )


def _receipt_from_mapping(raw: object) -> BrokerReceipt:
    fields = frozenset(BrokerReceipt.__dataclass_fields__)
    item = _exact(raw, fields, "broker receipt")
    return BrokerReceipt(
        schema_version=item["schema_version"],  # type: ignore[arg-type]
        issuer=item["issuer"],  # type: ignore[arg-type]
        audience=item["audience"],  # type: ignore[arg-type]
        tenant_id=item["tenant_id"],  # type: ignore[arg-type]
        idempotency_key=item["idempotency_key"],  # type: ignore[arg-type]
        operation_digest=item["operation_digest"],  # type: ignore[arg-type]
        route_digest=item["route_digest"],  # type: ignore[arg-type]
        authorization_digest=item["authorization_digest"],  # type: ignore[arg-type]
        maximum_charge_cents=item["maximum_charge_cents"],  # type: ignore[arg-type]
        currency=item["currency"],  # type: ignore[arg-type]
        pricing_snapshot=item["pricing_snapshot"],  # type: ignore[arg-type]
        state=BrokerReceiptState(item["state"]),  # type: ignore[arg-type]
        charge_cents=item["charge_cents"],  # type: ignore[arg-type]
        evidence_digest=item["evidence_digest"],  # type: ignore[arg-type]
        output_digest=item["output_digest"],  # type: ignore[arg-type]
        issued_at=item["issued_at"],  # type: ignore[arg-type]
        not_before=item["not_before"],  # type: ignore[arg-type]
        expires_at=item["expires_at"],  # type: ignore[arg-type]
        nonce=item["nonce"],  # type: ignore[arg-type]
        key_id=item["key_id"],  # type: ignore[arg-type]
        algorithm=ReceiptAlgorithm(item["algorithm"]),  # type: ignore[arg-type]
    )


def signed_receipt_from_mapping(raw: object) -> SignedBrokerReceipt:
    item = _exact(raw, frozenset({"receipt", "signature"}), "signed broker receipt")
    return SignedBrokerReceipt(
        receipt=_receipt_from_mapping(item["receipt"]),
        signature=item["signature"],  # type: ignore[arg-type]
    )


def authorization_from_mapping(raw: object) -> BrokerAuthorization:
    fields = frozenset(BrokerAuthorization.__dataclass_fields__)
    item = _exact(raw, fields, "broker authorization")
    raw_usage = item["bounded_usage"]
    if not isinstance(raw_usage, list):
        raise ValueError("bounded_usage must be a JSON array")
    return BrokerAuthorization(
        schema_version=item["schema_version"],  # type: ignore[arg-type]
        tenant_id=item["tenant_id"],  # type: ignore[arg-type]
        idempotency_key=item["idempotency_key"],  # type: ignore[arg-type]
        operation_digest=item["operation_digest"],  # type: ignore[arg-type]
        route=_route_from_mapping(item["route"]),
        bounded_usage=tuple(_usage_from_mapping(bound) for bound in raw_usage),
        maximum_charge_cents=item["maximum_charge_cents"],  # type: ignore[arg-type]
        currency=item["currency"],  # type: ignore[arg-type]
        pricing_snapshot=item["pricing_snapshot"],  # type: ignore[arg-type]
        issued_at=item["issued_at"],  # type: ignore[arg-type]
        not_before=item["not_before"],  # type: ignore[arg-type]
        expires_at=item["expires_at"],  # type: ignore[arg-type]
    )


__all__ = [
    "BROKER_AUDIENCE",
    "SCHEMA_VERSION",
    "BrokerAuthorization",
    "BrokerReceipt",
    "BrokerReceiptState",
    "BrokerRoute",
    "BrokerUsageBound",
    "ReceiptAlgorithm",
    "SignedBrokerReceipt",
    "authorization_digest",
    "authorization_from_mapping",
    "assert_receipt_authority",
    "canonical_json_bytes",
    "receipt_signing_bytes",
    "route_digest",
    "signed_receipt_from_mapping",
]
