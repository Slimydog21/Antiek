"""SPR-03 M1 spike runner: measure servable-PDF hit-rate per OA source.

NOT part of the shipped acquisition path — a one-shot measurement tool. Runs a
FIXED sample of DOIs/queries against OpenAlex / Unpaywall / PMC / DOAJ and
reports, per source: fraction resolving to a fetchable PDF, and of those, the
fraction under a redistribution-granting license (per the SAME deny-by-default
resolver the prod path uses). Writes nothing to the substrate.

Run:  python -m acquisition.openaccess.spike_runner
It hits the live APIs (polite-pool mailto, conservative spacing) and prints a
markdown-ish table the operator can paste into SPIKE.md. Counted failure modes
are reported explicitly (no PDF URL / landing-page-not-PDF / license absent).
"""

from __future__ import annotations

import sys

import httpx

from . import doaj, openalex, pmc, unpaywall
from .throttle import OAThrottle

# The FIXED sample — recorded here so the numbers are reproducible. A spread
# across disciplines + OA flavors (gold/green/bronze/closed) chosen so the
# bronze-gating path is actually exercised, not just the happy CC-BY path.
SAMPLE_DOIS: tuple[str, ...] = (
    # Life sciences (PLOS / BMC — typically gold CC-BY)
    "10.1371/journal.pone.0000308",
    "10.1186/s13059-014-0550-8",
    "10.1371/journal.pbio.3000410",
    # Physics / CS (arXiv-mirrored, often green submittedVersion, license None)
    "10.48550/arxiv.1706.03762",
    "10.48550/arxiv.1810.04805",
    "10.1103/physrevlett.116.061102",
    # Chemistry / materials (mix of gold + bronze)
    "10.1021/jacs.9b09453",
    "10.1038/s41586-019-1666-5",
    # Medicine (NEJM/Lancet — often closed or bronze)
    "10.1056/nejmoa2002032",
    "10.1016/s0140-6736(20)30183-5",
    # Social science / economics (mixed OA)
    "10.1257/aer.20171532",
    # Math (often green or closed)
    "10.4007/annals.2010.171.2143",
    # Humanities OA journal (DOAJ-listed)
    "10.16995/olh.46",
    # eLife / open mega-journals (gold CC-BY)
    "10.7554/elife.00065",
    "10.1098/rsos.150449",
)

SAMPLE_QUERIES: tuple[str, ...] = (
    "graph neural networks",
    "crispr gene editing",
    "dark matter detection",
)


def run() -> int:
    throttle = OAThrottle(min_spacing_s=0.3)
    print("# OA spike — measured\n")
    print(f"sample: {len(SAMPLE_DOIS)} DOIs + {len(SAMPLE_QUERIES)} queries\n")

    # --- Unpaywall ---
    up_pdf = up_servable = up_nolic = up_nopdf = up_err = 0
    for doi in SAMPLE_DOIS:
        try:
            ft = unpaywall.resolve_doi(doi, throttle=throttle)
        except httpx.HTTPStatusError as e:
            up_err += 1
            print(f"  unpaywall {doi}: HTTP {e.response.status_code}")
            continue
        except Exception as e:
            up_err += 1
            print(f"  unpaywall {doi}: {type(e).__name__}")
            continue
        if ft.pdf_url:
            up_pdf += 1
            if ft.resolution.redistributable:
                up_servable += 1
            if ft.license_uri is None:
                up_nolic += 1
        else:
            up_nopdf += 1
    print(
        f"\nUnpaywall: pdf={up_pdf}/{len(SAMPLE_DOIS)} servable-of-pdf="
        f"{up_servable}/{up_pdf} no-pdf={up_nopdf} no-license-on-pdf={up_nolic} "
        f"err={up_err}"
    )

    # --- PMC ---
    pm_pdf = pm_servable = pm_nopdf = pm_none = 0
    for doi in SAMPLE_DOIS:
        try:
            art = pmc.resolve_by_doi(doi, throttle=throttle)
        except Exception as e:
            print(f"  pmc {doi}: {type(e).__name__}")
            continue
        if art is None:
            pm_none += 1
            continue
        if art.pdf_url:
            pm_pdf += 1
            if art.resolution.redistributable:
                pm_servable += 1
        else:
            pm_nopdf += 1
    print(
        f"PMC: pdf={pm_pdf}/{len(SAMPLE_DOIS)} servable-of-pdf={pm_servable}/{pm_pdf} "
        f"no-open-pdf={pm_nopdf} not-in-pmc={pm_none}"
    )

    # --- DOAJ (confirmation only) ---
    dj_in = dj_servable = dj_none = 0
    for doi in SAMPLE_DOIS:
        try:
            art = doaj.confirm_by_doi(doi, throttle=throttle)
        except Exception as e:
            print(f"  doaj {doi}: {type(e).__name__}")
            continue
        if art is None:
            dj_none += 1
            continue
        dj_in += 1
        if art.resolution.redistributable:
            dj_servable += 1
    print(
        f"DOAJ: in-doaj={dj_in}/{len(SAMPLE_DOIS)} servable-license={dj_servable}/{dj_in} "
        f"not-in-doaj={dj_none} (no hosted PDF — confirmation only)"
    )

    # --- OpenAlex (discovery) ---
    oa_works = oa_pdf = oa_servable = 0
    for q in SAMPLE_QUERIES:
        try:
            works = openalex.search_works(search=q, per_page=10, throttle=throttle)
        except Exception as e:
            print(f"  openalex {q!r}: {type(e).__name__}")
            continue
        for w in works:
            oa_works += 1
            if w.best_oa_pdf_url:
                oa_pdf += 1
                from .licenses import resolve_oa_license
                if resolve_oa_license(w.license_uri).redistributable:
                    oa_servable += 1
    print(
        f"OpenAlex: works={oa_works} with-pdf-url={oa_pdf} servable-of-pdf="
        f"{oa_servable}/{oa_pdf}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(run())
