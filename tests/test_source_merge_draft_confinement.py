"""A source merge may only splice a draft this server wrote into a book.

The reviewed packet carried ``draft_merge_path`` from the client, and
``source_merge._read_reviewed_draft`` once read whatever file it named. Preview
answered with that file's size and hash (and a different error when it did not
exist), and commit spliced its contents into the source document's body, where
the reader serves it: any file the server process can read, such as
``~/.antiek/secrets.env``, could be copied into a book. The draft must be a
regular ``draft-merge-*.html`` file directly inside the research artifacts
directory, reached without a symlink or ``..``, and every other value is refused
with the same answer whether or not the file exists.

The preview, apply and commit routes are retired and answer 410 without reading
anything (``test_source_merge_retired.py``): under ruling T6 a merge never
writes the source, so no HTTP path reaches this reader any more. The guard is
still tested here, on ``read_reviewed_draft_merge`` and the substrate preview and
commit functions, because that substrate code stays until a follow-up deletes
it (restore still depends on the commit receipts it wrote), and any caller that
reaches it again must meet a confined reader. ``apply_source_merge_review``
never reads the draft, it records the path string, so it has nothing to confine.
"""

from __future__ import annotations

import contextlib
import os
from pathlib import Path

import pytest
from test_artifact_routes import (  # noqa: F401  (fixture)
    _client,
    _source_merge_preview_evidence,
    _source_merge_ready_packet,
    api_env,
)

from runtime.db_lock import connect_write
from substrate.research_artifact import source_merge
from substrate.research_artifact.paths import read_reviewed_draft_merge
from substrate.research_artifact.source_merge import (
    commit_source_merge_review,
    preview_source_merge_review,
)

SECRET = "ANTIEK_SECRET_TOKEN=do-not-exfiltrate"
REFUSAL = "source_merge_draft_merge_path_invalid"


def _secret_file(api_env) -> Path:  # noqa: F811
    secret = Path(api_env["arts"]).parent / "secrets.env"
    secret.write_text(SECRET + "\n")
    return secret


def _preview(packet: dict, hashes: dict[str, str], draft_merge_path: str):
    """The substrate preview the retired preview route called, on the path given."""
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/confined_preview") as con:
        return preview_source_merge_review(
            con,
            document_id=packet["document_id"],
            draft_merge_path=draft_merge_path,
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=hashes,
            hash_conflicts=packet["hash_conflicts"],
        )


def _source_body() -> str:
    with connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/source_body") as con:
        (raw,) = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", ["doc-source-merge"]
        ).fetchone()
    return raw


def _variants(api_env) -> dict[str, str]:  # noqa: F811
    arts = Path(api_env["arts"])
    arts.mkdir(parents=True, exist_ok=True)
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
def test_the_reader_refuses_a_draft_path_the_server_did_not_write(api_env, variant):  # noqa: F811
    with pytest.raises(ValueError, match=REFUSAL) as refused:
        read_reviewed_draft_merge(_variants(api_env)[variant])
    assert SECRET not in str(refused.value)


def test_the_substrate_preview_refuses_a_file_outside_the_artifacts_dir(api_env):  # noqa: F811
    packet, hashes = _source_merge_ready_packet(_client())
    with pytest.raises(ValueError, match=REFUSAL):
        _preview(packet, hashes, str(_secret_file(api_env)))


def test_the_substrate_commit_cannot_splice_a_file_outside_the_artifacts_dir_into_the_book(api_env):  # noqa: F811
    # The attacker's flow: bind the commit to a preview of the real draft, then
    # name the secret. The refusal must come from the confined read, not from a
    # binding mismatch that a matching preview could get past.
    packet, hashes = _source_merge_ready_packet(_client())
    evidence = _source_merge_preview_evidence(packet, hashes)
    with (
        connect_write(os.environ["ANTIEK_DUCKDB_PATH"], purpose="test/confined_commit") as con,
        pytest.raises(ValueError, match=REFUSAL),
    ):
        commit_source_merge_review(
            con,
            document_id=packet["document_id"],
            parent_reading_thread_id=packet["parent_reading_thread_id"],
            draft_merge_path=str(_secret_file(api_env)),
            compose_index_path=packet["compose_index_path"],
            member_investigation_ids=packet["member_investigation_ids"],
            expected_content_hashes=hashes,
            hash_conflicts=packet["hash_conflicts"],
            expected_source_revision_id=evidence["source_revision_id"],
            expected_twin_revision_id=evidence["twin_revision_id"],
            expected_before_source_hash=evidence["before_source_hash"],
            expected_after_source_hash=evidence["after_source_hash"],
            expected_before_twin_hash=evidence["before_twin_hash"],
            expected_after_twin_hash=evidence["after_twin_hash"],
            operator_reviewer="pytest",
        )
    assert SECRET not in _source_body()
    assert _source_body() == "Original source book body."


