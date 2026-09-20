from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from infrastructure.connectors.herdr_bridge.antiek_client import (
    AntiekClient,
    AntiekHttpError,
    HttpResponse,
)
from infrastructure.connectors.herdr_bridge.cli import submit_result
from infrastructure.connectors.herdr_bridge.config import load_config
from infrastructure.connectors.herdr_bridge.daemon import BridgeDaemon
from infrastructure.connectors.herdr_bridge.herdr_adapter import (
    AgentAmbiguous,
    AgentUnavailable,
    HerdrAdapter,
)
from infrastructure.connectors.herdr_bridge.journal import BridgeJournal
from infrastructure.connectors.herdr_bridge.models import LeaseEnvelope, StructuredResult
from interfaces.research.api.app import create_app
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor
from substrate.feedback.service import create_feedback_thread
from substrate.feedback.store import CreateThreadCommand
from substrate.graph import ensure_initialized


def _write_private(path: Path, text: str) -> None:
    path.write_text(text)
    path.chmod(0o600)


def _config(tmp_path: Path) -> Path:
    secret_path = tmp_path / "bridge.secret"
    _write_private(secret_path, "test-secret\n")
    config_path = tmp_path / "bridge.json"
    _write_private(
        config_path,
        json.dumps(
            {
                "schema_version": 1,
                "antiek_base_url": "https://antiek.example.test",
                "credential_id": "mini-bridge-1",
                "credential_secret_file": str(secret_path),
                "bridge_instance_id": "faisals-mac-mini",
                "journal_path": str(tmp_path / "journal.sqlite3"),
                "result_cli": "/opt/antiek/bin/herdr-bridge",
                "workers": {
                    "research-owner": {
                        "agent": "prime-agent",
                        "cwd": "/Users/slimydog",
                    }
                },
            }
        ),
    )
    return config_path


def _lease() -> LeaseEnvelope:
    return LeaseEnvelope.parse(
        {
            "work_id": "wrk-1",
            "thread_id": "fth-1",
            "lease_id": "lse-1",
            "attempt_no": 1,
            "logical_worker_id": "research-owner",
            "lease_expires_at": "2026-08-21T12:02:00+00:00",
            "artifact": {
                "artifact_id": "artifact-1",
                "version": 2,
                "content_sha256": "a" * 64,
                "source_sha256": "b" * 64,
            },
            "anchor": {
                "normalization": "unicode-nfc-v1",
                "node_id": "insight-1",
                "node_text_sha256": "c" * 64,
                "start_scalar": 0,
                "end_scalar": 4,
                "quote": "fact",
                "prefix": "",
                "suffix": " remains",
            },
            "comment_markdown": "Verify this fact.",
            "context_sha256": "e" * 64,
        }
    )


def test_config_requires_private_files_and_https(tmp_path) -> None:
    config_path = _config(tmp_path)
    config = load_config(config_path)
    assert config.credential_secret == "test-secret"
    assert "test-secret" not in repr(config)
    assert config.workers["research-owner"].agent == "prime-agent"

    config_path.chmod(0o644)
    with pytest.raises(PermissionError, match="0600"):
        load_config(config_path)

    config_path.chmod(0o600)
    body = json.loads(config_path.read_text())
    body["antiek_base_url"] = "http://antiek.example.test"
    config_path.write_text(json.dumps(body))
    with pytest.raises(ValueError, match="HTTPS"):
        load_config(config_path)


