from __future__ import annotations

import json

import pytest

from tools.ops import kms_key_probe


class _FakeKmsClient:
    def __init__(self) -> None:
        self.plaintexts: dict[bytes, bytes] = {}

    def generate_data_key(self, *, KeyId, KeySpec):  # noqa: N803
        assert KeySpec == "AES_256"
        wrapped = b"wrapped-" + KeyId.encode("utf-8")
        self.plaintexts[wrapped] = b"plaintext-" + KeyId.encode("utf-8")
        return {"CiphertextBlob": wrapped}

    def decrypt(self, *, CiphertextBlob, KeyId):  # noqa: N803
        assert CiphertextBlob.startswith(b"wrapped-" + KeyId.encode("utf-8"))
        return {"Plaintext": self.plaintexts[CiphertextBlob]}


def test_kms_key_probe_passes_round_trip_without_secret_material():
    result = kms_key_probe.probe_kms_key(
        client=_FakeKmsClient(),
        region="us-east-1",
    )

    assert result.status == "PASS"
    assert result.expected_key_id == "alias/antiek-graph-test-graph"
    assert result.generated_key_id == "alias/antiek-graph-test-graph"
    assert result.wrapped_data_key_len is not None
    assert result.plaintext_len is not None
    assert result.does_not_close_oa011 is True
    payload = json.dumps(result, default=lambda obj: obj.__dict__)
    assert "wrapped-alias" not in payload
    assert "plaintext-alias" not in payload


def test_kms_key_probe_fails_generate_failure():
    class BadClient:
        def generate_data_key(self, **kwargs):
            raise RuntimeError("missing alias")

    result = kms_key_probe.probe_kms_key(client=BadClient())

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["generate_data_key"].passed is False
    assert "missing alias" in checks["generate_data_key"].detail


def test_kms_key_probe_fails_decrypt_failure():
    class BadDecryptClient(_FakeKmsClient):
        def decrypt(self, **kwargs):
            raise RuntimeError("decrypt denied")

    result = kms_key_probe.probe_kms_key(client=BadDecryptClient())

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert checks["decrypt_data_key"].passed is False
    assert "decrypt denied" in checks["decrypt_data_key"].detail


def test_kms_key_probe_text_output_marks_non_closure():
    result = kms_key_probe.probe_kms_key(client=_FakeKmsClient())

    text = kms_key_probe.format_text(result)

    assert "kms-key-probe: PASS" in text
    assert "oa011_closed_by_this_probe: no" in text
    assert "plaintext-alias" not in text
    assert "wrapped-alias" not in text


def test_kms_key_probe_json_cli(monkeypatch, capsys):
    monkeypatch.setattr(
        kms_key_probe,
        "_aws_boto3_client",
        lambda region: _FakeKmsClient(),
    )

    exit_code = kms_key_probe.main([
        "--region",
        "us-east-1",
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["region"] == "us-east-1"
    assert payload["does_not_close_oa011"] is True
    assert "plaintext-alias" not in json.dumps(payload)
    assert "wrapped-alias" not in json.dumps(payload)


def test_aws_client_loader_reports_missing_boto3(monkeypatch):
    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "boto3":
            raise ImportError("no boto3")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="antiek\\[kms\\]"):
        kms_key_probe._aws_boto3_client("us-east-1")


def test_kms_key_probe_json_cli_reports_client_loader_failure(monkeypatch, capsys):
    def fail_loader(region):
        raise RuntimeError("boto3 missing")

    monkeypatch.setattr(kms_key_probe, "_aws_boto3_client", fail_loader)

    exit_code = kms_key_probe.main(["--region", "us-east-1", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "FAIL"
    assert payload["checks"][0]["name"] == "client_configured"
    assert "boto3 missing" in payload["checks"][0]["detail"]
