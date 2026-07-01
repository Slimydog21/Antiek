import json

from compounding.verification.sft_readiness import (
    audit_sft_readiness,
    format_text,
    main,
)


def test_sft_readiness_fails_with_placeholder_metadata(tmp_path):
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "",
                "base_architecture": "",
                "rl_target_base_architecture": "",
                "model_artifact": "",
                "training_dataset_ref": "",
                "heldout_eval_ref": "",
                "model_sha256": "",
                "train_loss": "",
                "heldout_eval_score": "",
                "produced_at": "",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text("tiers: {}\n", encoding="utf-8")
    training_log = tmp_path / "training_log.md"

    result = audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    )

    assert result.status == "FAIL"
    assert result.policy_id is None
    assert result.registered_tier is None
    assert "loop3_unlocked_by_this_probe: no" in format_text(result)
    assert any(
        check["name"] == "metadata_required_fields" and not check["passed"]
        for check in result.checks
    )


def test_sft_readiness_passes_with_complete_evidence_chain(tmp_path):
    artifact = tmp_path / "model.safetensors"
    artifact.write_text("not a real model; path presence only", encoding="utf-8")
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "local/antiek-sft-001",
                "base_architecture": "qwen3-14b",
                "rl_target_base_architecture": "qwen3-14b",
                "model_artifact": str(artifact),
                "training_dataset_ref": "s3://antiek/trajectory-sft/train.jsonl",
                "heldout_eval_ref": "s3://antiek/trajectory-sft/eval.jsonl",
                "model_sha256": "a" * 64,
                "train_loss": 0.42,
                "heldout_eval_score": 0.73,
                "produced_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text(
        """
tiers:
  antiek_sft:
    provider: local
    model: antiek-sft-001
role_tiers: {}
""",
        encoding="utf-8",
    )
    training_log = tmp_path / "training_log.md"
    training_log.write_text(
        (
            "# Training log\n\n"
            "policy_id: local/antiek-sft-001\n"
            "base: qwen3-14b\n"
            "rl_target_base_architecture: qwen3-14b\n"
            "train_loss: 0.42\n"
            "heldout_eval_score: 0.73\n"
        ),
        encoding="utf-8",
    )

    result = audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    )

    assert result.status == "PASS"
    assert result.policy_id == "local/antiek-sft-001"
    assert result.base_architecture == "qwen3-14b"
    assert result.registered_tier == "antiek_sft"


def test_sft_readiness_accepts_uri_artifact_reference(tmp_path):
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "modal/antiek-sft-uri",
                "base_architecture": "llama-3.1-8b",
                "rl_target_base_architecture": "llama-3.1-8b",
                "model_artifact": "s3://antiek/models/antiek-sft-uri",
                "training_dataset_ref": "s3://antiek/datasets/train.jsonl",
                "heldout_eval_ref": "s3://antiek/datasets/eval.jsonl",
                "model_sha256": "b" * 64,
                "train_loss": "0.51",
                "heldout_eval_score": "0.68",
                "produced_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text(
        "tiers:\n  sft:\n    provider: modal\n    model: antiek-sft-uri\n",
        encoding="utf-8",
    )
    training_log = tmp_path / "training_log.md"
    training_log.write_text(
        "modal/antiek-sft-uri\nllama-3.1-8b\n0.51\n0.68\n",
        encoding="utf-8",
    )

    assert audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    ).status == "PASS"


def test_sft_readiness_fails_when_dispatch_registration_mismatches(tmp_path):
    artifact = tmp_path / "model.safetensors"
    artifact.write_text("x", encoding="utf-8")
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "local/antiek-sft-001",
                "base_architecture": "qwen3-14b",
                "rl_target_base_architecture": "qwen3-14b",
                "model_artifact": str(artifact),
                "training_dataset_ref": "train.jsonl",
                "heldout_eval_ref": "eval.jsonl",
                "model_sha256": "c" * 64,
                "train_loss": 0.42,
                "heldout_eval_score": 0.73,
                "produced_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text(
        "tiers:\n  wrong:\n    provider: local\n    model: other-model\n",
        encoding="utf-8",
    )
    training_log = tmp_path / "training_log.md"
    training_log.write_text("local/antiek-sft-001\nqwen3-14b\n0.42\n0.73\n", encoding="utf-8")

    result = audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    )

    assert result.status == "FAIL"
    assert any(
        check["name"] == "sft_policy_registered_in_dispatch" and not check["passed"]
        for check in result.checks
    )


def test_sft_readiness_fails_when_training_log_omits_metrics(tmp_path):
    artifact = tmp_path / "model.safetensors"
    artifact.write_text("x", encoding="utf-8")
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "local/antiek-sft-001",
                "base_architecture": "qwen3-14b",
                "rl_target_base_architecture": "qwen3-14b",
                "model_artifact": str(artifact),
                "training_dataset_ref": "train.jsonl",
                "heldout_eval_ref": "eval.jsonl",
                "model_sha256": "d" * 64,
                "train_loss": 0.42,
                "heldout_eval_score": 0.73,
                "produced_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text(
        "tiers:\n  sft:\n    provider: local\n    model: antiek-sft-001\n",
        encoding="utf-8",
    )
    training_log = tmp_path / "training_log.md"
    training_log.write_text("local/antiek-sft-001\nqwen3-14b\n", encoding="utf-8")

    result = audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    )

    assert result.status == "FAIL"
    assert any(
        check["name"] == "training_log_references_model" and not check["passed"]
        for check in result.checks
    )


def test_sft_readiness_fails_when_base_does_not_match_rl_target(tmp_path):
    metadata = tmp_path / "sft-model.json"
    metadata.write_text(
        json.dumps(
            {
                "policy_id": "modal/antiek-sft-uri",
                "base_architecture": "llama-3.1-8b",
                "rl_target_base_architecture": "qwen3-14b",
                "model_artifact": "s3://antiek/models/antiek-sft-uri",
                "training_dataset_ref": "train.jsonl",
                "heldout_eval_ref": "eval.jsonl",
                "model_sha256": "e" * 64,
                "train_loss": 0.51,
                "heldout_eval_score": 0.68,
                "produced_at": "2026-07-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    dispatch_config = tmp_path / "config.yaml"
    dispatch_config.write_text(
        "tiers:\n  sft:\n    provider: modal\n    model: antiek-sft-uri\n",
        encoding="utf-8",
    )
    training_log = tmp_path / "training_log.md"
    training_log.write_text("modal/antiek-sft-uri\nllama-3.1-8b\nqwen3-14b\n0.51\n0.68\n", encoding="utf-8")

    result = audit_sft_readiness(
        metadata_path=metadata,
        dispatch_config_path=dispatch_config,
        training_log_path=training_log,
    )

    assert result.status == "FAIL"
    assert any(
        check["name"] == "base_architecture_matches_rl_target" and not check["passed"]
        for check in result.checks
    )


def test_cli_returns_nonzero_for_missing_sft_evidence(tmp_path, capsys):
    exit_code = main([
        "--metadata",
        str(tmp_path / "missing.json"),
        "--dispatch-config",
        str(tmp_path / "missing.yaml"),
        "--training-log",
        str(tmp_path / "missing.md"),
    ])

    assert exit_code == 1
    assert "loop3-sft-readiness: FAIL" in capsys.readouterr().out
