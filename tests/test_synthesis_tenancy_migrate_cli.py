from __future__ import annotations

import json
import os
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from tools.synthesis_tenancy_migrate import main


def _fixture(tmp_path: Path, monkeypatch):
    database = tmp_path / "graph.duckdb"
    root = tmp_path / "events"
    root.mkdir()
    monkeypatch.setenv(
        "ANTIEK_INVESTIGATION_TENANCY_KEY_SECRET", "cli-disposable-secret"
    )
    init_database_at_path(str(database))
    with connect_write(str(database), purpose="seed-synthesis-cli") as con:
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, "
            "target_question, synthesis_timestamp, status, "
            "implicit_recommendation) VALUES "
            "('private-alice-synthesis', 'shared-private-display', 'A?', "
            "CURRENT_TIMESTAMP, 'passed', 'proceed'), "
            "('private-bob-synthesis', 'shared-private-display', 'B?', "
            "CURRENT_TIMESTAMP, 'passed', 'proceed')"
        )
    assignment_path = tmp_path / "assignments.json"
    assignments = [
        {
            "synthesis_id": "private-alice-synthesis",
            "account_id": "private-alice-account",
            "investigation_id": "shared-private-display",
        },
        {
            "synthesis_id": "private-bob-synthesis",
            "account_id": "private-bob-account",
            "investigation_id": "shared-private-display",
        },
    ]
    assignment_path.write_text(json.dumps(assignments), encoding="utf-8")
    return database, root, assignment_path, assignments


def _args(action: str, database: Path, root: Path, assignments: Path) -> list[str]:
    return [
        action,
        "--db-path",
        str(database),
        "--root",
        str(root),
        "--assignments",
        str(assignments),
    ]


def test_plan_is_read_only_and_redacted(tmp_path, monkeypatch, capsys):
    database, root, assignment_path, private_rows = _fixture(tmp_path, monkeypatch)
    before = {
        path.relative_to(tmp_path): path.stat().st_size
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert main(_args("plan", database, root, assignment_path)) == 0
    output = capsys.readouterr().out
    receipt = json.loads(output)
    assert receipt["ready"] is True
    assert receipt["assignment_rows"] == receipt["database_rows"] == 2
    for row in private_rows:
        assert all(value not in output for value in row.values())
    after = {
        path.relative_to(tmp_path): path.stat().st_size
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    assert after == before


def test_disposable_migrate_verify_rollback_is_redacted(
    tmp_path, monkeypatch, capsys
):
    database, root, assignment_path, private_rows = _fixture(tmp_path, monkeypatch)
    migrate_args = _args("migrate", database, root, assignment_path)
    with pytest.raises(SystemExit):
        main(migrate_args)
    assert main([*migrate_args, "--approve-migration"]) == 0
    migrated_text = capsys.readouterr().out
    assert json.loads(migrated_text)["state"] == "shadow"
    assert main(_args("verify", database, root, assignment_path)) == 0
    verified_text = capsys.readouterr().out
    assert json.loads(verified_text)["assigned_rows"] == 2
    with pytest.raises(SystemExit):
        main(["rollback", "--db-path", str(database), "--root", str(root)])
    assert main(
        [
            "rollback",
            "--db-path",
            str(database),
            "--root",
            str(root),
            "--approve-rollback",
        ]
    ) == 0
    rollback_text = capsys.readouterr().out
    assert json.loads(rollback_text)["rolled_back_rows"] == 2
    for text in (migrated_text, verified_text, rollback_text):
        for row in private_rows:
            assert all(value not in text for value in row.values())
    con = duckdb.connect(str(database), read_only=True)
    try:
        assert con.execute(
            "SELECT account_digest, investigation_digest FROM syntheses"
        ).fetchall() == [(None, None), (None, None)]
    finally:
        con.close()


def test_activation_requires_exact_confirmation(tmp_path, monkeypatch, capsys):
    database, root, assignment_path, _private_rows = _fixture(tmp_path, monkeypatch)
    assert main(
        [*_args("migrate", database, root, assignment_path), "--approve-migration"]
    ) == 0
    capsys.readouterr()
    activate_args = _args("activate", database, root, assignment_path)
    with pytest.raises(SystemExit):
        main(activate_args)
    assert main(
        [
            *activate_args,
            "--confirm-activation",
            "activate-synthesis-tenancy-v1",
        ]
    ) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "scoped"


def test_assignment_symlink_is_rejected(tmp_path, monkeypatch):
    database, root, assignment_path, _private_rows = _fixture(tmp_path, monkeypatch)
    link = tmp_path / "assignment-link.json"
    os.symlink(assignment_path, link)
    with pytest.raises(ValueError, match="unsafe"):
        main(_args("plan", database, root, link))
