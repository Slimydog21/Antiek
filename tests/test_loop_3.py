"""Loop 3 substrate scaffold tests (Sprint 30+, master-spec §14.2)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from substrate.loop_3 import (
    Loop3UnlockCriterion,
    Loop3UnlockRequired,
    SFTConfig,
    SFTRunner,
    UnlockChecklist,
    VerifierEnvScaffold,
    build_env_from_trajectory,
    check_unlocked,
    harvest_trajectory_for_prime_rl,
    run_sft_iteration,
)


# ── Unlock gate ──────────────────────────────────────────────────────


def test_loop3_criteria_match_master_spec():
    """The 5 criteria per master-spec §14.2 + loop_3_unlock_criteria.md."""
    assert set(Loop3UnlockCriterion) == {
        Loop3UnlockCriterion.TRAJECTORY_VOLUME,
        Loop3UnlockCriterion.SFT_READINESS,
        Loop3UnlockCriterion.VALIDATED_REWARD,
        Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION,
        Loop3UnlockCriterion.EVAL_HEADROOM,
    }


def test_unlock_checklist_starts_empty():
    cl = UnlockChecklist()
    assert not cl.all_met()
    assert len(cl.remaining()) == 5


def test_unlock_checklist_all_met():
    cl = UnlockChecklist(
        trajectory_volume=True,
        sft_readiness=True,
        validated_reward=True,
        open_weight_justification=True,
        eval_headroom=True,
    )
    assert cl.all_met()
    assert cl.remaining() == []


def test_check_unlocked_refuses_without_env(monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    with pytest.raises(Loop3UnlockRequired):
        check_unlocked()


def test_check_unlocked_passes_with_env(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    check_unlocked()  # no raise


# ── SFT runner ──────────────────────────────────────────────────────


def test_sft_runner_refuses_without_unlock(monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    runner = SFTRunner()
    config = SFTConfig(
        base_model="qwen2.5-7b",
        learning_rate=1e-5,
        batch_size=16,
        lora_rank=8,
        lora_target_modules=("q_proj", "v_proj"),
    )
    with pytest.raises(Loop3UnlockRequired):
        run_sft_iteration(
            runner, config,
            train_fn=lambda c: 0.5,
            cost_fn=lambda c: Decimal("0.10"),
        )


def test_sft_runner_accepts_lower_loss(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    runner = SFTRunner(baseline_val_loss=1.0)
    config = SFTConfig(
        base_model="qwen2.5-7b",
        learning_rate=1e-5,
        batch_size=16,
        lora_rank=8,
        lora_target_modules=("q_proj",),
    )
    outcome = run_sft_iteration(
        runner, config,
        train_fn=lambda c: 0.7,
        cost_fn=lambda c: Decimal("0.15"),
    )
    assert outcome.accepted is True
    assert outcome.delta < 0
    assert runner.baseline_val_loss == 0.7  # advanced


def test_sft_runner_rejects_higher_loss(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    runner = SFTRunner(baseline_val_loss=1.0)
    config = SFTConfig(
        base_model="qwen2.5-7b",
        learning_rate=1e-3,
        batch_size=16,
        lora_rank=8,
        lora_target_modules=("q_proj",),
    )
    outcome = run_sft_iteration(
        runner, config,
        train_fn=lambda c: 1.2,
        cost_fn=lambda c: Decimal("0.15"),
    )
    assert outcome.accepted is False
    assert runner.baseline_val_loss == 1.0  # NOT advanced


# ── Verifiers env scaffold ──────────────────────────────────────────


def test_build_env_filters_telemetry_events():
    """The env scaffold filters out dispatch.call, context_pack.assembled,
    and health.check events so the agent sees role decisions only."""
    trajectory = [
        {"event_id": "e1", "action_type": "dispatch.call", "payload": {}},
        {"event_id": "e2", "action_type": "decomposer.delivered", "payload": {"q": "X"}},
        {"event_id": "e3", "action_type": "context_pack.assembled", "payload": {}},
        {"event_id": "e4", "action_type": "synthesizer.delivered", "payload": {"text": "Y"}},
    ]
    env = build_env_from_trajectory(trajectory)
    obs = env.reset()
    assert "decomposer.delivered" in obs.info["action_type"]


def test_verifiers_env_step_returns_zero_reward_pre_unlock():
    """Pre-unlock: env is observation-only; rewards are 0."""
    trajectory = [
        {"event_id": "e1", "action_type": "decomposer.delivered", "payload": {"q": "X"}},
        {"event_id": "e2", "action_type": "synthesizer.delivered", "payload": {"t": "Y"}},
    ]
    env = build_env_from_trajectory(trajectory)
    env.reset()
    obs, reward, done = env.step("any_action")
    assert reward.value == 0.0
    assert reward.info.get("unlock_gated") is True


# ── Trajectory harvest ──────────────────────────────────────────────


def test_harvest_refuses_without_unlock(monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    with pytest.raises(Loop3UnlockRequired):
        harvest_trajectory_for_prime_rl(
            trajectory_events=[],
            investigation_id="inv-x",
        )


def test_harvest_produces_triples_when_unlocked(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    trajectory = [
        {"event_id": "e1", "action_type": "decomposer.delivered", "role": "decomposer", "payload": {"q": "X"}},
        {"event_id": "e2", "action_type": "synthesizer.delivered", "role": "synthesizer", "payload": {"t": "Y"}},
    ]
    h = harvest_trajectory_for_prime_rl(
        trajectory_events=trajectory,
        investigation_id="inv-x",
    )
    assert len(h.triples) == 2
    assert h.metadata["harvested_triple_count"] == 2


def test_harvest_role_filter(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    trajectory = [
        {"event_id": "e1", "action_type": "decomposer.delivered", "role": "decomposer", "payload": {}},
        {"event_id": "e2", "action_type": "synthesizer.delivered", "role": "synthesizer", "payload": {}},
    ]
    h = harvest_trajectory_for_prime_rl(
        trajectory_events=trajectory,
        investigation_id="inv-x",
        role_filter="synthesizer",
    )
    assert len(h.triples) == 1
    assert h.triples[0]["info"]["role"] == "synthesizer"
