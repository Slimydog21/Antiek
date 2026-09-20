#!/usr/bin/env python3
"""Staged auth transport + policy probe for magic-link login (SPR-04).

Runs five checks against a live Antiek API base URL:

  1. ``GET /health`` — Layer A: API reachable (transport baseline).
  2. ``OPTIONS /auth/request`` with ``Origin`` — Layer A: CORS preflight
     for the Pages → API cross-origin login submit.
  3. ``POST /auth/request`` with JSON — Layer B: policy path completes
     with enumeration guard ``{"sent": true}`` (dry-run email defaults
     to a non-allowlisted address so no mail is sent).
  4. ``GET /auth/passkey/status`` without a session cookie — Layer B: the
     passkey discovery route is public and does not leak credential counts.
  5. ``GET /auth/me`` without session cookie — Layer B: middleware returns
     structured ``401`` with ``operator_auth_required``.

Composes with ``tools/prod_parity/check.py`` on ``main`` (that script owns
SHA/flywheel parity); this module is the auth-specific staged probe and
does not duplicate ``/health`` parity logic.

Exit codes:
    0 — every stage passed.
    1 — one or more stages failed (transport/policy assertion mismatch).
    2 — misconfiguration (invalid ``--base-url``, or could not reach host).

Usage::

    python tools/auth_probe.py --base-url https://api.antiek.ai
    python tools/auth_probe.py --base-url http://127.0.0.1:8000 --origin http://localhost:5173
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

_USER_AGENT = "antiek-auth-probe/1.0 (+https://antiek.ai)"
_DEFAULT_PROBE_EMAIL = "auth-probe-nonallowlisted@antiek.ai"


@dataclass(frozen=True)
class StageResult:
    name: str
    layer: str
    pass_: bool
    http_code: int | None
    detail: str

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "layer": self.layer,
            "pass": self.pass_,
            "http_code": self.http_code,
            "detail": self.detail,
        }


def _validate_base_url(raw: str) -> str:
    parsed = urlparse(raw.strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError(
            f"invalid --base-url {raw!r}: need http(s)://host[:port] "
            "(no path required)"
        )
    return f"{parsed.scheme}://{parsed.netloc}"


def _request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
    timeout: float = 15.0,
) -> tuple[int, dict[str, str], bytes]:
    hdrs = {
        "Accept": "application/json",
        "User-Agent": _USER_AGENT,
        **(headers or {}),
    }
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), exc.read()


def _json_body(raw: bytes) -> Any:
    if not raw:
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


def stage_health(base_url: str) -> StageResult:
    url = f"{base_url}/health"
    try:
        code, _headers, body = _request("GET", url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            "health",
            "A",
            False,
            None,
            f"GET /health failed: {exc}",
        )
    payload = _json_body(body)
    ok = code == 200 and isinstance(payload, dict) and payload.get("status") == "ok"
    detail = (
        "status ok"
        if ok
        else f"expected 200 with status=ok, got http={code} body={payload!r}"
    )
    return StageResult("health", "A", ok, code, detail)


def stage_cors_preflight(base_url: str, origin: str) -> StageResult:
    url = f"{base_url}/auth/request"
    try:
        code, headers, _body = _request(
            "OPTIONS",
            url,
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            "cors_preflight_auth_request",
            "A",
            False,
            None,
            f"OPTIONS /auth/request preflight failed: {exc}",
        )

    allow_origin = headers.get("access-control-allow-origin", "")
    allow_methods = headers.get("access-control-allow-methods", "").upper()
    origin_ok = allow_origin == origin or allow_origin == "*"
    methods_ok = "POST" in allow_methods or allow_methods == "*"
    ok = code in (200, 204) and origin_ok and methods_ok
    detail = (
        f"preflight ok (Allow-Origin={allow_origin!r}, Allow-Methods={allow_methods!r})"
        if ok
        else (
            "expected 200 or 204 with Allow-Origin matching --origin and POST in "
            f"Allow-Methods; got http={code} "
            f"Allow-Origin={allow_origin!r} Allow-Methods={allow_methods!r}"
        )
    )
    return StageResult("cors_preflight_auth_request", "A", ok, code, detail)


def stage_auth_request(base_url: str, origin: str, email: str) -> StageResult:
    url = f"{base_url}/auth/request"
    payload = json.dumps({"email": email}).encode("utf-8")
    try:
        code, _headers, body = _request(
            "POST",
            url,
            headers={
                "Content-Type": "application/json",
                "Origin": origin,
            },
            body=payload,
        )
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            "auth_request_dry_run",
            "B",
            False,
            None,
            f"POST /auth/request failed: {exc}",
        )

    parsed = _json_body(body)
    ok = code == 200 and parsed == {"sent": True}
    detail = (
        "sent:true (enumeration guard; dry-run email is non-allowlisted)"
        if ok
        else f"expected 200 {{\"sent\": true}}, got http={code} body={parsed!r}"
    )
    return StageResult("auth_request_dry_run", "B", ok, code, detail)


def stage_auth_me_unauthenticated(base_url: str) -> StageResult:
    url = f"{base_url}/auth/me"
    try:
        code, _headers, body = _request("GET", url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            "auth_me_without_cookie",
            "B",
            False,
            None,
            f"GET /auth/me failed: {exc}",
        )

    parsed = _json_body(body)
    error = parsed.get("error", {}) if isinstance(parsed, dict) else {}
    code_ok = error.get("code") == "operator_auth_required"
    ok = code == 401 and code_ok
    detail = (
        "401 operator_auth_required (session gate closed without cookie)"
        if ok
        else (
            f"expected 401 with error.code=operator_auth_required, "
            f"got http={code} body={parsed!r}"
        )
    )
    return StageResult("auth_me_without_cookie", "B", ok, code, detail)


def stage_passkey_status_unauthenticated(base_url: str) -> StageResult:
    url = f"{base_url}/auth/passkey/status"
    try:
        code, _headers, body = _request("GET", url)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return StageResult(
            "passkey_status_without_cookie",
            "B",
            False,
            None,
            f"GET /auth/passkey/status failed: {exc}",
        )

    parsed = _json_body(body)
    available = parsed.get("available") if isinstance(parsed, dict) else None
    count = parsed.get("count") if isinstance(parsed, dict) else object()
    ok = code == 200 and isinstance(available, bool) and count is None
    detail = (
        f"public passkey discovery ready (available={available!r}; count concealed)"
        if ok
        else (
            "expected 200 with boolean available and count=null, "
            f"got http={code} body={parsed!r}"
        )
    )
    return StageResult("passkey_status_without_cookie", "B", ok, code, detail)


def run_stages(base_url: str, origin: str, email: str) -> list[StageResult]:
    return [
        stage_health(base_url),
        stage_cors_preflight(base_url, origin),
        stage_auth_request(base_url, origin, email),
        stage_passkey_status_unauthenticated(base_url),
        stage_auth_me_unauthenticated(base_url),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Staged auth probe: health → CORS → auth/request → "
            "passkey/status → auth/me."
        ),
    )
    parser.add_argument(
        "--base-url",
        default="https://api.antiek.ai",
        help="API origin (default: https://api.antiek.ai)",
    )
    parser.add_argument(
        "--origin",
        default="https://antiek.ai",
        help="Browser Origin for CORS stages (default: https://antiek.ai)",
    )
    parser.add_argument(
        "--email",
        default=None,
        help=(
            "Email for POST /auth/request dry-run (default: non-allowlisted "
            f"{_DEFAULT_PROBE_EMAIL!r})"
        ),
    )
    args = parser.parse_args(argv)

    try:
        base_url = _validate_base_url(args.base_url)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

    email = (args.email or _DEFAULT_PROBE_EMAIL).strip().lower()
    results = run_stages(base_url, args.origin.strip(), email)

    for stage in results:
        print(json.dumps(stage.to_json()))

    if all(s.pass_ for s in results):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
