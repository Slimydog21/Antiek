"""Narrow, rotatable authentication for the outbound Mac-mini bridge."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass(frozen=True, slots=True)
class BridgePrincipal:
    credential_id: str
    logical_worker_id: str
    scopes: frozenset[str]


def authenticate_bridge(request: Request) -> BridgePrincipal:
    """Authenticate one bridge credential without accepting browser sessions."""
    if request.cookies:
        raise HTTPException(status_code=401, detail="bridge authentication required")
    authorization = request.headers.get("Authorization", "")
    scheme, separator, token = authorization.partition(" ")
    credential_id, dot, secret = token.partition(".")
    if scheme != "AntiekBridge" or not separator or not dot or not secret:
        raise HTTPException(status_code=401, detail="bridge authentication required")
    try:
        credentials = json.loads(os.environ.get("ANTIEK_BRIDGE_CREDENTIALS_JSON", "{}"))
        record = credentials.get(credential_id)
        expected = str(record["secret_sha256"])
        logical_worker_id = str(record["logical_worker_id"])
        raw_scopes = record["scopes"]
        if not isinstance(raw_scopes, list) or not all(
            isinstance(scope, str) and scope for scope in raw_scopes
        ):
            raise TypeError
        scopes = frozenset(raw_scopes)
    except (AttributeError, KeyError, TypeError, ValueError):
        raise HTTPException(status_code=401, detail="bridge authentication required") from None
    supplied = hashlib.sha256(secret.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="bridge authentication required")
    if not credential_id or not logical_worker_id:
        raise HTTPException(status_code=401, detail="bridge authentication required")
    return BridgePrincipal(credential_id, logical_worker_id, scopes)


__all__ = ["BridgePrincipal", "authenticate_bridge"]
