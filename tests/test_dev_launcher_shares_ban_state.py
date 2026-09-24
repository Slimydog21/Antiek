"""The dev launcher's per-worktree ANTIEK_HOME must not split the arXiv ban state.

``scripts/start-shared-duckdb-mac-mini.sh`` exports ``ANTIEK_HOME=$WT/.antiek-home``
to isolate per-worktree state. Since SPR-05 task 5, ``ANTIEK_HOME`` also moves
the arXiv throttle state (the ban sentinel), the governor flock derived from it,
``source_throttle.json`` and the ban-event log. Those four are host-scoped: arXiv
bans the IP, not the worktree. An API started by the launcher without pinning
them got a private governor, ignored a ban the operator's CLI had armed and kept
sending to arxiv.org, and logged its own bans where ``tools.arxiv_verify
--ban-events`` in a normal shell never reads.

The test runs two real processes. The first is a plain shell with no ``ANTIEK_*``
variables; it arms an arXiv ban. The second runs in the launcher's environment,
built by evaluating the launcher's own top-level assignment and ``export``
lines, and must see that ban. Only files under ``tmp_path`` are written: both
processes get a surrogate ``HOME`` and the launcher's ``ANTIEK_SHARED_HOME``
points into it.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_LAUNCHER = _REPO / "scripts" / "start-shared-duckdb-mac-mini.sh"

# Column-0 ``NAME=...`` or ``export NAME=...``. Indented lines (inside if-blocks)
# and command substitutions (``$(git ...)``, ``$(cd ...)``) are skipped: they
# either act on the live box or need a real checkout, and neither sets a path
# this test is about.
_ASSIGNMENT = re.compile(r"^(?:export )?[A-Z_][A-Z0-9_]*=")

_ARM_BAN = """
from acquisition.arxiv.throttle import ArxivThrottle
from substrate.source_throttle import SourceThrottle
ArxivThrottle().note_response(429, {}, url="https://export.arxiv.org/api/query")
SourceThrottle().note_response("arxiv_export", 429, {}, url="https://export.arxiv.org/api/query")
"""

_OBSERVE = """
import json, os
from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle, default_state_path
from acquisition.arxiv.rate_governor import default_lock_path
from substrate.ban_events import default_ban_event_log_path, read_ban_events
from substrate.source_throttle import SourceThrottle
from substrate.source_throttle import default_state_path as source_state_path
try:
    ArxivThrottle().wait_if_needed()
    arxiv_banned = False
except ArxivBanned:
    arxiv_banned = True
print(json.dumps({
    "antiek_home": os.environ.get("ANTIEK_HOME", ""),
    "arxiv_state": default_state_path(),
    "arxiv_lock": default_lock_path(),
    "source_state": source_state_path(),
    "ban_log": default_ban_event_log_path(),
    "arxiv_banned": arxiv_banned,
    "source_banned": SourceThrottle().is_banned("arxiv_export"),
    "ban_events_seen": len(read_ban_events()),
}))
"""


def _launcher_env_statements() -> str:
    lines = [
        line
        for line in _LAUNCHER.read_text(encoding="utf-8").splitlines()
        if _ASSIGNMENT.match(line) and "$(" not in line
    ]
    # Non-vacuity: the per-worktree redirect this test guards against must be
    # among the evaluated lines, or the test would pass without exercising it.
    assert any(line.startswith("export ANTIEK_HOME=") for line in lines), (
        "the launcher no longer exports ANTIEK_HOME on a column-0 line; "
        "update this test's extraction before trusting it"
    )
    return "\n".join(lines)


def _plain_env(home: Path) -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(home),
        "PYTHONPATH": str(_REPO),
    }


def test_launcher_api_shares_the_host_ban_state_with_a_plain_shell(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    shared_home = home / ".antiek"
    worktree = tmp_path / "wt"
    home.mkdir()
    worktree.mkdir()
    arm = tmp_path / "arm.py"
    arm.write_text(_ARM_BAN, encoding="utf-8")
    observe = tmp_path / "observe.py"
    observe.write_text(_OBSERVE, encoding="utf-8")

    # Process 1: an operator shell (the CLI, a harvest) with no ANTIEK_* set.
    subprocess.run(
        [sys.executable, str(arm)],
        env=_plain_env(home),
        cwd=_REPO,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Process 2: the launcher's environment. PYTHONPATH is re-pointed at this
    # checkout because the launcher sets it to $WT, a scratch dir here.
    script = (
        _launcher_env_statements()
        + '\nexport PYTHONPATH="$_REPO"\nexec "$_PY" "$_OBSERVE"\n'
    )
    env = _plain_env(home) | {
        "ANTIEK_WORKTREE": str(worktree),
        "ANTIEK_PLATFORM": str(tmp_path / "platform"),
        "ANTIEK_SHARED_HOME": str(shared_home),
        "_REPO": str(_REPO),
        "_PY": sys.executable,
        "_OBSERVE": str(observe),
    }
    proc = subprocess.run(
        ["bash", "-c", script],
        env=env,
        cwd=_REPO,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    seen = json.loads(proc.stdout.strip().splitlines()[-1])

    # The per-worktree redirect is live in this environment, so a pass below
    # means the pins won over it, not that ANTIEK_HOME was never set.
    assert seen["antiek_home"] == str(worktree / ".antiek-home")
    assert seen["arxiv_state"] == str(shared_home / "arxiv_throttle.json")
    assert seen["arxiv_lock"] == str(shared_home / "arxiv_throttle.json.governor.lock")
    assert seen["source_state"] == str(shared_home / "source_throttle.json")
    assert seen["ban_log"] == str(shared_home / "ban_events.jsonl")
    # The behaviour the paths exist for: the launcher's API obeys the ban the
    # plain shell armed, and reads the log the plain shell wrote.
    assert seen["arxiv_banned"] is True
    assert seen["source_banned"] is True
    assert seen["ban_events_seen"] == 2
