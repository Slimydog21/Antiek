"""CompactionPolicy + CompactionConfig — operator-controllable compaction knobs."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib  # type: ignore[import-not-found]
else:  # pragma: no cover
    import tomli as tomllib  # type: ignore[import-not-found]


class CompactionPolicy(str, Enum):
    STRICT = "strict"
    LOSSY = "lossy"
    INTERACTIVE = "interactive"


@dataclass(frozen=True)
class CompactionConfig:
    policy: CompactionPolicy = CompactionPolicy.STRICT
    threshold_pct: float = 0.85
    keep_first_n: int = 4
    keep_last_n: int = 8
    summary_model: str | None = None

    def __post_init__(self) -> None:
        if not 0 < self.threshold_pct <= 1.0:
            raise ValueError(f"threshold_pct must be in (0, 1], got {self.threshold_pct}")
        if self.keep_first_n < 0 or self.keep_last_n < 0:
            raise ValueError("keep_first_n / keep_last_n must be >= 0")

    @classmethod
    def for_project(cls, project_root: Path) -> "CompactionConfig":
        cfg_file = project_root / ".antiek" / "config.toml"
        if not cfg_file.exists():
            return cls()
        data = tomllib.loads(cfg_file.read_text())
        c = data.get("compaction", {}) or {}
        return cls(
            policy=CompactionPolicy(c.get("policy", "strict")),
            threshold_pct=float(c.get("threshold_pct", 0.85)),
            keep_first_n=int(c.get("keep_first_n", 4)),
            keep_last_n=int(c.get("keep_last_n", 8)),
            summary_model=c.get("summary_model"),
        )
