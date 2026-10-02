"""The web app must read the field names the API actually emits.

Two silent breaks found on 2026-09-20, both in CommandPalette.tsx, both
invisible because the reader supplied a fallback:

  inv.topic   -> InvestigationSummary has `question`, never `topic`, so every
                 investigation row fell through to `?? inv.investigation_id`
                 and displayed a raw UUID.
  data.parked -> WatchForLaterResponse is {count, questions}, so `?? []` made
                 the parked-question section permanently empty.

Neither raised. A wrong key in TypeScript is `undefined`, and `??` turns
`undefined` into a plausible-looking default — the same shape as every other
defect in this audit: a check that stops measuring and reports success.

`lib/api.ts` declared the correct names for both endpoints the whole time, so
the contract was known; one file simply disagreed with it and nothing
compared them. This test is that comparison.

It reads the field names out of the live OpenAPI schema rather than a
hardcoded list, so a backend rename fails here too, not just a frontend typo.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from interfaces.research.api.app import create_app

_PALETTE = (
    Path(__file__).resolve().parents[1]
    / "apps" / "reading" / "src" / "components" / "CommandPalette.tsx"
)


def _schema_properties(model: str) -> set[str]:
    spec: dict[str, Any] = create_app().openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    assert schemas, "openapi produced no component schemas — check is vacuous"
    assert model in schemas, f"{model} missing from the schema; was it renamed?"
    props = set(schemas[model].get("properties", {}))
    assert props, f"{model} declared no properties — check is vacuous"
    return props


def _palette_source() -> str:
    src = _PALETTE.read_text(encoding="utf-8")
    assert len(src) > 1000, "CommandPalette.tsx looks truncated"
    return src


def test_investigation_title_field_exists_in_schema() -> None:
    props = _schema_properties("InvestigationSummary")
    src = _palette_source()
    reads = set(re.findall(r"\binv\.([A-Za-z_]\w*)", src))
    assert reads, "found no `inv.<field>` reads — the extractor is broken"
    unknown = sorted(reads - props)
    assert not unknown, (
        f"CommandPalette.tsx reads {unknown} off a GET /investigations row, but "
        f"InvestigationSummary declares {sorted(props)}. A wrong key is "
        "`undefined`, and the `??` fallback hides it behind a raw UUID."
    )


def test_watch_for_later_list_field_exists_in_schema() -> None:
    props = _schema_properties("WatchForLaterResponse")
    src = _palette_source()
    assert "data.questions" in src, (
        "CommandPalette.tsx no longer reads `data.questions` from "
        "/watch-for-later; if the key changed, check it against "
        f"WatchForLaterResponse, which declares {sorted(props)}"
    )
    assert "data.parked" not in src, (
        "`data.parked` is back. WatchForLaterResponse emits "
        f"{sorted(props)} — `parked` has never been one of them, and the "
        "`?? []` makes the failure silent."
    )
