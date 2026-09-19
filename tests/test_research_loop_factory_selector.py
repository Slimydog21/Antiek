"""Selector tests for cascade_routes._research_loop_factory — no network."""

from __future__ import annotations

import pytest

STUB_SENTINEL = object()
EXA_SENTINEL = object()
MULTI_SENTINEL = object()


@pytest.fixture
def cascade_routes():
    from interfaces.research.api import cascade_routes as mod

    return mod


def test_factory_default_calls_stub_not_exa(monkeypatch, cascade_routes):
    monkeypatch.delenv("ANTIEK_DRW_GATHER", raising=False)

    def fake_stub(*, steps: int, cost_per_step: float):
        assert steps == 2
        assert cost_per_step == 0.01
        return STUB_SENTINEL

    def fake_exa(*, top_k: int):
        pytest.fail("make_exa_gather_loop must not be called when env unset / non-exa")

    monkeypatch.setattr(cascade_routes, "make_contract_gather_stub", fake_stub)
    monkeypatch.setattr(cascade_routes, "make_exa_gather_loop", fake_exa)

    assert cascade_routes._research_loop_factory() is STUB_SENTINEL


def test_factory_exa_env_returns_exa_sentinel(monkeypatch, cascade_routes):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "exa")

    def fake_stub(*, steps: int, cost_per_step: float):
        pytest.fail("make_contract_gather_stub must not be called when ANTIEK_DRW_GATHER=exa")

    def fake_exa(*, top_k: int, **kwargs):
        assert top_k == 3
        assert kwargs["enable_reasoning"] is True
        return EXA_SENTINEL

    monkeypatch.setattr(cascade_routes, "make_contract_gather_stub", fake_stub)
    monkeypatch.setattr(cascade_routes, "make_exa_gather_loop", fake_exa)

    assert cascade_routes._research_loop_factory() is EXA_SENTINEL


def test_factory_garbage_env_falls_back_to_stub(monkeypatch, cascade_routes):
    monkeypatch.setenv("ANTIEK_DRW_GATHER", "banana")

    def fake_stub(*, steps: int, cost_per_step: float):
        assert steps == 2
        assert cost_per_step == 0.01
        return STUB_SENTINEL

    def fake_exa(*, top_k: int):
        pytest.fail("make_exa_gather_loop must not be called for garbage env value")

    monkeypatch.setattr(cascade_routes, "make_contract_gather_stub", fake_stub)
    monkeypatch.setattr(cascade_routes, "make_exa_gather_loop", fake_exa)

    assert cascade_routes._research_loop_factory() is STUB_SENTINEL


def test_factory_multi_source_requires_and_forwards_reviewed_authority(
    monkeypatch, cascade_routes
):
    authority = object()
    launch_plan = object()

    def fake_multi(**kwargs):
        assert kwargs["launch_plan"] is launch_plan
        assert kwargs["authority"] is authority
        assert kwargs["feed_urls"] == ("https://writer.example/feed",)
        return MULTI_SENTINEL

    monkeypatch.setattr(cascade_routes, "make_authorized_multi_source_gather_loop", fake_multi)
    assert (
        cascade_routes._research_loop_factory(
            gather_mode="authorized_multi_source",
            authority=authority,
            multi_source_launch_plan=launch_plan,
            multi_source_feed_urls=("https://writer.example/feed",),
        )
        is MULTI_SENTINEL
    )


def test_factory_multi_source_never_falls_back_to_stub(monkeypatch, cascade_routes):
    monkeypatch.setattr(
        cascade_routes,
        "make_contract_gather_stub",
        lambda **kwargs: pytest.fail("multi-source must not fall back to stub"),
    )
    with pytest.raises(ValueError, match="requires reviewed authority"):
        cascade_routes._research_loop_factory(gather_mode="authorized_multi_source")
