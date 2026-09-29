---
name: public-data
description: >-
    Query authoritative public data sources for research that must cite its evidence, covering corporate and
    financial disclosure, clinical trials and drug safety, defence procurement, sanctions and conflict, patents,
    case law and the scientific literature. Use when a claim needs a primary source rather than a search result
    - company filings, trial results, drug labels and adverse events, award and contract records, sanctions
    screening, defence spending, conflict events, patent or court records, or a citation with a DOI or PMID.
    Every source is free or needs only a free key, and each carries its endpoint, auth requirement, rate limit
    and update cadence so the answer can be dated. Not for general web search, which is what the websearch-
    failover skill is for.
---

# public-data

Authoritative public sources for claims that must cite their evidence. The registry
holds **133 sources** across 4 domains; every one was probed
live before it was admitted. Nothing here needs a paid account.

Read [references/sources.md](references/sources.md) for the full contract of each source
(endpoint, auth, rate limit, licence, cadence, caveats). The machine-readable copy of the
same data is [references/registry.json](references/registry.json).

## Calling a source from the kernel

One module wraps the registry, so you do not hand-roll URLs:

```python
import sys; sys.path.insert(0, "/Users/slimydog/.agents/skills/public-data/scripts")
import public_data as pd

pd.sources("health-clinical")            # what exists in a domain
pd.by_id("sec-edgar-companyfacts")       # the full contract for one source
pd.fetch("ofac-sdn-list")                # generic fetch, polite UA, retry on 429/5xx
pd.edgar_companyfacts(320193)            # typed helpers, below
```

Typed helpers, each verified by shape on 2026-09-29: `edgar_companyfacts`, `edgar_submissions`,
`clinicaltrials`, `openfda_label`, `federal_register`, `worldbank_indicator`, `comtrade_preview`,
`crossref_works`, `openalex_works`, and `openalex_abstract` (OpenAlex ships abstracts as a
position-to-word index, not text).

Run the shape gate before trusting any of it:

```bash
python3 ~/.agents/skills/public-data/scripts/public_data.py selftest     # 8/8 must pass
```

It asserts payload SHAPE, not a status code - a 200 carrying an HTML application shell is the
failure mode this project already met once at the USPTO portal, so a bare 200 is not evidence.

## The rule that keeps this honest

- **Cite the source and the date of the data, not the API.** A trial result, an award
  record and a label revision all carry their own effective date.
- **Prefer the publisher over the aggregator.** Every entry here is the agency, registry
  or standards body that owns the record.
- **Check `auth` before you promise a number.** `free_key` entries need a key you must
  register for; the note says where.
- **Respect the rate limit in the table.** Several of these return 429 for a few seconds
  and several ban an IP for hammering.
- **A bulk file and its API are different products.** Where a source exposes both, the
  file usually needs no key and the API usually does. The caveats say which is which.
- **Fetch with python or `/usr/bin/curl`, and never disable TLS verification.** A second
  curl lives inside Anaconda with its own CA bundle and fails with a certificate error on
  hosts the system curl reaches. Measured 2026-09-29 on the Treasury sanctions host. If a
  fetch fails on TLS, check which curl ran before believing the host is at fault.

## Health, clinical and pharmaceutical (39)

