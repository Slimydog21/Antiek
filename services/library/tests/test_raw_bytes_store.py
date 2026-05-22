"""Tests for the content-addressed raw bytes store."""

from __future__ import annotations

import hashlib
import os
import sys

import pytest

_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)


@pytest.fixture()
def antiek_home(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    return tmp_path


def test_store_returns_path_and_sha(antiek_home):
    from services.library.raw_bytes_store import store_bytes
    path, sha = store_bytes(b"hello world", ext="pdf")
    assert sha == hashlib.sha256(b"hello world").hexdigest()
    assert sha in path
    assert path.endswith(".pdf")
    assert os.path.exists(path)


def test_store_is_idempotent_on_same_bytes(antiek_home):
    from services.library.raw_bytes_store import store_bytes
    p1, s1 = store_bytes(b"same content", ext="pdf")
    p2, s2 = store_bytes(b"same content", ext="pdf")
    assert p1 == p2
    assert s1 == s2


def test_different_bytes_get_different_paths(antiek_home):
    from services.library.raw_bytes_store import store_bytes
    p1, _ = store_bytes(b"alpha", ext="pdf")
    p2, _ = store_bytes(b"beta", ext="pdf")
    assert p1 != p2


def test_load_returns_original_bytes(antiek_home):
    from services.library.raw_bytes_store import store_bytes, load_bytes
    path, _ = store_bytes(b"original payload", ext="pdf")
    assert load_bytes(path) == b"original payload"


def test_load_raises_on_disk_corruption(antiek_home):
    from services.library.raw_bytes_store import store_bytes, load_bytes, IntegrityError
    path, _ = store_bytes(b"clean", ext="pdf")
    # Corrupt the file in place.
    with open(path, "wb") as f:
        f.write(b"corrupted")
    with pytest.raises(IntegrityError):
        load_bytes(path)


def test_overwrite_on_corruption_during_store(antiek_home):
    """If a stored blob's hash is wrong (disk corruption), a re-store
    of the correct bytes overwrites it."""
    from services.library.raw_bytes_store import store_bytes, load_bytes
    path, _ = store_bytes(b"good", ext="pdf")
    with open(path, "wb") as f:
        f.write(b"corrupted")
    # Re-store the correct bytes — should overwrite.
    path2, _ = store_bytes(b"good", ext="pdf")
    assert path == path2
    assert load_bytes(path) == b"good"


def test_directory_sharding(antiek_home):
    from services.library.raw_bytes_store import store_bytes
    path, sha = store_bytes(b"shard test", ext="pdf")
    # The blob should live under <root>/<sha[:2]>/.
    assert f"/{sha[:2]}/" in path


def test_iter_stored_hashes(antiek_home):
    from services.library.raw_bytes_store import store_bytes, iter_stored_hashes
    store_bytes(b"a", ext="pdf")
    store_bytes(b"b", ext="pdf")
    store_bytes(b"c", ext="pdf")
    stored = iter_stored_hashes()
    assert len(stored) == 3
    expected = {
        hashlib.sha256(x).hexdigest() for x in (b"a", b"b", b"c")
    }
    assert set(stored) == expected
