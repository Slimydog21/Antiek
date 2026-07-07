"""Orchestration audit (Sprint 8 day 2).

``phase_audit`` walks the phase log + skill files + trajectory and
emits typed ``AUDIT_FINDING_EMITTED`` events on detected gaps. The
Antiek-side equivalent of upstream's hub_audit: the upstream's graph-
hub-dominance check is deferred until Sprint 9 (alongside
substrate/graph/rlm_tools); the phase audit is the deliverable Day 2
focuses on since it gates Loop 1 closure.

Gap categories:
- ``missing_phase`` (critical) — required phase 6/7/8 never entered.
- ``unverified_phase`` (critical) — entered+exited but not verified.
- ``postcondition_failed`` (warning) — live re-check reports failure.
- ``no_auto_patch`` (critical) — Phase 8 verified but trajectory
  carries no AUTO_PATCH_APPLIED event with patched domains.
- ``empty_skill_dir`` (warning) — knowledge skills root has no
  <domain>-knowledge subdirs.
"""

from .phase8_calibration_status import (
    Phase8CalibrationStatus,
    phase8_calibration_status,
    record_phase8_gate_review,
    summarize_phase8_calibration,
)
from .phase_audit import (
    AuditFinding,
    audit_phase_log,
    collect_findings,
)

__all__ = [
    "AuditFinding",
    "collect_findings",
    "audit_phase_log",
    "Phase8CalibrationStatus",
    "phase8_calibration_status",
    "record_phase8_gate_review",
    "summarize_phase8_calibration",
]
