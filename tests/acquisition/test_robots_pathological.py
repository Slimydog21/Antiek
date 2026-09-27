"""A host's own robots.txt must not be able to stall the fetcher.

The rules are the host's text and the URL can be the host's redirect target,
so both inputs to a robots decision are adversarial. A matcher that turns
each ``*`` into a backtracking ``.*`` spends time polynomial in the wildcard
count while holding the GIL: "/*a*a*a*a*a*a*a*ab" against a 41-character path
took 11 s. These tests bound the time of such decisions and check that the
non-backtracking matcher still decides every rule the way the regex did.
"""

from __future__ import annotations

import logging
import random
import re
import time
from collections.abc import Callable, Iterator

import httpx
import pytest

import acquisition.urls.robots
from acquisition.urls.client import fetch
from acquisition.urls.robots import (
    MAX_ROBOTS_BYTES,
    RobotsDisallowed,
    parse_robots,
    robots_allows,
)

AGENT = "Antiek-Agent/0.1 (+https://antiek.ai/contact)"

# New matcher: microseconds. The backtracking regex: seconds to hours.
DECISION_DEADLINE_S = 0.5


@pytest.fixture(autouse=True)
def clean_caches() -> Iterator[None]:
    acquisition.urls.robots.clear_robots_cache()
    yield
    acquisition.urls.robots.clear_robots_cache()


def _timed_allows(robots_txt: str, url: str) -> tuple[bool, float]:
    parsed = parse_robots(robots_txt)
    start = time.perf_counter()
    allowed = robots_allows(parsed, AGENT, url)
    return allowed, time.perf_counter() - start


def _file_of(rule_for: Callable[[int], str], limit: int = MAX_ROBOTS_BYTES) -> str:
    """A robots.txt as large as the fetcher will parse, of ``rule_for(i)`` lines."""
    lines = ["User-agent: *"]
    size = len(lines[0]) + 1
    i = 0
    while True:
        line = rule_for(i)
        if size + len(line) + 1 > limit:
            return "\n".join(lines) + "\n"
        lines.append(line)
        size += len(line) + 1
        i += 1


@pytest.mark.parametrize(
    ("wildcards", "path_length"),
    [(8, 41), (12, 400), (40, 4000)],
    ids=["8-wildcards-41-chars", "12-wildcards-400-chars", "40-wildcards-4000-chars"],
)
def test_a_many_wildcard_rule_is_decided_without_backtracking(
    wildcards: int, path_length: int
) -> None:
    """The critic's shape: every "a" can be placed many ways, and the missing
    "b" makes a backtracking matcher try them all before it fails."""
    rule = "/" + "*a" * wildcards + "b"
    url = "https://h.example/" + "a" * (path_length - 1)

    allowed, elapsed = _timed_allows(f"User-agent: *\nDisallow: {rule}\n", url)

    assert allowed is True
    assert elapsed < DECISION_DEADLINE_S, f"{elapsed:.3f}s for {wildcards} wildcards"


def test_a_many_wildcard_rule_still_matches_when_it_should() -> None:
    rule = "/" + "*a" * 40 + "b"
    url = "https://h.example/" + "a" * 3999 + "b"

    allowed, elapsed = _timed_allows(f"User-agent: *\nDisallow: {rule}\n", url)

    assert allowed is False
    assert elapsed < DECISION_DEADLINE_S


def _regex_decides(pattern: str, path: str) -> bool:
    """The backtracking definition, fine on inputs this small."""
    anchored = pattern.endswith("$")
    body = pattern[:-1] if anchored else pattern
    regex = ".*".join(re.escape(segment) for segment in body.split("*"))
    return re.match(regex + ("\\Z" if anchored else ""), path) is not None


