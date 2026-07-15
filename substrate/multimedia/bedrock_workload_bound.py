"""Pure, redacted Bedrock batch workload and maximum-cost contracts."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal, localcontext
from typing import TypeAlias

_SHA256 = re.compile(r"[0-9a-f]{64}")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,17})(?:\.[0-9]{1,12})?")
_CALCULATED_DECIMAL = re.compile(r"(?:0|[1-9][0-9]{0,30})(?:\.[0-9]{1,30})?")
_TIMESTAMP = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z")
_MAX_JSON_DEPTH = 24
_MAX_JSON_ITEMS = 100_000
_MAX_TEXT_CHARS = 1_000_000
_MAX_JSONL_BYTES = 1_000_000_000
_MAX_CENTS = 4_611_686_018_427_387_903

JsonScalar: TypeAlias = None | bool | int | str  # noqa: UP040 - Python 3.11 support
JsonValue: TypeAlias = (  # noqa: UP040 - Python 3.11 support
    JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]
)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _text(name: str, value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{name} must be non-empty canonical text")
    return value


def _positive_int(name: str, value: object, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum:
        raise ValueError(f"{name} must be an integer between 1 and {maximum}")
    return value


def _digest(name: str, value: object) -> str:
    value = _text(name, value)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be a lowercase SHA-256")
    return value


def _decimal(name: str, value: object) -> str:
    value = _text(name, value)
    if _DECIMAL.fullmatch(value) is None or ("." in value and value.endswith("0")):
        raise ValueError(f"{name} must be a canonical non-negative decimal")
    return value


def _timestamp(name: str, value: object) -> datetime:
    value = _text(name, value)
    if _TIMESTAMP.fullmatch(value) is None:
        raise ValueError(f"{name} must be a whole-second UTC timestamp")
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid UTC timestamp") from exc
    return parsed


@dataclass(frozen=True)
class BedrockBatchModelProfile:
    provider_model_id: str
    antiek_model: str
    region: str
    rate_tier: str
    context_tokens: int
    maximum_records: int
    maximum_output_tokens_per_record: int
    output_cap_field: str
    profile_version: str

    def __post_init__(self) -> None:
        for name in (
            "provider_model_id", "antiek_model", "region", "rate_tier",
            "output_cap_field", "profile_version",
        ):
            _text(name, getattr(self, name))
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", self.output_cap_field) is None:
            raise ValueError("output_cap_field must be a JSON field name")
        _positive_int("context_tokens", self.context_tokens, 10_000_000)
        _positive_int("maximum_records", self.maximum_records, 100_000)
        _positive_int(
            "maximum_output_tokens_per_record",
            self.maximum_output_tokens_per_record,
            self.context_tokens,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "antiek_model": self.antiek_model,
            "context_tokens": self.context_tokens,
            "maximum_output_tokens_per_record": self.maximum_output_tokens_per_record,
            "maximum_records": self.maximum_records,
            "output_cap_field": self.output_cap_field,
            "profile_version": self.profile_version,
            "provider_model_id": self.provider_model_id,
            "rate_tier": self.rate_tier,
            "region": self.region,
        }

    @property
    def canonical_json(self) -> str:
        return _canonical(self.as_dict())

    @property
    def profile_digest(self) -> str:
        return _sha256(self.canonical_json.encode())

    @classmethod
    def from_json(cls, raw: str) -> BedrockBatchModelProfile:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("profile_json must be canonical JSON") from exc
        if not isinstance(payload, dict) or _canonical(payload) != raw:
            raise ValueError("profile_json must be a canonical object")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise ValueError("profile_json has an invalid shape") from exc


@dataclass(frozen=True)
class BedrockBatchRateSnapshot:
    provider_model_id: str
    region: str
    rate_tier: str
    input_usd_per_million_tokens: str
    output_usd_per_million_tokens: str
    fixed_request_usd: str
    currency: str
    effective_at: str
    valid_until: str
    source_digest: str
    rate_version: str
    paid: bool = True

    def __post_init__(self) -> None:
        for name in ("provider_model_id", "region", "rate_tier", "rate_version"):
            _text(name, getattr(self, name))
        for name in (
            "input_usd_per_million_tokens", "output_usd_per_million_tokens",
            "fixed_request_usd",
        ):
            _decimal(name, getattr(self, name))
        if self.currency != "USD":
            raise ValueError("currency must be USD")
        if not isinstance(self.paid, bool):
            raise ValueError("paid must be boolean")
        effective = _timestamp("effective_at", self.effective_at)
        valid_until = _timestamp("valid_until", self.valid_until)
        if valid_until <= effective:
            raise ValueError("valid_until must be after effective_at")
        _digest("source_digest", self.source_digest)

    def as_dict(self) -> dict[str, object]:
        return {
            "currency": self.currency,
            "effective_at": self.effective_at,
            "fixed_request_usd": self.fixed_request_usd,
            "input_usd_per_million_tokens": self.input_usd_per_million_tokens,
            "output_usd_per_million_tokens": self.output_usd_per_million_tokens,
            "paid": self.paid,
            "provider_model_id": self.provider_model_id,
            "rate_tier": self.rate_tier,
            "rate_version": self.rate_version,
            "region": self.region,
            "source_digest": self.source_digest,
            "valid_until": self.valid_until,
        }

    @property
    def canonical_json(self) -> str:
        return _canonical(self.as_dict())

    @property
    def rate_digest(self) -> str:
        return _sha256(self.canonical_json.encode())

    def require_current(self, now: datetime) -> None:
        if not isinstance(now, datetime) or now.tzinfo is None:
            raise TypeError("now must be timezone-aware")
        current = now.astimezone(UTC).replace(microsecond=0)
        if not _timestamp("effective_at", self.effective_at) <= current < _timestamp(
            "valid_until", self.valid_until
        ):
            raise ValueError("rate snapshot is not current")

    @classmethod
    def from_json(cls, raw: str) -> BedrockBatchRateSnapshot:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("rates_json must be canonical JSON") from exc
        if not isinstance(payload, dict) or _canonical(payload) != raw:
            raise ValueError("rates_json must be a canonical object")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise ValueError("rates_json has an invalid shape") from exc


@dataclass(frozen=True)
class BedrockBatchWorkloadBound:
    contract_version: str
    workload_byte_length: int
    workload_sha256: str
    record_count: int
    ordered_record_ids_sha256: str
    output_caps_sha256: str
    profile_json: str
    profile_digest: str
    rates_json: str
    rates_digest: str
    input_token_ceiling: int
    output_token_ceiling: int
    exact_unrounded_usd: str
    reservation_cents: int

    def __post_init__(self) -> None:
        if self.contract_version != "bedrock-batch-workload-bound-v1":
            raise ValueError("unknown workload bound contract version")
        _positive_int("workload_byte_length", self.workload_byte_length, _MAX_JSONL_BYTES)
        _positive_int("record_count", self.record_count, 100_000)
        for name in (
            "workload_sha256", "ordered_record_ids_sha256", "output_caps_sha256",
            "profile_digest", "rates_digest",
        ):
            _digest(name, getattr(self, name))
        if _sha256(self.profile_json.encode()) != self.profile_digest:
            raise ValueError("profile digest mismatch")
        if _sha256(self.rates_json.encode()) != self.rates_digest:
            raise ValueError("rates digest mismatch")
        _positive_int("input_token_ceiling", self.input_token_ceiling, 1_000_000_000_000)
        if isinstance(self.output_token_ceiling, bool) or not 0 < self.output_token_ceiling <= 1_000_000_000_000:
            raise ValueError("output_token_ceiling is out of range")
        if (
            not isinstance(self.exact_unrounded_usd, str)
            or _CALCULATED_DECIMAL.fullmatch(self.exact_unrounded_usd) is None
            or ("." in self.exact_unrounded_usd and self.exact_unrounded_usd.endswith("0"))
        ):
            raise ValueError("exact_unrounded_usd must be a canonical calculated decimal")
        if isinstance(self.reservation_cents, bool) or not 0 <= self.reservation_cents <= _MAX_CENTS:
            raise ValueError("reservation_cents is out of range")
        try:
            profile_contract = BedrockBatchModelProfile.from_json(self.profile_json)
            rates_contract = BedrockBatchRateSnapshot.from_json(self.rates_json)
            profile = profile_contract.as_dict()
            rates = rates_contract.as_dict()
            if (
                self.profile_digest != profile_contract.profile_digest
                or self.rates_digest != rates_contract.rate_digest
                or (
                    profile_contract.provider_model_id,
                    profile_contract.region,
                    profile_contract.rate_tier,
                )
                != (
                    rates_contract.provider_model_id,
                    rates_contract.region,
                    rates_contract.rate_tier,
                )
            ):
                raise ValueError("profile and rate identity conflict")
            expected_input = self.record_count * profile_contract.context_tokens
            maximum_output = (
                self.record_count * profile["maximum_output_tokens_per_record"]
            )
            with localcontext() as context:
                context.prec = 80
                expected_total = (
                    Decimal(expected_input)
                    * Decimal(rates["input_usd_per_million_tokens"])
                    + Decimal(self.output_token_ceiling)
                    * Decimal(rates["output_usd_per_million_tokens"])
                ) / Decimal(1_000_000) + Decimal(rates["fixed_request_usd"])
                expected_cents = int(
                    (expected_total * 100).to_integral_value(rounding=ROUND_CEILING)
                )
            expected_exact = format(expected_total, "f")
            if "." in expected_exact:
                expected_exact = expected_exact.rstrip("0").rstrip(".")
            calculated_valid = (
                self.input_token_ceiling == expected_input
                and self.output_token_ceiling <= maximum_output
                and self.exact_unrounded_usd == expected_exact
                and self.reservation_cents == expected_cents
                and (
                    expected_cents != 0
                    or (
                        rates["paid"] is False
                        and all(
                            Decimal(rates[name]) == 0
                            for name in (
                                "input_usd_per_million_tokens",
                                "output_usd_per_million_tokens",
                                "fixed_request_usd",
                            )
                        )
                    )
                )
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            calculated_valid = False
        if not calculated_valid:
            raise ValueError("workload bound calculated operands do not reconcile")

    def as_dict(self) -> dict[str, object]:
        return {
            "contract_version": self.contract_version,
            "exact_unrounded_usd": self.exact_unrounded_usd,
            "input_token_ceiling": self.input_token_ceiling,
            "ordered_record_ids_sha256": self.ordered_record_ids_sha256,
            "output_caps_sha256": self.output_caps_sha256,
            "output_token_ceiling": self.output_token_ceiling,
            "profile_digest": self.profile_digest,
            "profile_json": self.profile_json,
            "rates_digest": self.rates_digest,
            "rates_json": self.rates_json,
            "record_count": self.record_count,
            "reservation_cents": self.reservation_cents,
            "workload_byte_length": self.workload_byte_length,
            "workload_sha256": self.workload_sha256,
        }

    @property
    def canonical_json(self) -> str:
        return _canonical(self.as_dict())

    @property
    def digest(self) -> str:
        return _sha256(self.canonical_json.encode())

    @classmethod
    def from_json(cls, raw: str) -> BedrockBatchWorkloadBound:
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("workload bound must be canonical JSON") from exc
        if not isinstance(payload, dict) or _canonical(payload) != raw:
            raise ValueError("workload bound must be a canonical object")
        try:
            return cls(**payload)
        except TypeError as exc:
            raise ValueError("workload bound has an invalid shape") from exc

    def verify_workload_bytes(self, workload_bytes: bytes) -> None:
        if not isinstance(workload_bytes, bytes):
            raise TypeError("workload_bytes must be exact bytes")
        if len(workload_bytes) != self.workload_byte_length or _sha256(workload_bytes) != self.workload_sha256:
            raise ValueError("workload bytes conflict with the bound")
        if not workload_bytes.endswith(b"\n"):
            raise ValueError("workload bytes must end with LF")
        records: list[Mapping[str, object]] = []
        try:
            for line in workload_bytes.splitlines():
                decoded = line.decode("ascii")
                payload = json.loads(decoded)
                if _canonical(payload) != decoded or not isinstance(payload, dict):
                    raise ValueError("workload record is not canonical")
                records.append(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("workload bytes are not canonical ASCII JSONL") from exc
        rematerialized, rebound = materialize_bedrock_batch_workload(
            records,
            BedrockBatchModelProfile.from_json(self.profile_json),
            BedrockBatchRateSnapshot.from_json(self.rates_json),
        )
        if rematerialized != workload_bytes or rebound != self:
            raise ValueError("workload bytes do not reproduce the bound")

    def require_current(self, now: datetime) -> None:
        BedrockBatchRateSnapshot.from_json(self.rates_json).require_current(now)


def _validated_json(value: object, *, depth: int, counter: list[int]) -> JsonValue:
    if depth > _MAX_JSON_DEPTH:
        raise ValueError("modelInput exceeds maximum JSON depth")
    counter[0] += 1
    if counter[0] > _MAX_JSON_ITEMS:
        raise ValueError("workload exceeds maximum JSON items")
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        if not -(2**63) <= value < 2**63:
            raise ValueError("JSON integer is out of range")
        return value
    if isinstance(value, str):
        if len(value) > _MAX_TEXT_CHARS:
            raise ValueError("JSON text is too large")
        return value
    if isinstance(value, Mapping):
        result: dict[str, JsonValue] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("JSON object keys must be strings")
            if len(key) > _MAX_TEXT_CHARS:
                raise ValueError("JSON key is too large")
            result[key] = _validated_json(item, depth=depth + 1, counter=counter)
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_validated_json(item, depth=depth + 1, counter=counter) for item in value]
    raise ValueError("modelInput accepts JSON values without floats")


def materialize_bedrock_batch_workload(
    records: Sequence[Mapping[str, object]],
    profile: BedrockBatchModelProfile,
    rates: BedrockBatchRateSnapshot,
) -> tuple[bytes, BedrockBatchWorkloadBound]:
    """Return exact JSONL bytes and their conservative, prompt-free spend bound."""
    if not isinstance(profile, BedrockBatchModelProfile) or not isinstance(rates, BedrockBatchRateSnapshot):
        raise TypeError("profile and rates must be server-owned typed contracts")
    if not isinstance(records, Sequence) or isinstance(records, (str, bytes, bytearray)):
        raise ValueError("records must be a bounded sequence")
    if not 1 <= len(records) <= profile.maximum_records:
        raise ValueError("record count is outside the model profile")
    identity = (profile.provider_model_id, profile.region, profile.rate_tier)
    if identity != (rates.provider_model_id, rates.region, rates.rate_tier):
        raise ValueError("rate identity does not match model profile")

    lines: list[bytes] = []
    record_ids: list[str] = []
    caps: list[int] = []
    seen: set[str] = set()
    counter = [0]
    for record in records:
        if not isinstance(record, Mapping) or set(record) != {"recordId", "modelInput"}:
            raise ValueError("each record must contain exactly recordId and modelInput")
        record_id = _text("recordId", record["recordId"])
        if record_id in seen:
            raise ValueError("recordId values must be unique")
        seen.add(record_id)
        model_input = _validated_json(record["modelInput"], depth=1, counter=counter)
        if not isinstance(model_input, dict):
            raise ValueError("modelInput must be an object")
        cap = model_input.get(profile.output_cap_field)
        if isinstance(cap, bool) or not isinstance(cap, int) or not 1 <= cap <= profile.maximum_output_tokens_per_record:
            raise ValueError("record output cap is missing or outside the profile")
        canonical_record = {"modelInput": model_input, "recordId": record_id}
        lines.append((_canonical(canonical_record) + "\n").encode("ascii"))
        record_ids.append(record_id)
        caps.append(cap)

    jsonl = b"".join(lines)
    if len(jsonl) > _MAX_JSONL_BYTES:
        raise ValueError("canonical workload is too large")
    input_ceiling = len(records) * profile.context_tokens
    output_ceiling = sum(caps)
    with localcontext() as context:
        context.prec = 80
        total = (
            Decimal(input_ceiling) * Decimal(rates.input_usd_per_million_tokens)
            + Decimal(output_ceiling) * Decimal(rates.output_usd_per_million_tokens)
        ) / Decimal(1_000_000) + Decimal(rates.fixed_request_usd)
        cents = int((total * 100).to_integral_value(rounding=ROUND_CEILING))
    if cents > _MAX_CENTS:
        raise ValueError("reservation cents overflow")
    if cents == 0 and (rates.paid or any(Decimal(value) != 0 for value in (
        rates.input_usd_per_million_tokens,
        rates.output_usd_per_million_tokens,
        rates.fixed_request_usd,
    ))):
        raise ValueError("zero reservation requires an explicitly non-paid zero rate")
    exact = format(total, "f")
    if "." in exact:
        exact = exact.rstrip("0").rstrip(".")
    bound = BedrockBatchWorkloadBound(
        contract_version="bedrock-batch-workload-bound-v1",
        workload_byte_length=len(jsonl),
        workload_sha256=_sha256(jsonl),
        record_count=len(records),
        ordered_record_ids_sha256=_sha256(_canonical(record_ids).encode()),
        output_caps_sha256=_sha256(_canonical(caps).encode()),
        profile_json=profile.canonical_json,
        profile_digest=profile.profile_digest,
        rates_json=rates.canonical_json,
        rates_digest=rates.rate_digest,
        input_token_ceiling=input_ceiling,
        output_token_ceiling=output_ceiling,
        exact_unrounded_usd=exact,
        reservation_cents=cents,
    )
    return bytes(jsonl), bound


__all__ = [
    "BedrockBatchModelProfile",
    "BedrockBatchRateSnapshot",
    "BedrockBatchWorkloadBound",
    "materialize_bedrock_batch_workload",
]
