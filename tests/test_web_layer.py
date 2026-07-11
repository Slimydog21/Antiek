"""Contract and composition proofs for the two-vendor web layer."""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from acquisition.web_layer.cost import estimate_cost
from acquisition.web_layer.exa_discovery import (
    DiscoveryConfigurationError,
    ExaDiscovery,
)
from acquisition.web_layer.interfaces import ExtractionAdapter
from acquisition.web_layer.jina_extract import (
    ExtractionConfigurationError,
    JinaExtractor,
)
from acquisition.web_layer.stub_extract import SwapStubExtractor

FIXED_NOW = datetime(2026, 7, 11, 9, 30, tzinfo=UTC)


class FakeResponse:
    def __init__(self, body: object) -> None:
        self.body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.body


class RecordingDiscoveryHttp:
    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses = list(responses or [])
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: object,
        json: object,
        timeout: float,
    ) -> FakeResponse:
        self.calls.append(
            {"url": url, "headers": headers, "json": json, "timeout": timeout}
        )
        return FakeResponse(self.responses.pop(0))


class FakeTextResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


class RecordingExtractionHttp:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[dict[str, Any]] = []

    def get(
        self,
        url: str,
        *,
        headers: object,
        timeout: float,
    ) -> FakeTextResponse:
        self.calls.append({"url": url, "headers": headers, "timeout": timeout})
        return FakeTextResponse(self.text)


SOURCE_URL = "https://source.test/article"
FULL_TEXT = "# Complete article\n\nEvidence-rich body text."


def make_jina_extractor() -> ExtractionAdapter:
    return JinaExtractor(
        http=RecordingExtractionHttp(FULL_TEXT),
        clock=lambda: FIXED_NOW,
        environ={"JINA_API_KEY": "jina-secret"},
    )


def make_swap_stub_extractor() -> ExtractionAdapter:
    return SwapStubExtractor(
        documents={SOURCE_URL: FULL_TEXT},
        clock=lambda: FIXED_NOW,
    )


def test_cost_examples_are_hand_computed_to_the_cent() -> None:
    # 2 Exa searches × $0.007 = $0.014, which rounds to $0.01 to the cent.
    exa = estimate_cost("exa", "search", 2)
    assert exa.usd_estimate == Decimal("0.014")
    assert exa.usd_estimate.quantize(Decimal("0.01")) == Decimal("0.01")

    # 3 Jina URL reads × $0.00 = $0.00 exactly.
    jina = estimate_cost("jina", "extract", 3)
    assert jina.usd_estimate == Decimal("0.00")
    assert jina.usd_estimate.quantize(Decimal("0.01")) == Decimal("0.00")


def test_cost_rejects_negative_units_and_unknown_pairs() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        estimate_cost("exa", "search", -1)
    with pytest.raises(ValueError, match="unsupported vendor operation"):
        estimate_cost("jina", "search", 1)


def test_exa_search_fixture_round_trip_with_fixed_clock() -> None:
    http = RecordingDiscoveryHttp(
        [
            {
                "results": [
                    {
                        "url": "https://example.test/paper",
                        "title": "A useful paper",
                        "score": 0.875,
                        "publishedDate": "2026-06-01T00:00:00Z",
                    }
                ]
            }
        ]
    )
    client = ExaDiscovery(
        http=http, clock=lambda: FIXED_NOW, environ={"EXA_API_KEY": "exa-secret"}
    )

    response = client.search("research agents", limit=5)

    assert response.results[0].url == "https://example.test/paper"
    assert response.results[0].score == 0.875
    assert response.results[0].published_at == datetime(2026, 6, 1, tzinfo=UTC)
    assert response.discovered_at == FIXED_NOW
    assert response.cost == estimate_cost("exa", "search", 1)
    assert http.calls[0]["url"] == "https://api.exa.ai/search"
    assert http.calls[0]["json"] == {"query": "research agents", "numResults": 5}


def test_exa_find_similar_is_the_highlight_spawn_path() -> None:
    http = RecordingDiscoveryHttp(
        [{"results": [{"url": "https://similar.test/one", "title": "Similar"}]}]
    )
    client = ExaDiscovery(
        http=http, clock=lambda: FIXED_NOW, environ={"EXA_API_KEY": "exa-secret"}
    )

    response = client.find_similar("https://seed.test/highlight-source", limit=3)

    assert [hit.url for hit in response.results] == ["https://similar.test/one"]
    assert response.cost == estimate_cost("exa", "find_similar", 1)
    assert response.discovered_at == FIXED_NOW
    assert http.calls[0]["url"] == "https://api.exa.ai/findSimilar"
    assert http.calls[0]["json"] == {
        "url": "https://seed.test/highlight-source",
        "numResults": 3,
    }


def test_exa_missing_key_fails_before_http_and_key_never_renders() -> None:
    http = RecordingDiscoveryHttp()
    with pytest.raises(DiscoveryConfigurationError, match="EXA_API_KEY"):
        ExaDiscovery(http=http, clock=lambda: FIXED_NOW, environ={})
    assert http.calls == []

    secret = "exa-do-not-render"
    client = ExaDiscovery(
        http=http, clock=lambda: FIXED_NOW, environ={"EXA_API_KEY": secret}
    )
    assert secret not in repr(client)
    assert secret not in str(client)


@pytest.mark.parametrize(
    "make_extractor",
    [make_jina_extractor, make_swap_stub_extractor],
    ids=["reference", "swap-stub"],
)
def test_extraction_adapter_shared_contract(
    make_extractor: Callable[[], ExtractionAdapter],
) -> None:
    """One suite, with no vendor branches or vendor-specific assertions."""

    response = make_extractor().extract(SOURCE_URL)

    assert response.result.source_url == SOURCE_URL
    assert response.result.text == FULL_TEXT
    assert response.result.retrieved_at == FIXED_NOW
    assert response.cost.operation == "extract"
    assert response.cost.units == 1
    assert response.cost.usd_estimate == Decimal("0.00")


def test_jina_fixture_uses_reader_prefix_and_get_only() -> None:
    http = RecordingExtractionHttp(FULL_TEXT)
    client = JinaExtractor(
        http=http,
        clock=lambda: FIXED_NOW,
        environ={"JINA_API_KEY": "jina-secret"},
    )

    client.extract(SOURCE_URL)

    assert http.calls[0]["url"] == f"https://r.jina.ai/{SOURCE_URL}"


def test_jina_missing_key_fails_before_http_and_key_never_renders() -> None:
    http = RecordingExtractionHttp(FULL_TEXT)
    with pytest.raises(ExtractionConfigurationError, match="JINA_API_KEY"):
        JinaExtractor(http=http, clock=lambda: FIXED_NOW, environ={})
    assert http.calls == []

    secret = "jina-do-not-render"
    client = JinaExtractor(
        http=http, clock=lambda: FIXED_NOW, environ={"JINA_API_KEY": secret}
    )
    assert secret not in repr(client)
    assert secret not in str(client)
