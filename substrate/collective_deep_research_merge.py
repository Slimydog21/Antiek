"""Collective deep research → written analysis intent (pure).

Merges ≥2 floating/sub-agent research instances into draft/full analysis
intent. analysis_written is always False. Findings are caller-supplied only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AnalysisMergeKind = Literal["draft_analysis", "full_analysis"]
InstanceStatus = Literal["completed", "open", "proposed", "closed"]


class CollectiveAnalysisMergeError(ValueError):
    """Fail-closed validation for collective analysis merge."""


@dataclass(frozen=True)
class CollectiveAnalysisIntent:
    kind: AnalysisMergeKind
    parent_asset_id: str
    instance_ids: tuple[str, ...]
    findings: tuple[str, ...]
    operator_ack: bool
    analysis_written: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "parent_asset_id": self.parent_asset_id,
            "instance_ids": list(self.instance_ids),
            "findings": list(self.findings),
            "operator_ack": self.operator_ack,
            "analysis_written": False,
            "notes": list(self.notes),
            "authority": "collective_analysis_intent_only",
        }


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise CollectiveAnalysisMergeError(f"{field} must be an explicit boolean")
    return value


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CollectiveAnalysisMergeError(f"{field} must be a non-empty string")
    return value.strip()


def propose_collective_analysis_merge(
    instances: object,
    *,
    kind: object,
    operator_ack: object,
    extra_findings: object | None = None,
) -> CollectiveAnalysisIntent:
    """Propose draft/full analysis intent. Never writes analysis assets."""
    ack = _require_bool(operator_ack, field="operator_ack")
    if kind not in ("draft_analysis", "full_analysis"):
        raise CollectiveAnalysisMergeError(
            "kind must be draft_analysis or full_analysis"
        )
    kind_s: AnalysisMergeKind = kind
    if kind_s == "full_analysis" and ack is not True:
        raise CollectiveAnalysisMergeError(
            "full_analysis requires operator_ack=true (fail closed)"
        )
    if not isinstance(instances, list) or len(instances) < 2:
        raise CollectiveAnalysisMergeError(
            "collective analysis requires at least 2 instances"
        )

    parent = _require_nonempty(
        instances[0].get("parent_asset_id") if isinstance(instances[0], dict) else None,
        field="instances[0].parent_asset_id",
    )
    ids: list[str] = []
    findings: list[str] = []
    notes: list[str] = []

    for i, inst in enumerate(instances):
        if not isinstance(inst, dict):
            raise CollectiveAnalysisMergeError(f"instances[{i}] must be an object")
        iid = _require_nonempty(inst.get("instance_id"), field=f"instances[{i}].instance_id")
        p = _require_nonempty(
            inst.get("parent_asset_id"), field=f"instances[{i}].parent_asset_id"
        )
        if p != parent:
            raise CollectiveAnalysisMergeError(
                "collective analysis requires same parent_asset_id"
            )
        status = inst.get("status")
        if status not in ("completed", "open", "proposed", "closed"):
            raise CollectiveAnalysisMergeError(
                f"instances[{i}].status must be proposed|open|completed|closed"
            )
        if status == "closed":
            raise CollectiveAnalysisMergeError(
                f"instances[{i}] status must be proposed|open|completed (not closed)"
            )
        if kind_s == "full_analysis" and status != "completed":
            raise CollectiveAnalysisMergeError(
                "full_analysis requires all instances completed"
            )
        ids.append(iid)
        raw_findings = inst.get("findings")
        if raw_findings is not None:
            if not isinstance(raw_findings, list):
                raise CollectiveAnalysisMergeError(
                    f"instances[{i}].findings must be string[] when set"
                )
            for j, f in enumerate(raw_findings):
                if not isinstance(f, str) or not f.strip():
                    raise CollectiveAnalysisMergeError(
                        f"instances[{i}].findings[{j}] must be non-empty string"
                    )
                findings.append(f.strip())

    seen: set[str] = set()
    unique: list[str] = []
    for iid in ids:
        if iid in seen:
            continue
        seen.add(iid)
        unique.append(iid)
    if len(unique) < 2:
        raise CollectiveAnalysisMergeError(
            "collective analysis requires at least 2 distinct instance_ids"
        )

    if extra_findings is not None:
        if not isinstance(extra_findings, list):
            raise CollectiveAnalysisMergeError("extra_findings must be string[] or null")
        for j, f in enumerate(extra_findings):
            if not isinstance(f, str) or not f.strip():
                raise CollectiveAnalysisMergeError(
                    f"extra_findings[{j}] must be non-empty string"
                )
            findings.append(f.strip())

    if not findings:
        notes.append(
            "no findings supplied — analysis scaffold intent only (no invent content)"
        )
    else:
        notes.append(f"findings={len(findings)} caller-supplied only")

    notes.append("analysis_written=false")
    notes.append(
        "draft analysis intent — provisional combined document not written"
        if kind_s == "draft_analysis"
        else "full analysis intent — parent/analysis asset not mutated in pure layer"
    )

    return CollectiveAnalysisIntent(
        kind=kind_s,
        parent_asset_id=parent,
        instance_ids=tuple(unique),
        findings=tuple(findings),
        operator_ack=ack,
        analysis_written=False,
        notes=tuple(notes),
        authority="collective_analysis_intent_only",
    )


__all__ = [
    "CollectiveAnalysisIntent",
    "CollectiveAnalysisMergeError",
    "propose_collective_analysis_merge",
]