def test_a_missing_path_and_a_present_one_are_refused_alike(api_env):  # noqa: F811
    # No existence oracle: the answer must not depend on whether the file is there.
    packet, hashes = _source_merge_ready_packet(_client())
    present = _secret_file(api_env)
    absent = present.with_name("absent.env")
    assert not absent.exists()

    def refusal(read) -> tuple[type, str]:
        with pytest.raises(ValueError) as refused:
            read()
        return type(refused.value), str(refused.value)

    for path in (present, absent):
        assert refusal(lambda p=path: read_reviewed_draft_merge(str(p))) == (ValueError, REFUSAL)
        assert refusal(lambda p=path: _preview(packet, hashes, str(p))) == (ValueError, REFUSAL)


def test_the_draft_the_server_composed_is_accepted(api_env):  # noqa: F811
    # Positive control: the confinement admits exactly what compose wrote.
    packet, hashes = _source_merge_ready_packet(_client())
    draft = packet["draft_merge_path"]
    assert Path(draft).name.startswith("draft-merge-")
    text = read_reviewed_draft_merge(draft)
    assert "Source merge A" in text
    assert "Source merge B" in text
    preview = _preview(packet, hashes, draft)
    assert preview.status == "previewed"
    assert preview.writes_performed is False


def test_a_draft_swapped_for_a_symlink_after_validation_is_not_read(api_env):  # noqa: F811
    # A caller validates the draft, then the substrate reads it. Replacing the
    # draft with a symlink between the two must not reach the target: the read
    # itself refuses a symlink, it does not rely on the earlier check.
    packet, hashes = _source_merge_ready_packet(_client())
    draft = Path(packet["draft_merge_path"])
    read_reviewed_draft_merge(str(draft))
    draft.unlink()
    draft.symlink_to(_secret_file(api_env))
    with pytest.raises(ValueError, match=REFUSAL) as refused:
        _preview(packet, hashes, str(draft))
    assert SECRET not in str(refused.value)


def test_a_relative_artifacts_dir_still_reads_its_own_draft(api_env, monkeypatch, tmp_path):  # noqa: F811
    # Compose returns a relative draft path when the artifacts directory is
    # configured relative; the confinement must read it the same way.
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", "relative-artifacts")
    packet, hashes = _source_merge_ready_packet(_client())
    assert not os.path.isabs(packet["draft_merge_path"])
    assert "Source merge A" in read_reviewed_draft_merge(packet["draft_merge_path"])
    assert _preview(packet, hashes, packet["draft_merge_path"]).status == "previewed"


def test_a_draft_swapped_right_after_the_readers_first_access_is_not_read(api_env, monkeypatch):  # noqa: F811
    # The race inside the reader: once its first filesystem access to the draft
    # completes, the draft is replaced by a symlink to another file. A reader
    # that checks and then reopens by name follows the symlink; one that reads
    # from the descriptor it opened cannot.
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
    packet, hashes = _source_merge_ready_packet(_client())
    fifo = Path(api_env["arts"]) / "draft-merge-fifo.html"
    os.mkfifo(fifo)
    blocked, outcome = _returns_promptly(lambda: read_reviewed_draft_merge(str(fifo)), fifo)
    assert not blocked, "the draft reader blocked on a FIFO"
    assert REFUSAL in str(outcome.get("error")), outcome
    blocked, outcome = _returns_promptly(lambda: _preview(packet, hashes, str(fifo)), fifo)
    assert not blocked, "the substrate preview blocked on a FIFO"
    assert REFUSAL in str(outcome.get("error")), outcome
