"""Operator actions — a read-only VIEW over ``docs/OPERATOR_ACTIONS.md``.

``docs/operator_gate_actions.md`` owns the original G1-G12 gate-action ledger.
``docs/OPERATOR_ACTIONS.md`` is the broader operator-only living index (OA-001
and onward): counsel, publishers, escrow accounts, production deploy checks, and
other tasks engineering cannot complete alone.

This module parses only the quick-status table. It never writes the markdown and
does not author a second task store. If the operator edits the table, the next
read reflects it.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def canonical_operator_actions_path() -> Path:
    """The canonical operator-only action file. Never written by this package."""
    return _repo_root() / "docs" / "OPERATOR_ACTIONS.md"


class OperatorActionStatus(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    AWAITING_OPERATOR_TEST = "awaiting_operator_test"
    PARTIALLY_DONE = "partially_done"
    DEFERRED = "deferred"
    UNKNOWN = "unknown"

    @property
    def is_open_family(self) -> bool:
        return self is not OperatorActionStatus.CLOSED


@dataclass(frozen=True)
class OperatorAction:
    action_id: str
    title: str
    status: OperatorActionStatus
    status_raw: str
    blocks: str
    owner: str

    @property
    def is_closed(self) -> bool:
        return self.status is OperatorActionStatus.CLOSED

    @property
    def is_closeable(self) -> bool:
        return self.status is OperatorActionStatus.AWAITING_OPERATOR_TEST


@dataclass(frozen=True)
class OperatorActionsView:
    source_path: str
    actions: tuple[OperatorAction, ...]

    def open_actions(self) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self.actions if not a.is_closed)

    def closeable_actions(self) -> tuple[OperatorAction, ...]:
        return tuple(a for a in self.actions if a.is_closeable)

    def first_open(self) -> OperatorAction | None:
        open_actions = self.open_actions()
        return open_actions[0] if open_actions else None

    def status_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for action in self.actions:
            key = action.status.value
            counts[key] = counts.get(key, 0) + 1
        return counts


def _normalize_status(raw: str) -> OperatorActionStatus:
    normalized = " ".join(raw.strip().upper().split())
    if normalized == "CLOSED":
        return OperatorActionStatus.CLOSED
    if normalized.startswith("OPEN"):
        return OperatorActionStatus.OPEN
    if normalized == "IN_PROGRESS":
        return OperatorActionStatus.IN_PROGRESS
    if normalized == "AWAITING OPERATOR TEST":
        return OperatorActionStatus.AWAITING_OPERATOR_TEST
    if normalized == "PARTIALLY DONE":
        return OperatorActionStatus.PARTIALLY_DONE
    if normalized == "DEFERRED":
        return OperatorActionStatus.DEFERRED
    return OperatorActionStatus.UNKNOWN


def parse_operator_actions(md: str, *, source_path: str) -> OperatorActionsView:
    """Parse the quick-status table from ``docs/OPERATOR_ACTIONS.md``."""
    actions: list[OperatorAction] = []
    in_table = False
    for line in md.splitlines():
        if line.strip() == "| ID | Title | Status | Blocks | Owner |":
            in_table = True
            continue
        if not in_table:
            continue
        if line.startswith("|---"):
            continue
        if not line.startswith("|"):
            if actions:
                break
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 5:
            continue
        action_id, title, status_raw, blocks, owner = cells
        if not action_id.startswith("OA-"):
            continue
        actions.append(
            OperatorAction(
                action_id=action_id,
                title=title,
                status=_normalize_status(status_raw),
                status_raw=status_raw,
                blocks=blocks,
                owner=owner,
            )
        )
    return OperatorActionsView(source_path=source_path, actions=tuple(actions))


def load_operator_actions(
    path: Path | None = None,
) -> OperatorActionsView:
    source = path or canonical_operator_actions_path()
    try:
        source_path = str(source.relative_to(_repo_root()))
    except ValueError:
        source_path = str(source)
    return parse_operator_actions(
        source.read_text(encoding="utf-8"),
        source_path=source_path,
    )
