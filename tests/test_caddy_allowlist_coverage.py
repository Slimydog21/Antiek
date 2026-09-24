"""CI drift-guard: every path FastAPI actually serves MUST be matched by the
Caddy ``@api_routes`` allowlist, or Caddy serves the SPA HTML for that path in
prod instead of proxying to uvicorn — silently breaking the API.

The allowlist is a hand-maintained ONE-LINE ``path`` matcher in
``infrastructure/ansible/templates/Caddyfile.j2`` (Caddy's tokenizer can't span
lines). Because it's hand-maintained, it DRIFTS: it shipped missing
``/library`` + ``/api/ad/*`` (SPR-09), ``/books /coordination /corpus
/meta-readings /speech``, and then ``/styles`` + ``/artifacts`` — each a
registered route the prod edge couldn't reach, discovered only by curling prod
after deploy. This guard makes that drift a red CI check at the source, not a
production surprise.

WHERE THE ROUTE SET COMES FROM. The real routing table, via
``create_app().openapi()`` plus the websocket routes the schema omits — NOT a
regex over the source. The regex scanner this replaced matched
``@app.<verb>("...")`` decorators and ``APIRouter(prefix="...")`` literals, so
a prefix-less router (``style_router = APIRouter(tags=["styles"])`` carrying
``@style_router.get("/styles")``) was invisible to it: the whole style wheel
sat dead at the edge for its entire deployed life while this file stayed
green. The same scanner mis-resolved factory-built routers
(``thread.py: make_router()``) and nested ``include_router`` prefixes.
``app.openapi()`` is FastAPI's own answer to "what does this app serve", so it
is immune to all three.
"""

from __future__ import annotations

import functools
import os
import re

import pytest
from fastapi.routing import APIWebSocketRoute

from interfaces.research.api.app import create_app

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_CADDY = os.path.join(
    _REPO, "infrastructure", "ansible", "templates", "Caddyfile.j2"
)

# Routes deliberately NOT proxied to uvicorn (e.g. SPA-only paths). Empty
# today — every registered API route should be reachable through the edge. If
# a future route is intentionally SPA-only, add its top-level prefix here WITH
# a one-line reason, so the exclusion is explicit and reviewed.
_ALLOWLIST_EXCEPTIONS: set[str] = set()

# FastAPI framework routes are not part of the schema the app publishes about
# itself, so the served-path enumeration below cannot see them. Keep them
# explicit because missing one sends API tooling to the SPA HTML shell in
# production.
_FRAMEWORK_API_PATHS: set[str] = {"/openapi.json"}

# A silent collapse of the served-path set — the schema failing to build, a
# refactor that empties the enumeration — must fail here rather than let the
# coverage checks pass over nothing. The regex scanner it replaced saw 62
# prefixes and ~100 decorator paths; the routing table reports 350+.
_MIN_SERVED_PATHS = 100


def _top_prefix(path: str) -> str:
    seg = path.strip("/").split("/")[0].split("{")[0].strip("/")
    return "/" + seg if seg else "/"


@functools.lru_cache(maxsize=1)
def _served_paths() -> tuple[str, ...]:
    """Every path the app serves, read off the routing table itself.

    ``app.openapi()`` enumerates every HTTP operation FastAPI mounted —
    routers included without a prefix, factory-built routers, nested
    includes — because it walks the same route objects the request router
    does. It omits websocket endpoints, so those are read off ``app.routes``
    directly: the edge has to proxy ``/ws/*`` too. Built once per session,
    since constructing the app takes seconds.
    """
    app = create_app()
    paths = set(app.openapi().get("paths", {}))
    paths.update(r.path for r in app.routes if isinstance(r, APIWebSocketRoute))
    return tuple(sorted(paths))


def _registered_prefixes() -> set[str]:
    return {_top_prefix(p) for p in _served_paths()} - {"/"}


def _allowlist_prefixes() -> set[str]:
    with open(_CADDY, encoding="utf-8") as fh:
        line = next(line_text for line_text in fh if "@api_routes path" in line_text)
    toks = line.split()[2:]  # tokens after "@api_routes" "path"
    # tokens are glob prefixes like "/ad-impressions*" or "/api/ad/*" — strip
    # the trailing "*" AND reduce to the top-level segment before comparing.
    return {
        "/" + t.strip("/").rstrip("*").strip("/").split("/")[0]
        for t in toks
        if t.startswith("/")
    }


def _allowlist_paths() -> set[str]:
    with open(_CADDY, encoding="utf-8") as fh:
        line = next(line_text for line_text in fh if "@api_routes path" in line_text)
    return {t.rstrip("*") for t in line.split()[2:] if t.startswith("/")}


def test_caddy_allowlist_covers_every_registered_route() -> None:
    registered = _registered_prefixes()
    allow = _allowlist_prefixes()
    missing = sorted(
        p for p in registered if p not in allow and p not in _ALLOWLIST_EXCEPTIONS
    )
    assert not missing, (
        "Caddy @api_routes allowlist (infrastructure/ansible/templates/"
        "Caddyfile.j2) is MISSING these registered route prefixes — prod would "
        f"serve the SPA HTML for them instead of proxying to uvicorn: {missing}. "
        "Add each to the @api_routes path line (or, if a route is intentionally "
        "SPA-only, to _ALLOWLIST_EXCEPTIONS in this test with a reason)."
    )


