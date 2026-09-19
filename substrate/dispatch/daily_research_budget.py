"""Atomic account-scoped daily holds for interactive research launches."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Literal

_SCHEMA_VERSION = 1
_DEFAULT_DAILY_CAP_USD = "5.00"


class DailyResearchBudgetInvalid(ValueError):
    """The persisted ledger or requested transition is invalid."""


class DailyResearchBudgetExceeded(DailyResearchBudgetInvalid):
    """A new hold would exceed the account's daily cap."""


@dataclass(frozen=True)
class DailyResearchBudgetSnapshot:
    date_stamp: str
    cap_cents: int
    held_cents: int
    settled_cents: int

    @property
    def remaining_cents(self) -> int:
        return self.cap_cents - self.held_cents - self.settled_cents


def _cents(value: Decimal | str | float | int, *, name: str) -> int:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DailyResearchBudgetInvalid(f"{name} is not valid money") from exc
    quantized = decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if decimal != quantized or quantized < 0:
        raise DailyResearchBudgetInvalid(f"{name} must be non-negative whole cents")
    return int(quantized * 100)


def _actual_cents(value: Decimal | str | float | int) -> int:
    try:
        decimal = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise DailyResearchBudgetInvalid("actual amount is not valid money") from exc
    if decimal < 0:
        raise DailyResearchBudgetInvalid("actual amount must be non-negative")
    return int(decimal.quantize(Decimal("0.01"), rounding=ROUND_CEILING) * 100)


def _date_stamp(now: datetime | None) -> str:
    instant = now or datetime.now(UTC)
    if instant.tzinfo is None:
        instant = instant.replace(tzinfo=UTC)
    return instant.astimezone(UTC).strftime("%Y%m%d")


def _resolved_date_stamp(*, now: datetime | None, date_stamp: str | None) -> str:
    if date_stamp is None:
        return _date_stamp(now)
    if now is not None:
        raise DailyResearchBudgetInvalid("provide either now or date_stamp, not both")
    if len(date_stamp) != 8 or not date_stamp.isascii() or not date_stamp.isdigit():
        raise DailyResearchBudgetInvalid("daily research date stamp is invalid")
    try:
        datetime.strptime(date_stamp, "%Y%m%d")
    except ValueError as exc:
        raise DailyResearchBudgetInvalid("daily research date stamp is invalid") from exc
    return date_stamp


def _account_digest(account_id: str) -> str:
    if not account_id or account_id != account_id.strip():
        raise DailyResearchBudgetInvalid("account id is invalid")
    return hashlib.sha256(
        b"antiek.daily-research-budget.account.v1\x00" + account_id.encode("utf-8")
    ).hexdigest()


def _root(root: Path | None) -> Path:
    if root is not None:
        return root
    home = Path(os.environ.get("ANTIEK_HOME", Path.home() / ".antiek"))
    return home / "budgets" / "research-daily"


def configured_daily_research_cap() -> Decimal:
    for name in ("ANTIEK_OPERATOR_BUDGET_USD", "ANTIEK_DAEMON_HOURLY_BUDGET_USD"):
        raw = os.environ.get(name)
        if raw is not None and raw.strip():
            _cents(raw.strip(), name=name)
            return Decimal(raw.strip()).quantize(Decimal("0.01"))
    return Decimal(_DEFAULT_DAILY_CAP_USD)


def _paths(root: Path, date_stamp: str) -> tuple[Path, Path]:
    return root / f"{date_stamp}.json", root / f"{date_stamp}.lock"


def _empty(date_stamp: str) -> dict[str, object]:
    return {"schema_version": _SCHEMA_VERSION, "date_stamp": date_stamp, "accounts": {}}


def _read(path: Path, date_stamp: str) -> dict[str, object]:
    if not path.exists():
        return _empty(date_stamp)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DailyResearchBudgetInvalid("daily research ledger is unreadable") from exc
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != _SCHEMA_VERSION
        or document.get("date_stamp") != date_stamp
        or not isinstance(document.get("accounts"), dict)
    ):
        raise DailyResearchBudgetInvalid("daily research ledger header is invalid")
    return document


