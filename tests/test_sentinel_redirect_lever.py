"""One lever (``ANTIEK_HOME``) redirects both throttle sentinel files.

SPR-05 arXiv task 5 part A: ``default_state_path()`` in both
``acquisition.arxiv.throttle`` and ``substrate.source_throttle`` honours
``ANTIEK_HOME`` between the per-file override and the ``~/.antiek`` fallback,
so a half-redirected run can no longer write one sentinel to tmp and the other
into the operator's live file. These tests only RESOLVE paths — they never
create, open, or write any file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acquisition.arxiv import rate_governor, throttle
from substrate import source_throttle
from tools import arxiv_verify


def test_antiek_home_redirects_both_sentinel_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTIEK_ARXIV_THROTTLE_PATH", raising=False)
    monkeypatch.delenv("ANTIEK_SOURCE_THROTTLE_PATH", raising=False)
    monkeypatch.delenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", raising=False)
    home = tmp_path / "home"
    monkeypatch.setenv("ANTIEK_HOME", str(home))

    expected_arxiv = str(home / "arxiv_throttle.json")
    assert throttle.default_state_path() == expected_arxiv
    assert source_throttle.default_state_path() == str(home / "source_throttle.json")
    # rate_governor.default_lock_path() derives from default_state_path()
    # and must follow the same lever automatically.
    assert rate_governor.default_lock_path() == expected_arxiv + ".governor.lock"
    # The verifier must read the same file the throttle writes.
    assert arxiv_verify._throttle_path() == expected_arxiv


def test_specific_path_outranks_antiek_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    arxiv = tmp_path / "explicit-arxiv.json"
    source = tmp_path / "explicit-source.json"
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(arxiv))
    monkeypatch.setenv("ANTIEK_SOURCE_THROTTLE_PATH", str(source))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "home"))

    assert throttle.default_state_path() == str(arxiv)
    assert source_throttle.default_state_path() == str(source)


def test_blank_antiek_home_falls_back_to_dot_antiek(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.delenv("ANTIEK_ARXIV_THROTTLE_PATH", raising=False)
    monkeypatch.delenv("ANTIEK_SOURCE_THROTTLE_PATH", raising=False)
    monkeypatch.delenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", raising=False)
    monkeypatch.setenv("ANTIEK_HOME", "   ")
    # HOME must be redirected: with a blank ANTIEK_HOME the fallback is
    # Path.home()/".antiek"/..., and the autouse ``_isolate_arxiv_governor``
    # raises at teardown if that resolves to the operator's real file.
    monkeypatch.setenv("HOME", str(tmp_path))

    assert throttle.default_state_path() == str(
        tmp_path / ".antiek" / "arxiv_throttle.json"
    )
    assert source_throttle.default_state_path() == str(
        tmp_path / ".antiek" / "source_throttle.json"
    )
