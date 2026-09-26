"""atomic_write_nofollow closes every descriptor on every failure path.

The write-error cleanup unlinked the temp file and then closed the parent
directory's descriptor; if that unlink raised anything but FileNotFoundError
(a permission change, say), the close never ran and each failed write leaked a
descriptor (codex, on #3432). A cleanup failure must also not replace the
error that caused it. Closing the temp file is part of the same contract
(codex, on this PR): a close error never replaces the write error, and a
close that fails after a good write still removes the temp and publishes
nothing.
"""

from __future__ import annotations

import os

import pytest

from substrate.research_artifact import paths


def _open_fds() -> int:
    return len(os.listdir("/dev/fd"))


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    root = tmp_path / "artifacts"
    root.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(root))
    return root


def test_a_normal_write_publishes_and_leaves_no_temp(artifacts):
    paths.atomic_write_nofollow(artifacts / "a.html", b"hello")
    assert (artifacts / "a.html").read_bytes() == b"hello"
    assert [p.name for p in artifacts.iterdir()] == ["a.html"]


def test_a_failed_write_whose_cleanup_also_fails_leaks_nothing(artifacts, monkeypatch):
    real_unlink = os.unlink

    def failing_write(fd, data):
        raise OSError(28, "No space left on device")

    def failing_unlink(name, *args, **kwargs):
        if str(name).endswith(".tmp"):
            raise PermissionError(13, "Permission denied")
        return real_unlink(name, *args, **kwargs)

    monkeypatch.setattr(paths.os, "write", failing_write)
    monkeypatch.setattr(paths.os, "unlink", failing_unlink)
    before = _open_fds()
    for _ in range(20):
        with pytest.raises(OSError) as err:
            paths.atomic_write_nofollow(artifacts / "b.html", b"x")
        # The write failure is what surfaces, not the cleanup's.
        assert err.value.errno == 28
    assert _open_fds() == before


def test_a_failed_publish_whose_cleanup_also_fails_leaks_nothing(artifacts, monkeypatch):
    real_unlink = os.unlink

    def failing_replace(*args, **kwargs):
        raise OSError(18, "Invalid cross-device link")

    def failing_unlink(name, *args, **kwargs):
        if str(name).endswith(".tmp"):
            raise PermissionError(13, "Permission denied")
        return real_unlink(name, *args, **kwargs)

    monkeypatch.setattr(paths.os, "replace", failing_replace)
    monkeypatch.setattr(paths.os, "unlink", failing_unlink)
    before = _open_fds()
    for _ in range(20):
        with pytest.raises(OSError) as err:
            paths.atomic_write_nofollow(artifacts / "c.html", b"x")
        assert err.value.errno == 18
    assert _open_fds() == before


def _temp_close_fails(monkeypatch) -> None:
    """Closing a temp file's descriptor really closes it, then reports EIO.

    Only descriptors opened on a ``.tmp`` name fail, so the parent
    directory's close (and anything else) behaves normally, and the real
    close always runs, so the test leaks no descriptor of its own."""
    real_open, real_close = os.open, os.close
    temp_fds: set[int] = set()

    def tracking_open(name, *args, **kwargs):
        fd = real_open(name, *args, **kwargs)
        if str(name).endswith(".tmp"):
            temp_fds.add(fd)
        return fd

    def failing_close(fd):
        real_close(fd)
        if fd in temp_fds:
            temp_fds.discard(fd)
            raise OSError(5, "Input/output error")

    monkeypatch.setattr(paths.os, "open", tracking_open)
    monkeypatch.setattr(paths.os, "close", failing_close)


def test_a_failed_close_after_a_failed_write_keeps_the_write_error(artifacts, monkeypatch):
    def failing_write(fd, data):
        raise OSError(28, "No space left on device")

    _temp_close_fails(monkeypatch)
    monkeypatch.setattr(paths.os, "write", failing_write)
    before = _open_fds()
    for _ in range(20):
        with pytest.raises(OSError) as err:
            paths.atomic_write_nofollow(artifacts / "d.html", b"x")
        # The write failure is what surfaces, not the close's.
        assert err.value.errno == 28
    assert _open_fds() == before
    assert list(artifacts.iterdir()) == []


def test_a_failed_close_after_a_good_write_publishes_nothing(artifacts, monkeypatch):
    (artifacts / "e.html").write_bytes(b"before")
    _temp_close_fails(monkeypatch)
    before = _open_fds()
    for _ in range(20):
        with pytest.raises(OSError) as err:
            paths.atomic_write_nofollow(artifacts / "e.html", b"after")
        assert err.value.errno == 5
    assert _open_fds() == before
    # The temp is gone and the target still holds what it held before.
    assert [p.name for p in artifacts.iterdir()] == ["e.html"]
    assert (artifacts / "e.html").read_bytes() == b"before"
