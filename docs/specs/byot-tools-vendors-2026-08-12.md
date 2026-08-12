# BYOTools — Tool/Vendor Connection Expansion Spec (2026-08-12)

**Status**: operator-brief response — "bring your own tools, not only bring
your own tokens… allow users to connect their X Developer account API, YouTube
API, and the other core internet APIs; and also key data vendors… figure out
what are the best options and offer my users the options."

**Current state (verified on main)**: `settings_tool_connections.py` +
`ToolConnectionsPanel.tsx` already support X (Twitter) and YouTube with quota
tracking (youtube_units, hard_exhausted, reset_at); `research_tool_search.py`
searches owner-connected X and YouTube (merged #3026/#3013). This spec covers
the *expansion* surface.

---

## 1. Already built (verified)

| Tool | Backend | Frontend | Quota model |
|---|---|---|---|
| X (Twitter) API v2 | settings_tool_connections.py | ToolConnectionsPanel | bearer token; usage counted |
| YouTube Data API | settings_tool_connections.py | ToolConnectionsPanel | youtube_units; hard_exhausted; reset_at |

## 2. Expansion candidates, ranked by user value for knowledge workers

### Tier 1 — ship next (high value, standard OAuth/API keys)
1. **Google Drive / Docs** (OAuth 2.0) — personal document corpus ingestion
   (the user's own assets → HTML pipeline). Highest-value BYOTools addition:
   it feeds the ingestion thesis directly.
2. **Notion** (OAuth 2.0 internal integration) — workspace ingestion.
3. **Substack / RSS** (no auth) — follow feeds into the reading pipeline
   (already partially supported via arxiv-style acquisition? add RSS reader).
4. **Reddit API** (OAuth 2.0, read-only) — research source.
5. **GitHub** (fine-grained PAT or OAuth) — code/knowledge ingestion for the
   agent's coding-tool surface (Processing sketches, analysis scripts).

### Tier 2 — data vendors (paid/subscription; operator selects)
- **Sell-side research**: Bloomberg Terminal API (enterprise, expensive),
  FactSet (enterprise), S&P Capital IQ (enterprise), or the accessible tier:
  **Seeking Alpha API** (no official public API; scraping is TOS-gray) —
  **honest verdict**: sell-side research APIs are enterprise-gated; the
  realistic v1 options are (a) user uploads PDFs they have access to (already
  supported by the ingestion pipeline — the Bartz-compliant path), (b) Tier-1
  brokers' public research portals via RSS.
- **Expert interviews**: GLG/AlphaSights have no public API for individuals —
  the Antiek-native answer is the DeepBlu interview surface (Surface D) +
  user-uploaded transcripts. No vendor integration needed.
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
2. RSS/Substack (zero-auth reader feeds)
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
