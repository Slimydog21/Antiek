"""Explicit composition-root dependencies for private Substack review signing."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re
import secrets
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from substrate.engagement_spine.store import EngagementStore, FileEngagementStore

SUBSTACK_AUTH_ACTIVE_KEY_ID_ENV = "ANTIEK_SUBSTACK_AUTH_ACTIVE_KEY_ID"
SUBSTACK_AUTH_SIGNING_KEY_ENV_ENV = "ANTIEK_SUBSTACK_AUTH_SIGNING_KEY_ENV"
SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_ENV = "ANTIEK_SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_JSON"


def system_clock_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class SubstackAuthorizationApiDependencies:
    engagement_store: EngagementStore
    active_key_id: str
    signing_key: bytes
    verification_keys: Mapping[str, bytes]
    clock_ms: Callable[[], int] = system_clock_ms
    token_hex: Callable[[int], str] = secrets.token_hex
    test_mode: bool = False

    def __post_init__(self) -> None:
        if (
            not self.active_key_id
            or self.active_key_id != self.active_key_id.strip()
            or len(self.active_key_id) > 128
        ):
            raise ValueError("Substack authorization active key id must be canonical")
        if type(self.signing_key) is not bytes or len(self.signing_key) < 32:
            raise ValueError("Substack authorization signing key must be at least 256 bits")
        for key_id, key in self.verification_keys.items():
            if (
                type(key_id) is not str
                or not key_id
                or key_id != key_id.strip()
                or len(key_id) > 128
                or type(key) is not bytes
                or len(key) < 32
            ):
                raise ValueError("Substack authorization verification keyring is invalid")
        if self.verification_keys.get(self.active_key_id) != self.signing_key:
            raise ValueError("Substack authorization active key is absent from its keyring")
        if not self.test_mode and (
            type(self.engagement_store) is not FileEngagementStore
            or self.clock_ms is not system_clock_ms
            or self.token_hex is not secrets.token_hex
        ):
            raise ValueError(
                "production Substack authorization requires durable trusted dependencies"
            )


def _decode_key(value: str) -> bytes:
    if not value or len(value) > 4_096:
        raise ValueError("Substack authorization key has an invalid encoded length")
    try:
        decoded = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
    except (ValueError, TypeError, binascii.Error) as exc:
        raise ValueError("Substack authorization key must be base64url") from exc
    if len(decoded) < 32:
        raise ValueError("Substack authorization key must decode to at least 256 bits")
    return decoded


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Substack authorization keyring contains duplicate keys")
        result[key] = value
    return result


def build_substack_authorization_dependencies(
    *,
    engagement_store: EngagementStore,
    environ: Mapping[str, str],
    forbidden_key_envs: frozenset[str] = frozenset(),
    forbidden_keys: tuple[bytes, ...] = (),
) -> SubstackAuthorizationApiDependencies | None:
    """Load a purpose-specific keyring; absent is closed, partial is fatal."""

    active = environ.get(SUBSTACK_AUTH_ACTIVE_KEY_ID_ENV, "").strip()
    signing_env = environ.get(SUBSTACK_AUTH_SIGNING_KEY_ENV_ENV, "").strip()
    keyring_json = environ.get(SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_ENV, "").strip()
    if not any((active, signing_env, keyring_json)):
        return None
    if not all((active, signing_env, keyring_json)):
        raise ValueError("Substack authorization keyring configuration is incomplete")
    try:
        raw_keyring = json.loads(keyring_json, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ValueError("Substack authorization keyring configuration is invalid") from exc
    if not isinstance(raw_keyring, dict) or not 1 <= len(raw_keyring) <= 16:
        raise ValueError("Substack authorization verification keyring is invalid")
    key_envs: dict[str, str] = {}
    for key_id, env_name in raw_keyring.items():
        if (
            type(key_id) is not str
            or re.fullmatch(r"[A-Za-z0-9._-]{1,128}", key_id) is None
            or type(env_name) is not str
            or re.fullmatch(r"[A-Z][A-Z0-9_]{2,127}", env_name) is None
        ):
            raise ValueError("Substack authorization verification keyring is invalid")
        key_envs[key_id] = env_name
    if key_envs.get(active) != signing_env:
        raise ValueError("Substack authorization active key does not match its keyring")
    if set(key_envs.values()) & forbidden_key_envs:
        raise ValueError("Substack authorization keys must not reuse consent keys")
    keys: dict[str, bytes] = {}
    for key_id, env_name in key_envs.items():
        encoded = environ.get(env_name, "")
        if not encoded:
            raise ValueError("A Substack authorization verification key is missing")
        keys[key_id] = _decode_key(encoded)
    if any(
        hmac.compare_digest(substack_key, forbidden_key)
        for substack_key in keys.values()
        for forbidden_key in forbidden_keys
    ):
        raise ValueError("Substack authorization keys must not reuse consent key material")
    return SubstackAuthorizationApiDependencies(
        engagement_store=engagement_store,
        active_key_id=active,
        signing_key=keys[active],
        verification_keys=keys,
    )


__all__ = [
    "SUBSTACK_AUTH_ACTIVE_KEY_ID_ENV",
    "SUBSTACK_AUTH_SIGNING_KEY_ENV_ENV",
    "SUBSTACK_AUTH_VERIFICATION_KEY_ENVS_ENV",
    "SubstackAuthorizationApiDependencies",
    "build_substack_authorization_dependencies",
    "system_clock_ms",
]
