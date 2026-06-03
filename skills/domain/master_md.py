"""MASTER.md generation from an archived synthesis row.

Sprint 6 day 4-5 port of Researchmaxx ``synthesis_to_master.py`` (491
LOC). Bridges Phase 6 (synthesis archival) and Phase 7 (delivery). The
upstream's failure mode that motivated this primitive — the worker
model silently dropping the "load synthesis.json and write MASTER.md"
prose instruction — is the same compounding gate the typed
``MasterMdWrittenPayload`` event now records, so a missing render is
loud rather than silent.

Source of truth is the synthesis dict (a thin wrapper around what the
upstream DuckDB query returns). The DB loader is **deferred** —
``substrate/init_db.py`` hasn't migrated the syntheses table yet; the
caller in production (orchestrator) will load the row and pass it in.

Idempotency: the rendered MASTER.md begins with a
``<!-- synthesis_id: <id> -->`` marker. ``generate_master_md`` reads
the first 4 KiB of any existing file at the target path; on marker
match the regeneration is skipped and a ``MasterMdSkippedPayload``
event is emitted instead.
"""

from __future__ import annotations

import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from ...constants import ANTIEK_PARAM_VERSION
    from ...event_log import emit_typed
    from ...schemas import (
        MasterMdSkippedPayload,
        MasterMdWrittenPayload,
    )
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from substrate.constants import ANTIEK_PARAM_VERSION  # type: ignore[no-redef]
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas import (  # type: ignore[no-redef]
        MasterMdSkippedPayload,
        MasterMdWrittenPayload,
    )


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


# Marker the rendered MASTER.md header carries. ``generate_master_md``
# reads the first 4 KiB of any existing file at the target path; on
# marker match the regeneration is skipped.
SYNTHESIS_ID_MARKER = "<!-- synthesis_id: "

# Idempotency cap on how much of an existing file to read when checking
# for the marker. Generous; the marker sits on the first line.
_IDEMPOTENCY_HEAD_BYTES = 4096

DEFAULT_FILENAME = "MASTER.md"


def default_research_base() -> Path:
    """Where ``<topic_slug>/MASTER.md`` lands by default. The
    ``ANTIEK_RESEARCH_DIR`` env var overrides; the default mirrors
    upstream ``~/research/``."""
    return Path(os.environ.get(
        "ANTIEK_RESEARCH_DIR",
        os.path.expanduser("~/research"),
    ))


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def slugify(text: str, max_len: int = 64) -> str:
    """Lowercase, non-alnum → hyphen, collapse runs, trim. Empty
    input maps to ``untitled`` (never empty)."""
    if not text:
        return "untitled"
    s = text.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    if not s:
        return "untitled"
    return s[:max_len].rstrip("-") or "untitled"


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    import json
    return json.dumps(v, default=str)


def _render_components(components: Any) -> str:
    if not components or not isinstance(components, list):
        return "_No thesis components recorded._\n"
    lines: list[str] = []
    for i, c in enumerate(components, 1):
        if not isinstance(c, dict):
            lines.append(f"### Component {i}\n\n{_safe_str(c)}\n")
            continue
        claim = c.get("claim", "(no claim)")
        conf = c.get("confidence", "unknown")
        basis = c.get("confidence_basis")
        chunks = c.get("supporting_chunk_ids") or []
        paths = c.get("supporting_path_indices") or []
        lines.append(f"### Component {i}")
        lines.append("")
        lines.append(f"- **Claim:** {claim}")
        lines.append(
            f"- **Confidence:** {conf}" + (f" — {basis}" if basis else "")
        )
        if chunks:
            shown = ", ".join(f"`{c_}`" for c_ in chunks[:12])
            tail = f" … (+{len(chunks) - 12} more)" if len(chunks) > 12 else ""
            lines.append(f"- **Supporting chunks ({len(chunks)}):** {shown}{tail}")
        else:
            lines.append("- **Supporting chunks:** _none_")
        if paths:
            lines.append(f"- **Supporting path indices:** {paths}")
        lines.append("")
    return "\n".join(lines)


def _render_falsifications(items: Any) -> str:
    if not items or not isinstance(items, list):
        return "_No falsification conditions recorded._\n"
    lines: list[str] = []
    for i, f in enumerate(items, 1):
        if isinstance(f, dict):
            cond = f.get("condition", "(no condition)")
            obs = f.get("specific_observable")
            line = f"{i}. **{cond}**"
            if obs:
                line += f" — *Observable:* {obs}"
            lines.append(line)
        else:
            lines.append(f"{i}. {_safe_str(f)}")
    return "\n".join(lines) + "\n"


