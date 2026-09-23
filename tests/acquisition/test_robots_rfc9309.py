"""RFC 9309 rule evaluation and fetch-level licence hardening tests."""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.urls.client import FetchPurpose, fetch
from acquisition.urls.robots import (
    RobotsGroup,
    RobotsRule,
    parse_robots,
    robots_allows,
)

AGENT = "Antiek-Agent/0.1 (+https://antiek.ai/contact)"
SEARCH = "Antiek-Search/0.1 (+https://antiek.ai/contact)"


@pytest.fixture(autouse=True)
def clean_caches() -> Iterator[None]:
    acquisition.urls.robots.clear_robots_cache()
    yield
    acquisition.urls.robots.clear_robots_cache()


def _parser(body: str) -> acquisition.urls.robots.ParsedRobots:
    return parse_robots(body)


def test_the_exact_purpose_group_beats_a_family_group_before_it() -> None:
    parser = _parser(
        "User-agent: Antiek\nAllow: /\n\n"
        "User-agent: Antiek-Agent\nDisallow: /private\n"
    )

    assert robots_allows(parser, AGENT, "https://x/private") is False
    assert robots_allows(parser, SEARCH, "https://x/private") is True


def test_a_family_group_is_the_fallback_for_its_purposes() -> None:
    parser = _parser("User-agent: Antiek\nDisallow: /\n")

    assert robots_allows(parser, AGENT, "https://x/x") is False
    assert robots_allows(parser, SEARCH, "https://x/x") is False


def test_a_family_group_beats_the_star_group() -> None:
    parser = _parser(
        "User-agent: *\nDisallow: /\n\n"
        "User-agent: Antiek\nAllow: /\n"
    )

    assert robots_allows(parser, AGENT, "https://x/x") is True


def test_groups_for_the_same_token_are_merged() -> None:
    parser = _parser(
        "User-agent: Antiek-Agent\nDisallow: /a\n\n"
        "User-agent: Antiek-Agent\nDisallow: /b\n"
    )

    assert robots_allows(parser, AGENT, "https://x/a") is False
    assert robots_allows(parser, AGENT, "https://x/b") is False
    assert robots_allows(parser, AGENT, "https://x/c") is True


def test_the_longest_matching_rule_wins() -> None:
    parser = _parser("User-agent: *\nDisallow: /\nAllow: /public\n")

    assert robots_allows(parser, AGENT, "https://x/public/a") is True
    assert robots_allows(parser, AGENT, "https://x/other") is False


def test_allow_wins_a_length_tie() -> None:
    parser = _parser("User-agent: *\nDisallow: /a\nAllow: /a\n")

    assert robots_allows(parser, AGENT, "https://x/a") is True


def test_dollar_anchors_a_wildcard_rule() -> None:
    parser = _parser("User-agent: *\nDisallow: /*.pdf$\n")

    assert robots_allows(parser, AGENT, "https://x/doc.pdf") is False
    assert robots_allows(parser, AGENT, "https://x/doc.pdf.html") is True


def test_star_matches_a_path_segment_sequence() -> None:
    parser = _parser("User-agent: *\nDisallow: /tmp/*/secret\n")

    assert robots_allows(parser, AGENT, "https://x/tmp/x/secret") is False
    assert robots_allows(parser, AGENT, "https://x/tmp/secret") is True


def test_an_empty_disallow_allows_all() -> None:
    parser = _parser("User-agent: *\nDisallow:\n")

    assert robots_allows(parser, AGENT, "https://x/anything") is True


def test_an_unrelated_group_does_not_apply() -> None:
    parser = _parser("User-agent: OtherBot\nDisallow: /\n")

    assert robots_allows(parser, AGENT, "https://x/anything") is True


def test_every_star_group_is_merged() -> None:
    parser = _parser("User-agent: *\nAllow: /\n\nUser-agent: *\nDisallow: /private\n")

    assert robots_allows(parser, AGENT, "https://x/private") is False
    assert robots_allows(parser, AGENT, "https://x/other") is True


def test_the_fragment_is_not_matched() -> None:
    parser = _parser("User-agent: *\nDisallow: /private$\n")

    assert robots_allows(parser, AGENT, "https://x/private#section") is False
    assert robots_allows(parser, AGENT, "https://x/private/more") is True


def test_a_percent_encoded_asterisk_is_literal() -> None:
    """"%2A" is an encoded reserved character: it is not a wildcard, and (RFC
    3986) it is not equivalent to a bare "*" either, so it matches only
    "%2A"."""
    parser = _parser("User-agent: *\nDisallow: /public/%2A\n")

    assert robots_allows(parser, AGENT, "https://x/public/foo") is True
    assert robots_allows(parser, AGENT, "https://x/public/%2a") is False


def test_an_encoded_reserved_slash_is_not_a_path_separator() -> None:
    parser = _parser(
        "User-agent: *\nDisallow: /private%2Fadmin\nAllow: /private/admin/public\n"
    )

    assert robots_allows(parser, AGENT, "https://x/private%2Fadmin/public") is False
    assert robots_allows(parser, AGENT, "https://x/private/admin/public") is True


