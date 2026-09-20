"""Dispatch binding — the lineup registry ACTUALLY changes routing.

All offline: a fake registered provider serves the dispatch call; the
lineup registry is redirected to tmp via env. The tier fallback chain is
preserved for unregistered override providers (preference, not SPOF).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from substrate.dispatch.base import NormalizedUsage, RawProviderResponse
from substrate.dispatch.router import (
    DispatchConfig,
    dispatch,
    register_provider,
    reset_provider_registry,
)

REGISTRY_V1 = {
    "owners": {
        "__operator__": {
            "general": {
                "writer": {"provider_id": "zai", "model_id": "glm-5.2"},
                "data_verification": None,
            },
            "advanced": {
                "verification": {"provider_id": "deepseek", "model_id": "deepseek-v4-pro"},
            },
            "updated_at": "2026-08-12T20:00:00Z",
        }
    }
}


class _FakeProvider:
    """Duck-typed provider following the house test pattern (dispatch
    tests do not subclass the Protocol)."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.family = f"{name}-family"
        self.calls: list[dict] = []

    def call(self, *, model, prompt, max_tokens, temperature):  # type: ignore[no-untyped-def]
        self.calls.append({"model": model})
        return RawProviderResponse(
            text="fake-ok",
            raw_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            finish_reason="stop",
            latency_ms=1,
        )

    def normalize_usage(self, raw_usage: dict):  # type: ignore[no-untyped-def]
        return NormalizedUsage(input_tokens=1, output_tokens=1)


def _write_registry(tmp: Path, payload: dict) -> None:
    path = tmp / "settings" / "lineup.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ANTIEK_LINEUP_PATH", str(tmp_path / "settings" / "lineup.json"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    reset_provider_registry()
    return tmp_path


@pytest.fixture
def cfg() -> DispatchConfig:
    return DispatchConfig.from_yaml(
        Path(__file__).resolve().parents[1] / "substrate" / "dispatch" / "config.yaml"
    )


def test_no_registry_uses_platform_default(env: Path, cfg: DispatchConfig) -> None:
    register_provider(_FakeProvider(name="zai"))
    result = dispatch(
        "hello", "verifier", investigation_id="i-1", config=cfg,
    )
    assert result.provider == "zai"
    assert result.model == "glm-5.2"


def test_action_assignment_routes_the_dispatch_role(env: Path, cfg: DispatchConfig) -> None:
    _write_registry(env, REGISTRY_V1)
    register_provider(_FakeProvider(name="zai"))
    register_provider(_FakeProvider(name="deepseek"))
    # advanced["verification"] = deepseek/deepseek-v4-pro → role verifier
    result = dispatch("check", "verifier", investigation_id="i-2", config=cfg)
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-pro"


def test_role_assignment_routes_all_owned_roles(env: Path, cfg: DispatchConfig) -> None:
    _write_registry(env, REGISTRY_V1)
    register_provider(_FakeProvider(name="zai"))
    # writer role → zai/glm-5.2 → synthesizer (owned by writer)
    result = dispatch("synthesize", "synthesizer", investigation_id="i-3", config=cfg)
    assert result.provider == "zai"
    assert result.model == "glm-5.2"


def test_unassigned_role_keeps_platform_default(env: Path, cfg: DispatchConfig) -> None:
    _write_registry(env, REGISTRY_V1)
    register_provider(_FakeProvider(name="zai"))
    # data_verification role is None → verifier's action assignment absent
    # for grounder (grounder is owned by data_verification, general=None)
    result = dispatch("ground", "grounder", investigation_id="i-4", config=cfg)
    assert result.provider == "zai"
    assert result.model == "glm-5.2"


def test_unregistered_override_provider_falls_back(env: Path, cfg: DispatchConfig) -> None:
    _write_registry(
        env,
        {
            "owners": {
                "__operator__": {
                    "general": {},
                    "advanced": {
                        "verification": {"provider_id": "does-not-exist", "model_id": "x"},
                    },
                }
            }
        },
    )
    register_provider(_FakeProvider(name="zai"))
    register_provider(_FakeProvider(name="deepseek"))
    result = dispatch("check", "verifier", investigation_id="i-5", config=cfg)
    # the override replaces the verify tier's PRIMARY; the fallback chain
    # (deepseek → xiaomi) is preserved → deepseek answers
    assert result.provider == "deepseek"
    assert result.model == "deepseek-v4-pro"


def test_caller_explicit_override_beats_lineup(env: Path, cfg: DispatchConfig) -> None:
    _write_registry(env, REGISTRY_V1)
    register_provider(_FakeProvider(name="zai"))
    register_provider(_FakeProvider(name="deepseek"))
    register_provider(_FakeProvider(name="xiaomi"))
    result = dispatch(
        "check",
        "verifier",
        investigation_id="i-6",
        config=cfg,
        provider_override="xiaomi",
        model_override="mimo-v2.5-pro",
    )
    assert result.provider == "xiaomi"
    assert result.model == "mimo-v2.5-pro"
