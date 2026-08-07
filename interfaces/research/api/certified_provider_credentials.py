"""Account onboarding for the process-wide certified dispatch providers.

This is intentionally an operator-only surface. Certified providers are global
bootstrap routes, not request-scoped user-model routes: allowing any signed-in
user to replace one would redirect every user's curated dispatch. Access
therefore defaults closed and requires the authenticated owner to exactly match
``ANTIEK_OPERATOR_USER_ID``.

Request bodies are parsed manually so validation errors never reflect an API key.
Responses and inventory contain metadata only.
"""

from __future__ import annotations

import os
import threading
from typing import Final

from fastapi import APIRouter, FastAPI, HTTPException, Request
from pydantic import BaseModel

from runtime.byok.store import (
    CredentialIntegrityError,
    CredentialMetadata,
    delete_credential,
    list_credentials,
    store_credential,
)
from substrate.dispatch.providers.bootstrap import register_default_providers

from .settings_models_admin import request_owner_user_id

_OPERATOR_ENV: Final = "ANTIEK_OPERATOR_USER_ID"
_MIN_KEY_LEN: Final = 8
_MAX_KEY_LEN: Final = 512
_REPLACE_LOCK = threading.RLock()

# Handles are the exact pipeline suffixes consumed by byok_key_source.py.
# Z.ai has two registered policy adapters that share one credential.
_HANDLE_TO_PROVIDERS: Final[dict[str, tuple[str, ...]]] = {
    "anthropic": ("anthropic",),
    "deepseek": ("deepseek",),
    "hermes": ("hermes",),
    "openrouter": ("openrouter",),
    "xiaomi": ("xiaomi",),
    "zai": ("zai", "zai_reasoning"),
}


class CertifiedProviderCredentialRow(BaseModel):
    provider_handle: str
    key_present: bool


class CertifiedProviderCredentialInventory(BaseModel):
    providers: list[CertifiedProviderCredentialRow]
    byot_only: bool


class CertifiedProviderCredentialResult(BaseModel):
    provider_handle: str
    key_present: bool
    registered_providers: list[str]
    source: str


certified_provider_credentials_router = APIRouter(
    prefix="/settings/providers/certified", tags=["settings"]
)


def _operator_owner(request: Request) -> str:
    owner = request_owner_user_id(request)
    configured = os.environ.get(_OPERATOR_ENV, "")
    if not configured or owner != configured:
        raise HTTPException(
            status_code=403,
            detail="certified provider credential access denied",
        )
    return owner


def _pipeline_kind(handle: str) -> str:
    return f"provider:{handle}"


def _matching_credentials(
    metadata: list[CredentialMetadata],
    handle: str,
) -> list[CredentialMetadata]:
    # Match exactly what the process-wide resolver sees. Legacy records without
    # an owner are included so an operator replacement removes ambiguity.
    wanted = _pipeline_kind(handle)
    return [item for item in metadata if item.pipeline_kind == wanted]


def _parse_key(payload: object) -> str:
    if not isinstance(payload, dict) or set(payload) != {"api_key"}:
        raise HTTPException(
            status_code=400,
            detail="invalid certified provider credential request",
        )
    key = payload.get("api_key")
    if not isinstance(key, str) or not (_MIN_KEY_LEN <= len(key) <= _MAX_KEY_LEN):
        raise HTTPException(
            status_code=400,
            detail="invalid certified provider credential request",
        )
    return key


@certified_provider_credentials_router.get(
    "",
    response_model=CertifiedProviderCredentialInventory,
)
def get_certified_provider_credentials(
    request: Request,
) -> CertifiedProviderCredentialInventory:
    _operator_owner(request)
    try:
        metadata = list_credentials()
    except (CredentialIntegrityError, OSError, PermissionError) as exc:
        raise HTTPException(
            status_code=503, detail="certified provider credential inventory unavailable"
        ) from exc
    return CertifiedProviderCredentialInventory(
        providers=[
            CertifiedProviderCredentialRow(
                provider_handle=handle,
                key_present=bool(_matching_credentials(metadata, handle)),
            )
            for handle in _HANDLE_TO_PROVIDERS
        ],
        byot_only=os.environ.get("ANTIEK_BYOT_ONLY", "").strip().lower()
        in {"1", "true", "yes", "on"},
    )


@certified_provider_credentials_router.put(
    "/{provider_handle}",
    response_model=CertifiedProviderCredentialResult,
    status_code=201,
)
async def put_certified_provider_credential(
    provider_handle: str,
    request: Request,
) -> CertifiedProviderCredentialResult:
    owner = _operator_owner(request)
    providers = _HANDLE_TO_PROVIDERS.get(provider_handle)
    if providers is None:
        raise HTTPException(status_code=404, detail="unknown certified provider")
    try:
        payload = await request.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="invalid certified provider credential request",
        ) from exc
    key = _parse_key(payload)

    with _REPLACE_LOCK:
        try:
            old = _matching_credentials(list_credentials(), provider_handle)
            # Persist the replacement before touching the old ciphertext. A
            # failed write therefore leaves the previously working key intact.
            new_id = store_credential(
                owner,
                key,
                pipeline_kind=_pipeline_kind(provider_handle),
                owner_user_id=owner,
            )
            for item in old:
                delete_credential(item.cred_id)
            current = _matching_credentials(list_credentials(), provider_handle)
            if len(current) != 1 or current[0].cred_id != new_id:
                raise CredentialIntegrityError(
                    "credential replacement did not establish singular authority"
                )
            registered = register_default_providers(
                quiet=True,
                only=list(providers),
            )
            if registered != set(providers):
                raise RuntimeError("certified provider registration incomplete")
        except (
            CredentialIntegrityError,
            OSError,
            PermissionError,
            RuntimeError,
            ValueError,
        ) as exc:
            raise HTTPException(
                status_code=503,
                detail="certified provider credential update unavailable",
            ) from exc

        seam = getattr(request.app.state, "registered_providers", None)
        if isinstance(seam, set):
            seam.update(registered)
        return CertifiedProviderCredentialResult(
            provider_handle=provider_handle,
            key_present=True,
            registered_providers=sorted(registered),
            source="encrypted_byok_store",
        )


def register_certified_provider_credential_routes(app: FastAPI) -> None:
    app.include_router(certified_provider_credentials_router)


__all__ = [
    "certified_provider_credentials_router",
    "register_certified_provider_credential_routes",
]
