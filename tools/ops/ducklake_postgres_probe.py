"""Operator probe for OA-012 DuckLake Postgres catalog deployment.

OA-012 closes only after the operator runs a real production round trip against
the Postgres-backed DuckLake catalog and records the evidence. This probe
executes that register/lookup proof without printing the production DSN.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from substrate.ducklake.catalog import DuckLakeCatalog, PostgresCatalogBackend

DEFAULT_DSN_ENV = "ANTIEK_DUCKLAKE_POSTGRES_DSN"
DEFAULT_USER_ID = "antiek-oa012-postgres-probe"
DEFAULT_DB_PATH = "/tmp/antiek-oa012-postgres-probe.duckdb"


@dataclass(frozen=True)
class ProbeCheck:
    name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class DuckLakePostgresProbeResult:
    status: str
    dsn_env: str
    dsn_configured: bool
    user_id: str
    db_path: str
    checks: list[ProbeCheck]
    does_not_close_oa012: bool = True


BackendFactory = Callable[[str], PostgresCatalogBackend]


def _default_backend_factory(dsn: str) -> PostgresCatalogBackend:
    return PostgresCatalogBackend(dsn=dsn)


def probe_ducklake_postgres(
    *,
    dsn: str | None,
    dsn_env: str = DEFAULT_DSN_ENV,
    user_id: str = DEFAULT_USER_ID,
    db_path: str = DEFAULT_DB_PATH,
    cleanup: bool = True,
    backend_factory: BackendFactory | None = None,
) -> DuckLakePostgresProbeResult:
    checks: list[ProbeCheck] = []
    dsn_configured = bool(dsn and dsn.strip())
    checks.append(ProbeCheck(
        name="dsn_configured",
        passed=dsn_configured,
        detail=f"{dsn_env} is set" if dsn_configured else f"{dsn_env} is empty",
    ))
    if not dsn_configured:
        return DuckLakePostgresProbeResult(
            status="FAIL",
            dsn_env=dsn_env,
            dsn_configured=False,
            user_id=user_id,
            db_path=db_path,
            checks=checks,
        )

    backend_factory = backend_factory or _default_backend_factory
    try:
        backend = backend_factory(dsn.strip())
        catalog = DuckLakeCatalog(backend=backend)
    except Exception as exc:  # noqa: BLE001 - probe reports constructor failures
        checks.append(ProbeCheck(
            name="postgres_backend_constructed",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        ))
        return DuckLakePostgresProbeResult(
            status="FAIL",
            dsn_env=dsn_env,
            dsn_configured=True,
            user_id=user_id,
            db_path=db_path,
            checks=checks,
        )

    checks.append(ProbeCheck(
        name="postgres_backend_constructed",
        passed=True,
        detail="PostgresCatalogBackend constructed and schema initialized",
    ))

    try:
        entry = catalog.register(
            user_id=user_id,
            db_path=db_path,
            encryption_key_ref="alias/antiek-graph-oa012-probe",
            shard_id="oa012",
            last_size_bytes=12,
        )
        looked_up = catalog.lookup(user_id)
    except Exception as exc:  # noqa: BLE001 - probe reports live round-trip failures
        checks.append(ProbeCheck(
            name="register_lookup_round_trip",
            passed=False,
            detail=f"{type(exc).__name__}: {exc}",
        ))
        return DuckLakePostgresProbeResult(
            status="FAIL",
            dsn_env=dsn_env,
            dsn_configured=True,
            user_id=user_id,
            db_path=db_path,
            checks=checks,
        )

    checks.append(ProbeCheck(
        name="register_lookup_round_trip",
        passed=looked_up == entry,
        detail=(
            "lookup matched registered entry"
            if looked_up == entry
            else f"lookup mismatch: expected={entry!r} actual={looked_up!r}"
        ),
    ))

    if cleanup:
        try:
            removed = catalog.deregister(user_id)
            after_cleanup = catalog.lookup(user_id)
        except Exception as exc:  # noqa: BLE001 - cleanup failure should be visible
            checks.append(ProbeCheck(
                name="cleanup_removed_probe_row",
                passed=False,
                detail=f"{type(exc).__name__}: {exc}",
            ))
        else:
            checks.append(ProbeCheck(
                name="cleanup_removed_probe_row",
                passed=removed and after_cleanup is None,
                detail=(
                    "probe row removed"
                    if removed and after_cleanup is None
                    else f"removed={removed} after_cleanup={after_cleanup!r}"
                ),
            ))
    else:
        checks.append(ProbeCheck(
            name="cleanup_removed_probe_row",
            passed=True,
            detail="cleanup skipped by operator request",
        ))

    return DuckLakePostgresProbeResult(
        status="PASS" if all(check.passed for check in checks) else "FAIL",
        dsn_env=dsn_env,
        dsn_configured=True,
        user_id=user_id,
        db_path=db_path,
        checks=checks,
    )


def format_text(result: DuckLakePostgresProbeResult) -> str:
    lines = [
        f"ducklake-postgres-probe: {result.status}",
        f"dsn_env: {result.dsn_env}",
        f"dsn_configured: {'yes' if result.dsn_configured else 'no'}",
        f"user_id: {result.user_id}",
        f"db_path: {result.db_path}",
    ]
    for check in result.checks:
        marker = "PASS" if check.passed else "FAIL"
        lines.append(f"{marker} {check.name}: {check.detail}")
    lines.append("oa012_closed_by_this_probe: no")
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the OA-012 DuckLake Postgres catalog register/lookup proof. "
            "Does not print the DSN or close OA-012 by itself."
        )
    )
    parser.add_argument(
        "--dsn",
        default=None,
        help=(
            "Postgres DSN. Prefer the env var; this value is never printed. "
            f"Default: ${DEFAULT_DSN_ENV}"
        ),
    )
    parser.add_argument(
        "--dsn-env",
        default=DEFAULT_DSN_ENV,
        help=f"Env var used when --dsn is omitted. Default: {DEFAULT_DSN_ENV}",
    )
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--db-path", default=DEFAULT_DB_PATH)
    parser.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Leave the probe row in catalog_entries for manual inspection.",
    )
    parser.add_argument("--json", action="store_true", help="Emit JSON.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dsn = args.dsn if args.dsn is not None else os.environ.get(args.dsn_env)
    result = probe_ducklake_postgres(
        dsn=dsn,
        dsn_env=args.dsn_env,
        user_id=args.user_id,
        db_path=args.db_path,
        cleanup=not args.no_cleanup,
    )
    if args.json:
        print(json.dumps(asdict(result), indent=2, sort_keys=True))
    else:
        print(format_text(result))
    return 0 if result.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
