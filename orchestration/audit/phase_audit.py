"""Phase audit — emits typed ``AUDIT_FINDING_EMITTED`` events on
detected gaps in the phase log + skill files + trajectory.

Sprint 8 day 2. The Antiek-side equivalent of upstream's hub_audit:
instead of auditing knowledge-graph hub dominance (deferred until
Sprint 9 alongside rlm_tools migration), this audit walks the phase
log + skill files + trajectory and surfaces structural gaps the
operator should see.

Gap categories detected:

- ``missing_phase``        — required completion phase (6/7/8) never entered
- ``unverified_phase``     — required phase entered+exited but never verified
- ``postcondition_failed`` — live postcondition check returns ``passed=False``
- ``no_auto_patch``        — Phase 8 verified but no AUTO_PATCH_APPLIED event
                             with patched domains (compounding gate triggered
                             without actually patching anything)
- ``empty_skill_dir``      — knowledge skills dir exists but has no domain subdirs

Each finding emits an ``AUDIT_FINDING_EMITTED`` typed event into the
investigation's trajectory with severity ∈ {info, warning, critical}.
The CLI reports them; downstream dashboards can subscribe to the
category and severity for triage.

Audit is observe-only: it never modifies the phase log or skill
files. The orchestrator (Sprint 8 day 3) can run audit between
phase transitions to surface gaps before they compound.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

try:
    from ...constants import AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION
    from ...event_log import emit_typed
    from ...schemas import (
        ActionType,
        AuditFindingPayload,
        AuditSeverity,
        AutoPatchAppliedPayload,
        Event,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import (  # type: ignore[no-redef]
        AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION,
    )
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        ActionType,
        AuditFindingPayload,
        AutoPatchAppliedPayload,
        Event,
    )

from ..phase_log import PhaseLog
from ..phase_runner.postconditions import (
    default_knowledge_skills_dir,
    run_check,
)


@dataclass(frozen=True)
class AuditFinding:
    """One detected gap. Translated to ``AuditFindingPayload`` and
    emitted by ``audit_phase_log``."""

    category: str
    severity: str  # one of AuditSeverity values
    description: str
    evidence: str
    target_phase: int | None = None
    target_path: str | None = None


# ---------------------------------------------------------------------------
# Finding-builder helpers
# ---------------------------------------------------------------------------


def _check_required_phases(plog: PhaseLog) -> list[AuditFinding]:
    """Walk required completion phases (6/7/8). Surface
    ``missing_phase`` for any never-entered, ``unverified_phase`` for
    entered-but-not-verified."""
    findings: list[AuditFinding] = []
    phases = plog.data.get("phases", {})
    for phase_id in AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION:
        rec = phases.get(str(phase_id))
        if not rec:
            findings.append(AuditFinding(
                category="missing_phase",
                severity="critical",
                description=f"Required phase {phase_id} was never entered.",
                evidence=(
                    f"phase_log carries no record for phase {phase_id}; "
                    f"completion gate will refuse to advance."
                ),
                target_phase=phase_id,
            ))
            continue
        if not rec.get("verified"):
            findings.append(AuditFinding(
                category="unverified_phase",
                severity="critical",
                description=f"Phase {phase_id} entered but never verified.",
                evidence=(
                    f"phase_log.phases.{phase_id}.verified is false; "
                    f"assert_ready_for_completion will fail."
                ),
                target_phase=phase_id,
            ))
    return findings


def _check_postconditions(
    investigation_id: str,
    plog: PhaseLog,
    *,
    research_dir: str | None,
    knowledge_skills_dir: str | None,
) -> list[AuditFinding]:
    """For every phase that was entered (whether verified or not),
    re-run its postcondition as a live diagnostic. Failures emit
    ``postcondition_failed``."""
    findings: list[AuditFinding] = []
    for phase_str in sorted(plog.data.get("phases", {}).keys(), key=int):
        try:
            phase = int(phase_str)
        except ValueError:
            continue
        passed, reason = run_check(
            phase, investigation_id,
            research_dir=research_dir,
            knowledge_skills_dir=knowledge_skills_dir,
        )
        if not passed:
            findings.append(AuditFinding(
                category="postcondition_failed",
                severity="warning",
                description=(
                    f"Phase {phase} postcondition failed under live re-check."
                ),
                evidence=reason,
                target_phase=phase,
            ))
    return findings


def _check_auto_patch_for_phase_8(
    investigation_id: str,
    plog: PhaseLog,
) -> list[AuditFinding]:
    """If Phase 8 is marked verified but the trajectory carries no
    ``AUTO_PATCH_APPLIED`` event with patched domains, emit
    ``no_auto_patch`` — the compounding gate triggered without
    actually patching anything. This is the silent-failure mode the
    upstream's "ALWAYS execute Phase 8" prose suffered from."""
    from substrate.event_log import trajectory

    phase_8 = plog.data.get("phases", {}).get("8")
    if not phase_8 or not phase_8.get("verified"):
        return []  # only check verified Phase 8
    for row in trajectory(investigation_id):
        if row.get("action_type") != ActionType.AUTO_PATCH_APPLIED.value:
            continue
        try:
            e = Event.model_validate(row)
        except Exception as exc:
            # A skipped AUTO_PATCH_APPLIED row can flip this check to a false
            # `no_auto_patch` critical (the patched row it needed was dropped),
            # so surface it (matching the module's stderr idiom below).
            print(
                f"audit_phase_log: malformed AUTO_PATCH_APPLIED row skipped "
                f"for {investigation_id}: {exc!r}",
                file=sys.stderr,
            )
            continue
        if isinstance(e.payload, AutoPatchAppliedPayload) and e.payload.patched:
            return []  # at least one patched domain — gate satisfied
    return [AuditFinding(
        category="no_auto_patch",
        severity="critical",
        description=(
            "Phase 8 verified but no auto_patch_applied event with "
            "patched domains found in trajectory."
        ),
        evidence=(
            "The compounding gate was marked complete without any "
            "skill being patched — this is the silent-failure mode "
            "the protocol exists to prevent."
        ),
        target_phase=8,
    )]


