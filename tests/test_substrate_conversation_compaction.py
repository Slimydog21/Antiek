"""Tests for substrate/conversation/compaction — policy, trigger, lossy algorithm."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from substrate.conversation.compaction import (
    ContextPressureNeedsOperator,
    ContextPressureTooHigh,
    compact,
    should_compact,
)
from substrate.conversation.event import Event
from substrate.conversation.event_log import EventLog
from substrate.conversation.policy import CompactionConfig, CompactionPolicy
from substrate.conversation.token_counter import (
    SEAM_ID,
    count_tokens,
    declare_token_count_seam,
)
from substrate.hooks import HookContext, HookRegistry, HookShortCircuit
from substrate.observability.burn import BurnRecorder


@pytest.fixture(autouse=True)
def _reset_burn():
    BurnRecorder._reset_instances()
    yield
    BurnRecorder._reset_instances()


@pytest.fixture
def registry() -> HookRegistry:
    r = HookRegistry()
    declare_token_count_seam(r)
    return r


def _seed_log(project_root: Path, session_id: str, n: int) -> EventLog:
    log = EventLog(session_id, project_root, fsync_on_append=False)
    for i in range(1, n + 1):
        kind = "user_message" if i % 2 == 1 else "assistant_message"
        log.append(
            Event(
                position=i,
                ts=f"2026-05-24T00:00:0{i % 10}+00:00",
                kind=kind,  # type: ignore[arg-type]
                payload={"text": f"msg-{i} " * 30},
            )
        )
    return log


def _dummy_summarizer(messages: list[dict[str, Any]], model: str) -> str:
    return f"[summary of {len(messages)} messages]"


def test_compaction_config_default_is_strict() -> None:
    c = CompactionConfig()
    assert c.policy is CompactionPolicy.STRICT
    assert c.threshold_pct == 0.85
    assert c.keep_first_n == 4
    assert c.keep_last_n == 8


def test_compaction_config_invalid_threshold_raises() -> None:
    with pytest.raises(ValueError):
        CompactionConfig(threshold_pct=1.5)
    with pytest.raises(ValueError):
        CompactionConfig(threshold_pct=0)


def test_compaction_config_loads_from_toml(tmp_path: Path) -> None:
    cfg = tmp_path / ".antiek" / "config.toml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        '[compaction]\n'
        'policy = "lossy"\n'
        "threshold_pct = 0.7\n"
        "keep_first_n = 2\n"
        "keep_last_n = 4\n"
    )
    c = CompactionConfig.for_project(tmp_path)
    assert c.policy is CompactionPolicy.LOSSY
    assert c.threshold_pct == 0.7


def test_compaction_config_missing_toml_uses_defaults(tmp_path: Path) -> None:
    c = CompactionConfig.for_project(tmp_path)
    assert c.policy is CompactionPolicy.STRICT


def test_token_counter_uses_heuristic_when_no_hook(registry: HookRegistry) -> None:
    n = count_tokens(registry, text="x" * 40, model="any-model")
    assert n == 10


def test_token_counter_extension_overrides_via_short_circuit(registry: HookRegistry) -> None:
    class _Counter:
        def __call__(self, ctx: HookContext, **kw: Any) -> None:
            raise HookShortCircuit(result=999)

    registry.register_hook(SEAM_ID, _Counter(), "pre", "test-counter")
    n = count_tokens(registry, text="anything", model="any")
    assert n == 999


def test_should_compact_returns_false_below_threshold(registry, tmp_path: Path) -> None:
    log = _seed_log(tmp_path, "s", n=3)
    trigger, current, threshold = should_compact(
        registry=registry, log=log, config=CompactionConfig(threshold_pct=0.85),
        model="m", context_window=200_000,
    )
    assert trigger is False


def test_should_compact_returns_true_above_threshold(registry, tmp_path: Path) -> None:
    log = _seed_log(tmp_path, "s", n=20)
    trigger, current, threshold = should_compact(
        registry=registry, log=log, config=CompactionConfig(threshold_pct=0.5),
        model="m", context_window=100,
    )
    assert trigger is True


def test_compact_strict_raises_with_structured_info(registry, tmp_path: Path) -> None:
    _seed_log(tmp_path, "s", n=5)
    with pytest.raises(ContextPressureTooHigh) as ei:
        compact(
            session_id="s", project_root=tmp_path, registry=registry,
            config=CompactionConfig(policy=CompactionPolicy.STRICT, threshold_pct=0.01),
            model="claude-opus-4-7", context_window=100, summarizer=_dummy_summarizer,
        )
    err = ei.value
    assert err.session_id == "s"
    assert "antiek compact" in str(err)
    assert "antiek branch from" in str(err)


def test_compact_interactive_raises_needs_operator(registry, tmp_path: Path) -> None:
    _seed_log(tmp_path, "s", n=5)
    with pytest.raises(ContextPressureNeedsOperator):
        compact(
            session_id="s", project_root=tmp_path, registry=registry,
            config=CompactionConfig(policy=CompactionPolicy.INTERACTIVE, threshold_pct=0.01),
            model="m", context_window=10, summarizer=_dummy_summarizer,
        )


def test_compact_lossy_creates_branch_before_mutating(registry, tmp_path: Path) -> None:
    log = _seed_log(tmp_path, "s", n=20)
    pre_position = log.position()
    result = compact(
        session_id="s", project_root=tmp_path, registry=registry,
        config=CompactionConfig(policy=CompactionPolicy.LOSSY, keep_first_n=4, keep_last_n=8),
        model="m", context_window=100, summarizer=_dummy_summarizer,
    )
    assert result.pre_compaction_branch is not None
    branch_log = EventLog(result.pre_compaction_branch, tmp_path, fsync_on_append=False)
    assert branch_log.position() == pre_position
    assert log.position() == pre_position + 1
    last_event = list(log.iter_events())[-1]
    assert last_event.kind == "system_marker"
    assert last_event.payload["compaction"]["n_summarized"] == 20 - 4 - 8


def test_compact_lossy_boundary_exact(registry, tmp_path: Path) -> None:
    _seed_log(tmp_path, "s", n=20)
    r = compact(
        session_id="s", project_root=tmp_path, registry=registry,
        config=CompactionConfig(policy=CompactionPolicy.LOSSY, keep_first_n=4, keep_last_n=8),
        model="m", context_window=100, summarizer=_dummy_summarizer,
    )
    assert r.n_summarized == 8


def test_compact_lossy_skips_when_nothing_to_summarize(registry, tmp_path: Path) -> None:
    _seed_log(tmp_path, "s", n=6)
    r = compact(
        session_id="s", project_root=tmp_path, registry=registry,
        config=CompactionConfig(policy=CompactionPolicy.LOSSY, keep_first_n=4, keep_last_n=8),
        model="m", context_window=100, summarizer=_dummy_summarizer,
    )
    assert r.pre_compaction_branch is None
    assert r.n_summarized == 0


def test_compact_lossy_branch_is_independent(registry, tmp_path: Path) -> None:
    _seed_log(tmp_path, "s", n=15)
    r = compact(
        session_id="s", project_root=tmp_path, registry=registry,
        config=CompactionConfig(policy=CompactionPolicy.LOSSY, keep_first_n=2, keep_last_n=2),
        model="m", context_window=100, summarizer=_dummy_summarizer,
    )
    branch_log = EventLog(r.pre_compaction_branch, tmp_path, fsync_on_append=False)
    branch_events = list(branch_log.iter_events())
    assert len(branch_events) == 15


def test_compact_lossy_marker_contains_position_and_n(registry, tmp_path: Path) -> None:
    log = _seed_log(tmp_path, "s", n=20)
    compact(
        session_id="s", project_root=tmp_path, registry=registry,
        config=CompactionConfig(policy=CompactionPolicy.LOSSY, keep_first_n=4, keep_last_n=8),
        model="m", context_window=100, summarizer=_dummy_summarizer,
    )
    summary = list(log.iter_events())[-1].payload["compaction"]["summary"]
    assert "[compacted by antiek at position 20" in summary
    assert "8 messages removed" in summary
