"""Readiness audit tests for Autoresearch Wedge 1."""

from __future__ import annotations

import json
from pathlib import Path

from tools.prompt_autoresearch import (
    audit_wedge1_readiness,
    render_readiness_markdown,
)


def test_wedge1_readiness_reports_current_tree_honestly():
    report = audit_wedge1_readiness(Path("."))
    statuses = {item.id: item.status for item in report.items}

    assert report.all_satisfied is False
    assert statuses["program"] == "operator_bound"
    assert statuses["tooling"] == "satisfied"
    assert statuses["calibration"] == "operator_bound"
    assert statuses["golden_traces"] == "operator_bound"
    assert statuses["budget"] == "satisfied"
    assert statuses["local_only"] == "satisfied"


def test_wedge1_readiness_markdown_names_operator_bound_items():
    report = audit_wedge1_readiness(Path("."))

    md = render_readiness_markdown(report)

    assert "# Prompt autoresearch Wedge 1 readiness" in md
    assert "`operator_bound`" in md
    assert "`golden_traces`" in md


def test_wedge1_readiness_cli_json_shape(capsys):
    from tools.prompt_autoresearch.readiness_cli import main

    rc = main(["--repo-root", ".", "--json"])

    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["all_satisfied"] is False
    assert {item["id"] for item in payload["items"]} == {
        "program",
        "tooling",
        "calibration",
        "golden_traces",
        "budget",
        "local_only",
    }
