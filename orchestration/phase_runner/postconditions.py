"""Phase postconditions — mechanical checks per phase artifact.

Sprint 8 day 2 — the artifact-level correspondence layer that
complements ``orchestration.phase_log.PhaseLog``. The phase log is the
*trust* layer (was the call made?); postconditions are the
*correspondence* layer (does the world reflect what the call claimed?).

Each check returns ``(passed, reason)``. The reason is the verbatim
evidence string ``verify_phase`` writes into the phase log on success
and the diagnostic stderr message on failure.

Phases 1-5: file artifacts in the per-investigation research dir.
Verbatim mirrors of the upstream Researchmaxx file shapes
(orientation.md / round1-*.md / round1-critique.md / round2-*.md /
round2-critique.md) — same artifact convention so a migrated
trajectory's directory layout stays interoperable.

Phases 6-8: trajectory-event-based (not DuckDB-row-based). The
syntheses/edges DB tables haven't migrated yet; the substrate's
trajectory IS the queryable source of truth.

- Phase 6: ``SYNTHESIZE_DELIVERED`` event with
  ``constraint_loop_status`` ∈ {single_pass, passed} +
  non-vacuous falsification conditions.
- Phase 7: ``MASTER_MD_WRITTEN`` event OR ``MASTER.md`` file present.
- Phase 8: ``AUTO_PATCH_APPLIED`` event with status="patched" AND any
  patched skill OR direct skill-file growth check.
- Phase 9: ``PhaseLog.assert_ready_for_completion``.

The trajectory-based approach is **the load-bearing choice** for the
Antiek-vs-Researchmaxx contract: a verify gate that requires a
specific typed event to be in the trajectory closes a class of
"checked but didn't actually happen" failure modes the upstream
suffered from with prose-only enforcement.
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

try:
    from ...event_log import trajectory
    from ...schemas import (
        ActionType,
        AutoPatchAppliedPayload,
        Event,
        MasterMdWrittenPayload,
        SynthesizeDeliveredPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.event_log import trajectory  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        ActionType,
        AutoPatchAppliedPayload,
        Event,
        MasterMdWrittenPayload,
        SynthesizeDeliveredPayload,
    )

from ..phase_log import PhaseAssertionError, PhaseLog

# ---------------------------------------------------------------------------
# Thresholds (matches upstream Researchmaxx values)
# ---------------------------------------------------------------------------


# Phase 1 orientation memo size floor.
_ORIENTATION_MIN_CHARS = 500

# Phase 2 round-1 dimension file size floor.
_ROUND1_MIN_BYTES = 500

# Phase 4 round-2 deep-dive size floor.
_ROUND2_DEEP_DIVE_MIN_BYTES = 500

# Phase 5 round-2 critique size floor.
_ROUND2_CRITIQUE_MIN_BYTES = 200

# Phase 7 MASTER.md size floor (rejects empty stubs).
_PHASE_7_MASTER_MIN_BYTES = 2000

# Phase 6 acceptable terminal statuses (constraint loop must have
# converged cleanly). Mirrors orchestrate.py's
# _PHASE_6_VERIFY_STATUSES verbatim.
_PHASE_6_VERIFY_STATUSES: frozenset[str] = frozenset({"passed", "single_pass"})

# Phase 6 vacuous-falsification substrings (the dry-run stub sentinel).
_PHASE_6_VACUOUS_SUBSTRINGS: tuple[str, ...] = ("stub answer",)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def default_research_dir(investigation_id: str) -> str:
    """Per-investigation artifact dir. ``ANTIEK_RESEARCH_DIR`` env var
    overrides the base; default is ``~/research/<investigation_id>``."""
    base = os.environ.get(
        "ANTIEK_RESEARCH_DIR",
        os.path.expanduser("~/research"),
    )
    return os.path.join(base, investigation_id)


def default_knowledge_skills_dir() -> str:
    """Root for ``<domain>-knowledge`` skill subdirs. Mirrors
    ``skills.domain.patch.default_skills_root`` for consistency."""
    return os.environ.get(
        "ANTIEK_KNOWLEDGE_SKILLS_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "knowledge_skills",
        ),
    )


# ---------------------------------------------------------------------------
# Trajectory helpers
# ---------------------------------------------------------------------------


def _events_of_type(investigation_id: str, action_type: ActionType) -> list[Event]:
    """Return the list of validated Event objects for a given action
    type. Tolerates ``trajectory()`` returning an empty list when the
    investigation has no events yet."""
    out: list[Event] = []
    for row in trajectory(investigation_id):
        if row.get("action_type") != action_type.value:
            continue
        try:
            out.append(Event.model_validate(row))
        except Exception:  # pragma: no cover — malformed row; skip
            continue
    return out


# ---------------------------------------------------------------------------
# Phase 1 — Orient
# ---------------------------------------------------------------------------


def check_phase_1(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """``orientation.md`` exists, is ≥ ``_ORIENTATION_MIN_CHARS``, and
    contains a ``## Prior Graph Knowledge`` section with at least one
    chunk/node regex citation."""
    research_dir = research_dir or default_research_dir(investigation_id)
    path = os.path.join(research_dir, "orientation.md")
    if not os.path.exists(path):
        return False, f"{path} not found"
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        return False, f"{path} unreadable: {e}"

    if len(text) < _ORIENTATION_MIN_CHARS:
        return False, (
            f"orientation.md too short ({len(text)} chars < "
            f"{_ORIENTATION_MIN_CHARS})"
        )

    header_re = re.compile(r"^##\s+Prior\s+Graph\s+Knowledge", re.MULTILINE)
    m = header_re.search(text)
    if not m:
        return False, "orientation.md missing '## Prior Graph Knowledge' section"

    section_start = m.end()
    next_header = re.search(r"^##\s", text[section_start:], re.MULTILINE)
    section = (
        text[section_start: section_start + next_header.start()]
        if next_header else text[section_start:]
    )
    if not re.search(r"\bchunk[-_][A-Za-z0-9_-]+|\bnode[-_][A-Za-z0-9_-]+", section):
        return False, (
            "Prior Graph Knowledge section has no chunk/node regex citation"
        )
    return True, "orientation.md OK (regex citation in Prior Graph Knowledge)"


# ---------------------------------------------------------------------------
# Phase 2 — Round 1 landscape
# ---------------------------------------------------------------------------


def check_phase_2(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """Three round-1 dimension files exist and are non-trivially sized."""
    research_dir = research_dir or default_research_dir(investigation_id)
    required = (
        "round1-technical.md", "round1-competitive.md", "round1-strategic.md",
    )
    missing: list[str] = []
    too_small: list[str] = []
    for name in required:
        p = os.path.join(research_dir, name)
        if not os.path.exists(p):
            missing.append(p)
            continue
        if os.path.getsize(p) <= _ROUND1_MIN_BYTES:
            too_small.append(f"{p} ({os.path.getsize(p)} bytes)")
    if missing:
        return False, "missing: " + ", ".join(missing)
    if too_small:
        return False, f"≤{_ROUND1_MIN_BYTES} bytes: " + ", ".join(too_small)
    return True, f"3 round-1 files OK under {research_dir}"


# ---------------------------------------------------------------------------
# Phase 3 — Round 1 critique
# ---------------------------------------------------------------------------


def check_phase_3(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """``round1-critique.md`` exists + references each dimension."""
    research_dir = research_dir or default_research_dir(investigation_id)
    path = os.path.join(research_dir, "round1-critique.md")
    if not os.path.exists(path):
        return False, f"{path} not found"
    try:
        text = open(path, encoding="utf-8").read().lower()
    except OSError as e:
        return False, f"{path} unreadable: {e}"
    missing = [
        k for k in ("technical", "competitive", "strategic") if k not in text
    ]
    if missing:
        return False, (
            f"round1-critique.md does not reference: {', '.join(missing)}"
        )
    return True, "round1-critique.md references all three dimensions"


# ---------------------------------------------------------------------------
# Phase 4 — Round 2 deep dive
# ---------------------------------------------------------------------------


def check_phase_4(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """At least one ``round2-*.md`` (≠ critique) exists with > floor."""
    research_dir = research_dir or default_research_dir(investigation_id)
    if not os.path.isdir(research_dir):
        return False, f"{research_dir} not a directory"
    candidates: list[str] = []
    for name in os.listdir(research_dir):
        if (
            not name.startswith("round2-")
            or name == "round2-critique.md"
            or not name.endswith(".md")
        ):
            continue
        full = os.path.join(research_dir, name)
        if os.path.getsize(full) > _ROUND2_DEEP_DIVE_MIN_BYTES:
            candidates.append(full)
    if not candidates:
        return False, (
            f"no round2-*.md (≠ critique) >{_ROUND2_DEEP_DIVE_MIN_BYTES} "
            f"bytes in {research_dir}"
        )
    return True, (
        f"{len(candidates)} round-2 deep-dive file(s): "
        f"{os.path.basename(candidates[0])}"
    )


# ---------------------------------------------------------------------------
# Phase 5 — Round 2 critique
# ---------------------------------------------------------------------------


def check_phase_5(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """``round2-critique.md`` exists > floor."""
    research_dir = research_dir or default_research_dir(investigation_id)
    path = os.path.join(research_dir, "round2-critique.md")
    if not os.path.exists(path):
        return False, f"{path} not found"
    sz = os.path.getsize(path)
    if sz <= _ROUND2_CRITIQUE_MIN_BYTES:
        return False, (
            f"{path} too small ({sz} bytes ≤ {_ROUND2_CRITIQUE_MIN_BYTES})"
        )
    return True, f"round2-critique.md OK ({sz} bytes)"


# ---------------------------------------------------------------------------
# Phase 6 — Synthesizer Delivered
# ---------------------------------------------------------------------------


def _falsifications_are_vacuous(
    falsifications: list[Any] | None,
) -> tuple[bool, str]:
    """Mirror the upstream heuristic: a falsification list is vacuous
    if empty, all single-word, or all matching dry-run stub strings.
    Returns ``(is_vacuous, reason)``."""
    if not falsifications:
        return True, "no falsification_conditions"
    all_single_word = True
    all_stub = True
    for item in falsifications:
        cond = ""
        if isinstance(item, dict):
            cond = str(item.get("condition", "")).strip()
        elif hasattr(item, "condition"):
            cond = str(getattr(item, "condition", "")).strip()
        elif isinstance(item, str):
            cond = item.strip()
        cond_lower = cond.lower()
        if len(cond.split()) >= 2:
            all_single_word = False
        if not any(s in cond_lower for s in _PHASE_6_VACUOUS_SUBSTRINGS):
            all_stub = False
        if not all_single_word and not all_stub:
            return False, ""
    if all_stub:
        return True, "all falsification conditions match dry-run stub strings"
    if all_single_word:
        return True, "all falsification conditions are single words"
    return False, ""


def check_phase_6(
    investigation_id: str,
) -> tuple[bool, str]:
    """A ``SYNTHESIZE_DELIVERED`` event is in the trajectory with a
    converged ``constraint_loop_status`` AND non-vacuous
    falsification conditions. Replaces upstream's DuckDB syntheses-row
    check with the typed trajectory equivalent — the substrate's
    event log IS the queryable source of truth for Antiek."""
    events = _events_of_type(
        investigation_id, ActionType.SYNTHESIZE_DELIVERED,
    )
    if not events:
        return False, (
            f"no synthesize.delivered event for investigation_id="
            f"{investigation_id}"
        )

    # Iterate newest-first (the last Delivered event is the canonical
    # one for the investigation; earlier ones may be from constraint-
    # loop retries that the bridge superseded).
    for e in reversed(events):
        payload = e.payload
        if not isinstance(payload, SynthesizeDeliveredPayload):
            continue
        if payload.constraint_loop_status not in _PHASE_6_VERIFY_STATUSES:
            continue
        # 2026-05-18 H2.5: insufficient_evidence escape hatch.
        # The synthesizer's contract says: "if you cannot produce a
        # defensible thesis with non-vacuous falsifications, signal
        # insufficient_evidence and emit empty arrays." When the
        # synthesizer correctly signals that, this is a converged
        # terminal state — the investigation IS complete, the answer
        # IS "no defensible thesis." Phase 6 must accept that as
        # converged or the whole substrate has no way to end an
        # underdetermined investigation cleanly. The parser already
        # honors this escape hatch (roles/synthesizer/parser.py); the
        # postcondition was lagging.
        if payload.implicit_recommendation == "insufficient_evidence":
            return True, (
                f"synthesize.delivered: insufficient_evidence verdict "
                f"(constraint_loop_status={payload.constraint_loop_status}, "
                f"iterations={payload.constraint_loop_iterations}). "
                f"Empty/vacuous falsifications are acceptable under this "
                f"recommendation."
            )
        vacuous, why = _falsifications_are_vacuous(payload.falsification_conditions)
        if vacuous:
            return False, (
                f"synthesize.delivered present "
                f"(constraint_loop_status={payload.constraint_loop_status}) "
                f"but falsification_conditions vacuous: {why}"
            )
        return True, (
            f"synthesize.delivered: "
            f"constraint_loop_status={payload.constraint_loop_status}, "
            f"iterations={payload.constraint_loop_iterations}, "
            f"{len(payload.falsification_conditions)} non-vacuous falsifier(s)"
        )

    # No event with a converged status.
    statuses = sorted({
        e.payload.constraint_loop_status
        for e in events
        if isinstance(e.payload, SynthesizeDeliveredPayload)
    })
    return False, (
        f"synthesize.delivered present (statuses={statuses}) but none "
        f"converged with non-vacuous falsifications"
    )


# ---------------------------------------------------------------------------
# Phase 7 — Delivery
# ---------------------------------------------------------------------------


def check_phase_7(
    investigation_id: str,
    *,
    research_dir: str | None = None,
) -> tuple[bool, str]:
    """A ``MASTER_MD_WRITTEN`` event for this investigation OR a
    ``MASTER.md`` file on disk with > floor bytes. Either suffices —
    delivery is fundamentally hard to verify mechanically, so we
    weaken to the strongest defensible proxy."""
    events = _events_of_type(investigation_id, ActionType.MASTER_MD_WRITTEN)
    for e in reversed(events):
        if isinstance(e.payload, MasterMdWrittenPayload):
            return True, (
                f"master_md_written event: path={e.payload.path}, "
                f"bytes={e.payload.byte_count}"
            )

    # File-system fallback.
    research_dir = research_dir or default_research_dir(investigation_id)
    master = os.path.join(research_dir, "MASTER.md")
    if os.path.exists(master):
        sz = os.path.getsize(master)
        if sz > _PHASE_7_MASTER_MIN_BYTES:
            return True, f"{master} present ({sz} bytes)"
        return False, (
            f"{master} too small ({sz} bytes ≤ {_PHASE_7_MASTER_MIN_BYTES})"
        )
    return False, (
        f"no master_md_written event and no {master} on disk"
    )


# ---------------------------------------------------------------------------
# Phase 8 — Knowledge extraction (KEYSTONE)
# ---------------------------------------------------------------------------


def check_phase_8(
    investigation_id: str,
    *,
    knowledge_skills_dir: str | None = None,
    investigation_started_at: datetime | None = None,
) -> tuple[bool, str]:
    """The keystone. Two checks (either suffices in Antiek — the dual
    requirement of the upstream's DB-edge + skill-growth check
    collapses to the trajectory event in the typed substrate):

      (A) An ``AUTO_PATCH_APPLIED`` event with at least one patched
          domain in the patched list.
      (B) A skill file under the knowledge skills root has mtime
          AFTER ``investigation_started_at`` (defaults to phase_log's
          created_at).

    The keystone discipline: Phase 8 is "did this investigation
    actually compound?". Either evidence shape is sufficient
    proof.

    2026-05-18 H2.5 escape hatch: when the upstream synthesis was
    ``insufficient_evidence``, there is no defensible thesis to
    extract knowledge from, and Phase 8 cannot produce a non-empty
    ``patched`` list. Treat that as a no-op pass — the substrate
    correctly compounded an underdetermined verdict, which is itself
    a useful signal (the operator now knows this question is
    unresolvable on current evidence). Mirrors Phase 6's escape
    hatch."""
    # ── (0) Insufficient-evidence escape hatch ──
    synth_events = _events_of_type(
        investigation_id, ActionType.SYNTHESIZE_DELIVERED,
    )
    for e in reversed(synth_events):
        payload = e.payload
        if isinstance(payload, SynthesizeDeliveredPayload):
            if payload.implicit_recommendation == "insufficient_evidence":
                return True, (
                    "phase 8 skipped: upstream synthesis was "
                    "insufficient_evidence — no defensible thesis to "
                    "compound into the knowledge graph"
                )
            break

    # ── (A) Trajectory event ──
    events = _events_of_type(investigation_id, ActionType.AUTO_PATCH_APPLIED)
    for e in reversed(events):
        if isinstance(e.payload, AutoPatchAppliedPayload):
            if e.payload.patched:
                return True, (
                    f"auto_patch_applied: status={e.payload.status}, "
                    f"patched={e.payload.patched}"
                )

    # ── (B) Skill-file mtime check ──
    knowledge_skills_dir = (
        knowledge_skills_dir or default_knowledge_skills_dir()
    )
    if not os.path.isdir(knowledge_skills_dir):
        return False, (
            f"no auto_patch_applied event with patched domains, AND "
            f"knowledge skills dir not found: {knowledge_skills_dir}"
        )

    cutoff = investigation_started_at
    if cutoff is None:
        try:
            plog = PhaseLog.open(investigation_id)
            ts = plog.data.get("created_at")
            if ts:
                # 2026-05-18 H4.5 fix: ``rstrip("Z")`` + naive
                # ``fromisoformat`` produced a tzinfo=None datetime
                # whose ``.timestamp()`` was interpreted as LOCAL
                # time. On the operator's UTC+3 dev machine this
                # silently shifted the cutoff 3 hours backwards,
                # making every seed file appear "modified after"
                # the cutoff. The same bug was masked in production
                # (UTC server) because real investigations satisfy
                # path A or the insufficient_evidence escape hatch
                # — only the test path with a no-domains-match
                # synthesizer hit the broken path B comparison.
                # Now we keep timezone info through the comparison.
                cutoff = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except Exception:
            pass
    if cutoff is None:
        cutoff = datetime.now(UTC) - timedelta(hours=24)
    if cutoff.tzinfo is None:
        # Backstop: any naive cutoff is interpreted as UTC, not
        # local time. The operator-supplied
        # ``investigation_started_at`` kwarg is documented as UTC
        # per the docstring; defensive-cast here so a stray naive
        # value doesn't reintroduce the local-time-shift bug.
        cutoff = cutoff.replace(tzinfo=UTC)
    cutoff_ts = cutoff.timestamp()

    for entry in sorted(os.listdir(knowledge_skills_dir)):
        if not entry.endswith("-knowledge"):
            continue
        domain_dir = os.path.join(knowledge_skills_dir, entry)
        if not os.path.isdir(domain_dir):
            continue
        for root, _dirs, files in os.walk(domain_dir):
            for fname in files:
                p = os.path.join(root, fname)
                try:
                    if os.stat(p).st_mtime > cutoff_ts:
                        return True, (
                            f"skill file {p!r} modified after "
                            f"{cutoff.isoformat()}"
                        )
                except OSError:
                    continue

    return False, (
        f"no auto_patch_applied event with patched domains, AND no "
        f"skill file modified after {cutoff.isoformat()} under "
        f"{knowledge_skills_dir}"
    )


# ---------------------------------------------------------------------------
# Phase 9 — Completion
# ---------------------------------------------------------------------------


def check_phase_9(investigation_id: str) -> tuple[bool, str]:
    """Delegate to ``PhaseLog.assert_ready_for_completion``."""
    try:
        plog = PhaseLog.open(investigation_id)
        plog.assert_ready_for_completion()
    except PhaseAssertionError as e:
        return False, str(e)
    except Exception as e:
        return False, f"failed to open phase log: {e}"
    return True, "phases 6, 7, 8 all verified in phase log"


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------


CHECKS: dict[int, Callable[..., tuple[bool, str]]] = {
    1: check_phase_1,
    2: check_phase_2,
    3: check_phase_3,
    4: check_phase_4,
    5: check_phase_5,
    6: check_phase_6,
    7: check_phase_7,
    8: check_phase_8,
    9: check_phase_9,
}


_CHECK_KWARGS: dict[int, tuple[str, ...]] = {
    1: ("research_dir",),
    2: ("research_dir",),
    3: ("research_dir",),
    4: ("research_dir",),
    5: ("research_dir",),
    6: (),
    7: ("research_dir",),
    8: ("knowledge_skills_dir",),
    9: (),
}


def run_check(
    phase: int,
    investigation_id: str,
    *,
    research_dir: str | None = None,
    knowledge_skills_dir: str | None = None,
) -> tuple[bool, str]:
    """Universal dispatcher — the phase_runner CLI's preferred entry
    point. Accepts every kwarg; forwards only the ones the target
    check accepts."""
    if phase not in CHECKS:
        return False, f"unknown phase: {phase}"
    accepted = _CHECK_KWARGS[phase]
    candidate = {
        "research_dir": research_dir,
        "knowledge_skills_dir": knowledge_skills_dir,
    }
    kwargs = {
        k: v for k, v in candidate.items()
        if k in accepted and v is not None
    }
    return CHECKS[phase](investigation_id, **kwargs)