def _check_skill_dir_populated(
    knowledge_skills_dir: str | None,
) -> list[AuditFinding]:
    """``empty_skill_dir`` — the skills root exists but carries no
    ``<domain>-knowledge`` subdirs. Phase 8 can't compound into
    anything; flag for operator attention."""
    skills_root = knowledge_skills_dir or default_knowledge_skills_dir()
    if not os.path.isdir(skills_root):
        return []  # absence handled by Phase 8 postcondition; not a finding
    has_domain = any(
        os.path.isdir(os.path.join(skills_root, e)) and e.endswith("-knowledge")
        for e in os.listdir(skills_root)
    )
    if has_domain:
        return []
    return [AuditFinding(
        category="empty_skill_dir",
        severity="warning",
        description=(
            "Knowledge skills root has no <domain>-knowledge subdirs."
        ),
        evidence=(
            f"{skills_root} exists but contains no domain skill files. "
            "Phase 8 compounding will never patch anything until "
            "domain skills are seeded."
        ),
        target_path=skills_root,
    )]


# ---------------------------------------------------------------------------
# Public entry points
# ---------------------------------------------------------------------------


def collect_findings(
    investigation_id: str,
    *,
    research_dir: str | None = None,
    knowledge_skills_dir: str | None = None,
) -> list[AuditFinding]:
    """Run all audit checks; return the findings list WITHOUT
    emitting. Pure-data path for tests and dashboards that want to
    inspect findings before deciding what to surface."""
    plog = PhaseLog.open(investigation_id)
    findings: list[AuditFinding] = []
    findings.extend(_check_required_phases(plog))
    findings.extend(_check_postconditions(
        investigation_id, plog,
        research_dir=research_dir,
        knowledge_skills_dir=knowledge_skills_dir,
    ))
    findings.extend(_check_auto_patch_for_phase_8(investigation_id, plog))
    findings.extend(_check_skill_dir_populated(knowledge_skills_dir))
    return findings


def audit_phase_log(
    investigation_id: str,
    *,
    research_dir: str | None = None,
    knowledge_skills_dir: str | None = None,
    emit: bool = True,
) -> list[AuditFinding]:
    """Run the audit AND emit one ``AUDIT_FINDING_EMITTED`` event per
    finding. Returns the findings list (mirroring
    ``collect_findings``). ``emit=False`` is the dry-run shape for
    operator preview."""
    findings = collect_findings(
        investigation_id,
        research_dir=research_dir,
        knowledge_skills_dir=knowledge_skills_dir,
    )
    if not emit:
        return findings
    for f in findings:
        try:
            emit_typed(
                investigation_id,
                AuditFindingPayload(
                    category=f.category,
                    severity=f.severity,  # type: ignore[arg-type]
                    description=f.description,
                    evidence=f.evidence,
                    target_phase=f.target_phase,
                    target_path=f.target_path,
                ),
                role="phase_auditor",
                policy_id="orchestrator-deterministic",
            )
        except Exception as e:  # pragma: no cover — diagnostic only
            print(
                f"audit_phase_log: failed to emit finding ({f.category}): {e!r}",
                file=sys.stderr,
            )
    return findings
