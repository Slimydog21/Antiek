from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from substrate.research_artifact.authority import ArtifactAuthority
from substrate.research_artifact.outbox import stage_event
from substrate.schemas.events import ArtifactGeneratedPayload


def _run(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo)
    return subprocess.run(
        [sys.executable, str(repo / "tools/research_artifact_event_reconcile.py"), *args],
        cwd=repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_artifact_event_reconcile_cli_is_guarded_redacted_and_exact(tmp_path, monkeypatch):
    repo = Path(__file__).resolve().parents[1]
    artifacts = tmp_path / "artifacts"
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(artifacts))
    alice = ArtifactAuthority("alice-secret", "shared")
    stage_event(
        alice,
        event_key="recover-one",
        role="note_taker",
        payload=ArtifactGeneratedPayload(
            artifact_id="artifact-one",
            artifact_kind="other",
            intent="recovery proof",
            generating_role="note_taker",
            artifact_path="opaque-artifact",
            content_hash="a" * 64,
            size_bytes=1,
            source_event_ids=["source-one"],
        ).model_dump(mode="json"),
    )
    common = (
        "--artifact-root",
        str(artifacts),
        "--events-root",
        str(events),
        "--account-id",
        "alice-secret",
        "--investigation-id",
        "shared",
    )
    status = _run(repo, "status", *common)
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout) == {
        "pending": 1,
        "quarantined": 0,
        "state": "status",
    }
    assert "alice-secret" not in status.stdout

    refused = _run(repo, "reconcile", *common)
    assert refused.returncode == 2
    drained = _run(repo, "reconcile", *common, "--approve-reconcile")
    assert drained.returncode == 0, drained.stderr
    assert json.loads(drained.stdout) == {
        "attempted": 1,
        "delivered": 1,
        "pending": 0,
        "quarantined": 0,
        "state": "reconciled",
    }
    assert "alice-secret" not in drained.stdout

    bob = _run(
        repo,
        "status",
        "--artifact-root",
        str(artifacts),
        "--events-root",
        str(events),
        "--account-id",
        "bob",
        "--investigation-id",
        "shared",
    )
    assert json.loads(bob.stdout)["pending"] == 0
