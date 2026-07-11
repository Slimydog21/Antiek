"""Cascade/DRW launch gate on source-policy preflight receipts.

Consumes ``run_source_policy_preflight`` (PR #776) without owning preflight or
readiness modules. Does **not** open the public network, reserve budget, write
graph state, or start a cascade session.

Semantics
---------
* ``source_policy is None`` / empty and not required → no preflight (legacy launch).
* ``source_policy`` non-empty → run offline probes; fail closed when any named
  source is ``unavailable`` or not ``adapter_importable``.
* ``status=gated`` (importable but not offline-exercised) is **allowed** with an
  honest receipt — production launch does not inject MockTransport clients.
* ``runner_consumes_today`` is never invented here; it flows from the probe.

Optional ``require_policy=True`` (request flag or ``ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT=1``)
refuses launch when no policy pack is supplied.
"""

from __future__ import annotations

import os
from collections.abc import Callable, Sequence
from typing import Any, cast

import httpx

from substrate.research_sources.preflight import (
    SourcePolicy,
    SourcePolicyPreflight,
    run_source_policy_preflight,
)


class SourcePolicyLaunchBlocked(RuntimeError):
    """Launch refused because source-policy preflight failed closed.

    ``receipt`` is the preflight payload when probes ran; may be ``None`` when
    the policy pack itself was missing under a require-policy gate.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str,
        receipt: SourcePolicyPreflight | None = None,
        blocked_sources: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.receipt = receipt
        self.blocked_sources = list(blocked_sources or [])

    def http_detail(self) -> dict[str, Any]:
        detail: dict[str, Any] = {
            "code": self.code,
            "message": str(self),
            "blocked_sources": self.blocked_sources,
            "retryable": False,
        }
        if self.receipt is not None:
            detail["source_preflight"] = self.receipt.model_dump()
        return detail


def _env_require_policy() -> bool:
    raw = os.environ.get("ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT", "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


_ALLOWED: frozenset[str] = frozenset(
    {"arxiv", "substack", "web", "operator_corpus"}
)


def _coerce_policy(source_policy: Sequence[str]) -> list[SourcePolicy]:
    out: list[str] = []
    bad: list[str] = []
    for raw in source_policy:
        name = str(raw).strip()
        if name not in _ALLOWED:
            bad.append(name)
            continue
        out.append(name)
    if bad:
        raise SourcePolicyLaunchBlocked(
            "unknown source_policy entries: " + ", ".join(bad),
            code="source_policy_invalid",
            receipt=None,
            blocked_sources=bad,
        )
    return cast(list[SourcePolicy], out)


def evaluate_source_policy_for_launch(
    source_policy: Sequence[str] | None,
    *,
    root_id: str | None = None,
    problem: str | None = None,
    require_policy: bool | None = None,
    gather_mode: str | None = None,
    arxiv_client: httpx.Client | None = None,
    arxiv_throttle: Any | None = None,
    substack_client: httpx.Client | None = None,
    preflight_fn: Callable[..., SourcePolicyPreflight] | None = None,
) -> SourcePolicyPreflight | None:
    """Return a preflight receipt when a policy pack is supplied; else None.

    Raises :class:`SourcePolicyLaunchBlocked` when launch must fail closed.
    """
    require = (
        bool(require_policy)
        if require_policy is not None
        else _env_require_policy()
    )
    raw = list(source_policy) if source_policy else []

    if not raw:
        if require:
            raise SourcePolicyLaunchBlocked(
                "source_policy is required for this launch "
                "(set LaunchRequest.source_policy or clear ANTIEK_DRW_REQUIRE_SOURCE_PREFLIGHT)",
                code="source_policy_required",
                receipt=None,
                blocked_sources=[],
            )
        return None

    policy = _coerce_policy(raw)

    runner: Callable[..., SourcePolicyPreflight] = (
        preflight_fn if preflight_fn is not None else run_source_policy_preflight
    )
    receipt = runner(
        policy,
        root_id=root_id,
        problem=problem,
        arxiv_client=arxiv_client,
        arxiv_throttle=arxiv_throttle,
        substack_client=substack_client,
        gather_mode=gather_mode,
    )
    if not isinstance(receipt, SourcePolicyPreflight):
        # Defensive: injectable fakes must still look like a receipt.
        raise SourcePolicyLaunchBlocked(
            "source-policy preflight returned a non-receipt object",
            code="source_preflight_invalid",
            receipt=None,
            blocked_sources=[str(s) for s in policy],
        )

    blocked: list[str] = []
    for entry in receipt.entries:
        if (not entry.adapter_importable) or entry.status == "unavailable":
            blocked.append(str(entry.source))

    if blocked:
        raise SourcePolicyLaunchBlocked(
            "source-policy preflight blocked launch: "
            + ", ".join(blocked)
            + " unavailable or not adapter-importable",
            code="source_policy_unavailable",
            receipt=receipt,
            blocked_sources=blocked,
        )
    return receipt


__all__ = [
    "SourcePolicyLaunchBlocked",
    "evaluate_source_policy_for_launch",
]
