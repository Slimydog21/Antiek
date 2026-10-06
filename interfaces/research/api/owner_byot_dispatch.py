"""Exact owner-BYOT dispatch for request-scoped AI actions."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager, suppress
from dataclasses import replace
from datetime import UTC, datetime
from decimal import ROUND_CEILING, Decimal
from pathlib import Path
from typing import TypedDict
from uuid import uuid4

from fastapi import FastAPI, Request

from interfaces.research.api import settings_models_admin as models_admin
from interfaces.research.api.account_memory_identity import (
    FORBIDDEN_OWNERS,
    OPERATOR_STORAGE_SENTINEL,
    derive_owner_from_verified_email,
)
from runtime.byok.store import guard_current_credential, prepare_current_master_key
from runtime.research_runner.byot_provider_catalog import (
    get_model_variant,
    get_provider_preset,
)
from runtime.research_runner.provider_route_authority import canonical_provider_endpoint
from substrate.byot_usage.actions import (
    ActionAttemptSnapshot,
    ApprovedOwnerRoute,
    AttemptProposal,
    CanonicalInputBinding,
    FinalSendFacts,
    OwnerActionRef,
    VerifiedAttemptFacts,
)
from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict
from substrate.constants import ANTIEK_PARAM_VERSION
from substrate.dispatch.base import NormalizedUsage
from substrate.dispatch.canonical_http import (
    AdmittedCanonicalPolicy,
    CanonicalClaimLost,
    CanonicalExchange,
    CanonicalHttpRefused,
    execute_owned_http,
    validate_owned_response_text,
)
from substrate.dispatch.providers.anthropic import AnthropicProvider
from substrate.dispatch.providers.openai_compat import OpenAICompatProvider
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
    current_provider_registration,
    dispatch,
    normalize_finish_reason,
)
from substrate.event_log import emit_typed, iter_physical_events
from substrate.schemas import EVENT_SCHEMA_VERSION, DispatchCallPayload, Event

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


class _OwnedResultMetadata(TypedDict):
    version: str
    response_digest: str
    response_id_digest: str
    input_tokens: int
    output_tokens: int
    finish_reason: str | None
    latency_ms: int


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
    context_pack_event_id: str | None = None,
    parent_event_id: str | None = None,
) -> tuple[DispatchResult, DispatchAuthority]:
    """Revalidate, freeze, and execute exactly one owner-paid model rung.

    The default role is ``thought_partner``: the Talk-to-Book ask path (the
    caller that relies on the default) answers through the SAME role as
    Surface E / AISidecar / Dialogue since the role unify — an owner-paid
    rung is not a second partner personality. Loop One callers pass their
    own role explicitly."""
    if owner_action is not None:
        return _dispatch_owned_canonical(
            app=app, request_owner_user_id=request_owner_user_id,
            resource_owner_user_id=resource_owner_user_id, document_id=document_id,
            choice=choice, prompt=prompt, investigation_id=investigation_id,
            logical_operation_id=logical_operation_id,
            resource_authority_digest=resource_authority_digest,
            resource_authority_guard=resource_authority_guard,
            config=config, usage_ledger=usage_ledger, role=role, action=action,
            owner_action=owner_action, context_pack_event_id=context_pack_event_id,
            parent_event_id=parent_event_id,
        )
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
                context_pack_event_id=context_pack_event_id,
                parent_event_id=parent_event_id,
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
                notdiamond_shadow=False,
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


def _owned_policy(
    record: models_admin.UserModelRecord, model_id: str,
    exact_config: DispatchConfig, role: str, prompt: str, credential_fingerprint: str,
    generation: int,
) -> AdmittedCanonicalPolicy:
    """Admit two exact catalog rows independently of the adapter's builder."""
    if not (
        (record.provider_catalog_id == "deepseek"
         and record.provider_kind == "openai_compat"
         and model_id == "deepseek-flash-nothink")
        or (record.provider_catalog_id == "anthropic"
            and record.provider_kind == "anthropic"
            and model_id == "claude-haiku-4-5-20251001")
    ):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    catalog_id = record.provider_catalog_id
    if catalog_id is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    preset = get_provider_preset(catalog_id)
    if (record.base_url or preset.default_base_url) != preset.default_base_url:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    variant = get_model_variant(preset, model_id)
    if (record.provider_catalog_id == "deepseek"
        and (variant.request_model_id != "deepseek-flash"
             or variant.thinking != "disabled")):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    if (record.provider_catalog_id == "anthropic"
        and (variant.request_model_id != "claude-haiku-4-5-20251001"
             or variant.thinking is not None)):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    tier = exact_config.tiers[exact_config.role_tiers[role]]
    rates = {rate.unit.value: rate.usd_per_unit for rate in variant.rates}
    if (tier.provider != record.id or tier.model != model_id
        or type(tier.max_tokens) is not int or type(tier.temperature) is not float
        or set(rates) != {"input_token", "output_token"}):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    return AdmittedCanonicalPolicy(
        protocol=record.provider_kind,
        provider_id=record.id,
        catalog_model=model_id,
        wire_model=variant.request_model_id,
        endpoint=preset.default_base_url + preset.chat_completions_path,
        prompt=prompt,
        output_limit=tier.max_tokens,
        temperature=tier.temperature,
        thinking="disabled" if record.provider_catalog_id == "deepseek" else None,
        input_rate=rates["input_token"], output_rate=rates["output_token"],
        price_snapshot=variant.snapshot,
        credential_fingerprint=credential_fingerprint,
        registration_generation=generation,
    )


