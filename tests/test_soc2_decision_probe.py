from __future__ import annotations

import json
from pathlib import Path

from tools.ops import soc2_decision_probe


def _decision_doc(
    *,
    decision: str,
    deals_blocked: int,
    gated_pipeline: int,
    acv: str,
    branch: str,
) -> str:
    pursue = (
        "## §4 If PURSUE\n\n"
        "1. **Vendor selection** — Drata. Decision: fastest path. "
        "Decision factors: existing controls map cleanly.\n"
        "2. **Auditor selection** — Example CPA, AI platform experience.\n"
        "3. **Observation window opens** — 2026-07-15\n"
        "4. **Observation window closes** — 2027-01-15\n"
        "5. **Report delivered** — 2027-02-15\n\n"
        "Cost estimate at signing: $45000\n"
        "Cost estimate at delivery (Type II first report): $60000\n"
    )
    defer = (
        "## §5 If DEFER\n\n"
        "Document the specific signal that's missing, so the next quarterly\n"
        "review knows what changed:\n\n"
        "**Why DEFER now:** no enterprise buyer is blocked on SOC 2.\n\n"
        "**Renewal date:** 2026-10-01\n\n"
        "**What would flip this to PURSUE:** one blocked enterprise deal or "
        "three SOC-2-gated prospects.\n\n"
        "**Substrate hygiene maintenance:** continues regardless.\n"
    )
    if branch == "pursue":
        branch_sections = pursue + "\n---\n\n" + defer.replace(
            "no enterprise buyer is blocked on SOC 2",
            "not applicable because decision is pursue",
        )
    else:
        branch_sections = pursue.replace(
            "Drata. Decision: fastest path.",
            "not applicable. Decision: deferred.",
        ) + "\n---\n\n" + defer
    return f"""# Sprint 25+ — SOC 2 Type II Pursue/Defer Decision

**Status:** Filed.

**Author:** operator

**Decided:** 2026-07-01

**Cited evidence:**
- Latest `/marketplace/snapshot` output: reports/marketplace-snapshot-20260701.json
- Cumulative enterprise procurement conversations: {gated_pipeline} SOC-2-gated prospects
- Substrate hygiene readiness: docs/trust_center_public.md

---

## §1 Verdict

**Decision: {decision}**

---

## §2 The procurement-signal threshold

**Current measurement:**
- Deals blocked on SOC 2 specifically: {deals_blocked} (refs: none)
- Pipeline of SOC-2-gated prospects: {gated_pipeline}
- Estimated annual contract value at risk if SOC 2 not pursued: ${acv}
- Comparison: SOC 2 Type II first-report cost: $60000 + 6 months attention

---

## §3 Substrate readiness

| Control | Sprint 18 scaffold | SOC-2-ready evidence | Status |
|---------|--------------------|-----------------------|--------|
| Encryption at rest (per-graph KMS) | designed in | OA-011 production probe pending | gap |
| Access logging (append-only) | in code | 90-day log retention runbook | ready |
| Change management | CI gates on schema | PR approval workflow document | ready |
| Vulnerability scanning | Dependabot/Snyk | critical-CVE SLA runbook | ready |
| Backup testing | quarterly drill | restore-success log 2026-06-20 | ready |
| Retrieval-time policy_tag gating | SQL-WHERE level | OA-020 probe command | gap |

**Substrate readiness verdict:** GAPS REMAIN

---

{branch_sections}

---

## §6 Cross-references

- Master-spec §13.7
"""


def test_soc2_decision_probe_fails_current_template():
    result = soc2_decision_probe.probe_soc2_decision(Path("docs/soc2_decision.md"))

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["no_template_placeholders"].passed is False
    assert checks["decision_binary"].passed is False


def test_soc2_decision_probe_passes_defer_decision(tmp_path):
    path = tmp_path / "soc2_decision.md"
    path.write_text(
        _decision_doc(
            decision="DEFER",
            deals_blocked=0,
            gated_pipeline=0,
            acv="0",
            branch="defer",
        )
    )

    result = soc2_decision_probe.probe_soc2_decision(path)

    assert result.status == "PASS"
    assert result.decision == "DEFER"
    assert result.does_not_close_oa019 is True


def test_soc2_decision_probe_fails_defer_when_threshold_says_pursue(tmp_path):
    path = tmp_path / "soc2_decision.md"
    path.write_text(
        _decision_doc(
            decision="DEFER",
            deals_blocked=1,
            gated_pipeline=0,
            acv="250000",
            branch="defer",
        )
    )

    result = soc2_decision_probe.probe_soc2_decision(path)

    assert result.status == "FAIL"
    checks = {check.name: check for check in result.checks}
    assert checks["defer_threshold_consistent"].passed is False


def test_soc2_decision_probe_passes_pursue_decision(tmp_path):
    path = tmp_path / "soc2_decision.md"
    path.write_text(
        _decision_doc(
            decision="PURSUE",
            deals_blocked=1,
            gated_pipeline=2,
            acv="250000",
            branch="pursue",
        )
    )

    result = soc2_decision_probe.probe_soc2_decision(path)

    assert result.status == "PASS"
    assert result.decision == "PURSUE"


def test_soc2_decision_probe_json_cli(tmp_path, capsys):
    path = tmp_path / "soc2_decision.md"
    path.write_text(
        _decision_doc(
            decision="DEFER",
            deals_blocked=0,
            gated_pipeline=0,
            acv="0",
            branch="defer",
        )
    )

    exit_code = soc2_decision_probe.main([
        "--decision-path",
        str(path),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa019"] is True
