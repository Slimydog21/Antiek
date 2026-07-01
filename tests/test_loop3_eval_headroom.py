import json

from compounding.verification.eval_headroom import (
    audit_eval_headroom,
    format_text,
    main,
)


def _write_eval_jsonl(path, count):
    with path.open("w", encoding="utf-8") as handle:
        for index in range(count):
            handle.write(
                json.dumps(
                    {
                        "chunk_text": f"example {index}",
                        "expected_parameters": [
                            {"name": "x", "value": index, "units": "count"}
                        ],
                    }
                )
                + "\n"
            )


def _write_sources(tmp_path):
    current = tmp_path / "current-score.json"
    ceiling = tmp_path / "ceiling-score.json"
    noise = tmp_path / "noise-floor.json"
    gepa = tmp_path / "gepa-report.md"
    current.write_text(json.dumps({"score": 0.61}), encoding="utf-8")
    ceiling.write_text(json.dumps({"score": 0.84}), encoding="utf-8")
    noise.write_text(json.dumps({"noise": 0.03}), encoding="utf-8")
    gepa.write_text("GEPA optimization reached a plateau after generation 7.", encoding="utf-8")
    return current, ceiling, noise, gepa


def test_eval_headroom_fails_with_existing_50_example_fixture(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v0.jsonl"
    _write_eval_jsonl(eval_set, 50)
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence)

    assert result.status == "FAIL"
    assert result.eval_example_count == 50
    assert "loop3_unlocked_by_this_probe: no" in format_text(result)


def test_eval_headroom_passes_with_sufficient_margin_and_gepa_plateau(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    _write_eval_jsonl(eval_set, 200)
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence)

    assert result.status == "PASS"
    assert result.eval_example_count == 200
    assert result.headroom_margin == 0.22999999999999998


def test_eval_headroom_fails_when_margin_does_not_exceed_noise(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    _write_eval_jsonl(eval_set, 200)
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.80,
                "current_score_ref": str(current),
                "ceiling_kind": "human_agreement",
                "ceiling_score": 0.82,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence)

    assert result.status == "FAIL"
    assert any(
        check["name"] == "headroom_exceeds_noise" and not check["passed"]
        for check in result.checks
    )


def test_eval_headroom_fails_without_gepa_plateau(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    _write_eval_jsonl(eval_set, 200)
    current, ceiling, noise, _gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": False,
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence)

    assert result.status == "FAIL"
    assert result.gepa_plateaued is False


def test_eval_headroom_accepts_gepa_plateau_report(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    _write_eval_jsonl(eval_set, 200)
    current, ceiling, noise, _gepa = _write_sources(tmp_path)
    report = tmp_path / "gepa-report.md"
    report.write_text("GEPA run reached a plateau after generation 7.", encoding="utf-8")
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(report),
            }
        ),
        encoding="utf-8",
    )

    assert audit_eval_headroom(evidence_path=evidence).status == "PASS"


def test_eval_headroom_rejects_lowered_threshold_even_if_counts_pass(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v0.jsonl"
    _write_eval_jsonl(eval_set, 50)
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence, min_eval_examples=50)

    assert result.status == "FAIL"
    assert any(
        check["name"] == "default_threshold_evidence_mode" and not check["passed"]
        for check in result.checks
    )


def test_eval_headroom_rejects_padded_empty_eval_rows(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    eval_set.write_text(("{}\n" * 200), encoding="utf-8")
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": 0.03,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    result = audit_eval_headroom(evidence_path=evidence)

    assert result.status == "FAIL"
    assert result.eval_example_count == 0


def test_eval_headroom_rejects_negative_noise_floor(tmp_path):
    eval_set = tmp_path / "parameter_extractor_v1.jsonl"
    _write_eval_jsonl(eval_set, 200)
    current, ceiling, noise, gepa = _write_sources(tmp_path)
    evidence = tmp_path / "eval-headroom.json"
    evidence.write_text(
        json.dumps(
            {
                "eval_set_path": str(eval_set),
                "current_policy_id": "local/antiek-sft",
                "current_score": 0.61,
                "current_score_ref": str(current),
                "ceiling_kind": "closed_weight",
                "ceiling_score": 0.84,
                "ceiling_ref": str(ceiling),
                "reward_noise_floor": -0.01,
                "reward_noise_floor_ref": str(noise),
                "gepa_plateaued": True,
                "gepa_report_ref": str(gepa),
            }
        ),
        encoding="utf-8",
    )

    assert audit_eval_headroom(evidence_path=evidence).status == "FAIL"


def test_cli_returns_nonzero_until_eval_headroom_evidence_exists(tmp_path, capsys):
    exit_code = main(["--evidence", str(tmp_path / "missing.json")])

    assert exit_code == 1
    assert "loop3-eval-headroom: FAIL" in capsys.readouterr().out
