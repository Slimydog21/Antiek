"""Regression tests for per-hop robots consultation and licence hardening."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.urls.client import clear_refusal_counts, fetch
from acquisition.urls.robots import (
    FetchText,
    RobotsDisallowed,
    cached_origins,
    robots_policy_for,
)


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


def _serving(body: str, calls: list[str]) -> FetchText:
    def fetch_text(url: str, _follow: bool) -> tuple[int, str, str]:
        calls.append(url)
        return 200, body, url

    return fetch_text


_MANY_RULES = "User-agent: *\n" + "".join(f"Disallow: /private-{i}/\n" for i in range(40))


def test_the_policy_cache_is_bounded_and_drops_the_least_recently_used(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A long-lived process that fetches many origins must not keep every
    robots.txt it ever parsed."""
    monkeypatch.setattr(acquisition.urls.robots, "MAX_CACHED_ROBOTS_BYTES", 8 * 1024)
    agent = "Antiek-Agent/0.1"
    hot_calls: list[str] = []
    for i in range(50):
        robots_policy_for(
            "https://hot.example/", fetch_text=_serving(_MANY_RULES, hot_calls), user_agent=agent,
        )
        robots_policy_for(
            f"https://o{i}.example/", fetch_text=_serving(_MANY_RULES, []), user_agent=agent,
        )

    cached = cached_origins()
    assert len(cached) < 20
    assert "https://o0.example" not in cached
    assert "https://o49.example" in cached
    # Used between every store, the hot origin is never the least recently
    # used, so it stays cached and its robots.txt is read once.
    assert "https://hot.example" in cached
    assert hot_calls == ["https://hot.example/robots.txt"]


def test_expired_policies_are_swept_when_another_origin_is_stored(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = [1_000.0]
    monkeypatch.setattr(acquisition.urls.robots, "_clock", lambda: now[0])
    agent = "Antiek-Agent/0.1"
    robots_policy_for("https://old.example/", fetch_text=_serving(_MANY_RULES, []), user_agent=agent)

    now[0] += acquisition.urls.robots.ROBOTS_CACHE_TTL_S + 1
    robots_policy_for("https://new.example/", fetch_text=_serving(_MANY_RULES, []), user_agent=agent)

    assert cached_origins() == ("https://new.example",)


# --- RSL <content url> scope (codex r1 MED-2) --------------------------------


def _scoped_rsl(*scopes: tuple[str, str]) -> bytes:
    """An RSL licence with one ``<content url>`` per (url, payment type)."""
    contents = "".join(
        f'<content url="{url}"><license><payment type="{payment}"/></license></content>'
        for url, payment in scopes
    )
    return f'<rsl xmlns="https://rslstandard.org/rsl">{contents}</rsl>'.encode()


_LICENSED_ROBOTS = b"User-agent: *\nAllow: /\nLicense: /license.xml\n"


def test_a_licence_scoped_to_another_path_says_nothing_about_this_page() -> None:
    """RSL 1.0 s3.3: ``<content url>`` names the licensed asset or scope. A
    free licence for /free is not a licence for /paid."""
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (200, _scoped_rsl(("/free", "free"))),
         ("a.example", "/paid"): (200, b"<html>paid</html>"),
         ("a.example", "/free"): (200, b"<html>free</html>")},
        {},
    )

    paid = fetch("https://a.example/paid", client=client)
    free = fetch("https://a.example/free", client=client)

    assert paid.rights_terms.no_charge is False
    assert paid.rights_terms.payment_types == ()
    assert paid.rights_terms.content_url is None
    assert paid.rights_terms.license_url == "https://a.example/license.xml"
    assert free.rights_terms.no_charge is True
    assert free.rights_terms.content_url == "/free"


def test_the_most_specific_content_scope_decides_a_page() -> None:
    """RSL 1.0 s3.1.1: a narrower declaration takes precedence over a wider
    one, whatever their order in the file."""
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (
             200, _scoped_rsl(("/open/*.html$", "attribution"), ("/", "purchase")),
         ),
         ("a.example", "/open/essay.html"): (200, b"<html>open</html>"),
         ("a.example", "/open/essay.pdf"): (200, b"<html>pdf</html>"),
         ("a.example", "/shop"): (200, b"<html>shop</html>")},
        {},
    )

    open_page = fetch("https://a.example/open/essay.html", client=client)
    pdf_page = fetch("https://a.example/open/essay.pdf", client=client)
    shop_page = fetch("https://a.example/shop", client=client)

    assert open_page.rights_terms.payment_types == ("attribution",)
    assert pdf_page.rights_terms.payment_types == ("purchase",)
    assert shop_page.rights_terms.payment_types == ("purchase",)


