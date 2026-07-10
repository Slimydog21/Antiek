"""Research brief model, projection, clarification, gate, and provenance."""

from .clarifier import clarifying_questions, fold_answers
from .lifecycle import RunToken, amend, approve, run_token
from .model import BriefState, BudgetTuple, LifecycleEvent, ResearchBrief
from .project_html import parse_html, project_to_html
from .provenance import BriefRunRecord, brief_content_hash, link_run

__all__ = [
    "BriefRunRecord", "BriefState", "BudgetTuple", "LifecycleEvent", "ResearchBrief",
    "RunToken", "amend", "approve", "brief_content_hash", "clarifying_questions",
    "fold_answers", "link_run", "parse_html", "project_to_html", "run_token",
]
