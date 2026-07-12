"""Explicit production composition root for the Midnight Oil API.

The default module-level FastAPI app remains offline/non-spending. Operators
launch this factory explicitly with a closed config file and environment-held
keys; construction fails before serving if durable stores, keyring, provider
attestations, or the dispatch plan are incomplete.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI

from substrate.dispatch import DispatchConfig
from substrate.midnight_oil.live import build_router_live_plan
from substrate.midnight_oil.runtime import (
    MidnightOilRuntimeConfig,
    MidnightOilRuntimeStores,
    build_runtime_stores,
    install_attested_providers,
    load_consent_keyring,
)

from .midnight_oil_routes import MidnightOilDependencies


@dataclass(frozen=True)
class MidnightOilApiRuntime:
    config: MidnightOilRuntimeConfig
    stores: MidnightOilRuntimeStores
    dependencies: MidnightOilDependencies
    dispatch_config: DispatchConfig


def build_midnight_oil_api_runtime(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> MidnightOilApiRuntime:
    environment = os.environ if environ is None else environ
    config = MidnightOilRuntimeConfig.from_file(config_path)
    signing_key, verification_keys = load_consent_keyring(config, environment)
    install_attested_providers(config, environment)
    dispatch_config = DispatchConfig.from_yaml(config.dispatch_config_path)
    stores = build_runtime_stores(config)
    dependencies = MidnightOilDependencies(
        owner_jobs=stores.owner_jobs,
        jobs=stores.jobs,
        consents=stores.consents,
        operation_queue=stores.operation_queue,
        active_key_id=config.consent_active_key_id,
        signing_key=signing_key,
        verification_keys=verification_keys,
        live_plan_resolver=lambda job: build_router_live_plan(
            job, config=dispatch_config
        ),
    )
    return MidnightOilApiRuntime(
        config=config,
        stores=stores,
        dependencies=dependencies,
        dispatch_config=dispatch_config,
    )


def create_midnight_oil_production_app(
    config_path: str | Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    """Construct the only API app that mounts spend-authoritative routes."""

    from .app import create_app

    environment = os.environ if environ is None else environ
    runtime = build_midnight_oil_api_runtime(config_path, environ=environment)
    app = create_app(
        register_providers=False,
        enable_midnight_oil=True,
        midnight_oil_dependencies=runtime.dependencies,
        operator_auth_environ=environment,
    )
    app.state.midnight_oil_runtime = runtime
    return app


def production_app() -> FastAPI:
    """Uvicorn ``--factory`` entrypoint; config path is explicit in env."""

    path = os.environ.get("ANTIEK_MIDNIGHT_OIL_CONFIG", "").strip()
    if not path:
        raise RuntimeError("ANTIEK_MIDNIGHT_OIL_CONFIG is required")
    return create_midnight_oil_production_app(path)


__all__ = [
    "MidnightOilApiRuntime",
    "build_midnight_oil_api_runtime",
    "create_midnight_oil_production_app",
    "production_app",
]
