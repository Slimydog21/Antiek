"""A source merge may only splice a draft this server wrote into a book.

The reviewed packet carries ``draft_merge_path`` from the client, and
``source_merge._read_reviewed_draft`` read whatever file it named. Preview
answered with that file's size and hash (and a different error when it did not
exist), and commit spliced its contents into the source document's body, where
the reader serves it: any file the server process can read, such as
``~/.antiek/secrets.env``, could be copied into a book. The draft must be a
regular ``draft-merge-*.html`` file directly inside the research artifacts
directory, reached without a symlink or ``..``, and every other value is refused
with the same answer whether or not the file exists.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
from test_artifact_routes import (  # noqa: F401  (fixture)
    _client,
    _source_merge_commit_payload,
    _source_merge_ready_packet,
    api_env,
)

from runtime.db_lock import connect_write

SECRET = "ANTIEK_SECRET_TOKEN=do-not-exfiltrate"
REFUSAL = "source_merge_draft_merge_path_invalid"


def _secret_file(api_env) -> Path:  # noqa: F811
    secret = Path(api_env["arts"]).parent / "secrets.env"
    secret.write_text(SECRET + "\n")
    return secret


def _preview(client, packet: dict, hashes: dict[str, str]):
    return client.post(
        "/research/artifacts/source-merge/preview",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
        },
    )


def _source_body() -> str:
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_body") as con:
        (raw,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", ["doc-source-merge"]
        ).fetchone()
    return raw


def _assert_refused(resp) -> None:
    assert resp.status_code == 400, resp.text
    assert REFUSAL in resp.text, resp.text


def _variants(api_env) -> dict[str, str]:  # noqa: F811
    arts = Path(api_env["arts"])
    secret = _secret_file(api_env)
    link = arts / "draft-merge-inv-evil-a-inv-evil-b.html"
    link.symlink_to(secret)
    other = arts / "inv-src-a.html"
    other.write_text("<p>another investigation's artifact</p>")
    elsewhere = arts.parent / "elsewhere"
    elsewhere.mkdir(exist_ok=True)
    lookalike = elsewhere / "draft-merge-inv-src-a-inv-src-b.html"
    lookalike.write_text(SECRET)
    (arts / "sub").mkdir(exist_ok=True)
    return {
        "absolute-outside": str(secret),
        "dotdot-escape": str(arts / ".." / "secrets.env"),
        "dotdot-in-name": str(arts / "draft-merge-x" / ".." / ".." / "secrets.env"),
        "symlinked-draft": str(link),
        "non-draft-artifact": str(other),
        "relative": "secrets.env",
        "draft-named-outside": str(lookalike),
        "draft-named-via-dotdot": str(arts / "sub" / ".." / ".." / "elsewhere" / lookalike.name),
    }


@pytest.mark.parametrize(
    "variant",
    ["absolute-outside", "dotdot-escape", "dotdot-in-name", "symlinked-draft",
     "non-draft-artifact", "relative", "draft-named-outside", "draft-named-via-dotdot"],
)
def test_preview_refuses_a_draft_path_the_server_did_not_write(api_env, variant):  # noqa: F811
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    packet["draft_merge_path"] = _variants(api_env)[variant]
    _assert_refused(_preview(client, packet, hashes))


def test_commit_cannot_splice_a_file_outside_the_artifacts_dir_into_the_book(api_env):  # noqa: F811
    # The attacker's flow: preview the secret's path, then commit with the
    # revision ids and hashes that preview returned, so the binding matches.
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    evil = {**packet, "draft_merge_path": str(_secret_file(api_env))}
    preview = _preview(client, evil, hashes)
    evidence = preview.json() if preview.status_code == 200 else {
        key: "unused" for key in ("source_revision_id", "twin_revision_id", "before_source_hash",
                                  "after_source_hash", "before_twin_hash", "after_twin_hash")
    }
    resp = client.post(
        "/research/artifacts/source-merge/commit",
        json=_source_merge_commit_payload(evil, hashes, evidence),
    )
    _assert_refused(resp)
    assert SECRET not in _source_body()


def test_apply_refuses_a_draft_path_the_server_did_not_write(api_env):  # noqa: F811
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    packet["draft_merge_path"] = str(_secret_file(api_env))
    resp = client.post(
        "/research/artifacts/source-merge/apply",
        json={
            "reviewed_packet": packet,
            "expected_content_hashes": hashes,
            "acknowledge_reviewed_draft": True,
            "acknowledge_source_book_mutation": True,
            "acknowledge_twin_document_mutation": True,
            "operator_reviewer": "pytest",
        },
    )
    _assert_refused(resp)


def test_a_missing_path_and_a_present_one_are_refused_alike(api_env):  # noqa: F811
    # No existence oracle: the answer must not depend on whether the file is there.
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    present = _secret_file(api_env)
    answers = []
    for path in (present, present.with_name("absent.env")):
        resp = _preview(client, {**packet, "draft_merge_path": str(path)}, hashes)
        answers.append((resp.status_code, resp.json()))
    assert answers[0] == answers[1], answers


def test_the_draft_the_server_composed_still_previews(api_env):  # noqa: F811
    # Positive control: the confinement admits exactly what compose wrote.
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    resp = _preview(client, packet, hashes)
    assert resp.status_code == 200, resp.text
    assert resp.json()["writes_performed"] is False


def test_the_substrate_reader_is_confined_without_the_route(api_env):  # noqa: F811
    # A future caller that skips the HTTP preflight still cannot read an
    # arbitrary file: the confinement lives in the reader itself.
    from substrate.research_artifact.source_merge import preview_source_merge_review

    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    with (
        connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/direct_preview") as con,
        pytest.raises(ValueError, match=REFUSAL),
    ):
        preview_source_merge_review(
            con,
            document_id="doc-source-merge",
            draft_merge_path=str(_secret_file(api_env)),
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=hashes,
            hash_conflicts=[],
        )


def test_a_draft_swapped_for_a_symlink_after_validation_is_not_read(api_env, monkeypatch):  # noqa: F811
    # The route validates the draft, then the substrate reads it. Replacing the
    # draft with a symlink between the two must not reach the target: the read
    # itself refuses a symlink, it does not rely on the earlier check.
    import interfaces.research.api.artifact_routes as routes

    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    secret = _secret_file(api_env)
    real = routes._validate_source_merge_preflight

    def validate_then_swap(body, *, db_path):
        members = real(body, db_path=db_path)
        draft = Path(body.reviewed_packet.draft_merge_path)
        draft.unlink()
        draft.symlink_to(secret)
        return members

    monkeypatch.setattr(routes, "_validate_source_merge_preflight", validate_then_swap)
    resp = _preview(client, packet, hashes)
    assert resp.status_code != 200, resp.text
    assert REFUSAL in resp.text, resp.text
    assert SECRET not in resp.text


def test_a_relative_artifacts_dir_still_previews_its_own_draft(api_env, monkeypatch, tmp_path):  # noqa: F811
    # Compose returns a relative draft path when the artifacts directory is
    # configured relative; the confinement must read it the same way.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", "relative-artifacts")
    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    resp = _preview(client, packet, hashes)
    assert resp.status_code == 200, resp.text


def test_a_draft_swapped_right_after_the_readers_first_access_is_not_read(api_env, monkeypatch):  # noqa: F811
    # The race inside the reader: once its first filesystem access to the draft
    # completes, the draft is replaced by a symlink to another file. A reader
    # that checks and then reopens by name follows the symlink; one that reads
    # from the descriptor it opened cannot.
    from substrate.research_artifact import source_merge

    client = _client()
    packet, _ = _source_merge_ready_packet(client)
    draft = Path(packet["draft_merge_path"])
    secret = _secret_file(api_env)
    swapped: list[bool] = []

    def swap_once() -> None:
        if not swapped:
            swapped.append(True)
            draft.unlink()
            draft.symlink_to(secret)

    def names_draft(target) -> bool:
        return os.fspath(target).endswith(draft.name)

    real_lstat, real_open = os.lstat, os.open

    def lstat_then_swap(target, *args, **kwargs):
        result = real_lstat(target, *args, **kwargs)
        if names_draft(target):
            swap_once()
        return result

    def open_then_swap(target, *args, **kwargs):
        result = real_open(target, *args, **kwargs)
        if names_draft(target):
            swap_once()
        return result

    monkeypatch.setattr(os, "lstat", lstat_then_swap)
    monkeypatch.setattr(os, "open", open_then_swap)
    try:
        text = source_merge._read_reviewed_draft(str(draft))
    except ValueError as err:
        assert REFUSAL in str(err)
    else:
        assert SECRET not in text
    assert swapped, "the reader never touched the draft"


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


def test_a_fifo_named_like_a_draft_is_refused_without_blocking(api_env):  # noqa: F811
    # Opening a FIFO for reading blocks until a writer appears; the check that
    # refuses non-regular files must not sit behind that open.
    from substrate.research_artifact.paths import read_reviewed_draft_merge

    client = _client()
    packet, hashes = _source_merge_ready_packet(client)
    fifo = Path(api_env["arts"]) / "draft-merge-fifo.html"
    os.mkfifo(fifo)
    blocked, outcome = _returns_promptly(lambda: read_reviewed_draft_merge(str(fifo)), fifo)
    assert not blocked, "the draft reader blocked on a FIFO"
    assert REFUSAL in str(outcome.get("error")), outcome
    blocked, outcome = _returns_promptly(
        lambda: _preview(client, {**packet, "draft_merge_path": str(fifo)}, hashes), fifo
    )
    assert not blocked, "the source-merge preflight blocked on a FIFO"
    _assert_refused(outcome["value"])
