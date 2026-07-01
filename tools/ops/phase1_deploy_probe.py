"""Operator probe for OA-009 Phase 1 deployment verification.

The probe checks the two public surfaces named by OA-009:

* the API health endpoint reports a post-Sprint-21 shape with providers and a
  real build SHA;
* the public app marketplace route is reachable without authentication.

Passing this probe supports OA-009, but OA-009 is not closed until the operator
has deployed the intended commit and recorded the production evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Any, Sequence

DEFAULT_API_URL = "https://api.antiek.ai"
DEFAULT_APP_MARKETPLACE_URL = "https://antiek.ai/marketplace"
AUTH_PATH_MARKERS = ("/login", "/sign-in", "/signin", "/auth")
SHA_RE = re.compile(r"^[0-9a-f]{6,40}$")
REQUIRED_HEALTH_KEYS = frozenset(
    {
        "status",
        "param_version",
        "schema_version",
        "subscriber_count",
        "registered_providers",
        "build_sha",
        "flywheel_ready",
        "knowledge_reuse_count",
    }
)


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status_code: int
    content_type: str
    body: str


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class Phase1DeployProbeResult:
    status: str
    api_url: str
    health_url: str
    marketplace_url: str
    final_marketplace_url: str
    expected_sha: str | None
    checks: list[ProbeCheck]
    does_not_close_oa009: bool = True


def fetch_url(url: str, *, accept: str, timeout_s: float = 10.0) -> FetchResult:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "antiek-phase1-deploy-probe/1.0",
            "Accept": accept,
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            raw = resp.read(1_000_000)
            return FetchResult(
                url=url,
                final_url=resp.geturl(),
                status_code=int(resp.status),
                content_type=resp.headers.get("content-type", ""),
                body=raw.decode("utf-8", errors="replace"),
            )
    except urllib.error.HTTPError as exc:
        raw = exc.read(1_000_000)
        return FetchResult(
            url=url,
            final_url=exc.geturl(),
            status_code=int(exc.code),
            content_type=exc.headers.get("content-type", ""),
            body=raw.decode("utf-8", errors="replace"),
        )
    except urllib.error.URLError as exc:
        return FetchResult(
            url=url,
            final_url=url,
            status_code=0,
            content_type="",
            body=f"URL error: {exc.reason}",
        )


def _health_url(api_url: str) -> str:
    base = api_url.rstrip("/")
    return base if base.endswith("/health") else base + "/health"


def _is_success(status_code: int) -> bool:
    return 200 <= status_code < 300


def _looks_like_auth_redirect(final_url: str) -> bool:
    path = urllib.parse.urlparse(final_url).path.lower()
    return any(marker in path for marker in AUTH_PATH_MARKERS)


def _looks_like_html(fetch: FetchResult) -> bool:
    content_type = fetch.content_type.lower()
    body = fetch.body.lstrip().lower()
    return (
        "text/html" in content_type
        or body.startswith("<!doctype html")
        or body.startswith("<html")
    )


def _health_checks(
    fetch: FetchResult,
    *,
    expected_sha: str | None,
) -> list[ProbeCheck]:
    checks = [
        ProbeCheck(
            name="health_http_2xx",
            passed=_is_success(fetch.status_code),
            detail=f"status={fetch.status_code} final_url={fetch.final_url}",
        )
    ]
    try:
        payload: Any = json.loads(fetch.body)
    except json.JSONDecodeError as exc:
        checks.append(
            ProbeCheck(
                name="health_json",
                passed=False,
                detail=f"invalid JSON: {exc}",
            )
        )
        return checks

    checks.append(
        ProbeCheck(
            name="health_json",
            passed=isinstance(payload, dict),
            detail=f"type={type(payload).__name__}",
        )
    )
    if not isinstance(payload, dict):
        return checks

    missing = sorted(REQUIRED_HEALTH_KEYS - payload.keys())
    checks.append(
        ProbeCheck(
            name="health_post_sprint21_shape",
            passed=not missing,
            detail="all required keys present" if not missing else f"missing={missing}",
        )
    )
    checks.append(
        ProbeCheck(
            name="health_status_ok",
            passed=payload.get("status") == "ok",
            detail=f"status={payload.get('status')!r}",
        )
    )

    providers = payload.get("registered_providers")
    checks.append(
        ProbeCheck(
            name="health_registered_providers",
            passed=isinstance(providers, list) and bool(providers),
            detail=(
                ",".join(str(provider) for provider in providers)
                if isinstance(providers, list)
                else f"type={type(providers).__name__}"
            ),
        )
    )

    build_sha = payload.get("build_sha")
    sha_shaped = isinstance(build_sha, str) and bool(SHA_RE.fullmatch(build_sha))
    checks.append(
        ProbeCheck(
            name="health_build_sha_shaped",
            passed=sha_shaped,
            detail=f"build_sha={build_sha!r}",
        )
    )
    if expected_sha:
        checks.append(
            ProbeCheck(
                name="health_expected_sha",
                passed=build_sha == expected_sha,
                detail=f"build_sha={build_sha!r} expected_sha={expected_sha!r}",
            )
        )

    checks.append(
        ProbeCheck(
            name="health_flywheel_fields_typed",
            passed=(
                isinstance(payload.get("flywheel_ready"), bool)
                and isinstance(payload.get("knowledge_reuse_count"), int)
            ),
            detail=(
                f"flywheel_ready={payload.get('flywheel_ready')!r} "
                f"knowledge_reuse_count={payload.get('knowledge_reuse_count')!r}"
            ),
        )
    )
    return checks


def _marketplace_checks(fetch: FetchResult) -> list[ProbeCheck]:
    return [
        ProbeCheck(
            name="marketplace_http_2xx",
            passed=_is_success(fetch.status_code),
            detail=f"status={fetch.status_code} final_url={fetch.final_url}",
        ),
        ProbeCheck(
            name="marketplace_not_auth_redirect",
            passed=not _looks_like_auth_redirect(fetch.final_url),
            detail=f"final_url={fetch.final_url}",
        ),
        ProbeCheck(
            name="marketplace_html",
            passed=_looks_like_html(fetch),
            detail=f"content_type={fetch.content_type or 'unknown'}",
        ),
    ]


def probe_phase1_deploy(
    *,
    api_url: str = DEFAULT_API_URL,
    marketplace_url: str = DEFAULT_APP_MARKETPLACE_URL,
    expected_sha: str | None = None,
    timeout_s: float = 10.0,
) -> Phase1DeployProbeResult:
    normalized_expected = expected_sha.strip().lower() if expected_sha else None
    health_url = _health_url(api_url)
    health = fetch_url(health_url, accept="application/json", timeout_s=timeout_s)
    marketplace = fetch_url(
        marketplace_url,
        accept="text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        timeout_s=timeout_s,
    )
    checks = [
        *_health_checks(health, expected_sha=normalized_expected),
        *_marketplace_checks(marketplace),
    ]
    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    return Phase1DeployProbeResult(
        status=status,
        api_url=api_url,
        health_url=health_url,
        marketplace_url=marketplace_url,
        final_marketplace_url=marketplace.final_url,
        expected_sha=normalized_expected,
        checks=checks,
    )


def format_text(result: Phase1DeployProbeResult) -> str:
    lines = [
        f"phase1-deploy-probe: {result.status}",
        f"health_url: {result.health_url}",
        f"marketplace_url: {result.marketplace_url}",
        f"final_marketplace_url: {result.final_marketplace_url}",
    ]
    if result.expected_sha:
        lines.append(f"expected_sha: {result.expected_sha}")
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa009_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the public API health and marketplace route for OA-009. "
            "Does not close OA-009 by itself."
        )
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"API base URL or /health URL. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--marketplace-url",
        default=DEFAULT_APP_MARKETPLACE_URL,
        help=f"Public marketplace route URL. Default: {DEFAULT_APP_MARKETPLACE_URL}",
    )
    parser.add_argument(
        "--expected-sha",
        help="Expected deployed git SHA. When present, build_sha must match.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout must be positive")
    result = probe_phase1_deploy(
        api_url=args.api_url,
        marketplace_url=args.marketplace_url,
        expected_sha=args.expected_sha,
        timeout_s=args.timeout,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
