"""CI drift-guard: every FastAPI route prefix MUST be in the Caddy
``@api_routes`` allowlist, or Caddy serves the SPA HTML for that path in prod
instead of proxying to uvicorn — silently breaking the API.

The allowlist is a hand-maintained ONE-LINE ``path`` matcher in
``infrastructure/ansible/templates/Caddyfile.j2`` (Caddy's tokenizer can't span
lines). Because it's hand-maintained, it DRIFTS: it shipped missing
``/library`` + ``/api/ad/*`` (SPR-09) and ``/books /coordination /corpus
/meta-readings /speech`` — each a registered route the prod edge couldn't reach,
discovered only by curling prod after deploy. This guard makes that drift a red
CI check at the source, not a production surprise.
"""

from __future__ import annotations

import glob
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
_API_DIR = os.path.join(_REPO, "interfaces", "research", "api")
_CADDY = os.path.join(
    _REPO, "infrastructure", "ansible", "templates", "Caddyfile.j2"
)

# Routes deliberately NOT proxied to uvicorn (e.g. SPA-only paths). Empty
# today — every registered API route should be reachable through the edge. If
# a future route is intentionally SPA-only, add its top-level prefix here WITH
# a one-line reason, so the exclusion is explicit and reviewed.
_ALLOWLIST_EXCEPTIONS: set[str] = set()

# FastAPI framework routes are not declared in interfaces/research/api/*.py, so
# the prefix scanner below cannot infer them. Keep them explicit because missing
# one sends API tooling to the SPA HTML shell in production.
_FRAMEWORK_API_PATHS: set[str] = {"/openapi.json"}

_DECORATOR = re.compile(
    r"""@app\.(?:get|post|put|delete|patch|websocket)\(\s*["']([^"']+)["']"""
)
# Standalone APIRouters register top-level prefixes the @app scanner misses
# (e.g. multimedia_router = APIRouter(prefix="/multimedia") — live prod gap).
_ROUTER_PREFIX = re.compile(
    r"""APIRouter\(\s*(?:[^)]*?\bprefix\s*=\s*["']([^"']+)["'])"""
)


def _top_prefix(path: str) -> str:
    seg = path.strip("/").split("/")[0].split("{")[0].strip("/")
    return "/" + seg if seg else "/"


def _registered_prefixes() -> set[str]:
    out: set[str] = set()
    for f in glob.glob(os.path.join(_API_DIR, "*.py")):
        with open(f, encoding="utf-8") as fh:
            src = fh.read()
        for m in _DECORATOR.finditer(src):
            p = _top_prefix(m.group(1))
            if p != "/":
                out.add(p)
        for m in _ROUTER_PREFIX.finditer(src):
            p = _top_prefix(m.group(1))
            if p != "/":
                out.add(p)
    return out


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
        f"are not discoverable from app decorators: {missing}. Missing paths "
        "would return SPA HTML instead of uvicorn JSON in prod."
    )


def test_drift_guard_is_not_vacuous() -> None:
    # If parsing silently broke (empty sets), the coverage test would pass
    # vacuously. Pin both sides to be non-trivially populated so a regex/file
    # regression reddens here instead of hiding the real gap.
    assert len(_registered_prefixes()) >= 40
    assert len(_allowlist_prefixes()) >= 40


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
