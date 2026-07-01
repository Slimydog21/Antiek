from __future__ import annotations

import json

from substrate.advertisers import (
    Advertiser,
    CampaignStatus,
    SqliteAdvertiserStore,
    create_campaign,
)
from tools.ops import advertiser_run_rate_probe


def _seed_campaign(
    store: SqliteAdvertiserStore,
    *,
    advertiser_id: str,
    daily_budget_cents: int,
    status: CampaignStatus = CampaignStatus.ACTIVE,
) -> None:
    store.upsert_advertiser(
        Advertiser(
            advertiser_id=advertiser_id,
            display_name=f"Advertiser {advertiser_id}",
            sector="recruiting",
            contact_email=f"{advertiser_id}@example.com",
            stripe_customer_id=None,
        )
    )
    create_campaign(
        store,
        advertiser_id=advertiser_id,
        sector="recruiting",
        intent="hiring_manager",
        creative_headline="Hire better operators",
        creative_url="https://example.com/hire",
        daily_budget_cents=daily_budget_cents,
        status=status,
    )


def test_advertiser_run_rate_probe_passes_at_oa016_threshold(tmp_path):
    store_path = tmp_path / "advertisers.sqlite"
    store = SqliteAdvertiserStore(str(store_path))
    for idx in range(3):
        _seed_campaign(
            store,
            advertiser_id=f"adv-{idx}",
            daily_budget_cents=5_600,
        )

    result = advertiser_run_rate_probe.probe_advertiser_run_rate(
        store_path=store_path,
    )

    assert result.status == "PASS"
    assert result.active_advertiser_count == 3
    assert result.monthly_run_rate_cents == 504_000


def test_advertiser_run_rate_probe_fails_duplicate_active_advertiser(tmp_path):
    store_path = tmp_path / "advertisers.sqlite"
    store = SqliteAdvertiserStore(str(store_path))
    _seed_campaign(store, advertiser_id="adv-1", daily_budget_cents=20_000)
    _seed_campaign(store, advertiser_id="adv-1", daily_budget_cents=20_000)
    _seed_campaign(store, advertiser_id="adv-2", daily_budget_cents=20_000)

    result = advertiser_run_rate_probe.probe_advertiser_run_rate(
        store_path=store_path,
    )

    assert result.status == "FAIL"
    by_check = {check.name: check for check in result.checks}
    assert by_check["active_advertiser_count"].passed is False
    assert by_check["monthly_run_rate"].passed is True


def test_advertiser_run_rate_probe_ignores_inactive_campaigns(tmp_path):
    store_path = tmp_path / "advertisers.sqlite"
    store = SqliteAdvertiserStore(str(store_path))
    _seed_campaign(store, advertiser_id="adv-1", daily_budget_cents=20_000)
    _seed_campaign(
        store,
        advertiser_id="adv-2",
        daily_budget_cents=20_000,
        status=CampaignStatus.PAUSED,
    )
    _seed_campaign(store, advertiser_id="adv-3", daily_budget_cents=20_000)

    result = advertiser_run_rate_probe.probe_advertiser_run_rate(
        store_path=store_path,
    )

    assert result.status == "FAIL"
    assert result.active_advertiser_count == 2
    assert result.monthly_run_rate_cents == 1_200_000


def test_advertiser_run_rate_probe_missing_store_is_fail(tmp_path):
    result = advertiser_run_rate_probe.probe_advertiser_run_rate(
        store_path=tmp_path / "missing.sqlite",
    )

    assert result.status == "FAIL"
    assert result.checks[0].name == "store_exists"


def test_advertiser_run_rate_probe_json_cli(tmp_path, capsys):
    store_path = tmp_path / "advertisers.sqlite"
    store = SqliteAdvertiserStore(str(store_path))
    for idx in range(3):
        _seed_campaign(
            store,
            advertiser_id=f"adv-{idx}",
            daily_budget_cents=5_600,
        )

    exit_code = advertiser_run_rate_probe.main(
        ["--store-path", str(store_path), "--json"]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa016"] is True
