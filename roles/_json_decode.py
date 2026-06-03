"""Shared JSON-tolerant decoder for role response parsers.

Originally lived inside ``interfaces/research/api/wrestling.py``;
extracted in Sprint 4 day 4-5 because three role modules now import
it (``roles.grounder.parser``, ``roles.note_taker.parser``,
``roles.challenger`` future) and the wrestling-module-level home was
creating import cycles when the formalized roles loaded.

Has zero downstream dependencies. Safe to import from anywhere.

The wrestling bridge re-exports the same name (its
``_extract_json_object`` is now a thin alias) so existing callers
keep working without churn.
"""

from __future__ import annotations

import json


def extract_json_object(text: str) -> dict | None:
    """Best-effort JSON extraction. Handles the common LLM failure
    modes: extra prose before/after, ```json fences, trailing
    commentary. Returns the first balanced ``{...}`` that decodes
    or None when nothing parses.

    Does NOT attempt to fix trailing commas, smart quotes, or other
    structural issues — if the model produces invalid JSON despite
    the role prompt's explicit "no markdown fences, JSON only"
    instruction, the conservative answer is to return None and let
    the caller fall back to its default-on-failure path (usually:
    skip emission rather than fabricate structured output).
    """
    text = text.strip()
    if not text:
        return None
    # Strip ```json ... ``` fences.
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json\n"):
            text = text[5:]
        elif text.lower().startswith("json"):
            text = text[4:]
    # Find the first balanced { ... } that decodes.
    start = text.find("{")
    while start != -1:
        end = text.rfind("}")
        while end > start:
            candidate = text[start : end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                end = text.rfind("}", start, end)
        start = text.find("{", start + 1)
    return None
