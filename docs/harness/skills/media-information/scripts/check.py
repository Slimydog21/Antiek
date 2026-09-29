#!/usr/bin/env python3
"""Probe every media provider and report live/dead with the exact reason.

Usage: python3 check.py [--json]
Exit 0 when at least the no-credential providers are live; 1 when one of them is broken.
"""
import json, subprocess, sys, time
import httpx

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"}
PLAIN = {"User-Agent": "prime-agent research contact:faisalnazer2@gmail.com"}

def http(name, url, headers, note="", attempts=3):
    """Try `attempts` times. Reddit in particular 403s intermittently."""
    last = None
    statuses = []
    for i in range(attempts):
        try:
            r = httpx.get(url, headers=headers, timeout=20, follow_redirects=True)
            statuses.append(r.status_code)
            if r.status_code < 400:
                extra = f" (attempt {i+1}/{attempts})" if i else ""
                return {"provider": name, "live": True, "status": r.status_code,
                        "detail": (note or f"{len(r.content)} bytes") + extra}
            last = r
            time.sleep(1.5 * (i + 1))
        except Exception as e:
            statuses.append(f"{type(e).__name__}")
            time.sleep(1.5 * (i + 1))
    flaky = any(s == 200 for s in statuses) or (len(statuses) > 1 and len(set(map(str, statuses))) > 1)
    return {"provider": name, "live": False, "status": statuses[-1] if statuses else None,
            "detail": (note or "") + (" | FLAKY: mixed statuses " + str(statuses) if flaky else
                                      f" | all {attempts} attempts failed: {statuses}")}

def shell(name, cmd):
    try:
        p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=90)
        ok = p.returncode == 0 and p.stdout.strip() != ""
        return {"provider": name, "live": ok, "status": p.returncode,
                "detail": (p.stdout.strip().splitlines() or [""])[0][:90]}
    except Exception as e:
        return {"provider": name, "live": False, "status": None, "detail": f"{type(e).__name__}: {e}"}

def main():
    results = [
        shell("youtube (yt-dlp)", "yt-dlp --version"),
        # probe the WORKLOAD, not the key listing: `x env` exits 0 even with empty tokens
        shell("x cli (real call)", "x me"),
        http("reddit (browser UA)", "https://www.reddit.com/r/MachineLearning/top.json?limit=1", UA),
        http("hacker news", "https://hn.algolia.com/api/v1/search?query=test&hitsPerPage=1", PLAIN),
        http("mastodon.social", "https://mastodon.social/api/v1/timelines/tag/ai?limit=1", PLAIN),
        http("podcasts (itunes)", "https://itunes.apple.com/search?term=agents&media=podcast&limit=1", PLAIN),
        http("rss", "https://news.ycombinator.com/rss", PLAIN),
        http("wayback", "https://archive.org/wayback/available?url=example.com", PLAIN),
        http("bluesky (public)", "https://public.api.bsky.app/xrpc/app.bsky.feed.searchPosts?q=test&limit=1", UA,
             "403 from this network is expected"),
    ]
    if "--json" in sys.argv:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            mark = "live" if r["live"] else "DEAD"
            print(f"{mark:5s} {r['provider']:24s} {str(r['status'] or '-'):>5s}  {r['detail']}")
    core = ["youtube (yt-dlp)", "hacker news", "mastodon.social", "podcasts (itunes)", "rss", "wayback"]
    broken = [r for r in results if r["provider"] in core and not r["live"]]
    return 1 if broken else 0

if __name__ == "__main__":
    sys.exit(main())
