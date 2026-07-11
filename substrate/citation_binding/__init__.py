"""SPR-04 citation binding, HTML projection, and FACT support gate."""

from .bind import bind_report, segment_claims
from .gate import SUPPORT_THRESHOLD, Blocked, Done, GateOutcome, SupportJudge, gate_report
from .model import AnnotatedReport, CitationAnnotation, Claim
from .project_html import project_to_html

__all__ = [
    "SUPPORT_THRESHOLD", "AnnotatedReport", "Blocked", "CitationAnnotation",
    "Claim", "Done", "GateOutcome", "SupportJudge", "bind_report",
    "gate_report", "project_to_html", "segment_claims",
]
