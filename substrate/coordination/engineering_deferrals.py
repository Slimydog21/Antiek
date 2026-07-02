"""Engineering deferrals — read-only VIEW over ``docs/engineering_deferrals.md``.

The deferrals file is the sequencing-discipline companion to the operator gate
ledger: it names things agents should *not* pre-build until a specific unlock
criterion fires. This module exposes that status without creating a second
deferral store and without any write path back to the markdown.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_engineering_deferrals_path() -> Path:
    return _repo_root() / "docs" / "engineering_deferrals.md"


class DeferralStatus(StrEnum):
    DEFERRED = "deferred"
    PARTIAL = "partial"
    SUBSTRATE_SHIPPED = "substrate_shipped"
    CLOSED = "closed"
    UNKNOWN = "unknown"

    @property
    def is_closed(self) -> bool:
        return self is DeferralStatus.CLOSED


@dataclass(frozen=True)
class EngineeringDeferral:
    deferral_id: str
    title: str
    status: DeferralStatus
    status_raw: str
    unlock_criterion: str | None
    blocks: str | None

    @property
    def is_closed(self) -> bool:
        return self.status.is_closed


@dataclass(frozen=True)
class EngineeringDeferralsView:
    source_path: str
    deferrals: tuple[EngineeringDeferral, ...]

    def open_deferrals(self) -> tuple[EngineeringDeferral, ...]:
        return tuple(d for d in self.deferrals if not d.is_closed)

    def first_open(self) -> EngineeringDeferral | None:
        open_deferrals = self.open_deferrals()
        return open_deferrals[0] if open_deferrals else None

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for deferral in self.deferrals:
            key = deferral.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


_SECTION_RE = re.compile(
    r"^## (D\d+) [—-] (.+?)\n(?P<body>.*?)(?=^## D\d+ [—-] |\n## Cross-reference:|\Z)",
    flags=re.MULTILINE | re.DOTALL,
)


def _repo_relative(path: Path) -> str:
    try:
        return str(path.relative_to(_repo_root()))
    except ValueError:
        return str(path)


def _strip_markdown(text: str) -> str:
    return " ".join(text.replace("**", "").replace("`", "").split())


def _field(body: str, label: str) -> str | None:
    m = re.search(rf"^\*\*{re.escape(label)}:\*\*\s*(.+)", body, flags=re.MULTILINE)
    return _strip_markdown(m.group(1)) if m else None


def _normalize_status(raw: str | None) -> DeferralStatus:
    if not raw:
        return DeferralStatus.UNKNOWN
    normalized = raw.lower()
    if "closed" in normalized or "satisfied" in normalized:
        return DeferralStatus.CLOSED
    if "partial" in normalized:
        return DeferralStatus.PARTIAL
    if "substrate shipped" in normalized or "substrate prep" in normalized:
        return DeferralStatus.SUBSTRATE_SHIPPED
    if "deferred" in normalized:
        return DeferralStatus.DEFERRED
    return DeferralStatus.UNKNOWN


def parse_engineering_deferrals(
    md: str,
    *,
    source_path: str,
) -> EngineeringDeferralsView:
    deferrals: list[EngineeringDeferral] = []
    for match in _SECTION_RE.finditer(md):
        body = match.group("body")
        status_raw = _field(body, "Status") or ""
        deferrals.append(
            EngineeringDeferral(
                deferral_id=match.group(1),
                title=_strip_markdown(match.group(2)),
                status=_normalize_status(status_raw),
                status_raw=status_raw,
                unlock_criterion=_field(body, "Unlock criterion"),
                blocks=_field(body, "Blocks-what"),
            )
        )
    if not deferrals:
        raise ValueError(f"no engineering deferrals found in {source_path}")
    return EngineeringDeferralsView(source_path=source_path, deferrals=tuple(deferrals))


def load_engineering_deferrals(
    path: Path | None = None,
) -> EngineeringDeferralsView:
    source = path or canonical_engineering_deferrals_path()
    return parse_engineering_deferrals(
        source.read_text(encoding="utf-8"),
        source_path=_repo_relative(source),
    )
