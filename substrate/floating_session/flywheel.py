"""Session completion → twin deposit → promote → research context flywheel.

One product entry that closes the recursive note-taker loop for a finished
floating deep-research session: insights/questions land on the twin
substrate, promote into depth-graph (injectable), and return an assembled
research context pack ready for the next prompt.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from substrate.engagement_spine.research_context import ResearchContextPack
from substrate.engagement_spine.store import EngagementStore

from .context_bridge import session_research_context
from .session import FloatingSession, complete_session_research
from .store import SessionStore


@dataclass(frozen=True)
class SessionFlywheelResult:
    """Outcome of complete → twin → promote → context pack."""

    session: FloatingSession
    context: ResearchContextPack
    view_format: str = "html"

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session.session_id,
            "spawn_id": self.session.spawn_id,
            "status": self.session.status,
            "context": self.context.to_dict(),
            "view_format": self.view_format,
            "prompt_block": self.context.prompt_block(),
            # Residual (jt): surface session research_tier for Antiek-bench.
            "research_tier": getattr(self.session, "research_tier", None)
            or "deep",
        }


def complete_session_with_context_flywheel(
    session_id: str,
    *,
    session_store: SessionStore,
    engagement_store: EngagementStore,
    output_text: str,
    insights: Sequence[str] = (),
    questions: Sequence[str] = (),
    query: str | None = None,
    promote_insight_fn: Any = None,
    promote_question_fn: Any = None,
    record_twins: bool = True,
    include_twin_promote: bool = True,
) -> SessionFlywheelResult:
    """Complete research, deposit twins, promote, assemble context pack.

    Pure composition of existing surfaces — no second writers.
    """
    session = complete_session_research(
        session_id,
        session_store=session_store,
        engagement_store=engagement_store,
        output_text=output_text,
        insights=list(insights),
        questions=list(questions),
        record_twins=record_twins,
    )
    pack = session_research_context(
        session_id,
        session_store=session_store,
        engagement_store=engagement_store,
        query=query,
        promote_insight_fn=promote_insight_fn,
        promote_question_fn=promote_question_fn,
        include_twin_promote=include_twin_promote,
    )
    return SessionFlywheelResult(session=session, context=pack, view_format="html")
