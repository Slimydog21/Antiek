# Antiek X Capture (browser extension)

Sprint 14. A Chrome / Chromium / Arc / Edge MV3 extension that captures
the X (Twitter) thread on the current tab and POSTs it to the Antiek
substrate.

## Why

Direct API ingest is impractical:

- X's public API does not return reliable thread-reconstructions on the
  free tier.
- The paid tier costs more per month than the substrate spends on LLM
  inference, and most of what you'd ingest is one tweet per request.
- The DOM on x.com already contains the canonical text the operator
  saw. Capturing the DOM is exactly the right level of abstraction.

## Install (operator)

1. Visit `chrome://extensions/`
2. Toggle "Developer mode" on
3. Click "Load unpacked"
4. Pick `~/Desktop/Antiek/apps/x-extension/`

The icons are deliberately omitted from this scaffold (no operator
asset yet). The browser will warn about missing icons but the
extension functions without them. To silence the warnings, drop
16/48/128-px PNGs into `apps/x-extension/icons/`.

## Use

1. Open a tweet in the browser (URL contains `/status/`)
2. Click the Antiek toolbar icon
3. (First time only) Set the API endpoint (`https://api.antiek.ai` or
   `http://localhost:8000` for local dev) and an investigation id
4. Click "Capture this thread"

The popup posts the captured payload to `POST /sources/twitter`. The
substrate writes a `social_thread` document with one chunk per tweet.

## DOM selectors

The content script uses these X-specific selectors:

- `article[data-testid="tweet"]` — each tweet
- `a[href*="/status/"][role="link"]` — extract the tweet id
- `div[data-testid="User-Name"] a[href^="/"]` — extract the author handle
- `div[data-testid="tweetText"]` — extract the tweet text
- `time[datetime]` — extract the post timestamp
- `svg[aria-label="Verified account"]` — verified-account check
- `img[alt="Image"]` — media URLs

When X redesigns the DOM (this happens), the selectors need updating.

## Data shape

The payload posted to `/sources/twitter`:

```json
{
  "thread_url": "https://x.com/<handle>/status/<id>",
  "root_tweet_id": "<id>",
  "author_handle": "<handle>",
  "investigation_id": "__operator__",
  "tweets": [
    {
      "tweet_id": "...",
      "text": "...",
      "author_handle": "...",
      "author_verified": false,
      "posted_at": "2026-05-18T14:30:00Z",
      "reply_to": null,
      "quote_of": null,
      "media_urls": []
    }
  ]
}
```

The substrate parser is `acquisition.twitter.ingest_thread_payload`.