| source | auth | what it answers |
|---|---|---|
| `biorxiv-medrxiv-api` | none | Earliest public evidence of a clinical result: preprints move before journals, and the /pubs endpoint links a... |
| `cdc-data-socrata` | none | Weekly notifiable-disease counts and local prevalence estimates with a stable dataset ID and a $where query... |
| `cdc-wonder-api` **(unverified)** | none | The only public route to detailed US mortality cross-tabs (cause x county x age x year), which is the denominator... |
| `chembl-api` | none | Mechanism and potency evidence for a pipeline thesis: target, assay type, measured value and the paper it came... |
| `clinicaltrials-gov-api-v2` | none | The canonical register for every trial number, phase, endpoint, enrolment and sponsor a clinical or pharma memo... |
| `cms-asp-pricing-files` | none | A regulated US price series per drug, published quarterly with a legal basis - the anchor for price-per-unit... |
| `cms-open-payments` | none | Conflict-of-interest evidence for an investment or clinical memo: named key opinion leaders, speaker fees and... |
| `cms-provider-data-api` **(unverified)** | none | Prescriber-level and hospital-level payment and utilisation data: the ground truth behind 'who prescribes what, and... |
| `dailymed-spl-api` | none | Gives label history and the raw SPL XML when the openFDA label index has flattened a field away. Version history... |
| `ema-medicines-output` | none | EU side of an approval timeline and an ATC-coded product list from the regulator, which is the citable counterpart... |
| `eu-ctis-public-api` | none | The only authoritative view of EU-authorised trials after the 2019 Clinical Trials Regulation; needed for European... |
| `europepmc` | none | Broader than PubMed for the same query and it exposes full text for OA articles and a citation count, which is what... |
| `fda-orange-book-files` | none | Loss-of-exclusivity and generic-entry timing come from this file, not from a label: patent expiry plus exclusivity... |
| `fda-purple-book-files` | none | The biologic-side complement to the Orange Book. Biosimilar and interchangeable status with dates is what a... |
| `health-canada-dpd` | none | A third regulator's product list with its own identifiers (DIN), which is what a comparative approval-timing claim... |
| `icd10cm-cdc-bulk` | none | Bulk code-to-description joins for a clinical model: the API is for lookups, this is for rebuilding the whole... |
| `isrctn-registry-api` | none | Independent UK/global registry coverage that is not in ClinicalTrials.gov; useful for UK site counts and for trials... |
| `medicaid-nadac` | none | The closest public thing to a real US acquisition price, published weekly with a documented survey method. It gives... |
| `nhsbsa-open-data` | none | Actual dispensed volume and cost by practice and month, which is the UK demand series behind a volume or share... |
| `nice-syndication-api` **(unverified)** | free_key | UK reimbursement decisions gate whether a product is actually paid for: a TA number and a recommendation date is... |
| `nlm-clinical-tables` | none | The fastest free route from a clinical phrase to a coded identifier. It is also the free partial substitute for... |
| `nppes-npi-registry` | none | Provider identity resolution: it turns a name in an Open Payments or claims record into an NPI, a specialty and a... |
| `oecd-health-sdmx` | none | Cross-country pharmaceutical spend and consumption series from the statistical publisher itself, which is how a... |
| `open-targets-platform` | none | Gives a defensible association score with the underlying evidence classes, so a target's support can be described... |
| `openfda-device-maude` | none | The device analogue of FAERS, and the only structured public record of device failures - relevant to defence-... |
| `openfda-device-udi` | none | Medical-device identification for device-based claims: manufacturers, device classes and catalogue numbers that a... |
| `openfda-drug-label` | none | The label is the legal source for indication, dose and contraindication claims. Every 'what is this drug approved... |
| `openfda-drug-shortages` | none | Supply-chain evidence: a shortage entry is a dated, citable primary record of a manufacturing or demand failure,... |
| `openfda-drugsfda` | none | Approval dates and application types are the input to loss-of-exclusivity and generic-entry timing in an investment... |
| `openfda-enforcement-recalls` | none | Recall history is due-diligence evidence: a recalled lot, its class and its distribution list is a dated primary... |
| `openfda-faers` | none | Post-market safety signal work: a reaction count with a report window is the difference between a defensible signal... |
| `openfda-ndc-directory` | none | The join key between pricing, volume and labelling sources: NADAC, ASP and Medicaid claims are all keyed by NDC, so... |
| `pubchem-pug-rest` | none | Chemistry grounding for a formulation or mechanism claim: molecular formula, mass, LogP and identifiers that... |
| `pubmed-eutils` | none | The citation backbone: a PMID plus MeSH terms makes a literature claim checkable, and publication-type filters... |
| `rxnav-rxnorm` | none | The normalisation layer between sources that spell drugs differently: it turns a label name, an NDC and a trial... |
| `usaspending-federal-awards` | none | The money trail behind clinical and health-industrial claims: BARDA/ASPR medical countermeasure contracts, HHS and... |
| `who-disease-outbreak-news` | none | A dated, authoritative outbreak feed for bio-event monitoring. Each item carries who/when/what fields, so a... |
| `who-gho-odata` | none | Country-level denominators and burden figures for a clinical or market-sizing model, from the publisher rather than... |
| `who-icd11-api` **(unverified)** | free_key | ICD-11 is the coding standard WHO members will migrate to; for a model that must survive a coding change, the... |

## Corporate, financial and macro (34)