def test_licence_terms_are_selected_for_the_url_the_redirects_ended_on() -> None:
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (200, _scoped_rsl(("/free/", "free"))),
         ("a.example", "/paid"): (200, b"<html>paid</html>")},
        {("a.example", "/free/start"): "https://a.example/paid"},
    )

    page = fetch("https://a.example/free/start", client=client)

    assert page.final_url == "https://a.example/paid"
    assert page.rights_terms.no_charge is False
    assert page.rights_terms.payment_types == ()


# --- robots.txt redirects (codex r1 MED-3) ----------------------------------


def test_a_robots_txt_redirect_to_a_disallowed_page_is_not_followed() -> None:
    """The robots.txt GET is a request like any other: A/robots.txt pointing
    at B/private must not fetch B/private when B's robots.txt disallows it."""
    client, requested = _client(
        {("b.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /private\n"),
         ("b.example", "/private"): (200, b"User-agent: *\nAllow: /\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): "https://b.example/private"},
    )

    page = fetch("https://a.example/page", client=client)

    assert "https://b.example/private" not in requested
    assert "https://b.example/robots.txt" in requested
    assert page.status_code == 200
    assert "disallow" in (page.robots_fail_open_reason or "")


def test_a_robots_txt_redirect_to_another_robots_txt_is_followed() -> None:
    """RFC 9309 s2.3.1.2: follow robots.txt redirects (http->https, apex->www);
    a robots.txt is never governed by robots rules, so no check is needed."""
    client, requested = _client(
        {("www.a.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /page\n")},
        {("a.example", "/robots.txt"): "https://www.a.example/robots.txt"},
    )

    with pytest.raises(RobotsDisallowed):
        fetch("https://a.example/page", client=client)

    assert "https://a.example/page" not in requested


def test_a_robots_txt_redirect_loop_across_origins_terminates() -> None:
    client, requested = _client(
        {("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): "https://b.example/x",
         ("b.example", "/robots.txt"): "https://a.example/y"},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "https://a.example/y" not in requested


def test_more_than_five_robots_txt_redirects_fail_open() -> None:
    """RFC 9309 s2.3.1.2: after five consecutive redirects a crawler MAY
    assume robots.txt is unavailable."""
    hops = {("a.example", "/robots.txt"): "https://a.example/r1"}
    hops.update({("a.example", f"/r{i}"): f"https://a.example/r{i + 1}" for i in range(1, 9)})
    client, requested = _client({("a.example", "/page"): (200, b"<html>ok</html>")}, hops)

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "redirect" in (page.robots_fail_open_reason or "")
    assert "https://a.example/r6" not in requested


# --- cache weight counts licence terms (codex r1 MED-4) ---------------------


def _retained_chars(value: object, seen: set[int] | None = None) -> int:
    """Characters of text reachable from ``value`` through dataclasses,
    mappings and sequences: what a cached policy actually keeps alive."""
    import dataclasses

    seen = set() if seen is None else seen
    if id(value) in seen:
        return 0
    seen.add(id(value))
    if isinstance(value, str):
        return len(value)
    if isinstance(value, dict):
        return sum(_retained_chars(k, seen) + _retained_chars(v, seen) for k, v in value.items())
    if isinstance(value, (tuple, list, frozenset, set)):
        return sum(_retained_chars(v, seen) for v in value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return sum(_retained_chars(getattr(value, f.name), seen) for f in dataclasses.fields(value))
    return 0


def test_the_cache_weight_counts_licence_terms_loaded_after_insertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_CACHED_ROBOTS_BYTES", 1024)
    big = "x" * 100_000
    licence = (
        '<rsl><content url="/"><license>'
        f'<permits type="usage">{big}</permits>'
        "</license></content></rsl>"
    ).encode()
    routes: dict[tuple[str, str], tuple[int, bytes]] = {}
    for i in range(3):
        routes[(f"o{i}.example", "/robots.txt")] = (200, _LICENSED_ROBOTS)
        routes[(f"o{i}.example", "/license.xml")] = (200, licence)
        routes[(f"o{i}.example", "/page")] = (200, b"<html>ok</html>")
    client, _requested = _client(routes, {})

    for i in range(3):
        page = fetch(f"https://o{i}.example/page", client=client)
        assert len(page.rights_terms.permits[0]) > 100_000

    cache = acquisition.urls.robots._cache
    weight = sum(entry[2] for entry in cache.values())
    retained = sum(_retained_chars(entry[0]) for entry in cache.values())
    assert weight >= retained, f"cache_weight {weight} < {retained} characters retained"
    assert weight <= 1024 or len(cache) == 1, (
        f"{len(cache)} origins cached at weight {weight} over a 1024 budget"
    )
    assert cached_origins() == ("https://o2.example",)
