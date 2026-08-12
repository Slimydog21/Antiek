"""TollBit on-demand summarization with an intentionally narrow data seam.

The licensed body exists only as a local variable passed to ``derive``.  It is
never returned by this module and is excluded from every persistence model.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

import httpx

from runtime.db_lock import connect_write

LICENSE_TYPE = "ON_DEMAND_LICENSE"
PERMISSION = "SUMMARIZATION"
_MAX_SNIPPET = 600
_MAX_SUMMARY = 4_000
_MAX_CITATION = 1_000
_IDEMPOTENCY_RE = re.compile(r"^[A-Za-z0-9._:-]{16,200}$")


class LicensedAccessError(RuntimeError):
    pass


class LicensedAccessDenied(LicensedAccessError):
    pass


class LicensedAccessUnavailable(LicensedAccessError):
    pass


class LicensedAccessConflict(LicensedAccessError):
    pass


class Deriver(Protocol):
    """Constrained local derivation seam; implementations must retain nothing."""

    def derive(self, body: str, *, canonical_url: str) -> Derivation: ...


@dataclass(frozen=True)
class Derivation:
    citation: str
    snippet: str
    summary: str


@dataclass(frozen=True)
class LicensedReceipt:
    transaction_id: str
    idempotency_key: str
    request_digest: str
    owner_identity_digest: str
    canonical_url: str
    content_digest: str
    license_type: str
    license_id: str
    permission: str
    price_micros: int
    currency: str
    citation: str
    snippet: str
    summary: str
    created_at: str
    receipt_mac: str


def _canonical_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
        raise ValueError("url must be an absolute HTTP(S) URL")
    if parts.username or parts.password or parts.fragment:
        raise ValueError("url credentials and fragments are forbidden")
    host = parts.hostname.lower()
    port = parts.port
    netloc = host if port is None else f"{host}:{port}"
    if (parts.scheme.lower(), port) in {("http", 80), ("https", 443)}:
        netloc = host
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _ensure_schema(con: Any) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS licensed_research_operations (
          idempotency_key VARCHAR PRIMARY KEY, request_digest VARCHAR NOT NULL,
          state VARCHAR NOT NULL, created_at VARCHAR NOT NULL, updated_at VARCHAR NOT NULL
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS licensed_research_receipts (
          transaction_id VARCHAR PRIMARY KEY,
          idempotency_key VARCHAR UNIQUE NOT NULL,
          request_digest VARCHAR NOT NULL,
          owner_identity_digest VARCHAR NOT NULL,
          canonical_url VARCHAR NOT NULL,
          content_digest VARCHAR NOT NULL,
          license_type VARCHAR NOT NULL,
          license_id VARCHAR NOT NULL,
          permission VARCHAR NOT NULL,
          price_micros BIGINT NOT NULL,
          currency VARCHAR NOT NULL,
          citation VARCHAR NOT NULL,
          snippet VARCHAR NOT NULL,
          summary VARCHAR NOT NULL,
          created_at VARCHAR NOT NULL,
          receipt_mac VARCHAR NOT NULL
        )
    """)


def _row_to_receipt(row: tuple[object, ...]) -> LicensedReceipt:
    return LicensedReceipt(*row)  # type: ignore[arg-type]


