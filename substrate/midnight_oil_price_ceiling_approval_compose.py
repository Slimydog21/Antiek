"""Midnight Oil price-ceiling recommendation → approval → unattended pack (pure).

live_execution_authorized and charge_executed always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from substrate.midnight_oil_launch_package_compose import (
    MidnightOilLaunchPackageComposeError,
    MidnightOilPriceCeilingRecommend,
    recommend_midnight_oil_price_ceiling,
)
from substrate.midnight_oil_unattended_package_compose import (
    MidnightOilUnattendedPackageCompose,
    MidnightOilUnattendedPackageComposeError,
    compose_midnight_oil_unattended_package,
)

MoPriceCeilingStage = Literal[
    "recommend_only", "approve_ceiling", "unattended_pack"
]
VALID_STAGES = frozenset(
    ("recommend_only", "approve_ceiling", "unattended_pack")
)


class MidnightOilPriceCeilingApprovalComposeError(ValueError):
    """Fail-closed validation for MO price ceiling approval flow."""


@dataclass(frozen=True)
class MidnightOilPriceCeilingApprovalCompose:
    operator_id: str
    stage: MoPriceCeilingStage
    recommend: MidnightOilPriceCeilingRecommend
    approved_ceiling_usd: float | None
    ceiling_approved: bool
    unattended: MidnightOilUnattendedPackageCompose | None
    pack_ready: bool
    live_execution_authorized: bool
    charge_executed: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "operator_id": self.operator_id,
            "stage": self.stage,
            "recommend": self.recommend.to_dict(),
            "approved_ceiling_usd": self.approved_ceiling_usd,
            "ceiling_approved": self.ceiling_approved,
            "unattended": self.unattended.to_dict() if self.unattended else None,
            "pack_ready": self.pack_ready,
            "live_execution_authorized": False,
            "charge_executed": False,
            "notes": list(self.notes),
            "authority": (
                "midnight_oil_price_ceiling_approval_compose_advisory"
            ),
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MidnightOilPriceCeilingApprovalComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_positive_finite(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise MidnightOilPriceCeilingApprovalComposeError(
            f"{field} must be a positive finite number"
        )
    f = float(value)
    if not (f > 0) or f != f:  # NaN check
        raise MidnightOilPriceCeilingApprovalComposeError(
            f"{field} must be a positive finite number"
        )
    return f


def compose_midnight_oil_price_ceiling_approval(
    *,
    operator_id: object,
    work_minutes: object,
    goals: object,
    price_ceiling_ack: object,
    operator_ack: object,
    stage: object,
    usd_per_hour: object | None = None,
    goal_intensity: object | None = None,
    approved_ceiling_usd: object | None = None,
    below_recommend_override: object | None = None,
    unattended_ack: object | None = None,
    spend_consent: object | None = None,
) -> MidnightOilPriceCeilingApprovalCompose:
    """Recommend → approve ceiling → optional unattended pack. Never launches."""
    if not isinstance(price_ceiling_ack, bool):
        raise MidnightOilPriceCeilingApprovalComposeError(
            "price_ceiling_ack must be an explicit boolean"
        )
    if not isinstance(operator_ack, bool):
        raise MidnightOilPriceCeilingApprovalComposeError(
            "operator_ack must be an explicit boolean"
        )
    if stage not in VALID_STAGES:
        raise MidnightOilPriceCeilingApprovalComposeError(
            "stage must be recommend_only|approve_ceiling|unattended_pack"
        )
    stage_s: MoPriceCeilingStage = stage  # type: ignore[assignment]
    op = _require_nonempty(operator_id, field="operator_id")
    minutes = _require_positive_finite(work_minutes, field="work_minutes")
    if not isinstance(goals, list) or len(goals) == 0:
        raise MidnightOilPriceCeilingApprovalComposeError(
            "goals must be a non-empty array"
        )

    notes: list[str] = [
        "live_execution_authorized=false — MO never launches from pure pack",
        "charge_executed=false — recommended ceiling is advisory only",
        "system recommends; operator must approve ceiling before unattended pack",
    ]

    try:
        recommend = recommend_midnight_oil_price_ceiling(
            work_minutes=minutes,
            goal_count=len(goals),
            usd_per_hour=usd_per_hour,
            goal_intensity=goal_intensity,
        )
    except MidnightOilLaunchPackageComposeError as e:
        raise MidnightOilPriceCeilingApprovalComposeError(str(e)) from e
    notes.extend(f"[recommend] {n}" for n in recommend.notes)

    approved: float | None = None
    if approved_ceiling_usd is not None:
        if not isinstance(approved_ceiling_usd, (int, float)) or isinstance(
            approved_ceiling_usd, bool
        ):
            raise MidnightOilPriceCeilingApprovalComposeError(
                "approved_ceiling_usd must be non-negative finite when set"
            )
        approved = float(approved_ceiling_usd)
        if approved != approved or approved < 0:
            raise MidnightOilPriceCeilingApprovalComposeError(
                "approved_ceiling_usd must be non-negative finite when set"
            )
        notes.append(f"approved_ceiling_usd={approved}")
    else:
        notes.append("approved_ceiling_usd=null — operator has not set a ceiling")

    override = False if below_recommend_override is None else below_recommend_override
    if not isinstance(override, bool):
        raise MidnightOilPriceCeilingApprovalComposeError(
            "below_recommend_override must be boolean when set"
        )

    ceiling_approved = False
    if stage_s == "recommend_only":
        notes.append(
            "stage=recommend_only — show recommended ceiling; no approval required yet"
        )
    else:
        if not price_ceiling_ack:
            notes.append(
                "ceiling_approved=false — price_ceiling_ack required after reviewing recommendation"
            )
        elif approved is None:
            notes.append(
                "ceiling_approved=false — approved_ceiling_usd required to approve"
            )
        elif (
            recommend.recommended_ceiling_usd is not None
            and approved + 1e-9 < recommend.recommended_ceiling_usd
            and not override
        ):
            notes.append(
                f"ceiling_approved=false — approved ${approved} < recommended "
                f"${recommend.recommended_ceiling_usd}; set below_recommend_override=true to force"
            )
        elif not operator_ack:
            notes.append(
                "ceiling_approved=false — operator_ack required with ceiling approval"
            )
        else:
            ceiling_approved = True
            if (
                recommend.recommended_ceiling_usd is not None
                and approved + 1e-9 < recommend.recommended_ceiling_usd
                and override
            ):
                notes.append(
                    "ceiling_approved=true with below_recommend_override "
                    "(operator accepted lower ceiling)"
                )
            else:
                notes.append(
                    "ceiling_approved=true — operator accepted recommended or higher ceiling"
                )

    unattended: MidnightOilUnattendedPackageCompose | None = None
    if stage_s == "unattended_pack":
        if not isinstance(unattended_ack, bool):
            raise MidnightOilPriceCeilingApprovalComposeError(
                "unattended_ack must be an explicit boolean when stage=unattended_pack"
            )
        if not isinstance(spend_consent, bool):
            raise MidnightOilPriceCeilingApprovalComposeError(
                "spend_consent must be an explicit boolean when stage=unattended_pack"
            )
        if not ceiling_approved:
            notes.append(
                "unattended pack deferred — ceiling not approved under policy"
            )
        else:
            try:
                unattended = compose_midnight_oil_unattended_package(
                    operator_id=op,
                    work_minutes=minutes,
                    goals=goals,
                    operator_ack=operator_ack,
                    unattended_ack=unattended_ack,
                    spend_consent=spend_consent,
                    usd_per_hour=usd_per_hour,
                    approved_ceiling_usd=approved,
                )
            except MidnightOilUnattendedPackageComposeError as e:
                raise MidnightOilPriceCeilingApprovalComposeError(
                    str(e)
                ) from e
            notes.extend(f"[unattended] {n}" for n in unattended.notes)

    if stage_s == "recommend_only":
        pack_ready = True
        notes.append(
            "pack_ready=true — recommendation surface ready (advisory only)"
        )
    elif stage_s == "approve_ceiling":
        pack_ready = ceiling_approved
        notes.append(
            "pack_ready=true — ceiling approval intent ready; charge_executed=false"
            if pack_ready
            else "pack_ready=false — ceiling approval gates open"
        )
    else:
        pack_ready = (
            ceiling_approved is True
            and unattended is not None
            and unattended.unattended_package_ready is True
        )
        notes.append(
            "pack_ready=true — ceiling approved + unattended package ready; "
            "still no live execution"
            if pack_ready
            else "pack_ready=false — ceiling or unattended package gates open"
        )

    if unattended is not None and unattended.live_execution_authorized is not False:
        raise MidnightOilPriceCeilingApprovalComposeError(
            "invariant: live_execution_authorized must remain false"
        )

    notes.extend(
        (
            "live_execution_authorized=false",
            "charge_executed=false",
        )
    )

    return MidnightOilPriceCeilingApprovalCompose(
        operator_id=op,
        stage=stage_s,
        recommend=recommend,
        approved_ceiling_usd=approved,
        ceiling_approved=ceiling_approved,
        unattended=unattended,
        pack_ready=pack_ready,
        live_execution_authorized=False,
        charge_executed=False,
        notes=tuple(notes),
        authority="midnight_oil_price_ceiling_approval_compose_advisory",
    )


def format_midnight_oil_price_ceiling_approval_summary(
    c: MidnightOilPriceCeilingApprovalCompose,
) -> str:
    rec = c.recommend.recommended_ceiling_usd
    rec_s = "null" if rec is None else f"${rec}"
    app_s = (
        "null"
        if c.approved_ceiling_usd is None
        else f"${c.approved_ceiling_usd}"
    )
    return (
        f"pack_ready={c.pack_ready} · stage={c.stage} · "
        f"recommended={rec_s} · approved={app_s} · "
        f"ceiling_approved={c.ceiling_approved} · "
        f"live_execution_authorized=false · charge_executed=false"
    )


__all__ = [
    "MidnightOilPriceCeilingApprovalCompose",
    "MidnightOilPriceCeilingApprovalComposeError",
    "compose_midnight_oil_price_ceiling_approval",
    "format_midnight_oil_price_ceiling_approval_summary",
]
