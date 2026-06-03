"""Tests for acquisition/arxiv/licenses.py + throttle.py (SPR-02 M2 + M4).

The license mapping is the audit artifact: every row in ``_LICENSE_TABLE``
plus the unknown/missing fallback gets an explicit, non-vacuous assertion.
The load-bearing case is unknown -> gated (deny-by-default) — it is tested
directly, never assumed.

The throttle tests use an injected fake clock so they are deterministic and
never sleep 3 real seconds. The simulated-429 -> banned-until -> batch-pause
path is the load-bearing case there.
"""

from __future__ import annotations

import os
import sys

import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv.licenses import (  # noqa: E402
    license_basis_string,
    resolve_license,
)
from acquisition.arxiv.throttle import (  # noqa: E402
    MIN_REQUEST_SPACING_S,
    ArxivBanned,
    ArxivThrottle,
)
from substrate.books.ingest import _VALID_BOOK_CONTENT_CLASSES  # noqa: E402
from substrate.constants import GATED_DEFAULT_CONTENT_CLASS  # noqa: E402

# ---------------------------------------------------------------------------
# M2: license mapping — servable rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "http://creativecommons.org/licenses/by/4.0/",
        "https://creativecommons.org/licenses/by/4.0/",
        "http://creativecommons.org/licenses/by/3.0/",
    ],
)
def test_cc_by_is_servable(uri):
    r = resolve_license(uri)
    assert r.redistributable is True
    # 2026-05-29 remap: CC-BY is source-declared-open, NOT a §9.10 publisher opt-in.
    assert r.content_class == "source_declared_open"
    assert "CC BY" in r.license_name


def test_cc_by_sa_is_servable():
    r = resolve_license("http://creativecommons.org/licenses/by-sa/4.0/")
    assert r.redistributable is True
    # 2026-05-29 remap: CC-BY-SA is source-declared-open, NOT a §9.10 publisher opt-in.
    assert r.content_class == "source_declared_open"
    assert "BY-SA" in r.license_name


def test_cc0_is_servable():
    r = resolve_license("http://creativecommons.org/publicdomain/zero/1.0/")
    assert r.redistributable is True
    # 2026-05-29 remap: CC0 is a public-domain dedication -> public_domain.
    assert r.content_class == "public_domain"
    assert "CC0" in r.license_name


# ---------------------------------------------------------------------------
# M2: license mapping — gated rows
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "uri",
    [
        "http://creativecommons.org/licenses/by-nc/4.0/",
        "http://creativecommons.org/licenses/by-nc-sa/4.0/",
        "http://creativecommons.org/licenses/by-nc-nd/4.0/",
    ],
)
def test_cc_by_nc_is_gated(uri):
    """The CC-BY-NC* judgment call: NC forbids commercial reuse; Antiek's
    ad-funded serving is commercial -> gated. This MUST NOT be servable."""
    r = resolve_license(uri)
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert "NC" in r.license_name
    assert "commercial" in r.rationale.lower()


