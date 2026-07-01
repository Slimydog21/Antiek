from __future__ import annotations

import json

import pytest

from tools.ops import federation_exchange_probe


def test_federation_exchange_probe_passes_with_two_fresh_dbs(tmp_path):
    sender_path = tmp_path / "sender.duckdb"
    receiver_path = tmp_path / "receiver.duckdb"

    result = federation_exchange_probe.run_probe(sender_path, receiver_path)

    assert result.status == "PASS"
    assert result.does_not_close_oa018 is True
    assert result.sender_reference_id is not None
    assert result.receiver_reference_id is not None
    assert result.revenue_routing_handle == "revshare:oa018:synthetic"
    assert {check.name for check in result.checks} == {
        "sender_config_persisted",
        "sender_partner_trusted",
        "outbound_signed_token",
        "receiver_config_persisted",
        "receiver_partner_trusted",
        "inbound_accepted",
        "nonce_persisted",
        "replay_rejected",
    }
    assert all(check.passed for check in result.checks)


def test_federation_exchange_probe_uses_sibling_receiver_db_by_default(tmp_path):
    sender_path = tmp_path / "sender.duckdb"

    result = federation_exchange_probe.run_probe(sender_path)

    assert result.status == "PASS"
    assert result.receiver_db_path.endswith("sender.receiver.duckdb")


def test_federation_exchange_probe_text_marks_oa018_not_closed(tmp_path):
    result = federation_exchange_probe.run_probe(
        tmp_path / "sender.duckdb",
        tmp_path / "receiver.duckdb",
    )

    text = federation_exchange_probe.format_text(result)

    assert "federation-exchange-probe: PASS" in text
    assert "PASS replay_rejected" in text
    assert "oa018_closed_by_this_probe: no" in text


def test_federation_exchange_probe_json_cli(tmp_path, capsys):
    exit_code = federation_exchange_probe.main([
        "--db-path",
        str(tmp_path / "sender.duckdb"),
        "--receiver-db-path",
        str(tmp_path / "receiver.duckdb"),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa018"] is True
    assert "v1." not in json.dumps(payload)
    assert "shared_secret" not in json.dumps(payload)


def test_federation_exchange_probe_refuses_existing_db_path(tmp_path, capsys):
    existing = tmp_path / "sender.duckdb"
    existing.write_text("already here")

    with pytest.raises(SystemExit) as exc:
        federation_exchange_probe.main([
            "--db-path",
            str(existing),
            "--receiver-db-path",
            str(tmp_path / "receiver.duckdb"),
        ])

    assert exc.value.code == 2
    assert "must not already exist" in capsys.readouterr().err
