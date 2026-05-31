"""Wikisource connector tests (SPR-06 M3). No live network."""

from __future__ import annotations

from acquisition.books import wikisource
from acquisition.books.pd_connector_base import classify_and_ingest

from .conftest import FakeFetcher, book_asset_row

API = wikisource.API_URL

_BODY_WIKITEXT = (
    "{{header | title=On the Origin of Species | author=Charles Darwin}}\n"
    "When on board H.M.S. Beagle, as naturalist, I was much struck with "
    "certain facts in the distribution of the inhabitants of South America. "
    "<ref>a footnote that must be stripped</ref>\n"
    "== Navigation ==\n"
    "[[Category:PD-old]]\n"
    + "These facts seemed to throw some light on the origin of species. " * 30
)


def _category_members(titles):
    return {
        "query": {
            "categorymembers": [{"title": t, "ns": 0} for t in titles]
        }
    }


def _categories_response(pagename, categories):
    return {
        "query": {
            "pages": {
                "1": {
                    "title": pagename,
                    "categories": [{"title": f"Category:{c}"} for c in categories],
                }
            }
        }
    }


def _revision_response(pagename, content):
    return {
        "query": {
            "pages": {
                "1": {
                    "title": pagename,
                    "revisions": [{"slots": {"main": {"*": content}}}],
                }
            }
        }
    }


def _pd_fetcher(pagename="On the Origin of Species", categories=("PD-old",)):
    # FakeFetcher keys on URL only; all three calls hit the same API URL, so we
    # drive a fetcher that returns the right payload per call order via a queue.
    return _QueuedFetcher(
        [
            _category_members([pagename]),
            _categories_response(pagename, list(categories)),
            _revision_response(pagename, _BODY_WIKITEXT),
        ]
    )


class _QueuedFetcher:
    """A fetcher whose get_json returns queued payloads in call order (the
    Wikisource flow makes 3 same-URL API calls per discover)."""

    def __init__(self, json_queue):
        self._queue = list(json_queue)
        self.json_calls = []

    def get_json(self, url, *, params=None):
        self.json_calls.append((url, dict(params or {})))
        return self._queue.pop(0)

    def get_bytes(self, url, *, params=None):
        raise AssertionError("wikisource carries body inline; no get_bytes")


def test_discover_enumerates_candidates_from_api():
    fetcher = _pd_fetcher()
    cands = wikisource.discover(fetcher, limit=5)
    assert len(cands) == 1
    c = cands[0]
    assert c.source == "wikisource"
    assert c.source_id == "wikisource:On_the_Origin_of_Species"
    # PD established from the PD-old license category, named in the pd_signal so
    # the resulting license_basis quotes the category (not assumed, not masked).
    assert c.license_uri is None
    assert c.pd_signal and "pd-old" in c.pd_signal.lower()


def test_pd_category_classifies_servable():
    (c,) = wikisource.discover(_pd_fetcher(), limit=1)
    decision = c.classification()
    assert decision.servable is True
    assert decision.content_class == "public_domain"


def test_non_pd_category_is_gated_not_servable():
    """An item whose Wikisource license category is NOT PD/PD-equivalent is
    NOT marked public_domain — classify() gates it (M3 AC)."""
    fetcher = _QueuedFetcher(
        [
            _category_members(["Recent Copyrighted Work"]),
            _categories_response("Recent Copyrighted Work", ["Copyrighted", "CC-BY"]),
            _revision_response(
                "Recent Copyrighted Work",
                "Some recent text under copyright. " * 40,
            ),
        ]
    )
    (c,) = wikisource.discover(fetcher, limit=1)
    decision = c.classification()
    assert decision.servable is False
    assert decision.content_class == "restricted_pending_opt_in"
    assert c.license_uri is None and c.pd_signal is None


def test_cc_by_sa_category_is_source_declared_open_not_pd():
    """A free-licensed (CC-BY-SA) Wikisource page is servable but classified
    source_declared_open, NOT public_domain (the license is declared, not PD)."""
    fetcher = _QueuedFetcher(
        [
            _category_members(["A Free Essay"]),
            _categories_response("A Free Essay", ["CC-BY-SA 4.0"]),
            _revision_response("A Free Essay", "An openly licensed essay body. " * 40),
        ]
    )
    (c,) = wikisource.discover(fetcher, limit=1)
    decision = c.classification()
    assert decision.servable is True
    assert decision.content_class == "source_declared_open"


def test_clean_wikitext_strips_chrome_keeps_body():
    """Navigation chrome / templates / footnote boilerplate stripped before
    extraction; the body survives (M3 AC)."""
    cleaned = wikisource.clean_wikitext(_BODY_WIKITEXT)
    assert "much struck with" in cleaned  # body kept
    assert "title=On the Origin" not in cleaned  # {{header}} template stripped
    assert "a footnote that must be stripped" not in cleaned  # <ref> stripped
    assert "Navigation" not in cleaned  # nav section header stripped
    assert "Category:PD-old" not in cleaned  # category link stripped


def test_ingest_servable_with_basis_naming_category(temp_substrate):
    from .conftest import StubEmbedder

    (c,) = wikisource.discover(_pd_fetcher(), limit=1)
    # Body rides inline (fetched via the API call), so ingest needs no get_bytes.
    fetcher = FakeFetcher()
    outcome = classify_and_ingest(
        c, fetcher, db_path=temp_substrate["db_path"], embedder=StubEmbedder()
    )
    assert outcome.ingested is True
    assert outcome.content_class == "public_domain"
    assert outcome.servable is True
    cc, basis, raw_text = book_asset_row(temp_substrate["db_path"], outcome.document_id)
    assert cc == "public_domain"
    # license_basis names the Wikisource category that established PD.
    assert basis and "pd-old" in basis.lower()
    assert raw_text and "much struck with" in raw_text
    assert fetcher.bytes_calls == []  # body was inline, never re-fetched