def test_the_matcher_decides_every_rule_as_the_backtracking_regex_does() -> None:
    """Differential check over random short patterns and paths drawn from the
    characters that make greedy placement hard ("a", "b", "/", "*", "$")."""
    rng = random.Random(9309)
    disagreements: list[tuple[str, str]] = []
    for _ in range(4000):
        pattern = "/" + "".join(rng.choice("ab/**") for _ in range(rng.randint(0, 7)))
        if rng.random() < 0.3:
            pattern += "$"
        path = "/" + "".join(rng.choice("ab/") for _ in range(rng.randint(0, 9)))
        parsed = parse_robots(f"User-agent: *\nDisallow: {pattern}\n")
        disallowed = not robots_allows(parsed, AGENT, f"https://h.example{path}")
        if disallowed != _regex_decides(pattern, path):
            disagreements.append((pattern, path))

    assert disagreements == []


def test_a_hostile_file_at_the_size_limit_is_decided_quickly_and_refused() -> None:
    """512 KiB of distinct wildcard rules against a 16 KiB path would cost
    billions of comparisons; the cost cap stops the decision and refuses the
    URL rather than skipping rules it never checked."""
    robots_txt = _file_of(lambda i: f"Disallow:/*ab{i}")
    url = "https://h.example/" + "a" * 16383

    allowed, elapsed = _timed_allows(robots_txt, url)

    assert allowed is False
    assert elapsed < DECISION_DEADLINE_S


def test_a_decision_over_the_cost_cap_is_refused_loudly(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_MATCH_COST", 10_000)
    parsed = parse_robots("User-agent: *\n" + "".join(f"Disallow: /*z{i}\n" for i in range(50)))

    with caplog.at_level(logging.WARNING, logger="acquisition.urls.robots"):
        long_path_allowed = robots_allows(parsed, AGENT, "https://h.example/" + "a" * 999)
    short_path_allowed = robots_allows(parsed, AGENT, "https://h.example/aaaa")

    assert long_path_allowed is False
    assert "character comparisons" in caplog.text
    assert short_path_allowed is True


def test_the_cost_cap_leaves_a_large_real_shaped_file_alone() -> None:
    """Hundreds of wildcard rules against a long URL (the costliest of twelve
    real files measured spends 9.7M comparisons at 16 KiB) stay far under the
    cap and are decided by their rules, not refused."""
    rules = "".join(f"Disallow: /*/private-{i}/*.json$\n" for i in range(300))
    robots_txt = "User-agent: *\n" + rules + "Disallow: /*/tree/*/secret\n"
    query = "&".join(f"k{i}=v{i}" for i in range(500))
    open_url = f"https://h.example/org/repo/tree/main/README?{query}"
    secret_url = f"https://h.example/org/repo/tree/main/secret?{query}"
    assert len(open_url) > 4000

    open_allowed, open_elapsed = _timed_allows(robots_txt, open_url)
    secret_allowed, _ = _timed_allows(robots_txt, secret_url)

    assert open_allowed is True
    assert secret_allowed is False
    assert open_elapsed < DECISION_DEADLINE_S


def _client(robots_txt: bytes) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, headers={"Content-Type": "text/plain"}, content=robots_txt,
                request=request,
            )
        return httpx.Response(
            200, headers={"Content-Type": "text/html"}, content=b"<html>ok</html>",
            request=request,
        )

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_is_not_stalled_by_a_hostile_rule() -> None:
    """End to end. Four wildcards held fetch() for 12.7 s on a 251-character
    path; this rule has ten."""
    client = _client(b"User-agent: *\nDisallow: /" + b"*a" * 10 + b"b\n")

    start = time.perf_counter()
    page = fetch("https://h.example/" + "a" * 250, client=client)
    elapsed = time.perf_counter() - start

    assert page.status_code == 200
    assert elapsed < DECISION_DEADLINE_S * 2


def test_fetch_refuses_a_page_whose_rules_cost_too_much(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(acquisition.urls.robots, "MAX_MATCH_COST", 10_000)
    client = _client(b"User-agent: *\n" + b"".join(b"Disallow: /*z%d\n" % i for i in range(50)))

    with pytest.raises(RobotsDisallowed):
        fetch("https://h.example/" + "a" * 999, client=client)
