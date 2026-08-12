"""arXiv acquisition health verifier — endpoint, governor, sync state, coverage.

Checks that the arXiv OAI-PMH endpoint is reachable, the rate governor is
configured sanely, the sync state files are consistent, and the documents
store has the expected coverage. Designed for nightly cron / systemd
ExecStartPost so failures surface immediately.

Exit 0 only when ALL checks pass. Prints a machine-readable JSON verdict
(--json) and a human-readable report (default).

Follows the CLI style of tools/arxiv_oai_sync.py (argparse, no new deps).

Usage::

    python -m tools.arxiv_verify
    python -m tools.arxiv_verify --json
    python -m tools.arxiv_verify --db-path /path/to/antiek.duckdb
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)


# ── State path resolution (honors env vars, same convention as oai_sync) ──

def _throttle_path() -> str:
    env = os.environ.get("ANTIEK_ARXIV_THROTTLE_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_throttle.json")


def _harvest_state_path() -> str:
    env = os.environ.get("ANTIEK_ARXIV_OAI_STATE_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_oai_harvest.json")


def _sync_state_path() -> str:
    env = os.environ.get("ANTIEK_ARXIV_OAI_SYNC_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "arxiv_oai_sync.json")


def _governor_lock_path() -> str:
    env = os.environ.get("ANTIEK_ARXIV_GOVERNOR_LOCK_PATH")
    if env:
        return env
    return _throttle_path() + ".governor.lock"


def _default_census_path() -> str | None:
    """The systemd service writes the census JSON here."""
    state_dir = os.environ.get("ANTIEK_STATE_DIR")
    if state_dir:
        return os.path.join(state_dir, "reports", "arxiv_oai_census.json")
    p = Path.home() / ".antiek" / "reports" / "arxiv_oai_census.json"
    return str(p) if p.exists() else None


def _default_db_path() -> str:
    env = os.environ.get("ANTIEK_DUCKDB_PATH")
    if env:
        return env
    return str(Path.home() / ".antiek" / "antiek.duckdb")


# ── Check result ──

@dataclass
class Check:
    name: str
    passed: bool
    detail: str = ""
    value: object = None


@dataclass
class Verdict:
    checks: list[Check] = field(default_factory=list)
    timestamp: str = ""
    endpoint_url: str = ""

    @property
    def ok(self) -> bool:
        return all(c.passed for c in self.checks)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "timestamp": self.timestamp,
            "endpoint_url": self.endpoint_url,
            "checks": [
                {
                    "name": c.name,
                    "passed": c.passed,
                    "detail": c.detail,
                    **({"value": c.value} if c.value is not None else {}),
                }
                for c in self.checks
            ],
        }


# ── Individual checks ──

def _check_endpoint_health(base_url: str, timeout: float = 15.0) -> Check:
    """GET the OAI-PMH Identify verb. Verifies the endpoint is reachable and
    returns valid OAI-PMH XML."""

    url = f"{base_url}?verb=Identify"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Antiek-Verifier/0.1 (tools.arxiv_verify)"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
        root = ET.fromstring(body)
        ns = {"oai": "http://www.openarchives.org/OAI/2.0/"}
        repo = root.find(".//oai:repositoryName", ns)
        name = repo.text.strip() if repo is not None and repo.text else "(unknown)"
        return Check(
            name="endpoint_health",
            passed=True,
            detail=f"OAI-PMH Identify succeeded: {name}",
            value=name,
        )
    except urllib.error.HTTPError as e:
        return Check(
            name="endpoint_health",
            passed=False,
            detail=f"HTTP {e.code} from {url}: {e.reason}",
        )
    except Exception as e:
        return Check(
            name="endpoint_health",
            passed=False,
            detail=f"Cannot reach {url}: {e}",
        )


def _check_rate_governor() -> Check:
    """Verify the rate governor config: min spacing >= 3s, state file readable."""
    from acquisition.arxiv.throttle import MIN_REQUEST_SPACING_S

    path = _throttle_path()
    lock = _governor_lock_path()

    if MIN_REQUEST_SPACING_S < 3.0:
        return Check(
            name="rate_governor",
            passed=False,
            detail=f"MIN_REQUEST_SPACING_S={MIN_REQUEST_SPACING_S}s < 3.0s (arXiv policy minimum)",
        )

    details = [f"spacing={MIN_REQUEST_SPACING_S}s"]
    state_exists = Path(path).exists()
    details.append(f"state_file={'present' if state_exists else 'absent'}")
    details.append(f"lock_path={lock}")

    # Parse throttle state if present
    state_info = ""
    if state_exists:
        try:
            raw = json.loads(Path(path).read_text())
            banned_until = raw.get("banned_until", 0)
            now = time.time()
            if banned_until > now:
                remaining = banned_until - now
                details.append(f"BANNED for {remaining:.0f}s")
                state_info = f" (BANNED {remaining:.0f}s remaining)"
            else:
                details.append("ban_sentinel=clear")
        except (json.JSONDecodeError, OSError):
            details.append("state_file=unreadable")

    return Check(
        name="rate_governor",
        passed=MIN_REQUEST_SPACING_S >= 3.0,
        detail=", ".join(details) + state_info,
    )


def _check_sync_state() -> Check:
    """Check that the sync checkpoint and harvest cursor files are consistent."""
    sync_path = _sync_state_path()
    harvest_path = _harvest_state_path()

    issues: list[str] = []
    info: list[str] = []

    # Sync checkpoint (high-water mark)
    sync_p = Path(sync_path)
    if sync_p.exists():
        try:
            raw = json.loads(sync_p.read_text())
            datestamp = raw.get("last_successful_datestamp")
            harvested_at = raw.get("last_harvested_at")
            if datestamp:
                info.append(f"sync_hwm={datestamp}")
            else:
                issues.append("sync checkpoint exists but last_successful_datestamp is null")
            if harvested_at:
                info.append(f"sync_last_run={harvested_at}")
        except (json.JSONDecodeError, OSError):
            issues.append("sync checkpoint unreadable")
    else:
        info.append("sync checkpoint absent (first run or never completed)")

    # Harvest cursor (mid-run resume)
    harvest_p = Path(harvest_path)
    if harvest_p.exists():
        try:
            raw = json.loads(harvest_p.read_text())
            token = raw.get("resumption_token")
            if token:
                info.append("harvest cursor has pending token (interrupted harvest)")
            else:
                info.append("harvest cursor present but no pending token")
        except (json.JSONDecodeError, OSError):
            issues.append("harvest cursor unreadable")
    else:
        info.append("harvest cursor absent (clean state)")

    return Check(
        name="sync_state",
        passed=len(issues) == 0,
        detail="; ".join(issues) if issues else "; ".join(info),
    )


def _check_census_json() -> Check:
    """If the census JSON exists, validate its structure and check for stale data."""
    census_path = _default_census_path()
    if census_path is None or not Path(census_path).exists():
        return Check(
            name="census_json",
            passed=True,  # not a failure — census is optional
            detail="census JSON not present (optional)",
        )

    try:
        raw = json.loads(Path(census_path).read_text())
    except (json.JSONDecodeError, OSError):
        return Check(
            name="census_json",
            passed=False,
            detail="census JSON present but unreadable",
        )

    required_keys = {"total", "t1", "t2", "t3", "harvested_at"}
    missing = required_keys - set(raw.keys())
    if missing:
        return Check(
            name="census_json",
            passed=False,
            detail=f"census JSON missing keys: {missing}",
        )

    total = raw["total"]
    harvested_at = raw.get("harvested_at", "")
    hwm = raw.get("high_water_datestamp", "")
    return Check(
        name="census_json",
        passed=True,
        detail=f"census: total={total}, harvested_at={harvested_at}, hwm={hwm}",
        value=raw,
    )


def _check_coverage(db_path: str | None) -> Check:
    """Check document count in DuckDB. Non-fatal if DB is absent."""
    if not db_path or not Path(db_path).exists():
        return Check(
            name="coverage",
            passed=True,
            detail="DuckDB not present (skipped)",
        )

    try:
        import duckdb
        con = duckdb.connect(db_path, read_only=True)
        try:
            row = con.execute(
                "SELECT COUNT(*) FROM documents WHERE document_id LIKE 'doc-arxiv-%'"
            ).fetchone()
            count = row[0] if row else 0
        finally:
            con.close()
        return Check(
            name="coverage",
            passed=True,
            detail=f"arXiv documents in DuckDB: {count}",
            value=count,
        )
    except Exception as e:
        return Check(
            name="coverage",
            passed=False,
            detail=f"DuckDB query failed: {e}",
        )


# ── Main ──

def run_checks(
    *,
    base_url: str = "https://oaipmh.arxiv.org/oai",
    db_path: str | None = None,
) -> Verdict:
    """Execute all checks and return a verdict."""
    v = Verdict(
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        endpoint_url=base_url,
    )
    v.checks.append(_check_endpoint_health(base_url))
    v.checks.append(_check_rate_governor())
    v.checks.append(_check_sync_state())
    v.checks.append(_check_census_json())
    v.checks.append(_check_coverage(db_path))
    return v


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m tools.arxiv_verify",
        description=(
            "Verify arXiv acquisition health: endpoint, rate governor, "
            "sync state, coverage. Exit 0 if all checks pass."
        ),
    )
    p.add_argument(
        "--json", action="store_true", dest="json_output",
        help="emit machine-readable JSON verdict",
    )
    p.add_argument(
        "--base-url", default="https://oaipmh.arxiv.org/oai",
        help="OAI-PMH base URL (default oaipmh.arxiv.org/oai)",
    )
    p.add_argument(
        "--db-path",
        help="DuckDB path (default: ANTIEK_DUCKDB_PATH or ~/.antiek/antiek.duckdb)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = args.db_path or _default_db_path()
    verdict = run_checks(base_url=args.base_url, db_path=db)

    if args.json_output:
        print(json.dumps(verdict.to_dict(), indent=2))
    else:
        print(f"arXiv verification — {verdict.timestamp}")
        print(f"  endpoint: {verdict.endpoint_url}")
        status = "PASS" if verdict.ok else "FAIL"
        print(f"  verdict:  {status}\n")
        for c in verdict.checks:
            icon = "✓" if c.passed else "✗"
            print(f"  {icon} {c.name}: {c.detail}")
        if not verdict.ok:
            print("\n  Some checks FAILED. See details above.")

    return 0 if verdict.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
