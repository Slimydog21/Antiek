"""Native balance dispatch — which catalog ids read provider credit.

Verifies, against a stubbed transport (no live net):
- ``zhipu_glm`` and ``mimo`` dispatch to their native adapters and resolve to
  ``kind == "balance_native"``;
- ``xai`` has no native adapter and resolves to ``kind == "spend_history"``
  (Antiek's own meter), so a meter is never presented as provider credit;
- both new adapters parse their declared fixture and degrade to
  ``unavailable`` on HTTP error and on schema drift.

The dispatch tests go through the REAL ``_fetch_balance`` in
``byot_usage_routes`` (not a monkeypatched one) with ``httpx.Client`` swapped
for a ``MockTransport``-backed client. Deleting an entry from
``native_adapters`` sends that id down the spend-history path and turns the
matching test red — that is the mutation check the spec asks for.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from interfaces.research.api import byot_usage_routes
from runtime.byok.secret_str import SecretStr
from substrate.byot_usage.balance.mimo import fetch_mimo_balance
from substrate.byot_usage.balance.zhipu_glm import fetch_zhipu_glm_balance
from substrate.byot_usage.ledger import ByotUsageLedger

_FIXTURE = {"data": {"total_balance": "42.50", "granted_balance": "10.00"}}


class _StubHttpx:
    """Stand-in for the ``httpx`` module attribute inside the routes module.

    ``_fetch_balance`` does ``with httpx.Client(timeout=...) as client``; this
    returns a real ``httpx.Client`` bound to a ``MockTransport`` so the
    adapter's request path and auth header are exercised without any socket.
    """

    def __init__(self, handler: Any) -> None:
        self._handler = handler
        self.requests: list[httpx.Request] = []

    def Client(self, **kwargs: Any) -> httpx.Client:  # noqa: N802 - mirrors httpx.Client
        def _record(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return self._handler(request)

        return httpx.Client(transport=httpx.MockTransport(_record), **kwargs)


@pytest.fixture()
def ledger(tmp_path: Path) -> ByotUsageLedger:
    return ByotUsageLedger(tmp_path / "usage.sqlite3")


@pytest.fixture()
def stub_httpx(monkeypatch: pytest.MonkeyPatch) -> _StubHttpx:
    stub = _StubHttpx(lambda _request: httpx.Response(200, json=_FIXTURE))
    monkeypatch.setattr(byot_usage_routes, "httpx", stub)
    return stub


def _dispatch(
    catalog_id: str,
    base_url: str,
    ledger: ByotUsageLedger,
) -> Any:
    return byot_usage_routes._fetch_balance(  # noqa: SLF001 - the seam under test
        catalog_id=catalog_id,
        key=SecretStr("sk-test-native-key"),
        base_url=base_url,
        ledger=ledger,
        api_key_id=f"key-{catalog_id}",
        owner_user_id="user-A",
    )


# ---------------------------------------------------------------------------
# Dispatch through the real native_adapters map
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("catalog_id", "base_url", "expected_path"),
    [
        ("zhipu_glm", "https://api.z.ai/api/paas/v4", "/api/paas/v4/user/balance"),
        ("mimo", "https://api.mimo.xiaomi.com/v1", "/v1/user/balance"),
    ],
)
def test_native_adapter_resolves_balance_native(
    catalog_id: str,
    base_url: str,
    expected_path: str,
    ledger: ByotUsageLedger,
    stub_httpx: _StubHttpx,
) -> None:
    snapshot = _dispatch(catalog_id, base_url, ledger)

    assert snapshot.catalog_id == catalog_id
    assert snapshot.kind == "balance_native"
    assert snapshot.balance_usd == 42.50
    assert snapshot.granted_usd == 10.00
    assert snapshot.note is None
    # The stubbed transport saw exactly one bearer-authed GET at the declared path.
    assert [r.method for r in stub_httpx.requests] == ["GET"]
    assert stub_httpx.requests[0].url.path == expected_path
    assert stub_httpx.requests[0].headers["Authorization"] == "Bearer sk-test-native-key"


def test_xai_has_no_native_adapter_and_resolves_spend_history(
    ledger: ByotUsageLedger,
    stub_httpx: _StubHttpx,
) -> None:
    ledger.record_settlement("key-xai", "user-A", 250, "a" * 64)
    ledger.set_limit("key-xai", "user-A", 5000)

    snapshot = _dispatch("xai", "https://api.x.ai/v1", ledger)

    assert snapshot.catalog_id == "xai"
    assert snapshot.kind == "spend_history"
    assert snapshot.spend_usd == 2.50
    assert snapshot.budget_usd == 50.00
    assert snapshot.balance_usd is None
    # No provider call happens on the meter path.
    assert stub_httpx.requests == []


# ---------------------------------------------------------------------------
# Adapter fixture parsing + degradation (direct, no dispatch)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, json_data: Any, *, error: Exception | None = None) -> None:
        self._json = json_data
        self._error = error

    def raise_for_status(self) -> None:
        if self._error:
            raise self._error

    def json(self) -> Any:
        return self._json


class _FakeHTTP:
    def __init__(self, response: _FakeResponse) -> None:
        self._response = response
        self.last_url: str | None = None

    def get(self, url: str, *, headers: dict[str, str] | None = None) -> _FakeResponse:
        del headers
        self.last_url = url
        return self._response


@pytest.mark.parametrize(
    ("fetch", "catalog_id", "base_url", "expected_url"),
    [
        (
            fetch_zhipu_glm_balance,
            "zhipu_glm",
            "https://api.z.ai/api/paas/v4",
            "https://api.z.ai/api/paas/v4/user/balance",
        ),
        (
            fetch_mimo_balance,
            "mimo",
            "https://api.mimo.xiaomi.com/v1",
            "https://api.mimo.xiaomi.com/v1/user/balance",
        ),
    ],
)
def test_adapter_parses_declared_fixture(
    fetch: Any, catalog_id: str, base_url: str, expected_url: str,
) -> None:
    http = _FakeHTTP(_FakeResponse(_FIXTURE))

    result = fetch(SecretStr("sk-test"), base_url=base_url, http=http)

    assert result.catalog_id == catalog_id
    assert result.kind == "balance_native"
    assert result.balance_usd == 42.50
    assert result.granted_usd == 10.00
    assert http.last_url == expected_url


@pytest.mark.parametrize("fetch", [fetch_zhipu_glm_balance, fetch_mimo_balance])
def test_adapter_unavailable_on_http_error(fetch: Any) -> None:
    http = _FakeHTTP(_FakeResponse({}, error=Exception("429 Too Many Requests")))

    result = fetch(SecretStr("sk-test"), base_url="https://example.invalid/v1", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None
    assert "429" in result.note


@pytest.mark.parametrize("fetch", [fetch_zhipu_glm_balance, fetch_mimo_balance])
def test_adapter_unavailable_on_schema_drift(fetch: Any) -> None:
    http = _FakeHTTP(_FakeResponse({"unexpected": "shape"}))

    result = fetch(SecretStr("sk-test"), base_url="https://example.invalid/v1", http=http)

    assert result.kind == "unavailable"
    assert result.note is not None
    assert "schema drift" in result.note
