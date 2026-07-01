"""Local event sinks for prompt-autoresearch audit logs."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def jsonl_event_sink(path: Path) -> Callable[[dict[str, Any]], None]:
    """Return a callback that appends prompt-autoresearch events as JSONL."""

    def append_event(event: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, sort_keys=True) + "\n")

    return append_event
