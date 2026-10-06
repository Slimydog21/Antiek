"""Type-narrowed adapters for Python's numeric conversion protocols."""

from __future__ import annotations

import sys
from collections.abc import Buffer
from typing import Protocol, SupportsFloat, SupportsIndex, SupportsInt, runtime_checkable


@runtime_checkable
class _SupportsTrunc(Protocol):
    def __trunc__(self) -> int: ...


def to_float(value: object) -> float:
    if isinstance(value, (str, Buffer, SupportsFloat, SupportsIndex)):
        return float(value)
    raise TypeError("value does not support float conversion")


def to_int(value: object) -> int:
    if isinstance(value, (str, Buffer, SupportsInt, SupportsIndex)):
        return int(value)
    # int() still accepts __trunc__ on Python 3.11-3.13. Keep its own
    # validation and deprecation warning until that protocol is removed.
    if sys.version_info < (3, 14) and isinstance(value, _SupportsTrunc):
        return int(value)
    raise TypeError("value does not support int conversion")
