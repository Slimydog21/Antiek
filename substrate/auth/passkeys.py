"""Passkey ceremonies and the single-operator credential store.

Antiek is deliberately single-operator until G7.  This module keeps the
WebAuthn boundary equally small: discoverable credentials for one operator,
short-lived one-shot challenges in process memory, and an atomic JSON store
outside the repository.  The FastAPI service is already constrained to one
worker by the DuckDB single-writer invariant, so a process-local challenge
registry is the honest deployment model (a restart merely asks the operator
to touch Face ID / Touch ID again).

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
from dataclasses import asdict, dataclass
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
_STORE_VERSION = 1
_OPERATOR_USER_ID = b"antiek-single-operator"


class PasskeyError(Exception):
    """A closed, user-safe passkey failure."""


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


@dataclass(frozen=True)
class _Ceremony:
    kind: Literal["registration", "authentication"]
    challenge: bytes
    expires_at: float


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


def _read_credentials_unlocked() -> list[PasskeyCredential]:
    path = passkey_store_path()
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("version") != _STORE_VERSION:
            raise PasskeyError("The passkey store version is not supported.")
        return [
            PasskeyCredential(
                credential_id=item["credential_id"],
                public_key=item["public_key"],
                sign_count=int(item["sign_count"]),
                transports=tuple(item.get("transports", ())),
                device_type=item.get("device_type", "unknown"),
                backed_up=bool(item.get("backed_up", False)),
                label=item.get("label", "Passkey"),
                created_at=int(item["created_at"]),
                last_used_at=item.get("last_used_at"),
            )
            for item in payload.get("credentials", [])
        ]
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
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


def _put_ceremony(kind: Literal["registration", "authentication"], challenge: bytes) -> str:
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
        )
    return ceremony_id


def _consume_ceremony(ceremony_id: str, kind: Literal["registration", "authentication"]) -> bytes:
    with _ceremony_lock:
        ceremony = _ceremonies.pop(ceremony_id, None)
    if ceremony is None or ceremony.kind != kind or ceremony.expires_at <= time.monotonic():
        raise PasskeyError("This unlock request expired. Try again.")
    return ceremony.challenge


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


def registration_options(*, email: str) -> dict[str, Any]:
    credentials = list_credentials()
    options = generate_registration_options(
        rp_id=_rp_id(),
        rp_name="Antiek",
        user_id=_OPERATOR_USER_ID,
        user_name=email,
        user_display_name="Antiek operator",
        timeout=PASSKEY_CHALLENGE_TTL_SECONDS * 1000,
        exclude_credentials=_descriptors(credentials),
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    body = cast(dict[str, Any], json.loads(options_to_json(options)))
    body["ceremony_id"] = _put_ceremony("registration", options.challenge)
    return body


def complete_registration(*, ceremony_id: str, credential: dict[str, Any], label: str) -> PasskeyCredential:
    challenge = _consume_ceremony(ceremony_id, "registration")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=challenge,
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
    )
    with _store_lock:
        existing = _read_credentials_unlocked()
        existing = [item for item in existing if item.credential_id != record.credential_id]
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
    challenge = _consume_ceremony(ceremony_id, "authentication")
    credential_id = credential.get("id")
    if not isinstance(credential_id, str) or not credential_id:
        raise PasskeyError("That passkey response was incomplete.")
    with _store_lock:
        credentials = _read_credentials_unlocked()
        match = next((item for item in credentials if item.credential_id == credential_id), None)
        if match is None:
            raise PasskeyError("This passkey is not registered with Antiek.")
        try:
            verified = verify_authentication_response(
                credential=credential,
                expected_challenge=challenge,
                expected_rp_id=_rp_id(),
                expected_origin=_origins(),
                credential_public_key=_unb64(match.public_key),
                credential_current_sign_count=match.sign_count,
                require_user_verification=True,
            )
        except Exception as exc:
            raise PasskeyError("Antiek could not verify that passkey. Try again.") from exc
        updated = PasskeyCredential(
            **{
                **asdict(match),
                "sign_count": verified.new_sign_count,
                "device_type": str(verified.credential_device_type.value),
                "backed_up": verified.credential_backed_up,
                "last_used_at": int(time.time()),
            }
        )
        credentials = [updated if item.credential_id == match.credential_id else item for item in credentials]
        _write_credentials_unlocked(credentials)
    return updated
