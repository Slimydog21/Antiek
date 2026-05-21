"""Loop 3 persistent checklist + rubric verifier tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-loop3-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


# ── /loop-3/status defaults ─────────────────────────────────────────


def test_status_starts_all_false(isolated_db, monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    client = _client()
    resp = client.get("/loop-3/status")
    assert resp.status_code == 200
    body = resp.json()
    assert body["all_criteria_met"] is False
    assert body["env_unlocked"] is False
    assert body["fully_unlocked"] is False
    for met in body["criteria"].values():
        assert met is False


# ── POST /loop-3/checklist flips a single criterion ─────────────────


def test_checklist_post_flips_one_criterion(isolated_db, monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    client = _client()
    resp = client.post(
        "/loop-3/checklist",
        json={
            "criterion": "trajectory_volume",
            "met": True,
            "note": "10K trajectories harvested",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["criteria"]["trajectory_volume"] is True
    assert body["criteria"]["sft_readiness"] is False
    assert body["notes"]["trajectory_volume"] == "10K trajectories harvested"
    # all_criteria_met false until ALL five flip.
    assert body["all_criteria_met"] is False
    # env still unset.
    assert body["env_unlocked"] is False


def test_checklist_rejects_unknown_criterion(isolated_db):
    client = _client()
    resp = client.post(
        "/loop-3/checklist",
        json={"criterion": "not_a_real_criterion", "met": True},
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "unknown_criterion"
    assert "trajectory_volume" in body["detail"]["valid"]


def test_all_five_criteria_set_then_env_flips_fully_unlocks(
    isolated_db, monkeypatch,
):
    """all_criteria_met + env_unlocked == fully_unlocked. Both gates
    independently must flip — operator's separation per §14.2."""
    client = _client()
    for criterion in [
        "trajectory_volume",
        "sft_readiness",
        "validated_reward",
        "open_weight_justification",
        "eval_headroom",
    ]:
        resp = client.post(
            "/loop-3/checklist",
            json={"criterion": criterion, "met": True},
        )
        assert resp.status_code == 200

    # No env → criteria met but not fully unlocked.
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)
    resp = client.get("/loop-3/status")
    body = resp.json()
    assert body["all_criteria_met"] is True
    assert body["env_unlocked"] is False
    assert body["fully_unlocked"] is False

    # Flip env → fully unlocked.
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")
    resp = client.get("/loop-3/status")
    body = resp.json()
    assert body["fully_unlocked"] is True


# ── Trust Center reads from persistent checklist ──────────────────


def test_trust_center_surfaces_real_unlock_state(isolated_db):
    client = _client()
    client.post(
        "/loop-3/checklist",
        json={"criterion": "validated_reward", "met": True, "note": "rubric calibrated"},
    )
    resp = client.get("/trust-center")
    body = resp.json()
    # The Trust Center now reads from persistent state.
    assert body["loop_3_unlock_status"]["validated_reward"] is True
    assert body["loop_3_unlock_status"]["trajectory_volume"] is False


# ── Rubric verifier — pre-unlock gate ──────────────────────────────


def test_rubric_verifier_refuses_pre_unlock(monkeypatch):
    """The rubric scorer raises Loop3UnlockRequired without the env
    flip, even on a trivially-correct action."""
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)

    from substrate.loop_3.rubric_verifier import score_against_ground_truth
    from substrate.loop_3.unlock_gate import Loop3UnlockRequired

    with pytest.raises(Loop3UnlockRequired):
        score_against_ground_truth("x", "x")


# ── Rubric verifier — post-unlock scoring ──────────────────────────


def test_rubric_verifier_exact_match_full_reward(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")

    from substrate.loop_3.rubric_verifier import score_against_ground_truth

    score = score_against_ground_truth(
        '{"a": 1, "b": 2}',
        '{"a": 1, "b": 2}',
    )
    assert score.exact_match is True
    assert score.reward == 1.0


def test_rubric_verifier_soft_overlap_fractional_reward(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")

    from substrate.loop_3.rubric_verifier import score_against_ground_truth

    # 2/3 of the ground truth's keys match the agent's dict.
    score = score_against_ground_truth(
        '{"a": 1, "b": 2, "c": 999}',
        '{"a": 1, "b": 2, "c": 3}',
    )
    assert score.exact_match is False
    assert score.soft_overlap == pytest.approx(2 / 3)
    assert score.reward == pytest.approx(2 / 3)


def test_rubric_verifier_handles_malformed_json(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")

    from substrate.loop_3.rubric_verifier import score_against_ground_truth

    score = score_against_ground_truth("not-json", '{"a": 1}')
    assert score.reward == 0.0
    assert "malformed JSON" in score.notes


# ── VerifierEnvScaffold integration ──────────────────────────────


def test_env_step_pre_unlock_returns_zero_reward(monkeypatch):
    monkeypatch.delenv("ANTIEK_LOOP3_UNLOCKED", raising=False)

    from substrate.loop_3.verifiers_env import build_env_from_trajectory

    env = build_env_from_trajectory([
        {"event_id": "e1", "action_type": "x.delivered",
         "role": "r", "payload": {"k": "v"}},
        {"event_id": "e2", "action_type": "y.delivered",
         "role": "r", "payload": {"k": "w"}},
    ])
    env.reset()
    _, reward, _ = env.step("anything")
    assert reward.value == 0.0
    assert reward.info["unlock_gated"] is True


def test_env_step_post_unlock_emits_real_reward(monkeypatch):
    monkeypatch.setenv("ANTIEK_LOOP3_UNLOCKED", "1")

    import json as _json

    from substrate.loop_3.verifiers_env import build_env_from_trajectory

    env = build_env_from_trajectory([
        {"event_id": "e1", "action_type": "x.delivered",
         "role": "r", "payload": {"k": "v"}},
    ])
    env.reset()
    correct_action = _json.dumps({"k": "v"}, sort_keys=True)
    _, reward, _ = env.step(correct_action)
    assert reward.info["unlock_gated"] is False
    assert reward.info["exact_match"] is True
    assert reward.value == 1.0
