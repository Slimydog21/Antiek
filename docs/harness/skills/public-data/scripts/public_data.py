#!/usr/bin/env python3
"""public_data - call any source in the public-data registry.

    python3 public_data.py list [domain]        # what is in the registry
    python3 public_data.py fetch <id> [path] [k=v ...]
    python3 public_data.py edgar 320193         # typed helpers below
    python3 public_data.py selftest             # probe a sample and assert the SHAPE

Import it from the kernel with the path, no install needed:

    import sys; sys.path.insert(0, "/Users/slimydog/.agents/skills/public-data/scripts")
    import public_data as pd
    pd.edgar_companyfacts(320193)["facts"]["us-gaap"].keys()
"""
from __future__ import annotations

import json
import pathlib
import sys
import time
import urllib.parse

try:
    import httpx
except ImportError:  # the kernel has httpx; a bare python3 may not
    httpx = None

HERE = pathlib.Path(__file__).resolve().parent
REGISTRY = HERE.parent / "references" / "registry.json"
CONTACT = "faisalnazer2@gmail.com"
UA = {"User-Agent": f"prime-agent research contact:{CONTACT}"}
TIMEOUT = 45


def sources(domain: str | None = None) -> list[dict]:
    reg = json.loads(REGISTRY.read_text())
    return [s for s in reg if not domain or s.get("domain") == domain]


def by_id(source_id: str) -> dict:
    for s in sources():
        if s["id"] == source_id:
            return s
    raise KeyError(f"no source {source_id!r} in the registry ({len(sources())} known)")


def get(url: str, params: dict | None = None, headers: dict | None = None, attempts: int = 3):
    """GET with the polite UA, a retry on 429/5xx, and an honest error.

    Returns (status, json_or_text). Raises RuntimeError with the server's own words on
    a hard failure, because a bare status code has cost this project time before.
    """
    if httpx is None:
        raise RuntimeError("httpx is required: run this inside the prime-agent kernel")
    h = {**UA, **(headers or {})}
    last = None
    for i in range(attempts):
        try:
            r = httpx.get(url, params=params, headers=h, timeout=TIMEOUT, follow_redirects=True)
        except Exception as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.5 * (i + 1))
            continue
        if r.status_code < 400:
            ctype = r.headers.get("content-type", "")
            return r.status_code, (r.json() if "json" in ctype else r.text)
        if r.status_code in (429, 500, 502, 503, 504):
            last = f"HTTP {r.status_code}"
            time.sleep(2 * (i + 1))
            continue
        raise RuntimeError(f"HTTP {r.status_code} from {url}: {r.text[:300]}")
    raise RuntimeError(f"gave up after {attempts} attempts on {url}: {last}")


def fetch(source_id: str, path: str = "", **params):
    """Generic fetch against a registry source."""
    s = by_id(source_id)
    url = s["base_url"].rstrip("/") + (path or ((s.get("endpoints") or [""])[0]))
    if url.startswith("/"):
        url = s["base_url"].rstrip("/") + url
    return get(url, params=params or None)


# --- typed helpers: the ones worth remembering ------------------------------------

def edgar_companyfacts(cik: int):
    """Every XBRL fact a US filer has tagged. cik is the bare integer."""
    return get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")[1]


def edgar_submissions(cik: int):
    """Filing history for a filer."""
    return get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")[1]


def clinicaltrials(query: str, page_size: int = 10, **filters):
    """Trial search. v2 only: the v1 /api/query endpoint is retired."""
    params = {"query.term": query, "pageSize": page_size, **filters}
    return get("https://clinicaltrials.gov/api/v2/studies", params=params)[1]


def openfda_label(search: str, limit: int = 5):
    """Drug labels. NOTE: no match returns HTTP 404 with error.code NOT_FOUND, which is
    an empty result, not a failure - this helper returns {} for that case."""
    try:
        return get("https://api.fda.gov/drug/label.json", params={"search": search, "limit": limit})[1]
    except RuntimeError as e:
        if "NOT_FOUND" in str(e):
            return {}
        raise


def federal_register(term: str, per_page: int = 10, agency: str | None = None):
    """Rulemaking and notices. count truncates at 10000, so narrow the query."""
    params = {"per_page": per_page, "conditions[term]": term}
    if agency:
        params["conditions[agencies][]"] = agency
    return get("https://www.federalregister.gov/api/v1/documents.json", params=params)[1]


