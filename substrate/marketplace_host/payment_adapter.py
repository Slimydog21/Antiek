"""Payment adapter boundary for L5 digital book seamless port (residual akr).

Offline-honest by default. Live checkout/rails require dual-gate
``ANTIEK_MARKETPLACE_LIVE_PAYMENT=1`` **and** an injected upstream processor.
Never invents $0 entitlement. Manual opaque receipts remain in ``purchase.py``.

FUTURE-AGENT-SPEC-l5-digital-book-seamless-port Sprint 1:
  create_checkout(book_id, owner_id) → CheckoutSession
  confirm_receipt(opaque_ref) → Entitlement  (manual path)
  confirm_checkout_session(session_id) → Entitlement  (live path · gated)
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Callable, Mapping, Protocol, runtime_checkable

# Dual-gate L5 env (operator-only). Unset/false ⇒ deferred adapter.
ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV = "ANTIEK_MARKETPLACE_LIVE_PAYMENT"


def env_flag(name: str, *, environ: Mapping[str, str] | None = None) -> bool:
    """True only for explicit 1/true/yes/on (case-insensitive)."""
    src = environ if environ is not None else __import__("os").environ
    raw = str(src.get(name, "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def live_payment_enabled(*, environ: Mapping[str, str] | None = None) -> bool:
    """Whether L5 live payment dual-gate is operator-enabled."""
    return env_flag(ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV, environ=environ)


class LivePaymentDeferredError(RuntimeError):
    """Typed deferred error when live payment rails are not dual-gate ready.

    Machine-readable ``code`` / ``payment_path`` for UI honesty stamps.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str = "l5_live_payment_deferred",
        payment_path: str = "manual_receipt_only",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.payment_path = payment_path
        self.live_payment = False


@dataclass(frozen=True)
class CheckoutSession:
    """Checkout session boundary object (never invents charged state)."""

    session_id: str
    book_id: str
    owner_id: str
    status: str  # deferred | ready | confirmed | failed
    live_payment: bool
    payment_path: str
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "book_id": self.book_id,
            "owner_id": self.owner_id,
            "status": self.status,
            "live_payment": self.live_payment,
            "payment_path": self.payment_path,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class Entitlement:
    """Host entitlement after purchase proof — HTML host path remains separate."""

    entitlement_id: str
    book_id: str
    owner_id: str
    live_payment: bool
    payment_path: str
    opaque_reference: str = ""
    checkout_session_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "entitlement_id": self.entitlement_id,
            "book_id": self.book_id,
            "owner_id": self.owner_id,
            "live_payment": self.live_payment,
            "payment_path": self.payment_path,
            "opaque_reference": self.opaque_reference,
            "checkout_session_id": self.checkout_session_id,
        }


@runtime_checkable
class PaymentUpstream(Protocol):
    """Live processor boundary. Must not be invoked when dual-gate is off."""

    def create_checkout_session(
        self, *, book_id: str, owner_id: str
    ) -> dict[str, Any]: ...

    def confirm_checkout_session(
        self, *, session_id: str
    ) -> dict[str, Any]: ...


@runtime_checkable
class PaymentAdapter(Protocol):
    def create_checkout(self, *, book_id: str, owner_id: str) -> CheckoutSession: ...

    def confirm_receipt(
        self,
        opaque_ref: str,
        *,
        book_id: str,
        owner_id: str,
    ) -> Entitlement: ...

    def confirm_checkout_session(self, *, session_id: str) -> Entitlement: ...


def _stable_id(prefix: str, *parts: str) -> str:
    material = ":".join(parts)
    return prefix + hashlib.sha256(material.encode()).hexdigest()[:16]


