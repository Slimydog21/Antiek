from __future__ import annotations

import duckdb
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from interfaces.research.api.licensed_research_access import create_licensed_research_router
from substrate.licensed_access import (
    Derivation,
    LicensedAccessConflict,
    LicensedAccessDenied,
    LicensedAccessUnavailable,
    TollBitLicensedAccess,
)


class FixedDeriver:
    def __init__(self, result=None):
        self.result = result or Derivation(
            "Example citation", "bounded snippet", "bounded summary"
        )

    def derive(self, body, *, canonical_url):
        return self.result


def _service(tmp_path, handler):
    return TollBitLicensedAccess(
        api_key="secret-never-persist", user_agent="antiek-agent/1",
        signing_key=b"s" * 32, db_path=str(tmp_path / "licensed.duckdb"),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_paid_content_is_transient_and_replay_makes_no_network_call(tmp_path):
    calls = []
    raw = "LICENSED RAW CANARY that must never persist"

    def handler(request):
        calls.append(request)
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5000, "currency": "USD"},
                "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                            "permissions": [{"name": "PARTIAL_USE"}]},
            }]}])
        if request.url.path.endswith("/tokens/content"):
            assert request.headers["TollbitKey"] == "secret-never-persist"
            return httpx.Response(200, json={"token": "one-time-secret-token"})
        assert request.headers["TollbitToken"] == "one-time-secret-token"
        return httpx.Response(200, json={
            "content": {"body": raw},
            "rate": {"price": {"priceMicros": 5000, "currency": "USD"},
                     "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1", "permissions": [{"name": "PARTIAL_USE"}]}},
        })

    service = _service(tmp_path, handler)
    first = service.acquire(owner_id="alice", url="https://EXAMPLE.com/a",
                            max_price_micros=6000,
                            idempotency_key="idem-123456789012", deriver=FixedDeriver())
    replay = service.acquire(owner_id="alice", url="https://example.com/a",
                             max_price_micros=6000,
                             idempotency_key="idem-123456789012", deriver=FixedDeriver())
    assert replay == first
    assert len(calls) == 3
    db_bytes = (tmp_path / "licensed.duckdb").read_bytes()
    assert raw.encode() not in db_bytes
    assert b"one-time-secret-token" not in db_bytes
    assert b"secret-never-persist" not in db_bytes
    with duckdb.connect(str(tmp_path / "licensed.duckdb"), read_only=True) as con:
        columns = {r[1] for r in con.execute("PRAGMA table_info('licensed_research_receipts')").fetchall()}
    assert not {"raw_body", "body", "content", "token", "api_key"} & columns


@pytest.mark.parametrize("status", [402, 403, 500])
def test_provider_failures_fail_closed_without_receipt(tmp_path, status):
    service = _service(tmp_path, lambda _: httpx.Response(status, json={"detail": "secret"}))
    error = LicensedAccessDenied if status in {402, 403} else Exception
    with pytest.raises(error):
        service.acquire(owner_id="alice", url="https://example.com/a",
                        max_price_micros=6000, idempotency_key="idem-123456789012",
                        deriver=FixedDeriver(Derivation("c", "s", "x")))


def test_quote_drift_fails_closed(tmp_path):
    n = 0
    def handler(request):
        nonlocal n
        n += 1
        if n == 1:
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"},
                "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1", "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if n == 2:
            return httpx.Response(200, json={"token": "token"})
        return httpx.Response(200, json={"content": {"body": "raw"}, "rate": {
            "price": {"priceMicros": 6, "currency": "USD"},
            "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1", "permissions": [{"name": "PARTIAL_USE"}]}}})
    with pytest.raises(LicensedAccessDenied, match="denied"):
        _service(tmp_path, handler).acquire(
            owner_id="alice", url="https://example.com/a", max_price_micros=10,
            idempotency_key="idem-123456789012", deriver=FixedDeriver(Derivation("c", "s", "x")))


def test_tampered_signed_owner_receipt_fails_closed(tmp_path):
    def handler(request):
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"},
                "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                            "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if request.url.path.endswith("/tokens/content"):
            return httpx.Response(200, json={"token": "token"})
        return httpx.Response(200, json={"content": {"body": "raw"}, "rate": {
            "price": {"priceMicros": 5, "currency": "USD"},
            "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1", "permissions": [{"name": "PARTIAL_USE"}]}}})

    service = _service(tmp_path, handler)
    kwargs = dict(owner_id="alice", url="https://example.com/a", max_price_micros=10,
                  idempotency_key="idem-123456789012",
                  deriver=FixedDeriver(Derivation("c", "s", "x")))
    service.acquire(**kwargs)
    with duckdb.connect(str(tmp_path / "licensed.duckdb")) as con:
        con.execute("UPDATE licensed_research_receipts SET owner_identity_digest=?", ["0" * 64])
    with pytest.raises(LicensedAccessDenied, match="integrity"):
        service.acquire(**kwargs)


