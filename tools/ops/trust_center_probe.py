"""Operator probe for OA-013 Trust Center publication.

The probe checks that the public Trust Center route is reachable without
authentication and, when an API URL is provided, that the Trust Center
publication endpoint returns the expected public payload shape. Passing this
probe supports OA-013, but OA-013 is not closed until it is run against the
production domains and the operator records the deploy evidence.
"""

from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from typing import Sequence

DEFAULT_APP_URL = "https://antiek.ai/trust"
DEFAULT_API_URL = "https://api.antiek.ai/trust-center"
AUTH_PATH_MARKERS = ("/login", "/sign-in", "/signin", "/auth")
REQUIRED_API_KEYS = frozenset(
    {
        "differential_privacy_epsilon_budgets",
        "deletion_sla_days",
        "substrate_controls",
        "compliance_frameworks",
        "loop_3_unlock_status",
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
class TrustCenterProbeResult:
    status: str
    app_url: str
    final_app_url: str
    api_url: str | None
    checks: list[ProbeCheck]
    does_not_close_oa013: bool = True


def fetch_url(url: str, *, timeout_s: float = 10.0) -> FetchResult:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "antiek-trust-center-probe/1.0",
            "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
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


def _api_payload_checks(fetch: FetchResult) -> list[ProbeCheck]:
    checks: list[ProbeCheck] = [
        ProbeCheck(
            name="api_http_2xx",
            passed=_is_success(fetch.status_code),
            detail=f"status={fetch.status_code} final_url={fetch.final_url}",
        )
    ]
    try:
        payload = json.loads(fetch.body)
    except json.JSONDecodeError as exc:
        checks.append(
            ProbeCheck(
                name="api_json",
                passed=False,
                detail=f"invalid JSON: {exc}",
            )
        )
        return checks

    checks.append(
        ProbeCheck(
            name="api_json",
            passed=isinstance(payload, dict),
            detail=f"type={type(payload).__name__}",
        )
    )
    if not isinstance(payload, dict):
        return checks

    missing = sorted(REQUIRED_API_KEYS - payload.keys())
    checks.append(
        ProbeCheck(
            name="api_publication_shape",
            passed=not missing,
            detail="all required keys present" if not missing else f"missing={missing}",
        )
    )
    budgets = payload.get("differential_privacy_epsilon_budgets")
    checks.append(
        ProbeCheck(
            name="api_dp_budgets_present",
            passed=isinstance(budgets, dict) and bool(budgets),
            detail=(
                f"budget_count={len(budgets)}"
                if isinstance(budgets, dict)
                else f"type={type(budgets).__name__}"
            ),
        )
    )
    return checks


def probe_trust_center(
    *,
    app_url: str = DEFAULT_APP_URL,
    api_url: str | None = DEFAULT_API_URL,
    timeout_s: float = 10.0,
) -> TrustCenterProbeResult:
    app = fetch_url(app_url, timeout_s=timeout_s)
    checks = [
        ProbeCheck(
            name="app_http_2xx",
            passed=_is_success(app.status_code),
            detail=f"status={app.status_code} final_url={app.final_url}",
        ),
        ProbeCheck(
            name="app_not_auth_redirect",
            passed=not _looks_like_auth_redirect(app.final_url),
            detail=f"final_url={app.final_url}",
        ),
        ProbeCheck(
            name="app_html",
            passed=_looks_like_html(app),
            detail=f"content_type={app.content_type or 'unknown'}",
        ),
        ProbeCheck(
            name="app_mentions_trust",
            passed="trust" in app.body.lower(),
            detail="body contains trust copy marker",
        ),
    ]

    if api_url:
        api = fetch_url(api_url, timeout_s=timeout_s)
        checks.extend(_api_payload_checks(api))

    status = "PASS" if all(check.passed for check in checks) else "FAIL"
    return TrustCenterProbeResult(
        status=status,
        app_url=app_url,
        final_app_url=app.final_url,
        api_url=api_url,
        checks=checks,
    )


def format_text(result: TrustCenterProbeResult) -> str:
    lines = [
        f"trust-center-probe: {result.status}",
        f"app_url: {result.app_url}",
        f"final_app_url: {result.final_app_url}",
    ]
    if result.api_url:
        lines.append(f"api_url: {result.api_url}")
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa013_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify the public Trust Center route and optional publication API. "
            "Does not close OA-013 by itself."
        )
    )
    parser.add_argument(
        "--app-url",
        default=DEFAULT_APP_URL,
        help=f"Public Trust Center page URL. Default: {DEFAULT_APP_URL}",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=(
            "Trust Center publication API URL. Pass an empty string to skip. "
            f"Default: {DEFAULT_API_URL}"
        ),
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
    api_url = args.api_url.strip() or None
    if args.timeout <= 0:
        parser.error("--timeout must be positive")

    result = probe_trust_center(
        app_url=args.app_url,
        api_url=api_url,
        timeout_s=args.timeout,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