@dataclass
class DeferredPaymentAdapter:
    """Default adapter: live rails deferred; manual opaque receipt only.

    Never calls ``upstream`` even if injected (zero-upstream proof for tests).
    """

    upstream: PaymentUpstream | None = None
    # Observability for tests: prove upstream never touched.
    upstream_calls: int = 0

    def create_checkout(self, *, book_id: str, owner_id: str) -> CheckoutSession:
        if not (book_id or "").strip():
            raise ValueError("book_id is required")
        if not (owner_id or "").strip():
            raise ValueError("owner_id is required")
        # Intentionally never call self.upstream — deferred path.
        sid = _stable_id("chk_deferred_", owner_id.strip(), book_id.strip())
        return CheckoutSession(
            session_id=sid,
            book_id=book_id.strip(),
            owner_id=owner_id.strip(),
            status="deferred",
            live_payment=False,
            payment_path="manual_receipt_only",
            reason=(
                "L5 live payment dual-gate off "
                f"({ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV} unset/false) — "
                "use manual opaque receipt; never invent $0 entitlement"
            ),
        )

    def confirm_receipt(
        self,
        opaque_ref: str,
        *,
        book_id: str,
        owner_id: str,
    ) -> Entitlement:
        """Manual opaque receipt → non-live entitlement (never $0 invent)."""
        if not (book_id or "").strip():
            raise ValueError("book_id is required")
        if not (owner_id or "").strip():
            raise ValueError("owner_id is required")
        ref = (opaque_ref or "").strip()
        if not ref:
            raise ValueError("opaque_reference is required")
        # Refuse obvious card-like payloads (parity ManualPurchaseReceipt).
        digits = "".join(c for c in ref if c.isdigit())
        if len(digits) >= 13 and digits == ref.replace(" ", "").replace("-", ""):
            raise ValueError(
                "opaque_reference looks like a card number; store only a "
                "merchant order id or receipt token"
            )
        # Never call upstream on manual path.
        eid = _stable_id("ent_manual_", owner_id.strip(), book_id.strip(), ref)
        return Entitlement(
            entitlement_id=eid,
            book_id=book_id.strip(),
            owner_id=owner_id.strip(),
            live_payment=False,
            payment_path="manual_receipt_only",
            opaque_reference=ref,
        )

    def confirm_checkout_session(self, *, session_id: str) -> Entitlement:
        """Live confirm blocked while dual-gate off — typed deferred error."""
        # Prove zero upstream even if injected.
        _ = session_id
        raise LivePaymentDeferredError(
            "L5 live checkout confirm deferred — dual-gate "
            f"{ANTIEK_MARKETPLACE_LIVE_PAYMENT_ENV} not enabled or no live "
            "processor; use confirm_receipt(opaque_ref) for manual path",
            code="l5_live_payment_deferred",
            payment_path="manual_receipt_only",
        )


@dataclass
class LivePaymentAdapter:
    """Live rails adapter — only when dual-gate env + upstream installed.

    Still refuses to invent entitlement if upstream returns incomplete charge.
    """

    upstream: PaymentUpstream
    upstream_calls: int = 0

    def create_checkout(self, *, book_id: str, owner_id: str) -> CheckoutSession:
        if not (book_id or "").strip():
            raise ValueError("book_id is required")
        if not (owner_id or "").strip():
            raise ValueError("owner_id is required")
        self.upstream_calls += 1
        raw = self.upstream.create_checkout_session(
            book_id=book_id.strip(), owner_id=owner_id.strip()
        )
        sid = str(raw.get("session_id") or "").strip()
        if not sid:
            raise ValueError("upstream create_checkout_session must return session_id")
        return CheckoutSession(
            session_id=sid,
            book_id=book_id.strip(),
            owner_id=owner_id.strip(),
            status=str(raw.get("status") or "ready"),
            live_payment=True,
            payment_path="live_checkout",
            reason=str(raw.get("reason") or ""),
        )

    def confirm_receipt(
        self,
        opaque_ref: str,
        *,
        book_id: str,
        owner_id: str,
    ) -> Entitlement:
        """Manual path remains available even when live rails exist."""
        return DeferredPaymentAdapter().confirm_receipt(
            opaque_ref, book_id=book_id, owner_id=owner_id
        )

    def confirm_checkout_session(self, *, session_id: str) -> Entitlement:
        sid = (session_id or "").strip()
        if not sid:
            raise ValueError("session_id is required")
        self.upstream_calls += 1
        raw = self.upstream.confirm_checkout_session(session_id=sid)
        charged = bool(raw.get("charged") or raw.get("paid") or raw.get("confirmed"))
        if not charged:
            raise LivePaymentDeferredError(
                "upstream did not confirm a real charge — refusing $0 entitlement",
                code="l5_charge_unconfirmed",
                payment_path="live_checkout",
            )
        book_id = str(raw.get("book_id") or "").strip()
        owner_id = str(raw.get("owner_id") or "").strip()
        if not book_id or not owner_id:
            raise ValueError(
                "upstream confirm must return book_id and owner_id after charge"
            )
        eid = _stable_id("ent_live_", owner_id, book_id, sid)
        return Entitlement(
            entitlement_id=eid,
            book_id=book_id,
            owner_id=owner_id,
            live_payment=True,
            payment_path="live_checkout",
            checkout_session_id=sid,
            opaque_reference=str(raw.get("opaque_reference") or ""),
        )


def build_payment_adapter(
    *,
    environ: Mapping[str, str] | None = None,
    upstream: PaymentUpstream | None = None,
) -> PaymentAdapter:
    """Factory: live only when dual-gate env true **and** upstream injected.

    Default (no env / no upstream) → DeferredPaymentAdapter (zero upstream calls).
    """
    if live_payment_enabled(environ=environ) and upstream is not None:
        return LivePaymentAdapter(upstream=upstream)
    return DeferredPaymentAdapter(upstream=upstream)


# Type alias for test injectors that count calls without a full Protocol class.
UpstreamFn = Callable[..., dict[str, Any]]
