"""Bounded form transport for the opt-in dev-login credential."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl

from fastapi import Request

_MAX_BODY_BYTES = 8192
_MAX_NEXT_CHARS = 2048
_BAD_PERCENT_ESCAPE = re.compile(rb"%(?![0-9A-Fa-f]{2})")


async def read_dev_login_form(request: Request) -> tuple[str, str]:
    """Return token and next without framework validation echoing either value."""
    content_type = request.headers.get("content-type", "")
    parts = [part.strip().lower() for part in content_type.split(";")]
    if parts[0] != "application/x-www-form-urlencoded" or any(
        part != "charset=utf-8" for part in parts[1:]
    ):
        raise ValueError("invalid dev-login form")

    body = bytearray()
    async for chunk in request.stream():
        if len(body) + len(chunk) > _MAX_BODY_BYTES:
            raise ValueError("invalid dev-login form")
        body.extend(chunk)
    if _BAD_PERCENT_ESCAPE.search(body):
        raise ValueError("invalid dev-login form")
    try:
        pairs = parse_qsl(
            body.decode("ascii"), keep_blank_values=True, strict_parsing=True,
            max_num_fields=2, encoding="utf-8", errors="strict",
        )
    except (UnicodeError, ValueError) as exc:
        raise ValueError("invalid dev-login form") from exc
    fields = dict(pairs)
    if len(fields) != len(pairs) or set(fields) - {"token", "next"} or "token" not in fields:
        raise ValueError("invalid dev-login form")
    next_path = fields.get("next", "/")
    if len(next_path) > _MAX_NEXT_CHARS:
        raise ValueError("invalid dev-login form")
    return fields["token"], next_path