def test_an_unrelated_record_does_not_split_a_user_agent_run() -> None:
    parser = _parser(
        "User-agent: Antiek-Agent\nSitemap: https://x/s.xml\n"
        "User-agent: OtherBot\nDisallow: /private\n"
    )

    assert robots_allows(parser, AGENT, "https://x/private") is False


def test_equivalent_spellings_tie_and_allow_wins() -> None:
    parser = _parser("User-agent: *\nDisallow: /caf%C3%A9\nAllow: /café\n")

    assert robots_allows(parser, AGENT, "https://x/café") is True


def test_an_encoded_unreserved_character_is_decoded() -> None:
    parser = _parser("User-agent: *\nDisallow: /~joe\n")

    assert robots_allows(parser, AGENT, "https://x/%7Ejoe") is False


def test_consecutive_user_agent_lines_share_a_group() -> None:
    parser = _parser("User-agent: OtherBot\nUser-agent: Antiek-Agent\nDisallow: /x\n")

    assert robots_allows(parser, AGENT, "https://x/x") is False


def test_rules_before_any_user_agent_are_ignored() -> None:
    parser = _parser("Disallow: /\nUser-agent: *\nAllow: /\n")

    assert robots_allows(parser, AGENT, "https://x/x") is True


def test_equivalent_percent_encodings_match() -> None:
    parser = _parser("User-agent: *\nDisallow: /caf%C3%A9\n")

    assert robots_allows(parser, AGENT, "https://x/café") is False


def test_parse_robots_groups_records() -> None:
    parsed = parse_robots(
        "User-agent: A\nUser-agent: B\nDisallow: /a\n"
        "Sitemap: https://x/s.xml\nUser-agent: C\nAllow: /c\n"
    )

    assert parsed.groups == (
        RobotsGroup(("a", "b"), (RobotsRule(False, "/a"),)),
        RobotsGroup(("c",), (RobotsRule(True, "/c"),)),
    )


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
        status, body = routes[key]
        content_type = "text/plain" if request.url.path == "/robots.txt" else "text/html"
        return httpx.Response(
            status,
            headers={"Content-Type": content_type},
            content=body,
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler)), requested


def test_the_purpose_agent_is_used_for_the_licence_robots_check() -> None:
    client, requested = _client(
        {
            ("a.example", "/robots.txt"): (
                200,
                b"User-agent: Antiek-Agent\nDisallow: /license.xml\n\n"
                b"User-agent: *\nAllow: /\nLicense: /license.xml\n",
            ),
            ("a.example", "/license.xml"): (200, b"<rsl />"),
            ("a.example", "/page"): (200, b"<html>ok</html>"),
        },
        {},
    )

    page = fetch("https://a.example/page", client=client, purpose=FetchPurpose.AGENT)

    assert page.status_code == 200
    assert "https://a.example/license.xml" not in requested
    assert "disallowed" in (page.rights_terms.parse_error or "")


def test_a_licence_redirect_is_never_followed() -> None:
    client, requested = _client(
        {
            ("a.example", "/robots.txt"): (
                200,
                b"User-agent: *\nDisallow: /private\nLicense: /license.xml\n",
            ),
            ("a.example", "/license.xml"): (200, b"<rsl />"),
            ("a.example", "/page"): (200, b"<html>ok</html>"),
        },
        {("a.example", "/license.xml"): "/private"},
    )

    page = fetch("https://a.example/page", client=client)

    assert page.status_code == 200
    assert "https://a.example/private" not in requested
    assert "redirected" in (page.rights_terms.parse_error or "")


def test_fetch_decides_pages_by_rfc9309_group_selection() -> None:
    """The page decision itself (not just robots_allows in isolation) uses the
    most specific group: a purpose group listed AFTER a family group binds."""
    body = (
        b"User-agent: Antiek\nAllow: /\n\n"
        b"User-agent: Antiek-Agent\nDisallow: /private\n"
    )
    client, requested = _client(
        {
            ("g.example", "/robots.txt"): (200, body),
            ("g.example", "/private"): (200, b"<html>private</html>"),
        },
        {},
    )

    with pytest.raises(acquisition.urls.robots.RobotsDisallowed):
        fetch("https://g.example/private", client=client, purpose=FetchPurpose.AGENT)
    assert "https://g.example/private" not in requested

    page = fetch("https://g.example/private", client=client, purpose=FetchPurpose.SEARCH)
    assert page.status_code == 200


def test_fetch_decides_pages_by_the_longest_matching_rule() -> None:
    client, _requested = _client(
        {
            ("m.example", "/robots.txt"): (200, b"User-agent: *\nDisallow: /\nAllow: /public\n"),
            ("m.example", "/public/a"): (200, b"<html>a</html>"),
        },
        {},
    )

    assert fetch("https://m.example/public/a", client=client).status_code == 200
    with pytest.raises(acquisition.urls.robots.RobotsDisallowed):
        fetch("https://m.example/other", client=client)
