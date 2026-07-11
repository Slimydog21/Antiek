"""FACT-style support gate with strict injected-judge handling.

``Blocked.unsupported_claims`` contains exact report slices in report order.
Judge failures and non-``bool`` outputs fail closed and never leak exceptions.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass

from substrate.research_spans import ExtractiveSpan

from .model import AnnotatedReport

# OPERATOR_TUNABLE: doctrine I-3/FACT hypothesis. Retune only after W0's
# independent evaluation over 20 real reports. >=90% support is NOT MEASURED.
SUPPORT_THRESHOLD: float = 0.9
type SupportJudge = Callable[[str, tuple[ExtractiveSpan, ...]], bool]


@dataclass(frozen=True, slots=True)
class Done:
    support_rate: float
    supported_claims: int
    total_claims: int


@dataclass(frozen=True, slots=True)
class Blocked:
    reason: str
    unsupported_claims: tuple[str, ...]
    support_rate: float
    supported_claims: int
    total_claims: int


type GateOutcome = Done | Blocked


def gate_report(
    report: AnnotatedReport,
    *,
    judge: SupportJudge,
    unattended: bool,
    enforce: bool = True,
    threshold: float = SUPPORT_THRESHOLD,
) -> GateOutcome:
    """Judge every bound claim and return a typed done/blocked outcome."""
    if not isinstance(report, AnnotatedReport):
        raise TypeError("report must be an AnnotatedReport")
    if not callable(judge):
        raise TypeError("judge must be callable")
    if unattended and not enforce:
        raise ValueError("support gate is mandatory for unattended runs")
    if not enforce:
        raise ValueError("gate bypass is not supported")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise TypeError("threshold must be numeric")
    if not math.isfinite(float(threshold)) or not 0.0 < threshold <= 1.0:
        raise ValueError("threshold must be in (0, 1]")
    annotations = {(a.start, a.end): a for a in report.annotations}
    unsupported: list[str] = []
    invalid_output = False
    supported = 0
    for claim in report.claims:
        annotation = annotations.get((claim.start, claim.end))
        if annotation is None:
            unsupported.append(claim.text)
            continue
        try:
            verdict = judge(claim.text, annotation.supporting_spans)
        except Exception:  # hostile/plugin boundary: fail closed
            verdict = None
        if type(verdict) is not bool:
            invalid_output = True
            unsupported.append(claim.text)
        elif verdict:
            supported += 1
        else:
            unsupported.append(claim.text)
    total = len(report.claims)
    if total == 0:
        return Blocked("report contains no claim sentences", (), 0.0, 0, 0)
    rate = supported / total if total else 0.0
    if not invalid_output and rate >= threshold:
        return Done(rate, supported, total)
    reason = "invalid judge output; blocked closed" if invalid_output else (
        f"claim support {rate:.3f} is below required threshold {threshold:.3f}"
    )
    return Blocked(reason, tuple(unsupported), rate, supported, total)
