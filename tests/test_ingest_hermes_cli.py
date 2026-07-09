"""CLI contract for tools.ingest_hermes — dry-run default, plan, apply."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from tools.ingest_hermes import main, plan


@pytest.fixture
def hermes_dir(tmp_path: Path):
    d = tmp_path / "events"
    d.mkdir()
    line = json.dumps(
        {
            "event_id": "e1",
            "investigation_id": "inv-cli",
            "emitted_at": "2026-07-01T00:00:00Z",
            "action_type": "synthesize",
            "payload": {"sub_question": "what compounds?"},
        }
    )
    (d / "t.jsonl").write_text(line + "\n", encoding="utf-8")
    return d


def test_plan_counts(hermes_dir: Path):
    # plan requires allowed_roots — set env so default_allowed_roots includes hermes_dir
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        events, invs, ids = plan(hermes_dir, limit=None)
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert events == 1
    assert invs == 1
    assert ids == ["inv-cli"]


def test_dry_run_exits_zero_without_db(hermes_dir: Path, capsys):
    os.environ["ANTIEK_HERMES_EVENTS_DIR"] = str(hermes_dir)
    try:
        code = main(["--events-dir", str(hermes_dir)])
    finally:
        os.environ.pop("ANTIEK_HERMES_EVENTS_DIR", None)
    assert code == 0
    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "inv-cli" in out


def test_outside_root_fails(tmp_path: Path):
    outsider = tmp_path / "not-hermes"
    outsider.mkdir()
    code = main(["--events-dir", str(outsider)])
    assert code == 2
