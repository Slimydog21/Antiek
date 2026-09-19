"""Dispatch env bootstrap: load keys + skip unregistered without poison emit."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from interfaces.research.api.boot_providers import load_dispatch_env_files
from substrate.dispatch.base import NormalizedUsage, RawProviderResponse
from substrate.dispatch.router import (
    DispatchConfig,
    dispatch,
    register_provider,
    reset_provider_registry,
)
from substrate.event_log import trajectory


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    reset_provider_registry()
    yield
    reset_provider_registry()


@pytest.fixture
def _events_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    import substrate.event_log.events as evmod

    monkeypatch.setattr(evmod, "default_events_dir", lambda: str(events))
    return events


@pytest.fixture(scope="module")
def production_config() -> DispatchConfig:
    cfg_path = (
        Path(__file__).resolve().parents[1]
        / "substrate"
        / "dispatch"
        / "config.yaml"
    )
    return DispatchConfig.from_yaml(cfg_path)


def test_load_dispatch_env_files_sets_missing_keys(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / "keys.env"
    env_file.write_text("DEEPSEEK_API_KEY=sk-test-deepseek\nALREADY=from-file\n")
    monkeypatch.setenv("ANTIEK_ENV_FILE", str(env_file))
    monkeypatch.setenv("ALREADY", "from-process")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    loaded = load_dispatch_env_files()
    assert str(env_file) in loaded
    assert os.environ["DEEPSEEK_API_KEY"] == "sk-test-deepseek"
    assert os.environ["ALREADY"] == "from-process"


class _WorkingDeepSeek:
    name = "deepseek"

    def call(self, *, model, prompt, max_tokens, temperature) -> RawProviderResponse:
        return RawProviderResponse(
            text="ok from deepseek",
            raw_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            finish_reason="stop",
            latency_ms=5,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
            cached_input_tokens=0,
        )


def test_unregistered_primary_skips_without_error_emit(
    production_config: DispatchConfig,
    _events_dir: Path,
) -> None:
    """Missing zai must fall through to deepseek with only one dispatch.call."""
    register_provider(_WorkingDeepSeek())
    inv = "inv-skip-unreg"
    result = dispatch(
        "test prompt",
        "decomposer",
        investigation_id=inv,
        config=production_config,
    )
    assert result.provider == "deepseek"
    assert result.finish_reason == "stop"
    rows = [r for r in trajectory(inv) if r.get("action_type") == "dispatch.call"]
    assert len(rows) == 1
    assert rows[0]["payload"]["provider"] == "deepseek"
    assert rows[0]["payload"]["finish_reason"] == "stop"
