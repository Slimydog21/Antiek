"""Red-proofs for the aggregator PDF fetch in ``tools/run_corpus_ingest.py``.

``_fetch_paper_pdf`` fetches ``rec.pdf_url``, which is resolved at runtime from
CORE / Semantic Scholar / bioRxiv / PLOS metadata. All of those aggregators
mirror arXiv, so that URL can be ``https://arxiv.org/pdf/<id>`` on the initial
hop or after a redirect. It used to build a bare ``httpx.Client``, which made it
an ungoverned arXiv egress sitting on a live ingest loop — in ``tools/``, which
the rate-governor lint did not scan. arXiv bans by IP, so one ungoverned loop
bans the whole host.

No network: every request is served by an ``httpx.MockTransport``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from acquisition.arxiv import rate_governor  # noqa: E402
from acquisition.books.public_domain import text_to_pdf  # noqa: E402
from tools.run_corpus_ingest import _fetch_paper_pdf  # noqa: E402

_PDF_BYTES = text_to_pdf("A synthetic open-access paper body. " * 40, title="P")


class _Rec:
    def __init__(self, pdf_url: str) -> None:
        self.pdf_url = pdf_url


class _NoopThrottle:
    """The aggregator's SourceThrottle, reduced to the two methods
    ``_fetch_paper_pdf`` calls. Its budget is a different concern from the
    host-global arXiv gate under test here."""

    def __init__(self) -> None:
        self.before: list[str] = []
        self.noted: list[tuple[str, int]] = []

    def before_request(self, key: str) -> None:
        self.before.append(key)

    def note_response(
        self, key: str, status: int, headers: dict, *, url: str | None = None
    ) -> None:
        self.noted.append((key, status))


@pytest.fixture
def isolated_governor_state(tmp_path, monkeypatch):
    """Point the canonical throttle + governor flock at tmp_path, and clear the
    cached canonical throttle so it is rebuilt against these paths."""
    state = tmp_path / "arxiv_throttle.json"
    monkeypatch.setenv("ANTIEK_ARXIV_THROTTLE_PATH", str(state))
    monkeypatch.setenv("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH", str(tmp_path / "gov.lock"))
    monkeypatch.setattr(rate_governor, "_CANONICAL_THROTTLE", None, raising=False)
    return state


@pytest.fixture
def spy_governed_client(monkeypatch):
    """Wrap the real ``arxiv_governed_client`` factory so the test can inspect
    the client that ``_fetch_paper_pdf`` actually used, and serve its requests
    from a MockTransport instead of the network."""
    captured: list[httpx.Client] = []
    seen_urls: list[str] = []
    real = rate_governor.arxiv_governed_client

    def handler(request: httpx.Request) -> httpx.Response:
        seen_urls.append(str(request.url))
        return httpx.Response(
            200, content=_PDF_BYTES, headers={"content-type": "application/pdf"}
        )

    def factory(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        client = real(**kwargs)
        captured.append(client)
        return client

    monkeypatch.setattr(rate_governor, "arxiv_governed_client", factory)
    return {"clients": captured, "urls": seen_urls}


def test_fetch_paper_pdf_uses_a_governed_client(
    isolated_governor_state, spy_governed_client
):
    """The fetch is built by ``arxiv_governed_client``, and the client it hands
    back carries the per-hop request AND response governance hooks — the pair
    that holds an arXiv hop under the host-global flock and records a 429 into
    the ban sentinel. Asserting on the hooks, not just on the factory call,
    is what makes this a proof rather than a spelling check."""
    throttle = _NoopThrottle()
    rec = _Rec("https://arxiv.org/pdf/2402.03300")

    content = _fetch_paper_pdf(rec, throttle=throttle, source="core")

    assert content == _PDF_BYTES
    assert len(spy_governed_client["clients"]) == 1, "no governed client was built"
    client = spy_governed_client["clients"][0]
    assert getattr(client, "_antiek_arxiv_hooked", False) is True
    assert client.event_hooks.get("request"), "no per-hop request governance hook"
    assert client.event_hooks.get("response"), "no per-hop response (429) hook"
    # The aggregator's own throttle is still consulted — the two layers coexist.
    assert throttle.before == ["core"]


def test_fetch_paper_pdf_governs_an_arxiv_url_through_the_shared_state(
    isolated_governor_state, spy_governed_client
):
    """Behavioral proof, not shape: fetching an arXiv-host pdf_url writes the
    SHARED throttle state, which is what serializes this fetch against every
    other arXiv job on the box."""
    assert not isolated_governor_state.exists()

    _fetch_paper_pdf(
        _Rec("https://arxiv.org/pdf/2402.03300"),
        throttle=_NoopThrottle(),
        source="semantic_scholar",
    )

    assert isolated_governor_state.exists(), (
        "an arXiv-host fetch did not touch the host-global throttle state — "
        "it was not governed"
    )
    import json

    assert json.loads(isolated_governor_state.read_text())["last_request_at"] > 0


def test_fetch_paper_pdf_does_not_falsely_govern_a_non_arxiv_url(
    isolated_governor_state, spy_governed_client
):
    """The control. A publisher-host PDF must NOT take the arXiv flock: false
    governance would serialize unrelated open-access fetches behind arXiv's
    3-second spacing and make the ingest loop crawl for no reason."""
    _fetch_paper_pdf(
        _Rec("https://example.org/article/1.pdf"),
        throttle=_NoopThrottle(),
        source="plos",
    )

    assert not isolated_governor_state.exists(), (
        "a non-arXiv fetch touched the arXiv throttle state — false governance"
    )


def test_fetch_paper_pdf_records_a_429_from_an_arxiv_hop_in_the_ban_sentinel(
    isolated_governor_state, monkeypatch
):
    """A 429 from the arXiv hop must arm the ban sentinel through the response
    hook, so the NEXT arXiv request anywhere on this box refuses before
    egressing. Without the governed client this 429 was invisible to the
    host-global state."""
    import json

    real = rate_governor.arxiv_governed_client

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "600"})

    def factory(**kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return real(**kwargs)

    monkeypatch.setattr(rate_governor, "arxiv_governed_client", factory)

    with pytest.raises(httpx.HTTPStatusError):
        _fetch_paper_pdf(
            _Rec("https://arxiv.org/pdf/2402.03300"),
            throttle=_NoopThrottle(),
            source="core",
        )

    state = json.loads(Path(isolated_governor_state).read_text())
    assert state["banned_until"] > 0, "the 429 did not arm the host-global ban sentinel"
