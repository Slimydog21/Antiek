# Live hydrate wiring (arxiv / substack)

**Date:** 2026-07-09  
**Status:** residual (bk)  
**Default:** offline identity-only HTML assets (no network)

## Why

Hydrate must remain safe for tests and local agents. Live publication fetches
are **opt-in** so CI never depends on arXiv rate limits or Substack ToS edges.

## Env flags

| Env | Effect |
|---|---|
| `ANTIEK_HYDRATE_LIVE_ARXIV=1` | Wire `acquisition.arxiv.client.fetch_by_id` into engagement hydrate |
| `ANTIEK_HYDRATE_LIVE_SUBSTACK=1` | Enable Substack path **only if** a `fetch_post` factory is also provided |

Truthy values: `1`, `true`, `yes`, `on` (case-insensitive).

## API injectors (process-local)

On `interfaces.research.api.engagement_routes`:

* `hydrate_arxiv_fetch_by_id`
* `hydrate_substack_fetch_post`
* `hydrate_fetch_publication` (generic override)

Configure via:

```python
from interfaces.research.api import engagement_routes as eng
from substrate.engagement_spine import configure_engagement_hydrate_injectors

configure_engagement_hydrate_injectors(eng)  # reads env
```

## Honesty rules

1. No silent network when flags are unset.
2. Substack never auto-scrapes public pages without an explicit factory.
3. Human view of hydrated assets is HTML-first (never PDF-required).
4. Paywalled Substack bodies may be truncated; adapters may set `truncated=True`.

## Operator recipe

```bash
export ANTIEK_HYDRATE_LIVE_ARXIV=1
# start research API process; call POST /engagement/hydrate-ref
```

For Substack, also inject a ToS-safe feed/post fetcher in the app factory.
