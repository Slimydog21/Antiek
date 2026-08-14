# Link Monster — spec

**Status:** implemented (PR #3071, 2026-08-13) — backend + frontend + tests live; v2 proposals below are the backlog · **Owner:** operator + prime-agent · **Surface:** reading app + substrate + acquisition

> *"Antiek is the home of information. Link Monster is the front door: paste anything, it gets eaten, and whatever was inside becomes part of the graph."*

---

## 1. Vision

Link Monster is a single, dramatic ingestion surface for **everything the web links to**. The operator pastes a URL — X post, YouTube video, Instagram reels, TikTok, Substack essay, arXiv paper, a random blog — and the Monster **digests** it: it pulls every artifact it can (title, author, text, transcript, images, video metadata, timestamps, entities), then **stews it into the Antiek graph** (documents, chunks, nodes, edges, rights) so the knowledge compounds with everything else in the substrate.

The UX is not a form. It is an **industrial incinerator with a personality**: a giant blue Cookie-Monster-like creature whose mouth is a steel furnace grate. You feed it a link; it chews; fire ignites; sparks and digest-cards stream out into the graph constellation behind it. The whole environment is **Gravity Falls Weirdmageddon**: red apocalyptic sky, floating islands, blacklight palette, runes, sigils, an all-seeing eye, and geometry that is one step from tearing.

### 1.1 Design principles

1. **One door for all links.** Platform-specific plumbing lives *under* the hood; the operator never thinks about extractors.
2. **Digest everything, honestly.** Each artifact is labeled with its provenance: where it came from (oEmbed? OpenGraph? DOM? platform client?), when, and at what confidence. Nothing is silently invented.
3. **The graph is the point.** A link that only gets a title is a half-eaten snack; a link that contributes chunks, nodes, and edges is a full meal. The Monster tracks the difference and shows it.
4. **Graceful absence everywhere.** No API key? No transcript? Site blocked? The Monster burps and tells you exactly what it got and what it couldn't — never a 500, never a hang.
5. **Theatrical but fast.** The visualization is the emotional core, but it must never block the ingestion. Animation plays *while* the pipeline runs; the result lands when the pipeline lands.

---

## 2. Style bible — WEIRDMAGEDDON INCINERATOR

> *A giant, vaguely lovable blue monster made of furnace parts lives in a broken-apart sky. His mouth is a steel grate with fire behind it; his ears are smoke stacks; his head is a chimney. When you hand him a link, he eats it with theatrical relish, fire flares, and the digested light of the page — text, images, voices — pours out of his back into a constellation of glowing nodes that connects to everything the graph already knows. The sky is red, the geometry is a little wrong, the runes are watching.*

**Palette** (p5 + CSS tokens; final hexes per the Krea art-direction pass in `~/Antiek/link-monster-art/ART-DIRECTION.md`):
- Apocalypse sky: deep red/black gradient (`#1a0508` → `#4d0f14` → `#8f1d21`)
- Monster fur: electric blue (`#2f6bff` family), belly `#7fb2ff`
- Furnace fire: orange→gold→white core (`#ff9a2e` `#ffd166` `#fff7e0`)
- Blacklight accents: electric cyan (`#4dfff3`), magenta (`#ff2fd6`), toxic green (`#b6ff2f`)
- Graph constellation: cyan/white nodes on deep violet (`#0b0b2a`)
- Runes/sigils: gold `#e8c547` with glow

**Typography:** display — *Rubik Glitch* or *Rubik Mono One* for the title; body — *Space Grotesk* (industrial-techno); mono labels — *IBM Plex Mono*.

**Motifs (canvas):** furnace-grate teeth, chimney smoke puffs (noise-driven), floating island silhouettes (layered parallax), the all-seeing eye in a triangle, rune glyphs (drawn with bezier strokes, occasional blink), constellation nodes (bloom + connecting lines that appear as digest lands), ember/spark particles (additive blending), geometric "wrong" tessellation in the sky (slowly rotating hex/tri grids), paper-link cards with URL text that crumple when chewed.

**Motion (the devour sequence, 5 beats):**
1. **Paste** — the link card materializes at the paste bar (glitch-in).
2. **Fly** — the card arcs into the Monster's mouth (ease-in bezier; the Monster's eyes track it).
3. **Chew** — the furnace grate slams; the card crumples into sparks; fire flares; smoke puffs from the chimney.
4. **Ignite** — a shockwave ring; digest embers stream out of the Monster's back.
5. **Absorb** — embers fly into the constellation; new nodes bloom and connect; the feed card lands with the digest summary.