@contextmanager
def _current_owned_sender(
    *, app: FastAPI, owner: str, resolved: models_admin.OwnerModelAuthority,
    prompt: str, role: str, source_digest: str,
    source_guard: Callable[[], AbstractContextManager[str]],
    prepared_master_key: bytes, config: DispatchConfig | None,
    exact_config: DispatchConfig, authority: DispatchAuthority,
) -> Iterator[tuple[AdmittedCanonicalPolicy, OpenAICompatProvider | AnthropicProvider, str]]:
    """Take graph -> registry -> credential -> registration, then yield claim facts."""
    with source_guard() as current_source:
        if current_source != source_digest:
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        with models_admin.current_user_model_record(resolved.record.id) as record:
            if (record is None or not record.enabled or record != resolved.record
                or record.owner_user_id != owner or record.cred_ref != resolved.credential_id
                or record.cred_fingerprint != resolved.credential_fingerprint):
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
            with guard_current_credential(
                record.cred_ref, prepared_master_key=prepared_master_key,
            ) as credential:
                metadata = credential.metadata
                if (metadata.cred_id != record.cred_ref
                    or metadata.binding_version != 3
                    or metadata.owner_user_id != owner
                    or metadata.pipeline_kind != "model_provider"
                    or metadata.account_handle != record.id
                    or metadata.artifact_fingerprint != record.cred_fingerprint):
                    raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                with current_provider_registration(record.id) as registration:
                    provider = registration.provider
                    expected_type = (
                        models_admin._UserOpenAICompatProvider
                        if record.provider_kind == "openai_compat"
                        else models_admin._UserAnthropicProvider
                    )
                    seam = getattr(app.state, "registered_providers", None)
                    fingerprints = getattr(app.state, "user_model_registration_fingerprints", None)
                    record_fingerprint = models_admin._record_fingerprint(record)
                    if (not isinstance(provider, expected_type)
                        or not isinstance(seam, set) or record.id not in seam
                        or not isinstance(fingerprints, dict)
                        or fingerprints.get(record.id) != record_fingerprint
                        or getattr(provider, "_user_model_id", None) != record.id
                        or getattr(provider, "_cred_ref", None) != record.cred_ref
                        or getattr(provider, "_user_model_authority_fingerprint", None)
                           != record_fingerprint):
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    if (record.provider_kind == "anthropic"
                        and getattr(provider, "_enable_prompt_caching", None) is not False):
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    projected, budget_digest, current_config = _budget_and_exact_config(
                        record=record, model_id=resolved.model_id, prompt=prompt,
                        role=role, config=config, canonical_final=True,
                    )
                    budget_digest = hashlib.sha256(
                        f"{budget_digest}:{source_digest}".encode("ascii")
                    ).hexdigest()
                    payer = authority.fallback_manifest[0].payer
                    if (not isinstance(payer, OwnerByotPayer)
                        or payer.budget_envelope_digest != budget_digest
                        or current_config != exact_config):
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    policy = _owned_policy(
                        record, resolved.model_id, exact_config, role, prompt,
                        metadata.artifact_fingerprint, registration.generation,
                    )
                    if policy.reserved_cents != projected:
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    if not isinstance(provider, (OpenAICompatProvider, AnthropicProvider)):
                        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                    yield policy, provider, credential.secret.reveal()