def test_cc_by_nd_is_gated():
    r = resolve_license("http://creativecommons.org/licenses/by-nd/4.0/")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_arxiv_nonexclusive_default_is_gated():
    """The most common arXiv license: hosting only, author keeps copyright,
    NO grant to Antiek. The honesty case — arXiv-default is NOT a serve right."""
    r = resolve_license("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS
    assert "non-exclusive" in r.license_name.lower()


def test_all_rights_reserved_is_gated():
    r = resolve_license("All rights reserved")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


# ---------------------------------------------------------------------------
# M2: the load-bearing fallback — unknown / missing -> gated
# ---------------------------------------------------------------------------


def test_unknown_uri_falls_back_to_gated():
    """LOAD-BEARING: an unrecognised URI is NEVER guessed servable."""
    r = resolve_license("http://example.com/some-novel-license/9.9/")
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


@pytest.mark.parametrize("missing", [None, "", "   "])
def test_missing_license_falls_back_to_gated(missing):
    r = resolve_license(missing)
    assert r.redistributable is False
    assert r.content_class == GATED_DEFAULT_CONTENT_CLASS


def test_every_resolution_class_is_a_valid_book_content_class():
    """Whatever the table resolves to MUST be a class the substrate accepts;
    a typo here would otherwise crash register_book at ingest time."""
    sample_uris = [
        "http://creativecommons.org/licenses/by/4.0/",
        "http://creativecommons.org/licenses/by-sa/4.0/",
        "http://creativecommons.org/publicdomain/zero/1.0/",
        "http://creativecommons.org/licenses/by-nc/4.0/",
        "http://creativecommons.org/licenses/by-nd/4.0/",
        "http://arxiv.org/licenses/nonexclusive-distrib/1.0/",
        "totally-unknown",
        None,
    ]
    for uri in sample_uris:
        assert resolve_license(uri).content_class in _VALID_BOOK_CONTENT_CLASSES


# ---------------------------------------------------------------------------
# M2: license_basis audit string
# ---------------------------------------------------------------------------


def test_basis_string_servable_names_license_and_uri():
    r = resolve_license("http://creativecommons.org/licenses/by/4.0/")
    basis = license_basis_string(r)
    assert "CC BY" in basis
    assert "creativecommons.org/licenses/by/4.0" in basis


def test_basis_string_gated_states_why():
    r = resolve_license("http://arxiv.org/licenses/nonexclusive-distrib/1.0/")
    basis = license_basis_string(r)
    assert basis.startswith("GATED")
    assert "nonexclusive-distrib" in basis


def test_basis_string_missing_license_states_why():
    r = resolve_license(None)
    basis = license_basis_string(r)
    assert basis.startswith("GATED")
    assert "no license" in basis.lower()


# ---------------------------------------------------------------------------
# M4: throttle — deterministic fake clock
# ---------------------------------------------------------------------------


class _FakeClock:
    """A controllable monotonic-ish clock. ``sleep`` advances it instead of
    blocking, so >=3s spacing is exercised without a real wait."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _throttle(tmp_path, clock: _FakeClock) -> ArxivThrottle:
    state = tmp_path / "throttle.json"
    return ArxivThrottle(
        state_path=str(state), now=clock.now, sleep=clock.sleep
    )


def test_throttle_first_request_no_wait(tmp_path):
    clock = _FakeClock()
    t = _throttle(tmp_path, clock)
    start = clock.now()
    t.wait_if_needed()
    # First request: no prior timestamp -> no spacing wait.
    assert clock.now() == start


def test_throttle_enforces_min_spacing(tmp_path):
    clock = _FakeClock()
    t = _throttle(tmp_path, clock)
    t.wait_if_needed()  # records now
    # Immediately ask again — the throttle must sleep ~3s (advancing clock).
    before = clock.now()
    t.wait_if_needed()
    assert clock.now() - before >= MIN_REQUEST_SPACING_S


def test_throttle_no_wait_if_already_spaced(tmp_path):
    clock = _FakeClock()
    t = _throttle(tmp_path, clock)
    t.wait_if_needed()
    clock.advance(MIN_REQUEST_SPACING_S + 1.0)  # more than enough elapsed
    before = clock.now()
    t.wait_if_needed()
    assert clock.now() == before  # no extra sleep needed


def test_throttle_state_survives_across_instances(tmp_path):
    """Cross-process simulation: a SECOND throttle reading the SAME state
    file must honor the first's last_request_at (the original bug was
    in-process-only state)."""
    clock = _FakeClock()
    state = tmp_path / "throttle.json"
    t1 = ArxivThrottle(state_path=str(state), now=clock.now, sleep=clock.sleep)
    t1.wait_if_needed()  # writes last_request_at
    # A fresh instance (stand-in for a second shell) reads the same file.
    t2 = ArxivThrottle(state_path=str(state), now=clock.now, sleep=clock.sleep)
    before = clock.now()
    t2.wait_if_needed()
    assert clock.now() - before >= MIN_REQUEST_SPACING_S


def test_429_sets_ban_and_subsequent_request_raises(tmp_path):
    """LOAD-BEARING: a simulated 429 sets banned_until; the next
    wait_if_needed raises ArxivBanned so the batch PAUSES rather than
    re-hitting a banned endpoint."""
    clock = _FakeClock()
    t = _throttle(tmp_path, clock)
    t.wait_if_needed()
    t.note_response(429, headers={})  # no Retry-After -> default backoff
    assert t.is_banned() is True
    with pytest.raises(ArxivBanned):
        t.wait_if_needed()


def test_429_honors_retry_after_header(tmp_path):
    clock = _FakeClock()
    t = ArxivThrottle(
        state_path=str(tmp_path / "s.json"),
        # tiny default so we can prove Retry-After (3600) overrides it
        default_ban_backoff_s=1.0,
        now=clock.now,
        sleep=clock.sleep,
    )
    t.note_response(429, headers={"Retry-After": "3600"})
    assert t.banned_until() >= clock.now() + 3600.0


def test_ban_clears_after_window(tmp_path):
    clock = _FakeClock()
    t = ArxivThrottle(
        state_path=str(tmp_path / "s.json"),
        default_ban_backoff_s=100.0,
        now=clock.now,
        sleep=clock.sleep,
    )
    t.note_response(429, headers={})
    assert t.is_banned() is True
    clock.advance(101.0)  # past the ban window
    assert t.is_banned() is False
    # And a post-ban request no longer raises.
    t.wait_if_needed()


def test_non_429_response_is_noop(tmp_path):
    clock = _FakeClock()
    t = _throttle(tmp_path, clock)
    t.note_response(200, headers={})
    assert t.is_banned() is False
