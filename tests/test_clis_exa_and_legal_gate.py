"""Tests for the operator CLIs that bridge to the spec's
§15.1 validation criterion and the Sprint 18 audit acceptance:

  - `python -m acquisition.search.exa {discover,lookup,budget}`
  - `python -m substrate.legal_gate.audit`

Tests invoke the `main(argv=...)` entry points directly so we
don't depend on a subprocess boundary.
"""

from __future__ import annotations

import io
import json
import re
from datetime import UTC

import httpx
import pytest

from acquisition.search.exa.__main__ import (
    _build_parser as build_exa_parser,
)
from acquisition.search.exa.__main__ import (
    _cmd_budget,
    _cmd_discover,
    _cmd_lookup,
)
from acquisition.search.exa.__main__ import (
    main as exa_main,
)
from acquisition.search.exa.client import ExaClient
from substrate.legal_gate.audit import (
    _inconsistencies,
    _probe,
    _registry_summary,
)
from substrate.legal_gate.audit import (
    main as audit_main,
)

# ── Fixtures ──────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "graph.duckdb"))
    monkeypatch.setenv("EXA_API_KEY", "test-key")
    yield {"tmpdir": str(tmp_path), "events_dir": str(events_dir)}


# ── Exa CLI: argparse wiring ─────────────────────────────────────


def test_exa_parser_requires_subcommand():
    with pytest.raises(SystemExit):
        build_exa_parser().parse_args([])


def test_exa_parser_discover_requires_query_and_inv():
    p = build_exa_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["discover"])
    with pytest.raises(SystemExit):
        p.parse_args(["discover", "--query", "x"])
    # Both → OK.
    args = p.parse_args(["discover", "--query", "x", "--inv", "i"])
    assert args.query == "x"
    assert args.inv == "i"
    assert args.k == 10  # default


def test_exa_parser_lookup_requires_claim_and_inv():
    p = build_exa_parser()
    with pytest.raises(SystemExit):
        p.parse_args(["lookup"])
    args = p.parse_args(["lookup", "--claim", "c", "--inv", "i"])
    assert args.claim == "c"
    assert args.k == 3  # default


def test_exa_parser_budget_accepts_json_flag():
    args = build_exa_parser().parse_args(["budget", "--json"])
    assert args.json is True


# ── Exa CLI: budget subcommand ───────────────────────────────────


