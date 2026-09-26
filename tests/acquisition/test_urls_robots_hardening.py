"""Regression tests for per-hop robots consultation and licence hardening."""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.urls.client import CredentialedRedirect, clear_refusal_counts, fetch
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
    """One origin's licence fits the budget, two do not: loading the next
    origin's licence must evict the previous origin."""
    monkeypatch.setattr(acquisition.urls.robots, "MAX_CACHED_ROBOTS_BYTES", 150_000)
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
    assert weight <= 150_000, f"{len(cache)} origins cached at weight {weight} over a 150000 budget"
    assert cached_origins() == ("https://o2.example",)


# --- codex r2: every covering scope, empty url, oversized entry, userinfo ---


def test_a_site_wide_prohibition_survives_a_narrower_free_scope() -> None:
    """RSL 1.0 s3.1.1: all applicable terms are evaluated together, and a
    prohibition takes precedence. A narrower free scope sets the payment for
    /free/, but it does not lift the site-wide ban on AI training."""
    licence = (
        b'<rsl xmlns="https://rslstandard.org/rsl">'
        b'<content url="/"><license><prohibits type="usage">ai-train</prohibits>'
        b'<payment type="purchase"/></license></content>'
        b'<content url="/free/"><license><payment type="free"/></license></content>'
        b"</rsl>"
    )
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (200, licence),
         ("a.example", "/free/essay"): (200, b"<html>free</html>"),
         ("a.example", "/shop"): (200, b"<html>shop</html>")},
        {},
    )

    free = fetch("https://a.example/free/essay", client=client)
    shop = fetch("https://a.example/shop", client=client)

    assert free.rights_terms.prohibits == ("usage:ai-train",)
    assert free.rights_terms.payment_types == ("free",)
    assert free.rights_terms.no_charge is True
    assert free.rights_terms.content_url == "/free/"
    assert shop.rights_terms.prohibits == ("usage:ai-train",)
    assert shop.rights_terms.payment_types == ("purchase",)


def test_a_robots_linked_licence_with_an_empty_content_url_grants_nothing() -> None:
    """RSL 1.0 s3.3.1: ``url=""`` names the association's own scope only where
    the association mechanism permits it, and the robots.txt association
    (s4.4) does not. It must not make /paid free."""
    licence = (
        b'<rsl xmlns="https://rslstandard.org/rsl">'
        b'<content url=""><license><payment type="free"/></license></content>'
        b"</rsl>"
    )
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (200, licence),
         ("a.example", "/paid"): (200, b"<html>paid</html>")},
        {},
    )

    paid = fetch("https://a.example/paid", client=client)

    assert paid.rights_terms.no_charge is False
    assert paid.rights_terms.payment_types == ()
    assert paid.rights_terms.source == "rsl_out_of_scope"


def test_a_robots_txt_heavier_than_the_whole_cache_is_used_but_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_CACHED_ROBOTS_BYTES", 1024)
    agent = "Antiek-Agent/0.1"
    robots_policy_for("https://small.example/", fetch_text=_serving("", []), user_agent=agent)
    big_calls: list[str] = []

    policy = robots_policy_for(
        "https://big.example/", fetch_text=_serving(_MANY_RULES, big_calls), user_agent=agent,
    )

    assert policy.applied is True
    assert policy.allows(agent, "https://big.example/private-3/x") is False
    assert "https://big.example" not in cached_origins()
    assert "https://small.example" in cached_origins()
    robots_policy_for("https://big.example/", fetch_text=_serving(_MANY_RULES, big_calls), user_agent=agent)
    assert big_calls == ["https://big.example/robots.txt"] * 2


