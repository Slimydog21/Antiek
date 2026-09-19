"""Research-topic aggregation primitive per master-spec §7.3.

The spec calls for a ``research_topic`` concept that aggregates
investigations sharing context. Multiple investigations on the same
root question get rolled into one topic's "running master doc."

This module provides the minimal substrate primitive:

  - A deterministic ``topic_id_for(root_question)`` hash so different
    callers (the daemon, the operator's manual chase) agree on which
    investigations belong to the same topic.
  - A ``ResearchTopic`` accumulator the daemon uses to track depth
    (for the §7.4 max-5-levels cap) and the running list of
    investigation_ids per topic.

The topic is intentionally NOT persisted to DuckDB in this MVP — the
daemon rebuilds the topic graph from the event log each iteration.
Persistence belongs to a later sprint (Sprint 22+ multi-user) when
research_topic becomes a queryable substrate object.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

# Master-spec §7.4 hard cap on per-topic chase depth.
MAX_TOPIC_DEPTH: int = 5


def topic_id_for(root_question: str) -> str:
    """Stable ``topic-<sha256[:12]>`` id for a root question. The same
    root question always maps to the same topic_id across daemon
    restarts and across operator vs daemon spawns.

    The id is short enough to fit in event-log policy_id fields but
    long enough to make collisions across realistic question volumes
    negligible.
    """
    if not root_question or not root_question.strip():
        raise ValueError("empty root_question")
    normalized = " ".join(root_question.lower().split())[:300]
    h = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"topic-{h}"


@dataclass
class ResearchTopic:
    """In-memory aggregation of investigations under one root question.

    Owned by the daemon for one iteration. Reconstructed from the
    event log on each iteration; never persisted in MVP.
    """

    topic_id: str
    root_question: str
    investigation_ids: list[str] = field(default_factory=list)
    max_depth_reached: int = 0

    @property
    def investigation_count(self) -> int:
        return len(set(self.investigation_ids))

    @property
    def depth_remaining(self) -> int:
        """Levels of chase still allowed under this topic. Returns 0
        once the §7.4 hard cap is hit."""
        return max(0, MAX_TOPIC_DEPTH - self.max_depth_reached)

    def can_chase(self) -> bool:
        return self.depth_remaining > 0

    def record_spawn(
        self,
        investigation_id: str,
        *,
        depth: int = 1,
    ) -> None:
        """Note a new spawn under this topic. ``depth`` is the chase
        level of the new investigation (root=0, first child=1, etc.).
        The topic tracks the deepest level seen so far."""
        if investigation_id not in self.investigation_ids:
            self.investigation_ids.append(investigation_id)
        if depth > self.max_depth_reached:
            self.max_depth_reached = depth
