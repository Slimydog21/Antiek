"""Current-time execution qualification for derived revision companions."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from .provider_qualification import EvidenceStatus, load_provider_qualifications

SCHEMA_VERSION: Final = "antiek.derived-companion-execution.v1"
_DIMENSIONS: Final = (
    "pinned_pricing",
    "durable_idempotency",
    "hidden_retries_disabled",
    "authoritative_reconciliation",
    "stable_provider_evidence",
)


def project_derived_companion_execution(
    *, derived_asset_id: str, revision_id: str, content_sha256: str,
    generation: int, qualification_path: Path | None = None,
) -> dict[str, Any]:
    """Project checked provider evidence without granting spend authority."""
    scope = {"derived_asset_id": derived_asset_id, "revision_id": revision_id,
             "content_sha256": content_sha256, "generation": generation}
    try:
        qualifications = (load_provider_qualifications() if qualification_path is None
                          else load_provider_qualifications(qualification_path))
    except (OSError, TypeError, ValueError):
        return _projection(scope, reason="qualification_registry_invalid", routes=[])
    routes = []
    for qualification in sorted(qualifications, key=lambda item: item.route_key):
        blocking = [dimension for dimension in _DIMENSIONS
                    if qualification.evidence[dimension].status is not EvidenceStatus.PASS]
        routes.append({"provider": qualification.provider, "model": qualification.model,
                       "operation": qualification.operation,
                       "checked_at": qualification.checked_at,
                       "verdict": qualification.verdict.value,
                       "blocking_dimensions": blocking})
    reason = ("executable_route_not_registered"
              if any(item.fully_qualified for item in qualifications)
              else "no_provider_route_qualified")
    return _projection(scope, reason=reason, routes=routes)


def _projection(scope: dict[str, Any], *, reason: str,
                routes: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "scope": scope, "available": False,
            "reservable": False, "dispatch_authorized": False, "reason": reason,
            "pricing_status": "unavailable", "recommended_ceiling_cents": None,
            "routes": routes}


__all__ = ["SCHEMA_VERSION", "project_derived_companion_execution"]