def test_herdr_selector_refuses_ambiguity_and_prompt_uses_argv(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    calls: list[list[str]] = []

    def runner(argv: list[str]) -> str:
        calls.append(argv)
        if argv[-2:] == ["agent", "list"]:
            return json.dumps(
                {
                    "result": {
                        "agents": [
                            {
                                "agent": "prime-agent",
                                "agent_status": "idle",
                                "cwd": "/Users/slimydog",
                                "pane_id": "w11:p5",
                            },
                            {
                                "agent": "prime-agent",
                                "agent_status": "idle",
                                "cwd": "/Users/slimydog",
                                "pane_id": "w11:pA",
                            },
                        ]
                    }
                }
            )
        raise AssertionError(f"unexpected command: {argv}")

    adapter = HerdrAdapter(config=config, run=runner)
    with pytest.raises(AgentAmbiguous):
        adapter.resolve_target("research-owner")
    assert calls == [["herdr", "agent", "list"]]


def test_private_journal_survives_restart_and_accepts_one_correlated_result(
    tmp_path,
) -> None:
    journal_path = tmp_path / "journal.sqlite3"
    lease = _lease()
    first = BridgeJournal(journal_path)
    first.record_lease(lease)
    first.record_prompt_receipt(
        lease,
        target="w11:p5",
        receipt_sha256="f" * 64,
    )
    first.close()

    restarted = BridgeJournal(journal_path)
    pending = restarted.pending_attempts()
    assert len(pending) == 1
    assert pending[0].prompt_receipt_sha256 == "f" * 64
    assert pending[0].result is None
    result = StructuredResult.parse(
        {
            "work_id": lease.work_id,
            "lease_id": lease.lease_id,
            "attempt_no": lease.attempt_no,
            "context_sha256": lease.context_sha256,
            "kind": "reply",
            "reply_markdown": "The primary source confirms this.",
        }
    )
    restarted.capture_result(result)
    assert restarted.pending_results()[0].result == result
    with pytest.raises(ValueError, match="different result"):
        restarted.capture_result(
            StructuredResult.parse(
                {
                    **result.to_dict(),
                    "reply_markdown": "A conflicting response.",
                }
            )
        )
    assert os.stat(journal_path).st_mode & 0o777 == 0o600
    restarted.close()


def test_daemon_records_receipt_and_restart_never_reprompts(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()

    class FakeAntiek:
        def __init__(self) -> None:
            self.calls: list[str] = []
            self.leased = False

        def lease(self):
            self.calls.append("lease")
            if self.leased:
                return None
            self.leased = True
            return lease

        def submitted(self, _lease, *, target: str) -> None:
            assert target == "w11:p5"
            self.calls.append("submitted")

        def acknowledged(self, _lease, *, receipt_sha256: str) -> None:
            assert receipt_sha256 == "f" * 64
            self.calls.append("acknowledged")

        def working(self, _lease) -> None:
            self.calls.append("working")

        def renew(self, _lease) -> None:
            self.calls.append("renew")

        def result(self, _result) -> None:
            self.calls.append("result")

    class FakeHerdr:
        def __init__(self) -> None:
            self.prompts = 0

        def prompt(self, prompted, *, result_path: Path):
            from infrastructure.connectors.herdr_bridge.herdr_adapter import PromptReceipt

            assert prompted == lease
            assert result_path.name == "lse-1.json"
            self.prompts += 1
            return PromptReceipt("w11:p5", "f" * 64, "working")

    antiek = FakeAntiek()
    herdr = FakeHerdr()
    with BridgeJournal(config.journal_path) as journal:
        BridgeDaemon(config, antiek=antiek, herdr=herdr, journal=journal).process_once()
    assert antiek.calls == ["lease", "submitted", "acknowledged", "working"]
    assert herdr.prompts == 1

    restarted_herdr = FakeHerdr()
    with BridgeJournal(config.journal_path) as journal:
        BridgeDaemon(
            config,
            antiek=antiek,
            herdr=restarted_herdr,
            journal=journal,
        ).process_once()
    assert restarted_herdr.prompts == 0
    assert antiek.calls[-1] == "renew"


def test_daemon_flushes_captured_result_before_polling(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()
    result = StructuredResult.parse(
        {
            "work_id": lease.work_id,
            "lease_id": lease.lease_id,
            "attempt_no": lease.attempt_no,
            "context_sha256": lease.context_sha256,
            "kind": "reply",
            "reply_markdown": "Verified.",
        }
    )
    with BridgeJournal(config.journal_path) as journal:
        journal.record_lease(lease)
        journal.capture_result(result)

    calls: list[str] = []

    class FakeAntiek:
        def result(self, submitted: StructuredResult) -> None:
            assert submitted == result
            calls.append("result")

        def lease(self):
            calls.append("lease")
            return

    class NoPromptHerdr:
        def prompt(self, *_args, **_kwargs):
            raise AssertionError("captured result must not prompt Herdr")

    with BridgeJournal(config.journal_path) as journal:
        BridgeDaemon(
            config,
            antiek=FakeAntiek(),
            herdr=NoPromptHerdr(),
            journal=journal,
        ).process_once()
        assert journal.pending_results() == []
    assert calls == ["result", "lease"]


def test_antiek_client_uses_scoped_auth_stable_result_key_and_exact_json(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    calls: list[tuple[str, str, dict[str, str], object]] = []
    lease = _lease()

    def transport(method: str, url: str, headers: dict[str, str], body: object):
        calls.append((method, url, headers, body))
        if url.endswith("/lease"):
            return HttpResponse(200, lease.to_dict())
        return HttpResponse(200, {"state": "replied"})

    client = AntiekClient(config, transport=transport)
    loaded = client.lease()
    assert loaded == lease
    result = StructuredResult.parse(
        {
            "work_id": lease.work_id,
            "lease_id": lease.lease_id,
            "attempt_no": lease.attempt_no,
            "context_sha256": lease.context_sha256,
            "kind": "reply",
            "reply_markdown": "Verified.",
        }
    )
    client.result(result)
    client.result(result)

    assert calls[0][2]["Authorization"] == "AntiekBridge mini-bridge-1.test-secret"
    assert calls[0][2]["User-Agent"] == "AntiekHerdrBridge/0.1"
    assert calls[0][3] == {
        "bridge_instance_id": "faisals-mac-mini",
        "lease_seconds": 120,
    }
    first_result = calls[1]
    second_result = calls[2]
    assert first_result[1].endswith("/wrk-1/leases/lse-1/result")
    assert first_result[2]["Idempotency-Key"] == second_result[2]["Idempotency-Key"]
    assert first_result[3] == {
        "attempt_no": lease.attempt_no,
        "context_sha256": lease.context_sha256,
        "kind": "reply",
        "reply_markdown": "Verified.",
    }


def test_local_result_cli_accepts_only_private_correlated_result_file(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()
    with BridgeJournal(config.journal_path) as journal:
        journal.record_lease(lease)
    results_dir = config.journal_path.parent / "results"
    results_dir.mkdir(mode=0o700)
    result_path = results_dir / "lse-1.json"
    _write_private(
        result_path,
        json.dumps(
            {
                "work_id": lease.work_id,
                "lease_id": lease.lease_id,
                "attempt_no": lease.attempt_no,
                "context_sha256": lease.context_sha256,
                "kind": "reply",
                "reply_markdown": "Verified.",
            }
        ),
    )

    accepted = submit_result(config, result_path)
    assert accepted.kind == "reply"
    with BridgeJournal(config.journal_path) as journal:
        assert journal.pending_results()[0].result == accepted

    result_path.chmod(0o644)
    with pytest.raises(PermissionError, match="0600"):
        submit_result(config, result_path)


def test_transient_result_failure_stays_pending_and_retries_before_lease(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()
    result = StructuredResult.parse(
        {
            "work_id": lease.work_id,
            "lease_id": lease.lease_id,
            "attempt_no": 1,
            "context_sha256": lease.context_sha256,
            "kind": "reply",
            "reply_markdown": "Verified.",
        }
    )
    with BridgeJournal(config.journal_path) as journal:
        journal.record_lease(lease)
        journal.capture_result(result)

    calls: list[str] = []

    class FlakyAntiek:
        failed = False

        def result(self, _result) -> None:
            calls.append("result")
            if not self.failed:
                self.failed = True
                raise AntiekHttpError(503, "temporary")

        def lease(self):
            calls.append("lease")
            return

    antiek = FlakyAntiek()
    with BridgeJournal(config.journal_path) as journal:
        daemon = BridgeDaemon(config, antiek=antiek, herdr=object(), journal=journal)
        with pytest.raises(AntiekHttpError):
            daemon.process_once()
        assert len(journal.pending_results()) == 1
        daemon.process_once()
        assert journal.pending_results() == []
    assert calls == ["result", "result", "lease"]


def test_gone_result_closes_local_attempt_without_retry(tmp_path) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()
    result = StructuredResult.parse(
        {
            "work_id": lease.work_id,
            "lease_id": lease.lease_id,
            "attempt_no": lease.attempt_no,
            "context_sha256": lease.context_sha256,
            "kind": "reply",
            "reply_markdown": "Verified.",
        }
    )
    with BridgeJournal(config.journal_path) as journal:
        journal.record_lease(lease)
        journal.capture_result(result)

    class GoneAntiek:
        def result(self, _result) -> None:
            raise AntiekHttpError(410, "expired")

        def lease(self):
            return None

    with BridgeJournal(config.journal_path) as journal:
        daemon = BridgeDaemon(config, antiek=GoneAntiek(), herdr=object(), journal=journal)
        daemon.process_once()
        assert journal.pending_attempts() == []
        daemon.process_once()


@pytest.mark.parametrize(
    ("error", "error_code", "retryable"),
    [
        (AgentUnavailable("offline"), "herdr_unavailable", True),
        (AgentAmbiguous("ambiguous"), "herdr_target_ambiguous", False),
    ],
)
def test_herdr_delivery_failure_returns_structured_result(
    tmp_path, error, error_code: str, retryable: bool
) -> None:
    config = load_config(_config(tmp_path))
    lease = _lease()
    captured: list[StructuredResult] = []

    class FakeAntiek:
        def lease(self):
            return lease

        def result(self, result: StructuredResult) -> None:
            captured.append(result)

    class BrokenHerdr:
        def prompt(self, *_args, **_kwargs):
            raise error

    with BridgeJournal(config.journal_path) as journal:
        BridgeDaemon(
            config, antiek=FakeAntiek(), herdr=BrokenHerdr(), journal=journal
        ).process_once()
        assert journal.pending_attempts() == []
    assert len(captured) == 1
    assert captured[0].kind == "failure"
    assert captured[0].error_code == error_code
    assert captured[0].retryable is retryable


def test_journal_adds_agent_status_column_to_v1_database(tmp_path) -> None:
    import sqlite3

    journal_path = tmp_path / "journal.sqlite3"
    connection = sqlite3.connect(journal_path)
    connection.execute(
        "CREATE TABLE bridge_attempts ("
        "lease_id TEXT PRIMARY KEY, work_id TEXT NOT NULL, attempt_no INTEGER NOT NULL, "
        "context_sha256 TEXT NOT NULL, lease_json TEXT NOT NULL, lease_sha256 TEXT NOT NULL, "
        "target_observed TEXT, prompt_receipt_sha256 TEXT, result_json TEXT, "
        "result_sha256 TEXT, callback_delivered INTEGER NOT NULL DEFAULT 0, "
        "UNIQUE(work_id, attempt_no))"
    )
    connection.commit()
    connection.close()
    journal_path.chmod(0o600)

    with BridgeJournal(journal_path) as journal:
        journal.record_lease(_lease())
        assert journal.pending_attempts()[0].prompt_agent_status is None


def test_real_antiek_contract_and_fake_herdr_complete_one_feedback_loop(
    tmp_path, monkeypatch
) -> None:
    config = load_config(_config(tmp_path))
    db_path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    monkeypatch.setenv("ANTIEK_AGENT_WORK_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_FEEDBACK_ENABLED", "1")
    monkeypatch.setenv(
        "ANTIEK_BRIDGE_CREDENTIALS_JSON",
        json.dumps(
            {
                "mini-bridge-1": {
                    "secret_sha256": hashlib.sha256(b"test-secret").hexdigest(),
                    "logical_worker_id": "research-owner",
                    "scopes": ["lease", "renew", "submitted", "working", "result"],
                }
            }
        ),
    )
    ensure_initialized(db_path)
    create_feedback_thread(
        db_path,
        CreateThreadCommand(
            thread_id="fth-contract",
            root_item_id="fit-operator",
            work_id="wrk-contract",
            owner_user_id="__operator__",
            investigation_id="inv-contract",
            logical_worker_id="research-owner",
            artifact=ArtifactVersionRef("artifact-contract", 2, "a" * 64, "b" * 64),
            anchor=NodeTextAnchor("insight-1", "c" * 64, 0, 4, "fact", "", " remains"),
            body_markdown="Verify this fact.",
            operation_id="feedback:create:contract",
            request_sha256="d" * 64,
            context_sha256="e" * 64,
        ),
    )
    app = TestClient(create_app(register_wrestling=False))

    def transport(method: str, url: str, headers: dict[str, str], body: object):
        path = url.removeprefix(config.antiek_base_url)
        response = app.request(method, path, headers=headers, json=body)
        return HttpResponse(response.status_code, response.json())

    class FakeHerdr:
        def prompt(self, lease: LeaseEnvelope, *, result_path: Path):
            from infrastructure.connectors.herdr_bridge.herdr_adapter import PromptReceipt

            assert lease.work_id == "wrk-contract"
            assert result_path.name == f"{lease.lease_id}.json"
            return PromptReceipt("w11:p5", "f" * 64, "working")

    antiek = AntiekClient(config, transport=transport)
    with BridgeJournal(config.journal_path) as journal:
        daemon = BridgeDaemon(config, antiek=antiek, herdr=FakeHerdr(), journal=journal)
        daemon.process_once()
        attempt = journal.pending_attempts()[0]
        journal.capture_result(
            StructuredResult.parse(
                {
                    "work_id": attempt.lease.work_id,
                    "lease_id": attempt.lease.lease_id,
                    "attempt_no": attempt.lease.attempt_no,
                    "context_sha256": attempt.lease.context_sha256,
                    "kind": "reply",
                    "reply_markdown": "The primary source confirms this fact.",
                }
            )
        )
        daemon.process_once()

    thread = app.get("/feedback/threads/fth-contract")
    assert thread.status_code == 200, thread.text
    body = thread.json()
    assert body["work"]["state"] == "replied"
    assert body["items"][-1]["body_markdown"] == "The primary source confirms this fact."
    assert body["artifact"] == {
        "artifact_id": "artifact-contract",
        "version": 2,
        "content_sha256": "a" * 64,
        "source_sha256": "b" * 64,
    }
