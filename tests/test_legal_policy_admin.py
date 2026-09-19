from __future__ import annotations

import json

from substrate.legal_gate.admin import main


def _install(monkeypatch):
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_ISSUER_ID", "operator-policy-issuer")
    monkeypatch.setenv("ANTIEK_LEGAL_POLICY_RATIFICATION_SHA256", "7" * 64)


def _add_args(path, *extra):
    return [
        "--db",
        str(path),
        "add",
        "--matcher-kind",
        "domain",
        "--matcher-value",
        "restricted.example",
        "--citation-ref",
        "court-order-7",
        "--reason-code",
        "global-restriction",
        "--effective-at",
        "2026-07-15T09:00:00+00:00",
        *extra,
    ]


def test_admin_dry_run_is_non_mutating_then_apply_and_list(tmp_path, monkeypatch, capsys):
    _install(monkeypatch)
    path = tmp_path / "legal.duckdb"
    assert main(_add_args(path, "--dry-run")) == 0
    dry = json.loads(capsys.readouterr().out)
    assert dry["applied"] is False
    assert main(_add_args(path)) == 0
    applied = json.loads(capsys.readouterr().out)
    assert applied == {"applied": True, "event_id": dry["event_id"], "scope": "global"}
    assert main(["--db", str(path), "list", "--json"]) == 0
    listed = json.loads(capsys.readouterr().out)
    assert listed["scope"] == "global"
    assert [row["event_id"] for row in listed["events"]] == [applied["event_id"]]
    assert "account_digest" not in listed["events"][0]
    assert "matcher_value" not in listed["events"][0]


def test_admin_refuses_without_installed_capability(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTIEK_LEGAL_POLICY_ADMIN_ENABLED", raising=False)
    try:
        main(_add_args(tmp_path / "legal.duckdb"))
    except Exception as exc:
        assert "not installed" in str(exc)
    else:
        raise AssertionError("global policy administration must fail closed")
