"""The HTTP notes import reads only research artifacts, never a client's path.

``POST /research/{investigation_id}/artifact/import-notes`` passed the body's
``path`` to ``import_agent_notes``, which opened any file the server can read
and answered a missing file differently from a present one. The route now reads
the file through the artifacts directory's anchored, symlink-refusing reader
and gives every refused path the same answer. The command-line import, which
runs as the operator on their own machine, keeps reading local paths.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from pathlib import Path

from test_artifact_routes import _client, api_env  # noqa: F401  (fixture)

from substrate.graph.insight_question import promote_insight

REFUSAL = "import_notes_path_invalid"


def _exported(client, api_env) -> Path:  # noqa: F811
    promote_insight(text="An importable finding.", investigation_id="inv-imp",
                    confidence="moderate", source_document_id=None)
    resp = client.post("/research/inv-imp/artifact/export")
    assert resp.status_code == 200, resp.text
    return Path(resp.json()["path"])


def _import(client, path: str):
    return client.post("/research/inv-imp/artifact/import-notes", json={"path": path})


def test_an_artifact_in_the_artifacts_dir_imports(api_env):  # noqa: F811
    client = _client()
    resp = _import(client, str(_exported(client, api_env)))
    assert resp.status_code == 200, resp.text


def test_a_copy_outside_the_artifacts_dir_is_refused(api_env):  # noqa: F811
    client = _client()
    outside = Path(api_env["arts"]).parent / "outside.html"
    shutil.copyfile(_exported(client, api_env), outside)
    resp = _import(client, str(outside))
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == REFUSAL


def test_a_symlink_in_the_artifacts_dir_is_refused(api_env):  # noqa: F811
    client = _client()
    outside = Path(api_env["arts"]).parent / "outside.html"
    shutil.copyfile(_exported(client, api_env), outside)
    link = Path(api_env["arts"]) / "linked.html"
    link.symlink_to(outside)
    resp = _import(client, str(link))
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == REFUSAL


def test_a_missing_path_and_a_present_one_are_refused_alike(api_env):  # noqa: F811
    client = _client()
    present = Path(api_env["arts"]).parent / "present.env"
    present.write_text("PRIVATE=1\n")
    answers = [
        (r.status_code, r.json())
        for r in (_import(client, str(present)), _import(client, str(present.with_name("absent.env"))))
    ]
    assert answers[0] == answers[1] == (400, {"detail": REFUSAL}), answers


def _returns_promptly(fn, fifo: Path, timeout: float = 3.0):
    """Run ``fn`` in a thread; report whether it was still blocked after
    ``timeout``. A blocked reader is released by opening the FIFO for writing,
    so a regression fails the test instead of hanging the suite."""
    import threading

    outcome: dict[str, object] = {}

    def run() -> None:
        try:
            outcome["value"] = fn()
        except Exception as err:  # noqa: BLE001 - the test inspects it
            outcome["error"] = err

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout)
    blocked = worker.is_alive()
    if blocked:
        with contextlib.suppress(OSError):
            os.close(os.open(fifo, os.O_WRONLY | os.O_NONBLOCK))
        worker.join(5)
    return blocked, outcome


def test_a_fifo_in_the_artifacts_dir_is_refused_without_blocking(api_env):  # noqa: F811
    client = _client()
    fifo = Path(api_env["arts"]) / "notes-fifo.html"
    fifo.parent.mkdir(parents=True, exist_ok=True)
    os.mkfifo(fifo)
    blocked, outcome = _returns_promptly(lambda: _import(client, str(fifo)), fifo)
    assert not blocked, "the import-notes route blocked on a FIFO"
    resp = outcome["value"]
    assert resp.status_code == 400 and resp.json()["detail"] == REFUSAL, resp.text


def _open_fd_count() -> int:
    return len(os.listdir("/dev/fd"))


def test_refused_malformed_paths_do_not_leak_descriptors(api_env):  # noqa: F811
    # A NUL in a client path makes os.open raise ValueError rather than
    # OSError; each refusal must still close every descriptor it opened, or
    # repeated requests exhaust the server's descriptors.
    from substrate.research_artifact.paths import (
        read_importable_artifact,
        read_reviewed_draft_merge,
    )

    client = _client()
    arts = Path(api_env["arts"])
    arts.mkdir(parents=True, exist_ok=True)
    readers = (
        lambda: read_importable_artifact(str(arts / "bad\x00name.html")),
        lambda: read_reviewed_draft_merge(str(arts / "draft-merge-bad\x00name.html")),
    )
    for read in readers:
        with contextlib.suppress(ValueError):
            read()  # warm any lazy imports before counting
        before = _open_fd_count()
        for _ in range(20):
            with contextlib.suppress(ValueError):
                read()
        assert _open_fd_count() == before
    _import(client, str(arts / "warm\x00.html"))
    before = _open_fd_count()
    for _ in range(20):
        resp = _import(client, str(arts / "bad\x00name.html"))
        assert resp.status_code == 400 and resp.json()["detail"] == REFUSAL, resp.text
    assert _open_fd_count() == before