---

## 3. Terminology

| Term | Meaning |
|---|---|
| **Link** | Any URL the operator pastes. |
| **Digest** | The full structured extraction packet for one link: platform, canonical URL, title, author, published_at, text, transcript, images, video, entities, provenance per field, timing. |
| **Meal** | One completed ingest (digest + graph writes). |
| **Snack** | An ingest that only got metadata (no body) — still recorded, honestly labeled. |
| **Leftovers** | A failed ingest (blocked, paywalled, invalid, SSRF-blocked) — recorded with the failure reason. |
| **Monster Menu** | The feed of past meals/snacks/leftovers. |
| **The Grotto** | Saved/starred meals (a collection surface). |

---

## 4. Ingestion architecture

```
paste URL
   │
   ▼
[1] validate + classify          platforms.py   (youtube | x | instagram | tiktok | substack | generic)
   │
   ▼
[2] SSRF guard                   fetchguard.py   (resolve DNS, block private/link-local/metadata, http(s) only, redirect cap)
   │
   ▼
[3] extraction ladder            oembed.py        (platform oEmbed → OpenGraph → DOM → platform client)
   │
   ▼
[4] deep extraction              digest.py        (YouTube transcript via acquisition.youtube; generic text via acquisition.urls; media manifests)
   │
   ▼
[5] graph stew                   store.py         (documents + chunks + nodes + edges + rights + digest metadata + typed event)
   │
   ▼
[6] response                     digest packet → frontend (feed card + constellation update)
```

### 4.1 Platform classification (`platforms.py`)

URL → platform via host rules:

| Platform | Host patterns | Notes |
|---|---|---|
| `youtube` | youtube.com, youtu.be, m.youtube.com, music.youtube.com | incl. shorts |
| `x` | x.com, twitter.com | posts/threads |
| `instagram` | instagram.com, instagr.am | reels/posts |
| `tiktok` | tiktok.com, vm.tiktok.com, vt.tiktok.com | |
| `substack` | substack.com + any custom-domain with substack meta | via existing `acquisition/substack` |
| `generic` | everything else | via existing `acquisition/urls` |

### 4.2 Extraction ladder (`oembed.py`)

For each platform, try in order; stop at the first that yields a *usable* packet (non-empty title or text):

1. **Platform oEmbed** (X `publish.twitter.com/oembed`, TikTok `tiktok.com/oembed`, Instagram `instagram.com/oembed` (public, may 401 without token → falls through), Substack native, YouTube oEmbed `youtube.com/oembed`).
2. **OpenGraph/Twitter-Card meta** from a HEAD/GET of the page (`og:title`, `og:image`, `og:video`, `og:description`, `twitter:player`, `article:author`, etc.).
3. **DOM extraction** (generic readability path via `acquisition/urls.extract`).
4. **Platform client** where one exists: YouTube transcript via `acquisition/youtube/client.py` (timed segments); Substack via `acquisition/substack`.

Every field carries `provenance: "oembed" | "og" | "dom" | "platform" | "none"` and `fetched_at`.

### 4.3 SSRF guard (`fetchguard.py`) — NEW, mandatory

The existing `acquisition/urls` client has **no SSRF protection**; Link Monster's whole premise (paste any URL) makes this a hard requirement, not a nice-to-have:

