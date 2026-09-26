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
    select_license,
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


def test_dot_segments_are_resolved_before_matching() -> None:
    parser = _parser("User-agent: *\nDisallow: /private\n")

    assert robots_allows(parser, AGENT, "https://x/public/../private") is False
    assert robots_allows(parser, AGENT, "https://x/public/%2E%2E/private") is False
    assert robots_allows(parser, AGENT, "https://x/public/./ok") is True


def test_fetch_refuses_a_dot_segment_route_to_a_disallowed_path() -> None:
    client, requested = _client(
        {
            ("d.example", "/robots.txt"): (
                200,
                b"User-agent: *\nDisallow: /private\n",
            ),
            ("d.example", "/private"): (200, b"<html>private</html>"),
        },
        {},
    )

    with pytest.raises(acquisition.urls.robots.RobotsDisallowed):
        fetch("https://d.example/public/../private", client=client)

    assert "https://d.example/private" not in requested


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
    """"%2A" is not a wildcard: it matches only an asterisk (written "*" or
    "%2A" in the URI), never an arbitrary segment."""
    parser = _parser("User-agent: *\nDisallow: /public/%2A\n")

    assert robots_allows(parser, AGENT, "https://x/public/foo") is True
    assert robots_allows(parser, AGENT, "https://x/public/%2a") is False
    assert robots_allows(parser, AGENT, "https://x/public/*") is False


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


def test_a_group_licence_beats_the_global_one_and_falls_back_to_it() -> None:
    parsed = _parser(
        "License: /free.xml\nUser-agent: Antiek-Agent\nLicense: /paid.xml\nAllow: /\n\n"
        "User-agent: Antiek-Search\nAllow: /\n"
    )

    assert select_license(parsed, AGENT) == "/paid.xml"
    assert select_license(parsed, SEARCH) == "/free.xml"


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
                b"User-agent: Antiek-Agent\nLicense: /license.xml\n"
                b"Disallow: /license.xml\n\nUser-agent: *\nAllow: /\n",
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


def test_each_purpose_gets_its_own_licence_terms() -> None:
    free_rsl = (
        b'<rsl><content url="/"><license><payment type="free"/></license>'
        b"</content></rsl>"
    )
    paid_rsl = (
        b'<rsl><content url="/"><license><payment type="purchase"/></license>'
        b"</content></rsl>"
    )
    client, requested = _client(
        {
            ("l.example", "/robots.txt"): (
                200,
                b"License: /free.xml\nUser-agent: Antiek-Agent\n"
                b"License: /paid.xml\nAllow: /\n\nUser-agent: *\nAllow: /\n",
            ),
            ("l.example", "/free.xml"): (200, free_rsl),
            ("l.example", "/paid.xml"): (200, paid_rsl),
            ("l.example", "/a"): (200, b"<html>a</html>"),
            ("l.example", "/b"): (200, b"<html>b</html>"),
        },
        {},
    )

    search_page = fetch(
        "https://l.example/a", client=client, purpose=FetchPurpose.SEARCH
    )
    agent_page = fetch(
        "https://l.example/b", client=client, purpose=FetchPurpose.AGENT
    )

    assert search_page.rights_terms.payment_types == ("free",)
    assert agent_page.rights_terms.payment_types == ("purchase",)
    assert requested.count("https://l.example/robots.txt") == 1


def test_a_licence_disallowed_for_one_purpose_does_not_poison_another() -> None:
    client, _requested = _client(
        {
            ("p.example", "/robots.txt"): (
                200,
                b"License: /license.xml\nUser-agent: Antiek-Search\n"
                b"Disallow: /license.xml\n\nUser-agent: *\nAllow: /\n",
            ),
            ("p.example", "/license.xml"): (
                200,
                b'<rsl><content url="/"><license><payment type="free"/></license>'
                b"</content></rsl>",
            ),
            ("p.example", "/a"): (200, b"<html>a</html>"),
            ("p.example", "/b"): (200, b"<html>b</html>"),
        },
        {},
    )

    search_page = fetch(
        "https://p.example/a", client=client, purpose=FetchPurpose.SEARCH
    )
    agent_page = fetch(
        "https://p.example/b", client=client, purpose=FetchPurpose.AGENT
    )

    assert "disallowed" in (search_page.rights_terms.parse_error or "")
    assert agent_page.rights_terms.payment_types == ("free",)


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


def test_a_literal_special_character_in_the_uri_matches_its_encoded_pattern() -> None:
    """RFC 9309 s2.2.3's own examples: "%2A" in a pattern matches a literal
    "*" in the URI, and "%24" matches a literal "$"."""
    star = _parser("User-agent: *\nDisallow: /path/file-with-a-%2A.html\n")
    dollar = _parser("User-agent: *\nDisallow: /path/foo-%24\n")

    assert robots_allows(star, AGENT, "https://x/path/file-with-a-*.html") is False
    assert robots_allows(star, AGENT, "https://x/path/file-with-a-b.html") is True
    assert robots_allows(dollar, AGENT, "https://x/path/foo-$") is False
    assert robots_allows(dollar, AGENT, "https://x/path/foo-") is True


def test_a_byte_order_mark_does_not_hide_the_first_group() -> None:
    parser = _parser("﻿User-agent: *\nDisallow: /private\n")

    assert robots_allows(parser, AGENT, "https://x/private") is False
