"""Env-gated boot wiring for live twin seed note_taker (residual cb).

Default: do nothing (offline seed remains).
When ``ANTIEK_TWIN_SEED_LIVE=1`` **and** ``ANTIEK_TWIN_SEED_USE_DISPATCH=1``,
attempts to install a dispatch-backed seed fn. Failures are recorded in the
report; offline seed still works as fallback inside ``seed_twins_for_asset``.
"""

from __future__ import annotations

import os
from typing import Any

from .twin import (
    ANTIEK_TWIN_SEED_LIVE_ENV,
    configure_twin_seed_live,
    twin_seed_live_enabled,
)

ANTIEK_TWIN_SEED_USE_DISPATCH_ENV = "ANTIEK_TWIN_SEED_USE_DISPATCH"
_TRUTHY = frozenset({"1", "true", "yes", "on"})


def env_flag(name: str, *, environ: dict[str, str] | None = None) -> bool:
    env = environ if environ is not None else os.environ
    raw = str(env.get(name) or "").strip().lower()
    return raw in _TRUTHY


def build_dispatch_note_taker_seed_fn() -> Any:
    """Build a seed fn that calls note_taker role when available.

    Returns pairs of (kind, text). On any failure raises so seed_twins falls
    back to offline stubs (caller catches).
    """

    def _fn(title: str, body: str) -> list[tuple[str, str]]:
        # Prefer roles.note_taker if importable; otherwise raise → offline fallback
        try:
            from roles.note_taker.parser import parse_notes_response
        except Exception as exc:
            raise RuntimeError(f"note_taker unavailable: {exc}") from exc

        prompt = (
            f"Asset: {title}\n\nBody preview:\n{(body or '')[:2000]}\n\n"
            "Extract 1–3 insights and 1–3 open questions as notes."
        )
        try:
            from substrate.dispatch import dispatch

            result = dispatch(
                prompt,
                "note_taker",
                investigation_id=f"twin_seed:{title.strip()[:64]}",
            )
            text = (
                result
                if isinstance(result, str)
                else getattr(result, "text", None)
                or getattr(result, "content", None)
                or str(result)
            )
            notes = parse_notes_response(str(text))
        except Exception as exc:
            raise RuntimeError(f"dispatch note_taker failed: {exc}") from exc

        pairs: list[tuple[str, str]] = []
        for n in notes or []:
            kind = getattr(n, "kind", None) or (n.get("kind") if isinstance(n, dict) else None)
            content = getattr(n, "text", None) or getattr(n, "content", None)
            if content is None and isinstance(n, dict):
                content = n.get("text") or n.get("content")
            k = str(kind or "").lower()
            if "question" in k:
                pairs.append(("question", str(content or "").strip()))
            elif content:
                pairs.append(("insight", str(content or "").strip()))
        if not pairs:
            raise RuntimeError("note_taker returned no parseable notes")
        return pairs

    return _fn


def configure_twin_seed_from_env(
    *,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Install live twin seed inject when both env flags are on.

    Returns honesty report. Never installs when live env is off.
    """
    report: dict[str, Any] = {
        "live_env": twin_seed_live_enabled()
        if environ is None
        else env_flag(ANTIEK_TWIN_SEED_LIVE_ENV, environ=environ),
        "use_dispatch": env_flag(ANTIEK_TWIN_SEED_USE_DISPATCH_ENV, environ=environ),
        "installed": False,
        "notes": [],
        "view_format": "html",
        "source": "engagement_spine.twin_seed_live_wiring",
    }
    live = (
        twin_seed_live_enabled()
        if environ is None
        else env_flag(ANTIEK_TWIN_SEED_LIVE_ENV, environ=environ)
    )
    if not live:
        report["notes"].append(
            f"{ANTIEK_TWIN_SEED_LIVE_ENV} off (default) — offline twin seed only."
        )
        return report
    if not env_flag(ANTIEK_TWIN_SEED_USE_DISPATCH_ENV, environ=environ):
        report["notes"].append(
            f"{ANTIEK_TWIN_SEED_LIVE_ENV} on but "
            f"{ANTIEK_TWIN_SEED_USE_DISPATCH_ENV} off — "
            "operator must configure_twin_seed_live(fn) manually."
        )
        return report
    try:
        configure_twin_seed_live(build_dispatch_note_taker_seed_fn())
        report["installed"] = True
        report["notes"].append(
            "Dispatch-backed note_taker twin seed installed (env dual-gate)."
        )
    except Exception as exc:
        report["notes"].append(f"live twin seed install failed: {exc}")
    return report