def _render_risks(items: Any) -> str:
    if not items or not isinstance(items, list):
        return "_No execution risks recorded._\n"
    lines: list[str] = []
    for i, r in enumerate(items, 1):
        if isinstance(r, dict):
            desc = (
                r.get("risk") or r.get("description")
                or r.get("condition") or _safe_str(r)
            )
            sev = r.get("severity") or r.get("impact")
            line = f"{i}. {desc}"
            if sev:
                line += f" (severity: {sev})"
            lines.append(line)
        else:
            lines.append(f"{i}. {_safe_str(r)}")
    return "\n".join(lines) + "\n"


def _render_constraint_compliance(cc: Any) -> str:
    if not cc:
        return "_No constraint compliance recorded._\n"
    if not isinstance(cc, dict):
        return f"```\n{_safe_str(cc)}\n```\n"
    hard_ok = cc.get("hard_constraints_satisfied")
    soft = cc.get("soft_constraints_violated") or []
    justified = cc.get("violations_justified") or []
    lines = [f"- **Hard constraints satisfied:** {hard_ok}"]
    if soft:
        lines.append(f"- **Soft constraint violations:** {len(soft)}")
        for s in soft:
            lines.append(f"  - {_safe_str(s)}")
    else:
        lines.append("- **Soft constraint violations:** none")
    if justified:
        lines.append(f"- **Violations justified:** {len(justified)}")
        for j in justified:
            lines.append(f"  - {_safe_str(j)}")
    return "\n".join(lines) + "\n"


def _utc_iso_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def build_master_md(row: dict[str, Any]) -> str:
    """Render the MASTER.md body from a synthesis row dict.

    Required keys: ``synthesis_id``. Optional keys: ``investigation_id``,
    ``target_question``, ``synthesis_timestamp``, ``status``,
    ``implicit_recommendation``, ``thesis`` (a parsed dict — usually the
    ``thesis_json`` column already deserialized), ``thesis_text``.
    Missing fields fall back to placeholder strings — the renderer never
    raises on a partial row."""
    synthesis_id = row["synthesis_id"]
    topic = row.get("target_question") or "(untitled investigation)"
    timestamp = row.get("synthesis_timestamp") or _utc_iso_now()
    status = row.get("status") or "draft"
    implicit = row.get("implicit_recommendation") or "undetermined"
    investigation_id = row.get("investigation_id") or "(none)"

    thesis = row.get("thesis") or row.get("thesis_json") or {}
    if not isinstance(thesis, dict):
        thesis = {}

    summary = (
        thesis.get("thesis_summary")
        or row.get("thesis_text")
        or "_No thesis summary recorded._"
    )
    components = thesis.get("thesis_components")
    falsifications = thesis.get("falsification_conditions")
    risks = thesis.get("execution_risks")
    implicit_thesis = thesis.get("implicit_recommendation") or implicit
    constraint_compliance = thesis.get("constraint_compliance")

    parts: list[str] = []
    parts.append(f"{SYNTHESIS_ID_MARKER}{synthesis_id} -->")
    parts.append(f"<!-- param_version: {ANTIEK_PARAM_VERSION} -->")
    parts.append(f"<!-- generated_at: {_utc_iso_now()} -->")
    parts.append("")
    parts.append(f"# {topic}")
    parts.append("")
    parts.append(f"> Synthesis ID: `{synthesis_id}`  ")
    parts.append(f"> Investigation ID: `{investigation_id}`  ")
    parts.append(f"> Generated: {timestamp}  ")
    parts.append(f"> Param version: `{ANTIEK_PARAM_VERSION}`  ")
    parts.append(f"> Pipeline status: `{status}`  ")
    parts.append(f"> Implicit recommendation: `{implicit_thesis}`")
    parts.append("")
    parts.append("## Thesis Summary")
    parts.append("")
    parts.append(_safe_str(summary).rstrip() or "_(empty)_")
    parts.append("")
    parts.append("## Thesis Components")
    parts.append("")
    parts.append(_render_components(components))
    parts.append("## Falsification Conditions")
    parts.append("")
    parts.append(_render_falsifications(falsifications))
    parts.append("## Execution Risks")
    parts.append("")
    parts.append(_render_risks(risks))
    parts.append("## Implicit Recommendation")
    parts.append("")
    parts.append(f"`{implicit_thesis}`")
    parts.append("")
    parts.append("## Constraint Compliance")
    parts.append("")
    parts.append(_render_constraint_compliance(constraint_compliance))
    parts.append("---")
    parts.append("")
    parts.append(
        "_Generated by `skills/domain/master_md.py` from the archived "
        "synthesis row. Do not hand-edit; re-run the converter if the "
        "synthesis is updated._"
    )
    parts.append("")
    return "\n".join(parts)


