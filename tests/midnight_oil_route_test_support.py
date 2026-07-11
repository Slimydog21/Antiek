from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, Request

from interfaces.research.api.midnight_oil_routes import (
    MidnightOilDependencies,
    register_midnight_oil_routes,
)
from substrate.midnight_oil.job_store import SqliteDurableJobStore
from substrate.midnight_oil.spend_consent import SpendConsentStore


def register_authenticated_midnight_oil(app: FastAPI, tmp_path: Path) -> None:
    key = secrets.token_bytes(32)

    @app.middleware("http")
    async def authenticated_test_state(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.user_id = request.headers.get("x-test-user", "__operator__")
        return await call_next(request)

    register_midnight_oil_routes(
        app,
        MidnightOilDependencies(
            jobs=SqliteDurableJobStore(str(tmp_path / "midnight-oil-jobs.sqlite3")),
            consents=SpendConsentStore(tmp_path / "midnight-oil-consents.sqlite3"),
            active_key_id="test-key",
            signing_key=key,
            verification_keys={"test-key": key},
            test_mode=True,
        ),
    )
