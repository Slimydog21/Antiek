"""Exact owner-BYOT dispatch for request-scoped AI actions."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from contextlib import AbstractContextManager
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Request

from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.account_memory_identity import (
    FORBIDDEN_OWNERS,
    OPERATOR_STORAGE_SENTINEL,
    derive_owner_from_verified_email,
)
from runtime.research_runner.byot_provider_catalog import (
    get_model_variant,
    get_provider_preset,
)
from runtime.research_runner.provider_route_authority import canonical_provider_endpoint
from substrate.byot_usage.actions import (
    ApprovedOwnerRoute,
    AttemptProposal,
    FinalSendFacts,
    OwnerActionRef,
    VerifiedAttemptFacts,
)
from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict
from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.request_authority import (
    DispatchAuthority,
    DispatchAuthorityRefused,
    OwnerByotPayer,
    OwnerCredentialBinding,
    OwnerCredentialCandidate,
    PayerPolicy,
    ProposedRoute,
    RequestedModel,
    freeze_dispatch_authority,
)
from substrate.dispatch.router import (
    DispatchConfig,
    DispatchResult,
    TierPricing,
    dispatch,
)

_AUTHENTICATED_METHODS = frozenset({
    "antiek_session_cookie",
    "cloudflare_access_email",
    "cloudflare_service_token",
    "bearer_token",
})
# Of the authenticated methods, only these prove that a HUMAN verified the address now
# carried on request.state.user_email: the session cookie is minted only after magic-link
# or passkey proof plus the operator allowlist, and Cloudflare Access asserts a verified
# identity. The other two are machine credentials, so the e-mail fallback below must not
# be reachable from them even if an address were somehow attached — a robot holding a
# service token must not be handed a person's key to spend.
_HUMAN_VERIFIED_METHODS = frozenset({"antiek_session_cookie", "cloudflare_access_email"})

_ACTION = "read.talk_to_book"


class OwnerByotDispatchUnavailable(RuntimeError):
    """The selected owner route was not executable; deliberately value-free."""


class OwnerByotOutcomeUnknown(OwnerByotDispatchUnavailable):
    """Provider I/O may have occurred; the operation must not be retried."""


def authenticated_distinct_owner(request: Request) -> str:
    """Resolve the person whose credential and budget this request may spend.

    Refusing ``__operator__`` outright is correct in principle — a storage sentinel
    shared by every operator-authenticated path cannot name whose money is being spent —
    but it is also what every production login mints, so this predicate refused 100% of
    real requests. All four owner-paid entry points (talk-to-book ask at ``books.py``,
    the book research spin, the cascade launch, and ``POST /investigations``) turned that
    refusal into a 409 or a 422, which made the whole BYOT promise — bring your key, then
    use it — unreachable while looking like a validation error.

    So fall back exactly as ``account_memory_identity`` does, through the SAME derivation
    so one person is one owner across memory and spend: a session-cookie request has had
    its address verified and allowlist-checked by the auth middleware.

    This fails closed where it should. ``cloudflare_service_token`` and ``bearer_token``
    are machine callers that carry no address (``app.py:1592`` and ``:1603`` pass none),
    so they still raise — a machine must not spend a person's key on their behalf.
    """
    state = getattr(request, "state", None)
    method = getattr(state, "auth_method", None)
    owner = getattr(state, "user_id", None)
    if method not in _AUTHENTICATED_METHODS or not isinstance(owner, str) or not owner.strip():
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")

    normalized = owner.strip()
    if normalized.casefold() not in FORBIDDEN_OWNERS:
        return normalized

    # A shared or machine identity. Only the single-operator storage sentinel, on a
    # human-verified method, can be resolved to a person; "shared", "service" and
    # "local" get no fallback, matching account_memory_identity exactly so that the two
    # predicates cannot disagree about who a person is.
    if normalized.casefold() != OPERATOR_STORAGE_SENTINEL or method not in _HUMAN_VERIFIED_METHODS:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")

    derived = derive_owner_from_verified_email(getattr(state, "user_email", None))
    if derived is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    return derived


def dispatch_talk_to_book_byot(
    *,
    app: FastAPI,
    request_owner_user_id: str,
    resource_owner_user_id: str,
    document_id: str,
    choice: models_admin.UserModelChoice,
    prompt: str,
    investigation_id: str,
    logical_operation_id: str,
    resource_authority_digest: str | None = None,
    resource_authority_revalidator: Callable[[], str] | None = None,
    resource_authority_guard: Callable[[], AbstractContextManager[str]] | None = None,
    config: DispatchConfig | None = None,
    usage_ledger: ByotUsageLedger | None = None,
    role: str = "thought_partner",
    action: str = _ACTION,
    owner_action: OwnerActionRef | None = None,
) -> tuple[DispatchResult, DispatchAuthority]:
    """Revalidate, freeze, and execute exactly one owner-paid model rung.

    The default role is ``thought_partner``: the Talk-to-Book ask path (the
    caller that relies on the default) answers through the SAME role as
    Surface E / AISidecar / Dialogue since the role unify — an owner-paid
    rung is not a second partner personality. Loop One callers pass their
    own role explicitly."""
    try:
        authority, exact_config, frozen_route = _freeze_current_authority(
            app=app,
            request_owner_user_id=request_owner_user_id,
            resource_owner_user_id=resource_owner_user_id,
            document_id=document_id,
            choice=choice,
            prompt=prompt,
            logical_operation_id=logical_operation_id,
            resource_authority_digest=resource_authority_digest,
            config=config,
            role=role,
            action=action,
        )
        rung = authority.fallback_manifest[0]
        if not isinstance(rung.credential, OwnerCredentialBinding):
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        ledger = usage_ledger or ByotUsageLedger()
        route = _approved_action_route(frozen_route)
        request_digest = _canonical_request_digest(authority, exact_config, prompt, role)
        if owner_action is not None and (
            owner_action.owner_user_id != request_owner_user_id
            or resource_authority_digest is None
            or (resource_authority_guard is None and resource_authority_revalidator is None)
        ):
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        existing = ledger.operation(request_owner_user_id, logical_operation_id)
        if existing is not None:
            if existing.action_id != (owner_action.action_id if owner_action else None):
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
            if owner_action is not None:
                recorded = ledger.action_attempt(request_owner_user_id, logical_operation_id)
                if recorded is None or (
                    existing.state != "allocated" and recorded.request_digest != request_digest
                ):
                    raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
            if existing.state == "settled" and existing.authority_digest == authority.digest():
                replay = DispatchResult(
                    text=existing.result_text or "", usage=NormalizedUsage(0, 0),
                    cost_usd=float(existing.actual_cents or 0) / 100.0,
                    latency_ms=0, provider=existing.provider_id or rung.provider_id,
                    model=existing.model_id or rung.model_id, tier="owner-replay",
                    finish_reason="replayed", fallback_chain_index=0,
                    event_id=existing.dispatch_event_id or "owner-replay",
                )
                if owner_action is not None:
                    if resource_authority_guard is not None:
                        with resource_authority_guard() as current_resource_digest:
                            if current_resource_digest != resource_authority_digest:
                                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                            return replay, authority
                    if (
                        resource_authority_revalidator is None
                        or resource_authority_revalidator() != resource_authority_digest
                    ):
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                return replay, authority
            if owner_action is None or existing.state != "allocated":
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        try:
            if owner_action is None:
                ledger.prepare_operation(
                    rung.credential.user_model_id, request_owner_user_id,
                    logical_operation_id, rung.projected_max_cents, authority.digest(),
                )
            else:
                if not isinstance(rung.payer, OwnerByotPayer):
                    raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                ledger.allocate_action_attempt(
                    request_owner_user_id, owner_action.action_id,
                    AttemptProposal(
                        operation_id=logical_operation_id,
                        user_model_id=rung.credential.user_model_id,
                        provider_id=rung.provider_id, model_id=rung.model_id,
                        route_digest=route.route_digest,
                        authority_digest=authority.digest(),
                        rate_limit_digest=rung.payer.budget_envelope_digest,
                        reserved_cents=rung.projected_max_cents,
                        action_epoch=owner_action.epoch,
                    ),
                )
        except OperationConflict:
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
        # Re-read registry, credential metadata, endpoint and live adapter at
        # the final seam. Credential plaintext remains call-time only.
        try:
            current = models_admin.resolve_owner_model_authority(
                app, choice, owner_user_id=request_owner_user_id,
            )
            if current != frozen_route:
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
            if resource_authority_guard is not None:
                # The guard holds the graph's normal writer flock only across
                # final fact validation + durable sent transition. It closes
                # owner-transfer TOCTOU without holding DuckDB over network I/O.
                with resource_authority_guard() as current_resource_digest:
                    if current_resource_digest != resource_authority_digest:
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    _claim_canonical_attempt(
                        ledger, request_owner_user_id, logical_operation_id,
                        owner_action, authority, route, request_digest,
                        current_resource_digest,
                    )
            else:
                if (
                    resource_authority_revalidator is not None
                    and resource_authority_revalidator() != resource_authority_digest
                ):
                    raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                _claim_canonical_attempt(
                    ledger, request_owner_user_id, logical_operation_id,
                    owner_action, authority, route, request_digest,
                    resource_authority_digest,
                )
        except Exception:
            row = ledger.operation(request_owner_user_id, logical_operation_id)
            if row is not None and row.state == "prepared":
                ledger.cancel_prepared_operation(
                    request_owner_user_id, logical_operation_id,
                )
            elif row is not None and row.state == "allocated" and owner_action is not None:
                ledger.cancel_action_attempt(
                    request_owner_user_id, logical_operation_id,
                    expected_epoch=owner_action.epoch,
                )
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
        try:
            result = dispatch(
                prompt,
                role=role,
                investigation_id=investigation_id,
                config=exact_config,
                # BYOT_ONLY: the payer decides the provider. ``exact_config``
                # already makes the owner's rung the tier's primary with no
                # fallback; what re-routed owner-paid calls was the router's
                # operator-lineup consult, which fires whenever the caller
                # passes no override and swapped in the house provider —
                # house paid, and the guard below turned the owner's
                # reservation into ``unknown`` for a call that never touched
                # the owner's key. Opting out keeps the receipt honest too:
                # no override was applied, so none is recorded.
                operator_lineup=False,
            )
        except Exception:
            if owner_action is None:
                ledger.mark_operation_unknown(request_owner_user_id, logical_operation_id)
            else:
                ledger.mark_action_attempt_unknown(request_owner_user_id, logical_operation_id)
            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
        try:
            if owner_action is not None and (
                not result.usage.reported or result.usage.cache_unknown
            ):
                ledger.mark_action_attempt_unknown(request_owner_user_id, logical_operation_id)
                raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown")
            if (result.provider, result.model) != (rung.provider_id, rung.model_id):
                if owner_action is None:
                    ledger.mark_operation_unknown(request_owner_user_id, logical_operation_id)
                else:
                    ledger.mark_action_attempt_unknown(request_owner_user_id, logical_operation_id)
                raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown")
            actual_cents = int(
                (Decimal(str(result.cost_usd)) * 100).to_integral_value(
                    rounding=ROUND_CEILING,
                )
            )
            evidence = hashlib.sha256(
                json.dumps(
                    {
                        "authority_digest": authority.digest(),
                        "dispatch_event_id": result.event_id,
                        "provider": result.provider,
                        "model": result.model,
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            if result.event_id is None:
                raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown")
            if owner_action is None:
                ledger.record_operation_result(
                    request_owner_user_id, logical_operation_id,
                    actual_cents=actual_cents, evidence_sha256=evidence,
                    dispatch_event_id=result.event_id, provider_id=result.provider,
                    model_id=result.model, result_text=result.text,
                )
                ledger.settle_operation(
                    request_owner_user_id, logical_operation_id, actual_cents, evidence,
                )
            else:
                ledger.record_action_attempt_result(
                    request_owner_user_id, logical_operation_id,
                    VerifiedAttemptFacts(
                        provider_id=result.provider, model_id=result.model,
                        provider_attempt_event_id=result.event_id,
                        evidence_sha256=evidence, request_digest=request_digest,
                        cost_micro_usd=int((Decimal(str(result.cost_usd)) * 1_000_000)
                                           .to_integral_value(rounding=ROUND_CEILING)),
                        result_text=result.text,
                    ),
                )
                ledger.settle_action_attempt(request_owner_user_id, logical_operation_id)
        except OwnerByotOutcomeUnknown:
            raise
        except Exception:
            # A successful provider response with failed durable settlement is
            # unknown, never retryable. The sent reservation remains held.
            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
        return result, authority
    except OwnerByotDispatchUnavailable:
        raise
    except Exception:
        # Provider, registry, credential, and authority exceptions can retain
        # secrets or private prompts. Collapse them at this boundary.
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None


def approved_owner_action_route(
    app: FastAPI, choice: models_admin.UserModelChoice, *, owner_user_id: str,
) -> ApprovedOwnerRoute:
    """Resolve non-secret route facts for a server-approved action decision."""
    try:
        return _approved_action_route(models_admin.resolve_owner_model_authority(
            app, choice, owner_user_id=owner_user_id,
        ))
    except Exception:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None


def _approved_action_route(resolved: models_admin.OwnerModelAuthority) -> ApprovedOwnerRoute:
    record = resolved.record
    digest = hashlib.sha256(json.dumps({
        "owner_user_id": record.owner_user_id, "user_model_id": record.id,
        "provider_kind": record.provider_kind, "base_url": record.base_url,
        "model_id": resolved.model_id, "credential_id": resolved.credential_id,
        "credential_fingerprint": resolved.credential_fingerprint,
        "registration_fingerprint": resolved.registration_fingerprint,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ApprovedOwnerRoute(record.id, record.id, resolved.model_id, digest)


def _canonical_request_digest(
    authority: DispatchAuthority, config: DispatchConfig, prompt: str, role: str,
) -> str:
    """Bind the canonical dispatcher input, not a native SDK wire request."""
    tier = config.tiers[config.role_tiers[role]]
    return hashlib.sha256(json.dumps({
        "authority": authority.digest(), "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "role": role, "model": tier.model, "max_tokens": tier.max_tokens,
        "temperature": tier.temperature,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _claim_canonical_attempt(
    ledger: ByotUsageLedger, owner: str, operation: str,
    action: OwnerActionRef | None, authority: DispatchAuthority,
    route: ApprovedOwnerRoute, request_digest: str, body_digest: str | None,
) -> None:
    if action is None:
        ledger.mark_operation_sent(owner, operation)
        return
    payer = authority.fallback_manifest[0].payer
    if not isinstance(payer, OwnerByotPayer) or body_digest is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    claim = ledger.claim_action_attempt(owner, operation, FinalSendFacts(
        request_digest=request_digest, authority_digest=authority.digest(),
        route_digest=route.route_digest, rate_limit_digest=payer.budget_envelope_digest,
        body_authority_digest=body_digest,
        claim_nonce_digest=hashlib.sha256(uuid4().bytes).hexdigest(),
        action_epoch=action.epoch,
    ))
    if not claim.won:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")


def _freeze_current_authority(
    *,
    app: FastAPI,
    request_owner_user_id: str,
    resource_owner_user_id: str,
    document_id: str,
    choice: models_admin.UserModelChoice,
    prompt: str,
    logical_operation_id: str,
    resource_authority_digest: str | None,
    config: DispatchConfig | None,
    role: str = "user_agent",
    action: str = _ACTION,
) -> tuple[DispatchAuthority, DispatchConfig, models_admin.OwnerModelAuthority]:
    validated = models_admin.UserModelChoice.model_validate(choice.model_dump(mode="json"))
    try:
        resolved = models_admin.resolve_owner_model_authority(
            app, validated, owner_user_id=request_owner_user_id,
        )
    except models_admin.UserModelChoiceUnavailable:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
    record = resolved.record
    # The chosen variant (one of record.model_ids) is what gets bound, priced
    # and sent; the ledger stays keyed on record.id across variants.
    binding = OwnerCredentialBinding(
        owner_user_id=record.owner_user_id, user_model_id=record.id,
        credential_id=resolved.credential_id, provider_id=record.id,
        model_id=resolved.model_id, metadata_fingerprint=resolved.credential_fingerprint,
        binding_version=3,
    )

    projected_cents, budget_digest, exact_config = _budget_and_exact_config(
        record=record, model_id=resolved.model_id,
        prompt=prompt, role=role,
        config=config,
    )
    if resource_authority_digest is not None:
        budget_digest = hashlib.sha256(
            f"{budget_digest}:{resource_authority_digest}".encode("ascii")
        ).hexdigest()
    candidate = OwnerCredentialCandidate(
        binding=binding,
        record_owner_user_id=record.owner_user_id,
        credential_owner_user_id=record.owner_user_id,
        enabled=True, matching_records=1,
        current_metadata_fingerprint=resolved.credential_fingerprint,
    )
    payer = OwnerByotPayer(
        owner_user_id=request_owner_user_id,
        credential_id=resolved.credential_id,
        budget_envelope_digest=budget_digest,
    )
    try:
        authority = freeze_dispatch_authority(
            authenticated_owner_user_id=request_owner_user_id,
            resource_owner_user_id=resource_owner_user_id,
            resource_id=document_id,
            action=action,
            logical_operation_id=logical_operation_id,
            requested_model=RequestedModel(validated.provider_id, resolved.model_id),
            payer_policy=PayerPolicy.BYOT_ONLY,
            proposed_routes=(ProposedRoute(
                provider_id=validated.provider_id,
                model_id=resolved.model_id,
                projected_max_cents=projected_cents,
                owner_credential=candidate,
                payer=payer,
            ),),
            now=datetime.now(UTC),
        )
    except DispatchAuthorityRefused:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
    return authority, exact_config, resolved


def _budget_and_exact_config(
    *, record: models_admin.UserModelRecord | None, prompt: str,
    config: DispatchConfig | None, role: str = "user_agent",
    model_id: str | None = None,
) -> tuple[int, str, DispatchConfig]:
    if record is None or record.provider_catalog_id is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    # ``model_id`` is the chosen variant; the record's primary when absent.
    chosen_model_id = model_id or record.model_id
    preset = get_provider_preset(record.provider_catalog_id)
    variant = get_model_variant(preset, chosen_model_id)
    endpoint = record.base_url or "https://api.anthropic.com"
    if (
        record.provider_kind != preset.adapter_kind
        or canonical_provider_endpoint(endpoint)
        != canonical_provider_endpoint(preset.default_base_url)
    ):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    loaded = config or DispatchConfig.from_yaml(
        Path(__file__).parents[3] / "substrate/dispatch/config.yaml"
    )
    tier_name = loaded.role_tiers[role]
    base = loaded.tiers[tier_name]
    # Conservative local reservation: one input token per UTF-8 byte. This is
    # a local spend ceiling, not a claim about the provider's hard token limit.
    input_tokens = max(1, len(prompt.encode("utf-8")))
    rates = {rate.unit.value: rate.usd_per_unit for rate in variant.rates}
    projected_usd = (
        Decimal(input_tokens) * rates["input_token"]
        + Decimal(base.max_tokens) * rates["output_token"]
    )
    projected_cents = int((projected_usd * 100).to_integral_value(rounding=ROUND_CEILING))
    envelope = {
        "input_tokens": input_tokens,
        "max_output_tokens": base.max_tokens,
        "model_id": chosen_model_id,
        "projected_max_cents": projected_cents,
        "provider_id": record.id,
        "rate_snapshot": variant.snapshot,
    }
    digest = hashlib.sha256(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    exact_tier = replace(
        base,
        provider=record.id,
        model=chosen_model_id,
        pricing=TierPricing(
            input_per_mtok=float(rates["input_token"] * Decimal(1_000_000)),
            output_per_mtok=float(rates["output_token"] * Decimal(1_000_000)),
            cached_input_per_mtok=0.0,
        ),
        fallback=None,
    )
    tiers = dict(loaded.tiers)
    tiers[tier_name] = exact_tier
    return projected_cents, digest, DispatchConfig(loaded.role_tiers, tiers)


__all__ = [
    "OwnerByotDispatchUnavailable",
    "OwnerByotOutcomeUnknown",
    "authenticated_distinct_owner",
    "approved_owner_action_route",
    "dispatch_talk_to_book_byot",
]
