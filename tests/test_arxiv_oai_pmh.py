"""Tests for the OAI-PMH ListRecords harvester (SPR-01 M1).

NO live network: the ``httpx.Client`` is a ``MockTransport`` serving a recorded
multi-page resumption-token sequence (the same convention as
``tests/test_open_access_ingest.py``). The harvester is verified to:

  * page through resumption tokens to completion (the live full backfill is the
    SAME code path, run by the operator with a real client);
  * route EVERY HTTP call through the PR#23 persisted throttle (we assert via a
    counting throttle wrapper that wait/note bracket each request);
  * resume from the persisted cursor after a crash mid-harvest rather than
    re-fetching consumed pages;
  * PAUSE (raise ArxivBanned) rather than re-hit a banned endpoint.
"""

from __future__ import annotations

import os
import sys

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from datetime import UTC

from acquisition.arxiv.oai_pmh import OaiPmhHarvester  # noqa: E402
from acquisition.arxiv.throttle import ArxivBanned, ArxivThrottle  # noqa: E402

_NS = 'xmlns="http://www.openarchives.org/OAI/2.0/"'
_ARXIV_BODY_NS = 'xmlns="http://arxiv.org/OAI/arXiv/"'

_CC_BY = "http://creativecommons.org/licenses/by/4.0/"
_ARXIV_DEFAULT = "http://arxiv.org/licenses/nonexclusive-distrib/1.0/"


# ---------------------------------------------------------------------------
# Fixtures: deterministic clock + recorded XML pages
# ---------------------------------------------------------------------------


class _FakeClock:
    """Controllable clock; ``sleep`` advances instead of blocking so >=3s
    spacing is exercised without a real wait. Mirrors test_arxiv_licenses."""

    def __init__(self, start: float = 1000.0) -> None:
        self.t = start

    def now(self) -> float:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += seconds


def _throttle(tmp_path, clock: _FakeClock) -> ArxivThrottle:
    return ArxivThrottle(
        state_path=str(tmp_path / "throttle.json"),
        now=clock.now,
        sleep=clock.sleep,
    )


def _record(arxiv_id: str, datestamp: str, license_uri) -> str:
    lic = f"<license>{license_uri}</license>" if license_uri is not None else ""
    return f"""
      <record>
        <header>
          <identifier>oai:arXiv.org:{arxiv_id}</identifier>
          <datestamp>{datestamp}</datestamp>
        </header>
        <metadata>
          <arXiv {_ARXIV_BODY_NS}>
            <id>{arxiv_id}</id><title>T {arxiv_id}</title>
            <categories>cs.LG</categories>{lic}
          </arXiv>
        </metadata>
      </record>"""


def _page(*records: str, token: str | None = None) -> str:
    rt = f"<resumptionToken>{token}</resumptionToken>" if token else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<OAI-PMH {_NS}>
  <responseDate>2026-05-29T00:00:00Z</responseDate>
  <ListRecords>{''.join(records)}{rt}</ListRecords>
