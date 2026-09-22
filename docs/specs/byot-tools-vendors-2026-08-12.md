# BYOTools — Tool/Vendor Connection Expansion Spec (2026-08-12)

**Status**: operator-brief response — "bring your own tools, not only bring
your own tokens… allow users to connect their X Developer account API, YouTube
API, and the other core internet APIs; and also key data vendors… figure out
what are the best options and offer my users the options."

**Current state (re-verified on main 2026-09-22)**: the catalog in
`runtime/connectors/registry.py` (`ToolVendor` / `_VENDOR_ORDER`) ships FIVE
vendors: `youtube`, `polygon`, `fmp`, `edgar`, `x`. `settings_tool_connections.py`
+ `ToolConnectionsPanel.tsx` expose all five with quota tracking (youtube_units,
hard_exhausted, reset_at); `research_tool_search.py` searches owner-connected X
and YouTube (merged #3026/#3013). Polygon, FMP and EDGAR are connectable but
have no consuming surface yet (SPR-04 task 3). This spec covers the
*expansion* surface. Sell-side research and expert-interview vendors are
NOT OBTAINABLE; see
`docs/decisions/sell-side-and-expert-interview-not-obtainable-2026-09-20.md`.

---

## 1. Already built (verified on main 2026-09-22)

| Tool | Vendor id | Connector | Frontend | Quota model | Consumed by |
|---|---|---|---|---|---|
| YouTube Data API | `youtube` | `runtime/connectors/youtube.py` (api_key_query) | ToolConnectionsPanel | youtube_units; hard_exhausted; reset_at | `research_tool_search.py` |
| Polygon.io | `polygon` | `acquisition/polygon/client.py` `PolygonConnector` | ToolConnectionsPanel | vendor rate spec | nothing yet (connect-only) |
| Financial Modeling Prep | `fmp` | `acquisition/fmp/client.py` `FmpConnector` | ToolConnectionsPanel | vendor rate spec | nothing yet (connect-only) |
| SEC EDGAR | `edgar` | `acquisition/edgar/client.py` `EdgarConnector` (contact-keyed, not api-keyed) | ToolConnectionsPanel | SEC fair-access rate | nothing yet (connect-only) |
| X (Twitter) API v2 | `x` | `runtime/connectors/x_twitter.py` (bearer_token) | ToolConnectionsPanel | 25 req / 900 s governor; pay-per-use credits since 2026-06 | `research_tool_search.py` |

Also on main, server-side and NOT user-connectable: `acquisition/rss` and
`acquisition/substack` are operator-run acquisition lanes. They exist; they are
simply not BYOT connections. Do not list them as unbuilt.

## 2. Expansion candidates, ranked by user value for knowledge workers

### Tier 1 — ship next (high value, standard OAuth/API keys)
1. **Google Drive / Docs** (OAuth 2.0) — personal document corpus ingestion
   (the user's own assets → HTML pipeline). Highest-value BYOTools addition:
   it feeds the ingestion thesis directly.
2. **Notion** (OAuth 2.0 internal integration) — workspace ingestion.
3. **Substack / RSS** (no auth) — `acquisition/rss` and `acquisition/substack`
   already exist as server-side lanes. The open item is exposing them as a
   per-user connection (a user's own feed list), not building a reader.
4. **Reddit API** (OAuth 2.0, read-only) — research source.
5. **GitHub** (fine-grained PAT or OAuth) — code/knowledge ingestion for the
   agent's coding-tool surface (Processing sketches, analysis scripts).

### Tier 2 — data vendors (paid/subscription; operator selects)
- **Sell-side research**: NOT OBTAINABLE (closed 2026-09-20, see
  `docs/decisions/sell-side-and-expert-interview-not-obtainable-2026-09-20.md`).
  Bloomberg 24k-27k USD/seat/yr with the API gated behind a terminal, FactSet
  contract-only with no self-serve tier, S&P Capital IQ one-year minimum from
  ~25k USD/team; none permit redistribution to Antiek's users. The v1 answer is
  the user uploading research they hold lawful access to, at `personal_reading`
  with the user as fetch agent (§9.0).
- **Expert interviews**: NOT OBTAINABLE (same record). AlphaSense acquired
  Tegus for 930M USD in 2024; Tegus-AlphaSense, Third Bridge and Guidepoint
  hold the API/MCP surfaces under institutional subscriptions; GLG and
  AlphaSights have no individual API. The Antiek-native answer is the existing
  `acquisition/interview` lane plus user-uploaded transcripts at
  `personal_reading`. No vendor integration.
- **Survey data**: Qualtrics API (OAuth, survey responses → substrate),
  Typeform API (OAuth) — both real APIs, moderate value, good for
  interview/research data capture.
- **Alternative data / market data**: FRED (St. Louis Fed, free API key),
  Alpha Vantage (free tier), EIA/World Bank APIs (free) — cheap, high-value
  for quantitative research; these are the "quantitative data" lane the
  operator wants (DuckDB + Python analysis).

### Tier 3 — intentionally deferred/rejected
- TikTok/Instagram APIs (master-spec §8.4 deferral — scraping-only access).
- LinkedIn (API locked to approved partners).
- Enterprise paywalled research portals as *automated* sources (Bartz
  procurement liability — user uploads own-access docs instead, §9.0).

## 3. Architecture for expansion

- The `ToolConnection` model is vendor-agnostic already (credential_kind:
  api_key | oauth | contact; quota: youtube_units | generic note). Extend with
  `oauth` flows reusing `runtime/byok/` OAuth machinery (Grok/OpenAI/Anthropic
  flows from docs/specs/byot-oauth-2026-08-12.md) for Google/Notion/Reddit.
- New vendors = registry entries + optional vendor-specific adapter in
  `substrate/tool_connections/` (or acquisition/) + a row in the
  ToolConnectionsPanel vendor list + capability tag surfaced in
  research_tool_search.
- Every connection is owner-scoped (owner_user_id), encrypted at rest
  (SecretBox), revocable, and quota-honest (hard_exhausted + reset_at chips).

## 4. Recommended v1 addition order (operator decision)

1. Google Drive/Docs OAuth (feeds ingestion; highest leverage)
2. RSS/Substack as per-user connections (the server-side lanes already exist)
3. FRED + Alpha Vantage (free quantitative APIs → DuckDB tables)
4. GitHub PAT (code/Processing-sketch ingestion)
5. Reddit read-only OAuth
6. Qualtrics/Typeform (survey → interview data)

## 5. Data-vendor honesty note

Sell-side research and expert-interview access are enterprise-gated; there is
no credible self-serve API for individuals. The Antiek-native substitutes
(user-uploaded PDFs with legitimate access; DeepBlu interviews; survey forms)
are both more compliant (Bartz §9.0: the user is the fetch agent, never the
platform) and more aligned with the product thesis. Present these as the
offering rather than promising vendor integrations that cannot be built.
