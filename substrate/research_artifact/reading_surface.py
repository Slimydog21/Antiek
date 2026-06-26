"""Load, render, and condense KB-static ResearchArtifact HTML for reading."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .import_notes import parse_body_from_html
from .projection_verify import has_executable_scripts, has_provenance_markers
from .schema import ResearchArtifactBody


def kb_artifact_minimal_fixture_path() -> Path:
    """Cross-language contract fixture (pytest + vitest)."""
    root = Path(__file__).resolve().parents[2]
    return root / "tests" / "fixtures" / "kb_artifact_minimal.html"


@dataclass(frozen=True)
class ReadingCondensedView:
    """Substrate-faithful condensation for reading UI and graph navigation."""

    investigation_id: str
    problem_question: str
    content_hash: str
    findings: tuple[tuple[str, str, str | None], ...]
    open_gaps: tuple[tuple[str, str, bool], ...]
    synthesis_excerpt: str | None
    agent_notes: tuple[str, ...]
    html_bytes: int
    script_free: bool


def load_kb_artifact_html(path: Path | str) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(p)
    return p.read_text(encoding="utf-8")


def condense_body_for_reading(body: ResearchArtifactBody) -> ReadingCondensedView:
    findings = tuple(
        (ins.node_id, ins.text, ins.confidence) for ins in body.insights
    )
    gaps = tuple((q.node_id, q.text, q.escalated) for q in body.open_questions)
    return ReadingCondensedView(
        investigation_id=body.investigation_id,
        problem_question=body.problem_question,
        content_hash=body.content_hash(),
        findings=findings,
        open_gaps=gaps,
        synthesis_excerpt=body.synthesis_excerpt,
        agent_notes=tuple(n for n in body.agent_notes if (n or "").strip()),
        html_bytes=0,
        script_free=True,
    )


def consume_kb_artifact(path: Path | str) -> ReadingCondensedView:
    """Load HTML projection, parse canonical JSON island, return condensed view."""
    html = load_kb_artifact_html(path)
    if has_executable_scripts(html):
        raise ValueError("KB artifact must be script-free for reading consumption")
    if not has_provenance_markers(html):
        raise ValueError("KB artifact missing provenance markers")
    body = parse_body_from_html(html)
    view = condense_body_for_reading(body)
    return ReadingCondensedView(
        investigation_id=view.investigation_id,
        problem_question=view.problem_question,
        content_hash=view.content_hash,
        findings=view.findings,
        open_gaps=view.open_gaps,
        synthesis_excerpt=view.synthesis_excerpt,
        agent_notes=view.agent_notes,
        html_bytes=len(html.encode("utf-8")),
        script_free=True,
    )