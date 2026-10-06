"""The resource CSP on both hosts must keep the SPA working and stay tight.

Guards the 2026-09-27 full resource CSP in
``infrastructure/ansible/templates/Caddyfile.j2`` (api.antiek.ai) and
``apps/reading/public/_headers`` (antiek.ai). Two failure modes this
catches at CI instead of in a browser:

1. The two hosts drift apart again (they disagreed about which headers
   exist at all before 2026-09-26).
2. A "tightening" drops a source the SPA is proven to need (cross-origin
   API calls on the Pages host, blob: media, data: images) or adds
   unsafe-eval / inline script. A wrong CSP breaks the app silently,
   which is exactly why the full policy was deferred until now.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_CADDY = _REPO / "infrastructure" / "ansible" / "templates" / "Caddyfile.j2"
_HEADERS = _REPO / "apps" / "reading" / "public" / "_headers"


def _csp_from_caddy(text: str) -> str:
    match = re.search(r'Content-Security-Policy "([^"]+)"', text)
    assert match, "Caddyfile.j2 carries no quoted Content-Security-Policy value"
    return match.group(1)


def _csp_from_headers(text: str) -> str:
    match = re.search(r"^  Content-Security-Policy: (.+)$", text, re.MULTILINE)
    assert match, "_headers carries no Content-Security-Policy line"
    return match.group(1).strip()


@pytest.fixture(scope="module")
def policies() -> dict[str, str]:
    caddy = _csp_from_caddy(_CADDY.read_text(encoding="utf-8"))
    headers = _csp_from_headers(_HEADERS.read_text(encoding="utf-8"))
    return {"caddy": caddy, "headers": headers}


def _directives(policy: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for part in policy.split(";"):
        tokens = part.strip().split()
        if not tokens:
            continue
        out[tokens[0]] = tokens[1:]
    return out


def test_hosts_state_the_same_policy(policies: dict[str, str]) -> None:
    assert policies["caddy"] == policies["headers"]


def test_microphone_is_available_only_to_the_same_origin() -> None:
    caddy = re.search(r'Permissions-Policy "([^"]+)"', _CADDY.read_text())
    pages = re.search(r"^  Permissions-Policy: (.+)$", _HEADERS.read_text(), re.MULTILINE)
    assert caddy and pages
    for policy in (caddy.group(1), pages.group(1)):
        directives = dict(part.strip().split("=", 1) for part in policy.split(","))
        # Speak still requests browser consent; foreign frames get no mic.
        assert directives == {
            "camera": "()", "microphone": "(self)", "geolocation": "()",
        }


def test_frame_ancestors_unchanged(policies: dict[str, str]) -> None:
    for name, policy in policies.items():
        assert _directives(policy)["frame-ancestors"] == ["'self'"], name


def test_no_eval_or_inline_script(policies: dict[str, str]) -> None:
    for name, policy in policies.items():
        assert "unsafe-eval" not in policy, name
        script = _directives(policy)["script-src"]
        assert "unsafe-inline" not in script, name


def test_spa_sources_present(policies: dict[str, str]) -> None:
    # Each entry maps to a shipped surface; see the Caddyfile comment block.
    required = {
        "img-src": {"'self'", "data:"},
        "style-src": {"'self'", "'unsafe-inline'"},
        # Pages-hosted SPA calls api.antiek.ai and wss://api.antiek.ai.
        "connect-src": {"'self'", "https://api.antiek.ai", "wss://api.antiek.ai"},
        # ReadAloud TTS playback, style/document preview iframes.
        "media-src": {"'self'", "blob:"},
        "frame-src": {"'self'", "blob:"},
        "worker-src": {"'self'"},
        "object-src": {"'none'"},
    }
    for name, policy in policies.items():
        got = _directives(policy)
        for key, sources in required.items():
            assert sources <= set(got[key]), f"{name}: {key} missing {sources - set(got[key])}"
