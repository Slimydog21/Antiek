# ANT-AHT — Antiek HTML Transport

**Status:** exec-6 complete (2026-06-24). SPR-AHT-01…06 + `artifact_router` wired in `create_app`. SPR-AHT-07 is complete as the book-reader snapshot extension. SPR-AHT-08 is the ready follow-on for the reviewed source/twin apply boundary. P-18 `canonical_verify.sh html-transport`.

Open `index.html` for sprint roster. Regenerate pages: `./.venv/bin/python docs/htmlspec/antiek-html-transport/_generate.py` (when present).

**Gates:** `./scripts/canonical_verify.sh html-transport`

**Landscape:** `./.venv/bin/python docs/html/_build_landscape.py` → `docs/html/html-landscape.html`
