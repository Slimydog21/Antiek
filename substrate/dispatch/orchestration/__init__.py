"""Future multi-model orchestration (NotDiamond, CEO tier).

Antiek keeps a single ``dispatch()`` entry (§16). Orchestrators choose
``latency_mode``, research tier, or provider_override — they do not fork
the router.
"""

from .notdiamond import OrchestrationPlan, notdiamond_enabled, plan_research_lane

__all__ = ["OrchestrationPlan", "plan_research_lane"]