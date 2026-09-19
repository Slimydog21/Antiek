"""NotDiamond advisory posture for Settings — offline product surface.

Grounded in campaign VERDICT.md (2026-07-09):

* Advisory router: GO (measured wedge only)
* Authoritative dispatch: REJECT under §16

This module never calls NotDiamond cloud APIs and never claims ND owns
dispatch. Kill-switch env ``ANTIEK_NOTDIAMOND``: ``0``/empty/false → off
(default); any other non-empty value means advisory integration *may* be
enabled when Wave-1 ships — still not authority.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

# Env kill-switch (default off). Matches VERDICT.md executable path note.
ANTIEK_NOTDIAMOND_ENV = "ANTIEK_NOTDIAMOND"

# Stable campaign verdict — hard to vary without operator unlock docs.
ADVISORY_VERDICT = "GO"
AUTHORITY_VERDICT = "REJECT"
VERDICT_SOURCE = "docs/htmlspec/notdiamond-verdict/VERDICT.md"
VERDICT_DATE = "2026-07-09"


def kill_switch_enabled() -> bool:
    """True only when operator explicitly enables ND advisory experiments.

    Default is **off** (unset, empty, ``0``, ``false``, ``off``, ``no``).
    """
    raw = (os.environ.get(ANTIEK_NOTDIAMOND_ENV) or "").strip().lower()
    return raw not in ("", "0", "false", "off", "no", "disabled")


def resolve_advisory_suggestion(
    *,
    store: Any | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Return no ND suggestion until measured ND evidence is joined explicitly.

    Antiek-bench is separate comparative evidence, not a substitute NotDiamond
    recommendation. A static model placeholder must never become installable.
    """
    _ = store
    suggestion: dict[str, Any] = {
        "suggested_model_id": None,
        "suggested_provider_id": None,
        "suggestion_source": "notdiamond_advisory.not_measured",
        "suggestion_week_id": (week_id or "").strip() or None,
        "measurement_status": "NOT MEASURED",
        "notdiamond_is_dispatch_authority": False,
        "installable": False,
    }
    return suggestion


def notdiamond_advisory_payload(
    *,
    include_html: bool = False,
    store: Any | None = None,
    week_id: str | None = None,
) -> dict[str, Any]:
    """Public Settings entry: structured advisory posture (offline).

    Checkable fields:
    * ``advisory_allowed`` — True (verdict GO for advisory wedge)
    * ``authority_allowed`` / ``authority_rejected`` — False / True
    * ``dispatch_owner`` — never ``notdiamond``
    * ``kill_switch_enabled`` — from env
    * ``suggested_model_id`` — advisory only (residual br)
    * ``view_format`` — html
    """
    enabled = kill_switch_enabled()
    suggestion = resolve_advisory_suggestion(store=store, week_id=week_id)
    payload: dict[str, Any] = {
        "advisory_allowed": True,
        "advisory_verdict": ADVISORY_VERDICT,
        "authority_allowed": False,
        "authority_rejected": True,
        "authority_verdict": AUTHORITY_VERDICT,
        "dispatch_owner": "hermes_primary_plus_decision_tree",
        "notdiamond_is_dispatch_authority": False,
        "kill_switch_env": ANTIEK_NOTDIAMOND_ENV,
        "kill_switch_enabled": enabled,
        "default_off": True,
        "view_format": "html",
        "settings_panel": "notdiamond_advisory",
        "source": VERDICT_SOURCE,
        "verdict_date": VERDICT_DATE,
        "suggested_model_id": suggestion.get("suggested_model_id"),
        "suggested_provider_id": suggestion.get("suggested_provider_id"),
        "suggestion_source": suggestion.get("suggestion_source"),
        "suggestion_week_id": suggestion.get("suggestion_week_id"),
        "measurement_status": suggestion.get("measurement_status"),
        "recommended_mean_score": suggestion.get("recommended_mean_score"),
        "installable": bool(suggestion.get("installable")),
        "notes": [
            "Advisory GO (measured wedge only) — recommend model/tier; call-site may ignore.",
            "Authority REJECT under §16 — NotDiamond must not own dispatch.",
            "Kill-switch ANTIEK_NOTDIAMOND defaults off; enabling does not grant authority.",
            "Missing ND evidence is NOT MEASURED and cannot be installed.",
            "Antiek-bench is comparative evidence, never relabeled as a NotDiamond suggestion.",
        ],
    }
    if include_html:
        payload["html"] = project_notdiamond_advisory_html(payload)
    return payload


def project_notdiamond_advisory_html(payload: dict[str, Any] | None = None) -> str:
    """HTML-first human view of NotDiamond advisory posture (never PDF)."""
    from substrate.engagement_spine.project import project_to_html

    p = payload or notdiamond_advisory_payload(include_html=False)
    lines = [
        f"Advisory verdict: {p.get('advisory_verdict')} (allowed={p.get('advisory_allowed')})",
        f"Authority verdict: {p.get('authority_verdict')} "
        f"(rejected={p.get('authority_rejected')}; is_dispatch_authority="
        f"{p.get('notdiamond_is_dispatch_authority')})",
        f"Dispatch owner: {p.get('dispatch_owner')}",
        f"Kill-switch {p.get('kill_switch_env')}: "
        f"{'enabled' if p.get('kill_switch_enabled') else 'off (default)'}",
        f"Suggested model (advisory): {p.get('suggested_model_id') or '—'} "
        f"via {p.get('suggestion_source') or '—'}",
        f"Measurement status: {p.get('measurement_status') or 'NOT MEASURED'}",
        f"Source: {p.get('source')} ({p.get('verdict_date')})",
        "view: HTML — NotDiamond is not the dispatch authority.",
    ]
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "NotDiamond advisory posture"}],
        }
    ]
    for line in lines:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": line}],
            }
        )
    for note in p.get("notes") or []:
        blocks.append(
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": str(note)}],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="notdiamond-advisory",
        creator="notdiamond_advisory",
    )


def campaign_verdict_path() -> Path:
    """Path to campaign VERDICT.md relative to platform tree when present."""
    # platform/worktrees/... or platform/ → docs/htmlspec/...
    here = Path(__file__).resolve()
    # substrate/notdiamond_advisory.py → parents[1] = platform root (or worktree)
    root = here.parents[1]
    return root / "docs" / "htmlspec" / "notdiamond-verdict" / "VERDICT.md"
