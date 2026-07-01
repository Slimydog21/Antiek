"""Operator probe for OA-016 advertiser run-rate verification.

OA-016 closes only when the operator has actually signed advertisers. This
probe packages the mechanical evidence: at least three unique advertisers with
active campaigns and aggregate monthly run-rate above $5K, computed from the
existing advertiser campaign store.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path

from substrate.advertisers import CampaignStatus, SqliteAdvertiserStore

DEFAULT_MIN_ACTIVE_ADVERTISERS = 3
DEFAULT_MIN_MONTHLY_RUN_RATE_CENTS = 500_000


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class AdvertiserRunRateProbeResult:
    status: str
    store_path: str
    active_campaign_count: int
    active_advertiser_count: int
    monthly_run_rate_cents: int
    min_active_advertisers: int
    min_monthly_run_rate_cents: int
    active_campaign_ids: list[str]
    checks: list[ProbeCheck]
    does_not_close_oa016: bool = True


def probe_advertiser_run_rate(
    *,
    store_path: Path,
    min_active_advertisers: int = DEFAULT_MIN_ACTIVE_ADVERTISERS,
    min_monthly_run_rate_cents: int = DEFAULT_MIN_MONTHLY_RUN_RATE_CENTS,
) -> AdvertiserRunRateProbeResult:
    if not store_path.exists():
        return AdvertiserRunRateProbeResult(
            status="FAIL",
            store_path=str(store_path),
            active_campaign_count=0,
            active_advertiser_count=0,
            monthly_run_rate_cents=0,
            min_active_advertisers=min_active_advertisers,
            min_monthly_run_rate_cents=min_monthly_run_rate_cents,
            active_campaign_ids=[],
            checks=[
                ProbeCheck(
                    name="store_exists",
                    passed=False,
                    detail=f"missing store path: {store_path}",
                )
            ],
        )

    store = SqliteAdvertiserStore(str(store_path))
    active = [
        campaign
        for campaign in store.list_campaigns()
        if campaign.status == CampaignStatus.ACTIVE
    ]
    active_advertisers = {campaign.advertiser_id for campaign in active}
    monthly_run_rate_cents = sum(
        campaign.daily_budget_cents * 30 for campaign in active
    )
    active_campaign_ids = sorted(campaign.campaign_id for campaign in active)
    checks = [
        ProbeCheck(
            name="store_exists",
            passed=True,
            detail=f"store path exists: {store_path}",
        ),
        ProbeCheck(
            name="active_advertiser_count",
            passed=len(active_advertisers) >= min_active_advertisers,
            detail=(
                f"{len(active_advertisers)} unique active advertisers "
                f">= {min_active_advertisers}"
            ),
        ),
        ProbeCheck(
            name="monthly_run_rate",
            passed=monthly_run_rate_cents >= min_monthly_run_rate_cents,
            detail=(
                f"{monthly_run_rate_cents} cents "
                f">= {min_monthly_run_rate_cents} cents"
            ),
        ),
    ]
    return AdvertiserRunRateProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        store_path=str(store_path),
        active_campaign_count=len(active),
        active_advertiser_count=len(active_advertisers),
        monthly_run_rate_cents=monthly_run_rate_cents,
        min_active_advertisers=min_active_advertisers,
        min_monthly_run_rate_cents=min_monthly_run_rate_cents,
        active_campaign_ids=active_campaign_ids,
        checks=checks,
    )


def format_text(result: AdvertiserRunRateProbeResult) -> str:
    lines = [
        f"advertiser-run-rate-probe: {result.status}",
        f"store_path: {result.store_path}",
        f"active_campaign_count: {result.active_campaign_count}",
        f"active_advertiser_count: {result.active_advertiser_count}",
        f"monthly_run_rate_cents: {result.monthly_run_rate_cents}",
        f"active_campaign_ids: {','.join(result.active_campaign_ids)}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa016_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Verify OA-016 advertiser campaign count and monthly run-rate. "
            "Does not close OA-016 by itself."
        )
    )
    parser.add_argument(
        "--store-path",
        required=True,
        type=Path,
        help="Path to the advertiser SQLite store.",
    )
    parser.add_argument(
        "--min-active-advertisers",
        type=int,
        default=DEFAULT_MIN_ACTIVE_ADVERTISERS,
        help=f"Minimum unique active advertisers. Default: {DEFAULT_MIN_ACTIVE_ADVERTISERS}",
    )
    parser.add_argument(
        "--min-monthly-run-rate-cents",
        type=int,
        default=DEFAULT_MIN_MONTHLY_RUN_RATE_CENTS,
        help=(
            "Minimum aggregate active daily_budget_cents * 30. "
            f"Default: {DEFAULT_MIN_MONTHLY_RUN_RATE_CENTS}"
        ),
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
    if args.min_active_advertisers < 1:
        parser.error("--min-active-advertisers must be >= 1")
    if args.min_monthly_run_rate_cents < 1:
        parser.error("--min-monthly-run-rate-cents must be >= 1")
    result = probe_advertiser_run_rate(
        store_path=args.store_path.expanduser().resolve(),
        min_active_advertisers=args.min_active_advertisers,
        min_monthly_run_rate_cents=args.min_monthly_run_rate_cents,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
