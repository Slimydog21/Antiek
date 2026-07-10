"""Env-gated live hydrate adapter wiring (residual bk).

Opt-in only. Default remains offline identity-only hydrate.

Env flags (truthy: 1/true/yes/on):

* ``ANTIEK_HYDRATE_LIVE_ARXIV=1`` — wire ``acquisition.arxiv.client.fetch_by_id``
* ``ANTIEK_HYDRATE_LIVE_SUBSTACK=1`` — wire a feed-free post fetcher only if a
  custom factory is provided (Substack full-page fetch is ToS-sensitive;
  live default is NOT auto-enabled beyond explicit inject).

This module never enables silent network for Substack by default; arXiv live
is only enabled when the env flag is set and the import succeeds.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import Callable
from typing import Any

from .hydrate_adapters import (
    arxiv_metadata_fetch_publication,
    compose_fetch_publication,
    substack_post_fetch_publication,
)

_TRUTHY = frozenset({"1", "true", "yes", "on"})

ANTIEK_HYDRATE_LIVE_ARXIV_ENV = "ANTIEK_HYDRATE_LIVE_ARXIV"
ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV = "ANTIEK_HYDRATE_LIVE_SUBSTACK"


def env_flag(name: str, *, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(name) or "").strip().lower()
    return raw in _TRUTHY


def build_live_arxiv_fetch_by_id() -> Callable[[str], Any]:
    """Return acquisition.arxiv.client.fetch_by_id (may import httpx stack)."""
    from acquisition.arxiv.client import fetch_by_id

    def _wrapped(arxiv_id: str) -> Any:
        return fetch_by_id(arxiv_id)

    return _wrapped


def configure_engagement_hydrate_injectors(
    eng_mod: Any,
    *,
    environ: dict[str, str] | None = None,
    substack_fetch_post: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    """Configure engagement_routes injectors from env (+ optional substack factory).

    Returns a report of what was enabled. Does not enable anything unless flags set.
    """
    report: dict[str, Any] = {
        "arxiv_live": False,
        "substack_live": False,
        "notes": [],
        "view_format": "html",
        "source": "engagement_spine.hydrate_live_wiring",
    }

    # Reset optional injectors first for deterministic re-configure
    eng_mod.hydrate_arxiv_fetch_by_id = None
    eng_mod.hydrate_substack_fetch_post = None

    if env_flag(ANTIEK_HYDRATE_LIVE_ARXIV_ENV, environ=environ):
        try:
            eng_mod.hydrate_arxiv_fetch_by_id = build_live_arxiv_fetch_by_id()
            report["arxiv_live"] = True
            report["notes"].append(
                f"{ANTIEK_HYDRATE_LIVE_ARXIV_ENV} enabled — arXiv Atom metadata fetch wired."
            )
        except Exception as exc:
            report["notes"].append(f"arXiv live wiring failed: {exc}")
    else:
        report["notes"].append(
            f"{ANTIEK_HYDRATE_LIVE_ARXIV_ENV} unset/false — arXiv hydrate remains offline."
        )

    if env_flag(ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV, environ=environ):
        if substack_fetch_post is not None:
            eng_mod.hydrate_substack_fetch_post = substack_fetch_post
            report["substack_live"] = True
            report["notes"].append(
                f"{ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV} enabled with provided fetch_post factory."
            )
        else:
            report["notes"].append(
                f"{ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV} set but no fetch_post factory provided "
                "(refuse auto live Substack page scrape; inject factory explicitly)."
            )
    else:
        report["notes"].append(
            f"{ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV} unset/false — Substack hydrate remains offline."
        )

    return report


def live_fetch_publication_from_env(
    *,
    environ: dict[str, str] | None = None,
    substack_fetch_post: Callable[[str], Any] | None = None,
) -> Any | None:
    """Compose a fetch_publication callable from env flags (or None)."""
    adapters = []
    if env_flag(ANTIEK_HYDRATE_LIVE_ARXIV_ENV, environ=environ):
        with contextlib.suppress(Exception):
            adapters.append(
                arxiv_metadata_fetch_publication(
                    fetch_by_id=build_live_arxiv_fetch_by_id()
                )
            )
    if env_flag(ANTIEK_HYDRATE_LIVE_SUBSTACK_ENV, environ=environ) and substack_fetch_post:
        adapters.append(
            substack_post_fetch_publication(fetch_post=substack_fetch_post)
        )
    if not adapters:
        return None
    return compose_fetch_publication(*adapters)
