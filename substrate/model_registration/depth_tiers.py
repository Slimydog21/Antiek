"""Depth-tier presets for decision-tree driver selection (residual at).

Competitive map (Perplexity speed vs OpenAI depth) productized as three
operator-facing depth tiers:

* ``flash`` — fast / cheap path (maps to distill task class + flash dispatch tier)
* ``pro`` — balanced default (synthesize + pro)
* ``wrestle`` — long-horizon thorough research (wrestle + pro, larger output budget)

Does **not** reimplement #440 cost math. Returns projection *hints* that Settings
feeds into ``POST /settings/prompt-cost-estimate``. Process-local active tier
(same honesty as decision-tree install).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

DepthTier = Literal["flash", "pro", "wrestle"]

_VALID: frozenset[str] = frozenset({"flash", "pro", "wrestle"})

# Process-local active depth tier (mirrors decision-tree process registry).
_active_depth_tier: DepthTier | None = None


@dataclass(frozen=True)
class DepthTierPreset:
    depth_tier: DepthTier
    label: str
    description: str
    dispatch_tier: str
    task_class: str
    default_input_chars: int
    default_expected_output_tokens: int
    competitor_posture: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "depth_tier": self.depth_tier,
            "label": self.label,
            "description": self.description,
            "dispatch_tier": self.dispatch_tier,
            "task_class": self.task_class,
            "default_input_chars": self.default_input_chars,
            "default_expected_output_tokens": self.default_expected_output_tokens,
            "competitor_posture": self.competitor_posture,
        }


_PRESETS: dict[str, DepthTierPreset] = {
    "flash": DepthTierPreset(
        depth_tier="flash",
        label="Flash",
        description="Fast deep-research path — shorter outputs, lower cost ceiling.",
        dispatch_tier="flash",
        task_class="distill",
        default_input_chars=1500,
        default_expected_output_tokens=400,
        competitor_posture="Perplexity-class speed",
    ),
    "pro": DepthTierPreset(
        depth_tier="pro",
        label="Pro",
        description="Balanced research depth — default workstation driver posture.",
        dispatch_tier="pro",
        task_class="synthesize",
        default_input_chars=4000,
        default_expected_output_tokens=1200,
        competitor_posture="OpenAI/Gemini balanced report",
    ),
    "wrestle": DepthTierPreset(
        depth_tier="wrestle",
        label="Wrestle",
        description="Long-horizon thorough research — large output budget, wrestle task class.",
        dispatch_tier="pro",
        task_class="wrestle",
        default_input_chars=8000,
        default_expected_output_tokens=4000,
        competitor_posture="OpenAI Deep Research depth",
    ),
}


def list_depth_tiers() -> list[DepthTierPreset]:
    return [_PRESETS[k] for k in ("flash", "pro", "wrestle")]


def get_depth_tier_preset(depth_tier: str) -> DepthTierPreset:
    key = str(depth_tier or "").strip().lower()
    if key not in _VALID:
        raise ValueError(
            f"invalid depth_tier {depth_tier!r}; expected one of {sorted(_VALID)}"
        )
    return _PRESETS[key]


def set_active_depth_tier(depth_tier: str) -> DepthTierPreset:
    """Install process-local depth tier; returns preset."""
    global _active_depth_tier
    preset = get_depth_tier_preset(depth_tier)
    _active_depth_tier = preset.depth_tier
    return preset


def get_active_depth_tier() -> DepthTier | None:
    return _active_depth_tier


def clear_active_depth_tier() -> None:
    global _active_depth_tier
    _active_depth_tier = None


def apply_depth_tier(
    depth_tier: str,
    *,
    model_id: str | None = None,
    provider_id: str | None = None,
    install_driver: bool = False,
) -> dict[str, Any]:
    """Select depth tier and optionally install decision-tree driver.

    When ``install_driver`` and ``model_id`` are set, calls
    ``install_decision_tree_selection`` so dispatch and depth stay aligned.
    Cost projection remains #440 — this returns hints only.
    """
    preset = set_active_depth_tier(depth_tier)
    notes: list[str] = [
        f"Active depth tier set to {preset.depth_tier} (process-local).",
        "Cost projection uses #440 estimate_prompt_cost with returned hints.",
    ]
    install_result: dict[str, Any] | None = None
    mid = (model_id or "").strip() or None
    if install_driver and mid:
        from .install import install_decision_tree_selection

        result = install_decision_tree_selection(
            mid, provider_id=provider_id, ensure_registered=True
        )
        install_result = result.to_dict()
        notes.append(f"Decision-tree driver installed: {mid}")
    elif install_driver and not mid:
        notes.append(
            "install_driver requested but no model_id — depth tier only (no driver change)."
        )

    return {
        "depth_tier": preset.depth_tier,
        "preset": preset.to_dict(),
        "projection_hints": {
            "tier": preset.dispatch_tier,
            "input_chars": preset.default_input_chars,
            "expected_output_tokens": preset.default_expected_output_tokens,
            "task_class": preset.task_class,
        },
        "decision_tree_install": install_result,
        "view_format": "html",
        "settings_panel": "depth_tier_presets",
        "source": "substrate.model_registration.depth_tiers",
        "notes": notes,
    }


def depth_tiers_settings_payload(*, include_html: bool = False) -> dict[str, Any]:
    """Settings GET shape: list presets + active tier."""
    active = get_active_depth_tier()
    presets = [p.to_dict() for p in list_depth_tiers()]
    payload: dict[str, Any] = {
        "active_depth_tier": active,
        "presets": presets,
        "view_format": "html",
        "settings_panel": "depth_tier_presets",
        "source": "substrate.model_registration.depth_tiers",
        "notes": [
            "Depth tiers are process-local like decision-tree install.",
            "Budget projection remains #440; use projection_hints on apply.",
        ],
    }
    if active:
        payload["active_preset"] = get_depth_tier_preset(active).to_dict()
        payload["projection_hints"] = {
            "tier": get_depth_tier_preset(active).dispatch_tier,
            "input_chars": get_depth_tier_preset(active).default_input_chars,
            "expected_output_tokens": get_depth_tier_preset(
                active
            ).default_expected_output_tokens,
            "task_class": get_depth_tier_preset(active).task_class,
        }
    else:
        payload["active_preset"] = None
        payload["projection_hints"] = None
        payload["notes"].append("No depth tier selected yet.")
    if include_html:
        payload["html"] = project_depth_tiers_html(payload)
    return payload


def project_depth_tiers_html(payload: dict[str, Any]) -> str:
    from substrate.engagement_spine.project import project_to_html

    active = payload.get("active_depth_tier") or "(none)"
    blocks: list[dict[str, Any]] = [
        {
            "type": "heading",
            "attrs": {"level": 1},
            "content": [{"type": "text", "text": "Depth-tier presets"}],
        },
        {
            "type": "paragraph",
            "content": [
                {
                    "type": "text",
                    "text": f"Active: {active} · view: HTML · process-local",
                }
            ],
        },
    ]
    for p in payload.get("presets") or []:
        if not isinstance(p, dict):
            continue
        blocks.append(
            {
                "type": "paragraph",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            f"{p.get('depth_tier')}: {p.get('label')} — "
                            f"dispatch={p.get('dispatch_tier')} "
                            f"task={p.get('task_class')} "
                            f"out_tokens={p.get('default_expected_output_tokens')} "
                            f"({p.get('competitor_posture')})"
                        ),
                    }
                ],
            }
        )
    return project_to_html(
        {"type": "doc", "content": blocks},
        document_id="depth-tier-presets",
        creator="model_registration.depth_tiers",
    )
