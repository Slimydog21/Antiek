from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable, Mapping
from email.utils import parsedate_to_datetime
from pathlib import Path


class BannedUntil(RuntimeError):
    pass


class BanSentinel:
    def __init__(self, path: Path, now: Callable[[], float]) -> None:
        self.path, self.now = path, now

    def _read(self) -> float:
        try:
            value = json.loads(self.path.read_text())["banned_until"]
            return float(value)
        except OSError, ValueError, TypeError, KeyError:
            return 0.0

    def is_banned(self) -> bool:
        return self.now() < self._read()

    def refuse_if_banned(self) -> None:
        until = self._read()
        if self.now() < until:
            raise BannedUntil(f"provider request refused until {until}")

    def persist_retry_after(self, headers: Mapping[str, str], default_seconds: float) -> None:
        raw = headers.get("Retry-After") or headers.get("retry-after")
        until = self.now() + default_seconds
        if raw:
            try:
                until = self.now() + max(0.0, float(raw))
            except ValueError:
                with contextlib.suppress(TypeError, ValueError, OverflowError):
                    until = parsedate_to_datetime(raw).timestamp()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps({"banned_until": until}), encoding="utf-8")
        os.replace(tmp, self.path)
