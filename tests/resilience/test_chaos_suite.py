"""nygard SPR-06 — chaos suite: replay the INFRA-FAULT agent-failure fixtures
deterministically, via the SPR-01 injectors + the real substrate contracts.

Promotes ``tests/regression/agent_failures/`` (the infra-fault bucket ONLY) into a
runnable chaos suite. Each replay is keyed by the fixture id and asserts the
fixture exists (provenance preserved). The Phase-8-policy and §9.0-serve buckets
stay in ``tests/regression/test_agent_failures.py`` — untouched.

(The spec names this module ``chaos_suite.py``; it is named ``test_chaos_suite.py``
so pytest's default ``python_files = test_*.py`` actually collects + runs it — a
chaos suite that never runs is worthless.)

SPR-06 M1 classification (documented + enforced by the scope-boundary test below):
- infra-fault (chaos scope): loky-semaphore, arxiv-429, banned-until-sentinel,
  arxiv-missing-ssl-env, undersized-metadata-cache.
- Phase-8-policy (NOT here): phase8-skill-patch-gate-in-shadow-mode,
  drw_smoke_phase8_skill_patch.
- §9.0-serve (NOT here): web-article-served-at-user-owned,
  youtube-transcript-at-user-owned.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
import yaml

_FIX_DIR = Path(__file__).resolve().parents[1] / "regression" / "agent_failures"

INFRA_FAULT_FIXTURES: tuple[str, ...] = (
    "loky-semaphore-parameter-extractor",
    "arxiv-429-export-ban",
    "banned-until-sentinel-absent",
    "arxiv-missing-ssl-env",
    "undersized-metadata-cache",
)

# Fixtures we cannot yet drive deterministically — replayed as VISIBLE, documented
# stubs (not silently skipped), per the spec.
STUB_REPLAYS: dict[str, str] = {
    "arxiv-missing-ssl-env": (
        "needs an env-scrub scenario over the live SSL fetch path (SSL_CERT_FILE "
        "absence); no deterministic injector for a TLS/env fault yet"
    ),
    "undersized-metadata-cache": (
        "needs the arxiv metadata-cache internals (cache sizing); not an "
        "fs/db/provider/throttle seam the shipped harness can drive"
    ),
}

# Fixtures in OTHER buckets — must NOT leak into the chaos scope.
_OTHER_BUCKET_FIXTURES = (
    "phase8-skill-patch-gate-in-shadow-mode",
    "web-article-served-at-user-owned",
    "youtube-transcript-at-user-owned",
)


def _load(fixture_id: str) -> dict:
    p = _FIX_DIR / f"{fixture_id}.yaml"
    assert p.exists(), f"infra-fault fixture missing: {p}"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {}


# --------------------------------------------------------------------------- #
# Replays — each asserts the CORRECT post-fix behaviour.
# --------------------------------------------------------------------------- #


def _replay_loky_semaphore(_tmp_path) -> None:
    """The Phase-A loky OS-semaphore leak is architecturally eliminated (asyncio
    migration — SPR-07). Replay the modern guarantee: the async semaphore releases
    its permit on every abnormal teardown, so N kills never wedge the bound."""

    async def run() -> None:
        sem = asyncio.Semaphore(3)

        class _ExternalKill(RuntimeError):
            pass

        for _ in range(20):
            with pytest.raises(_ExternalKill):
                async with sem:
                    raise _ExternalKill()
            assert sem._value == 3  # permit released — no leak

    asyncio.run(run())


def _replay_arxiv_429(tmp_path) -> None:
    """A 429 must arm the banned_until sentinel so the next request PAUSES
    (SourceBanned) instead of re-hitting the banned host — the 2026-05-17 fix."""
    from substrate.source_throttle import SourceBanned, SourceThrottle

    clock = {"t": 1000.0}
    thr = SourceThrottle(
        state_path=str(tmp_path / "throttle.json"),
        now=lambda: clock["t"],
        sleep=lambda _s: None,
    )
    thr.note_response("arxiv", 429)
    assert thr.is_banned("arxiv")
    with pytest.raises(SourceBanned):
        thr.before_request("arxiv")  # pauses, does NOT re-attempt
    # Once the ban expires, requests are allowed again.
    clock["t"] = thr.banned_until("arxiv") + 1.0
    thr.before_request("arxiv")  # no raise


def _replay_banned_until_sentinel(tmp_path) -> None:
    """The fix persisted the ban sentinel cross-process. A FRESH throttle over the
    same state file must still see the ban — not re-hit because it forgot."""
    from substrate.source_throttle import SourceBanned, SourceThrottle

    clock = {"t": 1000.0}
    path = str(tmp_path / "throttle.json")
    SourceThrottle(state_path=path, now=lambda: clock["t"]).note_response("arxiv", 503)
    fresh = SourceThrottle(
        state_path=path, now=lambda: clock["t"], sleep=lambda _s: None
    )
    assert fresh.is_banned("arxiv")  # sentinel survived the new instance
    with pytest.raises(SourceBanned):
        fresh.before_request("arxiv")


_REPLAYS = {
    "loky-semaphore-parameter-extractor": _replay_loky_semaphore,
    "arxiv-429-export-ban": _replay_arxiv_429,
    "banned-until-sentinel-absent": _replay_banned_until_sentinel,
}


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture_id", INFRA_FAULT_FIXTURES)
def test_chaos_replay(fixture_id, tmp_path):
    fx = _load(fixture_id)
    assert fx.get("id") == fixture_id  # provenance: the fixture the replay claims
    if fixture_id in STUB_REPLAYS:
        pytest.skip(f"replay: stub — {STUB_REPLAYS[fixture_id]}")
    _REPLAYS[fixture_id](tmp_path)


def test_every_infra_fixture_is_driveable_or_documented_stub():
    """No infra-fault fixture may fall through silently — each is either replayed
    or an explicitly documented stub."""
    covered = set(_REPLAYS) | set(STUB_REPLAYS)
    assert set(INFRA_FAULT_FIXTURES) == covered
    for fid in INFRA_FAULT_FIXTURES:
        assert (_FIX_DIR / f"{fid}.yaml").exists(), f"missing fixture {fid}"


def test_scope_excludes_other_buckets():
    """Phase-8-policy and §9.0-serve fixtures must NOT be pulled into the chaos
    scope — they keep their existing regression runner."""
    for fid in _OTHER_BUCKET_FIXTURES:
        assert fid not in INFRA_FAULT_FIXTURES
        assert (_FIX_DIR / f"{fid}.yaml").exists()  # they still exist, elsewhere
