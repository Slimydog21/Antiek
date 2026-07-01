from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RUNBOOK = REPO / "infrastructure" / "runbooks" / "debug-a-real-run.md"
EVENTS_DIR = "tests/fixtures/trajectories"


def _documented_commands() -> list[str]:
    text = RUNBOOK.read_text(encoding="utf-8")
    commands: list[str] = []
    for match in re.finditer(r"```bash\n(.*?)\n```", text, flags=re.DOTALL):
        block = match.group(1).strip()
        for line in block.splitlines():
            command = line.strip()
            if command and not command.startswith("#"):
                commands.append(command)
    return commands


def _run(command: str) -> subprocess.CompletedProcess[str]:
    argv = shlex.split(command)
    if argv and argv[0] == "python":
        argv[0] = sys.executable
    return subprocess.run(
        argv,
        cwd=REPO,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def test_debug_runbook_commands_exit_zero() -> None:
    commands = _documented_commands()
    assert commands, "runbook should contain copy-pasteable bash commands"

    failures = []
    for command in commands:
        result = _run(command)
        if result.returncode != 0:
            failures.append(
                f"{command}\nexit={result.returncode}\nstdout={result.stdout}\nstderr={result.stderr}"
            )

    assert not failures, "\n\n".join(failures)


def test_debug_runbook_bisect_worked_example_verdicts() -> None:
    expected = {
        "empty_retrieval": "DATA",
        "provider_error": "DISPATCH",
        "code_bug": "CODE",
        "healthy": "INCONCLUSIVE",
    }

    for investigation_id, cause in expected.items():
        result = _run(
            "python tools/eventlog_bisect.py "
            f"--events-dir {EVENTS_DIR} --investigation-id {investigation_id}"
        )
        assert result.returncode == 0, result.stderr
        assert f"CAUSE: {cause}" in result.stdout


def test_runbook_step_claims_hold() -> None:
    """Every FACTUAL claim the runbook prose makes about fixture output is
    asserted here, so the prose cannot silently rot (glm SPR-06 SHOULD-FIX:
    the exit-0 checks did not verify the Steps 1-3/5 claims)."""
    q = f"python tools/eventlog_query.py"

    # Step 1: "Expect Final synthesis (phase 6) at the top for the healthy fixture."
    r1 = _run(f"{q} which-phase-slowest --events-dir {EVENTS_DIR} --investigation-id healthy")
    assert r1.returncode == 0, r1.stderr
    assert "Final synthesis" in r1.stdout
    # slowest-first: phase 6 must appear before the next-slowest phase-4 row.
    assert r1.stdout.index("Final synthesis") < r1.stdout.index("Round 2 deep dive on gaps"), r1.stdout

    # Step 2: "For healthy, expect status = completed; the stall columns are -."
    r2 = _run(f"{q} where-did-it-stall --events-dir {EVENTS_DIR} --investigation-id healthy")
    assert r2.returncode == 0, r2.stderr
    assert "completed" in r2.stdout

    # Step 3: "For provider_error, expect openai / gpt-4.1-mini with error_rate = 1."
    r3 = _run(f"{q} which-provider-fails --events-dir {EVENTS_DIR} --investigation-id provider_error")
    assert r3.returncode == 0, r3.stderr
    assert "openai" in r3.stdout and "gpt-4.1-mini" in r3.stdout

    # Step 5: the --correlation-id rehearsal command "warns that no rows matched".
    r5 = _run(f"{q} which-phase-slowest --correlation-id fixture-root --events-dir {EVENTS_DIR}")
    assert r5.returncode == 0, r5.stderr
    assert "no rows matched" in (r5.stdout + r5.stderr), (r5.stdout, r5.stderr)