def test_caddy_allowlist_covers_framework_api_paths() -> None:
    allow = _allowlist_paths()
    missing = sorted(path for path in _FRAMEWORK_API_PATHS if path not in allow)
    assert not missing, (
        "Caddy @api_routes allowlist is missing FastAPI framework paths that "
        f"are not discoverable from the app's own schema: {missing}. Missing "
        "paths would return SPA HTML instead of uvicorn JSON in prod."
    )


def test_drift_guard_is_not_vacuous(request: pytest.FixtureRequest) -> None:
    # If enumeration silently broke (empty sets), the coverage test would pass
    # vacuously. Pin both sides to be non-trivially populated so a schema/file
    # regression reddens here instead of hiding the real gap.
    served = _served_paths()
    assert len(served) >= _MIN_SERVED_PATHS, (
        f"only {len(served)} served paths discovered — the routing-table "
        "enumeration collapsed, and every coverage check above it is now "
        "comparing against nothing"
    )
    assert len(_registered_prefixes()) >= 40
    assert len(_allowlist_prefixes()) >= 40
    # Say the number out loud, even under -q: a run's own output should carry
    # the evidence that the floor was measured against a populated table.
    reporter = request.config.pluginmanager.get_plugin("terminalreporter")
    if reporter is not None:
        reporter.write_line(
            f"caddy drift-guard: {len(served)} served paths discovered via app.openapi()"
        )


def test_browser_navigation_never_swallows_auth_callbacks() -> None:
    """Email links navigate with ``Accept: text/html``.

    The SPA matcher must exclude the complete auth control plane so Caddy sends
    `/auth/callback` to FastAPI, where the token is verified and the session
    cookie is minted. This is intentionally source-shaped: it guards the Caddy
    matcher that caused the live failure, not a direct FastAPI test that bypasses
    the production proxy.
    """
    with open(_CADDY, encoding="utf-8") as fh:
        caddy = fh.read()

    matcher = re.search(r"@spa_browser_nav\s*\{(?P<body>.*?)\n\s*\}", caddy, re.DOTALL)
    assert matcher is not None, "@spa_browser_nav must remain an explicit matcher block"
    body = matcher.group("body")
    assert "header Accept *text/html*" in body
    assert "not path /auth/*" in body, (
        "browser-shaped /auth/callback requests would receive SPA index.html "
        "instead of reaching FastAPI"
    )


# ── Full-glob coverage (the sound check) ────────────────────────────────────
#
# Everything above compares TOP-LEVEL SEGMENTS: both sides reduce
# "/api/ad/*" and "/api/notebooks/{id}/artifact.html" to "/api". That makes a
# single narrow allowlist token vouch for an entire first segment, which is a
# false negative in exactly the direction that costs a production route.
#
# It did. The delta shipped GET /api/deliverables/{id}/artifact,
# /api/notebooks/{id}/artifact(.html) and /api/syntheses/{id}/artifact(.html)
# while the only /api glob in the Caddyfile was "/api/ad/*". All five were
# served the SPA shell at the edge, for every client, and the check above
# stayed green because "/api/ad/*" collapses to "/api".
#
# These compare the FULL glob the way Caddy's `path` matcher does. The
# segment-level tests are kept: they still catch a whole prefix going missing,
# and they are cheap.


def _allowlist_globs() -> list[str]:
    """The raw Caddy `path` tokens, unreduced."""
    with open(_CADDY, encoding="utf-8") as fh:
        line = next(t for t in fh if "@api_routes path" in t)
    return [t for t in line.split()[2:] if t.startswith("/")]


def _concrete(route: str) -> str:
    """Substitute a sample segment for each {param} so globs can be matched."""
    return re.sub(r"\{[^}]+\}", "x", route)


def _covered(route: str, globs: list[str]) -> bool:
    path = _concrete(route)
    for g in globs:
        if g.endswith("*"):
            if path.startswith(g[:-1]):
                return True
        elif path == g:
            return True
    return False


def test_every_registered_route_matches_a_full_caddy_glob() -> None:
    globs = _allowlist_globs()
    missing = sorted(r for r in _served_paths() if not _covered(r, globs))
    assert not missing, (
        "these served routes match NO glob in the Caddy @api_routes "
        f"allowlist, so production serves them the SPA HTML shell: {missing}. "
        "Add a covering glob to infrastructure/ansible/templates/Caddyfile.j2."
    )


def test_full_glob_check_is_not_vacuous() -> None:
    """Both sides must be non-trivially populated, and the matcher must work.

    The segment-level check above passed for months while five routes were
    dead at the edge; a coverage test that silently compares empty sets fails
    the same way.
    """
    routes = _served_paths()
    globs = _allowlist_globs()
    assert len(routes) >= _MIN_SERVED_PATHS, f"only {len(routes)} routes served"
    assert len(globs) >= 40, f"only {len(globs)} allowlist globs parsed"
    # The matcher must actually discriminate, not just return True.
    assert _covered("/health", ["/health"])
    assert _covered("/auth/callback", ["/auth/*"])
    assert not _covered("/api/notebooks/x/artifact", ["/api/ad/*"]), (
        "the matcher is collapsing prefixes again — /api/ad/* must not vouch "
        "for /api/notebooks/..."
    )
    # And a removed token must be detected, or the whole file proves nothing.
    without_auth = [g for g in globs if g != "/auth/*"]
    assert any(not _covered(r, without_auth) for r in routes), (
        "dropping /auth/* from the allowlist left every served path covered — "
        "the coverage check cannot detect a missing token"
    )