</OAI-PMH>"""


# A three-page harvest: page1 -> token TOK1, page2 -> token TOK2, page3 -> done.
_PAGE_1 = _page(
    _record("2401.0001", "2024-01-01", _CC_BY),
    _record("2401.0002", "2024-01-01", _ARXIV_DEFAULT),
    token="TOK1",
)
_PAGE_2 = _page(
    _record("2401.0003", "2024-01-02", _CC_BY),
    _record("2401.0004", "2024-01-02", None),
    token="TOK2",
)
# Final page: empty <resumptionToken/> is the OAI "last page" signal.
_PAGE_3 = _page(
    _record("2401.0005", "2024-01-03", _CC_BY),
    token=None,
)


def _multi_page_handler(seen_urls: list[str]):
    """A handler that walks the 3-page sequence keyed off the resumptionToken
    in the request URL, recording each URL so the test can assert the protocol
    (first page carries metadataPrefix; later pages carry only the token)."""

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_urls.append(url)
        if "resumptionToken=TOK1" in url:
            return httpx.Response(200, content=_PAGE_2.encode())
        if "resumptionToken=TOK2" in url:
            return httpx.Response(200, content=_PAGE_3.encode())
        return httpx.Response(200, content=_PAGE_1.encode())

    return handler


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), timeout=5.0)


# ---------------------------------------------------------------------------
# M1: paging through resumption tokens to completion
# ---------------------------------------------------------------------------


def test_harvest_pages_through_resumption_tokens_to_completion(tmp_path):
    clock = _FakeClock()
    seen: list[str] = []
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(_multi_page_handler(seen)),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    records = list(h.harvest(from_date="2024-01-01", until_date="2024-01-31"))

    ids = [r.arxiv_id for r in records]
    assert ids == ["2401.0001", "2401.0002", "2401.0003", "2401.0004", "2401.0005"]
    # Three pages were fetched.
    assert len(seen) == 3
    # First page carries metadataPrefix + window; subsequent pages carry ONLY
    # the resumption token (OAI-PMH forbids mixing them).
    assert "metadataPrefix=arXiv" in seen[0]
    assert "from=2024-01-01" in seen[0]
    assert "until=2024-01-31" in seen[0]
    assert "resumptionToken=TOK1" in seen[1] and "metadataPrefix" not in seen[1]
    assert "resumptionToken=TOK2" in seen[2] and "metadataPrefix" not in seen[2]


def test_harvest_clears_state_on_clean_completion(tmp_path):
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(_multi_page_handler([])),
        base_url="https://oai.test/oai2",
        state_path=str(state_path),
    )
    list(h.harvest())
    # A finished harvest leaves no cursor, so the next run starts fresh.
    assert not state_path.exists()


def test_single_page_harvest_no_token(tmp_path):
    clock = _FakeClock()

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_PAGE_3.encode())

    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(handler),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    records = list(h.harvest())
    assert [r.arxiv_id for r in records] == ["2401.0005"]


# ---------------------------------------------------------------------------
# M1: every HTTP call goes through the throttle
# ---------------------------------------------------------------------------


def test_every_page_request_goes_through_the_throttle(tmp_path):
    """The throttle's wait_if_needed must bracket EVERY request — re-implementing
    rate limiting is the bug that banned the box, so we assert the harvester
    calls the throttle once per page (3 pages -> 3 waits)."""
    clock = _FakeClock()
    waits = {"n": 0}
    real = _throttle(tmp_path, clock)
    orig_wait = real.wait_if_needed

    def counting_wait():
        waits["n"] += 1
        orig_wait()

    real.wait_if_needed = counting_wait  # type: ignore[method-assign]

    h = OaiPmhHarvester(
        throttle=real,
        client=_mock_client(_multi_page_handler([])),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    list(h.harvest())
    assert waits["n"] == 3  # one throttle wait per page


def test_throttle_enforces_spacing_between_pages(tmp_path):
    """Across pages the clock advances by >= 3s per inter-page gap (the
    throttle's spacing), proving the harvester does not burst the endpoint."""
    clock = _FakeClock()
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(_multi_page_handler([])),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    start = clock.now()
    list(h.harvest())
    # 3 pages -> 2 enforced inter-page gaps of >=3s (the first request is free).
    assert clock.now() - start >= 2 * 3.0


# ---------------------------------------------------------------------------
# M1: crash mid-harvest resumes from the last token
# ---------------------------------------------------------------------------


def test_crash_mid_harvest_resumes_from_last_token(tmp_path):
    """Simulate a crash after page 2: the cursor file holds TOK2; a FRESH
    harvester resumes by issuing ListRecords with resumptionToken=TOK2 and does
    NOT re-fetch pages 1-2."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"

    # --- run 1: consume pages 1 and 2, then "crash" before page 3. ---
    seen_run1: list[str] = []

    class _Boom(RuntimeError):
        pass

    def handler_run1(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_run1.append(url)
        if "resumptionToken=TOK1" in url:
            return httpx.Response(200, content=_PAGE_2.encode())
        if "resumptionToken=TOK2" in url:
            raise _Boom("network died mid-harvest")  # crash before page 3
        return httpx.Response(200, content=_PAGE_1.encode())

    h1 = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(handler_run1),
        base_url="https://oai.test/oai2",
        state_path=str(state_path),
    )
    got_run1 = []
    with pytest.raises(_Boom):
        for rec in h1.harvest():
            got_run1.append(rec.arxiv_id)

    # Pages 1+2 were consumed; the persisted cursor points at TOK2.
    assert got_run1 == ["2401.0001", "2401.0002", "2401.0003", "2401.0004"]
    assert state_path.exists()

    # --- run 2: a fresh harvester resumes from the saved cursor. ---
    seen_run2: list[str] = []

    def handler_run2(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen_run2.append(url)
        if "resumptionToken=TOK2" in url:
            return httpx.Response(200, content=_PAGE_3.encode())
        raise AssertionError(f"resume must start at TOK2, got {url}")

    h2 = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(handler_run2),
        base_url="https://oai.test/oai2",
        state_path=str(state_path),
    )
    got_run2 = [rec.arxiv_id for rec in h2.harvest()]

    # Resumed at TOK2 -> only page 3, with no re-fetch of pages 1-2.
    assert got_run2 == ["2401.0005"]
    assert len(seen_run2) == 1
    assert "resumptionToken=TOK2" in seen_run2[0]
    # And the completed harvest cleared the cursor.
    assert not state_path.exists()


def test_resume_false_ignores_persisted_cursor(tmp_path):
    """An explicit resume=False starts a fresh window even if a cursor file is
    present (the operator can force a clean re-harvest)."""
    clock = _FakeClock()
    state_path = tmp_path / "harvest.json"
    state_path.write_text('{"resumption_token": "STALE", "last_datestamp": "2024-01-02"}')

    seen: list[str] = []
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(_multi_page_handler(seen)),
        base_url="https://oai.test/oai2",
        state_path=str(state_path),
    )
    list(h.harvest(resume=False))
    # First request is a fresh metadataPrefix page, NOT the stale token.
    assert "metadataPrefix=arXiv" in seen[0]
    assert "resumptionToken=STALE" not in seen[0]


# ---------------------------------------------------------------------------
# M1: ban handling — PAUSE rather than re-hit
# ---------------------------------------------------------------------------


def test_active_ban_raises_before_any_request(tmp_path):
    """A pre-existing ban sentinel makes the very first page raise ArxivBanned
    from inside the throttle — the harvester never issues the request."""
    clock = _FakeClock()
    throttle = _throttle(tmp_path, clock)
    throttle.note_response(429, headers={"Retry-After": "3600"})  # set the ban

    seen: list[str] = []
    h = OaiPmhHarvester(
        throttle=throttle,
        client=_mock_client(_multi_page_handler(seen)),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    with pytest.raises(ArxivBanned):
        list(h.harvest())
    assert seen == []  # not a single request was issued while banned


def test_429_mid_harvest_sets_ban_then_resume_pauses(tmp_path):
    """Two-phase, the whole point of reusing the PR#23 throttle:

    (1) a 429 on page 2 surfaces as HTTPStatusError AND the throttle records the
        ban sentinel from the Retry-After (inside ``request`` -> note_response);
    (2) a SUBSEQUENT harvest then raises ArxivBanned BEFORE issuing any request
        — the harvest PAUSES instead of re-hitting the banned endpoint (the bug
        that originally IP-banned the box).
    """
    clock = _FakeClock()
    throttle = _throttle(tmp_path, clock)

    def handler(req: httpx.Request) -> httpx.Response:
        if "resumptionToken=TOK1" in str(req.url):
            return httpx.Response(429, headers={"Retry-After": "3600"})
        return httpx.Response(200, content=_PAGE_1.encode())

    h = OaiPmhHarvester(
        throttle=throttle,
        client=_mock_client(handler),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )

    # Phase 1: page 1 is consumed, page 2 429s.
    got = []
    with pytest.raises(httpx.HTTPStatusError) as exc:
        for rec in h.harvest():
            got.append(rec.arxiv_id)
    assert exc.value.response.status_code == 429
    assert got == ["2401.0001", "2401.0002"]
    assert throttle.is_banned() is True

    # Phase 2: the ban is honored — a re-run raises before any HTTP call.
    requests_made = []
    h._client = _mock_client(  # rebind to a tripwire client
        lambda req: requests_made.append(str(req.url)) or httpx.Response(200)
    )
    with pytest.raises(ArxivBanned):
        list(h.harvest())
    assert requests_made == []  # paused — not one re-hit while banned


# ---------------------------------------------------------------------------
# M1 + census: the full harvest folds into a reproducible census
# ---------------------------------------------------------------------------


def test_harvest_census_pages_and_partitions(tmp_path):
    from datetime import datetime

    clock = _FakeClock()
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=_mock_client(_multi_page_handler([])),
        base_url="https://oai.test/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    census = h.harvest_census(
        from_date="2024-01-01",
        until_date="2024-01-31",
        harvested_at=datetime(2026, 5, 29, tzinfo=UTC),
    )
    # 5 records across 3 pages: 3 CC-BY (T1), 1 arxiv-default (T3),
    # 1 absent-license (T3 + ambiguous).
    assert census.total == 5
    assert census.t1 == 3
    assert census.t3 == 2
    assert census.ambiguous == 1
    assert census.metadata_prefix == "arXiv"
    assert census.from_date == "2024-01-01"
    assert census.t1 + census.t2 + census.t3 == census.total


# ---------------------------------------------------------------------------
# 2026-08 upstream endpoint move: export.arxiv.org/oai2 → oaipmh.arxiv.org/oai
# ---------------------------------------------------------------------------


def test_default_oai_base_url_is_canonical_oaipmh():
    from acquisition.arxiv import oai_pmh

    assert oai_pmh.DEFAULT_OAI_BASE_URL == "https://oaipmh.arxiv.org/oai"


def test_harvest_follows_301_redirect_to_oaipmh(tmp_path):
    """The nightly sync must survive arXiv's 301 from export.arxiv.org/oai2
    (the historical default) to oaipmh.arxiv.org/oai — a stale base_url or a
    future upstream move must not silently kill the harvest."""
    clock = _FakeClock()
    seen: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        url = str(req.url)
        seen.append(url)
        if "export.arxiv.org" in url:
            new_url = url.replace("export.arxiv.org/oai2", "oaipmh.arxiv.org/oai")
            return httpx.Response(301, headers={"Location": new_url}, request=req)
        if "resumptionToken=TOK1" in url:
            return httpx.Response(200, content=_PAGE_3.encode())
        return httpx.Response(200, content=_PAGE_1.encode())

    client = httpx.Client(
        transport=httpx.MockTransport(handler),
        timeout=5.0,
        follow_redirects=True,
    )
    h = OaiPmhHarvester(
        throttle=_throttle(tmp_path, clock),
        client=client,
        base_url="https://export.arxiv.org/oai2",
        state_path=str(tmp_path / "harvest.json"),
    )
    records = list(h.harvest(from_date="2024-01-01", until_date="2024-01-31"))

    assert [r.arxiv_id for r in records] == ["2401.0001", "2401.0002", "2401.0005"]
    # Every page request was 301-redirected from the legacy host to the
    # canonical oaipmh host (4 hops: 2 pages × initial + redirect target).
    assert len(seen) == 4
    assert "export.arxiv.org/oai2" in seen[0] and "oaipmh.arxiv.org/oai" in seen[1]
    assert "export.arxiv.org/oai2" in seen[2] and "oaipmh.arxiv.org/oai" in seen[3]
