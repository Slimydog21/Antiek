"""Regression tests for per-hop robots consultation and licence hardening."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.urls.client import RobotsDisallowed, clear_refusal_counts, fetch
from acquisition.urls.robots import robots_policy_for


@pytest.fixture(autouse=True)
def clean_caches() -> Iterator[None]:
    acquisition.urls.robots.clear_robots_cache()
    clear_refusal_counts()
    yield
    acquisition.urls.robots.clear_robots_cache()
    clear_refusal_counts()


def _client(
    routes: dict[tuple[str, str], tuple[int, bytes]],
    redirects: dict[tuple[str, str], str],
) -> tuple[httpx.Client, list[str]]:
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        key = (request.url.host or "", request.url.path)
        if key in redirects:
            return httpx.Response(
                302,
                headers={"Location": redirects[key]},
                request=request,
            )
        status, body = routes.get(key, (404, b"not found"))
        content_type = "text/plain" if request.url.path == "/robots.txt" else "text/html"
        return httpx.Response(
            status,
            headers={"Content-Type": content_type},
            content=body,
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def _rsl(payment_type: str = "free") -> bytes:
    return (
        '<?xml version="1.0"?>'
        '<rsl xmlns="https://rslstandard.org/rsl">'
        f'<payment type="{payment_type}" />'
        "</rsl>"
    ).encode()


def test_an_invalid_licence_url_never_blocks_ingest() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\nLicense: http://[invalid/\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "invalid licence URL" in (page.rights_terms.parse_error or "")


def test_a_redirect_to_a_disallowed_path_on_another_host_is_refused() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("b.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /private\n")},
        {("a.example", "/page"): "https://b.example/private"},
    )

    with pytest.raises(RobotsDisallowed):
        fetch("https://a.example/page", client=client)

    assert "https://b.example/robots.txt" in requested
    assert "https://b.example/private" not in requested


def test_an_allowed_cross_host_redirect_reports_the_serving_origin() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("b.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("b.example", "/private"): (200, b"<html>served by B</html>")},
        {("a.example", "/page"): "https://b.example/private"},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.final_url == "https://b.example/private"
    assert "https://b.example/robots.txt" in requested


def test_a_disallowed_licence_file_is_not_fetched() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /license.xml\nLicense: /license.xml\n"),
         ("a.example", "/license.xml"): (200, _rsl()),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "https://a.example/license.xml" not in requested
    assert "disallowed" in (page.rights_terms.parse_error or "")


def test_a_licence_that_redirects_off_origin_is_not_used() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\nLicense: /license.xml\n"),
         ("a.example", "/license.xml"): (200, _rsl()),
         ("evil.example", "/l.xml"): (200, _rsl("free")),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/license.xml"): "https://evil.example/l.xml"},
    )

    page = fetch("https://a.example/page", client=client)

    assert "https://evil.example/l.xml" not in requested
    assert page.rights_terms.payment_types == ()
    assert "redirected" in (page.rights_terms.parse_error or "")


def test_an_applied_policy_beats_a_concurrently_stored_fail_open() -> None:
    def failing(_url: str, _follow: bool) -> tuple[int, str, str]:
        raise RuntimeError("the losing concurrent build failed")

    def outer(url: str, follow: bool) -> tuple[int, str, str]:
        robots_policy_for("https://race.example/y", fetch_text=failing, user_agent="Antiek-Agent/0.1")
        return 200, "User-agent: *\nDisallow: /x\n", url

    policy = robots_policy_for(
        "https://race.example/x", fetch_text=outer, user_agent="Antiek-Agent/0.1",
    )

    assert policy.applied is True
    assert policy.allows("Antiek-Agent/0.1", "https://race.example/x") is False

    def must_not_fetch(_url: str, _follow: bool) -> tuple[int, str, str]:
        raise AssertionError("the applied winner should be cached")

    cached = robots_policy_for(
        "https://race.example/z", fetch_text=must_not_fetch, user_agent="Antiek-Agent/0.1",
    )
    assert cached is policy


def test_a_binary_robots_txt_fails_open_with_a_reason() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"\x00\x01binary\x00"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "NUL" in (page.robots_fail_open_reason or "")


def test_an_html_error_page_served_as_robots_txt_fails_open_with_a_reason() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"<html><body>Not found</body></html>"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "no robots directives" in (page.robots_fail_open_reason or "")


def test_a_comment_only_robots_txt_is_an_applied_empty_policy() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"# nothing here\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert page.robots_fail_open_reason is None
