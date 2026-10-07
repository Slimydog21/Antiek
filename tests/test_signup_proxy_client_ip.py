"""Real ASGI proxy/limiter controls; not a live Cloudflare/Caddy verdict."""

import re
from pathlib import Path

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from interfaces.research.api.auth import (
    _REQUEST_RATE_LIMIT,
    _client_ip,
    _throttled,
    reset_auth_throttles,
)

TEMPLATES = Path(__file__).resolve().parents[1] / "infrastructure/ansible/templates"


@pytest.fixture
def ip_budget():
    reset_auth_throttles()

    async def observe(request: Request) -> JSONResponse:
        ip = _client_ip(request)
        refused = _throttled(f"request:{ip}", _REQUEST_RATE_LIMIT)
        return JSONResponse({"ip": ip}, status_code=429 if refused else 200)

    service = (TEMPLATES / "antiek.service.j2").read_text()
    match = re.search(r"--forwarded-allow-ips\s+(\S+)", service)
    assert match is not None, "The service must pin its upstream proxy trust"
    assert match.group(1) == "127.0.0.1"
    assert "--proxy-headers" in service
    assert "--host 127.0.0.1" in service
    app = ProxyHeadersMiddleware(
        Starlette(routes=[Route("/ip-budget", observe, methods=["POST"])]),
        trusted_hosts=match.group(1),
    )
    yield app
    reset_auth_throttles()


@pytest.mark.parametrize("peer", ["192.0.2.1", "127.0.0.2", "::1"])
def test_untrusted_peers_cannot_rotate_their_budget_with_forwarded_headers(ip_budget, peer):
    client = TestClient(ip_budget, client=(peer, 50000))
    for index in range(7):
        response = client.post("/ip-budget", headers={
            "X-Forwarded-For": f"198.51.100.{index + 1}",
            "X-Real-IP": f"198.51.100.{index + 1}",
            "CF-Connecting-IP": f"198.51.100.{index + 1}",
        })
        assert response.json()["ip"] == peer
        assert response.status_code == (200 if index < 6 else 429)


@pytest.mark.parametrize("visitor", ["198.51.100.1", "2001:db8::1"])
def test_only_caddy_normalized_forwarding_selects_the_trusted_visitor_budget(ip_budget, visitor):
    caddy = TestClient(ip_budget, client=("127.0.0.1", 50000))
    for index in range(7):
        response = caddy.post("/ip-budget", headers={
            "X-Forwarded-For": visitor,
            # These raw edge/visitor headers are not application authority.
            "X-Real-IP": f"192.0.2.{index + 1}",
            "CF-Connecting-IP": f"192.0.2.{index + 1}",
        })
        assert response.json()["ip"] == visitor
        assert response.status_code == (200 if index < 6 else 429)
    other = caddy.post("/ip-budget", headers={"X-Forwarded-For": "203.0.113.2"})
    assert other.status_code == 200
    assert other.json()["ip"] == "203.0.113.2"


def test_missing_normalized_forwarding_does_not_trust_raw_edge_headers(ip_budget):
    caddy = TestClient(ip_budget, client=("127.0.0.1", 50000))
    for index in range(7):
        response = caddy.post("/ip-budget", headers={
            "CF-Connecting-IP": f"192.0.2.{index + 1}",
            "X-Real-IP": f"192.0.2.{index + 1}",
        })
        assert response.json()["ip"] == "127.0.0.1"
        assert response.status_code == (200 if index < 6 else 429)


def test_tunnel_template_pins_edge_attribution_and_overwrites_inbound_forwarding():
    caddy = (TEMPLATES / "Caddyfile.j2").read_text()
    tunnel = (TEMPLATES / "cloudflared-config.yml.j2").read_text()
    assert "bind 127.0.0.1" in caddy
    assert "trusted_proxies static 127.0.0.1/32" in caddy
    assert "trusted_proxies_strict" in caddy
    assert "client_ip_headers CF-Connecting-IP\n" in caddy
    assert "header_up X-Forwarded-For {client_ip}" in caddy
    assert "header_up X-Real-IP {client_ip}" in caddy
    assert "header_up X-Forwarded-For {remote_host}" not in caddy
    assert "service: https://127.0.0.1:443" in tunnel
