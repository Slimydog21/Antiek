from __future__ import annotations

import json
import os

import pytest

from substrate.event_log import prepare_typed_event, trajectory_authorized
from substrate.investigation_streams import StreamStorageState, resolve_investigation_stream
from substrate.investigation_tenancy import InvestigationAuthority, legacy_lease_storage_state
from substrate.multi_user.auth import operator_claims
from substrate.schemas.events import DispatchCallPayload
from tools import investigation_tenancy_migrate as migration_tool
from tools.investigation_tenancy_migrate import main


def _event(investigation_id: str, event_id: str):
    return prepare_typed_event(
        investigation_id,
        DispatchCallPayload(
            provider="provider",
            model="model",
            tier="flash",
            target_role="researcher",
            input_tokens=1,
            output_tokens=2,
            cost_usd=0.01,
            latency_ms=3,
            prompt_hash="private-prompt-hash",
        ),
        event_id=event_id,
    )


def test_dry_run_is_redacted_and_apply_binds_operator(tmp_path, capsys):
    private_id = "private-question-stream"
    (tmp_path / f"{private_id}.jsonl").write_text("{}\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "--include-entries"]) == 0
    dry = capsys.readouterr().out
    assert private_id not in dry
    assert json.loads(dry)["entries"][0]["disposition"] == "valid_regular"

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--apply",
                "--approve-operator-migration",
            ]
        )
        == 0
    )
    applied = json.loads(capsys.readouterr().out)
    assert applied["attempted"] == len(applied["migrated"]) == 1
    assert list((tmp_path / ".tenancy" / "legacy-stream-leases").glob("*.json"))


def test_nonregular_stream_is_quarantined_without_following_link(tmp_path, capsys):
    target = tmp_path / "outside"
    target.write_text("unchanged", encoding="utf-8")
    os.symlink(target, tmp_path / "hostile.jsonl")
    result = main(
        [
            "--root",
            str(tmp_path),
            "--apply",
            "--approve-operator-migration",
        ]
    )
    assert result == 1
    receipt = json.loads(capsys.readouterr().out)
    assert len(receipt["quarantined"]) == 1
    assert target.read_text(encoding="utf-8") == "unchanged"


def test_owner_scoped_artifact_event_stream_is_excluded(tmp_path, capsys):
    artifact_stream = {
        "investigation_id": "opaque-owner-stream",
        "payload": {"intent": "research_artifact_v1:private-investigation"},
    }
    (tmp_path / "opaque-owner-stream.jsonl").write_text(
        json.dumps(artifact_stream) + "\n", encoding="utf-8"
    )
    (tmp_path / "historic-investigation.jsonl").write_text("{}\n", encoding="utf-8")

    assert main(["--root", str(tmp_path), "--batch-size", "10"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["total_discovered"] == 2
    assert receipt["migration_denominator"] == 1
    assert receipt["batch_count"] == 1
    assert receipt["summary"]["excluded_owner_scoped_artifact_event"] == 1


def test_mixed_or_malformed_artifact_stream_remains_in_denominator(tmp_path, capsys):
    artifact = {
        "investigation_id": "mixed",
        "payload": {"intent": "research_artifact_v1:private"},
    }
    (tmp_path / "mixed.jsonl").write_text(
        json.dumps(artifact) + "\n" + json.dumps({"payload": {"intent": "other"}}) + "\n",
        encoding="utf-8",
    )
    (tmp_path / "malformed.jsonl").write_text(
        json.dumps({**artifact, "investigation_id": "malformed"}) + "\n{" ,
        encoding="utf-8",
    )

    assert main(["--root", str(tmp_path), "--batch-size", "10"]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["migration_denominator"] == 2
    assert receipt["summary"] == {"valid_regular": 2}


def test_stream_scan_is_bounded_before_json_parsing(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(migration_tool, "_MAX_CLASSIFICATION_STREAM_BYTES", 1024)
    (tmp_path / "oversized.jsonl").write_bytes(b"x" * 2048)
    assert main(["--root", str(tmp_path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["migration_denominator"] == 1
    assert receipt["summary"] == {"valid_regular": 1}


def test_dry_run_creates_no_tenancy_or_lock_files(tmp_path, capsys):
    (tmp_path / "read-only-census.jsonl").write_text("{}\n", encoding="utf-8")
    before = {
        path.relative_to(tmp_path): (path.stat().st_size if path.is_file() else None)
        for path in tmp_path.rglob("*")
    }

    assert main(["--root", str(tmp_path)]) == 0

    capsys.readouterr()
    after = {
        path.relative_to(tmp_path): (path.stat().st_size if path.is_file() else None)
        for path in tmp_path.rglob("*")
    }
    assert after == before


def test_disposable_forward_and_rollback_cli_are_redacted(tmp_path, capsys):
    private_id = "private-cli-stream"
    event = _event(private_id, "evt-cli")
    (tmp_path / f"{private_id}.jsonl").write_text(
        json.dumps(event.model_dump(mode="json")) + "\n",
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--copy-composite",
                "--approve-composite-migration",
            ]
        )
        == 0
    )
    forward_text = capsys.readouterr().out
    assert private_id not in forward_text
    assert "private-prompt-hash" not in forward_text
    forward = json.loads(forward_text)
    assert forward["completed"][0]["disposition"] == "migrated"
    authority = InvestigationAuthority(
        operator_claims().user_id,
        private_id,
        root=tmp_path,
    )
    assert resolve_investigation_stream(authority).state is StreamStorageState.COMPOSITE
    assert [row["event_id"] for row in trajectory_authorized(authority)] == ["evt-cli"]

    assert (
        main(
            [
                "--root",
                str(tmp_path),
                "--rollback-composite",
                "--approve-composite-rollback",
            ]
        )
        == 0
    )
    rollback_text = capsys.readouterr().out
    assert private_id not in rollback_text
    assert json.loads(rollback_text)["completed"][0]["disposition"] == "rolled_back"
    assert legacy_lease_storage_state(authority) == "legacy"


def test_composite_cli_requires_direction_specific_approval(tmp_path):
    (tmp_path / "approval.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "--copy-composite"])
    with pytest.raises(SystemExit):
        main(["--root", str(tmp_path), "--rollback-composite"])


def test_census_entry_limit_fails_without_disclosing_candidate_names(tmp_path, capsys):
    private_ids = ["private-alpha", "private-beta", "private-gamma"]
    for investigation_id in private_ids:
        (tmp_path / f"{investigation_id}.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="census exceeds entry limit") as exc_info:
        main(
            [
                "--root",
                str(tmp_path),
                "--max-census-entries",
                "2",
            ]
        )

    rendered = str(exc_info.value) + capsys.readouterr().err
    assert all(private_id not in rendered for private_id in private_ids)


def test_lease_only_apply_rejects_control_characters_without_mutation(tmp_path):
    unsafe_id = "private\nstream"
    (tmp_path / f"{unsafe_id}.jsonl").write_text("{}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="investigation_id is invalid"):
        main(
            [
                "--root",
                str(tmp_path),
                "--apply",
                "--approve-operator-migration",
            ]
        )

    lease_root = tmp_path / ".tenancy" / "legacy-stream-leases"
    assert not lease_root.exists() or not any(lease_root.iterdir())
