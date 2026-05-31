# Substack RSS connector (`acquisition/substack/`)

A thin RSS connector that ingests the operator's **subscribed** Substack
publications' full-text posts into the personal-reading lane. Modeled
byte-for-byte on `acquisition/podcasts/` (client + adapter split,
`connect_write` single-writer, `on_conflict="ignore"` idempotency,
`chunk_markdown` + nodes). It adds two Substack-specific concerns the podcast
connector does not have: a full-vs-truncated (paywall) heuristic, and an
operator-curated per-publication subscription list that tolerates
custom-domain publications.

## What it does

- `fetch_feed(feed_url)` GETs `<publication>/feed`, parses each `<item>` with
  `feedparser` (the `[rss]` extra), and returns a `Publication` of `Post`s.
  Full body comes from `content:encoded` (feedparser's
  `entry.content[0].value`), falling back to `entry.summary`.
- `ingest_publication_feed(feed_url, investigation_id=...)` fetches then writes
  each post as a `documents` row (`document_type="newsletter_post"`) plus
  `chunks` and a graph `node`, funnelled through `connect_write` (purpose
  `"acquisition/substack"`).
- Identity is the post **GUID** (`entry.id`/`guid`, falling back to
  `entry.link`) → `doc-sub-<sha256(guid)[:16]>`; re-ingesting is idempotent
  via `on_conflict="ignore"`. Cross-feed idempotency holds in a multi-feed
  `ingest_subscriptions` run because identity is the GUID, not the feed.
- `ingest_subscriptions(path, investigation_id=...)` is the operator driver:
  it loads a curated manifest and ingests each publication, aggregating
  per-publication (ingested / skipped / truncated) counts.

## Why a Substack post lands `personal_reading` (and not `gated`)

`newsletter_post` is a **third-party** `document_type` — the author retains
copyright. The operator subscribed, so reading it is lawful for the operator;
we must **never serve it publicly, attribute ad revenue to it, or train on
it**. The personal-reading lane (`content_class=personal_reading`, added by
SPR-01) is exactly this state: full body readable on the owner path, excluded
from `SERVABLE_CONTENT_CLASSES`, included in `NON_ATTRIBUTABLE_CONTENT_CLASSES`,
absent from `PUBLIC_GRAPH_CONTENT_CLASSES`, and out of every training/RL
export. It is **not** `gated`: gated means "private search only, body hidden";
personal-reading means "owner reads the full body, public never sees it."

### M2 decision — option A (guard-reliant), not option B (explicit-pass)

We do **not** pass `content_class` from this adapter. `insert_document`'s
deny-by-default guard (`substrate/graph/ops.py:_resolve_content_class`)
re-maps any `document_type` in `constants.THIRD_PARTY_DOCUMENT_TYPES`
(which includes `newsletter_post`) to `personal_reading` when no class is
supplied.

- **Why A wins:** it matches the actual shipped SPR-02 sibling convention —
  `acquisition/urls/adapter.py` (lines 134-135) and `acquisition/podcasts`
  both omit `content_class` and rely on the guard. The policy then lives in
  **one** place; a future maintainer of this connector cannot pass the wrong
  class because this connector passes none. A leaked-servable post is the
  §9.0 catastrophe (Hachette / Bartz territory), so a single policy location
  is the most defensible defense.
- **Steelman of B (explicit-pass), and who absorbs the cost if A is wrong:**
  `content_class="personal_reading"` at the call site is self-documenting and
  the corpus audit explicitly whitelists it (`WEB_FAMILY_ALLOWED_CLASSES`).
  If option A were silently wrong — e.g. someone removed `newsletter_post`
  from `THIRD_PARTY_DOCUMENT_TYPES` — every Substack post would inherit the
  servable `user_owned` default and leak publicly. That risk is mitigated two
  ways: (1) a test in `tests/test_acquisition_substack.py` asserts ingest
  yields `personal_reading`, and (2) SPR-10's audit capstone asserts zero
  `newsletter_post` on a servable class. **What would reverse the choice:** if
  the guard's third-party set ever stops being the single source of truth, or
  if a connector needs a *non-default* class with a positive basis, switch to
  explicit-pass (the audit already permits it).

## Truncation (paywall) detection — flag, never fabricate

Many `/feed` entries carry the full post; paid posts arrive **truncated**.
`detect_truncation` returns `(truncated, reason)`:

- **Primary signal** — a case-insensitive substring match against
  `TRUNCATION_MARKERS` (publisher-inserted footers like *"this post is for
  paid subscribers"*, *"subscribe to keep reading"*, *"read the full post"*).
  These strings are transcribed from observed paywalled-feed footers; the feed
  itself stops at the marker.
- **Secondary, weaker signal** — body shorter than `MIN_FULL_BODY_CHARS`
  (280) **while** the entry advertised more (`summary` longer than the
  rendered body). `280` is conservative: a genuine essay is thousands of
  chars; a sub-280 body with a longer summary is a teaser. This only *adds*
  the `short_body` reason; it never overrides a marker hit.

We store **exactly** the markdown rendered from the feed body. We never
fabricate, pad, summarize, or interpolate a missing remainder, and we never
re-fetch the public web page to backfill a paid body (out of scope — a
distinct acquisition-ToS question). The verdict round-trips in document
metadata as `"truncated": true|false` and `"truncation_reason"`.

## Operator-curated subscription manifest

`subscriptions.example.json` documents the schema. The **real** manifest is
gitignored (`subscriptions.json` / `subscriptions.local.json`) or
operator-supplied — never committed (mirrors
`acquisition/opt_in/example_manifest.json`). `resolve_feed_url` resolves an
entry deterministically: explicit `feed_url` wins; else `base_url + "/feed"`
(works for `*.substack.com` and custom domains). `load_subscriptions` raises
`SubscriptionManifestError` (a `ValueError`, never a bare `KeyError`) naming
the offending entry.

## What it deliberately does NOT do (out of scope)

- **No unlocking of paid/paywalled posts.** Truncated → store the partial,
  flag it. No scraping the locked HTML, no credentialed fetch of the remainder.
- **No serving or attribution.** `newsletter_post` is non-servable,
  non-attributable by construction (SPR-01). No serve projection, no opt-in
  promotion path here.
- **No author → `ip_holder_id` resolution.** Left `ip_holder_id=None`;
  `personal_reading` accrues zero attribution regardless. **Open question**
  deferred to the operator / SPR-10.
- **No crawler / feed-discovery spider.** The subscription list is
  operator-curated; we do not auto-discover or follow links.
- **No re-implementing the lane gates.** SPR-01 owns
  `SERVABLE_CONTENT_CLASSES` / `NON_ATTRIBUTABLE_CONTENT_CLASSES` / the
  `insert_document` guard. This connector asserts them in tests; it does not
  edit them.

## Constants (defensibility — every magic number has a source)

- `DEFAULT_SUBSTACK_SOURCE_TIER = 4` (`substrate/constants.py`) — general-web
  tier, same as `acquisition/urls`' default; a subscribed newsletter is
  general-web-trust, not a curated corpus source. Overridable per
  `ingest_publication_feed(..., source_tier=...)` and per manifest entry.
- `MIN_FULL_BODY_CHARS = 280` (`client.py`) — conservative short-body floor;
  see "Truncation" above.
- `TRUNCATION_MARKERS` (`client.py`) — transcribed from observed Substack
  paywalled-feed footers.