def _write(path: Path, document: dict[str, object]) -> None:
    encoded = json.dumps(
        document, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _account(document: dict[str, object], account_id: str, cap_cents: int) -> dict[str, object]:
    accounts = document["accounts"]
    assert isinstance(accounts, dict)
    digest = _account_digest(account_id)
    row = accounts.setdefault(digest, {"cap_cents": cap_cents, "holds": {}})
    if not isinstance(row, dict) or not isinstance(row.get("holds"), dict):
        raise DailyResearchBudgetInvalid("daily research account row is invalid")
    stored_cap = row.get("cap_cents")
    if stored_cap != cap_cents:
        if row["holds"]:
            raise DailyResearchBudgetInvalid("daily research cap changed after activity")
        row["cap_cents"] = cap_cents
    return row


def _snapshot(date_stamp: str, row: dict[str, object]) -> DailyResearchBudgetSnapshot:
    holds = row["holds"]
    assert isinstance(holds, dict)
    held = settled = 0
    for item in holds.values():
        if not isinstance(item, dict):
            raise DailyResearchBudgetInvalid("daily research hold row is invalid")
        amount = item.get("amount_cents")
        actual = item.get("actual_cents")
        status = item.get("status")
        if not isinstance(amount, int) or amount <= 0:
            raise DailyResearchBudgetInvalid("daily research hold amount is invalid")
        if status == "held":
            held += amount
        elif status == "settled" and isinstance(actual, int) and 0 <= actual <= amount:
            settled += actual
        elif status != "released":
            raise DailyResearchBudgetInvalid("daily research hold status is invalid")
    cap = row.get("cap_cents")
    if not isinstance(cap, int) or cap < 0 or held + settled > cap:
        raise DailyResearchBudgetInvalid("daily research balance is invalid")
    return DailyResearchBudgetSnapshot(date_stamp, cap, held, settled)


def _transition(
    *,
    account_id: str,
    hold_id: str,
    cap_usd: Decimal | str | float | int,
    amount_usd: Decimal | str | float | int,
    action: Literal["hold", "settle", "release"],
    actual_usd: Decimal | str | float | int | None = None,
    now: datetime | None = None,
    date_stamp: str | None = None,
    root: Path | None = None,
) -> DailyResearchBudgetSnapshot:
    if len(hold_id) != 64 or any(char not in "0123456789abcdef" for char in hold_id):
        raise DailyResearchBudgetInvalid("hold id must be a SHA-256 digest")
    cap_cents = _cents(cap_usd, name="daily cap")
    amount_cents = _cents(amount_usd, name="hold amount")
    if amount_cents <= 0:
        raise DailyResearchBudgetInvalid("hold amount must be positive")
    actual_cents = _actual_cents(actual_usd) if actual_usd is not None else None
    date_stamp = _resolved_date_stamp(now=now, date_stamp=date_stamp)
    ledger_root = _root(root)
    ledger_root.mkdir(parents=True, exist_ok=True)
    path, lock_path = _paths(ledger_root, date_stamp)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        document = _read(path, date_stamp)
        row = _account(document, account_id, cap_cents)
        holds = row["holds"]
        assert isinstance(holds, dict)
        existing = holds.get(hold_id)
        if action == "hold":
            if isinstance(existing, dict) and existing.get("amount_cents") != amount_cents:
                raise DailyResearchBudgetInvalid("hold id was used for another amount")
            if existing is None or (
                isinstance(existing, dict) and existing.get("status") == "released"
            ):
                before = _snapshot(date_stamp, row)
                if amount_cents > before.remaining_cents:
                    raise DailyResearchBudgetExceeded("daily research cap exceeded")
                holds[hold_id] = {
                    "amount_cents": amount_cents,
                    "actual_cents": None,
                    "status": "held",
                }
            elif not isinstance(existing, dict):
                raise DailyResearchBudgetInvalid("hold id was used for another amount")
            elif existing.get("status") != "held":
                raise DailyResearchBudgetInvalid("daily research hold is already terminal")
        else:
            if not isinstance(existing, dict) or existing.get("amount_cents") != amount_cents:
                raise DailyResearchBudgetInvalid("daily research hold is missing")
            if action == "settle":
                if actual_cents is None or actual_cents > amount_cents:
                    raise DailyResearchBudgetInvalid("actual amount exceeds its hold")
                desired = {
                    "amount_cents": amount_cents,
                    "actual_cents": actual_cents,
                    "status": "settled",
                }
            else:
                desired = {"amount_cents": amount_cents, "actual_cents": None, "status": "released"}
            if existing != desired:
                if existing.get("status") != "held":
                    raise DailyResearchBudgetInvalid("daily research hold is already terminal")
                holds[hold_id] = desired
        snapshot = _snapshot(date_stamp, row)
        _write(path, document)
        return snapshot


def hold_daily_research_budget(**kwargs: object) -> DailyResearchBudgetSnapshot:
    return _transition(action="hold", **kwargs)  # type: ignore[arg-type]


def settle_daily_research_budget(**kwargs: object) -> DailyResearchBudgetSnapshot:
    return _transition(action="settle", **kwargs)  # type: ignore[arg-type]


def release_daily_research_budget(**kwargs: object) -> DailyResearchBudgetSnapshot:
    return _transition(action="release", **kwargs)  # type: ignore[arg-type]


def read_daily_research_budget(
    *,
    account_id: str,
    cap_usd: Decimal | str | float | int,
    now: datetime | None = None,
    date_stamp: str | None = None,
    root: Path | None = None,
) -> DailyResearchBudgetSnapshot:
    cap_cents = _cents(cap_usd, name="daily cap")
    date_stamp = _resolved_date_stamp(now=now, date_stamp=date_stamp)
    ledger_root = _root(root)
    ledger_root.mkdir(parents=True, exist_ok=True)
    path, lock_path = _paths(ledger_root, date_stamp)
    with lock_path.open("a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_SH)
        document = _read(path, date_stamp)
        row = _account(document, account_id, cap_cents)
        return _snapshot(date_stamp, row)


__all__ = [
    "DailyResearchBudgetExceeded",
    "DailyResearchBudgetInvalid",
    "DailyResearchBudgetSnapshot",
    "configured_daily_research_cap",
    "hold_daily_research_budget",
    "read_daily_research_budget",
    "release_daily_research_budget",
    "settle_daily_research_budget",
]
