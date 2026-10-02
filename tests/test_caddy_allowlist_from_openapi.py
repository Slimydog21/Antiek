"""The Caddy allowlist must cover every route FastAPI actually serves.

WHY THIS FILE EXISTS ALONGSIDE test_caddy_allowlist_coverage.py. That file
derives the route set with regexes over the source. Three things in this tree
defeat that, and each one produced a WRONG answer during the 2026-09-20 audit:

* Routers are built by factories -- ``thread.py: make_router()`` returns an
  APIRouter that is included inline, so no ``name = APIRouter(...)`` binding
  exists to read a prefix from.
* Routers nest. ``multimedia_router.include_router(assets_router)`` composes
  both prefixes with no ``prefix=`` at the include call, so a scanner that
  resolves only a router's own prefix reports ``/assets/{id}/...`` for a route
  really mounted at ``/multimedia/assets/{id}/...``. That single mistake
  invented ~40 unreachable routes that do not exist.
* The app wraps included routers in a custom ``_IncludedRouter`` whose
  children do not surface as top-level ``.path`` entries, and the prefix is
  baked into child paths for some routers but not others.

``app.openapi()`` is FastAPI's own answer to "what does this app serve", so it
is immune to all three. It was unusable until the PublisherClaimRequest scope
fix (tests/test_openapi_schema_builds.py) -- ``app.openapi()`` raised, which
is exactly why the earlier attempt fell back to regexes and got it wrong.

WHAT A FAILURE HERE MEANS. Caddy serves any path outside ``@api_routes`` the
SPA HTML shell with HTTP 200. The request never reaches uvicorn and the client
cannot tell it failed -- it gets a page instead of JSON, with a success code.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from interfaces.research.api.app import create_app

_CADDYFILE = (
    Path(__file__).resolve().parents[1]
    / "infrastructure" / "ansible" / "templates" / "Caddyfile.j2"
)


def _allowlist_tokens() -> list[str]:
    """The raw Caddy ``path`` tokens, unreduced.

    Reduction is what made the sibling segment-level checks blind: collapsing
    ``/api/ad/*`` and ``/api/notebooks/{id}/artifact`` both to ``/api`` lets a
    narrow token vouch for an entire first segment.
    """
    text = _CADDYFILE.read_text(encoding="utf-8")
    match = re.search(r"@api_routes path (.+)", text)
    assert match, "could not find the @api_routes line in the Caddyfile template"
    tokens = match.group(1).split()
    assert len(tokens) > 20, f"implausibly few allowlist tokens: {tokens}"
    return tokens


def _served_paths() -> list[str]:
    spec: dict[str, Any] = create_app().openapi()
    paths = sorted(spec.get("paths", {}))
    assert len(paths) > 100, (
        f"openapi reported only {len(paths)} paths — the schema likely failed "
        "to build, which would make this check vacuous"
    )
    return paths


def _matches(path: str, token: str) -> bool:
    """Caddy's ``path`` matcher: a trailing ``*`` is a prefix, else exact."""
    concrete = re.sub(r"\{[^}]+\}", "x", path)
    if token.endswith("*"):
        return concrete.startswith(token[:-1])
    return concrete == token


def _covered(path: str, tokens: list[str]) -> bool:
    return any(_matches(path, t) for t in tokens)


def test_openapi_enumeration_is_usable() -> None:
    """Guard the guard: if the schema stops building, fail loudly here."""
    paths = _served_paths()
    assert "/health" in paths, f"/health missing from the schema: {len(paths)} paths"


def test_every_served_path_is_reachable_through_caddy() -> None:
    tokens = _allowlist_tokens()
    missing = [p for p in _served_paths() if not _covered(p, tokens)]
    assert not missing, (
        "these paths are served by the API but match NO token in the Caddy "
        "@api_routes allowlist, so production answers them with the SPA HTML "
        f"shell and HTTP 200: {missing}. Add a covering token to "
        "infrastructure/ansible/templates/Caddyfile.j2."
    )


def test_check_is_not_vacuous() -> None:
    """A removed token must be detected, or this file proves nothing."""
    tokens = [t for t in _allowlist_tokens() if t != "/auth/*"]
    missing = [p for p in _served_paths() if not _covered(p, tokens)]
    assert missing, (
        "dropping /auth/* from the allowlist produced no uncovered path — the "
        "coverage check cannot detect a missing token and is vacuous"
    )