def worldbank_indicator(indicator: str, country: str = "all", mrv: int = 1):
    """Indicator series. The response is [metadata, rows]; this returns the rows."""
    _, body = get(f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator}",
                  params={"format": "json", "mrv": mrv, "per_page": 100})
    return body[1] if isinstance(body, list) and len(body) > 1 else body


def comtrade_preview(reporter: str, partner: str, period: str, cmd_code: str, flow: str = "X"):
    """UN Comtrade no-key preview. Description fields can be null - resolve codes locally."""
    url = f"https://comtradeapi.un.org/public/v1/preview/C/A/HS"
    return get(url, params={"reporterCode": reporter, "period": period,
                            "partnerCode": partner, "cmdCode": cmd_code, "flowCode": flow})[1]


def crossref_works(query: str, rows: int = 5):
    """Literature metadata with a DOI. Polite pool: one request per second."""
    return get("https://api.crossref.org/works",
               params={"query.bibliographic": query, "rows": rows, "mailto": CONTACT})[1]


def openalex_works(query: str, per_page: int = 5):
    return get("https://api.openalex.org/works",
               params={"search": query, "per_page": per_page, "mailto": CONTACT})[1]


def openalex_abstract(inverted: dict | None) -> str:
    """OpenAlex stores abstracts as a position->word index; rebuild the text."""
    if not inverted:
        return ""
    words = {}
    for word, positions in inverted.items():
        for p in positions:
            words[p] = word
    return " ".join(words[k] for k in sorted(words))


# --- selftest: assert SHAPE, not a 200 --------------------------------------------

def selftest() -> int:
    checks = []

    def check(name, fn, predicate, want):
        try:
            v = fn()
            ok = predicate(v)
            checks.append((name, ok, want if not ok else "ok"))
        except Exception as e:
            checks.append((name, False, f"{type(e).__name__}: {str(e)[:90]}"))

    check("edgar_companyfacts(320193)", lambda: edgar_companyfacts(320193),
          lambda d: "facts" in d and "us-gaap" in d["facts"], "a 'facts'/'us-gaap' tree")
    check("edgar_submissions(320193)", lambda: edgar_submissions(320193),
          lambda d: d.get("cik") == "0000320193" and "filings" in d, "cik + filings")
    check("clinicaltrials('pembrolizumab')", lambda: clinicaltrials("pembrolizumab", 1),
          lambda d: len(d.get("studies") or []) >= 1 and d["studies"][0]["protocolSection"]["identificationModule"]["nctId"].startswith("NCT"),
          "a studies[] with an NCT id")
    check("openfda_label(metformin)", lambda: openfda_label('openfda.generic_name:"metformin"', 1),
          lambda d: bool(d.get("results")), "results[]")
    check("federal_register('entity list')", lambda: federal_register("entity list", 1),
          lambda d: isinstance(d.get("results"), list) and d.get("count") is not None, "results[] + count")
    check("worldbank MS.MIL.XPND.CD", lambda: worldbank_indicator("MS.MIL.XPND.CD", "USA", 1),
          lambda rows: isinstance(rows, list) and rows and "value" in rows[0], "rows with a value")
    check("crossref_works('graphene')", lambda: crossref_works("graphene", 1),
          lambda d: bool(d.get("message", {}).get("items")), "message.items[]")
    check("openalex_works('graphene')", lambda: openalex_works("graphene", 1),
          lambda d: bool(d.get("results")), "results[]")

    width = max(len(n) for n, _, _ in checks)
    bad = 0
    for name, ok, detail in checks:
        print(f"{'PASS' if ok else 'FAIL'}  {name:<{width}}  {detail}")
        bad += 0 if ok else 1
    print(f"\n{len(checks) - bad}/{len(checks)} sources returned the expected shape")
    return 1 if bad else 0


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "list":
        dom = argv[1] if len(argv) > 1 else None
        for s in sorted(sources(dom), key=lambda x: (x.get("domain") or "", x["id"])):
            print(f"{s['id']:32s} {s.get('auth'):9s} {s.get('domain')}")
        print(f"\n{len(sources(dom))} sources")
        return 0
    if cmd == "selftest":
        return selftest()
    if cmd == "fetch":
        kwargs = dict(kv.split("=", 1) for kv in argv[2:] if "=" in kv)
        st, body = fetch(argv[1], **kwargs)
        print(json.dumps(body, indent=2)[:4000] if not isinstance(body, str) else body[:4000])
        return 0
    if cmd == "edgar":
        print(json.dumps(edgar_companyfacts(int(argv[1])).get("entityName")))
        return 0
    print(f"unknown command {cmd!r}; try --help")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
