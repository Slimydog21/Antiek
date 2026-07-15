"""Typed product adapter seams; live operation kinds stay disabled by default."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Literal

from substrate.paid_operations.worker import ProviderCapabilityAttestation, ProviderCapabilityError

OperationKind = Literal["collective_interrogation_v1", "midnight_oil_v1"]


@dataclass(frozen=True)
class OperationKindEnablement:
    kind: OperationKind
    enabled: bool
    reason: str
    capability: ProviderCapabilityAttestation | None = None


def collective_interrogation_enablement(
    capability: ProviderCapabilityAttestation | None = None,
) -> OperationKindEnablement:
    if not _capability_enables(capability, "collective_interrogation_v1"):
        return OperationKindEnablement(
            kind="collective_interrogation_v1",
            enabled=False,
            reason="collective interrogation paid dispatch is capability-gated and disabled",
            capability=capability,
        )
    return OperationKindEnablement(
        kind="collective_interrogation_v1",
        enabled=True,
        reason="capability attestation passed",
        capability=capability,
    )


def midnight_oil_enablement(
    capability: ProviderCapabilityAttestation | None = None,
) -> OperationKindEnablement:
    if not _capability_enables(capability, "midnight_oil_v1"):
        return OperationKindEnablement(
            kind="midnight_oil_v1",
            enabled=False,
            reason="midnight oil paid dispatch is capability-gated and disabled",
            capability=capability,
        )
    return OperationKindEnablement(
        kind="midnight_oil_v1",
        enabled=True,
        reason="capability attestation passed",
        capability=capability,
    )


def _capability_enables(
    capability: ProviderCapabilityAttestation | None,
    operation_kind: OperationKind,
) -> bool:
    if capability is None or not capability.enabled or capability.operation_kind != operation_kind:
        return False
    try:
        capability.validate(now_ms=time.time_ns() // 1_000_000)
    except ProviderCapabilityError:
        return False
    return True


__all__ = [
    "OperationKindEnablement",
    "collective_interrogation_enablement",
    "midnight_oil_enablement",
]
