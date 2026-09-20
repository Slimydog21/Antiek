"""Provider routing seam for multimedia generation.

SPR-03 builds the provider and cost gate before any expensive media calls. Krea
is the first visual provider, but routing is deliberately a product contract:
the user can choose ``cheapest``, ``balanced``, or ``highest_quality`` and see a
deterministic cost/quality plan before execution.

Krea API facts reviewed 2026-07-07 from the public docs:

* API key is provided as ``KREA_API_KEY`` and sent as ``Authorization: Bearer``.
* The feature API exposes assets, async jobs, webhooks, image generation, video
  generation, and upscale model families.
* Asset upload limit is documented as 75 MB.
* CI must not require a paid call; live execution here is only via an injected
  transport, so tests can prove request/cost/response handling without a key.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator

from substrate.contracts.multimedia import CostRow, GeneratedFile, ProviderCall, RoutePolicy

GenerationKind = Literal["image", "image_to_video", "video"]
ProviderName = Literal["krea", "local_placeholder"]
ProviderPlanStatus = Literal["dry_run", "ready", "requires_confirmation"]

KREA_API_KEY_ENV = "KREA_API_KEY"
KREA_ASSET_UPLOAD_LIMIT_MB = 75


class _RouterBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MultimediaProviderError(RuntimeError):
    """Base class for typed provider failures."""

    retryable: bool = False
    code: str = "provider_error"


class ProviderUnavailable(MultimediaProviderError):
    retryable = False
    code = "provider_unconfigured"


class ProviderUpstreamError(MultimediaProviderError):
    retryable = True
    code = "provider_upstream_error"


class BudgetExceeded(MultimediaProviderError):
    retryable = False
    code = "budget_exceeded"


class ProviderCapability(_RouterBase):
    provider: ProviderName
    kinds: tuple[GenerationKind, ...]
    auth_env_var: str | None = None
    max_asset_upload_mb: int | None = None
    output_mimes: tuple[str, ...] = Field(default_factory=tuple)
    notes: str


class MediaGenerationRequest(_RouterBase):
    kind: GenerationKind
    prompt: str = Field(min_length=1)
    route_policy: RoutePolicy = "balanced"
    duration_seconds: float | None = Field(default=None, ge=0)
    width_px: int | None = Field(default=None, ge=1)
    height_px: int | None = Field(default=None, ge=1)
    budget_usd: float | None = Field(default=None, ge=0)
    dry_run: bool = True
    seed: int | None = None

    @model_validator(mode="after")
    def duration_required_for_video(self) -> MediaGenerationRequest:
        if self.kind in {"image_to_video", "video"} and self.duration_seconds is None:
            raise ValueError("video generation requests require duration_seconds")
        return self

    def resolution_or_default(self) -> tuple[int, int]:
        if self.width_px and self.height_px:
            return (self.width_px, self.height_px)
        return _ROUTE_RESOLUTION[self.route_policy]


class ProviderRoute(_RouterBase):
    provider: ProviderName
    model: str
    route_policy: RoutePolicy
    quality_label: Literal["draft", "standard", "premium"]
    estimated_cost_usd: float = Field(ge=0)
    resolution: tuple[int, int] | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    reason: str
    status: ProviderPlanStatus = "dry_run"
    requires_confirmation: bool = False


class ProviderExecutionRecord(_RouterBase):
    """The auditable result of a provider call."""

    provider_call: ProviderCall
    cost_row: CostRow
    files: tuple[GeneratedFile, ...] = Field(default_factory=tuple)
    raw_job_id: str | None = None


class ProviderTransport(Protocol):
    def __call__(self, request: MediaGenerationRequest, route: ProviderRoute) -> Mapping[str, Any]:
        """Execute one provider call and return normalized provider data."""


KREA_CAPABILITY = ProviderCapability(
    provider="krea",
    kinds=("image", "image_to_video", "video"),
    auth_env_var=KREA_API_KEY_ENV,
    max_asset_upload_mb=KREA_ASSET_UPLOAD_LIMIT_MB,
    output_mimes=("image/png", "image/jpeg", "video/mp4"),
    notes=(
        "Public docs expose assets, async jobs, webhooks, image generation, "
        "video generation, and upscale families. Live calls require KREA_API_KEY."
    ),
)

LOCAL_PLACEHOLDER_CAPABILITY = ProviderCapability(
    provider="local_placeholder",
    kinds=("image", "image_to_video", "video"),
    auth_env_var=None,
    max_asset_upload_mb=None,
    output_mimes=("text/plain",),
    notes=(
        "Zero-cost dry-run fallback used to compare against Krea and to keep "
        "CI/provider planning free."
    ),
)

_BASE_PRICE_BY_KIND: dict[GenerationKind, float] = {
    "image": 0.02,
    "image_to_video": 0.18,
    "video": 0.30,
}
_ROUTE_MULTIPLIER: dict[RoutePolicy, float] = {
    "cheapest": 0.0,
    "balanced": 1.0,
    "highest_quality": 2.25,
}
_ROUTE_RESOLUTION: dict[RoutePolicy, tuple[int, int]] = {
    "cheapest": (640, 360),
    "balanced": (1280, 720),
    "highest_quality": (1920, 1080),
}


def provider_capabilities() -> tuple[ProviderCapability, ...]:
    return (KREA_CAPABILITY, LOCAL_PLACEHOLDER_CAPABILITY)


def route_media_request(request: MediaGenerationRequest) -> ProviderRoute:
    """Return the deterministic provider/model/resolution/cost plan."""

    if request.route_policy == "cheapest":
        route = ProviderRoute(
            provider="local_placeholder",
            model="dry-run-placeholder",
            route_policy=request.route_policy,
            quality_label="draft",
            estimated_cost_usd=0.0,
            resolution=request.resolution_or_default(),
            duration_seconds=request.duration_seconds,
            reason="Cheapest tier uses a zero-cost placeholder for approval before paid media.",
            status="dry_run",
            requires_confirmation=False,
        )
    elif request.route_policy == "balanced":
        route = ProviderRoute(
            provider="krea",
            model=_model_for(request.kind, request.route_policy),
            route_policy=request.route_policy,
            quality_label="standard",
            estimated_cost_usd=_estimate_cost(request),
            resolution=request.resolution_or_default(),
            duration_seconds=request.duration_seconds,
            reason="Balanced tier uses Krea standard settings for cost/quality trade-off.",
            status="dry_run" if request.dry_run else "ready",
        )
    else:
        route = ProviderRoute(
            provider="krea",
            model=_model_for(request.kind, request.route_policy),
            route_policy=request.route_policy,
            quality_label="premium",
            estimated_cost_usd=_estimate_cost(request),
            resolution=request.resolution_or_default(),
            duration_seconds=request.duration_seconds,
            reason="Highest-quality tier spends more for larger/longer Krea outputs.",
            status="dry_run" if request.dry_run else "ready",
        )
    _enforce_budget(request, route)
    return route


class KreaProviderAdapter:
    """Krea adapter shell.

    Live execution is intentionally transport-injected. Production can wire a
    transport that uses the Krea SDK/API; tests pass a fake transport. Without a
    transport this adapter supports dry-run planning only.
    """

    name: ProviderName = "krea"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        env: Mapping[str, str] | None = None,
        transport: ProviderTransport | None = None,
    ) -> None:
        source = env if env is not None else os.environ
        self._api_key = api_key if api_key is not None else source.get(KREA_API_KEY_ENV)
        self._transport = transport

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def dry_run(self, request: MediaGenerationRequest) -> ProviderRoute:
        return route_media_request(request.model_copy(update={"dry_run": True}))

    def execute(self, request: MediaGenerationRequest) -> ProviderExecutionRecord:
        live_request = request.model_copy(update={"dry_run": False})
        route = route_media_request(live_request)
        if route.provider != "krea":
            return _placeholder_record(live_request, route)
        if not self.configured:
            raise ProviderUnavailable(f"{KREA_API_KEY_ENV} is required for live Krea generation")
        if self._transport is None:
            raise ProviderUnavailable("Krea transport is not configured; dry-run is available")

        try:
            raw = self._transport(live_request, route)
        except MultimediaProviderError:
            raise
        except Exception as exc:  # provider/network failures are retryable.
            raise ProviderUpstreamError(str(exc)) from exc
        return _execution_record(live_request, route, raw)


def _model_for(kind: GenerationKind, route_policy: RoutePolicy) -> str:
    suffix = "pro" if route_policy == "highest_quality" else "standard"
    default = {
        "image": f"krea-image-{suffix}",
        "image_to_video": f"krea-image-to-video-{suffix}",
        "video": f"krea-video-{suffix}",
    }[kind]
    # Lineup binding (media actions): the operator's lineup assignment for
    # the kind's action wins when it names a krea-family model in the
    # action's allowed set; anything else keeps the deterministic default.
    from substrate.dispatch.lineup_override import effective_model_for_action
    action_id = {
        "image": "image_generation",
        "image_to_video": "video_generation",
        "video": "video_generation",
    }[kind]
    return effective_model_for_action(action_id, provider_family="krea", default=default)


def _estimate_cost(request: MediaGenerationRequest) -> float:
    base = _BASE_PRICE_BY_KIND[request.kind]
    multiplier = _ROUTE_MULTIPLIER[request.route_policy]
    duration_factor = 1.0
    if request.kind in {"image_to_video", "video"}:
        duration_factor = max(1.0, (request.duration_seconds or 0) / 5.0)
    return round(base * multiplier * duration_factor, 4)


def _enforce_budget(request: MediaGenerationRequest, route: ProviderRoute) -> None:
    if request.budget_usd is not None and route.estimated_cost_usd > request.budget_usd:
        raise BudgetExceeded(
            f"estimated cost ${route.estimated_cost_usd:.4f} exceeds budget "
            f"${request.budget_usd:.4f}"
        )


def _execution_record(
    request: MediaGenerationRequest,
    route: ProviderRoute,
    raw: Mapping[str, Any],
) -> ProviderExecutionRecord:
    call_id = str(raw.get("call_id") or _stable_id("call", request.prompt, route.model))
    prompt_id = _stable_id("prompt", request.prompt, route.model)
    cost = float(raw.get("cost_usd", route.estimated_cost_usd))
    file_rows = tuple(_files_from_raw(raw.get("files", ()), route, prompt_id))
    return ProviderExecutionRecord(
        provider_call=ProviderCall(
            call_id=call_id,
            provider=route.provider,
            model=route.model,
            prompt_id=prompt_id,
            route_policy=route.route_policy,
            status="succeeded",
            input_units=1,
            output_units=len(file_rows),
            unit_type=request.kind,
            cost_usd=cost,
            latency_ms=_int_or_none(raw.get("latency_ms")),
        ),
        cost_row=CostRow(
            cost_id=_stable_id("cost", call_id, str(cost)),
            call_id=call_id,
            provider=route.provider,
            route_policy=route.route_policy,
            cost_usd=cost,
            billable_units=float(raw.get("billable_units", 1)),
            unit_type=request.kind,
        ),
        files=file_rows,
        raw_job_id=str(raw.get("job_id")) if raw.get("job_id") is not None else None,
    )


def _placeholder_record(
    request: MediaGenerationRequest,
    route: ProviderRoute,
) -> ProviderExecutionRecord:
    call_id = _stable_id("call", request.prompt, "placeholder")
    return ProviderExecutionRecord(
        provider_call=ProviderCall(
            call_id=call_id,
            provider=route.provider,
            model=route.model,
            prompt_id=_stable_id("prompt", request.prompt, route.model),
            route_policy=route.route_policy,
            status="skipped",
            unit_type=request.kind,
            cost_usd=0,
        ),
        cost_row=CostRow(
            cost_id=_stable_id("cost", call_id, "0"),
            call_id=call_id,
            provider=route.provider,
            route_policy=route.route_policy,
            cost_usd=0,
            unit_type=request.kind,
        ),
        files=(),
    )


def _files_from_raw(
    rows: Any,
    route: ProviderRoute,
    prompt_id: str,
) -> list[GeneratedFile]:
    files: list[GeneratedFile] = []
    if not isinstance(rows, (list, tuple)):
        return files
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            continue
        uri = str(row.get("storage_uri") or row.get("url") or "")
        sha = str(row.get("sha256") or "")
        mime = str(row.get("mime") or ("video/mp4" if "video" in route.model else "image/png"))
        if not uri or not sha:
            continue
        files.append(
            GeneratedFile(
                file_id=str(row.get("file_id") or f"file-{index}"),
                kind="video" if mime.startswith("video/") else "image",
                storage_uri=uri,
                sha256=sha,
                mime=mime,
                provider=route.provider,
                prompt_id=prompt_id,
                duration_seconds=route.duration_seconds,
                width_px=route.resolution[0] if route.resolution else None,
                height_px=route.resolution[1] if route.resolution else None,
            )
        )
    return files


def _stable_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "BudgetExceeded",
    "GenerationKind",
    "KREA_API_KEY_ENV",
    "KREA_ASSET_UPLOAD_LIMIT_MB",
    "KREA_CAPABILITY",
    "KreaProviderAdapter",
    "LOCAL_PLACEHOLDER_CAPABILITY",
    "MediaGenerationRequest",
    "MultimediaProviderError",
    "ProviderCapability",
    "ProviderExecutionRecord",
    "ProviderRoute",
    "ProviderTransport",
    "ProviderUnavailable",
    "ProviderUpstreamError",
    "provider_capabilities",
    "route_media_request",
]