- Schemes: `http`/`https` only.
- DNS resolve → reject loopback (127.0.0.0/8, ::1), link-local (169.254.0.0/16, fe80::/10), private (RFC1918 10/8, 172.16/12, 192.168/16, fc00::/7), CGNAT (100.64/10), and cloud metadata (169.254.169.254 explicitly, also via redirect).
- Re-resolve **every redirect hop** (redirect to `http://127.0.0.1:8001/health` must be blocked — this is a live attack against this very repo's API).
- Redirect cap: 5.
- Timeout: 10 s connect/read; total budget 30 s.
- All rejections → typed `Leftover` with reason `ssrf_blocked:<target>` — recorded, never raised as 500.

### 4.4 Media extraction (the "as much information as possible" mandate)

Per platform, collect whatever exists into the digest's `artifacts`:

- **images**: `og:image` + oEmbed thumbnails (X post images from oEmbed `thumbnail_url`; Instagram/TikTok `thumbnail_url`); store URLs + dimensions when known (no byte-download in v1 — hotlink with provenance; byte-caching is a v2 Grotto feature).
- **video**: YouTube `video_id`, duration, channel, upload date, thumbnail, watch URL (full reuse of `acquisition/youtube` client); TikTok/IG `video` meta when oEmbed/OG provides.
- **transcript**: YouTube timed segments via existing client (timestamp-anchored chunks — the existing `_group_transcript_into_chunks` already produces `Timestamp: HH:MM:SS - HH:MM:SS` sections); TikTok/IG: none in v1 (honest `transcript: null`).
- **text**: X thread text via oEmbed `html` strip or OG description (full-thread capture remains the x-extension's job — the adapter contract already exists at `acquisition/twitter`); Substack/generic full markdown via existing adapters.

### 4.5 Graph stew (`store.py`)

Reuses the existing single-writer substrate path exactly (flock via `runtime/db_lock.connect_write`, `substrate/graph/ops`):

1. **Document row** — `insert_document` with `document_type` from the platform (`video_transcript` for YouTube with transcript; `social_thread` for X; `newsletter_post` for Substack; `web_article` for generic; `web_link` for metadata-only snacks), `source_tier=4`, `content_class` left to the existing deny-by-default guard (third-party → `personal_reading`; never servable), `metadata` = the full digest packet (JSON).
2. **Chunks** — text/transcript chunked via the existing chunker; each chunk `insert_chunk` (YouTube timestamp sections preserved).
3. **Nodes/edges** — author (person node), publisher/platform (organization node), title-derived entity/insight nodes at *low* confidence, edges `authored_by`, `published_by`, `mentions` with `extraction_confidence` and `source_tier=4`, `graph_scope="depth"`. (Light-touch v1: no LLM extraction; the loop-one/parameter-extractor machinery remains the deep-extraction layer. The Monster's job is acquisition + honest labeling.)
4. **Rights** — `register_source_document(source_kind=SourceKind.third_party)` → `personal_reading` (deny-by-default, per §9.0).
5. **Typed event** — new `link.monster.digested` (schema v33, payload: url, final_url, platform, document_id, artifacts counts, text_chars, transcript_chars, image_count, video_count, node_count, edge_count, duration_ms, outcome `meal|snack|leftover`).
6. **Dedup** — doc id from canonical final URL (existing `url_doc_id` convention); re-ingest → `on_conflict="ignore"` → returns existing doc id + `already_digested: true`.

---

## 5. API surface (`interfaces/research/api/link_monster_routes.py`)

Mounted via `register_link_monster_routes(app)` in `create_app`.

| Method/Path | Purpose |
|---|---|
| `POST /links/monster` `{url, investigation_id?}` | Digest one link. Returns the digest packet (or `already_digested`). Sync; total budget ≤ 45 s; graceful typed errors. |
| `GET /links/monster/feed?limit=20&before=` | Monster Menu — recent meals/snacks/leftovers (documents with digest metadata), newest first. |
| `GET /links/monster/{document_id}` | Full digest + chunk list + graph neighbors (nodes/edges touching the document). |
| `GET /links/monster/stats` | Counts: meals, snacks, leftovers, total chunks/nodes/edges contributed, per-platform breakdown, last-digest time. |
| `POST /links/monster/{document_id}/star` + `DELETE .../star` | Grotto (saved meals; metadata flag). |
| `GET /links/monster/grotto` | Starred meals. |

Error contract (mirrors krea routes' honest-503 idiom): every failure is a typed `{"ok": false, "reason": <machine-name>, "message": ...}` with the right status (400 invalid/unsupported URL, 422 SSRF-blocked, 429 rate-limited, 502 upstream unreachable, 503 no-provider) — never a bare 500, never a hang. No keys, no secrets, no full URL echo in error bodies beyond the normalized host.

---

## 6. Frontend (`apps/reading/src/modes/LinkMonster/`)

- **Route:** `/link-monster` (registered in `App.tsx` under `RequireAuth`).
- **Page anatomy** (single screen, no scrolling by default):
  1. **The Furnace Stage** — full-bleed p5.js canvas: Weirdmageddon sky (parallax islands + eye + runes), the Monster center-stage, constellation graph behind.
  2. **The Paste Bar** — styled as the Monster's mouth: input + "FEED IT" button; validation (URL shape) inline; pasting glitches the card in.
  3. **The Monster Menu** — right rail: recent meals as digest cards (platform icon, title, artifact badges: 🖼 🎬 📝 🎙, word counts, time); click → detail panel.
  4. **The Detail Panel** — overlay: full digest fields with provenance chips, artifact thumbnails, transcript/chunk list, graph neighbors, star button.
- **Tech:** p5.js (`p5` + `@types/p5` added to `apps/reading`), React 18 wrapper (`useRef` canvas + `new p5(sketch, el)`), zustand store for feed state, existing `apiFetch` client.
- **State machine:** `idle → validating → feeding → chewing → digesting → absorbed | leftover`. The canvas receives each phase and plays the matching beat; the API result arrives at `absorbed` and the feed updates.
- **A11y:** canvas is decorative-by-default (the digest data is always in the DOM feed); reduced-motion query disables the chew animation and shows a static scene.
- **Tests:** vitest for the page (render, phases, feed render, leftover state) + the API client (mocked fetch); no p5 in jsdom (mock the sketch module).

---

## 7. Creative feature proposals (v2+ menu, operator picks)

1. **Monster Growth** — the Monster levels up: persistent stats (meals eaten, chunks stewed, nodes connected) animate size/fire intensity; a "belly" gauge shows graph contribution.
2. **Moods of the Apocalypse** — day/night/seasonal palettes (Red Sky, Blacklight Night, Acid Rain) driven by the existing scene-mood machinery; each mood reshades the canvas only.
3. **The Grotto** — saved meals with notes; export a markdown bibliography of a grotto ("the monster's reading list").
4. **Leftovers Board** — failed/blocked links as a visible, dismissible graveyard with per-item reason (SSRF-blocked, paywalled, 404, no-text) — turns silent failures into an honest ops surface.
5. **Link Roulette** — one button, one random past meal re-shown with its graph neighbors ("the Monster remembers").
6. **Graph Projection** — click any meal → constellation view centered on its document node, neighbors animated in (uses existing graph query surface).
7. **Bulk Buffet** — paste N links at once (textarea or pasted chunk of text with URLs) → queue; Monster chews them one by one; feed fills.
8. **Wayback Snacks** — optional: on 404, try the Wayback Machine (opt-in env `ANTIEK_MONSTER_WAYBACK=1`).
9. **Ingredient Labels** — per-field provenance chips everywhere (oEmbed/OG/DOM/platform) — already in v1; this proposal is to make it a *feature*: "what the Monster actually tasted".
10. **The All-Seeing Eye** — a subtle stats glyph in the sky that "watches" (parallax toward cursor) and opens the stats panel on click.

---

## 8. Testing & verification

- **Backend unit** (`tests/test_link_monster_*.py`, httpx `MockTransport`, temp DB via the existing adapter-test pattern):
  - classification table (all platforms + edge hosts)
  - SSRF guard: 127.0.0.1, 169.254.169.254, RFC1918, redirect-to-private (the live `http://127.0.0.1:8001/health` attack), non-http schemes, >5 redirects
  - extraction ladder fallback (oEmbed missing → OG → DOM)
  - store path: document/chunks/nodes/edges rows, rights class `personal_reading`, dedup on re-ingest, digest metadata round-trip
  - routes: feed, detail, stats, star/grotto, all error statuses
- **Frontend** (`apps/reading` vitest): page render, phase transitions, feed render, leftover card, api client mocks.
- **Verification run:** `uv run pytest tests/test_link_monster_*.py -q`; `npm run typecheck` + `npm run build` in `apps/reading`; manual dev-server smoke against a live URL (network permitting).

---

## 9. Rollout

1. Feature branch from `origin/main` (worktree, per deploy convention), PR with CI (test-integrity + enforce-declared-bar must pass).
2. Schema: v33 event + codegen `types.ts` in the same commit (staleness check enforces).
3. Deploy via the main-tracking worktree path; **the canonical `~/Antiek/platform` branch must NOT be the deploy source** (known hazard, see FORENSIC-REPORT-2026-08-12-pass4.md §7.4).
4. Live smoke: paste one YouTube URL + one generic article URL against prod after deploy; verify digest + feed + graph neighbors; confirm `/health` still green and prod-parity still passes.

---

## 10. Explicit non-goals (v1)

- No byte-level media download/storage (image caching, video transcoding) — URLs + provenance only.
- No LLM entity extraction in the ingest path (loop-one owns that; the Monster is honest acquisition).
- No full X-thread DOM capture server-side (that is the x-extension's contract — the Monster uses oEmbed/OG; a thread link becomes a snack with a pointer).
- No rate-limit bypassing, no paywall circumvention, no login-gated fetching.
- No changes to the DuckDB single-writer invariant, no new runtimes, no new external credentials.
