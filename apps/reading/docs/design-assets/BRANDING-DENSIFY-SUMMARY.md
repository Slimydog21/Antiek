# Branding densification wave — 2026-07-15/16

PR #2416 tip (at close of this note): `92dad8cbe` — axe+LP green.

## Product surfaces now UI-consuming session brand

| Surface | Asset | testid |
|---|---|---|
| Werner moods thinking/celebrate | session PNGs | via brand/Werner.tsx |
| ArcadeCabinet chrome + ice/zombies art | session PNGs | cabinet-brand-* |
| Research wait arcade | session ice/zombies | research-wait-arcade |
| Library Read door | thinking | library-werner-brand |
| Research home | thinking | research-home-werner-brand |
| Write door | celebrate | write-home-werner-brand |
| Settings Antiek-bench | thinking | antiek-bench-werner |
| Login desk | thinking | login-werner-brand |
| Speak door | thinking (Werner mood) | speak-home-werner-brand |
| Thought partner panel | desk scene webp | thought-partner-desk-art |

## Living-TV interaction

- Scenery product map + hover glance (once/hotspot) + sun focus ring
- Product click highlight owned by AppShell map; peak-left ambient owns click highlight
- Cabinet play → highlight; budget over → fail; Midnight Oil arm → deep_research_start
- Arcade: ice fishing, clam catcher, zombies + LoadingGameHost

## Imagine inventory (not product-mapped)

`docs/design-assets/session-20260715/` including clam catcher candidate.

## Pulse

`branding-doors-pulse.log` — 76 tests / 12 files green (2026-07-16).

## Honest gaps still open

- Pure Flipbook sole UI NO-GO
- CF Pages external-pending often
- Operator merge wall on #2416

## Clam Catcher session promote (2026-07-16)

- Invent `session-20260715/werner_clam_catcher_refedit_v1.jpg` →
  `poses/session/werner_clam_catcher_session_v1.png` via `cut_session_fringe.py`
- Opaque provenance retained; four corners alpha=0; cabinet card uses session PNG
- Authored webp key art remains for in-game visual kit (no Werner on sprites)

## Thought-partner desk promote (2026-07-16)

- Invent `session-20260715/werner_thought_partner_desk_refedit_v1.jpg` →
  `poses/session/werner_thought_partner_desk_session_v1.webp` (1200×800, q88)
- Full-bleed scene art (not alpha character mark) on ThoughtPartnerPanel
- CTA emits Werner `highlight` living-TV beat

## Living-TV densify wave (2026-07-16 continuation)

| Delta | Tip | Behavior |
|---|---|---|
| Living-TV invent v2 → LGH strip | `8017e9d7a` | `werner_living_tv_session_v1.webp` on wait host; highlight on opt-in |
| `piece_started` product experience | `505adcc1f` | Write create → happy craft emote |
| Home doors PRODUCT_ACTIVATE | `c67016794` | `emoteForProductDoor` before navigate |
| Library open highlight | `df7069737` | shelf open/openAtPage → curious glance |
| Speak thinking brand | `a5c8b6f44` | `speak-home-werner-brand` session mood |
| Speak create | `7462661ae` | piece_started happy craft beat |
| Research absorb | `639ae47b0` | highlight on corpus attach |
| Home igloo arcade invent | `145cb173f` | scene webp + thinking mark on Home arcade card |
| Cabinet igloo banner | `77862e281` | same invent on ArcadeCabinet chrome |
| Antiek-bench desk strip | `c86a6a9fd` | thought-partner desk webp in Settings |
| Midnight Oil living-TV | `385909143` | living-TV invent + highlight on goal add |
| Login / Research / Write / Library / Speak living-TV | `3dd97e639`–`611cf6b33` | door invent strips complete |
| ReadingCompanion glass-box | `68bd0c484` | thinking mark + living-TV invent on in-book rail |
| ResearchThis spin | `68bd0c484` | notifyResearchStarted living-TV DR beat |
| TalkToBook / VoiceNote / Biography | `61ee9273b` | open highlight, note_saved, thinking brand |
| MetaReading / PersonalSpace | `062f54e23`–`b89d4f9f9` | living-TV invent strips on reading surfaces |
| Outcomes / Notebooks / Wrestle empty | `d0894b8a3` | thinking + living-TV brand chrome on audit, notebooks, wrestle doors |
| Documents / Investigations / Settings / Home living-TV | (wave) | substrate index doors + settings + home invent strip; inv start → deep_research_start |
| Sources / Brainstorm empty | (wave) | arXiv ingest door + watch-for-later empty; ingest highlight; launch deep_research_start | |


PR tip tracks `goal/twin-autoload-session-alpha` (#2416). Operator merge wall remains.

**Honest residuals still open:** pure Flipbook sole UI NO-GO; curious v2 candidate alpha-honest but not product-mapped (reactions are CSS/SVG); invent `living_tv_imagine_v1` superseded by promoted refedit v2; CF Pages external-pending often; operator merge.

## Living-TV product-door emotes (choreography)

| Product id | Emote |
|---|---|
| research | thinking |
| read | curious |
| write | happy |
| speak | curious |
| home | happy |
| more | noted |
| (other) | hit |

Exported as `emoteForProductDoor` from `werner` barrel. Tip at densify close: `de93a97e5` axe+LP green.
