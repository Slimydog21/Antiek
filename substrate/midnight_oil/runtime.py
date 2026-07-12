"""Closed production composition contract for Midnight Oil.

The JSON config contains paths and environment-variable *names*, never secret
values. Paid providers are installed only from operator-authored attestation
records whose endpoint fingerprint matches exactly; a boolean flag cannot turn
on spend.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from substrate.dispatch import (
    DispatchConfig,
    OpenAICompatProvider,
    TierConfig,
    register_provider,
)
from substrate.engagement_spine.store import FileEngagementStore

from .durable_job import DurableJobStore
from .job_store import DurableOwnerJobStore
from .operation_queue import DurableOperationQueue
from .spend_consent import SpendConsentStore


class MidnightOilRuntimeConfigError(ValueError):
    """The production composition is incomplete or cannot be defended."""


_CONFIG_FIELDS = {
    "state_dir",
    "graph_db_path",
    "engagement_dir",
    "dispatch_config_path",
    "retrieval_kind",
    "embedding_model_name",
    "consent_active_key_id",
    "consent_signing_key_env",
    "consent_verification_key_envs",
    "provider_attestation_paths",
    "worker_lease_ms",
    "worker_poll_ms",
}
_ATTESTATION_FIELDS = {
    "schema_version",
    "provider_name",
    "base_url",
    "chat_completions_path",
    "api_key_env",
    "endpoint_sha256",
    "dispatch_config_sha256",
    "evidence_ref",
    "verified_at",
}


def _absolute_path(value: object, field: str, *, must_exist: bool = False) -> Path:
    if not isinstance(value, str) or not value.strip() or len(value) > 4096:
        raise MidnightOilRuntimeConfigError(f"{field} must be a bounded path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise MidnightOilRuntimeConfigError(f"{field} must be absolute")
    if must_exist and not path.is_file():
        raise MidnightOilRuntimeConfigError(f"{field} does not exist")
    return path


def _text(value: object, field: str, maximum: int = 256) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or len(value) > maximum
    ):
        raise MidnightOilRuntimeConfigError(f"{field} must be canonical text")
    return value


def _json_object(path: Path, field: str) -> dict[str, object]:
    try:
        if path.stat().st_size > 1_000_000:
            raise MidnightOilRuntimeConfigError(f"{field} exceeds the size limit")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except MidnightOilRuntimeConfigError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise MidnightOilRuntimeConfigError(f"{field} is unreadable") from exc
    if not isinstance(raw, dict):
        raise MidnightOilRuntimeConfigError(f"{field} must be a JSON object")
    return raw


def provider_endpoint_sha256(
    *, provider_name: str, base_url: str, chat_completions_path: str, api_key_env: str
) -> str:
    payload = json.dumps(
        {
            "provider_name": provider_name,
            "base_url": base_url.rstrip("/"),
            "chat_completions_path": chat_completions_path,
            "api_key_env": api_key_env,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(b"antiek.midnight-oil.provider-endpoint.v1\x00" + payload).hexdigest()


@dataclass(frozen=True)
class ProviderIdempotencyAttestation:
    provider_name: str
    base_url: str
    chat_completions_path: str
    api_key_env: str
    endpoint_sha256: str
    dispatch_config_sha256: str
    evidence_ref: str
    verified_at: str

    @classmethod
    def from_file(cls, path: str | Path) -> ProviderIdempotencyAttestation:
        source = _absolute_path(str(path), "provider_attestation", must_exist=True)
        raw = _json_object(source, "provider attestation")
        if set(raw) != _ATTESTATION_FIELDS:
            raise MidnightOilRuntimeConfigError("provider attestation has unknown or missing fields")
        if raw.get("schema_version") != 1:
            raise MidnightOilRuntimeConfigError("provider attestation schema is unsupported")
        provider_name = _text(raw.get("provider_name"), "provider_name")
        base_url = _text(raw.get("base_url"), "base_url", 2048).rstrip("/")
        path_value = _text(raw.get("chat_completions_path"), "chat_completions_path", 512)
        api_key_env = _text(raw.get("api_key_env"), "api_key_env")
        evidence_ref = _text(raw.get("evidence_ref"), "evidence_ref", 2048)
        verified_at = _text(raw.get("verified_at"), "verified_at", 64)
        fingerprint = _text(raw.get("endpoint_sha256"), "endpoint_sha256", 64)
        dispatch_hash = _text(
            raw.get("dispatch_config_sha256"), "dispatch_config_sha256", 64
        )
        if not base_url.startswith("https://") or not path_value.startswith("/"):
            raise MidnightOilRuntimeConfigError("attested provider endpoint must be HTTPS")
        if re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", api_key_env) is None:
            raise MidnightOilRuntimeConfigError("attested API key environment name is invalid")
        if not evidence_ref.startswith(("https://", "urn:")):
            raise MidnightOilRuntimeConfigError("attestation evidence must be an HTTPS or URN reference")
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", verified_at) is None:
            raise MidnightOilRuntimeConfigError("attestation verification time must be UTC ISO-8601")
        expected = provider_endpoint_sha256(
            provider_name=provider_name,
            base_url=base_url,
            chat_completions_path=path_value,
            api_key_env=api_key_env,
        )
        if fingerprint != expected:
            raise MidnightOilRuntimeConfigError("provider attestation endpoint fingerprint conflicts")
        if re.fullmatch(r"[0-9a-f]{64}", dispatch_hash) is None:
            raise MidnightOilRuntimeConfigError("attested dispatch config hash is invalid")
        return cls(
            provider_name=provider_name,
            base_url=base_url,
            chat_completions_path=path_value,
            api_key_env=api_key_env,
            endpoint_sha256=fingerprint,
            dispatch_config_sha256=dispatch_hash,
            evidence_ref=evidence_ref,
            verified_at=verified_at,
        )


@dataclass(frozen=True)
class MidnightOilRuntimeConfig:
    state_dir: Path
    graph_db_path: Path
    engagement_dir: Path
    dispatch_config_path: Path
    retrieval_kind: str
    embedding_model_name: str
    consent_active_key_id: str
    consent_signing_key_env: str
    consent_verification_key_envs: dict[str, str]
    provider_attestation_paths: tuple[Path, ...]
    worker_lease_ms: int
    worker_poll_ms: int

    @classmethod
    def from_file(cls, path: str | Path) -> MidnightOilRuntimeConfig:
        source = _absolute_path(str(path), "runtime_config", must_exist=True)
        raw = _json_object(source, "runtime config")
        if set(raw) != _CONFIG_FIELDS:
            raise MidnightOilRuntimeConfigError("runtime config has unknown or missing fields")
        verification = raw.get("consent_verification_key_envs")
        attestations = raw.get("provider_attestation_paths")
        if not isinstance(verification, dict) or not 1 <= len(verification) <= 16:
            raise MidnightOilRuntimeConfigError("consent verification keyring is required")
        if not isinstance(attestations, list) or not 1 <= len(attestations) <= 16:
            raise MidnightOilRuntimeConfigError("at least one provider attestation is required")
        keyring = {
            _text(key, "verification_key_id", 128): _text(value, "verification_key_env", 128)
            for key, value in verification.items()
        }
        active = _text(raw.get("consent_active_key_id"), "consent_active_key_id", 128)
        signing_env = _text(raw.get("consent_signing_key_env"), "consent_signing_key_env", 128)
        if keyring.get(active) != signing_env:
            raise MidnightOilRuntimeConfigError("active consent key must match the signing environment")
        retrieval = _text(raw.get("retrieval_kind"), "retrieval_kind", 32)
        if retrieval not in {"brute_force", "vss"}:
            raise MidnightOilRuntimeConfigError("production retrieval kind must be brute_force or vss")
        lease = raw.get("worker_lease_ms")
        poll = raw.get("worker_poll_ms")
        if type(lease) is not int or not 10_000 <= lease <= 3_600_000:
            raise MidnightOilRuntimeConfigError("worker lease must be 10s..1h")
        if type(poll) is not int or not 100 <= poll <= 60_000:
            raise MidnightOilRuntimeConfigError("worker poll must be 100ms..60s")
        return cls(
            state_dir=_absolute_path(raw.get("state_dir"), "state_dir"),
            graph_db_path=_absolute_path(raw.get("graph_db_path"), "graph_db_path"),
            engagement_dir=_absolute_path(raw.get("engagement_dir"), "engagement_dir"),
            dispatch_config_path=_absolute_path(
                raw.get("dispatch_config_path"), "dispatch_config_path", must_exist=True
            ),
            retrieval_kind=retrieval,
            embedding_model_name=_text(
                raw.get("embedding_model_name"), "embedding_model_name", 512
            ),
            consent_active_key_id=active,
            consent_signing_key_env=signing_env,
            consent_verification_key_envs=keyring,
            provider_attestation_paths=tuple(
                _absolute_path(value, "provider_attestation", must_exist=True)
                for value in attestations
            ),
            worker_lease_ms=lease,
            worker_poll_ms=poll,
        )


@dataclass(frozen=True)
class MidnightOilRuntimeStores:
    owner_jobs: DurableOwnerJobStore
    jobs: DurableJobStore
    consents: SpendConsentStore
    operation_queue: DurableOperationQueue
    engagement_store: FileEngagementStore


def build_runtime_stores(config: MidnightOilRuntimeConfig) -> MidnightOilRuntimeStores:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.engagement_dir.mkdir(parents=True, exist_ok=True)
    return MidnightOilRuntimeStores(
        owner_jobs=DurableOwnerJobStore(config.state_dir / "owner-jobs.duckdb"),
        jobs=DurableJobStore(config.state_dir / "job-details.sqlite3"),
        consents=SpendConsentStore(config.state_dir / "spend-consents.sqlite3"),
        operation_queue=DurableOperationQueue(config.state_dir / "operations.sqlite3"),
        engagement_store=FileEngagementStore(config.engagement_dir),
    )


def _decode_key(value: str, field: str) -> bytes:
    if not value or len(value) > 4096:
        raise MidnightOilRuntimeConfigError(f"{field} has an invalid encoded length")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, TypeError, binascii.Error) as exc:
        raise MidnightOilRuntimeConfigError(f"{field} is not base64url") from exc
    if len(decoded) < 32:
        raise MidnightOilRuntimeConfigError(f"{field} must decode to at least 256 bits")
    return decoded


def load_consent_keyring(
    config: MidnightOilRuntimeConfig, environ: Mapping[str, str]
) -> tuple[bytes, dict[str, bytes]]:
    keys: dict[str, bytes] = {}
    for key_id, env_name in config.consent_verification_key_envs.items():
        raw = environ.get(env_name, "")
        if not raw:
            raise MidnightOilRuntimeConfigError("a consent verification key is missing")
        keys[key_id] = _decode_key(raw, "consent verification key")
    signing = keys[config.consent_active_key_id]
    return signing, keys


def install_attested_providers(
    config: MidnightOilRuntimeConfig, environ: Mapping[str, str]
) -> tuple[ProviderIdempotencyAttestation, ...]:
    admitted: list[ProviderIdempotencyAttestation] = []
    names: set[str] = set()
    for path in config.provider_attestation_paths:
        attestation = ProviderIdempotencyAttestation.from_file(path)
        if attestation.provider_name in names:
            raise MidnightOilRuntimeConfigError("provider attestation names must be unique")
        if not environ.get(attestation.api_key_env, ""):
            raise MidnightOilRuntimeConfigError("an attested provider API key is missing")
        names.add(attestation.provider_name)
        admitted.append(attestation)
    dispatch_config = DispatchConfig.from_yaml(config.dispatch_config_path)
    dispatch_hash = hashlib.sha256(config.dispatch_config_path.read_bytes()).hexdigest()
    if any(item.dispatch_config_sha256 != dispatch_hash for item in admitted):
        raise MidnightOilRuntimeConfigError(
            "provider attestation dispatch configuration conflicts"
        )
    configured: set[str] = set()
    for configured_tier in dispatch_config.tiers.values():
        tier: TierConfig | None = configured_tier
        while tier is not None:
            if tier.provider is not None:
                configured.add(tier.provider)
            tier = tier.fallback
    if not names & configured:
        raise MidnightOilRuntimeConfigError(
            "no attested provider is reachable from the dispatch configuration"
        )
    for attestation in admitted:
        register_provider(
            OpenAICompatProvider(
                name=attestation.provider_name,
                base_url=attestation.base_url,
                chat_completions_path=attestation.chat_completions_path,
                api_key_env=attestation.api_key_env,
                idempotency_guaranteed=True,
            )
        )
    return tuple(admitted)


__all__ = [
    "MidnightOilRuntimeConfig",
    "MidnightOilRuntimeConfigError",
    "MidnightOilRuntimeStores",
    "ProviderIdempotencyAttestation",
    "build_runtime_stores",
    "install_attested_providers",
    "load_consent_keyring",
    "provider_endpoint_sha256",
]
