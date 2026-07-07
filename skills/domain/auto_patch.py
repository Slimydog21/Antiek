"""Mechanical, idempotent backfill of knowledge skills.

Sprint 6 day 4-5 port of Researchmaxx ``skill_patcher.py`` (390 LOC).
Complement to ``skills/domain/extract.py`` (Phase 8 live wiring).

Two paths now coexist in the skill files:

- ``skills/domain/extract.extract_and_patch`` runs a fresh LLM call
  per synthesis × matched domain to distill section-aware findings
  and patches the human-curated sections at the top. Right default
  for new investigations.
- ``patch_from_synthesis`` (this module) renders the schema-validated
  structured fields verbatim under a dedicated
  ``## Auto-patched findings`` header at the bottom of the skill
  file. **Mechanical, deterministic, no LLM**. Right default for
  backfill, single-synthesis recovery, and any path that cannot
  afford an LLM hop.

Why two paths: the LLM extraction can drift; the structured fields
on the synthesis are already deterministic ground truth.
``knowledge_extraction`` chooses richer-but-judgment-bound output;
this module chooses faithful-and-deterministic. The two formats live
under different headers in the same file so a reader sees both.

Domain routing here uses a **distinct, narrower** ``DOMAIN_KEYWORDS``
dict from ``skills/domain/keywords.py``. Higher precision is the
right trade-off for mechanical backfill — a false positive writes
unrelated findings into the wrong skill with no human in the loop
to catch it.

Idempotency is enforced by a ``<!-- synthesis_id: <id> -->`` marker
inside each rendered subsection. Re-running with the same id is a
no-op.

DB loader is **deferred** — the orchestrator (or CLI) loads the row
and passes it as a dict to ``patch_from_synthesis``. Wires in when
``substrate/init_db.py`` extends to the syntheses table.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from substrate.event_log import emit_typed
    from substrate.schemas import (
        AutoPatchAppliedPayload,
        AutoPatchSkippedPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import emit_typed
    from substrate.schemas import (
        AutoPatchAppliedPayload,
        AutoPatchSkippedPayload,
    )

from .patch import default_skills_root

# ---------------------------------------------------------------------------
# Domain routing — DISTINCT from skills/domain/keywords.DOMAIN_KEYWORDS
# ---------------------------------------------------------------------------


# Lowercase substring match against ``(question || thesis_summary)``.
# These keywords are intentionally narrower than the Phase 8 extraction
# routing set because no LLM filters this path's output — a false-
# positive route would write unrelated findings into the wrong skill.
# Specific phrases ("h100", "ai chip", "training run") avoid generic
# drift ("ai" alone would route every macro-finance investigation to
# ai-infrastructure).
AUTO_PATCH_DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "quantum-computing-knowledge": [
        "quantum comput", "qubit", "psiquantum", "photonic qubit",
        "rydberg", "neutral atom", "trapped ion", "superconducting qubit",
        "quantum error correction", "qec", "topological qubit",
        "ionq", "quantinuum", "quera", "atom computing", "pasqal",
        "fault-toleran", "logical qubit",
    ],
    "defense-systems-knowledge": [
        "anduril", "killer drone", "loitering munition", "missile defense",
        "bomber", "fighter jet", "naval", "pentagon", "department of defense",
        "munitions", "lethality", "war economy", "defense industrial base",
        "icbm", "hypersonic", "kill chain",
    ],
    "ai-infrastructure-knowledge": [
        "h100", "h200", "b200", "gb200", "nvl", "tpu",
        "ai chip", "ai infrastructure", "training run", "inference cluster",
        "llm training", "transformer scaling", "ai sanction", "ai export control",
        "deepseek", "openai", "anthropic", "claude", "codex",
        "frontier ai", "frontier-ai", "ai lab", "compute scaling",
    ],
    "semiconductor-knowledge": [
        "semiconductor", "foundry", "tsmc", "samsung foundry", "asml",
        "hbm", "hbm3", "high-bandwidth memory", "memory triopoly",
        "sk hynix", "micron", "lithography", "euv", "wafer",
        "process node", "5nm", "3nm", "2nm", "advanced packaging",
        "fab capacity", "chip supply",
    ],
}


SECTION_MARKER = "## Auto-patched findings"
SECTION_PREAMBLE = (
    "_This section accumulates mechanical distillations from archived "
    "syntheses. Each subsection is idempotent (keyed on `synthesis_id`). "
    "Human-curated knowledge above is intentionally not overwritten._\n"
)


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def route_domains(question: str, thesis_summary: str = "") -> list[str]:
    """Return every domain whose vocabulary matches. Lowercase substring
    match; an investigation may land in zero, one, or several domains.
    Distinct from ``skills.domain.classify_domains`` — see module
    docstring for the precision-vs-recall trade-off."""
    haystack = ((question or "") + " " + (thesis_summary or "")).lower()
    matched: list[str] = []
    for domain, keywords in AUTO_PATCH_DOMAIN_KEYWORDS.items():
        if any(kw in haystack for kw in keywords):
            matched.append(domain)
    return matched


def already_patched(skill_path: Path, synthesis_id: str) -> bool:
    """True iff the on-disk skill file already carries the
    ``synthesis_id: <id>`` marker in any rendered subsection."""
    if not skill_path.exists():
        return False
    try:
        body = skill_path.read_text()
    except OSError:
        return False
    return f"synthesis_id: {synthesis_id}" in body


def _truncate(s: str, n: int) -> str:
    if not isinstance(s, str):
        return ""
    if len(s) <= n:
        return s
    return s[:n].rstrip() + "…"


def render_patch(syn: dict[str, Any]) -> str:
    """Render one per-synthesis subsection. All fields pulled directly
    from the synthesis row — no enrichment, no LLM call.

    Required key: ``synthesis_id``. Optional: ``investigation_id``,
    ``target_question``, ``implicit_recommendation``, ``thesis``
    (parsed dict with ``thesis_summary`` / ``thesis_components`` /
    ``falsification_conditions`` / ``execution_risks`` /
    ``reasoning_paths_used``)."""
    syn_id = syn["synthesis_id"]
    iid = syn.get("investigation_id") or "(no investigation_id)"
    question = syn.get("target_question") or "(no question recorded)"
    rec = syn.get("implicit_recommendation") or "(no recommendation)"
    thesis = syn.get("thesis") or {}
    summary = thesis.get("thesis_summary") or ""
    components = thesis.get("thesis_components") or []
    falsifications = thesis.get("falsification_conditions") or []
    risks = thesis.get("execution_risks") or []
    rpu = thesis.get("reasoning_paths_used") or []
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    out: list[str] = []
    out.append(f"### From investigation `{iid}` ({today})")
    out.append("")
    out.append(f"<!-- synthesis_id: {syn_id} -->")
    out.append(f"- **Question**: {_truncate(question, 400)}")
    out.append(f"- **Recommendation**: `{rec}`")
    if summary:
        out.append(f"- **Thesis**: {_truncate(summary, 800)}")
    if components:
        out.append("- **Load-bearing components**:")
        for comp in components[:6]:
            if not isinstance(comp, dict):
                continue
            claim = _truncate(comp.get("claim") or "", 240)
            conf = comp.get("confidence", "?")
            tier = comp.get("effective_source_tier")
            tier_str = f", tier={tier}" if tier is not None else ""
            out.append(f"  - [{conf}{tier_str}] {claim}")
    if falsifications:
        out.append("- **Falsification conditions**:")
        for f in falsifications[:4]:
            if not isinstance(f, dict):
                continue
            cond = _truncate(f.get("condition") or "", 220)
            obs = _truncate(f.get("specific_observable") or "", 220)
            out.append(f"  - {cond}  _(observable: {obs})_")
    if risks:
        out.append("- **Execution risks**:")
        for r in risks[:4]:
            if not isinstance(r, dict):
                continue
            risk = _truncate(r.get("risk") or "", 220)
            sev = r.get("severity_if_manifested", "?")
            out.append(f"  - [{sev}] {risk}")
    if isinstance(rpu, list) and rpu:
        valid = [p for p in rpu if isinstance(p, dict) and p.get("support_summary")]
        if valid:
            out.append("- **Reasoning paths cited** (first entry):")
            first = valid[0]
            out.append(
                f"  - nodes={first.get('path_node_ids') or []} "
                f"edges={first.get('path_edge_ids') or []}"
            )
            out.append(
                f"  - _{_truncate(first.get('support_summary') or '', 240)}_"
            )
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# File-system boundary
# ---------------------------------------------------------------------------


def patch_skill_file(skill_path: Path, patch_md: str) -> None:
    """Insert ``patch_md`` under the Auto-patched section in
    ``skill_path``, creating the section if needed. Idempotency
    (skipping already-patched syntheses) is the caller's responsibility
    via ``already_patched``."""
    body = skill_path.read_text() if skill_path.exists() else ""

    if SECTION_MARKER in body:
        marker_idx = body.find(SECTION_MARKER)
        # Find where the section ends — the next top-level `## ` after
        # our marker, or EOF. We slot the new patch just before that
        # boundary so entries accumulate within the section rather than
        # after subsequent human-curated sections.
        after = body[marker_idx + len(SECTION_MARKER):]
        next_section = after.find("\n## ")
        if next_section == -1:
            new_body = body + ("\n" if not body.endswith("\n") else "") + patch_md + "\n"
        else:
            split = marker_idx + len(SECTION_MARKER) + next_section
            new_body = body[:split] + "\n" + patch_md + "\n" + body[split:]
    else:
        # Append the section at the end of the file.
        new_body = (
            body.rstrip()
            + "\n\n"
            + SECTION_MARKER
            + "\n\n"
            + SECTION_PREAMBLE
            + "\n"
            + patch_md
            + "\n"
        )

    skill_path.write_text(new_body)


# ---------------------------------------------------------------------------
# Typed emit helpers
# ---------------------------------------------------------------------------


def _safe_emit_applied(
    *,
    investigation_id: str | None,
    result: dict[str, Any],
) -> None:
    """Best-effort AUTO_PATCH_APPLIED emit. Failures must never break
    the patch path."""
    try:
        # Per-error records are coerced to {str: str} to match the
        # payload's typed dict shape — upstream's free-form
        # ``{"domain": ..., "error": repr(e)}`` already produces
        # strings, but a defensive ``str()`` cast guards against an
        # unexpected exception repr that isn't already a string.
        coerced_errors = [
            {str(k): str(v) for k, v in (err or {}).items()}
            for err in (result.get("errors") or [])
        ]
        emit_typed(
            investigation_id or result["synthesis_id"],
            AutoPatchAppliedPayload(
                synthesis_id=result["synthesis_id"],
                matched_domains=list(result.get("matched_domains") or []),
                patched=list(result.get("patched") or []),
                skipped=list(result.get("skipped") or []),
                errors=coerced_errors,
                status=result.get("status", "unknown"),
            ),
            synthesis_id=result["synthesis_id"],
            role="auto_patch",
            policy_id="orchestrator-deterministic",
        )
    except Exception as e:  # pragma: no cover — diagnostic only
        print(
            f"auto_patch → AUTO_PATCH_APPLIED emit failed (non-fatal): {e!r}",
            file=sys.stderr,
        )


def _safe_emit_skipped(
    *,
    investigation_id: str | None,
    synthesis_id: str,
    domain: str,
    skill_path: str,
) -> None:
    try:
        emit_typed(
            investigation_id or synthesis_id,
            AutoPatchSkippedPayload(
                synthesis_id=synthesis_id,
                domain=domain,
                skill_path=skill_path,
            ),
            synthesis_id=synthesis_id,
            role="auto_patch",
            policy_id="orchestrator-deterministic",
        )
    except Exception as e:  # pragma: no cover — diagnostic only
        print(
            f"auto_patch → AUTO_PATCH_SKIPPED emit failed (non-fatal): {e!r}",
            file=sys.stderr,
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def patch_from_synthesis(
    syn: dict[str, Any],
    *,
    skills_root: Path | None = None,
    emit_events: bool = True,
) -> dict[str, Any]:
    """Core entry point. ``syn`` is a dict with keys::

        synthesis_id, investigation_id, target_question,
        implicit_recommendation, thesis (parsed dict)

    Returns a result dict capturing routing decisions and per-domain
    outcomes::

        {
          "synthesis_id": ...,
          "investigation_id": ...,
          "matched_domains": [...],
          "patched": [...],
          "skipped": [...],
          "errors": [{"domain": ..., "error": ...}, ...],
          "status": "patched" | "already_patched" | "failed" |
                    "partial" | "no_match",
        }

    When ``emit_events`` is false, the filesystem behavior and returned
    result are identical, but no AUTO_PATCH_* event-log records are emitted.
    Candidate replay uses that mode to materialize temporary skill overlays
    without pretending a production patch path ran.

    Never raises on a single skill's failure — individual errors land
    in the ``errors`` list and the overall status is set accordingly
    so a cron caller can distinguish "nothing matched" from
    "everything broke"."""
    root = skills_root or default_skills_root()
    syn_id = syn["synthesis_id"]
    question = syn.get("target_question") or ""
    thesis = syn.get("thesis") or {}
    summary = thesis.get("thesis_summary") or ""

    domains = route_domains(question, summary)
    result: dict[str, Any] = {
        "synthesis_id": syn_id,
        "investigation_id": syn.get("investigation_id"),
        "matched_domains": domains,
        "patched": [],
        "skipped": [],
        "errors": [],
    }

    if not domains:
        result["status"] = "no_match"
        if emit_events:
            _safe_emit_applied(
                investigation_id=syn.get("investigation_id"), result=result,
            )
        return result

    patch_md = render_patch(syn)

    for domain in domains:
        skill_path = root / domain / "SKILL.md"
        try:
            skill_path.parent.mkdir(parents=True, exist_ok=True)
            if already_patched(skill_path, syn_id):
                result["skipped"].append(domain)
                if emit_events:
                    _safe_emit_skipped(
                        investigation_id=syn.get("investigation_id"),
                        synthesis_id=syn_id, domain=domain,
                        skill_path=str(skill_path),
                    )
                continue
            patch_skill_file(skill_path, patch_md)
            result["patched"].append(domain)
        except Exception as e:  # pragma: no cover — diagnostic only
            result["errors"].append({"domain": domain, "error": repr(e)})

    if result["patched"]:
        result["status"] = "patched"
    elif result["skipped"] and not result["errors"]:
        result["status"] = "already_patched"
    elif result["errors"] and not result["patched"]:
        result["status"] = "failed"
    else:
        result["status"] = "partial"

    if emit_events:
        _safe_emit_applied(
            investigation_id=syn.get("investigation_id"), result=result,
        )
    return result
