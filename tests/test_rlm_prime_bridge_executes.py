"""SPR-01 Task 3 keystone: the live ``document.loaded`` call site must SPAWN Prime.

A test that asserts ``root_executor == "prime_agent"`` proves a label — the exact
stub-theater this repo has been burned by. This one installs a stand-in
``prime-agent`` that appends its argv as one line to a witness file on EVERY exec,
drives the real ``make_document_loaded_handler`` with both documented flags set on
an above-threshold document, and reads the spawn count back from the witness file.

Before Task 3 the witness file never came into existence: the bridge created a
session labelled ``prime_agent`` and nothing executed the binary. After it, the
witness records the two capability probes (``--version``, ``--help``) plus the
``-p`` run, and the session carries one recorded iteration.

The stand-in writes no handoff file, so this also exercises the Task 2 contract:
its stdout answer becomes the iteration summary rather than a 120s poll.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest

_HELP_TOKENS = (
    "-p --cwd --offline --no-session --no-tools --no-extensions --no-skills "
    "--no-prompt-templates --no-themes --no-context-files --mode rpc"
)


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-rlm-prime-keystone-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized

        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


class _RecordingBroadcaster:
    def __init__(self) -> None:
        self.events: list = []

    async def broadcast(self, event) -> None:
        self.events.append(event)


def _install_witness_binary(tmp_path: Path) -> tuple[Path, Path]:
    """A stand-in prime-agent that logs every exec's argv, then behaves."""
    witness = tmp_path / "witness.log"
    binary = tmp_path / "prime-agent"
    binary.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' \"$*\" >> '{witness}'\n"
        'case "$1" in\n'
        '  --version) echo "prime-agent 0.9.4"; exit 0;;\n'
        f'  --help) echo "{_HELP_TOKENS}"; exit 0;;\n'
        "esac\n"
        "cat >/dev/null\n"
        'echo "opening condensation from the stand-in"\n'
    )
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    return binary, witness


def _doc_loaded_event(*, document_id: str, size_bytes: int):
    from substrate.schemas.events import ActionType, DocumentLoadedPayload, Event

    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:8]}",
        investigation_id="inv-prime-keystone",
        action_type=ActionType.DOCUMENT_LOADED,
        payload=DocumentLoadedPayload(
            media_type="pdf",
            source_uri=f"file:///tmp/{document_id}.pdf",
            title=f"doc {document_id}",
            content_hash="deadbeef",
            size_bytes=size_bytes,
            page_count=10,
        ),
        param_version="test-v0",
        emitted_at=datetime.now(UTC),
        document_id=document_id,
    )


def test_live_call_site_spawns_prime_and_records_an_iteration(
    isolated_db, monkeypatch, tmp_path, capsys
) -> None:
    binary, witness = _install_witness_binary(tmp_path)
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", "1")
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_BIN", str(binary))
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_RLM_TIMEOUT_SECONDS", "10")

    from interfaces.research.api.wrestling import make_document_loaded_handler

    bus = _RecordingBroadcaster()
    handler = make_document_loaded_handler(db_path=isolated_db, broadcaster=bus)
    # 2 MiB -> ~524k estimated tokens, far above the 64K threshold.
    asyncio.run(
        handler(_doc_loaded_event(document_id="doc-prime-keystone", size_bytes=2_097_152))
    )

    execs = witness.read_text().splitlines() if witness.exists() else []
    prompt_runs = [line for line in execs if line.split()[-1:] == ["-p"]]
    handler_out = capsys.readouterr().out
    recorded = re.search(r"iterations=(\d+)", handler_out)
    iteration_count = int(recorded.group(1)) if recorded else 0

    print(f"spawns: {len(execs)}")
    print(f"prompt_runs: {len(prompt_runs)}")
    print(f"iteration_count: {iteration_count}")

    assert len(execs) >= 1, "the live call site spawned no Prime process at all"
    assert prompt_runs, "Prime was only probed (--version/--help), never run with -p"
    assert iteration_count >= 1, "the escalated session recorded no iteration"
    decided = [
        e
        for e in bus.events
        if (e.action_type.value if hasattr(e.action_type, "value") else e.action_type)
        == "rlm.bridge.decided"
    ]
    assert len(decided) == 1 and decided[0].payload.escalated is True


def test_flags_off_spawns_nothing(isolated_db, monkeypatch, tmp_path) -> None:
    """The default posture is unchanged: ratified but not Prime-enabled must not exec."""
    binary, witness = _install_witness_binary(tmp_path)
    monkeypatch.setenv("ANTIEK_RLM_RATIFIED", "1")
    monkeypatch.delenv("ANTIEK_PRIME_AGENT_RLM_ENABLED", raising=False)
    monkeypatch.setenv("ANTIEK_PRIME_AGENT_BIN", str(binary))

    from interfaces.research.api.wrestling import make_document_loaded_handler

    handler = make_document_loaded_handler(db_path=isolated_db, broadcaster=None)
    asyncio.run(handler(_doc_loaded_event(document_id="doc-prime-off", size_bytes=2_097_152)))

    assert not witness.exists(), witness.read_text()