def test_sent_unknown_is_never_blindly_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"},
                "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                            "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if request.url.path.endswith("/tokens/content"):
            return httpx.Response(200, json={"token": "token"})
        raise httpx.ReadTimeout("unknown after send", request=request)

    service = _service(tmp_path, handler)
    kwargs = dict(owner_id="alice", url="https://example.com/a", max_price_micros=10,
                  idempotency_key="idem-unknown-123456", deriver=FixedDeriver())
    with pytest.raises(LicensedAccessUnavailable):
        service.acquire(**kwargs)
    before = list(calls)
    with pytest.raises(LicensedAccessConflict, match="unknown"):
        service.acquire(**kwargs)
    assert calls == before


def test_claim_precedes_provider_and_concurrent_same_key_loses(tmp_path):
    service = None

    def handler(request):
        with pytest.raises(LicensedAccessConflict):
            service.acquire(
                owner_id="alice", url="https://example.com/a", max_price_micros=10,
                idempotency_key="idem-concurrent-1234", deriver=FixedDeriver(),
            )
        return httpx.Response(500)

    service = _service(tmp_path, handler)
    with pytest.raises(LicensedAccessUnavailable):
        service.acquire(owner_id="alice", url="https://example.com/a",
                        max_price_micros=10, idempotency_key="idem-concurrent-1234",
                        deriver=FixedDeriver())


