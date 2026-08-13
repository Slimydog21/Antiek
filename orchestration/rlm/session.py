"""RLM session orchestrator (rlm_integration_spec.md RLM-1).

State machine for long-doc wrestling with the RLM pattern. Ships
behind a ratification gate — six design decisions in
`rlm_integration_spec.md` §6 must be ratified before sessions can
run. Refuses to start otherwise.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

# Per rlm_integration_spec.md proposed constants (Section F additions).
RLM_DOC_THRESHOLD_TOKENS: int = 64_000  # documents above this use RLM mode
RLM_REPL_PER_CALL_TIMEOUT_SECONDS: int = 120
RLM_SESSION_COST_USD_CAP: Decimal = Decimal("5.00")


# Tool-isolation invariant per rlm_integration_spec.md Paper §2
# choice #3: every tool attaches to SubLLMWithTools, never the root
# REPL. Static check enforced in tests.
class RLMToolIsolationViolation(Exception):
    pass


class RLMRatificationRequired(Exception):
    """Raised if a session is created before §6 ratification.

    Per master-spec §15.7: 'six design decisions blocking RLM-1.
    Ratify the six decisions in a single review session when RLM-1
    sequences into priority (after Sprint 20). Pre-Sprint-20 they're
    premature to litigate.'

    Sessions refuse to run without operator-set ANTIEK_RLM_RATIFIED=1
    in env. The env var name is intentional — operator's lawyer-style
    discipline: explicit affirmative ratification, not a default."""


def _check_ratified() -> None:
    if os.environ.get("ANTIEK_RLM_RATIFIED", "") != "1":
        raise RLMRatificationRequired(
            "RLM track requires §6 design decisions ratified. "
            "Six decisions per rlm_integration_spec.md §6: "
            "RLM-as-bridge stance, cost attribution to root role, "
            "$5 session cap, subllm_role_tiers flash split, "
            "per-iteration event granularity, 64K wrestling threshold. "
            "Set ANTIEK_RLM_RATIFIED=1 after the review session."
        )


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SubLLMWithTools:
    """A sub-LLM equipped with tools. Per the tool-isolation
    invariant, ALL tools attach here — NEVER to the root REPL.
    The root REPL only dispatches to sub-LLMs; sub-LLMs do the
    tool calls."""

    name: str
    tools: tuple[str, ...]


@dataclass
class RLMSessionState:
    """State of an in-flight RLM session."""

    session_id: str
    investigation_id: str
    root_role: str  # the role that triggered the RLM session (synthesizer | wrestler)
    document_id: str | None
    root_executor: str = "dispatch"
    prime_goal_brief: str | None = None
    iteration_count: int = 0
    cost_usd_accumulated: Decimal = Decimal("0.00")
    started_at: str = field(default_factory=_now_iso)
    completed_at: str | None = None
    status: str = "in_progress"  # | "completed" | "failed" | "cost_capped"


@dataclass
class RLMSession:
    """The RLM session orchestrator. Holds the state + iteration
    machinery. Per rlm_integration_spec.md proposed event vocabulary,
    five new typed events:
        rlm.session_started, rlm.iteration, rlm.sub_call_dispatched,
        rlm.session_completed, rlm.session_failed
    These ship as part of the substrate event-log schema in the
    RLM-1 substrate-side work."""

    state: RLMSessionState
    sub_llms: list[SubLLMWithTools] = field(default_factory=list)
    iterations: list[dict] = field(default_factory=list)

    def record_iteration(self, *, summary: str, cost_usd: Decimal) -> None:
        """Record one iteration's outcome. Enforces the session cost
        cap per rlm_integration_spec.md $5 default."""
        if self.state.cost_usd_accumulated + cost_usd > RLM_SESSION_COST_USD_CAP:
            self.state.status = "cost_capped"
            self.state.completed_at = _now_iso()
            return
        self.state.iteration_count += 1
        self.state.cost_usd_accumulated += cost_usd
        self.iterations.append({
            "iteration": self.state.iteration_count,
            "summary": summary,
            "cost_usd": str(cost_usd),
            "at": _now_iso(),
        })

    def complete(self, *, final_summary: str) -> None:
        """Mark the session complete. The final summary flows back
        to the root role (synthesizer or wrestler) as the long-doc
        condensation."""
        self.state.status = "completed"
        self.state.completed_at = _now_iso()
        self.iterations.append({
            "iteration": "final",
            "summary": final_summary,
            "cost_usd": "0.00",
            "at": _now_iso(),
        })

    def attach_tool_to_sub_llm(self, sub_llm_name: str, tool_name: str) -> None:
        """Attach a tool to a sub-LLM. Per tool-isolation invariant,
        the substrate refuses to attach a tool to the root REPL
        (sub_llm_name='root' or 'repl' raises)."""
        if sub_llm_name in {"root", "repl", "root_repl"}:
            raise RLMToolIsolationViolation(
                f"tools cannot attach to the root REPL; attach to a "
                f"SubLLMWithTools instead (got sub_llm_name={sub_llm_name!r})"
            )
        # Find or create the sub-LLM.
        for i, s in enumerate(self.sub_llms):
            if s.name == sub_llm_name:
                self.sub_llms[i] = SubLLMWithTools(
                    name=s.name, tools=tuple(list(s.tools) + [tool_name]),
                )
                return
        self.sub_llms.append(SubLLMWithTools(name=sub_llm_name, tools=(tool_name,)))


def create_session(
    *,
    investigation_id: str,
    root_role: str,
    document_id: str | None = None,
    root_executor: str = "dispatch",
    prime_goal_brief: str | None = None,
) -> RLMSession:
    """Create an RLM session. Refuses to run if §6 ratification is
    not set."""
    _check_ratified()
    return RLMSession(state=RLMSessionState(
        session_id=f"rlm-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        root_role=root_role,
        document_id=document_id,
        root_executor=root_executor,
        prime_goal_brief=prime_goal_brief,
    ))


def iterate_session(
    session: RLMSession,
    *,
    summary: str,
    cost_usd: Decimal,
) -> None:
    """One iteration step. Operator wires real dispatch around this
    once the sub-LLM-with-tools tooling lands."""
    session.record_iteration(summary=summary, cost_usd=cost_usd)