def test_exa_cli_budget_renders_table(isolated_env):
    args = build_exa_parser().parse_args(["budget"])
    buf = io.StringIO()
    rc = _cmd_budget(args, out=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "date:" in out
    assert "spent_usd:" in out


def test_exa_cli_budget_renders_json(isolated_env):
    args = build_exa_parser().parse_args(["budget", "--json"])
    buf = io.StringIO()
    rc = _cmd_budget(args, out=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["call_count"] == 0
    assert obj["spent_usd"] == 0.0


# ── Exa CLI: discover subcommand (with mocked Exa) ───────────────


def _mock_exa_client(payload: dict, *, status: int = 200) -> ExaClient:
    def handler(request):
        return httpx.Response(status, json=payload)

    return ExaClient(
        api_key="k",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: None,
    )


def test_exa_cli_discover_renders_table(isolated_env, monkeypatch):
    """Hook the discover() function inside the subcommand to a
    mocked client. We monkeypatch the discover symbol the
    subcommand resolved at import time."""
    import acquisition.search.exa.__main__ as cli_mod

    real_discover = cli_mod.discover

    def fake_discover(*, query, investigation_id, num_results, **kwargs):
        return real_discover(
            query=query, investigation_id=investigation_id,
            num_results=num_results, client=_mock_exa_client({
                "results": [
                    {"url": "https://arxiv.org/x", "title": "Paper",
                     "score": 0.9, "id": "r1"},
                    {"url": "https://nytimes.com/y", "title": "News",
                     "score": 0.7, "id": "r2"},
                ],
            }),
            use_cache=False,
        )

    monkeypatch.setattr(cli_mod, "discover", fake_discover)

    args = build_exa_parser().parse_args([
        "discover", "--query", "claude pricing",
        "--inv", "inv-cli-1", "--k", "2",
    ])
    buf = io.StringIO()
    rc = _cmd_discover(args, out=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "arxiv.org/x" in out
    assert "nytimes.com/y" in out
    # Table header should be present
    assert re.search(r"^#\s+tier\s+score\s+url\s+title", out, re.MULTILINE)


def test_exa_cli_discover_json_output(isolated_env, monkeypatch):
    import acquisition.search.exa.__main__ as cli_mod
    real_discover = cli_mod.discover

    def fake_discover(*, query, investigation_id, num_results, **kwargs):
        return real_discover(
            query=query, investigation_id=investigation_id,
            num_results=num_results, client=_mock_exa_client({
                "results": [{"url": "https://e.com/a", "title": "A"}],
            }),
            use_cache=False,
        )

    monkeypatch.setattr(cli_mod, "discover", fake_discover)
    args = build_exa_parser().parse_args([
        "discover", "--query", "q", "--inv", "i", "--k", "1", "--json",
    ])
    buf = io.StringIO()
    rc = _cmd_discover(args, out=buf)
    assert rc == 0
    arr = json.loads(buf.getvalue())
    assert isinstance(arr, list)
    assert len(arr) == 1
    assert arr[0]["url"] == "https://e.com/a"


# ── Exa CLI: lookup subcommand ───────────────────────────────────


def test_exa_cli_lookup_renders_table(isolated_env, monkeypatch):
    import acquisition.search.exa.__main__ as cli_mod
    real_lookup = cli_mod.exa_lookup_claim

    def fake_lookup(*, claim_text, investigation_id, k):
        return real_lookup(
            claim_text=claim_text, investigation_id=investigation_id, k=k,
            client=_mock_exa_client({
                "results": [
                    {"url": "https://ir.tesla.com/q3", "title": "Q3",
                     "score": 0.92, "text": "Q3 deliveries 462,890"},
                ],
            }),
        )

    monkeypatch.setattr(cli_mod, "exa_lookup_claim", fake_lookup)
    args = build_exa_parser().parse_args([
        "lookup", "--claim", "Tesla Q3 deliveries", "--inv", "inv-cli-2",
    ])
    buf = io.StringIO()
    rc = _cmd_lookup(args, out=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "ir.tesla.com/q3" in out


def test_exa_cli_lookup_rejects_empty_claim_via_exit_code(isolated_env, monkeypatch):
    """The CLI propagates ValueError as exit code 4."""
    import acquisition.search.exa.__main__ as cli_mod

    def fake_lookup(*, claim_text, investigation_id, k):
        raise ValueError("empty claim_text")

    monkeypatch.setattr(cli_mod, "exa_lookup_claim", fake_lookup)
    args = build_exa_parser().parse_args([
        "lookup", "--claim", "anything", "--inv", "i",
    ])
    buf_err = io.StringIO()
    # _cmd_lookup writes its error to sys.stderr; substitute via
    # monkeypatch since the function reaches into the module.
    monkeypatch.setattr("sys.stderr", buf_err)
    rc = _cmd_lookup(args, out=io.StringIO())
    assert rc == 4


# ── Exa CLI: main() integration ──────────────────────────────────


def test_exa_main_returns_budget_zero_exit(isolated_env):
    rc = exa_main(["budget", "--json"])
    assert rc == 0


# ── Exa CLI: retention subcommands (Finding E) ──────────────────


def test_exa_cli_retention_rollup_dry_run_renders_table(isolated_env):
    """Dry-run is read-only — should never raise even when no
    discovery_events dir exists yet."""
    args = build_exa_parser().parse_args([
        "retention", "rollup", "--dry-run",
    ])
    buf = io.StringIO()
    from acquisition.search.exa.__main__ import _cmd_retention_rollup
    rc = _cmd_retention_rollup(args, out=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "DRY RUN" in out
    assert "events_dir=" in out


def test_exa_cli_retention_rollup_dry_run_json(isolated_env):
    args = build_exa_parser().parse_args([
        "retention", "rollup", "--dry-run", "--json",
    ])
    buf = io.StringIO()
    from acquisition.search.exa.__main__ import _cmd_retention_rollup
    rc = _cmd_retention_rollup(args, out=buf)
    assert rc == 0
    obj = json.loads(buf.getvalue())
    assert obj["dry_run"] is True
    assert obj["retention_days"] == 30
    assert "files_examined" in obj


def test_exa_cli_retention_rollup_custom_retention_days(isolated_env):
    args = build_exa_parser().parse_args([
        "retention", "rollup", "--retention-days", "7", "--dry-run", "--json",
    ])
    buf = io.StringIO()
    from acquisition.search.exa.__main__ import _cmd_retention_rollup
    rc = _cmd_retention_rollup(args, out=buf)
    obj = json.loads(buf.getvalue())
    assert obj["retention_days"] == 7


def test_exa_cli_retention_summary_empty_db(isolated_env, monkeypatch):
    """With no graph DB present, summary should print a friendly
    'no rows' message and exit 0."""
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH",
                       str(isolated_env["tmpdir"]) + "/does-not-exist.duckdb")
    args = build_exa_parser().parse_args([
        "retention", "summary",
    ])
    buf = io.StringIO()
    from acquisition.search.exa.__main__ import _cmd_retention_summary
    rc = _cmd_retention_summary(args, out=buf)
    assert rc == 0
    assert "no discovery_summary" in buf.getvalue()


def test_exa_cli_retention_summary_with_rows(isolated_env, monkeypatch):
    """Populate the discovery_summary table and verify the summary
    subcommand renders the rows."""
    import json as _json
    from datetime import datetime, timedelta
    from pathlib import Path

    db = str(Path(isolated_env["tmpdir"]) / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    from substrate.graph import ensure_initialized
    ensure_initialized(db)

    # Pre-populate one row via the rollup harness.
    from acquisition.search.retention import rollup_expired

    edir = Path(isolated_env["tmpdir"]) / "discovery_events"
    edir.mkdir(parents=True, exist_ok=True)
    old_ts = (datetime.now(UTC) - timedelta(days=45)).replace(tzinfo=None).isoformat() + "Z"
    (edir / "old.jsonl").write_text(_json.dumps({
        "action_type": "discovery.proposed", "emitted_at": old_ts,
        "payload": {"provider": "exa", "query": "old query",
                    "url": "https://e.com/x", "cost_usd_estimate": 0.005},
    }))
    rollup_expired(retention_days=30, db_path=db, events_dir=str(edir))

    # The rolled-up event is 45 days old; pass --days 60 so the
    # summary window includes it.
    args = build_exa_parser().parse_args(["retention", "summary", "--days", "60"])
    buf = io.StringIO()
    from acquisition.search.exa.__main__ import _cmd_retention_summary
    rc = _cmd_retention_summary(args, out=buf)
    assert rc == 0
    out = buf.getvalue()
    assert "exa" in out
    assert "$0.0050" in out


def test_exa_parser_retention_requires_sub_subcommand():
    """`retention` alone with no `rollup` / `summary` should error."""
    with pytest.raises(SystemExit):
        build_exa_parser().parse_args(["retention"])


# ── Legal-gate audit CLI ─────────────────────────────────────────


def test_audit_registry_summary_shape():
    s = _registry_summary()
    assert set(s.keys()) == {
        "banned_domains",
        "banned_corpus_ids",
        "banned_authors",
        "banned_title_substrings",
        "banned_content_hash_prefixes",
    }
    for v in s.values():
        assert isinstance(v, list)


def test_audit_inconsistencies_empty_on_empty_registry():
    """With the shipped empty seed registry, there should be no
    inconsistencies flagged."""
    assert _inconsistencies() == []


def test_audit_inconsistencies_flags_bad_entries(monkeypatch):
    from substrate.legal_gate import registry as r

    monkeypatch.setattr(r, "BANNED_DOMAINS", ("https://libgen.is", "", "/path/x"))
    monkeypatch.setattr(r, "BANNED_CONTENT_HASH_PREFIXES", ("xyz123", " "))
    issues = _inconsistencies()
    assert any("scheme" in i for i in issues)
    assert any("empty" in i for i in issues)
    assert any("path" in i for i in issues)
    assert any("non-hex" in i for i in issues)


def test_audit_probe_no_inputs_returns_empty_dict():
    assert _probe(
        url=None, author=None, title=None,
        corpus_id=None, content_hash=None,
    ) == {}


def test_audit_probe_url_against_empty_registry_allows():
    p = _probe(
        url="https://example.com/x",
        author=None, title=None, corpus_id=None, content_hash=None,
    )
    assert p["url"]["reason"] is None
    assert p["composite"]["verdict_allowed"] is True


def test_audit_probe_url_against_populated_registry_rejects(monkeypatch):
    from substrate.legal_gate import registry as r

    monkeypatch.setattr(r, "BANNED_DOMAINS", ("libgen.is",))
    p = _probe(
        url="https://mirror.libgen.is/book/123",
        author=None, title=None, corpus_id=None, content_hash=None,
    )
    assert p["url"]["reason"] is not None
    assert "libgen.is" in p["url"]["reason"]
    assert p["composite"]["verdict_allowed"] is False


def test_audit_main_json_output(capsys):
    rc = audit_main(["--json"])
    assert rc == 0
    out = capsys.readouterr().out
    obj = json.loads(out)
    assert "summary" in obj
    assert "inconsistencies" in obj
    assert "probe" in obj


def test_audit_main_human_output_no_probe(capsys):
    rc = audit_main([])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Legal-gate registry summary" in out
    # No probe → no probe section
    assert "Probe results" not in out


def test_audit_main_human_output_with_probe(capsys, monkeypatch):
    from substrate.legal_gate import registry as r

    monkeypatch.setattr(r, "BANNED_AUTHORS", ("Margaret Atwood",))
    rc = audit_main([
        "--probe-author", "Margaret Atwood, et al.",
    ])
    assert rc == 0
    captured = capsys.readouterr()
    # Probe output goes to stdout
    assert "Probe results" in captured.out
    assert "BLOCKED" in captured.out or "REJECTED" in captured.out
