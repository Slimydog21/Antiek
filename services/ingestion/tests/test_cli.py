"""Tests for the ``antiek library ingest`` CLI (SPR-03 / M8).

Coverage:

- ``--dry-run`` single URL → exit 0, prints document_id.
- ``--batch file.txt`` reads URLs and ingests sequentially.
- Failure → non-zero exit code + summary printed.
- Comments + blank lines in batch file are skipped.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from cli import library_ingest


@pytest.fixture
def temp_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-spr03-cli-")
    db_path = os.path.join(tmpdir, "graph.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_EVENT_LOG_DIR", events_dir)
    yield {"db_path": db_path, "tmpdir": tmpdir}


def test_cli_dry_run_single_url(temp_env, capsys):
    exit_code = library_ingest.main([
        "https://example.com/page",
        "--user", "test-user",
        "--dry-run",
        "--db-path", temp_env["db_path"],
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    assert "OK" in out
    assert "doc-dryrun-" in out


def test_cli_dry_run_batch(temp_env, capsys, tmp_path):
    urls_file = tmp_path / "urls.txt"
    urls_file.write_text(
        "# header comment\n"
        "https://a.example.com/x\n"
        "\n"
        "https://arxiv.org/abs/2402.03300\n"
        "# trailing comment\n"
        "https://b.example.com/y.pdf\n"
    )
    exit_code = library_ingest.main([
        "--batch", str(urls_file),
        "--user", "test-user",
        "--dry-run",
        "--db-path", temp_env["db_path"],
    ])
    assert exit_code == 0
    out = capsys.readouterr().out
    # Three URLs ingested (comments + blank lines skipped).
    assert out.count("[1/3]") == 1
    assert out.count("[2/3]") == 1
    assert out.count("[3/3]") == 1
    # arXiv URL routed to arxiv content type.
    assert "doc-dryrun-arxiv" in out
    # PDF URL routed correctly.
    assert "doc-dryrun-pdf" in out


def test_cli_rejects_both_url_and_batch(temp_env, tmp_path):
    f = tmp_path / "urls.txt"
    f.write_text("https://example.com\n")
    with pytest.raises(SystemExit):
        library_ingest.main([
            "https://example.com",
            "--batch", str(f),
            "--user", "u",
        ])


def test_cli_requires_url_or_batch(temp_env):
    with pytest.raises(SystemExit):
        library_ingest.main(["--user", "u"])