class TollBitLicensedAccess:
    """Fail-closed purchase/fetch/derive/receipt workflow."""

    def __init__(self, *, api_key: str, user_agent: str, signing_key: bytes,
                 db_path: str, client: httpx.Client | None = None,
                 gateway: str = "https://gateway.tollbit.com") -> None:
        if not api_key.strip() or not user_agent.strip():
            raise ValueError("TollBit api_key and registered user_agent are required")
        if len(signing_key) < 32:
            raise ValueError("signing_key must contain at least 32 bytes")
        self._api_key = api_key
        self._user_agent = user_agent
        self._signing_key = signing_key
        self._db_path = db_path
        self._client = client or httpx.Client(timeout=20.0)
        self._gateway = gateway.rstrip("/")

    def acquire(self, *, owner_id: str, url: str, max_price_micros: int,
                idempotency_key: str, deriver: Deriver) -> LicensedReceipt:
        owner = owner_id.strip()
        if not owner:
            raise LicensedAccessDenied("authenticated owner is required")
        if not _IDEMPOTENCY_RE.fullmatch(idempotency_key):
            raise ValueError("invalid Idempotency-Key")
        if isinstance(max_price_micros, bool) or not 0 <= max_price_micros <= 1_000_000_000:
            raise ValueError("max_price_micros is outside the bounded USD range")
        canonical_url = _canonical_url(url)
        owner_digest = hashlib.sha256(owner.encode()).hexdigest()
        request_digest = hashlib.sha256(_canonical_json({
            "owner": owner_digest, "url": canonical_url,
            "maxPriceMicros": max_price_micros, "permission": PERMISSION,
        })).hexdigest()
        replay = self._claim(idempotency_key, request_digest)
        if replay is not None:
            return replay
        try:
            rates = self._request("POST", "/dev/v2/rates/batch", json={"urls": [canonical_url]})
            rate = self._select_rate(rates, canonical_url)
            price_data = rate["price"]
            license_data = rate["license"]
            if not isinstance(price_data, dict):
                raise LicensedAccessDenied("licensed access denied")
            quoted_price = price_data["priceMicros"]
            if (isinstance(quoted_price, bool) or not isinstance(quoted_price, int)
                    or not 0 <= quoted_price <= 1_000_000_000):
                raise LicensedAccessDenied("licensed access denied")
            license_id = self._license_id(license_data)
            if quoted_price > max_price_micros:
                raise LicensedAccessDenied("licensed access denied")
        except Exception:
            self._release_unsent(idempotency_key, request_digest)
            raise
        # Conservative irreversible boundary: persist UNKNOWN before token
        # issuance. Any failure from here onward requires reconciliation and
        # may never trigger an automatic replay.
        self._mark_token_sent_unknown(idempotency_key, request_digest)
        try:
            token_data = self._request("POST", "/dev/v2/tokens/content", json={
                "url": canonical_url, "userAgent": self._user_agent,
                "maxPriceMicros": quoted_price, "currency": "USD",
                "licenseType": LICENSE_TYPE,
            })
            token = token_data.get("token") if isinstance(token_data, dict) else None
            if not isinstance(token, str) or not token:
                raise LicensedAccessUnavailable("licensed access unavailable")
        except Exception:
            # TOKEN_SENT_UNKNOWN is deliberately retained even for a known
            # 4xx: v1 does not assume provider error semantics prove no charge.
            raise
        content_data = self._request(
            "GET", f"/dev/v2/content/{quote(canonical_url, safe='')}",
            headers={"TollbitToken": token, "User-Agent": self._user_agent,
                     "Tollbit-Accept-Content": "text/markdown"},
        )
        actual = self._validate_content_rate(content_data, quoted_price, license_id)
        content = content_data.get("content") if isinstance(content_data, dict) else None
        raw_body = content.get("body") if isinstance(content, dict) else None
        if not isinstance(raw_body, str) or not raw_body:
            raise LicensedAccessUnavailable("TollBit content body was invalid")
        content_digest = hashlib.sha256(raw_body.encode()).hexdigest()
        try:
            derived = deriver.derive(raw_body, canonical_url=canonical_url)
        except Exception:
            raise LicensedAccessUnavailable("licensed derivation unavailable") from None
        checked = Derivation(
            # Citation is provenance-only, never model-authored licensed text.
            citation=self._bounded(canonical_url, _MAX_CITATION, "citation"),
            snippet=self._bounded(derived.snippet, _MAX_SNIPPET, "snippet"),
            summary=self._bounded(derived.summary, _MAX_SUMMARY, "summary"),
        )
        self._anti_verbatim(raw_body, checked)
        unsigned = {
            "transaction_id": f"tlb_{uuid.uuid4().hex}",
            "idempotency_key": idempotency_key, "request_digest": request_digest,
            "owner_identity_digest": owner_digest, "canonical_url": canonical_url,
            "content_digest": content_digest, "license_type": LICENSE_TYPE,
            "license_id": license_id,
            "permission": PERMISSION, "price_micros": actual, "currency": "USD",
            **asdict(checked), "created_at": datetime.now(UTC).isoformat(),
        }
        receipt = LicensedReceipt(**unsigned, receipt_mac=hmac.new(
            self._signing_key, _canonical_json(unsigned), hashlib.sha256).hexdigest())
        return self._commit(idempotency_key, request_digest, receipt)

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers: dict[str, str] = dict(kwargs.pop("headers", {}) or {})
        if path != "" and method == "POST":
            headers["TollbitKey"] = self._api_key
        try:
            response = self._client.request(method, self._gateway + path, headers=headers, **kwargs)
        except (httpx.TimeoutException, httpx.RequestError) as exc:
            raise LicensedAccessUnavailable("licensed content provider unavailable") from exc
        if response.status_code in {401, 403}:
            raise LicensedAccessDenied("licensed content authorization denied")
        if response.status_code == 402:
            raise LicensedAccessDenied("licensed content payment refused")
        if response.status_code >= 400:
            raise LicensedAccessUnavailable("licensed content provider failed")
        try:
            return response.json()
        except ValueError as exc:
            raise LicensedAccessUnavailable("licensed content provider returned invalid JSON") from exc

    @staticmethod
    def _select_rate(payload: object, url: str) -> dict[str, object]:
        if not isinstance(payload, list):
            raise LicensedAccessUnavailable("invalid TollBit rates response")
        entries = [x for x in payload if isinstance(x, dict) and x.get("url") == url]
        if len(entries) != 1 or not isinstance(entries[0].get("rates"), list):
            raise LicensedAccessDenied("no exact rate for requested URL")
        matches = []
        for rate in entries[0]["rates"]:
            if not isinstance(rate, dict):
                continue
            lic, price = rate.get("license"), rate.get("price")
            permissions = lic.get("permissions", []) if isinstance(lic, dict) else []
            names = {p.get("name") for p in permissions if isinstance(p, dict)}
            # TollBit's standard summarization license is ON_DEMAND_LICENSE;
            # its current wire permission is PARTIAL_USE (never FULL_USE).
            if (isinstance(lic, dict) and lic.get("licenseType") == LICENSE_TYPE
                    and "PARTIAL_USE" in names and "FULL_USE" not in names and isinstance(price, dict)
                    and price.get("currency") == "USD"
                    and isinstance(price.get("priceMicros"), int)
                    and not isinstance(price.get("priceMicros"), bool)
                    and 0 <= price["priceMicros"] <= 1_000_000_000):
                matches.append(rate)
        if len(matches) != 1:
            raise LicensedAccessDenied("exact summarization license unavailable or ambiguous")
        return matches[0]

    @staticmethod
    def _validate_content_rate(payload: object, quoted: int, license_id: str) -> int:
        rate = payload.get("rate") if isinstance(payload, dict) else None
        price = rate.get("price") if isinstance(rate, dict) else None
        lic = rate.get("license") if isinstance(rate, dict) else None
        actual = price.get("priceMicros") if isinstance(price, dict) else None
        permissions = lic.get("permissions", []) if isinstance(lic, dict) else []
        names = {p.get("name") for p in permissions if isinstance(p, dict)}
        if (isinstance(actual, bool) or not isinstance(actual, int)
                or not 0 <= actual <= 1_000_000_000 or actual != quoted
                or not isinstance(price, dict) or price.get("currency") != "USD"
                or not isinstance(lic, dict) or lic.get("licenseType") != LICENSE_TYPE
                or TollBitLicensedAccess._license_id(lic) != license_id
                or "PARTIAL_USE" not in names or "FULL_USE" in names):
            raise LicensedAccessDenied("licensed access denied")
        return actual

    @staticmethod
    def _license_id(license_data: object) -> str:
        value = (license_data.get("cuid") or license_data.get("id")) if isinstance(license_data, dict) else None
        if not isinstance(value, str) or not value.strip():
            raise LicensedAccessDenied("licensed access denied")
        return value.strip()

    @staticmethod
    def _anti_verbatim(raw: str, derived: Derivation) -> None:
        def words(value: str) -> list[str]:
            folded = unicodedata.normalize("NFKC", value).casefold()
            return re.findall(r"[\w]+", folded, flags=re.UNICODE)

        raw_words = words(raw)
        # Aggregate fields before inspection so splitting a copied phrase
        # across snippet/summary boundaries cannot evade the policy.
        output_words = words(" ".join(asdict(derived).values()))
        raw_chars = "".join(raw_words)
        output_chars = "".join(output_words)
        if len(output_chars) >= 20 and output_chars in raw_chars:
            raise LicensedAccessDenied("derived output policy denied")
        for width in (3, 4):
            grams = {tuple(raw_words[i:i + width])
                     for i in range(max(0, len(raw_words) - width + 1))}
            if any(tuple(output_words[i:i + width]) in grams
                   for i in range(max(0, len(output_words) - width + 1))):
                raise LicensedAccessDenied("derived output policy denied")

    @staticmethod
    def _bounded(value: str, limit: int, name: str) -> str:
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f"derived {name} is empty or exceeds {limit} characters")
        return value.strip()

    def _claim(self, key: str, digest: str) -> LicensedReceipt | None:
        with connect_write(self._db_path, purpose="licensed-access/replay") as con:
            _ensure_schema(con)
            op = con.execute("SELECT request_digest, state FROM licensed_research_operations WHERE idempotency_key=?", [key]).fetchone()
            if op is None:
                now = datetime.now(UTC).isoformat()
                con.execute("INSERT INTO licensed_research_operations VALUES (?, ?, 'CLAIMED', ?, ?)", [key, digest, now, now])
                return None
            if op[0] != digest:
                raise LicensedAccessConflict("licensed operation conflict")
            if op[1] != "SUCCEEDED":
                raise LicensedAccessConflict("licensed operation already in progress or outcome unknown")
            row = con.execute("SELECT transaction_id, idempotency_key, request_digest, owner_identity_digest, canonical_url, content_digest, license_type, license_id, permission, price_micros, currency, citation, snippet, summary, created_at, receipt_mac FROM licensed_research_receipts WHERE idempotency_key=?", [key]).fetchone()
        if row is None:
            raise LicensedAccessDenied("licensed receipt unavailable")
        receipt = _row_to_receipt(row)
        self._verify_receipt(receipt)
        return receipt

    def _mark_token_sent_unknown(self, key: str, digest: str) -> None:
        with connect_write(self._db_path, purpose="licensed-access/sent") as con:
            _ensure_schema(con)
            row = con.execute(
                "UPDATE licensed_research_operations SET state='TOKEN_SENT_UNKNOWN', updated_at=? "
                "WHERE idempotency_key=? AND request_digest=? AND state='CLAIMED' RETURNING idempotency_key",
                [datetime.now(UTC).isoformat(), key, digest],
            ).fetchone()
            if row is None:
                raise LicensedAccessConflict("licensed operation conflict")

    def _release_unsent(self, key: str, digest: str) -> None:
        with connect_write(self._db_path, purpose="licensed-access/release") as con:
            _ensure_schema(con)
            row = con.execute(
                "DELETE FROM licensed_research_operations WHERE idempotency_key=? AND request_digest=? "
                "AND state='CLAIMED' RETURNING idempotency_key", [key, digest]
            ).fetchone()
            if row is None:
                raise LicensedAccessConflict("licensed operation conflict")

    def _verify_receipt(self, receipt: LicensedReceipt) -> None:
        values = asdict(receipt)
        mac = values.pop("receipt_mac")
        expected = hmac.new(
            self._signing_key, _canonical_json(values), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(mac, expected):
            raise LicensedAccessDenied("licensed receipt integrity check failed")

    def _commit(self, key: str, digest: str, receipt: LicensedReceipt) -> LicensedReceipt:
        with connect_write(self._db_path, purpose="licensed-access/commit") as con:
            _ensure_schema(con)
            values = asdict(receipt)
            con.execute("BEGIN TRANSACTION")
            try:
                row = con.execute(
                    "UPDATE licensed_research_operations SET state='SUCCEEDED', updated_at=? "
                    "WHERE idempotency_key=? AND request_digest=? AND state='TOKEN_SENT_UNKNOWN' "
                    "RETURNING idempotency_key",
                    [datetime.now(UTC).isoformat(), key, digest],
                ).fetchone()
                if row is None:
                    raise LicensedAccessConflict("licensed operation conflict")
                con.execute(
                    "INSERT INTO licensed_research_receipts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [receipt.transaction_id, key, digest,
                     values["owner_identity_digest"], values["canonical_url"],
                     values["content_digest"], values["license_type"],
                     values["license_id"], values["permission"],
                     values["price_micros"], values["currency"], values["citation"],
                     values["snippet"], values["summary"], values["created_at"],
                     values["receipt_mac"]],
                )
                con.execute("COMMIT")
            except Exception:
                con.execute("ROLLBACK")
                raise
        return receipt
