"""Residual (sy): frontend WRITE_SEED_FEED_SOURCES ≡ substrate frozenset.

Prevents Settings honesty chrome from drifting off TWIN_WRITE_SEED_USAGE_SOURCES.
"""

from __future__ import annotations

import re
from pathlib import Path

from substrate.antiek_bench.usage_bridge import TWIN_WRITE_SEED_USAGE_SOURCES

_REPO = Path(__file__).resolve().parents[1]
_TS = (
    _REPO
    / "apps"
    / "reading"
    / "src"
    / "lib"
    / "writeSeedFeedSources.ts"
)


def _parse_ts_write_seed_sources() -> set[str]:
    text = _TS.read_text(encoding="utf-8")
    # WRITE_SEED_FEED_SOURCES: readonly string[] = [ "a", "b", ... ]
    m = re.search(
        r"WRITE_SEED_FEED_SOURCES[^=]*=\s*\[(.*?)\]\s*as const",
        text,
        re.DOTALL,
    )
    assert m, "WRITE_SEED_FEED_SOURCES array not found in writeSeedFeedSources.ts"
    body = m.group(1)
    return set(re.findall(r'"([a-z0-9_]+)"', body))


def test_write_seed_feed_sources_match_substrate() -> None:
    frontend = _parse_ts_write_seed_sources()
    backend = set(TWIN_WRITE_SEED_USAGE_SOURCES)
    assert frontend == backend, (
        f"frontend-only={sorted(frontend - backend)} "
        f"backend-only={sorted(backend - frontend)}"
    )
    # twin_draft_selected must stay excluded (covered by twin_chase).
    assert "twin_draft_selected" not in frontend
    assert "twin_promote_context" in frontend
    assert "deep_research_session" in frontend
