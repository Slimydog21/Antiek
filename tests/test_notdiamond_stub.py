"""NotDiamond orchestration stub."""


from substrate.dispatch.orchestration import (
    OrchestrationPlan,
    notdiamond_enabled,
    plan_research_lane,
)


def test_notdiamond_enabled_is_bool() -> None:
    assert isinstance(notdiamond_enabled(), bool)


def test_plan_interactive_user_present():
    plan = plan_research_lane(user_present=True)
    assert isinstance(plan, OrchestrationPlan)
    assert plan.latency_mode == "interactive"
    assert plan.primary_lane == "glm_tilert"


def test_plan_autonomous_synthesis():
    plan = plan_research_lane(user_present=False, task_kind="synthesis")
    assert plan.latency_mode == "autonomous"
    assert plan.primary_lane == "kimi"


def test_notdiamond_kill_switch(monkeypatch):
    monkeypatch.setenv("ANTIEK_NOTDIAMOND_DISABLED", "1")
    assert notdiamond_enabled() is False
    plan = plan_research_lane(user_present=False, task_kind="synthesis")
    assert "disabled" in plan.notes.lower()