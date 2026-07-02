"""Minimal JSON repair error-path helper for ARE-12 instrumentation.

This is not a broad permissive parser. It only handles the one mechanical
error shape common in generated model output: valid JSON surrounded by prose
or fenced code. Unrepairable input still raises ``json.JSONDecodeError``.
"""

from __future__ import annotations

import json
from typing import Any


def repair_json_string(raw: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start_obj = raw.find("{")
        start_arr = raw.find("[")
        starts = [idx for idx in (start_obj, start_arr) if idx >= 0]
        if not starts:
            raise
        start = min(starts)
        end = max(raw.rfind("}"), raw.rfind("]"))
        if end < start:
            raise
        return json.loads(raw[start : end + 1])