def test_a_licence_heavier_than_the_whole_cache_serves_its_fetch_but_is_not_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_CACHED_ROBOTS_BYTES", 1024)
    licence = (
        '<rsl><content url="/"><license>'
        f'<permits type="usage">{"x" * 100_000}</permits>'
        "</license></content></rsl>"
    ).encode()
    client, _requested = _client(
        {("small.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("small.example", "/page"): (200, b"<html>ok</html>"),
         ("o0.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("o0.example", "/license.xml"): (200, licence),
         ("o0.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )
    fetch("https://small.example/page", client=client)

    page = fetch("https://o0.example/page", client=client)

    assert len(page.rights_terms.permits[0]) > 100_000
    assert "https://o0.example" not in cached_origins()
    assert "https://small.example" in cached_origins()


_SECRET_LOCATION = "https://alice:probe-pass@b.example/x?token=q-secret"


def _leaks(text: str) -> list[str]:
    return [secret for secret in ("alice", "probe-pass", "q-secret") if secret in text]


def _logged(caplog: pytest.LogCaptureFixture, prefix: str = "") -> str:
    return "\n".join(
        f"{record.getMessage()} {record.args!r}"
        for record in caplog.records
        if record.name.startswith(prefix)
    )


def test_a_robots_txt_redirect_with_credentials_never_records_them(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, requested = _client(
        {("b.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /x\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): _SECRET_LOCATION},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    # A credentialed Location is refused before b.example is consulted
    # (test_a_robots_txt_redirect_carrying_credentials_is_not_followed).
    assert not any("b.example" in url for url in requested)
    reason = page.robots_fail_open_reason or ""
    assert "https://b.example/x" in reason
    assert "credentials" in reason
    assert _leaks(reason) == []
    assert _leaks(_logged(caplog)) == []
    assert _leaks(" ".join(cached_origins())) == []


@pytest.mark.parametrize("b_robots", [(404, b""), (200, b"User-agent: *\nDisallow: /x\n")])
def test_a_page_redirect_with_credentials_never_records_them(
    caplog: pytest.LogCaptureFixture, b_robots: tuple[int, bytes],
) -> None:
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("b.example", "/robots.txt"): b_robots,
         ("b.example", "/x"): (200, b"<html>b</html>")},
        {("a.example", "/page"): _SECRET_LOCATION},
    )

    refusal = ""
    with caplog.at_level(logging.DEBUG):
        try:
            page = fetch("https://a.example/page", client=client)
            refusal = page.robots_fail_open_reason or ""
        except (RobotsDisallowed, CredentialedRedirect) as exc:
            refusal = str(exc)

    assert refusal
    assert _leaks(refusal) == []
    # Every record: the credentialed hop is refused whatever b.example's
    # robots.txt says (test_a_page_redirect_carrying_credentials_is_refused_
    # before_they_are_sent), and nothing logged on the way names it whole.
    assert _leaks(_logged(caplog)) == []
    assert _leaks(" ".join(cached_origins())) == []


def test_a_licence_url_carrying_credentials_is_not_followed_or_recorded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (
            200, b"User-agent: *\nAllow: /\nLicense: https://alice:probe-pass@a.example/license.xml\n",
        ),
         ("a.example", "/license.xml"): (200, _rsl()),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    assert not any(url.endswith("/license.xml") for url in requested)
    assert page.rights_terms.no_charge is False
    assert "credentials" in (page.rights_terms.parse_error or "")
    assert _leaks(f"{page.rights_terms.license_url} {page.rights_terms.parse_error}") == []
    assert _leaks(_logged(caplog)) == []


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://u:p@h:8443/a?b", "https://h:8443"),
        ("https://alice@H.example/x", "https://h.example"),
        ("http://u:p@[::1]:8080/", "http://[::1]:8080"),
        ("https://h.example/a", "https://h.example"),
    ],
)
def test_origin_of_drops_userinfo(url: str, origin: str) -> None:
    assert acquisition.urls.robots.origin_of(url) == origin


# --- adversarial review of 5231bd522: redaction, token caps, default ports ---


def _all_records(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(record.getMessage() for record in caplog.records)


def test_a_path_parameter_token_is_redacted_from_a_refusal_reason(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """RFC 3986 s3.3 ``;`` path parameters can carry a token as well as a
    query can; a reason keeps each segment's path only."""
    client, _requested = _client(
        {("b.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): "https://b.example/x;token=tok-secret/y;v=2"},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    reason = page.robots_fail_open_reason or ""
    assert "https://b.example/x/y" in reason
    assert "tok-secret" not in reason
    assert "tok-secret" not in _logged(caplog, "acquisition")


def _raising_client(
    routes: dict[tuple[str, str], tuple[int, bytes]],
    redirects: dict[tuple[str, str], str],
    raising: set[tuple[str, str]],
) -> tuple[httpx.Client, list[str]]:
    """``_client``, except the routes in ``raising`` fail with a transport
    error whose text names the URL, as many transports' messages do."""
    inner, requested = _client(routes, redirects)

    def handler(request: httpx.Request) -> httpx.Response:
        if (request.url.host or "", request.url.path) in raising:
            requested.append(str(request.url))
            raise httpx.ConnectError(f"could not connect to {request.url}", request=request)
        return inner.send(request)

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_a_transport_error_naming_a_redirect_hop_is_redacted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _requested = _raising_client(
        {("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): "/moved?token=q-secret"},
        {("a.example", "/moved")},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    reason = page.robots_fail_open_reason or ""
    assert "ConnectError" in reason
    assert "https://a.example/moved" in reason
    assert _leaks(reason) == []
    assert _leaks(_logged(caplog, "acquisition")) == []


def test_a_licence_url_query_is_never_stored_or_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client, _requested = _raising_client(
        {("a.example", "/robots.txt"): (
            200, b"User-agent: *\nAllow: /\nLicense: /license.xml?token=q-secret\n",
        ),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
        {("a.example", "/license.xml")},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    terms = page.rights_terms
    assert terms.license_url == "https://a.example/license.xml"
    assert "ConnectError" in (terms.parse_error or "")
    assert _leaks(f"{terms.license_url} {terms.parse_error}") == []
    assert _leaks(_logged(caplog, "acquisition")) == []


def test_the_scope_budget_warning_redacts_the_licence_url(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_MATCH_COST", 5)
    client, _requested = _client(
        {("a.example", "/robots.txt"): (
            200, b"User-agent: *\nAllow: /\nLicense: /license.xml?token=q-secret\n",
        ),
         ("a.example", "/license.xml"): (200, _scoped_rsl(("/*a*b*c", "free"))),
         ("a.example", "/zzzzzzzzzz"): (200, b"<html>ok</html>")},
        {},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/zzzzzzzzzz", client=client)

    assert "too costly" in (page.rights_terms.parse_error or "")
    assert "character comparisons" in _logged(caplog, "acquisition")
    assert _leaks(_logged(caplog, "acquisition")) == []
    assert _leaks(page.rights_terms.license_url or "") == []
    # terms_covering redacts on its own, whatever licence_url it is handed.
    caplog.clear()
    raw = acquisition.urls.robots.parse_rsl_licence(
        _scoped_rsl(("/*a*b*c", "free")).decode(),
        license_url="https://alice:probe-pass@a.example/license.xml?token=q-secret",
    )
    with caplog.at_level(logging.DEBUG):
        acquisition.urls.robots.terms_covering(
            raw, origin="https://a.example", url="https://a.example/zzzzzzzzzz"
        )
    assert "character comparisons" in _logged(caplog, "acquisition")
    assert _leaks(_logged(caplog, "acquisition")) == []


def test_robots_disallowed_keeps_no_credential_in_any_attribute() -> None:
    client, _requested = _client(
        {("b.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /x\n")},
        {},
    )

    with pytest.raises(RobotsDisallowed) as caught:
        fetch(_SECRET_LOCATION, client=client)

    exc = caught.value
    assert exc.url == "https://b.example/x"
    assert _leaks(f"{exc} {exc!r} {vars(exc)}") == []


@pytest.mark.parametrize(
    "location",
    [
        "https://alice:probe-pass@b.example/allowed?token=q-secret",
        "https://b.example/allowed?token=q-secret",
    ],
)
def test_no_log_record_carries_a_robots_redirect_query(
    caplog: pytest.LogCaptureFixture, location: str,
) -> None:
    """Every record, httpx's own ``HTTP Request:`` INFO line included: the
    fetcher's requests are logged with their URLs redacted."""
    client, _requested = _client(
        {("b.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("b.example", "/allowed"): (200, b"User-agent: *\nDisallow: /secret\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): location},
    )

    with caplog.at_level(logging.DEBUG):
        fetch("https://a.example/page", client=client)

    assert any(record.name == "httpx" for record in caplog.records)
    assert _leaks(_all_records(caplog)) == []


def test_a_robots_txt_redirect_carrying_credentials_is_not_followed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Userinfo in a Location would be sent as credentials; a same-host one
    is no longer a different origin (origin_of drops it), so it is refused
    outright, like a credentialed License: URL."""
    client, requested = _client(
        {("a.example", "/elsewhere"): (200, b"User-agent: *\nDisallow: /\n"),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {("a.example", "/robots.txt"): "https://alice:probe-pass@a.example/elsewhere?token=q-secret"},
    )

    with caplog.at_level(logging.DEBUG):
        page = fetch("https://a.example/page", client=client)

    assert not any("/elsewhere" in url for url in requested)
    reason = page.robots_fail_open_reason or ""
    assert "credentials" in reason
    assert _leaks(reason) == []
    assert _leaks(_all_records(caplog)) == []


def test_a_bare_scope_flood_across_three_purposes_stays_cached() -> None:
    """Bare ``<content/>`` elements weigh far more parsed than their ten
    bytes; one licence of them per purpose must not push its origin out of
    the cache and so into re-reading robots.txt and the licence per page."""
    from acquisition.urls.client import FetchPurpose

    flood = ("<rsl>" + "<content/>" * 26_000 + "</rsl>").encode()
    assert len(flood) <= acquisition.urls.robots.MAX_LICENSE_BYTES
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, _LICENSED_ROBOTS),
         ("a.example", "/license.xml"): (200, flood),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )
    for purpose in FetchPurpose:
        fetch("https://a.example/page", client=client, purpose=purpose)
    requested.clear()

    fetch("https://a.example/page", client=client)

    assert "https://a.example" in cached_origins()
    assert requested == ["https://a.example/page"]


@pytest.mark.parametrize(
    ("url", "origin"),
    [
        ("https://h.example:443/", "https://h.example"),
        ("http://h.example:80/x", "http://h.example"),
        ("http://u:p@[::1]:80/", "http://[::1]"),
        ("https://h.example:80/", "https://h.example:80"),
        ("https://h.example:8443/", "https://h.example:8443"),
    ],
)
def test_origin_of_drops_the_scheme_default_port(url: str, origin: str) -> None:
    """RFC 6454 s4: an origin's port is the scheme default when omitted, so
    ``:443`` on https names the same origin as no port."""
    assert acquisition.urls.robots.origin_of(url) == origin


def test_a_licence_url_spelling_out_the_default_port_is_same_origin() -> None:
    client, requested = _client(
        {("a.example", "/robots.txt"): (
            200, b"User-agent: *\nAllow: /\nLicense: https://a.example:443/license.xml\n",
        ),
         ("a.example", "/license.xml"): (200, _scoped_rsl(("/", "free"))),
         ("a.example", "/page"): (200, b"<html>ok</html>")},
        {},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.rights_terms.no_charge is True
    assert any(url.endswith("/license.xml") for url in requested)


@pytest.mark.parametrize(
    ("url", "redacted"),
    [
        ("https://alice:pw@h.example:8443/a;k=v/b?token=q#frag", "https://h.example:8443/a/b"),
        ("/license.xml?token=q-secret", "/license.xml"),
        ("license.xml;token=q-secret", "license.xml"),
        ("mailto:alice:probe-pass@b.example?token=q-secret", "mailto:"),
        ("data:text/plain,q-secret", "data:"),
    ],
)
def test_redact_url_keeps_scheme_host_port_and_path_only(url: str, redacted: str) -> None:
    """A relative URL (a robots.txt ``License:`` value that failed to
    resolve) has no origin to print, so its path alone is kept; an opaque
    URI (``mailto:``, ``data:``) keeps only its scheme."""
    assert acquisition.urls.robots.redact_url(url) == redacted


@pytest.mark.parametrize(
    "location",
    ["mailto:alice:probe-pass@b.example?token=q-secret", "data:text/plain,alice:probe-pass"],
)
def test_an_opaque_robots_txt_redirect_is_refused_without_its_data(
    caplog: pytest.LogCaptureFixture, location: str,
) -> None:
    """A ``mailto:`` or ``data:`` Location has no host, so everything after
    the scheme is its data; the refusal names the scheme alone. (httpx
    rejects such a Location itself, so this drives the FetchText seam.)"""

    def fetch_text(url: str, _follow: bool) -> tuple[int, str, str]:
        return 302, "", location

    with caplog.at_level(logging.DEBUG):
        policy = acquisition.urls.robots.robots_policy_for(
            "https://a.example/page", fetch_text=fetch_text, user_agent="Antiek-Agent"
        )

    reason = policy.fail_open_reason or ""
    assert "not an http(s) URL" in reason
    assert _leaks(reason) == []
    assert _leaks(_all_records(caplog)) == []


# --- adversarial review of dae1d1ddd -----------------------------------------


def test_a_page_redirect_carrying_credentials_is_refused_before_they_are_sent() -> None:
    """httpx turns a Location's userinfo into an ``Authorization: Basic``
    header on the next hop, so following it would send credentials a server
    chose to another host, as robots.txt and licence hops already refuse to.
    The refusal names the hop redacted; nothing is requested from it."""
    seen_auth: list[str] = []
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        if "authorization" in request.headers:
            seen_auth.append(request.url.host or "")
        if (request.url.host, request.url.path) == ("a.example", "/page"):
            return httpx.Response(302, headers={"Location": _SECRET_LOCATION}, request=request)
        if request.url.path == "/robots.txt":
            return httpx.Response(200, content=b"User-agent: *\nAllow: /\n", request=request)
        return httpx.Response(200, content=b"<html>b</html>", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))

    with pytest.raises(httpx.RequestError, match="credentials") as excinfo:
        fetch("https://a.example/page", client=client)

    assert seen_auth == []
    assert "https://b.example/x" in str(excinfo.value)
    assert _leaks(str(excinfo.value)) == []
    assert not any(url.startswith("https://alice") or "b.example/x" in url for url in requested)


def test_a_relative_redirect_keeping_the_callers_own_credentials_is_followed() -> None:
    """Only credentials a server put in a Location are refused: a relative
    hop on the same host inherits the userinfo the caller chose to send."""
    client, requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("a.example", "/y"): (200, b"<html>y</html>")},
        {("a.example", "/page"): "/y"},
    )

    page = fetch("https://alice:probe-pass@a.example/page", client=client)

    assert page.status_code == 200
    assert requested[-1] == "https://alice:probe-pass@a.example/y"


def test_an_http_error_names_the_page_without_credentials_or_query() -> None:
    """``raise_for_status`` puts the whole URL in the exception text, and a
    caller that logs the exception logs it. The text keeps scheme, host and
    path only; the response stays on the exception for whoever needs it."""
    client, _requested = _client(
        {("a.example", "/robots.txt"): (200, b"User-agent: *\nAllow: /\n"),
         ("a.example", "/x"): (403, b"no")},
        {},
    )

    with pytest.raises(httpx.HTTPStatusError) as excinfo:
        fetch("https://alice:probe-pass@a.example/x?token=q-secret", client=client)

    assert excinfo.value.response.status_code == 403
    assert "403" in str(excinfo.value)
    assert "https://a.example/x" in str(excinfo.value)
    assert _leaks(str(excinfo.value)) == []
