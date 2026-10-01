"""Provider balance authority must precede a request or a dollar label."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from interfaces.research.api import byot_usage_routes
from runtime.byok.secret_str import SecretStr
from substrate.byot_usage.balance.mimo import fetch_mimo_balance
from substrate.byot_usage.balance.zhipu_glm import fetch_zhipu_glm_balance
from substrate.byot_usage.ledger import ByotUsageLedger


class _NoProviderRequest:
    def get(self, *args: Any, **kwargs: Any) -> None:
        pytest.fail("Undocumented provider balance endpoint was called")

    def Client(self, **kwargs: Any) -> None:  # noqa: N802 - mirrors httpx.Client
        pytest.fail("Undocumented provider balance transport was opened")


@pytest.fixture()
def ledger(tmp_path: Path) -> ByotUsageLedger:
    return ByotUsageLedger(tmp_path / "usage.sqlite3")


@pytest.mark.parametrize(
    ("catalog_id", "base_url"),
    [
        ("zhipu_glm", "https://api.z.ai/api/paas/v4"),
        ("mimo", "https://api.mimo.xiaomi.com/v1"),
    ],
)
def test_undocumented_native_balance_does_not_open_transport(
    catalog_id: str,
    base_url: str,
    ledger: ByotUsageLedger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(byot_usage_routes, "httpx", _NoProviderRequest())
    snapshot = byot_usage_routes._fetch_balance(  # noqa: SLF001 - dispatch seam
        catalog_id=catalog_id,
        key=SecretStr("sk-test-native-key"),
        base_url=base_url,
        ledger=ledger,
        api_key_id=f"key-{catalog_id}",
        owner_user_id="user-A",
    )
    assert snapshot.catalog_id == catalog_id
    assert snapshot.kind == "unavailable"
    assert snapshot.balance_usd is None
    assert snapshot.native_balances is None
    assert snapshot.note == "Provider has not documented a native balance API."


@pytest.mark.parametrize(
    ("fetch", "base_url"),
    [
        (fetch_zhipu_glm_balance, "https://api.z.ai/api/paas/v4"),
        (fetch_mimo_balance, "https://api.mimo.xiaomi.com/v1"),
    ],
)
def test_direct_adapter_also_refuses_guessed_endpoint(
    fetch: Any,
    base_url: str,
) -> None:
    snapshot = fetch(
        SecretStr("sk-test-native-key"),
        base_url=base_url,
        http=_NoProviderRequest(),
    )
    assert snapshot.kind == "unavailable"
    assert snapshot.balance_usd is None


def test_xai_uses_antiek_meter_without_a_provider_request(
    ledger: ByotUsageLedger,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(byot_usage_routes, "httpx", _NoProviderRequest())
    ledger.record_settlement("key-xai", "user-A", 250, "a" * 64)
    ledger.set_limit("key-xai", "user-A", 5000)
    snapshot = byot_usage_routes._fetch_balance(  # noqa: SLF001 - dispatch seam
        catalog_id="xai",
        key=SecretStr("sk-test-native-key"),
        base_url="https://api.x.ai/v1",
        ledger=ledger,
        api_key_id="key-xai",
        owner_user_id="user-A",
    )
    assert snapshot.kind == "spend_history"
    assert snapshot.spend_usd == 2.50
    assert snapshot.budget_usd == 50.00
    assert snapshot.balance_usd is None
