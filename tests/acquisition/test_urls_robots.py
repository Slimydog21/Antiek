"""Boundary tests for robots.txt and RSL consultation in the URL fetcher."""

from __future__ import annotations

import logging
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest

import acquisition.urls.robots
from acquisition.urls.client import fetch
from acquisition.urls.robots import RobotsDisallowed

Route = tuple[int, str, bytes]


@contextmanager
def _local_origin() -> Iterator[SimpleNamespace]:
    """One isolated HTTP origin on 127.0.0.1: serves ``routes`` (path ->
    (status, content_type, body); anything else 404s) and logs every path it
    was asked for in ``requested``, so a test can prove a request was NOT made."""
    routes: dict[str, Route] = {}
    requested: list[str] = []

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            requested.append(self.path)
            status, content_type, body = routes.get(
                self.path, (404, "text/plain", b"not found")
            )
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    httpd.daemon_threads = True
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield SimpleNamespace(
            base=f"http://127.0.0.1:{httpd.server_port}",
            port=httpd.server_port,
            routes=routes,
            requested=requested,
        )
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


@pytest.fixture
def server() -> Iterator[SimpleNamespace]:
    with _local_origin() as origin:
        yield origin


@pytest.fixture
def second_server() -> Iterator[SimpleNamespace]:
    """A second, distinct origin for the cross-origin directive test."""
    with _local_origin() as origin:
        yield origin


@pytest.fixture(autouse=True)
def clean_robots_cache():
    acquisition.urls.robots.clear_robots_cache()
    yield
    acquisition.urls.robots.clear_robots_cache()


def test_disallowed_path_raises_before_the_page_is_requested(server) -> None:
    server.routes["/robots.txt"] = (
        200,
        "text/plain",
        b"User-agent: *\nDisallow: /private/\n",
    )
    server.routes["/public/page"] = (
        200,
        "text/html",
        b"<html><body>ok</body></html>",
    )

    with pytest.raises(RobotsDisallowed) as raised:
        fetch(f"{server.base}/private/page")

    assert raised.value.robots_url == f"{server.base}/robots.txt"
    assert "/robots.txt" in server.requested
    assert "/private/page" not in server.requested

    page = fetch(f"{server.base}/public/page")

    assert page.status_code == 200
    assert page.robots_fail_open_reason is None


def test_rsl_license_directive_and_license_xml_surface_on_fetched_html(server) -> None:
    server.routes["/robots.txt"] = (
        200,
        "text/plain",
        b"User-agent: *\nAllow: /\nLicense: /license.xml\n",
    )
    server.routes["/license.xml"] = (
        200,
        "application/xml",
        (
            b'<rsl xmlns="https://rslstandard.org/rsl"><content url="/">'
            b"<license><permits type=\"usage\">all</permits>"
            b'<payment type="attribution"/></license></content></rsl>'
        ),
    )
    server.routes["/article"] = (200, "text/html", b"<html><body>article</body></html>")

    page = fetch(f"{server.base}/article")

    terms = page.rights_terms
    assert terms.source == "rsl_license_xml"
    assert terms.payment_types == ("attribution",)
    assert terms.no_charge is True
    assert terms.license_url == f"{server.base}/license.xml"
    assert terms.permits == ("usage:all",)


def test_missing_robots_txt_fails_open_with_a_visible_warning(server, caplog) -> None:
    server.routes["/page"] = (200, "text/html", b"<html><body>visible</body></html>")
    caplog.set_level(logging.WARNING, logger="acquisition.urls.robots")

    page = fetch(f"{server.base}/page")

    assert page.status_code == 200
    assert b"visible" in page.body
    assert "HTTP 404" in page.robots_fail_open_reason
    assert page.rights_terms.declared is False
    warnings = [
        record.getMessage()
        for record in caplog.records
        if record.name == "acquisition.urls.robots"
    ]
    assert any("failing OPEN" in message for message in warnings)


def test_robots_txt_is_fetched_once_per_origin(server) -> None:
    server.routes["/robots.txt"] = (200, "text/plain", b"User-agent: *\nAllow: /\n")
    server.routes["/one"] = (200, "text/html", b"<html>one</html>")
    server.routes["/two"] = (200, "text/html", b"<html>two</html>")

    first = fetch(f"{server.base}/one")
    second = fetch(f"{server.base}/two")

    assert first.status_code == 200
    assert second.status_code == 200
    assert server.requested.count("/robots.txt") == 1


def test_cross_origin_license_url_is_recorded_not_followed(server, second_server) -> None:
    license_url = f"http://127.0.0.1:{second_server.port}/license.xml"
    server.routes["/robots.txt"] = (
        200,
        "text/plain",
        f"User-agent: *\nLicense: {license_url}\n".encode(),
    )
    second_server.routes["/license.xml"] = (
        200,
        "application/xml",
        (
            b'<rsl xmlns="https://rslstandard.org/rsl"><content url="/">'
            b'<license><payment type="attribution"/></license></content></rsl>'
        ),
    )
    server.routes["/page"] = (200, "text/html", b"<html><body>A</body></html>")

    page = fetch(f"{server.base}/page")

    assert page.rights_terms.license_url == license_url
    assert "cross-origin" in page.rights_terms.parse_error
    assert second_server.requested == []


def test_the_robots_txt_url_itself_is_never_blocked_by_its_rules(server) -> None:
    server.routes["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /\n")

    page = fetch(f"{server.base}/robots.txt")

    assert page.status_code == 200
    assert page.robots_fail_open_reason is None
    assert server.requested == ["/robots.txt"]


class _FakeClock:
    """A monotonic clock the test advances by hand (no sleeping)."""

    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now


def test_an_unreachable_robots_txt_is_retried_after_the_short_window(
    server, monkeypatch
) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(acquisition.urls.robots, "_clock", clock)
    server.routes["/robots.txt"] = (503, "text/plain", b"down")
    server.routes["/private/page"] = (200, "text/html", b"<html>p</html>")

    first = fetch(f"{server.base}/private/page")
    assert "unreachable (HTTP 503)" in first.robots_fail_open_reason

    # The site comes back with a rule. Inside the retry window the cached
    # fail-open still stands; after it, the rule is read and enforced.
    server.routes["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /private/\n")
    clock.now += acquisition.urls.robots.UNREACHABLE_RETRY_S - 1
    fetch(f"{server.base}/private/page")
    assert server.requested.count("/robots.txt") == 1

    clock.now += 2
    with pytest.raises(RobotsDisallowed):
        fetch(f"{server.base}/private/page")
    assert server.requested.count("/robots.txt") == 2


def test_an_applied_policy_is_reread_after_the_rfc_9309_day(server, monkeypatch) -> None:
    clock = _FakeClock()
    monkeypatch.setattr(acquisition.urls.robots, "_clock", clock)
    server.routes["/robots.txt"] = (200, "text/plain", b"User-agent: *\nAllow: /\n")
    server.routes["/page"] = (200, "text/html", b"<html>p</html>")

    fetch(f"{server.base}/page")
    server.routes["/robots.txt"] = (200, "text/plain", b"User-agent: *\nDisallow: /\n")

    clock.now += acquisition.urls.robots.ROBOTS_CACHE_TTL_S - 1
    assert fetch(f"{server.base}/page").status_code == 200

    clock.now += 2
    with pytest.raises(RobotsDisallowed):
        fetch(f"{server.base}/page")