def test_verbatim_derivation_is_refused_after_fetch(tmp_path):
    raw = "these eight exact licensed words must never escape into any derived artifact"

    def handler(request):
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"},
                "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                            "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if request.url.path.endswith("/tokens/content"):
            return httpx.Response(200, json={"token": "token"})
        return httpx.Response(200, json={"content": {"body": raw}, "rate": {
            "price": {"priceMicros": 5, "currency": "USD"}, "license": {
                "licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                "permissions": [{"name": "PARTIAL_USE"}]}}})

    with pytest.raises(LicensedAccessDenied, match="policy"):
        _service(tmp_path, handler).acquire(
            owner_id="alice", url="https://example.com/a", max_price_micros=10,
            idempotency_key="idem-verbatim-12345",
            deriver=FixedDeriver(Derivation("citation", raw, "summary")),
        )


def test_token_timeout_is_held_unknown_and_never_retried(tmp_path):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"}, "license": {
                    "licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                    "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        raise httpx.ReadTimeout("token outcome unknown", request=request)

    service = _service(tmp_path, handler)
    kwargs = dict(owner_id="alice", url="https://example.com/a", max_price_micros=10,
                  idempotency_key="idem-token-timeout-12", deriver=FixedDeriver())
    with pytest.raises(LicensedAccessUnavailable):
        service.acquire(**kwargs)
    before = list(calls)
    with pytest.raises(LicensedAccessConflict):
        service.acquire(**kwargs)
    assert calls == before


def test_mark_failure_remains_claimed_and_cannot_retry(tmp_path, monkeypatch):
    service = _service(tmp_path, lambda _: pytest.fail("provider must not be reached"))
    original = service._mark_token_sent_unknown

    def fail_after_mark(key, digest):
        original(key, digest)
        raise RuntimeError("simulated post-commit acknowledgement loss")

    monkeypatch.setattr(service, "_mark_token_sent_unknown", fail_after_mark)
    kwargs = dict(owner_id="alice", url="https://example.com/a", max_price_micros=10,
                  idempotency_key="idem-mark-failure-123", deriver=FixedDeriver())
    # Rates must succeed before the mark boundary.
    monkeypatch.setattr(service, "_request", lambda *args, **kwargs: [{
        "url": "https://example.com/a", "rates": [{"price": {
            "priceMicros": 5, "currency": "USD"}, "license": {
                "licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                "permissions": [{"name": "PARTIAL_USE"}]}}]}])
    with pytest.raises(RuntimeError):
        service.acquire(**kwargs)
    with pytest.raises(LicensedAccessConflict):
        service.acquire(**kwargs)


def test_aggregate_and_punctuation_verbatim_evasions_are_refused():
    raw = "Alpha, beta—gamma delta; epsilon zeta eta theta."
    split = Derivation("https://example.com", "alpha beta", "gamma DELTA new words")
    with pytest.raises(LicensedAccessDenied, match="policy"):
        TollBitLicensedAccess._anti_verbatim(raw, split)


def test_post_fetch_license_identity_drift_is_denied(tmp_path):
    def handler(request):
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"}, "license": {
                    "licenseType": "ON_DEMAND_LICENSE", "id": "chosen-license",
                    "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if request.url.path.endswith("/tokens/content"):
            return httpx.Response(200, json={"token": "token"})
        return httpx.Response(200, json={"content": {"body": "licensed source body"},
            "rate": {"price": {"priceMicros": 5, "currency": "USD"}, "license": {
                "licenseType": "ON_DEMAND_LICENSE", "id": "different-license",
                "permissions": [{"name": "PARTIAL_USE"}]}}})

    with pytest.raises(LicensedAccessDenied):
        _service(tmp_path, handler).acquire(
            owner_id="alice", url="https://example.com/a", max_price_micros=10,
            idempotency_key="idem-license-drift-12", deriver=FixedDeriver(),
        )


@pytest.mark.parametrize("bad_price", [True, -1, 1_000_000_001])
def test_invalid_quoted_price_is_denied_before_token(tmp_path, bad_price):
    calls = []

    def handler(request):
        calls.append(request.url.path)
        return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
            "price": {"priceMicros": bad_price, "currency": "USD"}, "license": {
                "licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                "permissions": [{"name": "PARTIAL_USE"}]}}]}])

    with pytest.raises(LicensedAccessDenied):
        _service(tmp_path, handler).acquire(
            owner_id="alice", url="https://example.com/a", max_price_micros=10,
            idempotency_key=f"idem-bad-quote-{str(bad_price)}-1234", deriver=FixedDeriver(),
        )
    assert len(calls) == 1


@pytest.mark.parametrize("bad_price", [True, -1, 1_000_000_001])
def test_invalid_content_price_is_denied(tmp_path, bad_price):
    def handler(request):
        if request.url.path.endswith("/rates/batch"):
            return httpx.Response(200, json=[{"url": "https://example.com/a", "rates": [{
                "price": {"priceMicros": 5, "currency": "USD"}, "license": {
                    "licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                    "permissions": [{"name": "PARTIAL_USE"}]}}]}])
        if request.url.path.endswith("/tokens/content"):
            return httpx.Response(200, json={"token": "token"})
        return httpx.Response(200, json={"content": {"body": "licensed source body"},
            "rate": {"price": {"priceMicros": bad_price, "currency": "USD"},
                     "license": {"licenseType": "ON_DEMAND_LICENSE", "id": "lic-1",
                     "permissions": [{"name": "PARTIAL_USE"}]}}})

    with pytest.raises(LicensedAccessDenied):
        _service(tmp_path, handler).acquire(
            owner_id="alice", url="https://example.com/a", max_price_micros=10,
            idempotency_key=f"idem-bad-content-{str(bad_price)}-12", deriver=FixedDeriver(),
        )


def test_no_raw_content_in_database_wal_or_lock_artifacts(tmp_path):
    test_paid_content_is_transient_and_replay_makes_no_network_call(tmp_path)
    canary = b"LICENSED RAW CANARY"
    for path in tmp_path.iterdir():
        if path.is_file():
            assert canary not in path.read_bytes(), path


def test_api_requires_distinct_authenticated_owner_and_uses_constant_errors():
    class Stub:
        def acquire(self, **kwargs):
            raise LicensedAccessDenied("SECRET provider detail")

    app = FastAPI()
    app.include_router(create_licensed_research_router(service=Stub(), deriver=FixedDeriver()))
    client = TestClient(app)
    body = {"url": "https://example.com/a", "max_price_micros": 10}
    response = client.post("/research/licensed/summarize", json=body,
                           headers={"Idempotency-Key": "idem-api-123456789"})
    assert response.status_code == 401
    assert "SECRET" not in response.text

    authed_app = FastAPI()

    @authed_app.middleware("http")
    async def signed_owner(request, call_next):
        request.state.auth_method = "antiek_session_cookie"
        request.state.user_id = "owner-a"
        return await call_next(request)

    authed_app.include_router(
        create_licensed_research_router(service=Stub(), deriver=FixedDeriver())
    )
    authed = TestClient(authed_app).post(
        "/research/licensed/summarize", json=body,
        headers={"Idempotency-Key": "idem-api-123456789"},
    )
    assert authed.status_code == 403
    assert authed.json() == {"detail": "licensed access denied"}
