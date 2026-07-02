## Sprint SPR-03 (ANTIEK-HPRJ) — Widget Library — Handoff

### Env Card

| Field | Value |
|-------|-------|
| Date (UTC) | 2026-06-30 |
| Repo root (`pwd`) | `/Users/slimydog/Desktop/Antiek` |
| Branch | `html-projection/land-antiek` |
| Commit SHA | `10bbedaacd7f77e5b1217a5024744013d69d024a` |
| Python | `/Users/slimydog/Desktop/Antiek/.venv/bin/python` (`Python 3.12.13`) |
| LLM contacted this session | `no` |
| Network required for gates | `no` |

### Not proved

| Row | Hermetic proof | Not proved |
|-----|----------------|------------|
| Widget rendering | Empty, typical, degenerate fixtures for seven widgets | Browser screenshot approval on multiple viewports |
| Safety | Zero-script gate, hostile-input fixtures, cite URL scheme guard | Full browser CSP behavior |
| Visual drift | 21 frozen HTML goldens + gallery drift gate | Human design sign-off beyond committed gallery |
| Renderer reachability | `antiek_widget` block renders through `render()` and island round-trips | Signed `.antiek` `projection.html` shell packaging |

### Status

`done` — SPR-03 widget library, frozen goldens, gallery artifact, safety gates, palette gates, and renderer widget seam are landed and verified.

### Files touched

- `services/html_projection/tokens.py` — Lemon-UI widget palette, geometry constants, CSS derivation, and widget registry seam.
- `services/html_projection/widgets/` — seven pure-function widgets: `stat_chip`, `bar_chart`, `sparkline`, `donut`, `timeline`, `dep_graph`, and `cite_block`; canonical fixtures; deterministic `gallery.html` generator and committed gallery artifact.
- `services/html_projection/partials/widget.py` — renderer partial for `antiek_widget`, importing the widget package to register concrete widget renderers.
- `services/html_projection/contract.py` — `antiek_widget` / `widget` block contract maps to the widget partial.
- `services/html_projection/renderer.py` — includes the widget partial in the renderer partial map.
- `services/html_projection/tests/` — token isolation/derivation tests, widget behavior tests, frozen widget goldens, palette lint, gallery drift gate, and renderer widget-block tests.

### Milestones (checkboxes)

- [x] M1: Widget tokens and registry seam — widget palette derives from atomic `LEMON_*` constants; importing `tokens` does not import renderer/partials/widgets.
- [x] M2: Seven widgets — stat chip, bar chart, sparkline, donut, timeline, dependency graph, and citation block render deterministic script-free HTML/SVG over empty, typical, and degenerate fixtures.
- [x] M3: Frozen visual artifacts — 21 widget goldens plus `widgets/gallery.html` are committed and drift-gated.
- [x] M4: Safety and palette gates — hostile input is escaped or dropped, dangerous cite URLs are not linked, non-finite plotting values cannot leak `nan`/`inf`, and widget colors trace to the token palette.
- [x] M5: Renderer reachability — `antiek_widget` renders through `render()`, unknown/kindless widgets use the deterministic unsupported-widget placeholder, and the data island round-trips.

### Gate results

| gate | command | exit |
|------|---------|------|
| SPR-03 widget focused bundle | `./.venv/bin/python -m pytest services/html_projection/tests/test_tokens_isolation.py services/html_projection/tests/test_tokens_css_derives.py services/html_projection/tests/test_widgets_render.py services/html_projection/tests/test_widgets_golden.py services/html_projection/tests/test_palette_lint.py services/html_projection/tests/test_gallery.py services/html_projection/tests/test_widget_block.py -q` | 0 (`137 passed in 0.18s`) |

### Decisions made mid-flight

- Kept widgets as pure server-rendered HTML/SVG strings registered through `tokens.render_widget`; no client JavaScript, no browser runtime dependency, and no external assets.
- Froze widget output with generated-but-reviewed golden files instead of screenshot-only approval, so CI can catch byte drift deterministically.
- Kept chart layout deliberately simple and bounded: widget outputs must survive degenerate inputs without becoming unbounded layout engines.

### Assumptions surfaced

- The gallery is a review artifact, not the runtime contract; the runtime contract is the widget render function plus zero-script gate.
- `cite_block` may emit safe clickable `http`, `https`, or `mailto` references, but never script/data/vbscript URLs.
- Missing or malformed widget data should produce a visible deterministic fallback or omit the unsafe part, not raise or silently emit active markup.

### Steelman rejected alternative

Client-side charting library. Steelman: richer charts, less custom SVG code, familiar interaction patterns. Why it lost: HPRJ artifacts are autonomously ingested and must remain script-free and self-contained; a chart runtime would violate the core projection invariant.

### Open questions

- SPR-04 can now decide how the signed `projection.html` shell packages the renderer output into `.antiek`.
- Future widgets can be added through the registry, but they must inherit the same script-free, token-derived, golden-gated contract.

### Scope Map

**Investigation ID:** ANTIEK-HPRJ-SPR-03

**Next sprint:** SPR-04 signed projection shell.

### Out-of-scope temptations encountered

- Wanted to add interactive chart affordances; resisted because SPR-03 is static projection and the script-free invariant is load-bearing.
- Wanted to replace the existing renderer chrome palette; resisted because widgets own their Lemon-UI palette through `tokens.py` and should not rewrite SPR-02 chrome.