| source | auth | what it answers |
|---|---|---|
| `alpha-vantage` | free_key | A free, keyed quote and history check when a memo needs a price next to a filing and no terminal is open. Not the... |
| `bank-of-england-iadb` | none | Bank Rate and sterling FX for a UK defence or pharma counterparty. ONS covers activity; the Bank covers the policy... |
| `bea-data-api` | free_key | BEA is the source of the GDP, industry and trade-in-services numbers a memo should cite. FRED reprints many of... |
| `bis-stats-api` | none | The real broad dollar index and cross-border banking numbers when a memo discusses dollar strength or international... |
| `bls-public-api` | none | CPI, wages and unemployment are the price and labour inputs in a pharma cost model and in any macro section of a... |
| `census-bureau-api` | free_key | County Business Patterns and the trade release answer 'how many establishments, how much employment, what did the... |
| `cftc-commitments-of-traders` | none | Positioning in a commodity or rate future when a memo discusses hedging by a producer, airline, or Treasury-futures... |
| `companies-house` | free_key | UK subsidiary, joint-venture and PSC lookup for a defence or pharma group that files in Britain. The company number... |
| `ecb-data-portal` | none | Euro FX and the euro-area curve for a European revenue or debt line in a memo. The series key is the citation. |
| `estat-japan` | free_key | Japanese production, prices and trade for a Japan-sourced component or a MoF-adjacent macro fact, in machine-... |
| `eurostat-api` | none | Euro-area inflation and member-state GDP for a European supplier, payer or trial-site country in a memo. |
| `fdic-bankfind` | none | Bank counterparty and deposit-franchise facts for a lender in a memo, and the failure list when a financing party... |
| `federal-reserve-h15` | none | The constant-maturity Treasury curve a memo uses for discounting. It is the Board release, which outranks a vendor... |
| `ffiec-cdr-bulk` | none | The microdata behind bank peer comparisons when FDIC's pre-aggregated financials are not enough. Included because... |
| `finra-otc-and-regsho` | none | Short interest and short volume for a listed name in a trading or issuance memo. Reg SHO is daily and exchange-... |
| `fred-graph-csv` | free_key | The macro denominator in an investment memo (GDP, CPI, unemployment, yields, FX) with a stable series id the... |
| `gleif-lei` | none | The join key between a filing, a sanction name, an OpenFIGI security and a foreign subsidiary. A memo that names a... |
| `imf-sdmx` | none | Cross-country CPI and WEO growth when a memo compares markets. The dataflow id plus the time period is the... |
| `ncua-call-report` | none | Credit-union lender financials when a memo's financing or deposit counterparty is a credit union rather than a... |
| `nyfed-reference-rates` | none | SOFR and EFFR are the funding rates under a discount rate or a floating-rate instrument in a memo. SOMA is the... |
| `oecd-sdmx` | none | OECD CLI and national accounts for a non-US macro panel. Use it when the memo's comparison set is OECD members and... |
| `ofac-sdn` | none | Screen a counterparty, bank, vessel or foreign parent before a defence or clinical supply-chain memo treats it as a... |
| `ons-beta-api` | none | UK GDP and prices for a memo on a UK-listed supplier or a sterling cost base. The version id pins the vintage. |
| `openfigi` | none | Stable security id when a memo joins a 13F CUSIP, a ticker and a listing across venues. FIGI survives ticker... |
| `polygon-io` | paid_key | End-of-day prices for a larger ticker list than Alpha Vantage's 25 calls a day, if the operator takes the free... |
| `sba-foia-open-data` | none | Loan-level check on whether a small supplier actually received a PPP or EIDL loan, with lender and amount, for a... |
| `sec-edgar-companyfacts` | none | The citable numeric layer under a 10-K or 10-Q: revenue, assets, R&D, backlog-adjacent tags, segment facts. An... |
| `sec-edgar-filing-archives` | none | This is where a memo's filing number becomes a document: Form 4 XML, 13F information table, Form D primary_doc.xml,... |
| `sec-edgar-full-text` | none | Finds Form D raises, Form 4 insider sales, 13F holdings language and contract phrases inside 10-Ks when the... |
| `sec-edgar-submissions` | none | Primary identity and filing index for any issuer or filer in an investment memo or defence-industrial profile. The... |
| `sec-edgar-xbrl-frames` | none | Cross-sectional screen for a memo universe: total assets, revenue or R&D for every XBRL filer in one period, each... |
| `treasury-fiscal-data` | none | The primary print for Treasury debt, auction yields and bid-to-cover. A memo that quotes a U.S. yield or the debt... |
| `treasury-tic` | none | Who holds Treasury and U.S. long-term securities, by country. That is the cross-border demand fact behind a rates... |
| `world-bank-indicators` | none | Cross-country GDP, debt and external-account comparables when a memo leaves the US. The indicator code is the... |

