from __future__ import annotations

import json

import pytest

from tools.ops import retrieval_gate_probe


def test_probe_passes_with_synthetic_db(tmp_path):
    result = retrieval_gate_probe.run_probe(tmp_path / "probe.duckdb")

    assert result.status == "PASS"
    by_policy = {probe.policy_tag: probe for probe in result.probes}
    assert by_policy["attribution_eligible"].restricted_visible is False
    assert by_policy["private_research"].restricted_visible is True
    assert by_policy["typo_value_should_not_unlock"].restricted_visible is False


def test_probe_text_output_marks_oa020_not_closed(tmp_path):
    result = retrieval_gate_probe.run_probe(tmp_path / "probe.duckdb")

    text = retrieval_gate_probe.format_text(result)

    assert "retrieval-gate-probe: PASS" in text
    assert "oa020_closed_by_this_probe: no" in text
    assert "attribution_eligible: restricted=excluded" in text


def test_probe_json_cli(tmp_path, capsys):
    exit_code = retrieval_gate_probe.main(
        ["--db-path", str(tmp_path / "probe.duckdb"), "--json"]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa020"] is True


def test_probe_refuses_existing_db_path(tmp_path):
    existing = tmp_path / "probe.duckdb"
    existing.touch()

    with pytest.raises(SystemExit) as excinfo:
        retrieval_gate_probe.main(["--db-path", str(existing)])

    assert excinfo.value.code == 2
