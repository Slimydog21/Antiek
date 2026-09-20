"""Tests for acquisition.arxiv.ids — robust version split + error-feed detection.

Guards the fix for the fragile ``full_id.split("v")[0]`` id parse and the new
error-feed trap, both aligned with the ~/.claude/skills/arxiv contract.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.ids import (  # noqa: E402
    is_valid_arxiv_id,
    looks_like_error_feed,
    normalize_arxiv_id,
    split_id_version,
    strip_version,
)


@pytest.mark.parametrize(
    ("full", "base", "ver"),
    [
        ("2402.03300v2", "2402.03300", "v2"),
        ("2402.03300", "2402.03300", ""),
        ("2402.03300v12", "2402.03300", "v12"),
        ("1706.03762", "1706.03762", ""),
        # Old-style ids: no version, and NOT truncated at an internal char.
        ("hep-th/0601001", "hep-th/0601001", ""),
        ("hep-th/0601001v3", "hep-th/0601001", "v3"),
        ("math.AG/0512001", "math.AG/0512001", ""),
        ("cond-mat/0102536v1", "cond-mat/0102536", "v1"),
    ],
)
def test_split_id_version(full, base, ver):
    assert split_id_version(full) == (base, ver)
    assert strip_version(full) == base


def test_split_never_truncates_at_internal_v():
    # The old split("v")[0] would have cut this at the archive-name boundary if a
    # 'v' appeared; the anchored regex keeps the base whole.
    assert split_id_version("nlin/0605001v2") == ("nlin/0605001", "v2")


@pytest.mark.parametrize(
    ("cid", "ok"),
    [
        ("2402.03300", True),
        ("2402.033000", False),  # too many digits
        ("hep-th/0601001", True),
        ("math.AG/0512001", True),
        ("hep-th/060100", False),  # 6 digits, not 7
        ("not-an-id", False),
        ("2402.03300v2", False),  # version must be stripped before validation
        ("", False),
    ],
)
def test_is_valid_arxiv_id(cid, ok):
    assert is_valid_arxiv_id(cid) is ok


@pytest.mark.parametrize(
    ("raw", "base", "ver"),
    [
        ("arxiv:2402.03300v2", "2402.03300", "v2"),
        ("https://arxiv.org/abs/2402.03300v2", "2402.03300", "v2"),
        ("https://arxiv.org/pdf/2402.03300", "2402.03300", ""),
        ("https://arxiv.org/html/2402.03300v1", "2402.03300", "v1"),
        ("http://arxiv.org/pdf/2402.03300.pdf", "2402.03300", ""),
    ],
)
def test_normalize_from_urls(raw, base, ver):
    assert normalize_arxiv_id(raw) == (base, ver)


def test_normalize_validates():
    with pytest.raises(ValueError, match="well-formed"):
        normalize_arxiv_id("garbage-id", validate=True)
    # validate=False tolerates a non-canonical base (still splits the version)
    assert normalize_arxiv_id("garbage-id", validate=False) == ("garbage-id", "")


def test_looks_like_error_feed():
    assert looks_like_error_feed("http://arxiv.org/api/errors#incorrect_id_format")
    assert not looks_like_error_feed("http://arxiv.org/abs/2402.03300v2")
    assert not looks_like_error_feed("")
