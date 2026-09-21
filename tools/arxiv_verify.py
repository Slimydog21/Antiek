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

from runtime.db_lock import connect_read

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

# Defensive SSL bootstrap (SPR-05 task 3) — the endpoint check reaches
# export.arxiv.org over HTTPS through urllib, which builds its SSLContext at
# call time, so running here is early enough. A python.org interpreter has no
# system CA bundle. No-op when SSL_CERT_FILE is already set.
from runtime.ssl_bootstrap import bootstrap as _ssl_bootstrap  # noqa: E402

_ssl_bootstrap()


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

@dataclass(frozen=True)
class _UrlopenResult:
    """A urllib outcome in the ``.status_code`` / ``.headers`` shape the arXiv
    throttle reads for its 429 ban sentinel.

    ``urllib.request.urlopen`` raises ``HTTPError`` on a 4xx rather than
    returning it, so a 429 handed straight back through the governor would
    escape ``note_response`` and the ban sentinel would never arm — the failure
    this check exists to catch. ``_send`` therefore converts both outcomes into
    this one shape and the HTTPError is re-read from ``error`` afterwards.
    """

    status_code: int
    headers: dict[str, str]
    body: bytes
    error: urllib.error.HTTPError | None = None


def _check_endpoint_health(base_url: str, timeout: float = 15.0) -> Check:
    """GET the OAI-PMH Identify verb through the host-global arXiv governor.
    Verifies the endpoint is reachable and returns valid OAI-PMH XML.

    The verifier probes the SAME host production harvests
    (``oaipmh.arxiv.org``), and arXiv bans by IP, so an ungoverned probe here
    competes with a running harvest for the one-per-three-seconds budget and can
    itself trip the ban it is meant to report. Routing the send through
    ``govern_if_arxiv`` on the canonical throttle means the probe (a) waits its
    turn behind any other arXiv job on this box, (b) arms the ban sentinel if it
    draws a 429, and (c) refuses to egress at all while a ban is already armed —
    reporting that state instead of deepening it.
    """
    from acquisition.arxiv.client import default_user_agent
    from acquisition.arxiv.rate_governor import canonical_arxiv_throttle, govern_if_arxiv
    from acquisition.arxiv.throttle import ArxivBanned

    url = f"{base_url}?verb=Identify"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": default_user_agent()},
        )

        def _send() -> _UrlopenResult:
            try:
                with urllib.request.urlopen(req, timeout=timeout) as resp:
                    return _UrlopenResult(
                        status_code=int(getattr(resp, "status", 200) or 200),
                        headers=dict(getattr(resp, "headers", None) or {}),
                        body=resp.read(),
                    )
            except urllib.error.HTTPError as http_err:
                # Returned, not raised, so the governor's note_response sees the
                # status and a 429 arms the sentinel. Re-read from .error below.
                return _UrlopenResult(
                    status_code=int(http_err.code),
                    headers=dict(http_err.headers or {}),
                    body=b"",
                    error=http_err,
                )

        try:
            sent = govern_if_arxiv(url, _send, throttle=canonical_arxiv_throttle())
        except ArxivBanned:
            # A ban is already armed. Probing now would extend it; the honest
            # verdict is that the endpoint was deliberately NOT probed.
            return Check(
                name="endpoint_health",
                passed=False,
                detail="ban sentinel armed, endpoint not probed",
            )
        if sent.error is not None:
            raise sent.error
        body = sent.body
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
        con = connect_read(db_path)
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
