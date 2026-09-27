"""Passkey ceremonies and account-bound public credentials.

This module keeps the WebAuthn boundary small: discoverable credentials,
short-lived one-shot challenges in process memory, and an atomic JSON store
outside the repository. The FastAPI service is constrained to one worker by
the DuckDB single-writer invariant, so a restart merely requires a new
challenge.

Credential private keys never reach Antiek.  The store contains only public
keys, counters, transports, and operator-chosen labels.  Registration is
available only from an existing authenticated session; email remains the
bootstrap and recovery proof.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import threading
import time
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Literal, cast

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorTransport,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

PASSKEY_CHALLENGE_TTL_SECONDS = 5 * 60
_STORE_VERSION = 2


class PasskeyError(Exception):
    """A closed, user-safe passkey failure."""


@dataclass(frozen=True)
class PasskeySubjectBinding:
    provider: str
    subject: str
    owner_user_id: str


@dataclass(frozen=True)
class PasskeyCredential:
    credential_id: str
    public_key: str
    sign_count: int
    transports: tuple[str, ...]
    device_type: str
    backed_up: bool
    label: str
    created_at: int
    last_used_at: int | None = None
    binding: PasskeySubjectBinding | None = None


@dataclass(frozen=True)
class _Ceremony:
    kind: Literal["registration", "authentication"]
    challenge: bytes
    expires_at: float
    binding: PasskeySubjectBinding | None = None


_ceremonies: dict[str, _Ceremony] = {}
_ceremony_lock = threading.Lock()
_store_lock = threading.Lock()


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def passkey_store_path() -> Path:
    configured = os.environ.get("ANTIEK_PASSKEY_STORE", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / ".antiek" / "auth" / "passkeys.json"


def _validated_binding(binding: PasskeySubjectBinding) -> PasskeySubjectBinding:
    # A top-level import cycles: substrate.auth.__init__ imports this module
    # while multi_user.auth imports substrate.auth.magic_link.
    from substrate.multi_user.auth import AuthError, normalize_subject, subject_owner_id

    if not isinstance(binding, PasskeySubjectBinding):
        raise PasskeyError("The passkey account binding is invalid.")
    try:
        provider, subject = normalize_subject(binding.provider, binding.subject)
        owner = subject_owner_id(provider, subject)
    except (AuthError, AttributeError, TypeError) as exc:
        raise PasskeyError("The passkey account binding is invalid.") from exc
    if (
        provider != "magic_link"
        or provider != binding.provider
        or subject != binding.subject
        or owner != binding.owner_user_id
    ):
        raise PasskeyError("The passkey account binding is invalid.")
    return binding


def _read_credentials_unlocked() -> list[PasskeyCredential]:
    path = passkey_store_path()
    try:
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid passkey store")
        version = payload.get("version")
        if type(version) is not int or version not in (1, _STORE_VERSION):
            raise PasskeyError("The passkey store version is not supported.")
        items = payload.get("credentials")
        if not isinstance(items, list):
            raise ValueError("invalid passkey credentials")
        credentials: list[PasskeyCredential] = []
        seen: set[str] = set()
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("invalid passkey credential")
            credential_id = item["credential_id"]
            public_key = item["public_key"]
            sign_count = item["sign_count"]
            created_at = item["created_at"]
            transports = item.get("transports", [])
            last_used_at = item.get("last_used_at")
            if (
                not isinstance(credential_id, str) or not credential_id
                or credential_id in seen
                or not isinstance(public_key, str) or not public_key
                or type(sign_count) is not int or sign_count < 0
                or type(created_at) is not int or created_at < 0
                or not isinstance(transports, list)
                or not all(isinstance(value, str) for value in transports)
                or (last_used_at is not None and type(last_used_at) is not int)
                or not isinstance(item.get("device_type", "unknown"), str)
                or not isinstance(item.get("backed_up", False), bool)
                or not isinstance(item.get("label", "Passkey"), str)
            ):
                raise ValueError("invalid passkey credential")
            seen.add(credential_id)
            binding: PasskeySubjectBinding | None = None
            if version == 1:
                if "binding" in item:
                    raise ValueError("v1 passkey cannot attest a binding")
            else:
                raw_binding = item["binding"]
                if raw_binding is not None:
                    if not isinstance(raw_binding, dict) or set(raw_binding) != {
                        "provider", "subject", "owner_user_id",
                    }:
                        raise ValueError("invalid passkey binding")
                    binding = _validated_binding(PasskeySubjectBinding(**raw_binding))
            credentials.append(PasskeyCredential(
                credential_id=credential_id,
                public_key=public_key,
                sign_count=sign_count,
                transports=tuple(transports),
                device_type=item.get("device_type", "unknown"),
                backed_up=item.get("backed_up", False),
                label=item.get("label", "Passkey"),
                created_at=created_at,
                last_used_at=last_used_at,
                binding=binding,
            ))
        return credentials
    except (KeyError, TypeError, ValueError, json.JSONDecodeError, UnicodeError, OSError) as exc:
        raise PasskeyError("The passkey store is unreadable.") from exc


def list_credentials() -> list[PasskeyCredential]:
    with _store_lock:
        return _read_credentials_unlocked()


def delete_credential(credential_id: str) -> bool:
    """Remove one public credential, returning whether it existed."""
    with _store_lock:
        credentials = _read_credentials_unlocked()
        remaining = [item for item in credentials if item.credential_id != credential_id]
        if len(remaining) == len(credentials):
            return False
        _write_credentials_unlocked(remaining)
        return True


def delete_bound_credential(credential_id: str, owner_user_id: str) -> bool:
    """Authorize and delete one bound credential in the same store lock."""

    with _store_lock:
        credentials = _read_credentials_unlocked()
        match = next((item for item in credentials if item.credential_id == credential_id), None)
        if match is None or match.binding is None or match.binding.owner_user_id != owner_user_id:
            return False
        _write_credentials_unlocked([
            item for item in credentials if item.credential_id != credential_id
        ])
        return True


def _write_credentials_unlocked(credentials: list[PasskeyCredential]) -> None:
    path = passkey_store_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(f".tmp-{secrets.token_hex(6)}")
    payload = {
        "version": _STORE_VERSION,
        "credentials": [
            {**asdict(item), "transports": list(item.transports)}
            for item in credentials
        ],
    }
    try:
        with temp.open("w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.chmod(0o600)
        os.replace(temp, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        temp.unlink(missing_ok=True)


def _put_ceremony(
    kind: Literal["registration", "authentication"], challenge: bytes,
    *, binding: PasskeySubjectBinding | None = None,
) -> str:
    ceremony_id = secrets.token_urlsafe(24)
    now = time.monotonic()
    with _ceremony_lock:
        expired = [key for key, item in _ceremonies.items() if item.expires_at <= now]
        for key in expired:
            _ceremonies.pop(key, None)
        if len(_ceremonies) >= 256:
            oldest = min(_ceremonies, key=lambda key: _ceremonies[key].expires_at)
            _ceremonies.pop(oldest, None)
        _ceremonies[ceremony_id] = _Ceremony(
            kind=kind,
            challenge=challenge,
            expires_at=now + PASSKEY_CHALLENGE_TTL_SECONDS,
            binding=binding,
        )
    return ceremony_id


def _consume_ceremony(
    ceremony_id: str, kind: Literal["registration", "authentication"],
) -> _Ceremony:
    with _ceremony_lock:
        ceremony = _ceremonies.pop(ceremony_id, None)
    if ceremony is None or ceremony.kind != kind or ceremony.expires_at <= time.monotonic():
        raise PasskeyError("This unlock request expired. Try again.")
    return ceremony


def _rp_id() -> str:
    return os.environ.get("ANTIEK_WEBAUTHN_RP_ID", "antiek.ai").strip() or "antiek.ai"


def _origins() -> list[str]:
    configured = os.environ.get("ANTIEK_WEBAUTHN_ORIGINS", "").strip()
    if configured:
        return [value.strip().rstrip("/") for value in configured.split(",") if value.strip()]
    # Apex + www: Cloudflare Pages serves the same SPA on both, and
    # WebAuthn verification compares the EXACT page origin, so a
    # credential registered from either host must verify from both.
    # rp_id stays "antiek.ai" (a registrable-domain rpId covers its
    # subdomains, www included).
    return ["https://antiek.ai", "https://www.antiek.ai"]


def _descriptors(credentials: list[PasskeyCredential]) -> list[PublicKeyCredentialDescriptor]:
    descriptors: list[PublicKeyCredentialDescriptor] = []
    for credential in credentials:
        transports = []
        for value in credential.transports:
            try:
                transports.append(AuthenticatorTransport(value))
            except ValueError:
                continue
        descriptors.append(
            PublicKeyCredentialDescriptor(
                id=_unb64(credential.credential_id),
                transports=transports or None,
            )
        )
    return descriptors


def registration_options(*, binding: PasskeySubjectBinding) -> dict[str, Any]:
    _validated_binding(binding)
    credentials = [
        item for item in list_credentials()
        if item.binding is not None and item.binding.owner_user_id == binding.owner_user_id
    ]
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name="Antiek",
        user_id=binding.owner_user_id.encode("ascii"),
        user_name=binding.subject,
        user_display_name=binding.subject,
        timeout=PASSKEY_CHALLENGE_TTL_SECONDS * 1000,
        exclude_credentials=_descriptors(credentials),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    body = cast(dict[str, Any], json.loads(options_to_json(options)))
    body["ceremony_id"] = _put_ceremony(
        "registration", options.challenge, binding=binding,
    )
    return body


def complete_registration(
    *, ceremony_id: str, credential: dict[str, Any], label: str,
    binding: PasskeySubjectBinding,
) -> PasskeyCredential:
    ceremony = _consume_ceremony(ceremony_id, "registration")
    _validated_binding(binding)
    if ceremony.binding != binding:
        raise PasskeyError("The passkey account changed. Start registration again.")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=ceremony.challenge,
            expected_rp_id=_rp_id(),
            expected_origin=_origins(),
            require_user_verification=True,
        )
    except Exception as exc:  # library exposes several format-specific errors
        raise PasskeyError("That passkey could not be verified. Try again.") from exc

    response = credential.get("response") or {}
    transports = tuple(value for value in response.get("transports", []) if isinstance(value, str))
    now = int(time.time())
    record = PasskeyCredential(
        credential_id=_b64(verified.credential_id),
        public_key=_b64(verified.credential_public_key),
        sign_count=verified.sign_count,
        transports=transports,
        device_type=str(verified.credential_device_type.value),
        backed_up=verified.credential_backed_up,
        label=label.strip()[:80] or "Passkey",
        created_at=now,
        binding=binding,
    )
    with _store_lock:
        existing = _read_credentials_unlocked()
        if any(item.credential_id == record.credential_id for item in existing):
            raise PasskeyError("This passkey is already registered.")
        existing.append(record)
        _write_credentials_unlocked(existing)
    return record


def authentication_options() -> dict[str, Any]:
    # Empty allowCredentials enables discoverable credentials and Apple's
    # nearby-device QR flow.  Verification still rejects every key that is not
    # in Antiek's own store.
    options = generate_authentication_options(
        rp_id=_rp_id(),
        timeout=PASSKEY_CHALLENGE_TTL_SECONDS * 1000,
        allow_credentials=[],
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    body = cast(dict[str, Any], json.loads(options_to_json(options)))
    body["ceremony_id"] = _put_ceremony("authentication", options.challenge)
    return body


def complete_authentication(*, ceremony_id: str, credential: dict[str, Any]) -> PasskeyCredential:
    ceremony = _consume_ceremony(ceremony_id, "authentication")
    credential_id = credential.get("id")
    if not isinstance(credential_id, str) or not credential_id:
        raise PasskeyError("That passkey response was incomplete.")
    with _store_lock:
        credentials = _read_credentials_unlocked()
        match = next((item for item in credentials if item.credential_id == credential_id), None)
        if match is None:
            raise PasskeyError("This passkey is not registered with Antiek.")
        if match.binding is None:
            raise PasskeyError("This passkey needs to be enrolled again.")
        _validated_binding(match.binding)
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=ceremony.challenge,
                expected_rp_id=_rp_id(),
                expected_origin=_origins(),
                credential_public_key=_unb64(match.public_key),
                credential_current_sign_count=match.sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            raise PasskeyError("Antiek could not verify that passkey. Try again.") from exc
        updated = replace(
            match,
            sign_count=verified.new_sign_count,
            device_type=str(verified.credential_device_type.value),
            backed_up=verified.credential_backed_up,
            last_used_at=int(time.time()),
        )
        credentials = [updated if item.credential_id == match.credential_id else item for item in credentials]
        _write_credentials_unlocked(credentials)
    return updated
