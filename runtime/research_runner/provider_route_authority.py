"""Exact, server-owned execution authority for user-selected provider routes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from .cost_projection import CostCatalogEntry
from .provider_gateway import HardCeilingProviderAdapter
from .provider_qualification import EvidenceStatus, ProviderQualification


class RouteExecutionStatus(StrEnum):
    EXECUTABLE = "executable"
    BLOCKED_UNKNOWN_PRICING = "blocked_unknown_pricing"
    BLOCKED_IDEMPOTENCY_UNPROVEN = "blocked_idempotency_unproven"
    BLOCKED_RECONCILIATION_UNPROVEN = "blocked_reconciliation_unproven"
    BLOCKED_HIDDEN_RETRIES = "blocked_hidden_retries"
    BLOCKED_QUALIFICATION = "blocked_provider_qualification"
    BLOCKED_SELECTION_AUTHORITY = "blocked_selection_authority"
    BLOCKED_NO_ADAPTER = "blocked_no_hard_ceiling_adapter"
    BLOCKED_ADAPTER_MISMATCH = "blocked_hard_ceiling_adapter_mismatch"


def canonical_provider_endpoint(value: str) -> str:
    """Canonicalize a credential-free provider API root."""
    parsed = urlsplit(value)
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("provider endpoint must be a credential-free HTTP(S) URL")
    host = parsed.hostname.lower()
    scheme = parsed.scheme.lower()
    port = parsed.port
    default_port = 443 if scheme == "https" else 80
    rendered_host = f"[{host}]" if ":" in host else host
    netloc = (
        f"{rendered_host}:{port}" if port not in (None, default_port) else rendered_host
    )
    path = parsed.path.rstrip("/")
    return urlunsplit((scheme, netloc, path, "", ""))


@dataclass(frozen=True, slots=True)
class ProviderRouteIdentity:
    provider_kind: str
    model_id: str
    endpoint: str
    seam_id: str
    operation: str

    def __post_init__(self) -> None:
        if not all((self.provider_kind, self.model_id, self.seam_id, self.operation)):
            raise ValueError("provider route identity fields must be non-empty")
        object.__setattr__(self, "endpoint", canonical_provider_endpoint(self.endpoint))


@dataclass(frozen=True, slots=True)
class ProviderRouteAuthority:
    identity: ProviderRouteIdentity
    pricing_status: Literal["known", "unknown"]
    rate_snapshot: str | None
    hard_ceiling_eligible: bool
    execution_status: RouteExecutionStatus


@dataclass(frozen=True, slots=True)
class RouteAuthorityCatalogEntry:
    identity: ProviderRouteIdentity
    cost: CostCatalogEntry
    qualification: ProviderQualification

    def __post_init__(self) -> None:
        if not self.identity.endpoint.startswith("https://"):
            raise ValueError("paid route authority requires an HTTPS endpoint")
        if (self.cost.seam_id, self.cost.model, self.cost.operation) != (
            self.identity.seam_id,
            self.identity.model_id,
            self.identity.operation,
        ):
            raise ValueError("route authority cost entry differs from exact identity")
        if self.qualification.route_key != (
            self.cost.provider,
            self.cost.model,
            self.cost.operation,
        ):
            raise ValueError("route authority qualification differs from cost route")
        units = [rate.unit for rate in self.cost.rates]
        if len(units) != len(set(units)):
            raise ValueError("route authority cost entry repeats a billing unit")


AdapterLookup = Callable[[str], object | None]


@dataclass(frozen=True, slots=True)
class _AdapterRegistration:
    provider_id: str
    adapter: HardCeilingProviderAdapter[object]


class ProviderRouteAuthorityResolver:
    """Join exact route, price, qualification, and live adapter authority."""

    def __init__(
        self,
        entries: tuple[RouteAuthorityCatalogEntry, ...] = (),
        *,
        adapter_lookup: AdapterLookup | None = None,
    ) -> None:
        keys = [entry.identity for entry in entries]
        if len(keys) != len(set(keys)):
            raise ValueError("provider route authority contains duplicate identities")
        self._entries = {entry.identity: entry for entry in entries}
        self._adapters: dict[ProviderRouteIdentity, _AdapterRegistration] = {}
        self._adapter_lookup = adapter_lookup or (lambda _provider_id: None)

    def register_adapter(
        self,
        identity: ProviderRouteIdentity,
        provider_id: str,
        adapter: HardCeilingProviderAdapter[object],
    ) -> None:
        if not provider_id:
            raise ValueError("provider id must be non-empty")
        if (adapter.provider, adapter.model) != (provider_id, identity.model_id):
            raise ValueError("hard-ceiling adapter differs from exact route")
        self._adapters[identity] = _AdapterRegistration(provider_id, adapter)

    def resolve(
        self,
        identity: ProviderRouteIdentity,
        *,
        provider_id: str,
        now: datetime | None = None,
    ) -> ProviderRouteAuthority:
        entry = self._entries.get(identity)
        if entry is None or not self._pricing_known(entry.cost, now=now):
            return self._blocked(identity, RouteExecutionStatus.BLOCKED_UNKNOWN_PRICING)

        evidence = entry.qualification.evidence
        if not entry.cost.durable_idempotency or evidence.get("durable_idempotency") is None or evidence[
            "durable_idempotency"
        ].status is not EvidenceStatus.PASS:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_IDEMPOTENCY_UNPROVEN,
                entry.cost.snapshot,
            )
        if not entry.cost.authoritative_reconciliation or evidence.get(
            "authoritative_reconciliation"
        ) is None or evidence[
            "authoritative_reconciliation"
        ].status is not EvidenceStatus.PASS:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_RECONCILIATION_UNPROVEN,
                entry.cost.snapshot,
            )
        if not entry.cost.hidden_retries_disabled or evidence.get(
            "hidden_retries_disabled"
        ) is None or evidence[
            "hidden_retries_disabled"
        ].status is not EvidenceStatus.PASS:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_HIDDEN_RETRIES,
                entry.cost.snapshot,
            )
        if not entry.qualification.fully_qualified:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_QUALIFICATION,
                entry.cost.snapshot,
            )
        registration = self._adapters.get(identity)
        if registration is None:
            return self._blocked(
                identity, RouteExecutionStatus.BLOCKED_NO_ADAPTER, entry.cost.snapshot
            )
        if registration.provider_id != provider_id:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH,
                entry.cost.snapshot,
            )
        adapter = registration.adapter
        if self._adapter_lookup(provider_id) is not adapter:
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH,
                entry.cost.snapshot,
            )
        if (adapter.provider, adapter.model) != (provider_id, identity.model_id):
            return self._blocked(
                identity,
                RouteExecutionStatus.BLOCKED_ADAPTER_MISMATCH,
                entry.cost.snapshot,
            )
        capabilities = adapter.capabilities
        if not capabilities.durable_idempotency:
            status = RouteExecutionStatus.BLOCKED_IDEMPOTENCY_UNPROVEN
        elif not capabilities.authoritative_reconciliation:
            status = RouteExecutionStatus.BLOCKED_RECONCILIATION_UNPROVEN
        elif not capabilities.hidden_retries_disabled:
            status = RouteExecutionStatus.BLOCKED_HIDDEN_RETRIES
        else:
            return ProviderRouteAuthority(
                identity=identity,
                pricing_status="known",
                rate_snapshot=entry.cost.snapshot,
                hard_ceiling_eligible=True,
                execution_status=RouteExecutionStatus.EXECUTABLE,
            )
        return self._blocked(identity, status, entry.cost.snapshot)

    @staticmethod
    def _pricing_known(cost: CostCatalogEntry, *, now: datetime | None) -> bool:
        resolved_now = now or datetime.now(UTC)
        if resolved_now.tzinfo is None:
            resolved_now = resolved_now.replace(tzinfo=UTC)
        expires_at = cost.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return bool(
            cost.paid_service
            and cost.currency == "USD"
            and resolved_now < expires_at
            and cost.rates
            and all(rate.usd_per_unit.is_finite() and rate.usd_per_unit > 0 for rate in cost.rates)
        )

    @staticmethod
    def _blocked(
        identity: ProviderRouteIdentity,
        status: RouteExecutionStatus,
        rate_snapshot: str | None = None,
    ) -> ProviderRouteAuthority:
        return ProviderRouteAuthority(
            identity=identity,
            pricing_status="known" if rate_snapshot is not None else "unknown",
            rate_snapshot=rate_snapshot,
            hard_ceiling_eligible=False,
            execution_status=status,
        )


EMPTY_PROVIDER_ROUTE_AUTHORITY = ProviderRouteAuthorityResolver()


__all__ = [
    "EMPTY_PROVIDER_ROUTE_AUTHORITY",
    "ProviderRouteAuthority",
    "ProviderRouteAuthorityResolver",
    "ProviderRouteIdentity",
    "RouteAuthorityCatalogEntry",
    "RouteExecutionStatus",
    "canonical_provider_endpoint",
]
