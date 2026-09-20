"""Server-owned BYOT provider presets and pinned price rows.

Presets name provider-owned OpenAI-compatible endpoints. They clear the
unknown-pricing gate only for an exact provider/model/endpoint tuple; custom
endpoints receive no entry. Qualification remains explicitly unproven here, so
this catalog does not manufacture hard-ceiling execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from .cost_projection import CostCatalogEntry, UnitRate
from .protocol import BillingUnit
from .provider_qualification import (
    EvidenceStatus,
    ProviderQualification,
    QualificationEvidence,
    QualificationVerdict,
)
from .provider_route_authority import ProviderRouteIdentity, RouteAuthorityCatalogEntry

ProviderCatalogId = Literal[
    "openai",
    "anthropic",
    "deepseek",
    "kimi",
    "zhipu_glm",
    "mimo",
    "xai",
]
AdapterKind = Literal["openai_compat", "anthropic"]

_SEAM_ID = "user.prompt.generate"
_OPERATION = "generate"
_CATALOG_EXPIRES_AT = datetime(2027, 1, 1, tzinfo=UTC)
_CHECKED_AT = "2026-08-12T00:00:00+00:00"


@dataclass(frozen=True, slots=True)
class ByotModelVariant:
    model_id: str
    label: str
    rates: tuple[UnitRate, ...]
    snapshot: str


@dataclass(frozen=True, slots=True)
class ByotProviderPreset:
    catalog_id: ProviderCatalogId
    display: str
    adapter_kind: AdapterKind
    default_base_url: str
    chat_completions_path: str
    models: tuple[ByotModelVariant, ...]
    pricing_source: str


def _rates(input_per_million: str, output_per_million: str) -> tuple[UnitRate, ...]:
    million = Decimal("1000000")
    return (
        UnitRate(BillingUnit.INPUT_TOKEN, Decimal(input_per_million) / million),
        UnitRate(BillingUnit.OUTPUT_TOKEN, Decimal(output_per_million) / million),
    )


BYOT_PROVIDER_PRESETS: tuple[ByotProviderPreset, ...] = (
    ByotProviderPreset(
        catalog_id="openai",
        display="OpenAI",
        adapter_kind="openai_compat",
        default_base_url="https://api.openai.com",
        chat_completions_path="/v1/chat/completions",
        models=(
            ByotModelVariant(
                "gpt-5.6-sol",
                "GPT-5.6 Sol",
                _rates("5.00", "30.00"),
                "openai-gpt-5.6-sol-2026-08-12",
            ),
            ByotModelVariant(
                "gpt-5.6-terra",
                "GPT-5.6 Terra",
                _rates("2.00", "12.00"),
                "openai-gpt-5.6-terra-2026-08-12",
            ),
            ByotModelVariant(
                "gpt-5.6-luna",
                "GPT-5.6 Luna",
                _rates("0.20", "1.20"),
                "openai-gpt-5.6-luna-2026-08-12",
            ),
        ),
        pricing_source="https://developers.openai.com/api/docs/models",
    ),
    ByotProviderPreset(
        catalog_id="anthropic",
        display="Anthropic",
        adapter_kind="anthropic",
        default_base_url="https://api.anthropic.com",
        chat_completions_path="/v1/messages",
        models=(
            ByotModelVariant(
                "claude-opus-5",
                "Claude Opus 5",
                _rates("5.00", "25.00"),
                "anthropic-claude-opus-5-2026-08-12",
            ),
            ByotModelVariant(
                "claude-sonnet-5",
                "Claude Sonnet 5",
                _rates("2.00", "10.00"),
                "anthropic-claude-sonnet-5-2026-08-12",
            ),
            ByotModelVariant(
                "claude-haiku-4-5-20251001",
                "Claude Haiku 4.5",
                _rates("1.00", "5.00"),
                "anthropic-claude-haiku-4-5-20251001-2026-08-12",
            ),
        ),
        pricing_source="https://platform.claude.com/docs/en/about-claude/models/overview",
    ),
    ByotProviderPreset(
        catalog_id="deepseek",
        display="DeepSeek",
        adapter_kind="openai_compat",
        default_base_url="https://api.deepseek.com",
        chat_completions_path="/chat/completions",
        models=(
            ByotModelVariant(
                "deepseek-reasoner",
                "DeepSeek V4 Pro",
                _rates("0.55", "2.19"),
                "deepseek-v4-pro-2026-08-spec",
            ),
            ByotModelVariant(
                "deepseek-chat",
                "DeepSeek V4 Flash",
                _rates("0.28", "0.42"),
                "deepseek-v4-flash-2026-08-spec",
            ),
        ),
        pricing_source="https://api-docs.deepseek.com/quick_start/pricing",
    ),
    ByotProviderPreset(
        catalog_id="kimi",
        display="Moonshot / Kimi",
        adapter_kind="openai_compat",
        default_base_url="https://api.moonshot.ai/v1",
        chat_completions_path="/chat/completions",
        models=(
            ByotModelVariant(
                "kimi-k2.5",
                "Kimi K2.5",
                _rates("0.60", "2.50"),
                "kimi-k2.5-2026-08-spec",
            ),
        ),
        pricing_source="https://platform.moonshot.ai/docs/pricing/chat",
    ),
    ByotProviderPreset(
        catalog_id="zhipu_glm",
        display="Zhipu GLM",
        adapter_kind="openai_compat",
        default_base_url="https://api.z.ai/api/paas/v4",
        chat_completions_path="/chat/completions",
        models=(
            ByotModelVariant(
                "glm-5.2",
                "GLM 5.2",
                _rates("0.60", "2.20"),
                "zhipu-glm-5.2-2026-08-spec",
            ),
        ),
        pricing_source="https://docs.z.ai/guides/overview/pricing",
    ),
    ByotProviderPreset(
        catalog_id="mimo",
        display="Xiaomi MiMo",
        adapter_kind="openai_compat",
        default_base_url="https://api.mimo.xiaomi.com/v1",
        chat_completions_path="/chat/completions",
        models=(
            ByotModelVariant(
                "mimo-v2.5-pro",
                "MiMo V2.5 Pro",
                _rates("0.15", "0.60"),
                "xiaomi-mimo-v2.5-pro-2026-08-spec",
            ),
        ),
        pricing_source="https://platform.xiaomimimo.com/docs/pricing",
    ),
    ByotProviderPreset(
        catalog_id="xai",
        display="xAI",
        adapter_kind="openai_compat",
        default_base_url="https://api.x.ai/v1",
        chat_completions_path="/chat/completions",
        models=(
            ByotModelVariant(
                "grok-4.3",
                "Grok 4.3",
                _rates("3.00", "15.00"),
                "xai-grok-4.3-2026-08-spec",
            ),
        ),
        pricing_source="https://docs.x.ai/docs/models",
    ),
)

_PRESETS_BY_ID = {preset.catalog_id: preset for preset in BYOT_PROVIDER_PRESETS}
_ALIASES: dict[str, ProviderCatalogId] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "deepseek": "deepseek",
    "kimi": "kimi",
    "moonshot": "kimi",
    "moonshot/kimi": "kimi",
    "zhipu_glm": "zhipu_glm",
    "zhipu": "zhipu_glm",
    "glm": "zhipu_glm",
    "zhipu/glm": "zhipu_glm",
    "mimo": "mimo",
    "xiaomi": "mimo",
    "xiaomi/mimo": "mimo",
    "xai": "xai",
}


def canonical_catalog_id(value: str) -> ProviderCatalogId:
    try:
        return _ALIASES[value]
    except KeyError as exc:
        raise KeyError(f"unknown BYOT provider preset: {value}") from exc


def get_provider_preset(catalog_id: str) -> ByotProviderPreset:
    return _PRESETS_BY_ID[canonical_catalog_id(catalog_id)]


def get_model_variant(preset: ByotProviderPreset, model_id: str) -> ByotModelVariant:
    try:
        return next(model for model in preset.models if model.model_id == model_id)
    except StopIteration as exc:
        raise KeyError(f"model is not in BYOT provider preset: {model_id}") from exc


def _qualification(
    preset: ByotProviderPreset,
    variant: ByotModelVariant,
) -> ProviderQualification:
    evidence = {
        "pinned_pricing": QualificationEvidence(
            EvidenceStatus.PASS,
            preset.pricing_source,
            "The BYOT catalog pins positive input and output rates to this snapshot.",
        ),
        "stable_provider_evidence": QualificationEvidence(
            EvidenceStatus.PASS,
            preset.pricing_source,
            "The preset is limited to the provider-owned HTTPS endpoint.",
        ),
        "durable_idempotency": QualificationEvidence(
            EvidenceStatus.UNPROVEN,
            preset.pricing_source,
            "Durable provider idempotency is not established for this adapter class.",
        ),
        "hidden_retries_disabled": QualificationEvidence(
            EvidenceStatus.UNPROVEN,
            preset.pricing_source,
            "Provider-side hidden retry behavior is not established.",
        ),
        "authoritative_reconciliation": QualificationEvidence(
            EvidenceStatus.UNPROVEN,
            preset.pricing_source,
            "No authoritative charge reconciliation endpoint is wired.",
        ),
    }
    return ProviderQualification(
        provider=preset.catalog_id,
        model=variant.model_id,
        operation=_OPERATION,
        checked_at=_CHECKED_AT,
        verdict=QualificationVerdict.REFUSED,
        evidence=evidence,
        provider_kind=preset.adapter_kind,
        endpoint=preset.default_base_url,
        chargeable_units=frozenset(rate.unit for rate in variant.rates),
        expires_at=_CATALOG_EXPIRES_AT,
    )


def route_authority_catalog_entries() -> tuple[RouteAuthorityCatalogEntry, ...]:
    entries: list[RouteAuthorityCatalogEntry] = []
    for preset in BYOT_PROVIDER_PRESETS:
        for variant in preset.models:
            identity = ProviderRouteIdentity(
                provider_kind=preset.adapter_kind,
                model_id=variant.model_id,
                endpoint=preset.default_base_url,
                seam_id=_SEAM_ID,
                operation=_OPERATION,
            )
            cost = CostCatalogEntry(
                seam_id=_SEAM_ID,
                provider=preset.catalog_id,
                model=variant.model_id,
                operation=_OPERATION,
                rates=variant.rates,
                snapshot=variant.snapshot,
                expires_at=_CATALOG_EXPIRES_AT,
                assumptions=(
                    "rate row is pinned from the 2026-08 BYOT onboarding spec",
                    "cached-input discounts are excluded from the ceiling projection",
                    "hard-ceiling adapter qualification remains unproven",
                ),
            )
            entries.append(
                RouteAuthorityCatalogEntry(identity, cost, _qualification(preset, variant))
            )
    return tuple(entries)


__all__ = [
    "BYOT_PROVIDER_PRESETS",
    "ByotModelVariant",
    "ByotProviderPreset",
    "ProviderCatalogId",
    "canonical_catalog_id",
    "get_model_variant",
    "get_provider_preset",
    "route_authority_catalog_entries",
]
