"""
Discovery endpoints for agent callers.

Two surfaces:

  1. ``/openapi.json`` — FastAPI exposes this automatically (no work
     required here; we document it for the contract). Listed in
     :func:`discovery_summary` so a caller can find it.

  2. ``/.well-known/mcp.json`` — an MCP-tool-manifest view of the same
     surface, generated on demand from the FastAPI app's route table.
     Lets an MCP-aware agent discover the substrate's callable surface
     without prior knowledge.

To wire into the app (one line in ``app.py`` when the operator gets
to it; deliberately additive — no modification of existing routes)::

    from interfaces.research.api.discovery import router as discovery_router
    app.include_router(discovery_router)

Then ``GET /.well-known/mcp.json`` and ``GET /discovery`` work; the
existing ``GET /openapi.json`` is unchanged (FastAPI auto-exposes it).

Spec: ~/specs/antiek-yegge-execute/sprint-09-agent-loved-api.html
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Request

router = APIRouter(tags=["discovery"])


def _route_to_mcp_tool(route: Any, *, base_url: str) -> Dict[str, Any]:
    """Translate a FastAPI route into an MCP-manifest tool entry.

    The translation is intentionally lossy: MCP's tool shape is much
    simpler than OpenAPI's, so we extract the name, method, path,
    summary, and input parameters. Callers who want the full schema
    use ``/openapi.json``; MCP gets the quick-look view.
    """
    methods = sorted(getattr(route, "methods", set()) or {"GET"})
    # MCP tools are conventionally one-verb-per-tool; if a route handles
    # multiple methods we surface the first (sorted alphabetically) and
    # note the others in the description.
    primary_method = methods[0]
    other_methods = methods[1:]

    path = getattr(route, "path", "/")
    endpoint = getattr(route, "endpoint", None)
    summary = getattr(route, "summary", None) or (
        endpoint.__doc__.strip().splitlines()[0] if endpoint and endpoint.__doc__ else ""
    )

    extra_note = (
        f" (also accepts: {', '.join(other_methods)})" if other_methods else ""
    )

    return {
        "name": f"{primary_method}_{path}".replace("/", "_").strip("_"),
        "method": primary_method,
        "path": path,
        "url": f"{base_url.rstrip('/')}{path}",
        "summary": (summary + extra_note).strip(),
        # Parameter extraction is best-effort; agents needing
        # exhaustive schemas should pull /openapi.json.
        "parameters": _extract_params(route),
    }


def _extract_params(route: Any) -> List[Dict[str, Any]]:
    """Best-effort: pull path + query param names from the route.

    For full type info, callers consult ``/openapi.json``. This is
    only the quick-look agent-discovery view.
    """
    params: List[Dict[str, Any]] = []
    for dep in getattr(route, "dependant", None) and route.dependant.path_params or []:
        params.append({"name": dep.name, "in": "path",
                       "required": True, "type": "string"})
    for dep in getattr(route, "dependant", None) and route.dependant.query_params or []:
        params.append({"name": dep.name, "in": "query",
                       "required": dep.required, "type": "string"})
    return params


@router.get("/.well-known/mcp.json")
async def mcp_manifest(request: Request) -> Dict[str, Any]:
    """Return an MCP-tool-manifest view of this app's REST surface.

    The shape is intentionally close to the MCP spec's tool entry but
    simplified for discovery purposes — agents that need exhaustive
    schemas use ``/openapi.json``.
    """
    base_url = str(request.base_url)
    tools: List[Dict[str, Any]] = []
    # Iterate the app's routes — skip the discovery route itself and
    # any internal FastAPI routes that begin with "/openapi" or
    # "/docs" (the human-facing OpenAPI UI; agents don't need it).
    for route in request.app.routes:
        path = getattr(route, "path", "") or ""
        if path.startswith(("/openapi", "/docs", "/redoc", "/.well-known")):
            continue
        if not hasattr(route, "methods"):  # WebSocket, Mount, etc.
            continue
        tools.append(_route_to_mcp_tool(route, base_url=base_url))

    return {
        "mcp_version": "0.1",  # informal; matches Antiek's MCP-first stance
        "name": "antiek-research",
        "description": (
            "Antiek research substrate REST surface as MCP tools. "
            "For full schemas use /openapi.json."
        ),
        "openapi_url": f"{base_url.rstrip('/')}/openapi.json",
        "tools": tools,
    }


@router.get("/discovery")
async def discovery_summary(request: Request) -> Dict[str, Any]:
    """Index of discovery surfaces for agent callers."""
    base_url = str(request.base_url)
    return {
        "openapi": f"{base_url.rstrip('/')}/openapi.json",
        "mcp_manifest": f"{base_url.rstrip('/')}/.well-known/mcp.json",
        "envelope_convention": (
            "New routes return ResponseEnvelope[T]. See "
            "interfaces/research/api/envelope.py for the contract. "
            "Legacy routes return raw FastAPI shapes (migration is "
            "future-batch)."
        ),
        "idempotency": (
            "POST/PUT routes that opt in require an Idempotency-Key "
            "header. See interfaces/research/api/idempotency.py."
        ),
    }


__all__ = ["router"]
