"""One HTTP-facing authority for exact-command interactive research quotes."""

from __future__ import annotations

import secrets
import time

from fastapi import HTTPException, Request

from interfaces.research.api.settings_budget import (
    _authenticated_quote_account,
    _dispatch_config_path,
    _load_research_quote_keyring,
)
from substrate.dispatch.research_quote import (
    ResearchQuoteInvalid,
    ResearchQuoteReceipt,
    ResearchRouteManifest,
    build_research_route_manifest,
    issue_research_quote,
    verify_research_quote,
)
from substrate.dispatch.router import DispatchConfig


def issue_exact_research_quote(
    *,
    request: Request,
    command: str,
    research_tier: str,
    approved_run_ceiling_usd: float,
    selected_driver_role: str | None = None,
    selected_driver_provider: str | None = None,
    selected_driver_model: str | None = None,
    selected_driver_pricing_fingerprint: str | None = None,
) -> tuple[str, ResearchQuoteReceipt, ResearchRouteManifest]:
    account_id = _authenticated_quote_account(request)
    try:
        active_key_id, signing_key, _ = _load_research_quote_keyring()
        manifest = build_research_route_manifest(
            DispatchConfig.from_yaml(_dispatch_config_path())
        )
        if selected_driver_provider is not None:
            ready = getattr(request.app.state, "registered_providers", None)
            if not isinstance(ready, (set, frozenset, list, tuple)) or (
                selected_driver_provider not in ready
            ):
                raise ResearchQuoteInvalid(
                    "selected research driver provider is not boot-ready"
                )
        issued_at_ms = time.time_ns() // 1_000_000
        token, receipt = issue_research_quote(
            account_id=account_id,
            prompt=command,
            research_tier=research_tier,
            manifest=manifest,
            approved_run_ceiling_usd=approved_run_ceiling_usd,
            issued_at_ms=issued_at_ms,
            expires_at_ms=issued_at_ms + 5 * 60 * 1000,
            nonce=secrets.token_urlsafe(24),
            key_id=active_key_id,
            signing_key=signing_key,
            selected_driver_role=selected_driver_role,
            selected_driver_provider=selected_driver_provider,
            selected_driver_model=selected_driver_model,
            selected_driver_pricing_fingerprint=(
                selected_driver_pricing_fingerprint
            ),
        )
    except ResearchQuoteInvalid as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return token, receipt, manifest


def verify_exact_research_quote(
    *,
    request: Request,
    token: str | None,
    command: str,
    research_tier: str,
    approved_run_ceiling_usd: float,
    selected_driver_role: str | None = None,
    selected_driver_provider: str | None = None,
    selected_driver_model: str | None = None,
    selected_driver_pricing_fingerprint: str | None = None,
    allow_expired: bool = False,
) -> tuple[ResearchQuoteReceipt, ResearchRouteManifest]:
    account_id = _authenticated_quote_account(request)
    if token is None:
        raise HTTPException(status_code=422, detail="research quote token required")
    try:
        _, _, verification_keys = _load_research_quote_keyring()
        manifest = build_research_route_manifest(
            DispatchConfig.from_yaml(_dispatch_config_path())
        )
        if selected_driver_provider is not None:
            ready = getattr(request.app.state, "registered_providers", None)
            if not isinstance(ready, (set, frozenset, list, tuple)) or (
                selected_driver_provider not in ready
            ):
                raise ResearchQuoteInvalid(
                    "selected research driver provider is not boot-ready"
                )
        receipt = verify_research_quote(
            token,
            account_id=account_id,
            prompt=command,
            research_tier=research_tier,
            manifest=manifest,
            approved_run_ceiling_usd=approved_run_ceiling_usd,
            now_ms=time.time_ns() // 1_000_000,
            verification_keys=verification_keys,
            selected_driver_role=selected_driver_role,
            selected_driver_provider=selected_driver_provider,
            selected_driver_model=selected_driver_model,
            selected_driver_pricing_fingerprint=(
                selected_driver_pricing_fingerprint
            ),
            allow_expired=allow_expired,
        )
    except ResearchQuoteInvalid as exc:
        raise HTTPException(status_code=403, detail="research quote invalid") from exc
    return receipt, manifest
