"""Tests for balance adapters — fixture parsing and schema-drift degradation.

Verifies:
- DeepSeek adapter parses fixture JSON into normalised balance
- Kimi adapter parses fixture JSON into normalised balance
- Spend-history adapter computes remaining from ledger
- Malformed / error responses yield ``unavailable`` (not an exception)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from runtime.byok.secret_str import SecretStr
from substrate.byot_usage.balance.deepseek import fetch_deepseek_balance
from substrate.byot_usage.balance.kimi import fetch_kimi_balance
from substrate.byot_usage.balance.spend_history import fetch_spend_history_balance
from substrate.byot_usage.ledger import ByotUsageLedger

# ---------------------------------------------------------------------------
# Fake httpx-like response for MockTransport tests
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(
        self,
        json_data: Any,
        *,
        status_code: int = 200,
        raise_for_status_error: Exception | None = None,
    ) -> None:
        self._json = json_data
        self.status_code = status_code
        self._raise_err = raise_for_status_error

    def raise_for_status(self) -> None:
        if self._raise_err:
            raise self._raise_err

    def json(self) -> Any:
        return self._json


class _FakeHTTP:
    """Configurable fake HTTP client."""

    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_url: str | None = None
        self.last_headers: dict[str, str] | None = None

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> _FakeResponse:
        self.last_url = url
        self.last_headers = headers
        return self._response


# ---------------------------------------------------------------------------
# DeepSeek adapter
# ---------------------------------------------------------------------------


def test_deepseek_parses_valid_fixture() -> None:
    fixture = {
        "is_available": True,
        "balance_infos": [
            {
                "currency": "CNY",
                "total_balance": "150.50",
                "granted_balance": "100.00",
                "topped_up_balance": "50.50",
            }
        ],
    }
    http = _FakeHTTP(_FakeResponse(fixture))
    key = SecretStr("sk-test-deepseek-key")

    result = fetch_deepseek_balance(key, base_url="https://api.deepseek.com", http=http)

    assert result.catalog_id == "deepseek"
    assert result.kind == "balance_native"
    assert result.balance_usd == 150.50
    assert result.granted_usd == 100.00
    assert result.note is None
    assert http.last_url == "https://api.deepseek.com/user/balance"
    assert http.last_headers == {"Authorization": "Bearer sk-test-deepseek-key"}


def test_deepseek_unavailable_on_http_error() -> None:
    http = _FakeHTTP(
        _FakeResponse(
            {},
            status_code=429,
            raise_for_status_error=Exception("429 Too Many Requests"),
        )
    )
    key = SecretStr("sk-test-key")

    result = fetch_deepseek_balance(key, base_url="https://api.deepseek.com", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None
    assert "429" in result.note or "Too Many" in result.note


def test_deepseek_unavailable_on_malformed_json() -> None:
    # Missing balance_infos key
    http = _FakeHTTP(_FakeResponse({"unexpected": "shape"}))
    key = SecretStr("sk-test-key")

    result = fetch_deepseek_balance(key, base_url="https://api.deepseek.com", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None
    assert "schema drift" in result.note


def test_deepseek_unavailable_on_empty_balance_infos() -> None:
    http = _FakeHTTP(_FakeResponse({"is_available": True, "balance_infos": []}))
    key = SecretStr("sk-test-key")

    result = fetch_deepseek_balance(key, base_url="https://api.deepseek.com", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None


# ---------------------------------------------------------------------------
# Kimi / Moonshot adapter
# ---------------------------------------------------------------------------


def test_kimi_parses_valid_fixture() -> None:
    fixture = {
        "status": "ok",
        "data": {
            "available_balance": "75.25",
            "voucher_balance": "25.00",
            "cash_balance": "50.25",
        },
    }
    http = _FakeHTTP(_FakeResponse(fixture))
    key = SecretStr("sk-test-kimi-key")

    result = fetch_kimi_balance(key, base_url="https://api.moonshot.ai/v1", http=http)

    assert result.catalog_id == "kimi"
    assert result.kind == "balance_native"
    assert result.balance_usd == 75.25
    assert result.granted_usd == 50.25
    assert result.note is None
    assert http.last_url == "https://api.moonshot.ai/v1/users/me/balance"


def test_kimi_unavailable_on_http_error() -> None:
    http = _FakeHTTP(
        _FakeResponse(
            {},
            status_code=500,
            raise_for_status_error=Exception("500 Internal Server Error"),
        )
    )
    key = SecretStr("sk-test-key")

    result = fetch_kimi_balance(key, base_url="https://api.moonshot.ai/v1", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None


def test_kimi_unavailable_on_schema_drift() -> None:
    # Wrong nesting — "data" is missing
    http = _FakeHTTP(_FakeResponse({"status": "ok"}))
    key = SecretStr("sk-test-key")

    result = fetch_kimi_balance(key, base_url="https://api.moonshot.ai/v1", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None
    assert "schema drift" in result.note


# ---------------------------------------------------------------------------
# Spend-history adapter (OpenAI / no-live-call pattern)
# ---------------------------------------------------------------------------


def test_spend_history_computes_remaining_from_ledger(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-oai", "user-A", 450, "a" * 64)
    ledger.set_limit("key-oai", "user-A", 2000)

    result = fetch_spend_history_balance(
        SecretStr("sk-test"),
        base_url="https://api.openai.com/v1",
        http=_FakeHTTP(_FakeResponse({})),  # not used
        ledger=ledger,
        api_key_id="key-oai",
        owner_user_id="user-A",
    )

    assert result.catalog_id == "openai"
    assert result.kind == "spend_history"
    assert result.spend_usd == 4.50
    assert result.budget_usd == 20.00


def test_spend_history_no_limit_shows_spend_only(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-oai", "user-A", 100, "a" * 64)

    result = fetch_spend_history_balance(
        SecretStr("sk-test"),
        base_url="https://api.openai.com/v1",
        http=_FakeHTTP(_FakeResponse({})),
        ledger=ledger,
        api_key_id="key-oai",
        owner_user_id="user-A",
    )

    assert result.kind == "spend_history"
    assert result.spend_usd == 1.00
    assert result.budget_usd is None


def test_spend_history_no_ledger_row_returns_zero_spend(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    result = fetch_spend_history_balance(
        SecretStr("sk-test"),
        base_url="https://api.openai.com/v1",
        http=_FakeHTTP(_FakeResponse({})),
        ledger=ledger,
        api_key_id="key-unknown",
        owner_user_id="user-A",
    )

    assert result.kind == "spend_history"
    assert result.spend_usd == 0.0
    assert result.budget_usd is None
    assert result.note is not None


def test_spend_history_custom_catalog_id(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-ant", "user-A", 200, "a" * 64)

    result = fetch_spend_history_balance(
        SecretStr("sk-ant-test"),
        base_url="https://api.anthropic.com",
        http=_FakeHTTP(_FakeResponse({})),
        ledger=ledger,
        api_key_id="key-ant",
        owner_user_id="user-A",
        catalog_id="anthropic",
    )

    assert result.catalog_id == "anthropic"
    assert result.kind == "spend_history"
