"""Boundary tests for purpose-scoped URL User-Agents and visible refusals."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.arxiv.client import _DEFAULT_CONTACT
from acquisition.contact import ANTIEK_CONTACT_URL
from acquisition.urls.client import (
    FetchPurpose,
    clear_refusal_counts,
    fetch,
    refusal_counts,
    user_agent_for,
)
from acquisition.urls.robots import RobotsDisallowed


@pytest.fixture(autouse=True)
def clean_caches() -> Iterator[None]:
    acquisition.urls.robots.clear_robots_cache()
    clear_refusal_counts()
    yield
    acquisition.urls.robots.clear_robots_cache()
    clear_refusal_counts()


def _client(routes: dict[str, tuple[int, bytes]]) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(request.url.path, (404, b"not found"))
        content_type = "text/plain" if request.url.path == "/robots.txt" else "text/html"
        return httpx.Response(
            status,
            headers={"Content-Type": content_type},
            content=body,
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_three_distinct_purpose_agents() -> None:
    assert len(FetchPurpose) == 3
    agents = {user_agent_for(purpose) for purpose in FetchPurpose}
    assert len(agents) == 3
    # Distinct product tokens, so a robots.txt group can name one purpose.
    assert len({agent.split("/", 1)[0] for agent in agents}) == 3


def test_each_agent_carries_an_https_contact_url() -> None:
    for purpose in FetchPurpose:
        agent = user_agent_for(purpose)
        assert "https://" in agent
        assert ANTIEK_CONTACT_URL in agent


def test_the_arxiv_client_advertises_the_same_contact() -> None:
    assert _DEFAULT_CONTACT == "+" + ANTIEK_CONTACT_URL


def test_fetch_sends_the_agent_for_its_purpose() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen[request.url.path] = request.headers["user-agent"]
        status = 404 if request.url.path == "/robots.txt" else 200
        return httpx.Response(
            status,
            headers={"Content-Type": "text/html"},
            content=b"<html><body>ok</body></html>",
            request=request,
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    for purpose in FetchPurpose:
        url = f"https://ua-{purpose.name.lower()}.example/page"
        page = fetch(url, client=client, purpose=purpose)
        assert page.status_code == 200
        assert seen["/page"] == user_agent_for(purpose)

    seen.clear()
    page = fetch("https://default-agent.example/page", client=client)
    assert page.status_code == 200
    assert seen["/page"] == user_agent_for(FetchPurpose.AGENT)


def test_a_403_increments_the_per_host_counter_by_exactly_one() -> None:
    client = _client({
        "/robots.txt": (404, b"not found"),
        "/page": (403, b"forbidden"),
    })
    before = refusal_counts().get("blocked.example", {}).get(403, 0)

    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://blocked.example/page", client=client)

    assert refusal_counts().get("blocked.example", {}).get(403, 0) == before + 1
    assert refusal_counts()["blocked.example"] == {403: 1}


def test_401_and_402_are_counted_and_a_404_is_not() -> None:
    client = _client({
        "/unauthorized": (401, b"unauthorized"),
        "/payment": (402, b"payment required"),
        "/missing": (404, b"not found"),
    })

    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://unauthorized.example/unauthorized", client=client)
    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://payment.example/payment", client=client)
    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://missing.example/missing", client=client)

    assert refusal_counts()["unauthorized.example"] == {401: 1}
    assert refusal_counts()["payment.example"] == {402: 1}
    assert "missing.example" not in refusal_counts()


def test_counting_a_refusal_opens_no_database_writer(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client({
        "/robots.txt": (404, b"not found"),
        "/page": (403, b"forbidden"),
    })

    def no_database_write() -> None:
        raise AssertionError("fetch must not touch DuckDB")

    def no_database_read(db_path: str) -> None:
        raise AssertionError("fetch must not touch DuckDB")

    import runtime.db_lock

    monkeypatch.setattr(runtime.db_lock, "connect_write", no_database_write)
    monkeypatch.setattr(runtime.db_lock, "connect_read", no_database_read)

    with pytest.raises(httpx.HTTPStatusError):
        fetch("https://blocked.example/page", client=client)

    assert refusal_counts()["blocked.example"] == {403: 1}


def test_a_robots_group_for_one_purpose_binds_only_that_agent() -> None:
    client = _client({
        "/robots.txt": (200, b"User-agent: Antiek-Agent\nDisallow: /\n"),
        "/agent/page": (200, b"<html><body>agent</body></html>"),
        "/search/page": (200, b"<html><body>search</body></html>"),
    })

    with pytest.raises(RobotsDisallowed):
        fetch("https://split.example/agent/page", client=client, purpose=FetchPurpose.AGENT)

    page = fetch("https://split.example/search/page", client=client, purpose=FetchPurpose.SEARCH)
    assert page.status_code == 200
