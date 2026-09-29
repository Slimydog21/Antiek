---
name: media-information
description: >-
    Pull information out of media platforms into citable form - YouTube video metadata and
    transcripts, X posts and timelines, Reddit threads, Hacker News, Mastodon, podcast episode
    metadata, RSS feeds, and the Wayback Machine for links that have rotted or posts that were
    deleted. Use when a task needs what a video said, what someone posted, what a community
    discussed, what a podcast covered, or what a page used to say. Also use to check which media
    credentials are live before promising a result. Not for general web search, which the
    websearch-failover skill covers, and not for the curated public datasets in the public-data
    skill.
---

# media-information

One place for "what was said on a platform", with the credential state of each half stated plainly.

Run the check first, because two of these are credential-blocked on this machine:

```bash
python3 ~/.agents/skills/media-information/scripts/check.py
```

It prints one line per provider with live/dead plus the exact reason. Do not promise a source the
check marks dead.

## YouTube - works with no credential

`gws` cannot do YouTube: its service list is drive, sheets, gmail, calendar, admin-reports, docs,
slides, tasks, people, chat, classroom, forms, keep, meet, events, modelarmor, workflow, script, and
`youtube:v3` is rejected even in the unlisted-API form. **Use `yt-dlp`, which is installed and needs
no key.**

```bash
# metadata, one line, no download
yt-dlp --skip-download --no-warnings \
  --print '%(id)s|%(title)s|%(channel)s|%(upload_date)s|%(duration)s|%(view_count)s' <url>

# what the video actually says (auto captions, vtt), then read the file
yt-dlp --skip-download --write-auto-subs --sub-langs 'en.*' --sub-format vtt -o '/tmp/%(id)s.%(ext)s' <url>

# the newest N videos from a channel, without touching the API
yt-dlp --skip-download --flat-playlist --print '%(id)s %(title)s' --playlist-end 20 <channel-url>
```

Verified 2026-09-29 on `aircAruvnKk`: metadata returned
`aircAruvnKk|But what is a neural network?...|3Blue1Brown|1120|24549470`, and `--list-subs`
reported automatic captions in dozens of languages.

If a YouTube Data API key is ever added, the equivalent call is
`GET https://www.googleapis.com/youtube/v3/videos?part=snippet,statistics&id=<id>&key=<key>`, and
search is `search?part=snippet&q=...`. The key route is only worth it for quota-heavy search; for
reading a video or a channel, yt-dlp is faster and needs nothing.

## X - works

The `x` CLI reads (`me`, `user <handle>`, `get <id>`, `search <query>`, `timeline`) and writes
(`tweet`, guarded). It self-sources `~/.config/x-api/x.env`.

**State on 2026-09-29:** authenticated as `@FaisalNazer1` with OAuth 2.0 user-context tokens
(access + refresh). Verified live: `x me`, `x user`, and `x search` all return real data. The
app-only bearer is still absent, so this is user-context only.

Two quirks worth knowing: OAuth 2.0 access tokens are short-lived, and the CLI refreshes them
automatically (force it with `x refresh`). And `x timeline [username]` takes a **positional**
username, so passing `--max` there is misread as a username - omit args for your own timeline.

## Reddit - flaky from this machine, treat as unreliable

Reddit 403s a default client. A browser UA sometimes fixes it and sometimes does not: measured
2026-09-29, one call to the same URL returned 200 (3.3 KB) and a later run returned **403 three
times in a row** (189 KB block page). So: send a browser UA, retry with backoff, and if it keeps
403ing, say Reddit is unavailable rather than reporting an empty result as "no discussion".

```bash
curl -s -A 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36' \
  'https://www.reddit.com/r/MachineLearning/top.json?limit=25'
```

When it answers, `old.reddit.com` serves the same JSON with more fields.

## Hacker News - no key

```bash
curl -s 'https://hn.algolia.com/api/v1/search?query=<terms>&hitsPerPage=20'
curl -s 'https://hn.algolia.com/api/v1/search_by_date?tags=story&numericFilters=points>100'
```

Algolia indexes both stories and comments, so this covers "what did the engineering community say".

## Mastodon - no key, per instance

```bash
curl -s 'https://mastodon.social/api/v1/timelines/tag/<tag>?limit=40'
curl -s 'https://mastodon.social/api/v2/search?q=<terms>&resolve=true'
```

Public timelines and search work unauthenticated per instance; pick the instance where the
conversation lives rather than assuming mastodon.social.

## Podcasts - no key

```bash
curl -s 'https://itunes.apple.com/search?term=<terms>&media=podcast&limit=20'
```

Returns show metadata plus the feed URL, which then reads like any RSS feed. There is no public
transcript API; transcribe an episode locally if the words matter.

## RSS and Atom - no key, the highest-value habit

Any feed is a stable, dated, citable source, and many publishers (including Substack and most
research blogs) expose one. Fetch with the browser UA and parse the XML.

## Wayback Machine - for link rot and deleted posts

```bash
curl -s 'https://archive.org/wayback/available?url=<url>'          # nearest snapshot
curl -s 'http://web.archive.org/cdx/search/cdx?url=<url>&output=json&limit=5'   # snapshot history
```

Use this whenever a source you cited 404s or a post was deleted after you quoted it. A snapshot URL
plus its timestamp is a citable artifact.

## Not available from this network

**Bluesky's public AppView** (`public.api.bsky.app/xrpc/app.bsky.feed.searchPosts`) returns **403**
from this machine, with both a plain and a browser User-Agent, while the same endpoint class works
for others - treat it as network-blocked here until proven otherwise, and prefer an authenticated
session if it matters.

## The provenance rule

For every item, record **the platform, the canonical URL, the author, the timestamp, and the date
you retrieved it**. Media posts are editable and deletable; a quote without a retrieval date is not
evidence. Where a post may be deleted, take a Wayback snapshot at the moment you cite it.
