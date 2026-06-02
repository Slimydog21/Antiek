"""Domain-skill markdown patching.

Phase 8 takes a dict of ``{section_name: [finding...]}`` and applies
each finding as a bullet under the matching ``## Section Name``
heading in the target ``SKILL.md`` file.

Splits into:

- ``find_section_boundaries(content, section_name)`` — pure, returns
  ``(start_line_idx, end_line_idx, current_content_text)``.
- ``format_finding_bullet(text, confidence, date_observed, source)``
  — pure, returns one bullet string.
- ``apply_finding_to_section(current, text, confidence, date_observed,
  source)`` — pure string transformation.
- ``patch_skill(skill_name, findings, *, skills_root=None)`` —
  file-system boundary. Returns the list of section names that were
  patched (used by the orchestrator to emit Phase 8 telemetry).

The 2026-05-14 ``WP-A4`` fix is preserved: the section-header regex
matches ``H2 or deeper`` (``## or ###``) so top-level sections like
``Domain Fundamentals`` actually find their headers, and the section
name is matched as a **prefix** so ``Open Questions`` also matches
``## Open Questions & Uncertainties``.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def default_skills_root() -> Path:
    """The on-disk knowledge skills directory. ``ANTIEK_KNOWLEDGE_SKILLS_DIR``
    overrides; the default mirrors upstream
    ``~/.hermes/skills/knowledge/``."""
    raw = os.environ.get(
        "ANTIEK_KNOWLEDGE_SKILLS_DIR",
        os.path.join(
            os.environ.get("ANTIEK_HOME", os.path.expanduser("~/.antiek")),
            "knowledge_skills",
        ),
    )
    return Path(raw)


# Placeholder string the template SKILL.md files use before any
# findings have been merged. ``apply_finding_to_section`` replaces it
# instead of appending so the first compounding pass doesn't leave a
# stranded "(Findings will be added.)" line above the new bullet.
PLACEHOLDER_TEXT = "(Findings will be added.)"


def find_section_boundaries(
    skill_content: str, section_name: str,
) -> tuple[int, int, str]:
    """Find the line-range and text of one section.

    Returns ``(start_line, end_line, current_content_between_headers)``.

    - ``start_line`` is the line index AFTER the section header.
    - ``end_line`` is the line index of the next ``##+`` header (or
      ``len(lines)`` for the file-tail section).
    - Returns ``(-1, -1, "")`` when no matching header is found —
      the patcher logs and skips silently in that case.

    Match rules (the 2026-05-14 WP-A4 fix):
    - H2 or deeper (``##`` / ``###``).
    - Case-insensitive.
    - Section name is a PREFIX — ``"Open Questions"`` matches both
      ``"## Open Questions"`` and ``"## Open Questions & Uncertainties"``.
    """
    lines = skill_content.split("\n")
    section_pattern = re.compile(
        rf"^#{{2,}}\s+{re.escape(section_name)}\b", re.IGNORECASE
    )

    start_idx: int | None = None
    for i, line in enumerate(lines):
        if section_pattern.match(line):
            start_idx = i + 1  # content starts after the header
            break

    if start_idx is None:
        return -1, -1, ""

    end_idx = len(lines)
    for i in range(start_idx, len(lines)):
        if re.match(r"^##+\s+", lines[i]):
            end_idx = i
            break

    current = "\n".join(lines[start_idx:end_idx])
    return start_idx, end_idx, current


def format_finding_bullet(
    text: str,
    confidence: str,
    date_observed: str,
    source: str,
) -> str:
    """Render one finding as a markdown bullet.

    Layout: ``- [Confidence] (YYYY-MM) finding text — source``

    Empty fields are dropped (no leading ``[]`` if confidence is
    missing; no trailing ``—`` if source is missing); double spaces
    are squeezed."""
    confidence_tag = f"[{confidence}]" if confidence else ""
    date_tag = f"({date_observed})" if date_observed else ""
    source_tag = f"— {source}" if source else ""

    new_bullet = f"- {confidence_tag} {date_tag} {text} {source_tag}".strip()
    return re.sub(r" +", " ", new_bullet)


def apply_finding_to_section(
    current_content: str,
    *,
    text: str,
    confidence: str = "",
    date_observed: str = "",
    source: str = "",
) -> str:
    """Append (or replace placeholder) one finding bullet into a
    section's body. Pure — caller writes the result back to disk."""
    new_bullet = format_finding_bullet(
        text=text,
        confidence=confidence,
        date_observed=date_observed,
        source=source,
    )

    if PLACEHOLDER_TEXT in current_content:
        # Cascade of replace() preserves the upstream's intent: handle
        # placeholder-followed-by-blank-line, leading-newline-then-
        # placeholder, and standalone placeholder shapes the templates
        # produce in practice. Order matters — the longest pattern first
        # so the trailing newline doesn't get eaten twice.
        return current_content.replace(
            f"{PLACEHOLDER_TEXT}\n\n", new_bullet + "\n",
        ).replace(
            f"\n{PLACEHOLDER_TEXT}", "\n" + new_bullet,
        ).replace(
            PLACEHOLDER_TEXT, new_bullet,
        )

    if not current_content.strip():
        return new_bullet
    if current_content.rstrip().endswith("\n"):
        return current_content + new_bullet + "\n"
    return current_content + "\n" + new_bullet + "\n"


def patch_skill(
    skill_name: str,
    findings: dict,
    *,
    skills_root: Path | None = None,
) -> list[str]:
    """Patch a knowledge skill with extracted findings.

    Returns the list of section names that were successfully patched
    (drives the Phase 8 patched-sections telemetry on the orchestrator).

    File I/O at the boundary: load, transform per section, write back
    if anything changed. Missing skill files / missing sections print
    to stderr and are skipped (mirrors upstream — Phase 8 is best-effort
    and must never block synthesis archival)."""
    root = skills_root or default_skills_root()
    skill_path = root / skill_name / "SKILL.md"
    if not skill_path.exists():
        print(
            f"skills.domain.patch: skill {skill_name} not found at {skill_path}",
            file=sys.stderr,
        )
        return []

    content = skill_path.read_text()
    patched_sections: list[str] = []

    for section_name, finding_list in findings.items():
        if not finding_list:
            continue
        start, end, current = find_section_boundaries(content, section_name)
        if start == -1:
            print(
                f"skills.domain.patch: section {section_name!r} not found in "
                f"{skill_name}",
                file=sys.stderr,
            )
            continue

        new_section_content = current
        for finding in finding_list:
            if not isinstance(finding, dict):
                continue
            new_section_content = apply_finding_to_section(
                new_section_content,
                text=finding.get("text", ""),
                confidence=finding.get("confidence", ""),
                date_observed=finding.get("date_observed", ""),
                source=finding.get("source", ""),
            )

        if new_section_content != current:
            lines = content.split("\n")
            lines[start:end] = new_section_content.split("\n")
            content = "\n".join(lines)
            patched_sections.append(section_name)

    if patched_sections:
        skill_path.write_text(content)
        print(
            f"skills.domain.patch: patched {skill_name} sections "
            f"{patched_sections}",
            file=sys.stderr,
        )

    return patched_sections
