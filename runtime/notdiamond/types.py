"""ANT-ND SPR-01 — adapter data types + exception hierarchy.

The exception hierarchy is adapter-owned (not the raw ND SDK's) so callers can
treat NotDiamond as *advisory*: catching :class:`NotDiamondError` is sufficient
to fall through to dispatch's own routing (the ``cd602c9`` verify-tier fallback
stays primary — master spec §"Key invariants"). Every failure mode ND can
present maps to one subclass; nothing raw from the SDK escapes the adapter.

No dispatch coupling lives here (that is SPR-03). See
``~/specs/antiek-notdiamond/index.html``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class NotDiamondError(Exception):
    """Base for every adapter-raised error.

    Callers that want ND to be strictly advisory catch THIS: any subclass means
    "no usable recommendation — fall through to dispatch's own routing."
    """


class NotDiamondNotInstalled(NotDiamondError):
    """The optional ``notdiamond`` SDK is not installed.

    ND is an optional pip extra (``antiek[notdiamond]``); dispatch must run when
    it is absent. Raised lazily at first :func:`select_model` call, never at
    import.
    """


class NotDiamondAuthError(NotDiamondError):
    """``NOTDIAMOND_API_KEY`` is missing (or was rejected by the service).

    Raised at first call, not at import (mirrors
    ``substrate/dispatch/providers/anthropic.py``'s ``_resolve_api_key``). The
    error text names only the env var, never the key value.
    """


class NotDiamondTimeout(NotDiamondError):
    """``select_model`` exceeded ``timeout_ms``.

    The advisory decision has a hard latency budget (default 500 ms, mirroring
    the SPR-06 circuit-breaker) so ND can never stall the dispatch path it
    precedes. On timeout the caller falls through to dispatch's own routing.
    """


class NotDiamondAPIError(NotDiamondError):
    """The ND service errored, or returned a recommendation the adapter could
    not parse into a (provider, model) pair."""


@dataclass(frozen=True)
class Recommendation:
    """A parsed NotDiamond routing recommendation.

    Immutable so a recommendation cannot be mutated between the advisory hook
    (SPR-03) and the event-log attribution (SPR-02's ``record_nd_decision``).

    Attributes:
        provider: Recommended provider slug, e.g. ``"anthropic"``.
        model: Recommended model id, e.g. ``"claude-opus-4-7"``.
        session_id: ND's per-call trace id — the join key SPR-05/SPR-07 use to
            tie the recommendation to its eventual ``synthesis_rubric`` outcome.
        decision_latency_ms: Wall-clock duration of the ``select_model`` call,
            for the SPR-06 latency budget and Q2 (master-spec open question).
        raw: Opaque SDK debugging payload; never relied on by callers.
    """

    provider: str
    model: str
    session_id: str
    decision_latency_ms: int
    raw: dict[str, Any] = field(default_factory=dict)
