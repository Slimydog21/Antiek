"""Small deterministic text helpers shared by memory recall and routing."""

from __future__ import annotations

import re
import unicodedata

_WORD_RE = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)


def lexical_tokens(*values: str) -> tuple[str, ...]:
    """Return case-folded NFC word tokens without a search dependency."""
    return tuple(
        token.casefold()
        for value in values
        for token in _WORD_RE.findall(_normalized_unicode(value))
    )


def normalized_text(value: str) -> str:
    """Normalize presentation without discarding symbol position or number shape."""
    text = _normalized_unicode(value).casefold()
    output: list[str] = []
    for index, char in enumerate(text):
        previous = text[index - 1] if index else ""
        following = text[index + 1] if index + 1 < len(text) else ""
        if char.isalnum() or unicodedata.category(char).startswith("M") or char == "'":
            output.append(char)
        elif char.isspace():
            output.append(" ")
        elif char == "_" or unicodedata.category(char) == "Pd":
            if _is_word_char(previous) and _is_word_char(following):
                output.append(" ")
            elif following.isdigit() and (not previous or previous.isspace()):
                output.append("-")
            else:
                output.append(char)
        elif char in {"!", ",", ".", ":", ";", "?"}:
            output.append(char if previous.isdigit() and following.isdigit() else " ")
        else:
            output.append(char)
    return " ".join("".join(output).split())


def _is_word_char(value: str) -> bool:
    return bool(value) and (value.isalnum() or unicodedata.category(value).startswith("M"))


def _normalized_unicode(value: str) -> str:
    return unicodedata.normalize("NFC", value).replace("’", "'")


__all__ = ["lexical_tokens", "normalized_text"]
