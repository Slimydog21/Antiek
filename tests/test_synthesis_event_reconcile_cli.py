from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from middleware.archive import ArchiveInputs, archive_synthesis_authorized
from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.investigation_streams import initialize_composite_stream
from substrate.investigation_tenancy import InvestigationAuthority


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(root)
    return subprocess.run(
        [sys.executable, str(root / "tools/synthesis_event_reconcile.py"), *args],
        cwd=root,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_reconcile_cli_is_guarded_redacted_and_exact_authority(tmp_path, monkeypatch):
    root = Path(__file__).resolve().parents[1]
    database = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    init_database_at_path(str(database))
    alice = InvestigationAuthority("alice-secret", "shared-display", root=events)
    initialize_composite_stream(alice)

    import substrate.synthesis_event_outbox as outbox

    original_append = outbox.append_event_once_authorized
    monkeypatch.setattr(
        outbox,
        "append_event_once_authorized",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")),
    )
    with connect_write(str(database), purpose="test-cli-stage") as con:
        archive_synthesis_authorized(
            con,
            alice,
            ArchiveInputs(
                target_question="Recover me",
                synthesis_timestamp=datetime(2026, 7, 15, tzinfo=UTC),
                status="passed",
                implicit_recommendation="proceed",
            ),
            logical_key="cli-recovery",
        )
    monkeypatch.setattr(outbox, "append_event_once_authorized", original_append)

    common = (
        "--db-path", str(database), "--root", str(events),
        "--account-id", "alice-secret", "--investigation-id", "shared-display",
    )
    status = _run(root, "status", *common)
    assert status.returncode == 0, status.stderr
    assert json.loads(status.stdout) == {
        "delivered": 0, "failed": 0, "pending": 2, "state": "status"
    }
    assert "alice-secret" not in status.stdout

    refused = _run(root, "reconcile", *common)
    assert refused.returncode == 2
    drained = _run(root, "reconcile", *common, "--approve-reconcile")
    assert drained.returncode == 0, drained.stderr
    assert json.loads(drained.stdout) == {
        "attempted": 2, "delivered": 2, "pending": 0, "state": "reconciled"
    }
    assert "alice-secret" not in drained.stdout

    bob = _run(
        root, "status", "--db-path", str(database), "--root", str(events),
        "--account-id", "bob", "--investigation-id", "shared-display",
    )
    assert json.loads(bob.stdout)["delivered"] == 0
