# SPR-03 M1 — OA servable-PDF hit-rate spike

**Ran LIVE** in this environment on 2026-05-29 against the real OpenAlex /
Unpaywall / Europe PMC / DOAJ APIs (network was reachable). Numbers below are
measured, not estimated. Reproduce with:

```
/Users/slimydog/Desktop/Antiek/.venv/bin/python -m acquisition.openaccess.spike_runner
```

The runner + the fixed sample live in
`acquisition/openaccess/spike_runner.py` so the measurement is reproducible.
It writes NOTHING to the substrate.

## What is measured

For each source, two ratios:

1. **PDF-resolve rate** — fraction of the sample that resolves to a *fetchable
   full-text PDF URL* (not just a landing page, not a closed record).
2. **Servable-license rate** — of those with a PDF, the fraction whose
   *declared license actually grants redistribution* per the deny-by-default
   resolver (`acquisition.openaccess.licenses.resolve_oa_license`). This is the
   load-bearing number: "free to read" is NOT counted as servable.

## Fixed sample (recorded for reproducibility)

15 DOIs spanning disciplines + OA flavors (chosen so bronze/closed paths are
exercised, not just the happy CC-BY path) + 3 discovery queries for OpenAlex.

DOIs:
```
10.1371/journal.pone.0000308      (PLOS ONE, life sci, gold)
10.1186/s13059-014-0550-8         (Genome Biology, gold)
10.1371/journal.pbio.3000410      (PLOS Biology, gold)
10.48550/arxiv.1706.03762         (Attention Is All You Need, arXiv-green)
10.48550/arxiv.1810.04805         (BERT, arXiv-green)
10.1103/physrevlett.116.061102    (LIGO GW detection, APS)
10.1021/jacs.9b09453              (JACS, chemistry)
10.1038/s41586-019-1666-5         (Nature, mixed)
10.1056/nejmoa2002032             (NEJM, medicine)
10.1016/s0140-6736(20)30183-5     (Lancet, medicine)
10.1257/aer.20171532              (Am. Economic Review)
10.4007/annals.2010.171.2143      (Annals of Math)
10.16995/olh.46                   (Open Library of Humanities, DOAJ)
10.7554/elife.00065               (eLife, gold)
10.1098/rsos.150449               (Royal Society Open Science, gold)
```

Queries (OpenAlex, `open_access.is_oa:true`, 10/page): `graph neural networks`,
`crispr gene editing`, `dark matter detection`.

## Measured results

| Source    | PDF-resolve            | Servable-of-PDF | Notes |
|-----------|------------------------|-----------------|-------|
| Unpaywall | 9/15 (60%)             | 6/9 (67%)       | 4 DOIs 404'd (not in Unpaywall); 2 had a PDF but no license on it (green, gates) |
| PMC       | 6/15 (40%)             | 5/6 (83%)       | 7 DOIs not in PMC (PMC is biomed-skewed); 2 in PMC but no open PDF row |
| DOAJ      | 0 (no hosted PDFs)     | 4/4 license-servable | confirmation-only; 11/15 not in DOAJ; license needs the journal follow-up (see below) |
| OpenAlex  | 30/30 works had a URL  | 8/30 (27%)      | discovery surfaces a best-OA URL for nearly every OA work, but most are green/no-license -> gated |

Failure modes counted (the spike enumerates each, per the honesty constraint):
- **DOI with no OA location / not in source** — Unpaywall 404 (4), PMC
  not-in-pmc (7), DOAJ not-in-doaj (11). The single largest factor: coverage,
  not licensing. No source covers all disciplines.
- **OA URL that is a landing page, not a PDF** — the real guard is at
  INGEST: `read_pdf` (pypdf, `acquisition/books/reader.py`) rejects a
  non-PDF body (an HTML landing page has no valid PDF header) and the item
  is counted `failed` by the CLI; `ingest_oa_item` separately rejects a
  zero-byte fetch. (This spike MEASURES declared-PDF-URL presence — it
  distinguishes Unpaywall's `url_for_pdf` from its landing `url` — but does
  NOT download bytes, so it does not itself exercise the pypdf guard; the
  guard is the ingest-path mechanism, verified by the ingest tests, not by
  this sample.)
- **License field absent** — the dominant servable-gap. Unpaywall green
  copies and OpenAlex green works routinely have `license: null`; these gate
  deny-by-default (correctly — a green repository copy is not a redistribution
  grant). This is WHY servable-of-PDF is far below PDF-resolve everywhere.

## Key finding (load-bearing, fixed mid-spike)

The DOAJ **article**-search response does NOT carry the license — the journal
block on an article record has only ISSN/title/publisher. The license lives on
the **journal** record. The first spike pass therefore measured DOAJ
servable-license at **0/4** (every article gated for lack of a *visible*
license — safe but useless). I added a journal-by-ISSN follow-up
(`doaj.confirm_by_doi` → `journal_license_by_issn`); the re-run measured
**4/4** servable. Without that follow-up DOAJ is dead weight; with it, DOAJ is
a clean journal-level CC confirmation layer (no PDF bytes — it must pair with a
PDF resolver).

## API ergonomics / rate limits

- **OpenAlex** — polite pool via `mailto`; documented 10 req/s. JSON, clean
  `best_oa_location.license` + `oa_status`. Best discovery layer. No auth.
- **Unpaywall** — requires `email` query param. One DOI per request; 404 on
  unknown DOI (handled as a permanent per-item miss). Best single-DOI → best-OA
  resolver. 100k req/day soft cap (fine for non-prod batches).
- **Europe PMC** — no auth; `resultType=core` carries `license` +
  `fullTextUrlList`. The list mixes availability tiers; we take only the
  `Open access` + `pdf` row. Biomed-skewed coverage.
- **DOAJ** — no auth; two-hop (article → journal by ISSN) for the license.
  Slower; confirmation-only.

No source exhibited arXiv's IP-ban-on-burst behavior in this run; the
`OAThrottle` (polite-pool mailto + conservative spacing + retry-with-backoff,
NO ban-sentinel machinery) is the right size.

## Ship / defer recommendation

**SHIP all four**, in this role split:

- **Unpaywall** — primary single-DOI full-text resolver. Highest servable-PDF
  yield per request, cleanest license signal. Ship.
- **PMC / Europe PMC** — ship as the biomed full-text resolver + as a
  second-opinion PDF source when Unpaywall 404s a DOI that PMC covers.
- **OpenAlex** — ship as the discovery layer (topic/author → candidate DOIs),
  NOT as a full-text source on its own. Its 27% servable-of-PDF reflects that
  it surfaces green/no-license copies; route the servable DOIs to
  Unpaywall/PMC for the actual fetch.
- **DOAJ** — ship as a journal-level CC confirmation layer ONLY (no hosted
  PDFs). The CLI rejects a real `--source doaj` run for exactly this reason;
  it is `--dry-run`/confirmation use or pairs with another resolver.

The servable-of-PDF rates (27%–83%) are healthy *given the invariant*: the
low OpenAlex number is the deny-by-default gate working as designed on green
copies, not a defect. The binding caveat for a *production* ship (SPR-06, not
here) is coverage, not licensing — no single source covers all disciplines, so
prod ingestion should query OpenAlex for discovery and fan candidates across
Unpaywall + PMC. **No further spike is needed before SPR-06; this is a SHIP.**
