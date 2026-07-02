from __future__ import annotations

import builtins
import errno
import os
from dataclasses import dataclass
from typing import Any

import pytest

from runtime import db_lock
from substrate.dispatch.base import NormalizedUsage, ProviderError, RawProviderResponse
from substrate.dispatch.router import (
    DispatchConfig,
    TierConfig,
    dispatch,
    register_provider,
    reset_provider_registry,
)
from tools.faultinject import arm, locked_db, provider_fault, readonly_fs


@dataclass
class StubProvider:
    name: str
    text: str
    calls: int = 0

    def call(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int,
        temperature: float,
    ) -> RawProviderResponse:
        self.calls += 1
        return RawProviderResponse(
            text=self.text,
            raw_usage={"prompt_tokens": 1, "completion_tokens": 1},
            finish_reason="stop",
            latency_ms=1,
        )

    def normalize_usage(self, raw_usage: dict[str, Any]) -> NormalizedUsage:
        return NormalizedUsage(
            input_tokens=int(raw_usage.get("prompt_tokens", 0)),
            output_tokens=int(raw_usage.get("completion_tokens", 0)),
        )


def _dispatch_config(*, fallback: bool = False) -> DispatchConfig:
    fallback_tier = None
    if fallback:
        fallback_tier = TierConfig(
            name="test__fallback",
            provider="backup",
            model="backup-model",
            max_tokens=32,
            temperature=0.0,
            context_budget_tokens=128,
        )
    return DispatchConfig(
        role_tiers={"role": "flash"},
        tiers={
            "flash": TierConfig(
                name="flash",
                provider="primary",
                model="primary-model",
                max_tokens=32,
                temperature=0.0,
                context_budget_tokens=128,
                fallback=fallback_tier,
            )
        },
    )


@pytest.fixture
def clean_provider_registry(monkeypatch):
    reset_provider_registry()
    monkeypatch.setattr("substrate.dispatch.router.emit_typed", lambda *a, **k: "evt")
    yield
    reset_provider_registry()


def test_importing_faultinject_changes_no_write_primitives() -> None:
    original_open = builtins.open
    original_replace = os.replace

    import tools.faultinject as faultinject

    assert faultinject.REGISTRY["readonly_fs"].name == "readonly_fs"
    assert builtins.open is original_open
    assert os.replace is original_replace


def test_unarmed_write_and_replace_succeed(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()

    (target / "a.txt").write_text("ok", encoding="utf-8")
    src = tmp_path / "src.txt"
    src.write_text("new", encoding="utf-8")
    os.replace(src, target / "b.txt")

    assert (target / "a.txt").read_text(encoding="utf-8") == "ok"
    assert (target / "b.txt").read_text(encoding="utf-8") == "new"


def test_readonly_fs_is_path_scoped_and_restores(tmp_path) -> None:
    target = tmp_path / "retriever-cache"
    target.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    original_open = builtins.open

    with arm(readonly_fs(target)):
        (outside / "ok.txt").write_text("ok", encoding="utf-8")
        with pytest.raises(OSError) as exc:
            (target / "blocked.txt").write_text("blocked", encoding="utf-8")
        assert exc.value.errno == errno.EROFS

    assert builtins.open is original_open
    (target / "after.txt").write_text("after", encoding="utf-8")
    assert (target / "after.txt").read_text(encoding="utf-8") == "after"


def test_readonly_fs_fail_on_call_and_exception_safe_teardown(tmp_path) -> None:
    target = tmp_path / "target"
    target.mkdir()
    original_replace = os.replace

    with pytest.raises(ValueError), arm(readonly_fs(target, fail_on_call=2)):
        (target / "first.txt").write_text("first", encoding="utf-8")
        with pytest.raises(OSError) as exc:
            (target / "second.txt").write_text("second", encoding="utf-8")
        assert exc.value.errno == errno.EROFS
        raise ValueError("body raised")

    assert os.replace is original_replace
    src = tmp_path / "src.txt"
    src.write_text("replacement", encoding="utf-8")
    os.replace(src, target / "replaced.txt")
    assert (target / "replaced.txt").read_text(encoding="utf-8") == "replacement"


def test_locked_db_blocks_real_connect_write_then_releases(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "graph.duckdb"
    monkeypatch.setattr(db_lock, "_log_write_event", lambda *args, **kwargs: None)

    with arm(locked_db(db_path)):
        assert db_lock.is_locked(str(db_path)) is True
        with pytest.raises(db_lock.WriteLockTimeout):
            db_lock.connect_write(
                str(db_path),
                timeout_s=0.01,
                poll_interval_s=0.001,
                purpose="faultinject-test",
            )

    assert db_lock.is_locked(str(db_path)) is False
    con = db_lock.connect_write(str(db_path), timeout_s=0.1, purpose="after")
    try:
        con.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER)")
    finally:
        con.close()


def test_provider_fault_503_raises_then_disarms(clean_provider_registry) -> None:
    primary = StubProvider("primary", "ok")
    register_provider(primary)

    with arm(provider_fault(provider="primary", kind="503")):
        with pytest.raises(ProviderError) as exc:
            dispatch("prompt", "role", investigation_id="i", config=_dispatch_config())
        assert "HTTP 503" in str(exc.value)
        assert exc.value.retryable is True

    result = dispatch("prompt", "role", investigation_id="i", config=_dispatch_config())
    assert result.text == "ok"


def test_provider_fault_timeout_raises_then_disarms(clean_provider_registry) -> None:
    register_provider(StubProvider("primary", "ok"))

    with arm(provider_fault(provider="primary", kind="timeout")):
        with pytest.raises(ProviderError) as exc:
            dispatch("prompt", "role", investigation_id="i", config=_dispatch_config())
        assert "timeout" in str(exc.value)
        assert exc.value.retryable is True

    result = dispatch("prompt", "role", investigation_id="i", config=_dispatch_config())
    assert result.text == "ok"


def test_provider_fault_preserves_router_fallback_and_fail_on_call(
    clean_provider_registry,
) -> None:
    register_provider(StubProvider("primary", "primary-ok"))
    register_provider(StubProvider("backup", "backup-ok"))

    with arm(provider_fault(provider="primary", kind="503", fail_on_call=2)):
        first = dispatch(
            "prompt",
            "role",
            investigation_id="i",
            config=_dispatch_config(fallback=True),
        )
        second = dispatch(
            "prompt",
            "role",
            investigation_id="i",
            config=_dispatch_config(fallback=True),
        )

    assert first.text == "primary-ok"
    assert first.fallback_chain_index == 0
    assert second.text == "backup-ok"
    assert second.fallback_chain_index == 1