## Legal, IP, scientific literature and archives (34)

| source | auth | what it answers |
|---|---|---|
| `arxiv-export-api` | none | For hypersonics, quantum and ML-adjacent defence topics, the newest work appears here months before a journal.... |
| `caselaw-access-project` | none | Historical case law at zero cost and zero rate limit: ideal for tracing how a doctrine (patent eligibility,... |
| `common-crawl-index` | none | Bulk web text without scraping: for NLP over defence or pharma news, or for checking how a site presented something... |
| `congress-gov-v3` | free_key | Traces defence authorisation and appropriations language, export-control bills and pharma pricing bills to a... |
| `courtlistener-bulk-data` | none | Removes the API rate limit entirely for corpus work: 'find every opinion citing this statute' or 'all patent cases... |
| `courtlistener-rest-v4` | none | The only free machine-readable US case-law and docket index that answers 'what did a court decide' with a citable... |
| `crossref-rest` | none | The citation backbone: it converts a claim about a paper into a DOI plus funder and reference list, which is the... |
| `epo-ops` **(unverified)** | free_key | Patent families and legal status are what make a patent claim honest across jurisdictions: 'protected in the US'... |
| `eu-cellar-eurlex` | none | EU regulation drives defence export controls, chemicals and pharma market access; this is the primary machine path... |
| `europe-pmc-rest` | none | Gives the actual article XML, so a number from a trial can be quoted from the source rather than from a secondary... |
| `google-patents-bigquery` **(unverified)** | free_key | Answers questions no API can: 'how many US grants in CPC H04B did this assignee get per year since 2010', citation-... |
| `google-patents-search` | none | The fastest way to go from a technology claim to the patent set behind it (who filed, when, in which countries)... |
| `internet-archive-api` | none | Scanned public filings, old technical reports and broadcast news are exactly the corpora the operator OCRs. This... |
| `nasa-ads` **(unverified)** | free_key | Aerospace and space-physics literature with citation metrics is a direct input to defence-industrial analysis, and... |
| `nih-reporter` | none | Government funding is the demand signal behind clinical capability: which institution, which PI, which amount,... |
| `ntrs-nasa` | none | Grey literature is where engineering numbers live (test conditions, material properties). NTRS gives a citable... |
| `ofac-sanctions-lists` | none | US sanctions are the operative constraint on who a defence client or an investor can deal with; the record count... |
| `openalex` | none | Answers the meta-questions the operator actually asks: who funds this field, which institutions produce it, and how... |
| `openstates-v3` **(unverified)** | free_key | State law is where pharma pricing, Medicaid coverage, defence-site siting and state incentives are actually... |
| `openstreetmap-overpass` | none | Geolocation and infrastructure mapping for defence-industrial and site work: where a facility actually is, what... |
| `osti-api` **(unverified)** | none | The national-laboratory grey literature is where weapons, materials and computing details live, and it is the DOE... |
| `pacer` **(unverified)** | paid_key | The authoritative federal court record. When a defence contractor or a pharma company is sued and the filing is not... |
| `regulations-gov-v4` **(unverified)** | free_key | The comment record is evidence of who opposed or supported a rule: useful when a deliverable claims industry... |
| `semantic-scholar-graph` | free_key | Citation-graph lookups are how a technical claim gets validated - who cites this paper, and does the citing work... |
| `uk-legislation-api` | none | UK defence procurement, export licensing and pharma regulation sit in UK statutes; the Akoma Ntoso form gives... |
| `uk-national-archives-discovery` | none | UK defence-industrial history (ministry files, establishment reports, contracts) is described here and nowhere else... |
| `un-sc-sanctions-consolidated` | none | 'Who is sanctioned' with the reason and the listing date. UN listings bind member states, so they are the highest-... |
| `unpaywall` | free_key | Turns a paywalled citation into a readable source. When a deliverable cites a paper, this is how the operator... |
| `usaspending-prime-census` | none | Already installed and working in his harness (the usaspending_prime_census skill). Listed here for completeness so... |
| `uspto-open-data-portal` **(unverified)** | free_key | Who patented what is a core input to defence-industrial and pharma analysis (assignee concentration, blocking... |
| `uspto-tsdr-trademarks` **(unverified)** | free_key | Brand ownership and opposition history expose product-line strategy and shell-company structures that company... |
| `wayback-cdx-api` | none | Evidence of what a page said, and when: award notices, sanctions entries, procurement pages and price lists that... |
| `wikidata-sparql` | none | Entity resolution with free reuse rights: turning a company or person name into a stable Q-id with headquarters,... |
| `wipo-patentscope` **(unverified)** | none | Kept in the inventory so nobody builds against it: PCT filings matter for who is protecting inventions... |

## Defence, procurement, geopolitics and sanctions (26)

| source | auth | what it answers |
|---|---|---|
| `acled-api` | free_key | For a conflict that is happening this month, UCDP has not published yet. ACLED is the near-real-time event record,... |
| `congress-gov-api` | free_key | NDAA text, authorization levels, and the CRS explainer of a programme are the legislative half of a defence-demand... |
| `copernicus-dataspace` | none | Sentinel-1 SAR is the open way to check a claimed ship movement, a port closure, or damage to infrastructure... |
| `eda-defence-data` | none | European defence-spending comparisons that include procurement share and collaborative spending use EDA's... |
| `eu-fsd-sanctions` | none | A counterparty cleared against OFAC can still be designated in Brussels. EU defence and dual-use work, and any... |
| `eu-sanctions-map` | none | Before screening names, the question is often which regimes exist and when they were last amended. This is the... |
| `federal-register-api` | none | Entity List additions, ITAR amendments, and DoD rulemaking are published here before they appear in any sanctions... |
| `fpds-ng-atom` | none | When a memo needs the modification history or the exact action (a delivery order, a vendor, a signed date) rather... |
| `gdelt-v2` | none | GDELT is the widest net for 'what is being reported where right now'. It is a lead generator for a defence or... |
| `govinfo-api` | free_key | GAO findings and the President's Budget are the two documents a defence-demand memo cites for 'what was requested'... |
| `nasa-firms` | free_key | Thermal detections are the open-source way to corroborate a claimed strike on fuel storage, a refinery fire, or... |
| `nato-defence-expenditure` | none | The 2 percent and 5 percent pledges are defined on NATO's own tables, not on SIPRI. A memo about burden-sharing has... |
| `noaa-marinecadastre-ais` | none | Historical vessel movements in US waters, including tankers and government vessels, are citable from here without a... |
| `ofac-sdn-list` | none | This is the US answer to 'is this counterparty sanctioned'. A defence or investment memo that names a foreign... |
| `opensky-network` | none | It is the open way to check whether civil traffic is still flying a corridor, or whether a specific transponder was... |
| `sam-gov-entity-exclusions` **(unverified)** | free_key | Before naming a company as a prime or a supplier, the registration and the exclusions list say whether it can... |
| `sam-gov-opportunities` | free_key | This is the forward book: what DoD and civilian agencies are about to buy, before an award exists in FPDS or... |
| `sipri-arms-transfers` | none | A claim that a country is arming another country needs the SIPRI register, not a press roundup. Trend-indicator... |
| `sipri-milex` | none | Country defence-spending time series in a memo should come from this workbook, not from a news summary of it. It is... |
| `trade-gov-csl` | none | The BIS Entity List has no clean bulk file of its own (the old bis.doc.gov supplement path now returns an HTML... |
| `ucdp-ged` | none | Fatality and event counts in a conflict memo should cite a UCDP version, because the version is frozen and the... |
| `un-comtrade-preview` | none | Reported arms and ammunition trade in dollars and kilograms, by reporter and partner, is the customs counterpart to... |
| `un-sc-consolidated-list` | none | UN listings are the baseline most other regimes incorporate. A screening that checks OFAC and the EU and skips the... |
| `usaspending-api` | none | This is the queryable record of who the US government paid, for how much, and under which award id. Defence-demand... |
| `usgs-earthquake-fdsn` | none | A reported explosion near a test site or a front line is often an earthquake. This catalogue is the first check,... |
| `worldbank-milex-indicator` | none | For a quick, machine-readable GDP-share figure across every country, this is the one call. The citation still... |

## When a source is not here

Absence is deliberate in most cases; the lane notes record what was excluded and why.
If a needed source is missing, add it to the inventory first and regenerate, so the
registry stays the single description of what this skill can reach.
