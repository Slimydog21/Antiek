"""Private immutable note objects reject substitution and unbounded reads."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from substrate.research_artifact import note_store as store


@pytest.fixture(autouse=True)
def isolated_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))


def test_utf8_publish_reuse_and_no_clobber() -> None:
    with store.note_import_lock("inv"):
        digest, path, size = store.publish_note("inv", "Résumé العربية")
        assert size == len("Résumé العربية".encode())
        assert store.read_note("inv", digest, size) == "Résumé العربية"
        assert store.publish_note("inv", "Résumé العربية") == (digest, path, size)
        path.write_bytes(b"corrupt")
        with pytest.raises(store.NotePersistenceError):
            store.publish_note("inv", "Résumé العربية")
        assert path.read_bytes() == b"corrupt"
    assert not list(path.parent.glob("*.tmp"))


@pytest.mark.parametrize("part", ["root", "notes", "investigation", "leaf"])
def test_symlink_components_rejected(tmp_path: Path, part: str) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    root = tmp_path / "artifacts"
    digest = hashlib.sha256(b"secret").hexdigest()
    target = root if part == "root" else root / "notes"
    if part == "investigation":
        target = root / "notes" / "inv"
    elif part == "leaf":
        target = root / "notes" / "inv" / f"{digest}.txt"
        outside = outside / "secret.txt"
        outside.write_bytes(b"secret")
        outside.chmod(0o600)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside)
    with pytest.raises(store.NotePersistenceError):
        store.read_note("inv", digest, 6)
    with pytest.raises(store.NotePersistenceError), store.note_import_lock("inv"):
        store.publish_note("inv", "secret")
    if part == "leaf":
        assert outside.read_bytes() == b"secret"


@pytest.mark.parametrize("damage", ["hardlink", "fifo", "utf8", "whitespace", "oversize"])
def test_invalid_objects_reject_without_blocking(tmp_path: Path, damage: str) -> None:
    data = b"\xff" if damage == "utf8" else b" note " if damage == "whitespace" else b"note"
    digest = hashlib.sha256(data).hexdigest()
    path = store.note_path("inv", digest)
    path.parent.mkdir(parents=True)
    if damage == "fifo":
        os.mkfifo(path, 0o600)
    else:
        path.write_bytes(data)
        path.chmod(0o600)
    if damage == "hardlink":
        os.link(path, tmp_path / "second-link")
    size = store.MAX_NOTE_BYTES + 1 if damage == "oversize" else len(data)
    with pytest.raises(store.NotePersistenceError):
        store.read_note("inv", digest, size)


@pytest.mark.parametrize("iid,digest", [("../escape", "a" * 64), ("inv", "../escape"), ("inv", "a" * 16)])
def test_storage_identity_validation(iid: str, digest: str) -> None:
    with pytest.raises(store.NotePersistenceError):
        store.note_path(iid, digest)
