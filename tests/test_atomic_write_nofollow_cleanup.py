"""atomic_write_nofollow closes every descriptor on every failure path.

The write-error cleanup unlinked the temp file and then closed the parent
directory's descriptor; if that unlink raised anything but FileNotFoundError
(a permission change, say), the close never ran and each failed write leaked a
descriptor (codex, on #3432). A cleanup failure must also not replace the
error that caused it.
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
