"""SPR-07 gate — verdict report runs on empty events dir."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def test_tilert_speed_verdict_report_empty(tmp_path):
    env = {"PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [
            sys.executable,
            str(_REPO / "scripts" / "tilert_speed_verdict_report.py"),
            "--events-dir",
            str(tmp_path),
            "--min-investigations",
            "10",
        ],
        cwd=_REPO,
        capture_output=True,
        text=True,
        env={**__import__("os").environ, **env},
    )
    assert proc.returncode == 0, proc.stderr
    assert "insufficient_data" in proc.stdout
    assert "p50 latency_ms" in proc.stdout