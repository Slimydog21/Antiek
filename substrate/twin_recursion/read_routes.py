"""Immutable server registry for current reviewed twin promotion reads."""

from __future__ import annotations

import os
import stat
from collections.abc import Mapping
from dataclasses import InitVar, dataclass, field
from types import MappingProxyType

from .evidence_promotion import TwinEvidencePromotionLedger
from .ledger import TwinRecursionLedger


class CurrentTwinPromotionReadUnavailable(LookupError):
    """No server-owned read authority exists for this owner."""


class CurrentTwinPromotionReadIntegrityError(RuntimeError):
    """A qualified server authority changed after registration."""


def _owner_id(value: object) -> str:
    if (
        type(value) is not str
        or not value
        or len(value.encode("utf-8")) > 512
        or value.strip() != value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ValueError("owner_id must be an exact bounded identifier")
    return value


@dataclass(frozen=True)
class QualifiedCurrentTwinPromotionRead:
    owner_id: str
    graph_db_path: str
    promotions: InitVar[TwinEvidencePromotionLedger]
    twins: InitVar[TwinRecursionLedger]
    promotion_path: str = field(init=False)
    twin_path: str = field(init=False)
    _graph_identity: tuple[int, int] = field(default=(0, 0), init=False, repr=False)
    _promotion_identity: tuple[int, int] = field(default=(0, 0), init=False, repr=False)
    _twin_identity: tuple[int, int] = field(default=(0, 0), init=False, repr=False)
    _lock_identity: tuple[int, int] = field(default=(0, 0), init=False, repr=False)
    _promotion_verify_key: bytes = field(default=b"", init=False, repr=False)
    _twin_timeout: float = field(default=0.0, init=False, repr=False)

    def __post_init__(
        self, promotions: TwinEvidencePromotionLedger, twins: TwinRecursionLedger
    ) -> None:
        _owner_id(self.owner_id)
        if type(self.graph_db_path) is not str or not self.graph_db_path:
            raise ValueError("read authority requires an exact graph path")
        graph_path = os.path.realpath(os.path.abspath(self.graph_db_path))
        if graph_path != self.graph_db_path:
            raise ValueError("read authority requires a canonical graph path")
        if type(promotions) is not TwinEvidencePromotionLedger:
            raise TypeError("read authority requires the exact promotion ledger")
        if promotions.owner_id != self.owner_id:
            raise ValueError("promotion ledger owner differs from read authority")
        if not promotions.read_only:
            raise ValueError("read authority requires a read-only promotion ledger")
        if type(twins) is not TwinRecursionLedger:
            raise TypeError("read authority requires the exact twin ledger")
        if not twins.read_only:
            raise ValueError("read authority requires a read-only twin ledger")
        object.__setattr__(self, "promotion_path", promotions.path)
        object.__setattr__(self, "twin_path", twins.path)
        identities = tuple(
            self._identity(path)
            for path in (
                graph_path,
                promotions.path,
                twins.path,
                graph_path + ".write.lock",
            )
        )
        object.__setattr__(self, "_graph_identity", identities[0])
        object.__setattr__(self, "_promotion_identity", identities[1])
        object.__setattr__(self, "_twin_identity", identities[2])
        object.__setattr__(self, "_lock_identity", identities[3])
        object.__setattr__(self, "_promotion_verify_key", bytes(promotions._review_key))
        object.__setattr__(self, "_twin_timeout", twins._timeout)

    @staticmethod
    def _identity(path: str) -> tuple[int, int]:
        if os.path.realpath(os.path.abspath(path)) != path:
            raise ValueError("read authority paths must be canonical")
        value = os.stat(path, follow_symlinks=False)
        if not stat.S_ISREG(value.st_mode) or value.st_nlink != 1:
            raise ValueError("read authority paths must be private regular files")
        return value.st_dev, value.st_ino

    def require_current(self) -> None:
        current = tuple(
            self._identity(path)
            for path in (
                self.graph_db_path,
                self.promotion_path,
                self.twin_path,
                self.graph_db_path + ".write.lock",
            )
        )
        if current != (
            self._graph_identity,
            self._promotion_identity,
            self._twin_identity,
            self._lock_identity,
        ):
            raise CurrentTwinPromotionReadIntegrityError("read authority integrity unavailable")

    def open_readers(self) -> tuple[TwinEvidencePromotionLedger, TwinRecursionLedger]:
        self.require_current()
        promotions = TwinEvidencePromotionLedger.open_read_only(
            self.promotion_path,
            owner_id=self.owner_id,
            review_verify_key=self._promotion_verify_key,
        )
        twins = TwinRecursionLedger.open_read_only(self.twin_path, timeout=self._twin_timeout)
        self.require_current()
        return promotions, twins

    @property
    def graph_identity(self) -> tuple[int, int]:
        return self._graph_identity

    @property
    def lock_identity(self) -> tuple[int, int]:
        return self._lock_identity


class CurrentTwinPromotionReadRegistry:
    """Owner-keyed immutable registry; production defaults to no authority."""

    def __init__(self, routes: tuple[QualifiedCurrentTwinPromotionRead, ...] = ()) -> None:
        if type(routes) is not tuple or any(
            type(route) is not QualifiedCurrentTwinPromotionRead for route in routes
        ):
            raise TypeError("read routes must be an exact immutable tuple")
        values: dict[str, QualifiedCurrentTwinPromotionRead] = {}
        for route in routes:
            if route.owner_id in values:
                raise ValueError("current promotion owner routes must be unique")
            values[route.owner_id] = route
        self._routes: Mapping[str, QualifiedCurrentTwinPromotionRead] = MappingProxyType(values)

    def resolve(self, owner_id: str) -> QualifiedCurrentTwinPromotionRead:
        try:
            owner_id = _owner_id(owner_id)
        except ValueError as exc:
            raise CurrentTwinPromotionReadUnavailable("read authority unavailable") from exc
        route = self._routes.get(owner_id)
        if route is None:
            raise CurrentTwinPromotionReadUnavailable("read authority unavailable")
        return route


__all__ = [
    "CurrentTwinPromotionReadRegistry",
    "CurrentTwinPromotionReadIntegrityError",
    "CurrentTwinPromotionReadUnavailable",
    "QualifiedCurrentTwinPromotionRead",
]