def existing_marker_matches(path: Path, synthesis_id: str) -> bool:
    """True iff ``path`` exists AND its first 4 KiB include the
    ``<!-- synthesis_id: <id> -->`` marker. Reading the head only is a
    cost / safety choice — the marker sits on the first line by
    construction."""
    if not path.exists():
        return False
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            head = f.read(_IDEMPOTENCY_HEAD_BYTES)
    except OSError:
        return False
    return f"{SYNTHESIS_ID_MARKER}{synthesis_id} -->" in head


# ---------------------------------------------------------------------------
# Atomic write + typed emit
# ---------------------------------------------------------------------------


def _safe_emit_written(
    *,
    investigation_id: str | None,
    synthesis_id: str,
    path: str,
    byte_count: int,
    topic_slug: str | None,
) -> None:
    """Best-effort MASTER_MD_WRITTEN emit. Telemetry must never fail
    the disk-write path."""
    try:
        emit_typed(
            investigation_id or synthesis_id,
            MasterMdWrittenPayload(
                path=path,
                synthesis_id=synthesis_id,
                byte_count=byte_count,
                topic_slug=topic_slug,
                param_version=ANTIEK_PARAM_VERSION,
            ),
            synthesis_id=synthesis_id,
            role="master_md",
            policy_id="orchestrator-deterministic",
        )
    except Exception as e:  # pragma: no cover — diagnostic only
        print(
            f"master_md → MASTER_MD_WRITTEN emit failed (non-fatal): {e!r}",
            file=sys.stderr,
        )


def _safe_emit_skipped(
    *,
    investigation_id: str | None,
    synthesis_id: str,
    path: str,
    byte_count: int,
    topic_slug: str | None,
    reason: str,
) -> None:
    try:
        emit_typed(
            investigation_id or synthesis_id,
            MasterMdSkippedPayload(
                path=path,
                synthesis_id=synthesis_id,
                byte_count=byte_count,
                topic_slug=topic_slug,
                reason=reason,
            ),
            synthesis_id=synthesis_id,
            role="master_md",
            policy_id="orchestrator-deterministic",
        )
    except Exception as e:  # pragma: no cover — diagnostic only
        print(
            f"master_md → MASTER_MD_SKIPPED emit failed (non-fatal): {e!r}",
            file=sys.stderr,
        )


def generate_master_md(
    row: dict[str, Any],
    *,
    topic_slug: str | None = None,
    output_dir: str | None = None,
    research_base: Path | None = None,
    filename: str = DEFAULT_FILENAME,
) -> Path:
    """Generate ``<output_dir>/<filename>`` from ``row``.

    Path resolution order:

    1. ``output_dir`` is honored verbatim when provided.
    2. Otherwise the slug is ``topic_slug``, else derived from
       ``row["target_question"]``, else from ``investigation_id``,
       else ``untitled``.
    3. The target directory becomes
       ``research_base / slug`` (research_base defaults to
       ``ANTIEK_RESEARCH_DIR`` or ``~/research``).

    Idempotency: a fresh ``MasterMdSkippedPayload`` is emitted and the
    existing path is returned without re-rendering when the on-disk
    file's first 4 KiB carries the same synthesis_id marker.

    Returns the resolved absolute Path.
    """
    synthesis_id = row["synthesis_id"]
    investigation_id = row.get("investigation_id")

    if output_dir is None:
        slug = topic_slug or slugify(
            row.get("target_question") or "",
        ) or slugify(investigation_id or "") or "untitled"
        base = research_base if research_base is not None else default_research_base()
        out_dir = Path(base) / slug
        resolved_slug = slug
    else:
        out_dir = Path(output_dir)
        resolved_slug = topic_slug  # may be None; passed through for traceability

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (out_dir / filename).resolve()

    # Idempotency check
    if existing_marker_matches(out_path, synthesis_id):
        size = out_path.stat().st_size
        _safe_emit_skipped(
            investigation_id=investigation_id,
            synthesis_id=synthesis_id,
            path=str(out_path),
            byte_count=size,
            topic_slug=resolved_slug,
            reason="idempotent_match",
        )
        return out_path

    body = build_master_md(row)

    # Atomic write — temp + replace so a partial write can't corrupt
    # an existing MASTER.md.
    tmp_path = out_path.with_suffix(out_path.suffix + ".tmp")
    tmp_path.write_text(body, encoding="utf-8")
    os.replace(tmp_path, out_path)
    byte_count = out_path.stat().st_size

    _safe_emit_written(
        investigation_id=investigation_id,
        synthesis_id=synthesis_id,
        path=str(out_path),
        byte_count=byte_count,
        topic_slug=resolved_slug,
    )
    return out_path
