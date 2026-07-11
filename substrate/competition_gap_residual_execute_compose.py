"""Competition gap residual execution package compose (pure).

execution_authorized, backlog_mutated, store_mutated always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

AcceptanceGate = Literal[
    "pure_module",
    "red_proof_tests_x2",
    "heterogeneous_critic",
    "honesty_flags",
    "no_app_py_race",
    "registerable_routes_or_free_file",
    "operator_merge_only",
]

DEFAULT_GATES: tuple[AcceptanceGate, ...] = (
    "pure_module",
    "red_proof_tests_x2",
    "heterogeneous_critic",
    "honesty_flags",
    "no_app_py_race",
    "registerable_routes_or_free_file",
    "operator_merge_only",
)

VALID_GATES = frozenset(DEFAULT_GATES)
VALID_PRIORITY = frozenset(("P0", "P1", "P2", "P3"))
VALID_STATUS = frozenset(("behind", "unknown", "parity", "ahead"))


class CompetitionGapResidualExecuteComposeError(ValueError):
    """Fail-closed validation for residual execution package."""


@dataclass(frozen=True)
class CompetitionGapResidualExecuteCompose:
    residual_id: str
    area: str
    competitor: str
    priority: str
    antiek_status: str
    residual_text: str
    execution_hint: str
    acceptance_gates: tuple[str, ...]
    proposed_owned_files: tuple[str, ...]
    package_ready: bool
    execution_authorized: bool
    backlog_mutated: bool
    store_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "residual_id": self.residual_id,
            "area": self.area,
            "competitor": self.competitor,
            "priority": self.priority,
            "antiek_status": self.antiek_status,
            "residual_text": self.residual_text,
            "execution_hint": self.execution_hint,
            "acceptance_gates": list(self.acceptance_gates),
            "proposed_owned_files": list(self.proposed_owned_files),
            "package_ready": self.package_ready,
            "execution_authorized": False,
            "backlog_mutated": False,
            "store_mutated": False,
            "notes": list(self.notes),
            "authority": "competition_gap_residual_execute_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionGapResidualExecuteComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_competition_gap_residual_execute(
    *,
    residual: object,
    operator_ack: object,
    extra_gates: object | None = None,
    proposed_owned_files: object | None = None,
) -> CompetitionGapResidualExecuteCompose:
    """Package one residual for future agents. Never authorizes execution."""
    if not isinstance(operator_ack, bool):
        raise CompetitionGapResidualExecuteComposeError(
            "operator_ack must be an explicit boolean"
        )
    if not isinstance(residual, dict):
        raise CompetitionGapResidualExecuteComposeError(
            "residual must be an object"
        )
    rid = _require_nonempty(residual.get("residual_id"), field="residual.residual_id")
    competitor = _require_nonempty(
        residual.get("competitor"), field="residual.competitor"
    )
    residual_text = _require_nonempty(
        residual.get("residual_text"), field="residual.residual_text"
    )
    execution_hint = _require_nonempty(
        residual.get("execution_hint"), field="residual.execution_hint"
    )
    priority = residual.get("priority")
    if priority not in VALID_PRIORITY:
        raise CompetitionGapResidualExecuteComposeError(
            "residual.priority must be P0|P1|P2|P3"
        )
    status = residual.get("antiek_status")
    if status not in VALID_STATUS:
        raise CompetitionGapResidualExecuteComposeError(
            "residual.antiek_status invalid"
        )
    area = residual.get("area")
    if not isinstance(area, str) or not area.strip():
        raise CompetitionGapResidualExecuteComposeError(
            "residual.area must be a non-empty string"
        )

    notes: list[str] = [
        "execution_authorized=false — package is advisory for future agents",
        "backlog_mutated=false — residual plan package only",
        "store_mutated=false",
        "free-file doctrine: pure modules + registerable routes; no app.py race",
    ]

    gates: set[str] = set(DEFAULT_GATES)
    if extra_gates is not None:
        if not isinstance(extra_gates, list):
            raise CompetitionGapResidualExecuteComposeError(
                "extra_gates must be an array when set"
            )
        for i, g in enumerate(extra_gates):
            if g not in VALID_GATES:
                raise CompetitionGapResidualExecuteComposeError(
                    f"extra_gates[{i}] must be a known AcceptanceGate"
                )
            gates.add(str(g))
    acceptance_gates = tuple(sorted(gates))

    owned: list[str] = []
    if proposed_owned_files is not None:
        if not isinstance(proposed_owned_files, list):
            raise CompetitionGapResidualExecuteComposeError(
                "proposed_owned_files must be an array when set"
            )
        seen: set[str] = set()
        for i, f in enumerate(proposed_owned_files):
            path = _require_nonempty(f, field=f"proposed_owned_files[{i}]")
            if "app.py" in path.split("/")[-1] or path.endswith("/app.py"):
                raise CompetitionGapResidualExecuteComposeError(
                    "proposed_owned_files must not include app.py (ready-html ownership)"
                )
            if path in seen:
                raise CompetitionGapResidualExecuteComposeError(
                    f"duplicate proposed_owned_files: {path}"
                )
            seen.add(path)
            owned.append(path)

    notes.append(f"residual_id={rid} · priority={priority} · area={area}")
    notes.append(f"execution_hint={execution_hint}")
    notes.append(f"acceptance_gates={len(acceptance_gates)}")

    package_ready = operator_ack is True
    if not package_ready:
        notes.append("package_ready=false — operator_ack required")
    else:
        notes.append(
            "package_ready=true — future agents may claim free residual under free-file doctrine"
        )
    notes.extend(
        (
            "execution_authorized=false",
            "backlog_mutated=false",
            "store_mutated=false",
        )
    )

    return CompetitionGapResidualExecuteCompose(
        residual_id=rid,
        area=str(area).strip(),
        competitor=competitor,
        priority=str(priority),
        antiek_status=str(status),
        residual_text=residual_text,
        execution_hint=execution_hint,
        acceptance_gates=acceptance_gates,
        proposed_owned_files=tuple(owned),
        package_ready=package_ready,
        execution_authorized=False,
        backlog_mutated=False,
        store_mutated=False,
        notes=tuple(notes),
        authority="competition_gap_residual_execute_compose_advisory",
    )


__all__ = [
    "CompetitionGapResidualExecuteCompose",
    "CompetitionGapResidualExecuteComposeError",
    "DEFAULT_GATES",
    "compose_competition_gap_residual_execute",
]
