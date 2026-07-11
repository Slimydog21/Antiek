"""Marketplace purchase intent gate (pure, fail-closed).

Operator intent: buy a digital book only when free PD/OA preflight found none
(or the operator explicitly skips free-copy with acknowledgment).

This module never:
* charges Stripe / wallet
* ports EPUB bytes
* invents a free-copy miss

Rules:
* title required non-empty
* free_copy_preflight must be a structured result (or skip path)
* freely_available=True → purchase_intent_allowed=False (use free path)
* freely_available=False → purchase_intent_allowed=True (advisory open)
* skip_free_copy requires operator_skip_acknowledged=True strict bool
* purchase_executed always False here (gate only)
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

MAX_TITLE = 512
MAX_AUTHOR = 512
MAX_STORE = 128


class PurchaseGateError(ValueError):
    """Fail-closed validation for marketplace purchase gate."""


@dataclass(frozen=True)
class PurchaseGateDecision:
    title: str
    author: str | None
    purchase_intent_allowed: bool
    purchase_executed: bool
    path: str
    reasons: tuple[str, ...]
    notes: tuple[str, ...]
    free_copy_freely_available: bool | None
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "author": self.author,
            "purchase_intent_allowed": self.purchase_intent_allowed,
            "purchase_executed": False,  # never invent executed purchase
            "path": self.path,
            "reasons": list(self.reasons),
            "notes": list(self.notes),
            "free_copy_freely_available": self.free_copy_freely_available,
            "authority": "purchase_gate_advisory",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise PurchaseGateError(f"{field} must be an explicit boolean")
    return value


def _clean_title(value: object) -> str:
    if not isinstance(value, str):
        raise PurchaseGateError("title must be a string")
    text = value.strip()
    if not text:
        raise PurchaseGateError("title must be non-empty")
    if len(text) > MAX_TITLE:
        raise PurchaseGateError(f"title exceeds {MAX_TITLE} chars")
    return text


def _clean_optional_str(value: object | None, *, field: str, max_len: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise PurchaseGateError(f"{field} must be a string or null")
    text = value.strip()
    if not text:
        return None
    if len(text) > max_len:
        raise PurchaseGateError(f"{field} exceeds {max_len} chars")
    return text


def evaluate_purchase_gate(
    *,
    title: object,
    author: object | None = None,
    free_copy_preflight: Mapping[str, Any] | None = None,
    skip_free_copy: object = False,
    operator_skip_acknowledged: object | None = None,
    store: object | None = None,
) -> PurchaseGateDecision:
    """Decide whether purchase *intent* may proceed (not execute purchase)."""
    title_s = _clean_title(title)
    author_s = _clean_optional_str(author, field="author", max_len=MAX_AUTHOR)
    store_s = _clean_optional_str(store, field="store", max_len=MAX_STORE)
    skip = _require_bool(skip_free_copy, field="skip_free_copy")

    notes: list[str] = [
        "purchase_executed=false — gate never executes charges",
        "authority=purchase_gate_advisory",
    ]
    if store_s:
        notes.append(f"store={store_s}")

    free_available: bool | None = None
    reasons: list[str] = []
    path = "blocked"

    if skip:
        ack = operator_skip_acknowledged
        if not isinstance(ack, bool):
            raise PurchaseGateError(
                "operator_skip_acknowledged must be an explicit boolean when skip_free_copy=true"
            )
        if ack is not True:
            raise PurchaseGateError(
                "skip_free_copy requires operator_skip_acknowledged=true"
            )
        free_available = None
        path = "skip_free_copy"
        notes.append("operator acknowledged skip of free-copy preflight")
        allowed = True
    else:
        if free_copy_preflight is None:
            raise PurchaseGateError(
                "free_copy_preflight required unless skip_free_copy=true"
            )
        if not isinstance(free_copy_preflight, Mapping):
            raise PurchaseGateError("free_copy_preflight must be an object")
        if "freely_available" not in free_copy_preflight:
            raise PurchaseGateError(
                "free_copy_preflight.freely_available required (no invent)"
            )
        fa = free_copy_preflight["freely_available"]
        if not isinstance(fa, bool):
            raise PurchaseGateError(
                "free_copy_preflight.freely_available must be an explicit boolean"
            )
        free_available = fa
        if fa is True:
            allowed = False
            path = "use_free_copy"
            reasons.append(
                "free copy available — purchase intent blocked; use free path"
            )
        else:
            allowed = True
            path = "purchase_intent_after_free_miss"
            notes.append("free-copy preflight found no free copy")

    if not allowed and not reasons:
        reasons.append("purchase intent not allowed")

    return PurchaseGateDecision(
        title=title_s,
        author=author_s,
        purchase_intent_allowed=allowed,
        purchase_executed=False,
        path=path,
        reasons=tuple(reasons) if not allowed else (),
        notes=tuple(notes),
        free_copy_freely_available=free_available,
        authority="purchase_gate_advisory",
    )


__all__ = [
    "PurchaseGateDecision",
    "PurchaseGateError",
    "evaluate_purchase_gate",
]