def _owned_input_binding(
    *, policy: AdmittedCanonicalPolicy, authority: DispatchAuthority,
    owner_action: OwnerActionRef, source_digest: str,
    investigation_id: str, document_id: str, logical_operation_id: str,
    role: str, context_pack_event_id: str | None, parent_event_id: str | None,
    exact_config: DispatchConfig,
) -> CanonicalInputBinding:
    tier_name = exact_config.role_tiers[role]
    tier = exact_config.tiers[tier_name]
    logical = hashlib.sha256(json.dumps({
        "version": "owned-canonical-http.v1", "policy_digest": policy.input_digest(),
        "authority_digest": authority.digest(), "owner": owner_action.owner_user_id,
        "action_id": owner_action.action_id, "action_epoch": owner_action.epoch,
        "source_digest": source_digest, "document_id": document_id,
        "investigation_id": investigation_id, "operation_id": logical_operation_id,
        "role": role, "tier": tier_name, "provider": tier.provider,
        "model": tier.model, "max_tokens": tier.max_tokens,
        "temperature": tier.temperature,
        "context_pack_event_id": context_pack_event_id,
        "parent_event_id": parent_event_id,
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    return CanonicalInputBinding(logical, policy.input_digest())


def _owned_call_id(owner: str, operation: str) -> str:
    return "ocall-" + hashlib.sha256(f"{owner}\0{operation}".encode()).hexdigest()[:32]


def _owned_result_metadata(exchange: CanonicalExchange) -> _OwnedResultMetadata:
    return {
        "version": "owned-canonical-http.v1",
        "response_digest": exchange.response_digest,
        "response_id_digest": hashlib.sha256(exchange.provider_response_id.encode()).hexdigest(),
        "input_tokens": exchange.input_tokens, "output_tokens": exchange.output_tokens,
        "finish_reason": normalize_finish_reason(exchange.parsed.finish_reason),
        "latency_ms": exchange.parsed.latency_ms,
    }


def _owned_result_evidence(
    metadata_json: str, text: str, request_digest: str, nonce: str,
    policy_digest: str, cost_micro_usd: int,
) -> str:
    return hashlib.sha256(json.dumps({
        "metadata": metadata_json, "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
        "request_digest": request_digest, "claim_nonce_digest": nonce,
        "policy_digest": policy_digest, "cost_micro_usd": cost_micro_usd,
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _owned_result_from_attempt(
    attempt: ActionAttemptSnapshot, policy: AdmittedCanonicalPolicy,
) -> tuple[_OwnedResultMetadata, str]:
    raw = attempt.result_reference
    operation = attempt.operation
    if (raw is None or operation.result_text is None
        or operation.evidence_sha256 is None or operation.actual_cents is None
        or attempt.request_digest is None or attempt.claim_nonce_digest is None
        or attempt.cost_micro_usd is None):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    try:
        metadata = json.loads(raw)
    except (TypeError, ValueError):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
    if (type(metadata) is not dict
        or set(metadata) != {"version", "response_digest", "response_id_digest",
                             "input_tokens", "output_tokens", "finish_reason", "latency_ms"}
        or metadata["version"] != "owned-canonical-http.v1"
        or any(type(metadata[key]) is not str or len(metadata[key]) != 64
               for key in ("response_digest", "response_id_digest"))
        or any(type(metadata[key]) is not int or metadata[key] < 0
               for key in ("input_tokens", "output_tokens", "latency_ms"))
        or metadata["finish_reason"] not in {"stop", "length"}
        or operation.actual_cents != (attempt.cost_micro_usd + 9999) // 10000
        or operation.evidence_sha256 != _owned_result_evidence(
            raw, operation.result_text, attempt.request_digest,
            attempt.claim_nonce_digest, policy.input_digest(), attempt.cost_micro_usd,
        )):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    return _OwnedResultMetadata(
        version=metadata["version"], response_digest=metadata["response_digest"],
        response_id_digest=metadata["response_id_digest"],
        input_tokens=metadata["input_tokens"], output_tokens=metadata["output_tokens"],
        finish_reason=metadata["finish_reason"], latency_ms=metadata["latency_ms"],
    ), operation.result_text


def _owned_dispatch_event(
    *, owner: str, operation: str, investigation_id: str,
    parent_event_id: str | None, context_pack_event_id: str | None,
    role: str, tier: str, policy: AdmittedCanonicalPolicy,
    metadata: _OwnedResultMetadata, cost_micro_usd: int,
) -> str:
    event_id = _owned_call_id(owner, operation)
    policy_id = f"{policy.provider_id}/{policy.catalog_model}"
    payload = DispatchCallPayload.model_validate({
        "provider": policy.provider_id, "model": policy.catalog_model,
        "tier": tier, "target_role": role,
        "input_tokens": metadata["input_tokens"],
        "output_tokens": metadata["output_tokens"],
        "cost_usd": cost_micro_usd / 1_000_000,
        "latency_ms": metadata["latency_ms"],
        "verification_required": False, "fallback_chain_index": 0,
        "prompt_hash": "sha256:" + hashlib.sha256(policy.prompt.encode()).hexdigest()[:12],
        "finish_reason": metadata["finish_reason"],
        "context_pack_event_id": context_pack_event_id,
    })

    def exact_row() -> bool:
        try:
            physical_rows = list(iter_physical_events(investigation_id))
        except Exception:
            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
        rows = [row for row in physical_rows
                if row.get("event_id") == event_id]
        if len(rows) > 1:
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        if not rows:
            return False
        event = Event.model_validate(rows[0])
        if (event.investigation_id != investigation_id
            or event.parent_event_id != parent_event_id or event.role != role
            or event.policy_id != policy_id
            or event.param_version != ANTIEK_PARAM_VERSION
            or event.schema_version != EVENT_SCHEMA_VERSION
            or event.phase is not None or event.synthesis_id is not None
            or event.document_id is not None
            or event.payload.model_dump(mode="json") != payload.model_dump(mode="json")):
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        return True

    if not exact_row():
        try:
            emitted = emit_typed(
                investigation_id, payload, event_id=event_id,
                idempotent=True, strict_write=True, parent_event_id=parent_event_id,
                role=role, policy_id=policy_id,
            )
        except Exception:
            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
        if emitted != event_id or not exact_row():
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    return event_id


def _owned_dispatch_result(
    *, attempt: ActionAttemptSnapshot, policy: AdmittedCanonicalPolicy,
    metadata: _OwnedResultMetadata, text: str, tier: str,
    event_id: str, replayed: bool,
) -> DispatchResult:
    cost_micro_usd = attempt.cost_micro_usd
    if cost_micro_usd is None:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    return DispatchResult(
        text=text,
        usage=NormalizedUsage(metadata["input_tokens"], metadata["output_tokens"]),
        cost_usd=cost_micro_usd / 1_000_000,
        latency_ms=metadata["latency_ms"],
        provider=policy.provider_id, model=policy.catalog_model,
        tier=tier, finish_reason="replayed" if replayed else str(metadata["finish_reason"]),
        fallback_chain_index=0, event_id=event_id,
    )


def _dispatch_owned_canonical(
    *, app: FastAPI, request_owner_user_id: str, resource_owner_user_id: str,
    document_id: str, choice: models_admin.UserModelChoice, prompt: str,
    investigation_id: str, logical_operation_id: str,
    resource_authority_digest: str | None,
    resource_authority_guard: Callable[[], AbstractContextManager[str]] | None,
    config: DispatchConfig | None, usage_ledger: ByotUsageLedger | None,
    role: str, action: str, owner_action: OwnerActionRef,
    context_pack_event_id: str | None, parent_event_id: str | None,
) -> tuple[DispatchResult, DispatchAuthority]:
    """One owned allocation and final byte claim; never enters ordinary router."""
    if (owner_action.owner_user_id != request_owner_user_id
        or resource_owner_user_id != request_owner_user_id
        or resource_authority_digest is None or resource_authority_guard is None):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
    try:
        authority, exact_config, resolved = _freeze_current_authority(
            app=app, request_owner_user_id=request_owner_user_id,
            resource_owner_user_id=resource_owner_user_id, document_id=document_id,
            choice=choice, prompt=prompt, logical_operation_id=logical_operation_id,
            resource_authority_digest=resource_authority_digest, config=config,
            role=role, action=action, canonical_final=True,
        )
        rung = authority.fallback_manifest[0]
        payer = rung.payer
        if (not isinstance(rung.credential, OwnerCredentialBinding)
            or not isinstance(payer, OwnerByotPayer)):
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        master = prepare_current_master_key()
        def current_sender() -> AbstractContextManager[
            tuple[AdmittedCanonicalPolicy, OpenAICompatProvider | AnthropicProvider, str]
        ]:
            return _current_owned_sender(
                app=app, owner=request_owner_user_id, resolved=resolved, prompt=prompt,
                role=role, source_digest=resource_authority_digest,
                source_guard=resource_authority_guard, prepared_master_key=master,
                config=config, exact_config=exact_config, authority=authority,
            )

        with current_sender() as (policy, provider, secret):
            pass
        if policy.reserved_cents != rung.projected_max_cents:
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
        ledger = usage_ledger or ByotUsageLedger()
        route = _approved_action_route(resolved)
        existing = ledger.action_attempt(request_owner_user_id, logical_operation_id)
        original_epoch = (existing.proposal.action_epoch if existing is not None
                          else owner_action.epoch)
        input_binding = _owned_input_binding(
            policy=policy, authority=authority,
            owner_action=OwnerActionRef(request_owner_user_id, owner_action.action_id,
                                        original_epoch),
            source_digest=resource_authority_digest,
            investigation_id=investigation_id, document_id=document_id,
            logical_operation_id=logical_operation_id, role=role,
            context_pack_event_id=context_pack_event_id,
            parent_event_id=parent_event_id, exact_config=exact_config,
        )
        proposal = AttemptProposal(
            operation_id=logical_operation_id,
            user_model_id=rung.credential.user_model_id,
            provider_id=rung.provider_id, model_id=rung.model_id,
            route_digest=route.route_digest,
            authority_digest=authority.digest(),
            rate_limit_digest=payer.budget_envelope_digest,
            reserved_cents=policy.reserved_cents,
            action_epoch=original_epoch,
        )
        if existing is not None:
            if (existing.proposal != proposal
                or existing.operation.action_id != owner_action.action_id
                or ledger.canonical_input_binding(
                    request_owner_user_id, logical_operation_id,
                ) != input_binding):
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
            attempt = existing
        else:
            attempt = ledger.allocate_action_attempt(
                request_owner_user_id, owner_action.action_id, proposal,
                canonical_input=input_binding,
            )
        tier_name = exact_config.role_tiers[role]
        if attempt.operation.state in {"settlement_pending", "settled"}:
            with current_sender() as (current_policy, current_provider, current_secret):
                if (current_policy.digest() != policy.digest()
                    or current_provider is not provider
                    or not hmac.compare_digest(current_secret, secret)):
                    raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")
                metadata, text = _owned_result_from_attempt(attempt, policy)
                validate_owned_response_text(text, current_secret)
                if attempt.operation.state == "settlement_pending":
                    try:
                        attempt = ledger.settle_action_attempt(
                            request_owner_user_id, logical_operation_id,
                        )
                    except Exception:
                        observed = ledger.action_attempt(request_owner_user_id,
                                                         logical_operation_id)
                        if observed is None or observed.operation.state != "settled":
                            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
                        attempt = observed
            event_id = _owned_dispatch_event(
                owner=request_owner_user_id, operation=logical_operation_id,
                investigation_id=investigation_id, parent_event_id=parent_event_id,
                context_pack_event_id=context_pack_event_id, role=role, tier=tier_name,
                policy=policy, metadata=metadata,
                cost_micro_usd=attempt.cost_micro_usd or 0,
            )
            return _owned_dispatch_result(
                attempt=attempt, policy=policy, metadata=metadata, text=text,
                tier=tier_name, event_id=event_id, replayed=True,
            ), authority
        if attempt.operation.state != "allocated":
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable")

        nonce = hashlib.sha256(uuid4().bytes).hexdigest()
        claimed = False

        def final_claim(final_request_digest: str) -> str:
            nonlocal claimed
            with current_sender() as (current_policy, current_provider, current_secret):
                if (current_policy.digest() != policy.digest()
                    or current_provider is not provider
                    or not hmac.compare_digest(current_secret, secret)):
                    raise CanonicalHttpRefused("current_authority_changed")
                facts = FinalSendFacts(
                    request_digest=final_request_digest,
                    authority_digest=authority.digest(),
                    route_digest=route.route_digest,
                    rate_limit_digest=payer.budget_envelope_digest,
                    body_authority_digest=resource_authority_digest,
                    claim_nonce_digest=nonce, action_epoch=original_epoch,
                    canonical_input=input_binding,
                )
                try:
                    won = ledger.claim_action_attempt(
                        request_owner_user_id, logical_operation_id, facts,
                    )
                except Exception:
                    try:
                        observed = ledger.action_attempt(
                            request_owner_user_id, logical_operation_id,
                        )
                    except Exception:
                        raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
                    if observed is None:
                        raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
                    if (observed is not None and observed.operation.state == "sent"
                        and observed.request_digest == final_request_digest
                        and observed.claim_nonce_digest == nonce):
                        claimed = True
                        return nonce
                    if observed is not None and observed.operation.state == "allocated":
                        raise CanonicalHttpRefused("claim_refused") from None
                    raise CanonicalClaimLost("claim_lost") from None
                if not won.won:
                    raise CanonicalClaimLost("claim_lost")
                claimed = True
                return nonce

        try:
            exchange = execute_owned_http(policy, provider, secret, final_claim)
        except CanonicalClaimLost:
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
        except OwnerByotOutcomeUnknown:
            raise
        except Exception:
            try:
                current = ledger.action_attempt(request_owner_user_id, logical_operation_id)
            except Exception:
                if claimed:
                    raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
                raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
            if claimed and current is not None and current.operation.state == "sent":
                ledger.mark_action_attempt_unknown(request_owner_user_id,
                                                   logical_operation_id)
                raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
            if not claimed and current is not None and current.operation.state == "allocated":
                with suppress(OperationConflict):
                    ledger.cancel_action_attempt(request_owner_user_id,
                                                 logical_operation_id,
                                                 expected_epoch=original_epoch)
            raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None

        try:
            metadata = _owned_result_metadata(exchange)
            metadata_json = json.dumps(metadata, sort_keys=True, separators=(",", ":"))
            evidence = _owned_result_evidence(
                metadata_json, exchange.parsed.text, exchange.request_digest,
                exchange.claim_nonce_digest, policy.input_digest(), exchange.cost_micro_usd,
            )
            facts = VerifiedAttemptFacts(
                provider_id=policy.provider_id, model_id=policy.catalog_model,
                provider_attempt_event_id=_owned_call_id(request_owner_user_id,
                                                         logical_operation_id),
                evidence_sha256=evidence, request_digest=exchange.request_digest,
                cost_micro_usd=exchange.cost_micro_usd, result_reference=metadata_json,
                result_text=exchange.parsed.text,
            )
        except Exception:
            ledger.mark_action_attempt_unknown(request_owner_user_id, logical_operation_id)
            raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
        try:
            attempt = ledger.record_action_attempt_result(
                request_owner_user_id, logical_operation_id, facts,
            )
        except Exception:
            observed = ledger.action_attempt(request_owner_user_id, logical_operation_id)
            if observed is None or observed.operation.state not in {
                "settlement_pending", "settled",
            }:
                if observed is not None and observed.operation.state == "sent":
                    ledger.mark_action_attempt_unknown(request_owner_user_id,
                                                       logical_operation_id)
                raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
            attempt = ledger.record_action_attempt_result(
                request_owner_user_id, logical_operation_id, facts,
            )
        if attempt.operation.state != "settled":
            try:
                attempt = ledger.settle_action_attempt(request_owner_user_id,
                                                       logical_operation_id)
            except Exception:
                observed = ledger.action_attempt(request_owner_user_id,
                                                 logical_operation_id)
                if observed is not None and observed.operation.state == "settlement_pending":
                    try:
                        observed = ledger.settle_action_attempt(
                            request_owner_user_id, logical_operation_id,
                        )
                    except Exception:
                        observed = ledger.action_attempt(request_owner_user_id,
                                                         logical_operation_id)
                if observed is None or observed.operation.state != "settled":
                    raise OwnerByotOutcomeUnknown("owner_byot_outcome_unknown") from None
                attempt = observed
        event_id = _owned_dispatch_event(
            owner=request_owner_user_id, operation=logical_operation_id,
            investigation_id=investigation_id, parent_event_id=parent_event_id,
            context_pack_event_id=context_pack_event_id, role=role, tier=tier_name,
            policy=policy, metadata=metadata,
            cost_micro_usd=exchange.cost_micro_usd,
        )
        return _owned_dispatch_result(
            attempt=attempt, policy=policy, metadata=metadata,
            text=exchange.parsed.text, tier=tier_name, event_id=event_id,
            replayed=False,
        ), authority
    except OwnerByotDispatchUnavailable:
        raise
    except (CanonicalHttpRefused, OperationConflict):
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None
    except Exception:
        raise OwnerByotDispatchUnavailable("owner_byot_dispatch_unavailable") from None


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
    canonical_final: bool = False,
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
        config=config, canonical_final=canonical_final,
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
    canonical_final: bool = False,
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
    input_tokens = (
        len(prompt.encode("utf-8")) + len(variant.request_model_id.encode()) + 64
        if canonical_final else max(1, len(prompt.encode("utf-8")))
    )
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
    if canonical_final:
        envelope["version"] = "owned-canonical-http.v1"
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
