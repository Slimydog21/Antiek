# Source contracts

133 sources, merged from the inventory lanes and probed live. Fields follow the inventory schema.

## Corporate, financial and macro

### `alpha-vantage` - Alpha Vantage market data

- **publisher**: Alpha Vantage Inc.
- **base**: https://www.alphavantage.co
- **endpoints**: /query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo, /query?function=TIME_SERIES_INTRADAY&symbol=IBM&interval=5min&apikey=demo
- **auth**: free_key - Free key from https://www.alphavantage.co/support/#api-key. The demo key works only for IBM on the documented demo calls. A missing key returns a JSON error with HTTP 200.
- **rate limit**: Free key: 'the majority of our datasets for 25 API requests per day' (https://www.alphavantage.co/support/). Premium plans on https://www.alphavantage.co/premium/ are listed from $49.99/month upward.
- **format**: JSON
- **cadence**: real-time
- **coverage**: Equity quotes, daily and intraday bars, FX and indicators. Probed GLOBAL_QUOTE IBM with apikey=demo: HTTP 200, price 220.6700, latest trading day 2026-09-28, volume 5291533. Intraday demo HTTP 200, last refreshed 2026-09-28 19:55:00. A call with no key returned HTTP 200 and an Error Message telling the caller to claim a key.
- **licence**: Alpha Vantage terms of service bind the key. Data is vendor market data, not a filing. Do not cite it as a primary disclosure.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.alphavantage.co/query?function=GLOBAL_QUOTE&symbol=IBM&apikey=demo'` -> 200)
- **why**: A free, keyed quote and history check when a memo needs a price next to a filing and no terminal is open. Not the source for the fundamental number.
- **caveats**: HTTP 200 is also the error channel. demo is IBM-only. 25 requests per day will not support a universe scan. Premium starts at $49.99/month. Adjusted close and split handling differ by function.

### `bank-of-england-iadb` - Bank of England statistical database

- **publisher**: Bank of England
- **base**: https://www.bankofengland.co.uk
- **endpoints**: /boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Dec/2024&Dateto=31/Dec/2024&SeriesCodes=XUDLUSS&CSVF=TN&UsingCodes=Y&VPD=Y, /boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Aug/2026&Dateto=31/Aug/2026&SeriesCodes=IUMABEDR&CSVF=TN&UsingCodes=Y
- **auth**: none - No key. Series codes come from the Interactive Database series picker. csv.x=yes returns CSV.
- **rate limit**: Not documented. Both calls returned in under a second.
- **format**: CSV
- **cadence**: daily
- **coverage**: Sterling FX, Bank Rate and other BoE series. Probed XUDLUSS (spot USD into GBP convention as published) for December 2024: HTTP 200, CSV rows from 02 Jan 2024 style daily quotes; December request returned daily observations. IUMABEDR for August 2026: HTTP 200, one row 31 Aug 2026, 3.75.
- **licence**: Bank of England statistical series, published for public use. The specific disclaimer URL this lane tried (/legal/disclaimer) returned the BoE 404 page, so cite the series page and the Bank as publisher.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp?csv.x=yes&Datefrom=01/Aug/2026&Dateto=31/Aug/2026&SeriesCodes=IUMABEDR&CSVF=TN&UsingCodes=Y'` -> 200)
- **why**: Bank Rate and sterling FX for a UK defence or pharma counterparty. ONS covers activity; the Bank covers the policy rate.
- **caveats**: The endpoint is an old ASP report, not REST. Date format is DD/Mon/YYYY. A series can return a single month-end row. The non-underscore fromshowcolumns.asp path returned HTML rather than CSV in one test; use _iadb-fromshowcolumns.asp with csv.x=yes.

### `bea-data-api` - BEA data API

- **publisher**: U.S. Bureau of Economic Analysis
- **base**: https://apps.bea.gov
- **endpoints**: /api/data?UserID=DEMO&method=GETDATASETLIST&ResultFormat=JSON, /api/data?UserID=USER&method=GetData&DataSetName=NIPA&TableName=T10101&Frequency=A&Year=2023&ResultFormat=JSON
- **auth**: free_key - Free UserID from https://apps.bea.gov/API/signup/index.cfm. Sent as UserID query parameter. The published sample value DEMO is rejected.
- **rate limit**: Not stated on the signup page this lane read. Dataset-list call with DEMO returned in about 1s.
- **format**: JSON
- **cadence**: quarterly
- **coverage**: NIPA, GDP by industry, international transactions, input-output, regional accounts and other BEA datasets. Probed GETDATASETLIST with UserID=DEMO: HTTP 200 and a dataset list. Probed NIPA table T10101 for 2023 with the same DEMO id: HTTP 200 but body APIErrorCode 1, 'Invalid Request - Invalid API UserId.' So the route is live and the sample key is not.
- **licence**: BEA open-data program (https://www.bea.gov/open-data). U.S. federal statistical data, free to request with a UserID.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://apps.bea.gov/api/data?UserID=DEMO&method=GETDATASETLIST&ResultFormat=JSON'` -> 200)
- **why**: BEA is the source of the GDP, industry and trade-in-services numbers a memo should cite. FRED reprints many of them; BEA is the publisher.
- **caveats**: Do not ship UserID=DEMO. It returns HTTP 200 with an error object, which is easy to treat as data. Table names are codes (T10101), not titles. GetParameterList before GetData.

### `bis-stats-api` - BIS Data Portal SDMX API

- **publisher**: Bank for International Settlements
- **base**: https://stats.bis.org
- **endpoints**: /api/v2/data/dataflow/BIS/WS_EER/1.0/M.R.B.US?startPeriod=2024-12&endPeriod=2024-12&format=csvdata
- **auth**: none - No key. SDMX 2.1-style path on api/v2. Portal: https://data.bis.org/.
- **rate limit**: Not stated. One series-month call returned 215 bytes.
- **format**: CSV
- **cadence**: monthly
- **coverage**: BIS statistics, including effective exchange rates, credit, debt securities and locational banking. Probed WS_EER real broad USD index, monthly, December 2024: HTTP 200, OBS_VALUE 112.85, title 'United States - Real - Broad (64 economies)'.
- **licence**: BIS terms: users may use the statistics published in the BIS Data Portal under the terms headed 'About BIS statistics' (https://www.bis.org/terms_conditions.htm). Other BIS material has a narrower extract right.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://stats.bis.org/api/v2/data/dataflow/BIS/WS_EER/1.0/M.R.B.US?startPeriod=2024-12&endPeriod=2024-12&format=csvdata'` -> 200)
- **why**: The real broad dollar index and cross-border banking numbers when a memo discusses dollar strength or international bank claims. BIS is the publisher.
- **caveats**: Keys are dataflow-specific. The v1 path /api/v1 404s. Read the About BIS statistics terms before republishing a large extract. OBS_VALUE 112.85 is an index, not a rate.

### `bls-public-api` - BLS Public Data API

- **publisher**: U.S. Bureau of Labor Statistics
- **base**: https://api.bls.gov
- **endpoints**: /publicAPI/v1/timeseries/data/LNS14000000, /publicAPI/v2/timeseries/data/
- **auth**: none - Version 1 needs no key and accepts one series via POST body. Version 2 needs a free registration key for multiple series, calculations and higher limits: https://www.bls.gov/developers/. Registration is not a paid plan.
- **rate limit**: BLS documents v1 as the unregistered API and v2 as the registered API (https://www.bls.gov/developers/home.htm). This lane did not extract a current numeric cap from that page; one v1 POST returned in 121 ms.
- **format**: JSON
- **cadence**: monthly
- **coverage**: BLS time series: CPI, PPI, employment, unemployment, wages, import/export prices. Probed v1 POST for LNS14000000 (unemployment rate) with startyear/endyear 2024: HTTP 200, status REQUEST_SUCCEEDED, latest August 2026 value 4.1. GET on the v2 URL without a body returned HTTP 405. PPI flat file https://download.bls.gov/pub/time.series/pc/pc.data.0.Current returned HTTP 200, about 64.5 MB.
- **licence**: U.S. federal statistical release. BLS publishes the series for public use through the API (https://www.bls.gov/developers/).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Content-Type: application/json' -X POST -d '{"seriesid":["LNS14000000"],"startyear":"2024","endyear":"2024"}' https://api.bls.gov/publicAPI/v1/timeseries/data/LNS14000000` -> 200)
- **why**: CPI, wages and unemployment are the price and labour inputs in a pharma cost model and in any macro section of a memo. The series id is the citation.
- **caveats**: v1 requests are POST, not GET. Multiple series, net change and catalogs need v2 and a key. Series ids encode seasonal adjustment (LNS vs LNU). Footnotes can blank a value. Latest flag is on one observation only.

### `census-bureau-api` - Census Bureau data API and FT-900

- **publisher**: U.S. Census Bureau
- **base**: https://api.census.gov
- **endpoints**: /data.json, /data/2022/cbp.json, /data/2022/cbp?get=NAME,NAICS2017,ESTAB,EMP&for=us:*&NAICS2017=336411, https://www.census.gov/foreign-trade/Press-Release/current_press_release/ft900xlsx.zip
- **auth**: free_key - Data queries require a free key from https://api.census.gov/data/key_signup.html, sent as key=. The catalog and dataset metadata URLs answer without a key. Query limits page: https://www.census.gov/data/developers/guidance/api-user-guide.Query_Limits.html.
- **rate limit**: Census says an API key is required on every data query and that one query can include up to 50 variables (query-limits page, read 2026-09-29). A numeric daily cap was not in the HTML this lane extracted.
- **format**: JSON
- **cadence**: irregular
- **coverage**: Economic Census, County Business Patterns, ACS, population estimates, time series of retail and construction, and international trade. Catalog https://api.census.gov/data.json HTTP 200, 5.2 MB. CBP 2022 metadata HTTP 200. A CBP data query for NAICS 336411 without a key returned HTTP 200 with an HTML body titled Missing Key, not JSON. Current FT-900 workbook zip HTTP 200, 7,113,049 bytes: https://www.census.gov/foreign-trade/Press-Release/current_press_release/ft900xlsx.zip.
- **licence**: U.S. federal statistical data. Census developer terms require a key (https://www.census.gov/data/developers.html).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://api.census.gov/data/2022/cbp.json` -> 200)
- **why**: County Business Patterns and the trade release answer 'how many establishments, how much employment, what did the US export' for a defence-industrial NAICS or a country pair, which is a demand input in this operator's memos.
- **caveats**: HTTP 200 plus HTML 'Missing Key' is a failed query. NAICS and time vintage are part of the dataset path (2022/cbp is not the latest economic census). FT-900 is an Excel zip, not the API. Establishment counts are not firm counts.

### `cftc-commitments-of-traders` - CFTC Commitments of Traders

- **publisher**: U.S. Commodity Futures Trading Commission
- **base**: https://www.cftc.gov
- **endpoints**: /dea/newcot/deafut.txt, /dea/newcot/c_disagg.txt, https://publicreporting.cftc.gov/resource/6dca-aqww.json?$limit=1
- **auth**: none - No key for the text files or the Socrata resource. Socrata app token is optional. Portal: https://publicreporting.cftc.gov/ and report notes https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm.
- **rate limit**: Socrata default page size applies. Text files are one full report. A filtered JSON call returned in one request.
- **format**: JSON
- **cadence**: weekly
- **coverage**: Futures and options open interest by trader category. Probed deafut.txt HTTP 200, 433,046 bytes, first row WHEAT-SRW CBOT report date 2026-09-22, open interest 483279. Disaggregated c_disagg.txt HTTP 200. Socrata view 6dca-aqww ('Legacy - Futures Only') HTTP 200; a $select of open_interest_all for contract 001602 returned 483279 on 2026-09-22.
- **licence**: U.S. federal market report, published for public use (https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://publicreporting.cftc.gov/resource/6dca-aqww.json?$select=market_and_exchange_names,report_date_as_yyyy_mm_dd,open_interest_all&$where=cftc_contract_market_code=%27001602%27&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=1'` -> 200)
- **why**: Positioning in a commodity or rate future when a memo discusses hedging by a producer, airline, or Treasury-futures book. The report date is the citation.
- **caveats**: Column names on Socrata do not match the old text-file mnemonics; a wrong column is HTTP 400. Futures-only and combined, legacy and disaggregated, are different datasets. Text files are fixed-width in spirit and comma-separated in practice, with quoted market names.

### `companies-house` - UK Companies House public data API

- **publisher**: Companies House (UK registrar)
- **base**: https://api.company-information.service.gov.uk
- **endpoints**: /search/companies?q=rolls-royce, /company/00445790, /company/{number}/persons-with-significant-control, /company/{number}/filing-history
- **auth**: free_key - HTTP Basic auth with the API key as the username and an empty password. Create a free application at https://developer.company-information.service.gov.uk/manage-applications. Empty Authorization header returned HTTP 401.
- **rate limit**: Developer guidelines: up to 600 requests within a five-minute period, then HTTP 429 (https://developer.company-information.service.gov.uk/developer-guidelines).
- **format**: JSON
- **cadence**: real-time
- **coverage**: UK company profile, officers, PSC, filing history and document metadata. Probed /search/companies?q=rolls-royce and /company/00445790 with no key: both HTTP 401, body {"error":"Empty Authorization header","type":"ch:service"}. The developer-guidelines page HTTP 200 states the 600-request rule.
- **licence**: UK public-register data via the Companies House API. Crown copyright and the Open Government Licence apply to core register content (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The API itself requires a registered key.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://api.company-information.service.gov.uk/company/00445790` -> 401)
- **why**: UK subsidiary, joint-venture and PSC lookup for a defence or pharma group that files in Britain. The company number is the citation, and PSC is the ownership layer EDGAR does not have.
- **caveats**: 401 means the key is missing, not that the company is missing. Rate window is 600 per 5 minutes. Accounts are iXBRL or PDF, not a U.S.-style XBRL companyfacts API. This lane did not register a key, so no company payload was read.

### `ecb-data-portal` - ECB Data Portal API

- **publisher**: European Central Bank
- **base**: https://data-api.ecb.europa.eu
- **endpoints**: /service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2024-12-30&endPeriod=2024-12-31&format=csvdata, /service/data/FM/M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA?startPeriod=2024-12&format=csvdata, /service/data/YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=1&format=csvdata, /service/dataflow
- **auth**: none - No key. format=csvdata is the practical output. Dataflow list at /service/dataflow.
- **rate limit**: Not stated. CSV calls returned in 1-3 seconds.
- **format**: CSV
- **cadence**: daily
- **coverage**: ECB statistical data warehouse: FX, money-market rates, yield curves, balance sheet. Probed USD per EUR reference rate 2024-12-30: HTTP 200, OBS_VALUE 1.0444. Euro-area yield curve 10-year spot, last observation: 2026-09-28, OBS_VALUE 3.6313186552. EURIBOR 3-month monthly CSV HTTP 200. Dataflow inventory HTTP 200, about 147 KB.
- **licence**: ECB disclaimer: reuse is allowed and the information 'may be obtained free of charge' from the ECB site; modified statistics must be labelled as modified (https://www.ecb.europa.eu/services/using-our-site/disclaimer/html/index.en.html).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://data-api.ecb.europa.eu/service/data/EXR/D.USD.EUR.SP00.A?startPeriod=2024-12-30&endPeriod=2024-12-31&format=csvdata'` -> 200)
- **why**: Euro FX and the euro-area curve for a European revenue or debt line in a memo. The series key is the citation.
- **caveats**: Series keys are positional and fail closed. CSV has a long attribute header; OBS_VALUE is the number. The yield-curve key above is the AAA-style technical series the portal returned, not a government bond quote. Daily FX is a reference rate, not a trade.

### `estat-japan` - e-Stat API (Japan official statistics)

- **publisher**: Statistics Bureau of Japan / e-Stat
- **base**: https://api.e-stat.go.jp
- **endpoints**: /rest/3.0/app/json/getStatsList?lang=E&statsCode=00200544&limit=1
- **auth**: free_key - appId query parameter. Register at https://www.e-stat.go.jp/api/api-info/api-guide (HTTP 200). A call without appId returns JSON status 100, not an HTTP error.
- **rate limit**: Not measured. The guide page is the registration path; this lane did not create an application.
- **format**: JSON
- **cadence**: irregular
- **coverage**: Japanese official statistics catalog and table data, including trade and production tables once an appId is issued. Probed getStatsList for statsCode 00200544 with no appId: HTTP 200, body STATUS 100, 'Authentication failed. Please check that your appID are correct.'
- **licence**: Japanese government statistics via e-Stat. The API guide is the terms page; cite the stats code and table.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.e-stat.go.jp/rest/3.0/app/json/getStatsList?lang=E&statsCode=00200544&limit=1'` -> 200)
- **why**: Japanese production, prices and trade for a Japan-sourced component or a MoF-adjacent macro fact, in machine-readable form. Japan Customs publishes the trade tables; e-Stat is the API in front of official series.
- **caveats**: HTTP 200 with STATUS 100 means the key is missing. This lane did not register, so no table values were read. Table ids are e-Stat codes. English labels are partial.

### `eurostat-api` - Eurostat dissemination API

- **publisher**: Eurostat
- **base**: https://ec.europa.eu/eurostat/api/dissemination
- **endpoints**: /statistics/1.0/data/prc_hicp_manr?format=JSON&lang=en&geo=EA&coicop=CP00&unit=RCH_A&lastTimePeriod=1, /statistics/1.0/data/nama_10_gdp?format=JSON&lang=en&geo=DE&unit=CP_MEUR&na_item=B1GQ&lastTimePeriod=1, /sdmx/2.1/data/prc_hicp_midx?format=JSON&geo=EA&coicop=CP00&startPeriod=2024-12&endPeriod=2024-12
- **auth**: none - No key. Statistics API 1.0 and SDMX 2.1 both answered. Dataset codes are the Eurostat table codes.
- **rate limit**: Not stated. lastTimePeriod=1 keeps responses small. A less filtered HICP index call returned 451,678 bytes.
- **format**: JSON
- **cadence**: monthly
- **coverage**: Euro area and EU statistics. Probed HICP annual rate prc_hicp_manr for EA, all-items: HTTP 200, value 2.0, updated 2026-02-06. German GDP nama_10_gdp last period HTTP 200. HICP index via SDMX 2.1 HTTP 200. Setting time and lastTimePeriod together returned HTTP 400.
- **licence**: Eurostat copyright notice: reuse of statistical data 'for commercial or non-commercial purposes is authorised provided the source is acknowledged' (https://ec.europa.eu/eurostat/help/copyright-notice).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/prc_hicp_manr?format=JSON&lang=en&geo=EA&coicop=CP00&unit=RCH_A&lastTimePeriod=1'` -> 200)
- **why**: Euro-area inflation and member-state GDP for a European supplier, payer or trial-site country in a memo.
- **caveats**: Do not send time together with lastTimePeriod. geo=EA is the euro area, not a country. JSON-stat uses numeric indexes into dimensions; misreading the index attributes the value to the wrong country. Some tables stop updating on a lag (this HICP extract said February 2026).

### `fdic-bankfind` - FDIC BankFind Suite API

- **publisher**: Federal Deposit Insurance Corporation
- **base**: https://api.fdic.gov
- **endpoints**: /banks/institutions?filters=STALP:CA&fields=NAME,CERT,ASSET,CITY&limit=2, /banks/financials?filters=CERT:628&fields=CERT,REPDTE,ASSET,DEP&limit=1&sort_by=REPDTE&sort_order=DESC, /banks/failures?fields=NAME,FAILDATE,COST&limit=1&sort_by=FAILDATE&sort_order=DESC, /banks/locations?filters=CERT:628&fields=NAME,CITY,STALP&limit=1, /banks/sod?filters=YEAR:2023%20AND%20CERT:628&fields=CERT,YEAR,DEPSUMBR&limit=1
- **auth**: none - No key observed. Queries answered without an Authorization header. Docs: https://api.fdic.gov/banks/docs and guide https://www.fdic.gov/bank-data-guide.
- **rate limit**: Not stated in response headers this lane saw. limit= controls page size. Institutions index timestamp was 2026-09-25.
- **format**: JSON
- **cadence**: quarterly
- **coverage**: Institutions, financials (call-report derived), locations, deposits (SOD) and failures. Probed California institutions: HTTP 200, meta.total 1286. CERT 628 financials: REPDTE 20260630, ASSET 4091315000, DEP 2820284000. Failures: total 4117, latest row SMALL BUSINESS BANK, FAILDATE 7/17/2026, COST 5671. Locations for CERT 628: total 5401.
- **licence**: FDIC public bank data (https://www.fdic.gov/bank-data-guide). U.S. federal dataset.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.fdic.gov/banks/financials?filters=CERT:628&fields=CERT,REPDTE,ASSET,DEP&limit=1&sort_by=REPDTE&sort_order=DESC'` -> 200)
- **why**: Bank counterparty and deposit-franchise facts for a lender in a memo, and the failure list when a financing party has disappeared. CERT is the join key.
- **caveats**: Financial amounts are in thousands of dollars. REPDTE is YYYYMMDD. SOD DEPSUMBR can be zero on a branch-level row; do not treat one row as the bank. Failure COST units need the data dictionary. Filters are a custom syntax, and AND must be URL-encoded.

### `federal-reserve-h15` - Federal Reserve H.15 selected interest rates

- **publisher**: Board of Governors of the Federal Reserve System
- **base**: https://www.federalreserve.gov
- **endpoints**: /datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn, /feeds/h15.html
- **auth**: none - No key. Data Download Program: https://www.federalreserve.gov/datadownload/Choose.aspx?rel=H15. Series codes are chosen in that builder.
- **rate limit**: No documented cap. The full CSV this lane requested was 1,007,572 bytes.
- **format**: CSV
- **cadence**: daily
- **coverage**: H.15 Treasury constant-maturity yields, selected money-market rates and Fed funds. Probed the Data Download CSV for the packaged H.15 series set: HTTP 200, header begins 'Market yield on U.S. Treasury securities at 1-month constant maturity'.
- **licence**: Board disclaimer: unless otherwise indicated, information on the Board's website 'is in the public domain and may be copied and distributed without permission. Please cite to the Board as the source.' (https://www.federalreserve.gov/disclaimer.htm).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.federalreserve.gov/datadownload/Output.aspx?rel=H15&series=bf17364827e38702b42a58cf8eaa3f78&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn'` -> 200)
- **why**: The constant-maturity Treasury curve a memo uses for discounting. It is the Board release, which outranks a vendor yield.
- **caveats**: The series query parameter is an opaque package built by the Data Download UI, not a human series id. Business-day holidays are blank. Nominal and inflation-indexed curves are different packages.

### `ffiec-cdr-bulk` - FFIEC Central Data Repository call report bulk

- **publisher**: Federal Financial Institutions Examination Council
- **base**: https://cdr.ffiec.gov
- **endpoints**: /public/PWS/DownloadBulkData.aspx
- **auth**: none - Bulk download page is public. A single-bank CSV from the National Information Center returned a CAPTCHA page, so that path is not a machine API.
- **rate limit**: Interactive bulk page. No unauthenticated REST call succeeded.
- **format**: bulk download
- **cadence**: quarterly
- **coverage**: Bank call reports for the universe, distributed as bulk files from the CDR. Probed the download page: HTTP 200, title 'Download Bulk Data - FFIEC Central Data Repository'. A guessed file https://cdr.ffiec.gov/CDRDownload/CDR/Call/Call_09302024.zip returned HTTP 404. NIC one-bank CSV https://www.ffiec.gov/npw/FinancialReport/ReturnFinancialReportCSV returned HTTP 403 with title 'CAPTCHA Error | FFIEC'.
- **licence**: FFIEC public call-report data. The CDR page is the distribution point (https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://cdr.ffiec.gov/public/PWS/DownloadBulkData.aspx` -> 200)
- **why**: The microdata behind bank peer comparisons when FDIC's pre-aggregated financials are not enough. Included because the page is the authoritative distribution, with the CAPTCHA trap recorded.
- **caveats**: Do not treat the NIC CSV URL as an API: it 403s behind a CAPTCHA. Bulk filenames are not guessable. For a single bank's assets and deposits, use FDIC BankFind financials instead.

### `finra-otc-and-regsho` - FINRA equity short interest and Reg SHO daily files

- **publisher**: Financial Industry Regulatory Authority
- **base**: https://api.finra.org
- **endpoints**: /data/group/otcMarket/name/EquityShortInterest?limit=1, /data/group/otcMarket/name/weeklySummary, https://cdn.finra.org/equity/regsho/daily/CNMSshvol20260925.txt
- **auth**: none - The equity short-interest and weekly-summary queries answered with no token. Developer portal: https://developer.finra.org/. Some FINRA datasets require registration; these two did not.
- **rate limit**: limit and offset query parameters. A limit=1 call returned one row. No rate header observed.
- **format**: JSON
- **cadence**: daily
- **coverage**: Consolidated short interest and Reg SHO daily short volume. Probed EquityShortInterest with Accept: application/json: HTTP 200, one row AAALF, settlementDate 2018-09-14, currentShortShareNumber 131471. Without that header the same URL returns CSV. Reg SHO CNMSshvol20260925.txt HTTP 200, 546,817 bytes, pipe-delimited Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market. weeklySummary HTTP 200.
- **licence**: FINRA-published regulatory data. Developer portal terms apply (https://developer.finra.org/). Cite the settlement date.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Accept: application/json' 'https://api.finra.org/data/group/otcMarket/name/EquityShortInterest?limit=1'` -> 200)
- **why**: Short interest and short volume for a listed name in a trading or issuance memo. Reg SHO is daily and exchange-consolidated; short interest is the bi-monthly settlement print.
- **caveats**: Default response is CSV text even though the path looks like an API; send Accept: application/json. The no-filter call's first row can be an old OTC name, so filter by symbol and settlement date. Reg SHO file names are CNMSshvolYYYYMMDD.txt. Short volume is not short interest.

### `fred-graph-csv` - FRED graph CSV and API

- **publisher**: Federal Reserve Bank of St. Louis
- **base**: https://fred.stlouisfed.org
- **endpoints**: /graph/fredgraph.csv?id=GDP, /graph/fredgraph.csv?id=CPIAUCSL, https://api.stlouisfed.org/fred/series?series_id=GDP&file_type=json
- **auth**: free_key - The graph CSV endpoint needs no key. The JSON API at api.stlouisfed.org requires api_key from a free FRED account: https://fred.stlouisfed.org/docs/api/api_key.html. Probed without a key, the API returned HTTP 400 'Variable api_key is not set.'
- **rate limit**: FRED documents the key requirement but this lane did not find a numeric cap on the current api_key page. Graph CSV calls returned in under a second.
- **format**: CSV
- **cadence**: daily
- **coverage**: FRED and ALFRED vintages of macro series. Probed GDP graph CSV: HTTP 200, first row 1947-01-01, 243.164. CPIAUCSL CSV HTTP 200 from 1947-01-01. Series pages such as https://fred.stlouisfed.org/series/GDP are the citation landing page.
- **licence**: FRED legal page: 'Public Domain: Citation requested' for series that are in the public domain, and a warning that some series 'may be under copyright' (https://fred.stlouisfed.org/legal/). API use also binds the FRED API Terms of Use (https://fred.stlouisfed.org/docs/api/terms_of_use.html).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=GDP'` -> 200)
- **why**: The macro denominator in an investment memo (GDP, CPI, unemployment, yields, FX) with a stable series id the operator can cite. ALFRED vintages matter when a memo must use the number as it stood on a date.
- **caveats**: Graph CSV is a convenience extract, not the documented API, and it does not return vintage history. A FRED series is often a reprint of BEA, BLS or Treasury; cite the source agency for the number and FRED for the extract. Units and seasonal adjustment sit in the series title, not in the CSV header.

### `gleif-lei` - GLEIF LEI records

- **publisher**: Global Legal Entity Identifier Foundation
- **base**: https://api.gleif.org
- **endpoints**: /api/v1/lei-records?filter[entity.legalName]=LOCKHEED%20MARTIN%20CORPORATION&page[size]=1, /api/v1/lei-records/HWUPKR0MPOU8FGXBT394, /api/v1/lei-records/HWUPKR0MPOU8FGXBT394/isins?page[size]=2, /api/v1/lei-records/HWUPKR0MPOU8FGXBT394/direct-children?page[size]=1
- **auth**: none - No key. API root https://api.gleif.org/api/v1/lei-records. Golden copy publish date is in meta.
- **rate limit**: Page size is set with page[size]. This lane's calls returned in under a second. No numeric cap was in the response headers.
- **format**: JSON
- **cadence**: daily
- **coverage**: Legal Entity Identifier records: legal name, address, registration status, and relationship links. Probed Apple Inc. LEI HWUPKR0MPOU8FGXBT394 HTTP 200, golden copy publishDate 2026-09-29. ISINs for that LEI: total 949. Direct children: total 8. Name search LOCKHEED MARTIN CORPORATION returned LEI DPRBOZP0K5RM2YE8UU08, country US. A name search for 'Apple' returned total 370, so the filter is not exact.
- **licence**: GLEIF LEI data terms: the LEI data and access service 'are provided under the CC0 licence' (https://www.gleif.org/en/meta/lei-data-terms-of-use/).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://api.gleif.org/api/v1/lei-records/HWUPKR0MPOU8FGXBT394` -> 200)
- **why**: The join key between a filing, a sanction name, an OpenFIGI security and a foreign subsidiary. A memo that names a legal entity should carry the LEI.
- **caveats**: legalName filter is a search, not an exact key. Relationship endpoints 404 when no parent is reported; that is not a transport failure. ISIN coverage is what registrars submitted, not a full listing list. Pagination is JSON:API style.

### `imf-sdmx` - IMF SDMX 3.0 and DataMapper

- **publisher**: International Monetary Fund
- **base**: https://api.imf.org
- **endpoints**: /external/sdmx/3.0/structure/dataflow?limit=1, /external/sdmx/2.1/data/CPI/USA.CPI._T.IX.M?startPeriod=2024-01&endPeriod=2024-03, /external/sdmx/3.0/data/dataflow/IMF.STA/CPI_2026_MAY_VINTAGE/1.0.0/USA.CPI._T.IX.M?lastNObservations=1, https://www.imf.org/external/datamapper/api/v1/NGDP_RPCH/USA
- **auth**: none - No key on the calls that worked. The old host dataservices.imf.org did not resolve. Portal: https://data.imf.org/.
- **rate limit**: Not published in the responses. Structure calls can be hundreds of kilobytes; use limit and a dataflow id.
- **format**: JSON
- **cadence**: monthly
- **coverage**: IMF statistics dataflows (CPI, BOP, MFS and others) plus the DataMapper convenience API. Probed CPI SDMX 2.1 for USA CPI all-items index, monthly: HTTP 200, 2024-M01 141.439679347689, 2024-M02 142.3151445388903, 2024-M03 143.2350938178583. Dataflow catalog HTTP 200. DataMapper NGDP_RPCH/USA HTTP 200, USA 1980 value -0.3 and a long annual panel. dataservices.imf.org failed DNS.
- **licence**: IMF publishes these series for public use. The IMF copyright page returned HTTP 403 to this lane, so reuse terms were not re-read from the site; cite the series and vintage.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Accept: application/vnd.sdmx.data+json' 'https://api.imf.org/external/sdmx/2.1/data/CPI/USA.CPI._T.IX.M?startPeriod=2024-01&endPeriod=2024-03'` -> 200)
- **why**: Cross-country CPI and WEO growth when a memo compares markets. The dataflow id plus the time period is the citation. DataMapper is the small JSON path for one indicator.
- **caveats**: Dataflow ids are versioned (CPI_2026_MAY_VINTAGE). A wrong key count returns HTTP 400 with an HTML or JSON error, not an empty series. The legacy dataservices host is dead. DataMapper returns every country unless the path includes the country code, and the file is still large.

### `ncua-call-report` - NCUA credit union call report quarterly files

- **publisher**: National Credit Union Administration
- **base**: https://ncua.gov
- **endpoints**: /files/publications/analysis/call-report-data-2026-06.zip, /files/publications/analysis/call-report-data-2024-03.zip, /analysis/credit-union-corporate-call-report-data/quarterly-data
- **auth**: none - No key. Quarterly zip files are linked from https://ncua.gov/analysis/credit-union-corporate-call-report-data/quarterly-data.
- **rate limit**: Bulk download. 2024-03 zip was 8,508,589 bytes. No query API found; mapping.ncua.gov timed out on a name search.
- **format**: bulk download
- **cadence**: quarterly
- **coverage**: Account-level call report for U.S. credit unions, one zip per quarter, with an account-description text file inside. Probed 2024-03, 2024-12, 2025-09, 2025-12, 2026-03 and 2026-06 zips: each HTTP 200 and a PK zip header. The 2026-06 range read showed Acct-DescTradeNames.txt in the archive.
- **licence**: U.S. federal regulator public call-report release. Cite the quarter file.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -r 0-30 https://ncua.gov/files/publications/analysis/call-report-data-2026-06.zip` -> 200)
- **why**: Credit-union lender financials when a memo's financing or deposit counterparty is a credit union rather than a bank. FDIC does not cover them.
- **caveats**: File layout is a zip of text, and account codes change; read the account-description file in the same zip. The quarter is in the filename. A directory listing is not published; the pattern call-report-data-YYYY-QQ.zip worked for the quarters probed.

### `nyfed-reference-rates` - New York Fed reference rates and SOMA

- **publisher**: Federal Reserve Bank of New York
- **base**: https://markets.newyorkfed.org
- **endpoints**: /api/rates/all/latest.json, /read?productCode=50&eventCodes=500&limit=1&sort=postDt:-1&format=json, /api/soma/summary.json
- **auth**: none - No key on the markets API. Docs are linked from https://markets.newyorkfed.org/static/docs/markets-api.html (site section: https://www.newyorkfed.org/markets/reference-rates).
- **rate limit**: Not published on the responses this lane received. latest.json returned in one call.
- **format**: JSON
- **cadence**: daily
- **coverage**: EFFR, OBFR, SOFR, SOFR averages and index, TGCR, BGCR, and SOMA holdings. Probed /api/rates/all/latest.json HTTP 200: EFFR effectiveDate 2026-09-28 percentRate 3.88, target 3.75-4.00, volumeInBillions 110; SOFRAI effectiveDate 2026-09-29 average30day 3.73909. SOMA summary JSON HTTP 200, about 320 KB.
- **licence**: NY Fed publishes these as official reference rates. The Board's general website disclaimer says Board-site information is public domain with citation (https://www.federalreserve.gov/disclaimer.htm); cite the New York Fed release for these series specifically.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://markets.newyorkfed.org/api/rates/all/latest.json` -> 200)
- **why**: SOFR and EFFR are the funding rates under a discount rate or a floating-rate instrument in a memo. SOMA is the Fed's holdings, not a market price.
- **caveats**: Percent fields are numbers, volumes are billions. SOFR averages print on a different effectiveDate than EFFR. The /read search endpoint is easy to over-filter; latest.json is the safe daily call. History needs the dated endpoints, not latest.

### `oecd-sdmx` - OECD SDMX API

- **publisher**: OECD
- **base**: https://sdmx.oecd.org
- **endpoints**: /public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.0/USA.M.LI...AA...H?startPeriod=2024-01&endPeriod=2024-01, /public/rest/dataflow/OECD.SDD.STES/DSD_STES@DF_CLI/4.0?references=none
- **auth**: none - No key on the public REST path. Dataflow inventory is /public/rest/dataflow/all.
- **rate limit**: Not stated. A one-period CLI query returned in one call. The all-dataflows document was 8.9 MB.
- **format**: XML
- **cadence**: monthly
- **coverage**: OECD.Stat via SDMX, including the composite leading indicator. Probed DF_CLI for USA monthly amplitude-adjusted CLI, 2024-01: HTTP 200, ObsValue 99.83714, TIME_PERIOD 2024-01. Dataflow structure for DF_CLI HTTP 200. A national-accounts key with the wrong number of dimensions returned HTTP 403 and the text 'Not enough key values in query, expecting 13 got 12'.
- **licence**: OECD terms page returned HTTP 403 from this network (https://www.oecd.org/en/about/terms-and-conditions.html), so the licence text was not re-read. Treat as OECD statistical content requiring attribution until that page is readable.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_CLI,4.0/USA.M.LI...AA...H?startPeriod=2024-01&endPeriod=2024-01'` -> 200)
- **why**: OECD CLI and national accounts for a non-US macro panel. Use it when the memo's comparison set is OECD members and IMF WEO is too coarse.
- **caveats**: The key must have one position per dimension; a short key comes back as HTTP 403 with a plain-text explanation, which looks like an auth failure. Dots mean wildcard. Format defaults to SDMX-ML. Dataflow versions (4.0 vs 4.1) change the key.

### `ofac-sdn` - OFAC Specially Designated Nationals list

- **publisher**: U.S. Department of the Treasury, Office of Foreign Assets Control
- **base**: https://www.treasury.gov
- **endpoints**: /ofac/downloads/sdn.csv, /ofac/downloads/sdn.xml, /ofac/downloads/consolidated/consolidated.xml, https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV
- **auth**: none - No key. The treasury.gov paths redirect to the sanctions-list service. Schema notes: https://ofac.treasury.gov/specially-designated-nationals-list-data-formats-data-schemas (portal https://ofac.treasury.gov/).
- **rate limit**: Bulk files, not a query API. sdn.csv was 5,695,076 bytes; sdn.xml 29,089,607 bytes.
- **format**: CSV
- **cadence**: irregular
- **coverage**: SDN and consolidated sanctions entries. Probed sdn.xml HTTP 200: Publish_Date 09/23/2026, Record_Count 19391, first entry AEROCARIBBEAN AIRLINES, program CUBA. sdn.csv and the sanctions-list-service CSV also HTTP 200. consolidated.xml HTTP 200, about 1.06 MB.
- **licence**: Official U.S. sanctions list published for compliance screening. Reuse does not change the legal effect of a designation. Cite the publish date.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://www.treasury.gov/ofac/downloads/sdn.xml` -> 200)
- **why**: Screen a counterparty, bank, vessel or foreign parent before a defence or clinical supply-chain memo treats it as a permissible customer. The publish date is part of the citation.
- **caveats**: CSV has no header row and uses -0- as a null. Names are not unique; match on uid. The SDN file is not the consolidated list. A hit is a name match, not a legal conclusion. Lists change between memos; store the Publish_Date.

### `ons-beta-api` - UK Office for National Statistics Beta API

- **publisher**: Office for National Statistics
- **base**: https://api.beta.ons.gov.uk
- **endpoints**: /v1/datasets?limit=3, /v1/datasets/gdp-to-four-decimal-places, /v1/datasets/gdp-to-four-decimal-places/editions/time-series/versions/69/observations?time=Jun-26&geography=K02000001&unofficialstandardindustrialclassification=A--T, https://download.ons.gov.uk/downloads/datasets/gdp-to-four-decimal-places/editions/time-series/versions/69.csv
- **auth**: none - No key. Dataset list and observations are open. API root https://api.beta.ons.gov.uk/v1/datasets.
- **rate limit**: Not stated on the responses. Observations default limit 10000.
- **format**: JSON
- **cadence**: monthly
- **coverage**: ONS time series, including monthly GDP. Probed dataset gdp-to-four-decimal-places HTTP 200: latest version id 69, unit 'Index. Seasonally adjusted 2016=100', next_release '16 April 2026'. Observation Jun-26, geography K02000001, industry A--T: HTTP 200, observation 103.4055. CSV download HTTP 206, first data row Jun-26 production industries 98.3012. Dataset list HTTP 200 includes trade, regional GDP and CPIH.
- **licence**: ONS content is Crown copyright, reusable under the Open Government Licence with attribution (https://www.ons.gov.uk/methodology/geography/licences and https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.beta.ons.gov.uk/v1/datasets/gdp-to-four-decimal-places/editions/time-series/versions/69/observations?time=Jun-26&geography=K02000001&unofficialstandardindustrialclassification=A--T'` -> 200)
- **why**: UK GDP and prices for a memo on a UK-listed supplier or a sterling cost base. The version id pins the vintage.
- **caveats**: Observations 400 if any dimension is omitted. Version numbers move; read latest_version from the dataset document rather than hard-coding 69. Time codes look like Jun-26. The API is still branded beta.

### `openfigi` - OpenFIGI mapping

- **publisher**: OpenFIGI LLC (Bloomberg FIGI as an open identifier)
- **base**: https://api.openfigi.com
- **endpoints**: /v3/mapping, /v3/search, /v3/mapping/values/exchCode
- **auth**: none - Mapping works without a key. An optional free API key raises the rate limit; request it from https://www.openfigi.com/api. Send a JSON array, not a GET.
- **rate limit**: Measured response headers without a key: ratelimit-policy 25;w=60, ratelimit-limit 25, ratelimit-remaining 24, ratelimit-reset 60.
- **format**: JSON
- **cadence**: daily
- **coverage**: FIGI, composite FIGI, share class FIGI, ticker, exchange and security type. Probed POST /v3/mapping for TICKER AAPL exchCode US: HTTP 200, figi BBG000B9XRY4, name APPLE INC, shareClassFIGI BBG001S5N8V8. LMT mapped to BBG000C1BW00. /v3/search for 'Apple Inc' HTTP 200. exchCode values HTTP 200.
- **licence**: OpenFIGI API is the public mapping service for FIGI (https://www.openfigi.com/api). Identifiers are open; the service has its own request quota.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Content-Type: application/json' -d '[{"idType":"TICKER","idValue":"AAPL","exchCode":"US"}]' https://api.openfigi.com/v3/mapping` -> 200)
- **why**: Stable security id when a memo joins a 13F CUSIP, a ticker and a listing across venues. FIGI survives ticker changes better than the ticker does.
- **caveats**: POST a JSON array. Unkeyed limit is 25 requests per rolling minute. Search returns many listings; mapping with exchCode is the precise call. No prices. Bloomberg remains the owner of the FIGI allocation.

### `polygon-io` - Polygon.io market data

- **publisher**: Polygon.io (Massive)
- **base**: https://api.polygon.io
- **endpoints**: /v2/aggs/ticker/AAPL/prev, /v3/reference/tickers/AAPL, /v1/marketstatus/now
- **auth**: paid_key - Every probed call without apiKey returned HTTP 401 'API Key was not provided'. Signup: https://polygon.io/dashboard/signup. Pricing page lists a Stocks Basic plan at $0/month (end-of-day US stocks, 5 API calls per minute, 2 years of history) and paid plans at $29, $79 and $199 per month (https://polygon.io/pricing).
- **rate limit**: Stocks Basic, as priced on the page: 5 API calls per minute. Higher plans raise the cap. Not measured here because no key was used.
- **format**: JSON
- **cadence**: daily
- **coverage**: US stock aggregates, reference data and market status. Probed previous-day aggregate, ticker reference and market status with no key: each HTTP 401 and a JSON error. Docs page for the previous-aggregate route HTTP 200.
- **licence**: Commercial market-data API. The free tier is the vendor's plan, not a public-domain feed. Cite Polygon only as a price source.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://api.polygon.io/v2/aggs/ticker/AAPL/prev` -> 401)
- **why**: End-of-day prices for a larger ticker list than Alpha Vantage's 25 calls a day, if the operator takes the free Stocks Basic key. Still a vendor, not a filing source.
- **caveats**: No key, no data. The $0 plan is end-of-day and 5 calls per minute, so it is not a tape. Real-time and full history sit on the $29-$199 plans. 401 is the unauthenticated result, not a dead host.

### `sba-foia-open-data` - SBA open data (PPP FOIA loan files)

- **publisher**: U.S. Small Business Administration
- **base**: https://data.sba.gov
- **endpoints**: /api/1/search?fulltext=Paycheck%20Protection%20Program%20FOIA, /dataset/ppp-foia, /sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv
- **auth**: none - No key. DKAN catalog search is /api/1/search. Files are direct CSV links on the dataset page.
- **rate limit**: Bulk files. The over-150k PPP CSV is 452,077,279 bytes. Use HTTP Range.
- **format**: CSV
- **cadence**: irregular
- **coverage**: SBA FOIA loan-level releases, including PPP. Search for the PPP dataset: HTTP 200, identifier SBA-OCA-2022-07-001. Dataset page HTTP 200. public_150k_plus_240930.csv HTTP 200 with header LoanNumber, DateApproved, BorrowerName, InitialApprovalAmount and lender fields. The catalog also lists EIDL and Restaurant Revitalization files. The old CKAN path /api/3/action/package_search returned HTTP 404.
- **licence**: Dataset page states License 'U.S. Government Works' (https://data.sba.gov/dataset/ppp-foia).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -r 0-200 https://data.sba.gov/sites/default/files/distribution/SBA-OCA-2022-07-001/public_150k_plus_240930.csv` -> 206)
- **why**: Loan-level check on whether a small supplier actually received a PPP or EIDL loan, with lender and amount, for a counterparty paragraph.
- **caveats**: Files are snapshots (this PPP extract is dated 240930 in the filename), not a current portfolio. Borrower name is not an LEI. The over-150k file is one of many; sub-150k loans are split across numbered CSVs. CKAN clients will 404.

### `sec-edgar-companyfacts` - SEC EDGAR XBRL company facts

- **publisher**: U.S. Securities and Exchange Commission
- **base**: https://data.sec.gov
- **endpoints**: /api/xbrl/companyfacts/CIK0000320193.json, /api/xbrl/companyconcept/CIK0000320193/us-gaap/AccountsPayableCurrent.json
- **auth**: none - No key. Same SEC User-Agent rule as submissions. Docs: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- **rate limit**: Same SEC fair-access ceiling, 10 requests/second. Apple companyfacts returned 3.8 MB JSON.
- **format**: JSON
- **cadence**: daily
- **coverage**: All XBRL facts filed by one company, keyed by taxonomy (us-gaap, ifrs-full, dei) and tag, with units, period, filed date and accession. Companyconcept returns one tag. Probed Apple Inc. CIK 0000320193 (companyfacts HTTP 200, 3,789,099 bytes) and us-gaap/AccountsPayableCurrent (HTTP 200). Bulk zip of every companyfacts file is https://www.sec.gov/Archives/edgar/daily-index/xbrl/companyfacts.zip (HTTP 200, Content-Length 1,409,764,049 bytes on 2026-09-29).
- **licence**: U.S. federal work, public EDGAR dissemination (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json` -> 200)
- **why**: The citable numeric layer under a 10-K or 10-Q: revenue, assets, R&D, backlog-adjacent tags, segment facts. An investment memo can point at taxonomy, tag, period and accession instead of a scraped HTML table.
- **caveats**: Only filers who submit XBRL, and only tagged facts. Custom extension tags do not compare across issuers. A fact can be restated; use the filed date and accession, not the latest value alone. CY2023 (no quarter) frame keys 404; use the instant/duration period code.

### `sec-edgar-filing-archives` - SEC EDGAR filing archives and daily index

- **publisher**: U.S. Securities and Exchange Commission
- **base**: https://www.sec.gov
- **endpoints**: /Archives/edgar/data/1067983/000119312526403089/index.json, /Archives/edgar/data/1067983/000119312526403089/ownership.xml, /Archives/edgar/daily-index/2026/QTR3/master.20260925.idx, /cgi-bin/browse-edgar?action=getcompany&CIK=0000320193&type=10-K&count=1&output=atom
- **auth**: none - No key. User-Agent required. Directory index.json and the complete submission .txt are the stable machine paths.
- **rate limit**: 10 requests/second fair access, documented at https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data.
- **format**: XML
- **cadence**: real-time
- **coverage**: The filing body. Probed Berkshire filing 0001193125-26-403089: index.json HTTP 200 listed ownership.xml; that file is a Form 4 (documentType 4, periodOfReport 2026-09-23, issuer LENNAR CORP, reporting owner BERKSHIRE HATHAWAY INC). Daily master index master.20260925.idx HTTP 200. Company Atom feed for Apple 10-K HTTP 200 and returned accession 0000320193-25-000079. Ticker map https://www.sec.gov/files/company_tickers.json HTTP 200, 10,431 rows. Exchange map company_tickers_exchange.json HTTP 200.
- **licence**: U.S. federal work, public EDGAR archives (same fair-access page).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://www.sec.gov/Archives/edgar/data/1067983/000119312526403089/ownership.xml` -> 200)
- **why**: This is where a memo's filing number becomes a document: Form 4 XML, 13F information table, Form D primary_doc.xml, and the 10-K complete submission.
- **caveats**: Accession numbers in URLs drop the dashes. index.json is the directory listing; a guessed filename 404s. Form 4, 13F and Form D are XML; 10-K financials are mostly inside the complete submission or the XBRL instance. Daily index files are fixed-width text, not JSON.

### `sec-edgar-full-text` - SEC EDGAR full-text search

- **publisher**: U.S. Securities and Exchange Commission
- **base**: https://efts.sec.gov
- **endpoints**: /LATEST/search-index?forms=4&dateRange=custom&startdt=2026-09-26&enddt=2026-09-29, /LATEST/search-index?forms=D&dateRange=custom&startdt=2026-09-26&enddt=2026-09-29, /LATEST/search-index?q=%22revenue%22&forms=10-K&dateRange=custom&startdt=2024-01-01&enddt=2024-01-31
- **auth**: none - No key. Same SEC User-Agent rule. This is the backend of https://www.sec.gov/edgar/search/.
- **rate limit**: Not separately published. This lane's queries returned in 0.2-0.6s. Keep to the 10 requests/second fair-access ceiling.
- **format**: JSON
- **cadence**: real-time
- **coverage**: Full-text and form-filtered search over EDGAR filings. Probed forms=4 for 2026-09-26 to 2026-09-29: HTTP 200, hits.total.value 408, a hit with root_forms [4] and xslF345X06. forms=D over the same window: 327 hits. A 10-K phrase query for January 2024 returned 174 hits.
- **licence**: U.S. federal work, public EDGAR search (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://efts.sec.gov/LATEST/search-index?forms=4&dateRange=custom&startdt=2026-09-26&enddt=2026-09-29'` -> 200)
- **why**: Finds Form D raises, Form 4 insider sales, 13F holdings language and contract phrases inside 10-Ks when the operator does not already know the accession.
- **caveats**: Undocumented endpoint: parameter names can move when SEC changes the search UI. hits.total can be capped. Date filters are required for a tight query. Browse-edgar type=4 is prefix-match and returned 424B2; do not use it as a Form 4 filter.

### `sec-edgar-submissions` - SEC EDGAR submissions API

- **publisher**: U.S. Securities and Exchange Commission
- **base**: https://data.sec.gov
- **endpoints**: /submissions/CIK0001067983.json, /submissions/CIK##########-submissions-001.json
- **auth**: none - No key. SEC fair-access rules require a descriptive User-Agent with a contact email (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data). Declared User-Agent: prime-agent research contact:faisalnazer2@gmail.com.
- **rate limit**: Documented current max 10 requests/second on sec.gov EDGAR content (same page). data.sec.gov answered this lane in 0.1-0.7s.
- **format**: JSON
- **cadence**: real-time
- **coverage**: One JSON file per CIK: identity, SIC, tickers, exchanges, and the recent filings array (form, filingDate, accessionNumber, primaryDocument). Older filings paginate into additional submissions files. EDGAR electronic filings begin 1994/1995. Probed BERKSHIRE HATHAWAY INC (CIK 0001067983): tickers BRK-B/BRK-A, recent forms included 4, 3, SCHEDULE 13G, 13F-HR.
- **licence**: U.S. federal work. SEC publishes EDGAR for public access and states a fair-access rate (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data). Not a private licence.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://data.sec.gov/submissions/CIK0001067983.json` -> 200)
- **why**: Primary identity and filing index for any issuer or filer in an investment memo or defence-industrial profile. The accession number is the locator that later pulls the 10-K, 13F or Form 4.
- **caveats**: CIK must be zero-padded to 10 digits. The recent array is a window, not the full history; follow the additional submissions files. Filing metadata is not the filing body. Fair-access blocks follow a missing or generic User-Agent.

### `sec-edgar-xbrl-frames` - SEC EDGAR XBRL frames

- **publisher**: U.S. Securities and Exchange Commission
- **base**: https://data.sec.gov
- **endpoints**: /api/xbrl/frames/us-gaap/Assets/USD/CY2023Q4I.json
- **auth**: none - No key. Same SEC User-Agent rule. Period codes are documented at https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- **rate limit**: SEC fair-access ceiling, 10 requests/second. Assets CY2023Q4I returned 855,892 bytes.
- **format**: JSON
- **cadence**: daily
- **coverage**: One us-gaap (or other taxonomy) tag, one unit, one period, across all filers who reported it. Probed us-gaap/Assets/USD/CY2023Q4I: HTTP 200, label Assets. The same path with CY2023.json returned HTTP 404 NoSuchKey.
- **licence**: U.S. federal work, public EDGAR dissemination (https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://data.sec.gov/api/xbrl/frames/us-gaap/Assets/USD/CY2023Q4I.json` -> 200)
- **why**: Cross-sectional screen for a memo universe: total assets, revenue or R&D for every XBRL filer in one period, each row still carrying CIK and accession.
- **caveats**: Period suffix is part of the key: I instant, D duration, plus quarter. A wrong suffix is a 404 that looks like a missing concept. Units must match the tag (USD vs shares). Custom taxonomy tags are not in us-gaap frames.

### `treasury-fiscal-data` - U.S. Treasury Fiscal Data API

- **publisher**: U.S. Department of the Treasury, Bureau of the Fiscal Service
- **base**: https://api.fiscaldata.treasury.gov
- **endpoints**: /services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1, /services/api/fiscal_service/v1/accounting/od/auctions_query?filter=security_type:eq:Note,auction_date:gte:2026-09-01&sort=-auction_date&page[size]=3, /services/api/fiscal_service/v1/accounting/od/rates_of_exchange?page[size]=1
- **auth**: none - No key. Documentation: https://fiscaldata.treasury.gov/api-documentation/
- **rate limit**: Not a hard published cap on the documentation page this lane used. Calls returned in about 1s. Pagination is page[size] and page[number].
- **format**: JSON
- **cadence**: daily
- **coverage**: Debt to the penny, MSPD, auctions, interest rates, exchange rates and other Fiscal Service datasets. Probed debt_to_penny: HTTP 200, record_date 2026-09-25, tot_pub_debt_out_amt 40097178119750.91. Auctions: 7-year note auctioned 2026-09-24, high_yield 5.0850, bid_to_cover_ratio 2.42. Exchange-rate row for 2024-12-31 HTTP 200.
- **licence**: Fiscal Data: 'The data is offered free, without restriction, and available to copy, adapt, redistribute, or otherwise use for non-commercial or commercial purposes.' (https://fiscaldata.treasury.gov/api-documentation/).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1'` -> 200)
- **why**: The primary print for Treasury debt, auction yields and bid-to-cover. A memo that quotes a U.S. yield or the debt stock should land here, not on a secondary chart.
- **caveats**: Filter syntax is field:op:value with commas, not SQL. A future auction can return high_yield as the string 'null'. Amount fields are strings. Page size defaults are small. This is not the TIC cross-border dataset.

### `treasury-tic` - Treasury International Capital (TIC)

- **publisher**: U.S. Department of the Treasury
- **base**: https://ticdata.treasury.gov
- **endpoints**: /resource-center/data-chart-center/tic/Documents/slt_table1.txt, /resource-center/data-chart-center/tic/Documents/slt1d_globl.csv, https://home.treasury.gov/data/treasury-international-capital-tic-system-home-page
- **auth**: none - No key. Files are published as text and CSV on ticdata.treasury.gov. Portal: https://home.treasury.gov/data/treasury-international-capital-tic-system-home-page
- **rate limit**: No documented API limit because there is no query API. slt_table1.txt (960,294 bytes) downloaded in 12s.
- **format**: CSV
- **cadence**: monthly
- **coverage**: Foreign holdings of U.S. long-term securities and related TIC banking and securities forms. Probed slt_table1.txt HTTP 200, header 'Table 1: U.S. Long-Term Securities Held by Foreign Residents'. slt1d_globl.csv HTTP 206, header identifies Table 1D in millions of dollars.
- **licence**: U.S. Treasury public statistical release. No separate licence page found; treat as a federal public dataset and cite TIC table and release date.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' https://ticdata.treasury.gov/resource-center/data-chart-center/tic/Documents/slt_table1.txt` -> 200)
- **why**: Who holds Treasury and U.S. long-term securities, by country. That is the cross-border demand fact behind a rates or defence-budget financing paragraph.
- **caveats**: Layout is a spreadsheet dumped to text, with title rows before the header. Units are millions of dollars and the sign convention is in the table note. Filenames are stable only by convention. Major foreign holders and SLT are different tables.

### `world-bank-indicators` - World Bank indicators API

- **publisher**: World Bank
- **base**: https://api.worldbank.org
- **endpoints**: /v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&date=2023, /v2/country/USA/indicator/GC.DOD.TOTL.GD.ZS?format=json&mrv=1, /v2/sources?format=json&per_page=2
- **auth**: none - No key. format=json is required; the default is XML. Docs linked from https://data.worldbank.org/.
- **rate limit**: per_page controls page size. Responses include page and pages. Calls returned in under a second.
- **format**: JSON
- **cadence**: annual
- **coverage**: WDI and other indicator databases. Probed US NY.GDP.MKTP.CD for 2023: HTTP 200, value 27811517000000, lastupdated 2026-07-13. US central-government debt GC.DOD.TOTL.GD.ZS most recent: date 2024, value 115.768352618316. Sources catalog HTTP 200, 71 sources.
- **licence**: World Bank datasets are provided under CC BY 4.0 'with the additional terms' on attribution and dispute terms (https://www.worldbank.org/ext/en/legal/terms-conditions/datasets).
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.worldbank.org/v2/country/US/indicator/NY.GDP.MKTP.CD?format=json&date=2023'` -> 200)
- **why**: Cross-country GDP, debt and external-account comparables when a memo leaves the US. The indicator code is the citation.
- **caveats**: JSON body is a two-element array: paging metadata, then rows. Missing values are null and still count toward total. Country ids are ISO2 in the path. Debt and GDP concepts differ from Treasury and BEA; do not mix them in one sentence without saying so.

## Defence, procurement, geopolitics and sanctions

### `acled-api` - ACLED conflict event API

- **publisher**: Armed Conflict Location and Event Data (ACLED)
- **base**: https://acleddata.com
- **endpoints**: /api/acled/read?limit=1, /oauth/token
- **auth**: free_key - Free myACLED account at https://acleddata.com/user/register. Programmatic access is OAuth password grant against /oauth/token with client_id=acled, scope=authenticated; the access token lasts 24 hours. Docs: https://acleddata.com/api-documentation/getting-started.
- **rate limit**: Not stated on the getting-started page. Access is per account, and the data files are an alternative to paging the API.
- **format**: JSON
- **cadence**: weekly
- **coverage**: Political violence and protest events worldwide, with actors, fatalities, coordinates, and notes, updated far faster than UCDP. Coverage depth varies by country and is listed in ACLED's coverage table.
- **licence**: ACLED terms of use, accepted at registration. Citation of ACLED is required; redistribution of the raw event file is restricted by the terms accepted on the account.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://acleddata.com/api/acled/read?limit=1'` -> 403)
- **why**: For a conflict that is happening this month, UCDP has not published yet. ACLED is the near-real-time event record, and a memo about current fighting should say so and cite it.
- **caveats**: Unauthenticated calls return 403 with body 'Access denied', and the old host api.acleddata.com no longer resolves. The token endpoint expects form-encoded fields, not JSON. Event definitions differ from UCDP, so fatality totals will not match and should not be averaged. Country coverage starts in different years.

### `congress-gov-api` - Congress.gov API

- **publisher**: Library of Congress
- **base**: https://api.congress.gov
- **endpoints**: /v3/bill/118/hr/1?format=json&api_key=DEMO_KEY, /v3/crsreport?limit=1&api_key=DEMO_KEY
- **auth**: free_key - Query parameter api_key. Sign up at https://api.congress.gov/sign-up/ (an api.data.gov key). DEMO_KEY works for a smoke test and is capped at 30 requests per IP per hour.
- **rate limit**: 5,000 requests per hour per key, stated in the Library of Congress README. DEMO_KEY is 30 requests per IP per hour (api.data.gov default). The probe returned X-RateLimit-Limit: 10 on DEMO_KEY, so the shared demo bucket is tighter than the documented key limit.
- **format**: JSON
- **cadence**: daily
- **coverage**: Bills, amendments, members, committees, nominations, treaties, and the Congressional Research Service report corpus. A CRS report object carries authors, summary, topics, and PDF plus HTML links.
- **licence**: US government work. CRS report PDFs are linked from the formats array and are public.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.congress.gov/v3/bill/118/hr/1?format=json&api_key=DEMO_KEY'` -> 200)
- **why**: NDAA text, authorization levels, and the CRS explainer of a programme are the legislative half of a defence-demand number. The bill endpoint gives the action history; the CRS endpoint gives the analyst's summary with a PDF to cite.
- **caveats**: A missing key returns 403 with code API_KEY_MISSING. Default page size is 20 and the maximum is 250; a larger limit is silently cut to 250. CRS report ids look like LSB11484 or R47890. The PDF lives at congress.gov/crs_external_products, not inside the JSON.

### `copernicus-dataspace` - Copernicus Data Space catalogue

- **publisher**: European Space Agency / Copernicus Data Space Ecosystem
- **base**: https://catalogue.dataspace.copernicus.eu
- **endpoints**: /odata/v1/Products?$top=1&$filter=Collection/Name eq 'SENTINEL-1', /stac/collections
- **auth**: none - Catalogue search is open. Downloading the pixels requires a free Copernicus Data Space account and a token; the catalogue itself returned product ids without one.
- **rate limit**: Not stated for the catalogue. A $top=1 query is cheap; counting a whole collection is not, and the SENTINEL-1 count query was slow enough that the follow-up timed out.
- **format**: JSON
- **cadence**: real-time
- **coverage**: The Sentinel catalogue. A filtered count on SENTINEL-1 returned 17,607,960 products. STAC collections and the OData Products entity both answered, so either interface works for discovery.
- **licence**: Copernicus Sentinel data is free, full, and open under EU regulation. Attribution to Copernicus is requested.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://catalogue.dataspace.copernicus.eu/odata/v1/Products?$top=1&$filter=Collection/Name%20eq%20%27SENTINEL-1%27&$select=Name,Id'` -> 200)
- **why**: Sentinel-1 SAR is the open way to check a claimed ship movement, a port closure, or damage to infrastructure regardless of cloud. The catalogue is the machine path to the scene id before any pixel is pulled.
- **caveats**: OData filter syntax is strict and the collection name is case-sensitive ('SENTINEL-1'). The STAC collection list does not use that name, so do not assume the two catalogues share ids. Product download, as opposed to search, needs an account token. Counting without $select is expensive.

### `eda-defence-data` - EDA Defence Data portal

- **publisher**: European Defence Agency
- **base**: https://eda.europa.eu
- **endpoints**: /publications-and-data/defence-data, /publications-and-data/thematic-policy-reports/eda-defence-data-2025-2026
- **auth**: none - No key. The portal renders the annual aggregates as HTML; the thematic-report page offers the full workbook as a download behind a script-rendered button, so no stable file URL was recovered.
- **rate limit**: None observed. The portal page is 339 KB of HTML.
- **format**: bulk download
- **cadence**: annual
- **coverage**: EU member-state defence expenditure, equipment procurement, R&T, and personnel, annually since 2005, with the portal showing the aggregate series through the 2025 edition (EUR 418 billion total for the latest year shown).
- **licence**: European Defence Agency. Data is collected from member states under the 2005 Ministerial Steering Board decision and published for public reuse with attribution.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://eda.europa.eu/publications-and-data/defence-data'` -> 200)
- **why**: European defence-spending comparisons that include procurement share and collaborative spending use EDA's definitions, which neither SIPRI nor NATO publishes at that breakdown.
- **caveats**: The aggregate numbers are in the HTML, but the per-country workbook is behind a rendered download button and a guessed XLSX path 404'd. Scrape the portal for the headline series and fetch the report page for the rest. EDA membership is not the EU plus everyone, and the series starts in 2005. Figures are as reported by ministries and will not match SIPRI.

### `eu-fsd-sanctions` - EU Financial Sanctions Files

- **publisher**: European Commission, Service for Foreign Policy Instruments
- **base**: https://webgate.ec.europa.eu/fsd/fsf
- **endpoints**: /public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw
- **auth**: none - The token query parameter is a published constant (base64 for 'token-2017'), not a registered credential. Omitting it returns 403.
- **rate limit**: None stated. The file is 25.7 MB of XML and is regenerated daily (the probe file carried generationDate 2026-09-22).
- **format**: XML
- **cadence**: daily
- **coverage**: Every person and entity under an EU restrictive-measures regime, with regulation references, aliases, birth dates, and identification. It is the EU counterpart of the OFAC SDN file.
- **licence**: European Commission reuse terms. The file is the official consolidated list of persons, groups, and entities subject to EU financial sanctions.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content?token=dG9rZW4tMjAxNw'` -> 200)
- **why**: A counterparty cleared against OFAC can still be designated in Brussels. EU defence and dual-use work, and any European portfolio company, has to be checked here.
- **caveats**: The token is part of the URL and the request 403s without it; it is not a secret. The XML namespace is http://eu.europa.ec/fpi/fsd/export. Regime membership is per regulation, so a name match has to keep the programme. The file is the financial-sanctions list only; travel bans without an asset freeze can be absent.

### `eu-sanctions-map` - EU Sanctions Map API

- **publisher**: European Commission
- **base**: https://www.sanctionsmap.eu
- **endpoints**: /api/v1/regime
- **auth**: none - No key. The same payload is served at https://sanctionsmap.eu/api/v1/regime.
- **rate limit**: None stated. The regime list is one small JSON document.
- **format**: JSON
- **cadence**: irregular
- **coverage**: 55 restrictive-measures regimes with adoption and amendment dates, the measures imposed, and whether each regime has a designated-person list. It is the index, not the names.
- **licence**: European Commission. The map summarises regimes; the legal authority is the underlying Council decision and regulation, which the FSD file carries.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.sanctionsmap.eu/api/v1/regime'` -> 200)
- **why**: Before screening names, the question is often which regimes exist and when they were last amended. This is the regime index that points into the FSD file.
- **caveats**: It does not list designated persons; that is the FSD file. A regime with has_lists false is a sectoral measure, and citing this endpoint for a name would be wrong. The two hostnames return the same body.

### `federal-register-api` - Federal Register API

- **publisher**: Office of the Federal Register, National Archives and Records Administration
- **base**: https://www.federalregister.gov
- **endpoints**: /api/v1/documents.json?per_page=1&conditions[agencies][]=defense-department, /api/v1/documents.json?per_page=1&conditions[term]=entity+list&conditions[agencies][]=industry-and-security-bureau
- **auth**: none - No key. Agency slugs are lowercase hyphenated names (defense-department, industry-and-security-bureau).
- **rate limit**: Not stated in a response header. The documents endpoint caps a result set at 10,000 documents (50 pages at the default page size) and returns count:10000 once a query passes that.
- **format**: JSON
- **cadence**: daily
- **coverage**: Federal Register notices from 1994, including DoD rules, BIS Entity List additions, and ITAR notices. The DoD-agency query returned the capped 10,000; the BIS 'entity list' query returned 679 documents.
- **licence**: US government work. Document full text is public domain; the API returns metadata plus a body HTML link.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.federalregister.gov/api/v1/documents.json?per_page=1&conditions[agencies][]=defense-department'` -> 200)
- **why**: Entity List additions, ITAR amendments, and DoD rulemaking are published here before they appear in any sanctions dump. A citation to a Federal Register document number is the citable form of a control change.
- **caveats**: count stops at 10000, so a broad agency query silently truncates; narrow by term and date. The HTML reader-aids pages redirect to an unblock interstitial, but the /api/v1 JSON endpoint answered 200 directly. Publication date and the document number are the citation, not the API row id.

### `fpds-ng-atom` - FPDS-NG ATOM feed

- **publisher**: US General Services Administration (Federal Procurement Data System - Next Generation)
- **base**: https://www.fpds.gov
- **endpoints**: /ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC&q=LAST_MOD_DATE:[2026/09/28,2026/09/29]&start=0
- **auth**: none - Public ATOM feed, no key. Query syntax is the FPDS ezSearch language (field:value, date ranges with slashes).
- **rate limit**: Not published. Each response is one page of 10 entries; the next link is in the feed. A one-day window on 2026-09-28 returned a last-page start offset of 30430.
- **format**: XML
- **cadence**: daily
- **coverage**: Every reported US federal award action: new awards, modifications, delivery orders, vendor, contracting agency, NAICS, PSC, and dollars. It is the atom USAspending aggregates.
- **licence**: US federal procurement data. The feed is the public FPDS extract; contract text itself is not in the record.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.fpds.gov/ezsearch/FEEDS/ATOM?FEEDNAME=PUBLIC&q=LAST_MOD_DATE:%5B2026/09/28,2026/09/29%5D&start=0&length=1'` -> 200)
- **why**: When a memo needs the modification history or the exact action (a delivery order, a vendor, a signed date) rather than the rolled-up obligation, FPDS is the record and USAspending is the summary.
- **caveats**: The public feed returns 10 entries per page regardless of a larger length. Page by the start offset in the rel=next link. Date literals use slashes (2026/09/28), not ISO. Department names are stored with abbreviations ('DEPT OF DEFENSE'). The feed carries the action title and dollars, not the statement of work.

### `gdelt-v2` - GDELT 2.0 event files

- **publisher**: GDELT Project
- **base**: http://data.gdeltproject.org
- **endpoints**: /gdeltv2/lastupdate.txt, /gdeltv2/20260929150000.export.CSV.zip
- **auth**: none - No key. lastupdate.txt names the three current 15-minute files (events, mentions, graph). The DOC 2.0 query API is separate and rate-limited.
- **rate limit**: The bulk files have no key and no observed throttle. The DOC API returns 429 with the text 'Please limit requests to one every 5 seconds' and was still returning that on a retry, so prefer the files.
- **format**: CSV
- **cadence**: real-time
- **coverage**: A global event and mention stream every 15 minutes since 2015, coded to CAMEO event types with actor and location fields. The 15:00 UTC file on 2026-09-29 was 98 KB zipped.
- **licence**: GDELT is published for open research use. The event files are derived from news monitoring, so the citation is GDELT plus the underlying article URL carried in the mentions file.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'http://data.gdeltproject.org/gdeltv2/lastupdate.txt'` -> 200)
- **why**: GDELT is the widest net for 'what is being reported where right now'. It is a lead generator for a defence or sanctions note, not a number to print without opening the underlying article.
- **caveats**: The files are tab-separated CSV inside a zip and use GDELT's own column positions, which are not in a header row. The DOC API path /api/v2/doc/doc returned 429 on two separate attempts, so do not build on it. Event coding is automated and noisy; never cite a GDELT count as a fatality count. The host is http, and the file names are timestamps.

### `govinfo-api` - GovInfo API

- **publisher**: US Government Publishing Office
- **base**: https://api.govinfo.gov
- **endpoints**: /collections?api_key=DEMO_KEY, /collections/GAOREPORTS/2025-01-01T00:00:00Z?offset=0&pageSize=2&api_key=DEMO_KEY, /collections/BUDGET
- **auth**: free_key - Query parameter api_key. Sign up at https://www.govinfo.gov/api-signup (api.data.gov key, same key family as Congress.gov).
- **rate limit**: api.data.gov default of 1,000 requests per hour per key. DEMO_KEY is 30 per IP per hour. A second collection call in the same burst returned 429 OVER_RATE_LIMIT.
- **format**: JSON
- **cadence**: daily
- **coverage**: GPO collections including GAOREPORTS (16,569 packages modified since 2025-01-01 in the probe), BUDGET (President's Budget and agency appendices), FR, BILLSTATUS, PLAW, and USCODE. This is the machine path to GAO reports and DoD budget justification books when defense.gov blocks the client.
- **licence**: US government work. Package granules link to PDF and XML in the GovInfo bulk repository.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.govinfo.gov/collections/GAOREPORTS/2025-01-01T00:00:00Z?offset=0&pageSize=1&api_key=DEMO_KEY'` -> 200)
- **why**: GAO findings and the President's Budget are the two documents a defence-demand memo cites for 'what was requested' and 'what an auditor found'. Both are collections here, with package ids that survive a URL change.
- **caveats**: The lastModified bound must be ISO-8601 with a trailing Z (yyyy-MM-dd'T'HH:mm:ss'Z'); a date alone returns 400. A window can return count 0 even when the collection is healthy, so page backward. DEMO_KEY trips 429 within a handful of calls. Package summaries are a second request per hit.

### `nasa-firms` - NASA FIRMS active-fire API

- **publisher**: NASA LANCE / FIRMS
- **base**: https://firms.modaps.eosdis.nasa.gov
- **endpoints**: /api/area/csv/{MAP_KEY}/VIIRS_SNPP_NRT/world/1, /api/map_key/
- **auth**: free_key - A MAP_KEY is emailed after a free signup at https://firms.modaps.eosdis.nasa.gov/api/map_key/. The key is a path segment, not a header.
- **rate limit**: 5,000 transactions per 10-minute window per key, stated on the map-key page. A request spanning more days counts as more than one transaction. Area requests are limited to a day range of 1 to 5.
- **format**: CSV
- **cadence**: real-time
- **coverage**: Active fire and thermal detections from MODIS and VIIRS, globally, in near real time, with latitude, longitude, brightness, and confidence. The API service page reports version 4.1.16.
- **licence**: NASA open data. Cite FIRMS and the sensor (VIIRS S-NPP or MODIS). Near-real-time detections are not a fire-cause judgement.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://firms.modaps.eosdis.nasa.gov/api/area/csv/MAP_KEY/VIIRS_SNPP_NRT/world/1'` -> 400)
- **why**: Thermal detections are the open-source way to corroborate a claimed strike on fuel storage, a refinery fire, or front-line burning when no imagery analyst is available. The confidence field is the part worth quoting.
- **caveats**: A missing or placeholder key returns 400 'Invalid MAP_KEY.' The countries endpoint is marked 'currently not available' on the service page. Detections are hotspots, not events: gas flares, industry, and volcanoes all appear. Confidence and the day/night flag belong in any citation.

### `nato-defence-expenditure` - NATO defence expenditure tables

- **publisher**: North Atlantic Treaty Organization
- **base**: https://www.nato.int
- **endpoints**: /content/dam/nato/webready/documents/finance/def-exp-2026-en.pdf, /cps/en/natohq/topics_49198.htm
- **auth**: none - No key. The topic page lists one PDF per release back to 2001. The current file is the June 2026 communique tables.
- **rate limit**: None. The 2026 PDF is 10.2 MB.
- **format**: bulk download
- **cadence**: annual
- **coverage**: Defence expenditure by NATO ally in current and constant prices, share of GDP, equipment share, and real change, with the 2026 release covering estimates through 2026. The topic page links the full back series of communiques.
- **licence**: NATO public communique. Figures may be quoted with attribution to the NATO press release; the tables are the official allied definition of defence expenditure, which differs from SIPRI's.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.nato.int/content/dam/nato/webready/documents/finance/def-exp-2026-en.pdf'` -> 200)
- **why**: The 2 percent and 5 percent pledges are defined on NATO's own tables, not on SIPRI. A memo about burden-sharing has to cite this PDF, and the two series disagree by enough to matter.
- **caveats**: The PDF is a typeset communique, so numbers have to be extracted from tables rather than parsed as data. NATO revises prior-year estimates in each release. The GDP definition and the inclusion of pensions differ from SIPRI, so do not average the two.

### `noaa-marinecadastre-ais` - NOAA Marine Cadastre AIS archives

- **publisher**: US National Oceanic and Atmospheric Administration and US Coast Guard
- **base**: https://coast.noaa.gov
- **endpoints**: /htdata/CMSP/AISDataHandler/2024/, /htdata/CMSP/AISDataHandler/2023/AIS_2023_01_01.zip
- **auth**: none - No key. Daily zip files are listed in the year directory. The portal front door is https://marinecadastre.gov/ais/.
- **rate limit**: None stated. Each day is one zip; the 2023-01-01 file is 319 MB, so pull days, not years.
- **format**: CSV
- **cadence**: annual
- **coverage**: Vessel AIS positions for US coastal and inland waters, one CSV per day, with MMSI, timestamp, latitude, longitude, speed, and vessel type. The 2024 directory lists all 366 daily files; 2023 was confirmed by downloading the first bytes of a zip.
- **licence**: US government work. NOAA asks users to cite Marine Cadastre. The records are historical, not a live feed.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/'` -> 200)
- **why**: Historical vessel movements in US waters, including tankers and government vessels, are citable from here without a MarineTraffic subscription. It is the record for sanctions-evasion and port-call questions after the fact.
- **caveats**: US waters only, and the release lags by months, so it is not a live picture. A single day is about 300 MB compressed. MMSI is not a stable identity; vessels change it. The 2024 files exist as a directory listing; the 2023 file was the one whose bytes were checked.

### `ofac-sdn-list` - OFAC Specially Designated Nationals list

- **publisher**: US Department of the Treasury, Office of Foreign Assets Control
- **base**: https://sanctionslistservice.ofac.treas.gov
- **endpoints**: /api/PublicationPreview/exports/SDN.XML, /api/PublicationPreview/exports/SDN_ADVANCED.XML, /api/PublicationPreview/exports/CONS_ENHANCED.XML
- **auth**: none - No key. The Sanctions List Service redirects to a published S3 object; the stable URL is the PublicationPreview path. The legacy mirror https://www.treasury.gov/ofac/downloads/sdn.xml and sdn.csv also return 200.
- **rate limit**: No throttle observed. SDN.XML is 29 MB, SDN_ADVANCED.XML is 127 MB, so fetch and cache rather than poll.
- **format**: XML
- **cadence**: irregular
- **coverage**: The SDN list and the consolidated non-SDN sanctions lists (SSI, FSE, NS-PLC, and the rest), with programmes, aliases, addresses, and identification numbers. The advanced XML carries the structured identity model.
- **licence**: US government sanctions data, published for screening. OFAC's FAQ requires users to keep their own copy current; the list is not a safe harbour if stale.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.XML'` -> 200)
- **why**: This is the US answer to 'is this counterparty sanctioned'. A defence or investment memo that names a foreign supplier, a bank, or an owner has to clear it against this file, not against a news summary.
- **caveats**: There is no delta endpoint that answered; /api/Changes returned 404, so change detection means hashing the file. The advanced XML is 127 MB and will time out a client that buffers the body. Aliases and alternate spellings live in separate elements, so a name match against the primary name alone misses them. The consolidated list is a different file from the SDN list.

### `opensky-network` - OpenSky Network API

- **publisher**: OpenSky Network association
- **base**: https://opensky-network.org
- **endpoints**: /api/states/all, /api/states/all?lamin=50&lomin=3&lamax=51&lomax=4
- **auth**: none - Anonymous access works for the live state vectors. A free OpenSky account raises the credit quota and unlocks the last hour of states; historical flights beyond that need the approved research grant. Docs: https://openskynetwork.github.io/opensky-api/rest.html.
- **rate limit**: Credits per endpoint family. Anonymous is 400 credits per day for states, with a 10-second resolution and no history. A standard account gets 4,000 per day and 1 hour of history. The bounding box cuts the payload from 1.7 MB to a few KB.
- **format**: JSON
- **cadence**: real-time
- **coverage**: Live ADS-B state vectors worldwide: ICAO24 hex, callsign, country, position, altitude, and velocity. Coverage is densest where receivers exist and thin over oceans and conflict airspace where transponders are off.
- **licence**: OpenSky terms of use. Live state vectors are crowd-sourced ADS-B and may be used with attribution; the historical database has its own access policy.
- **cost**: free for live states; historical flights require a free account and, past one hour, an approved research role
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://opensky-network.org/api/states/all?lamin=50&lomin=3&lamax=51&lomax=4'` -> 200)
- **why**: It is the open way to check whether civil traffic is still flying a corridor, or whether a specific transponder was airborne, without a paid flight tracker. Military traffic that goes dark will not appear, and that absence is itself the finding.
- **caveats**: Anonymous calls ignore the time parameter. /api/flights/aircraft returned 403 'You cannot access historical flights' without an account. State vectors are an array of positional fields with no keys, so use the documented order. ADS-B is line-of-sight and voluntary; military aircraft are systematically missing.

### `sam-gov-entity-exclusions` - SAM.gov Entity and Exclusions API

- **publisher**: US General Services Administration
- **base**: https://api.sam.gov
- **endpoints**: /entity-information/v3/entities, /entity-information/v4/exclusions
- **auth**: free_key - Query parameter api_key from a SAM.gov Account Details page. Public registration and exclusion records need a non-federal personal key. Docs: https://open.gsa.gov/api/entity-api/ and https://open.gsa.gov/api/exclusions-api/
- **rate limit**: Same SAM role table: 10 requests/day with no role, 1,000/day for a non-federal user with a role. Entity search page size cannot exceed 10 records per call; UEI and CAGE batches are capped at 100.
- **format**: JSON
- **cadence**: daily
- **coverage**: SAM registrations (UEI, legal name, NAICS, address, status) and the exclusions list: debarments, suspensions, and proposed debarments.
- **licence**: US federal entity registration and exclusion data. Sensitive and FOUO sections require a federal system account and are not part of the public key.
- **cost**: free
- **verified**: False (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.sam.gov/entity-information/v3/entities?samRegistered=Yes'` -> 404)
- **why**: Before naming a company as a prime or a supplier, the registration and the exclusions list say whether it can legally receive a federal award. That is the counterparty check investment memos skip.
- **caveats**: Both probed URLs returned HTTP 404 with an empty body and no error JSON, including /entity-information/v4/exclusions?exclusionName=LOCKHEED. The documentation pages at open.gsa.gov returned 200 and describe the paths, so the contract is real and the unkeyed call is not a useful error. Do not treat 404 as 'no such entity'. Public key never returns the sensitive responsibility-and-integrity section.

### `sam-gov-opportunities` - SAM.gov Get Opportunities API

- **publisher**: US General Services Administration
- **base**: https://api.sam.gov
- **endpoints**: /opportunities/v2/search?limit=1&postedFrom=09/01/2026&postedTo=09/02/2026&api_key=
- **auth**: free_key - Query parameter api_key. Register a SAM.gov account and generate the key on the Account Details page. Docs: https://open.gsa.gov/api/get-opportunities-public-api/
- **rate limit**: Daily cap by role, stated on the Entity API docs at the same portal and applied across SAM public APIs: non-federal personal account with no role, 10 requests/day; non-federal with a role, 1,000/day; federal user, 1,000/day. Page size must be 0-1000.
- **format**: JSON
- **cadence**: daily
- **coverage**: Active federal contract opportunities (solicitations, presolicitations, sources sought, awards, special notices), updated daily; archived notices refreshed weekly.
- **licence**: US federal notice data. The API returns the active version of each notice; attachments are linked, not inlined.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.sam.gov/opportunities/v2/search?limit=1&postedFrom=09/01/2026&postedTo=09/02/2026'` -> 400)
- **why**: This is the forward book: what DoD and civilian agencies are about to buy, before an award exists in FPDS or USAspending. A defence-demand note that only reads awards is looking backwards.
- **caveats**: A missing api_key returns HTTP 400 with 'Required parameter api_key is not present', not 401. Dates are mm/dd/yyyy. postedFrom and postedTo are required once limit is set, and the window cannot exceed one year. The endpoint returns only the latest active version of a notice. The alpha host is api-alpha.sam.gov.

### `sipri-arms-transfers` - SIPRI Arms Transfers Database

- **publisher**: Stockholm International Peace Research Institute
- **base**: https://armstransfers.sipri.org
- **endpoints**: /ArmsTransfer/, https://www.sipri.org/databases/armstransfers
- **auth**: none - No key. The query UI is a web application at armstransfers.sipri.org; the Trade Registers generate a downloadable file per query. There is no documented unauthenticated bulk endpoint.
- **rate limit**: Not published. A GET on /ArmsTransfer/CSVResult returns the app shell (405 bytes of HTML), not a data file, so the download is produced by the query tool rather than a stable URL.
- **format**: bulk download
- **cadence**: annual
- **coverage**: Major conventional arms transfers from 1950, supplier, recipient, weapon designation, numbers ordered and delivered, and SIPRI trend-indicator values. It is the standard source for who sold what to whom.
- **licence**: Same SIPRI terms as the milex database: non-commercial use under 10 percent of the data set, commercial use requires a licence. https://www.sipri.org/about/terms-and-conditions.
- **cost**: free for non-commercial research use; commercial reuse needs a licence
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://armstransfers.sipri.org/ArmsTransfer/CSVResult'` -> 200)
- **why**: A claim that a country is arming another country needs the SIPRI register, not a press roundup. Trend-indicator values are the comparable unit across weapon types.
- **caveats**: The probed URL returns the application shell, not rows. Treat it as a verified entry point, then run the query inside the tool and save the export. Trend-indicator values are SIPRI's own unit and are not dollars. Delivery years and order years are different columns. The same fair-use cap as milex applies.

### `sipri-milex` - SIPRI Military Expenditure Database

- **publisher**: Stockholm International Peace Research Institute
- **base**: https://www.sipri.org
- **endpoints**: /sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx, /databases/milex
- **auth**: none - Direct XLSX download, no key. The current filename is versioned and is linked from https://www.sipri.org/databases/milex.
- **rate limit**: None. The workbook is 923 KB.
- **format**: bulk download
- **cadence**: annual
- **coverage**: Military spending for nearly every country, 1949-2025, in local currency, current and constant USD, share of GDP, and per capita. The file on the wire was revised 27 April 2026 (v1.2) and replaces earlier versions.
- **licence**: SIPRI fair use: non-commercial excerpting of less than 10 percent of a data set, both conditions required. 'Commercial use of SIPRI data must be authorized and licensed.' Stated at https://www.sipri.org/about/terms-and-conditions.
- **cost**: free for non-commercial research use; commercial reuse needs a licence
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://www.sipri.org/sites/default/files/SIPRI-Milex-data-1949-2025_v1.2.xlsx'` -> 200)
- **why**: Country defence-spending time series in a memo should come from this workbook, not from a news summary of it. It is the dataset the World Bank's own milex indicator cites as its source.
- **caveats**: The filename carries a version suffix that changes (v1.2 as probed). Financial-year and calendar-year sheets differ, and constant-dollar figures use a stated base year (2024 in this release). SIPRI revises history, so pin the filename and the revision date in the citation. Fair-use cap of 10 percent of the data set binds redistribution.

### `trade-gov-csl` - Consolidated Screening List

- **publisher**: International Trade Administration, US Department of Commerce
- **base**: https://data.trade.gov
- **endpoints**: /downloadable_consolidated_screening_list/v1/consolidated.csv, /downloadable_consolidated_screening_list/v1/consolidated.json
- **auth**: none - The bulk CSV, TSV, and JSON files need no key. The search API at data.trade.gov/consolidated_screening_list/v1/search requires a subscription key from https://developer.trade.gov and returned 401 without one. The API host api.trade.gov presents an expired TLS certificate.
- **rate limit**: None stated for the bulk file. The file is 16.8 MB of CSV, so download once a day rather than per name.
- **format**: CSV
- **cadence**: daily
- **coverage**: One flat file joining the BIS Entity List, Denied Persons List, Unverified List, Military End User list, OFAC SDN and non-SDN lists, and State Department debarments. Columns include source, name, programmes, addresses, federal register notice, and license requirement.
- **licence**: US government compilation of screening lists. ITA publishes it for export-control screening; the underlying lists keep their own agency authority.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://data.trade.gov/downloadable_consolidated_screening_list/v1/consolidated.csv'` -> 200)
- **why**: The BIS Entity List has no clean bulk file of its own (the old bis.doc.gov supplement path now returns an HTML page). This CSV is the machine-readable Entity List, plus the other US denied-party lists, in one schema.
- **caveats**: The search API is a different product and wants a key; do not assume the CSV's host serves the search. api.trade.gov fails TLS verification (certificate expired), so stay on data.trade.gov. The source column is the authority (EL, SDN, DPL); a hit is not an OFAC designation unless source says so. Names are not deduplicated across lists.

### `ucdp-ged` - UCDP Georeferenced Event Dataset

- **publisher**: Uppsala Conflict Data Program, Department of Peace and Conflict Research, Uppsala University
- **base**: https://ucdp.uu.se
- **endpoints**: /downloads/ged/ged261-csv.zip, https://ucdpapi.pcr.uu.se/api/gedevents/26.1?pagesize=1
- **auth**: none - The versioned CSV zip needs no key. The API needs a free token in the header x-ucdp-access-token, requested by email to mertcan.yilmaz@pcr.uu.se with a short project description. Docs: https://ucdp.uu.se/apidocs/
- **rate limit**: API: 5,000 requests per day, errors included. The bulk CSV has no limit; the v26.1 zip is 39 MB.
- **format**: CSV
- **cadence**: annual
- **coverage**: Organized-violence events with date, location, actors, and fatalities, versioned. v26.1 is the current release and the zip downloaded cleanly; the candidate versions and the dyadic conflict file are separate downloads.
- **licence**: UCDP data is free for research with citation of the dataset version. The API docs state it is free of charge and that each versioned URL returns the same data permanently.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://ucdp.uu.se/downloads/ged/ged261-csv.zip'` -> 200)
- **why**: Fatality and event counts in a conflict memo should cite a UCDP version, because the version is frozen and the definition of an event is published. It is the audited counterpart to the real-time feeds.
- **caveats**: The API without a token returns 401 'API token required'. Versions are not interchangeable: v24.1 and v26.1 both exist and counts change between them, so cite the version. pagesize and page paginate the API; filtering past the last page errors rather than returning empty. The bulk file is the better pull for a full year.

### `un-comtrade-preview` - UN Comtrade preview API

- **publisher**: United Nations Statistics Division
- **base**: https://comtradeapi.un.org
- **endpoints**: /public/v1/preview/C/A/HS?reporterCode=842&period=2024&partnerCode=156&cmdCode=9301&flowCode=X
- **auth**: none - The preview path is public. A subscription key for the full delivery API is issued from a free UN Comtrade account; key setup is documented at https://uncomtrade.org/docs/api-subscription-keys/.
- **rate limit**: Preview calls are throttled: the docs quote the error 'Rate limit is exceeded. Try again in 1 second.' Preview returns at most 500 records per query. The full extract is the bulk-file or async delivery product.
- **format**: JSON
- **cadence**: annual
- **coverage**: Merchandise trade by reporter, partner, year, and HS code. HS chapter 93 is arms and ammunition. The probed row was USA exports to China of HS 9301 in 2024: primary value 2,981 USD, quantity 2, net weight 10.625 kg.
- **licence**: UN Comtrade terms of use. Attribution to UN Comtrade is required; redistribution of a substantial extract should go through the cited bulk file rather than repeated preview calls.
- **cost**: free for preview (500-record cap); bulk delivery needs a free account and subscription key
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=842&period=2024&partnerCode=156&cmdCode=9301&flowCode=X'` -> 200)
- **why**: Reported arms and ammunition trade in dollars and kilograms, by reporter and partner, is the customs counterpart to SIPRI's weapon counts. A memo that quotes an arms-export value should come from here.
- **caveats**: Preview description fields (reporterDesc, cmdDesc) came back null on the 2024 row, so resolve codes locally. HS 93 is customs classification, not SIPRI major arms, and the two will not reconcile. Reporter and partner figures are asymmetric. primaryValue is USD. The preview is not the whole result set.

### `un-sc-consolidated-list` - UN Security Council consolidated sanctions list

- **publisher**: United Nations Security Council
- **base**: https://scsanctions.un.org
- **endpoints**: /resources/xml/en/consolidated.xml
- **auth**: none - No key. The human page is https://main.un.org/securitycouncil/en/content/un-sc-consolidated-list.
- **rate limit**: None stated. The XML is 2.2 MB.
- **format**: XML
- **cadence**: irregular
- **coverage**: All active UN sanctions regimes (ISIL/Al-Qaida, Taliban, DPRK, Iran, and the country regimes), individuals and entities, with aliases and listing dates.
- **licence**: United Nations. The list is the consolidated roster of individuals and entities designated by Security Council sanctions committees.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://scsanctions.un.org/resources/xml/en/consolidated.xml'` -> 200)
- **why**: UN listings are the baseline most other regimes incorporate. A screening that checks OFAC and the EU and skips the UN list will miss designations that have not yet been transcribed.
- **caveats**: The file is consolidated across committees, so the committee element is the regime and has to be kept. Listing does not equal an asset freeze in every member state until that state implements it. Updates are irregular; record the file date.

### `usaspending-api` - USAspending API

- **publisher**: US Department of the Treasury, Bureau of the Fiscal Service
- **base**: https://api.usaspending.gov
- **endpoints**: /api/v2/search/spending_by_award/, /api/v2/references/toptier_agencies/
- **auth**: none - No key. POST JSON to the search endpoints. Already wrapped by the operator's usaspending_prime_census skill; included so the merged skill still lists the authoritative endpoint.
- **rate limit**: No rate-limit header returned on the probe. The documented trap is semantic, not a throttle: award-type codes and subaward rows must be filtered explicitly or counts double.
- **format**: JSON
- **cadence**: daily
- **coverage**: US federal awards and subawards from FY2008, contract and assistance types, recipient, agency, place of performance, and obligation amounts.
- **licence**: US federal public data, no reuse restriction stated on the API. Cite the award id back to the record.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Content-Type: application/json' -d '{"filters":{"time_period":[{"start_date":"2026-09-01","end_date":"2026-09-02"}],"award_type_codes":["A"]},"fields":["Award ID","Recipient Name","Award Amount"],"limit":1,"page":1}' https://api.usaspending.gov/api/v2/search/spending_by_award/` -> 200)
- **why**: This is the queryable record of who the US government paid, for how much, and under which award id. Defence-demand work that names a prime or a contract value has to land here.
- **caveats**: ALREADY COVERED by usaspending_prime_census. TOTAL_RETAIL-style quantity fields do not exist here; amounts are obligations in dollars. Award-type codes A/B/C/D are contracts and exclude assistance unless asked for. Pagination is page/limit, and a missing time filter scans the whole corpus. Subawards are a separate endpoint and must not be added to prime counts.

### `usgs-earthquake-fdsn` - USGS earthquake catalogue (FDSN)

- **publisher**: US Geological Survey
- **base**: https://earthquake.usgs.gov
- **endpoints**: /fdsnws/event/1/query?format=geojson&limit=1&minmagnitude=5
- **auth**: none - No key. Standard FDSN event parameters: starttime, endtime, minmagnitude, bounding box, format=geojson or csv.
- **rate limit**: None stated. Keep limit set; an unbounded global query is large.
- **format**: JSON
- **cadence**: real-time
- **coverage**: Global earthquakes with magnitude, depth, place, and time. Reviewed solutions replace automatic ones. The probe returned a magnitude-5-plus event as GeoJSON.
- **licence**: US government work. The catalogue cites the contributing network in each feature's properties.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://earthquake.usgs.gov/fdsnws/event/1/query?format=geojson&limit=1&minmagnitude=5'` -> 200)
- **why**: A reported explosion near a test site or a front line is often an earthquake. This catalogue is the first check, and it gives a magnitude, a depth, and a reviewed-status flag to cite.
- **caveats**: Automatic solutions are revised, so store the event id and re-query before publishing a number. format=geojson and format=csv return different shapes. The limit parameter is essential; the default page is large.

### `worldbank-milex-indicator` - World Bank military-expenditure indicator

- **publisher**: World Bank (series compiled by SIPRI)
- **base**: https://api.worldbank.org
- **endpoints**: /v2/country/all/indicator/MS.MIL.XPND.CD?format=json&mrv=1&per_page=2, /v2/indicator/MS.MIL.XPND.CD?format=json
- **auth**: none - No key. format=json is required; the default is XML. Page with per_page and page.
- **rate limit**: None stated and none observed. The API is designed for bulk pulls of one indicator across all countries.
- **format**: JSON
- **cadence**: annual
- **coverage**: MS.MIL.XPND.CD is military expenditure in current USD and MS.MIL.XPND.GD.ZS is the GDP share, for all countries, most-recent value dated as updated 2026-07-13. It is a convenience cut of SIPRI, not an independent estimate.
- **licence**: World Bank terms; the sourceOrganization field credits 'SIPRI Military Expenditure Database'. Redistributing the series is fine; it does not relax SIPRI's own terms on the full workbook.
- **cost**: free
- **verified**: True (`curl -s -o /dev/null -w '%{http_code}' -A 'prime-agent research contact:faisalnazer2@gmail.com' 'https://api.worldbank.org/v2/country/USA/indicator/MS.MIL.XPND.GD.ZS?format=json&per_page=1&mrv=1'` -> 200)
- **why**: For a quick, machine-readable GDP-share figure across every country, this is the one call. The citation still belongs to SIPRI, and the full workbook wins wherever the two differ.
- **caveats**: The response is a two-element array: metadata, then rows. sourceOrganization says SIPRI, so do not cite it as World Bank analysis. It lags the SIPRI workbook (workbook revised April 2026, indicator updated July 2026, but the indicator is a subset). Null rows are common for countries SIPRI does not estimate.

## Health, clinical and pharmaceutical

### `biorxiv-medrxiv-api` - bioRxiv / medRxiv API (preprints)

- **publisher**: Cold Spring Harbor Laboratory (bioRxiv/medRxiv)
- **base**: https://api.biorxiv.org
- **endpoints**: /details/medrxiv/2024-01-01/2024-01-02/0, /details/biorxiv/{from}/{to}/{cursor}, /pubs/medrxiv/{doi}
- **auth**: none - No key required.
- **rate limit**: Not published; one 67 KB interval response in 1.1 s. Interval queries are cursor-paged by the trailing integer.
- **format**: JSON
- **cadence**: daily
- **coverage**: Every posted bioRxiv and medRxiv preprint with DOI, title, authors, category, posted date and published-journal mapping.
- **licence**: Per-preprint licence chosen by the author, typically CC BY, CC BY-NC or CC0 (biorxiv.org/about/FAQ). Check the individual preprint before republishing figures or text.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.biorxiv.org/details/medrxiv/2024-01-01/2024-01-02/0'` -> 200)
- **why**: Earliest public evidence of a clinical result: preprints move before journals, and the /pubs endpoint links a preprint to its final publication, which is exactly the audit trail an evidence table needs.
- **caveats**: Preprints are not peer reviewed - any number from them must be labelled as such. The interval endpoint returns at most 100 records per call, so a wide date range needs cursor iteration.

### `cdc-data-socrata` - CDC open data portal (Socrata) - NNDSS, PLACES, BRFSS and more

- **publisher**: U.S. Centers for Disease Control and Prevention (CDC)
- **base**: https://data.cdc.gov
- **endpoints**: /api/views.json?limit=N, /resource/{datasetId}.json?$limit=N, /api/catalog/v1?limit=N
- **auth**: none - No key for modest use; a free Socrata app token raises throttling limits (register at data.cdc.gov/profile/app_tokens).
- **rate limit**: Without a token Socrata throttles by IP and can return a short-term block; measured 1-2 s per call. Add an X-App-Token header for repeat work.
- **format**: JSON, CSV, XLSX via /resource/{id}.{ext}
- **cadence**: daily to annual by dataset
- **coverage**: Thousands of CDC datasets: NNDSS weekly notifiable disease tables, PLACES local estimates, BRFSS, vaccination coverage, environmental and occupational series.
- **licence**: US government work, public domain (17 U.S.C. 105). Some CDC datasets carry their own statement in the dataset description.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://data.cdc.gov/api/views.json?limit=2'` -> 200)
- **why**: Weekly notifiable-disease counts and local prevalence estimates with a stable dataset ID and a $where query language, so a rate can be rebuilt by anyone who re-runs the URL.
- **caveats**: The /api/catalog/v1 search endpoint is federated across data.gov and will return unrelated datasets (my probe's first hit was 'Dallas Police Active Calls'), so pin the dataset ID rather than trusting search order. Socrata $limit defaults to 1,000 rows - paginate with $offset.

### `cdc-wonder-api` - CDC WONDER API for Data Query (mortality and natality detail)

- **publisher**: U.S. Centers for Disease Control and Prevention (CDC/NCHS)
- **base**: https://wonder.cdc.gov/controller/datarequest
- **endpoints**: /datarequest/D76 (provisional mortality), /datarequest/D48 (underlying cause of death, 1999-2020), Docs: https://wonder.cdc.gov/wonder/help/wonder-api.html
- **auth**: none - No key required.
- **rate limit**: Published as 'the API allows a limited number of requests'; heavy scripted use is blocked. The web UI's own rate behaviour applies.
- **format**: XML (request and response)
- **cadence**: annual to monthly by database (D76 updates with provisional mortality data)
- **coverage**: Detailed mortality and natality microdata cross-tabulations: cause, age, sex, race, county and year, suppressed below CDC's small-count threshold.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: False (`curl -s --compressed -m 40 -A 'prime-agent research contact:faisalnazer2@gmail.com' -X POST --data-urlencode 'request_xml=<request-parameters><parameter><name>B_1</name><value>D76.V9-level2</value></parameter><parameter><name>M_1</name><value>D76.M1</value></parameter><parameter><name>O_location</name><value>D76.V9</value></parameter></request-parameters>' -o /dev/null -w '%{http_code}' 'https://wonder.cdc.gov/controller/datarequest/D76'` -> 500)
- **why**: The only public route to detailed US mortality cross-tabs (cause x county x age x year), which is the denominator side of disease-burden and risk work.
- **caveats**: UNVERIFIED BY ME: the API doc page returns 200 (https://wonder.cdc.gov/wonder/help/wonder-api.html) and my POST to /controller/datarequest/D76 reached the live query engine, which answered HTTP 500 with its own XML validation text naming my parameters ('Selections were made to location variable D76.V9'), so the endpoint is live and parsing - but my request body was incomplete and I did not obtain a 200 dataset. A full <request-parameters> XML per database is required; the R package socdatar/wonderapi shows working bodies.

### `chembl-api` - ChEMBL API (bioactivity, targets and mechanisms)

- **publisher**: European Bioinformatics Institute (EMBL-EBI), ChEMBL team
- **base**: https://www.ebi.ac.uk/chembl/api/data
- **endpoints**: /molecule/CHEMBL25.json, /activity.json?limit=1, /mechanism.json?molecule_chembl_id=CHEMBL25
- **auth**: none - No key required.
- **rate limit**: Not published; measured 0.6-0.9 s per call. Bulk PostgreSQL/CSV dumps are offered for heavy use.
- **format**: JSON, XML and bulk CSV
- **cadence**: quarterly (ChEMBL releases)
- **coverage**: ~2.4 M compounds and ~20 M activity measurements with targets, assays and mechanisms of action.
- **licence**: 'The ChEMBL data is made available on a Creative Commons Attribution-Share Alike 3.0 Unported License' (chembl.gitbook.io/chembl-interface-documentation/about). Share-alike applies to redistributed derived datasets.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL25.json'` -> 200)
- **why**: Mechanism and potency evidence for a pipeline thesis: target, assay type, measured value and the paper it came from, all with stable ChEMBL IDs.
- **caveats**: Assays are heterogeneous: potency values are not comparable across assay types and must carry their assay ID and units. The CC BY-SA share-alike term is a real constraint if a derived dataset is republished.

### `clinicaltrials-gov-api-v2` - ClinicalTrials.gov API v2 (trial register + posted results)

- **publisher**: U.S. National Library of Medicine (NLM)
- **base**: https://clinicaltrials.gov/api/v2
- **endpoints**: /studies?query.cond={condition}&pageSize=N, /studies/{nctId}, /stats/size
- **auth**: none - No key. NLM asks for a descriptive User-Agent; probes used contact:faisalnazer2@gmail.com.
- **rate limit**: No published hard limit; 50 requests/min is the commonly cited polite ceiling. Measured 0.7 s for one /studies page.
- **format**: JSON
- **cadence**: daily (records updated continuously)
- **coverage**: 604,950 studies as measured on 2026-09-29 at /stats/size, 1999-present, including FDAAA-posted results.
- **licence**: US federal government work; public domain in the US (17 U.S.C. 105). Terms page probed 200 with no reuse restriction stated.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://clinicaltrials.gov/api/v2/studies?query.cond=melanoma&pageSize=1'` -> 200)
- **why**: The canonical register for every trial number, phase, endpoint, enrolment and sponsor a clinical or pharma memo cites. Endpoint and eligibility text is machine-readable, so a model can be built from it without scraping.
- **caveats**: v1 (/api/query) is retired; use /api/v2. Pagination is pageToken-based, there is no bulk download. Results sections exist only for FDAAA-reportable trials, so absence of results is not absence of data.

### `cms-asp-pricing-files` - Medicare Part B Average Sales Price (ASP) pricing files

- **publisher**: U.S. Centers for Medicare & Medicaid Services (CMS)
- **base**: https://www.cms.gov
- **endpoints**: /files/zip/{month}-{year}-asp-pricing-file.zip, /medicare/payment/part-b-drugs/asp-pricing-files (index page)
- **auth**: none - No key required. Files are direct ZIP downloads linked from the index page.
- **rate limit**: Static file host; no documented limit. One 78,738-byte ZIP in 1.0 s.
- **format**: bulk download (ZIP of TXT/CSV)
- **cadence**: quarterly
- **coverage**: Quarterly ASP payment limits, NOC prices and NDC/HCPCS crosswalks for Part B drugs, by HCPCS code and billing unit, back to at least 2020.
- **licence**: US government work, public domain (17 U.S.C. 105); the FDA analogue states the same policy ('not copyrighted ... in the public domain', fda.gov/about-fda/about-website/website-policies).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.cms.gov/files/zip/july-2025-asp-pricing-file.zip'` -> 200)
- **why**: A regulated US price series per drug, published quarterly with a legal basis - the anchor for price-per-unit modelling and for comparing a company's realised US price against an administratively set one.
- **caveats**: The index page lists files by quarter with inconsistent name formats, and some legacy links route through /license/ama?file=... (AMA terms on a few code-related files). The newest ASP file lags the index page: my probe of the July 2025 file returned 200 while the newest seasonal-vaccine files were already 2026. Prices are payment limits, not transaction prices.

### `cms-open-payments` - CMS Open Payments (industry payments to physicians and teaching hospitals)

- **publisher**: U.S. Centers for Medicare & Medicaid Services (CMS)
- **base**: https://openpaymentsdata.cms.gov/api/1
- **endpoints**: /metastore/schemas/dataset/items?limit=N, /datastore/query/{datasetId}/0?limit=N
- **auth**: none - No key required.
- **rate limit**: Not published; measured 0.8 s.
- **format**: JSON, CSV
- **cadence**: annual (with a mid-year refresh)
- **coverage**: Every reported transfer of value from drug and device manufacturers to physicians, teaching hospitals and (since 2022) physician-owned entities, with amounts, nature and the related product.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://openpaymentsdata.cms.gov/api/1/metastore/schemas/dataset/items?limit=1'` -> 200)
- **why**: Conflict-of-interest evidence for an investment or clinical memo: named key opinion leaders, speaker fees and consulting flows by company and product, each a dated federal filing.
- **caveats**: The API surface is DKAN: datasets are discovered from the metastore and queried through /datastore/query/{id}/0. Attribution is by name, and name collisions are real, so check state and NPI before asserting an identity.

### `cms-provider-data-api` - CMS Provider Data API (hospital, physician and Part D prescriber datasets)

- **publisher**: U.S. Centers for Medicare & Medicaid Services (CMS)
- **base**: https://data.cms.gov/provider-data/api/1
- **endpoints**: /metastore/schemas/dataset/items?limit=N, /datastore/query/{datasetId}/0?limit=N
- **auth**: none - No key required.
- **rate limit**: Not published; one call measured 0.7 s, and a repeat probe timed out at 25 s once before answering in three consecutive retries.
- **format**: JSON, CSV
- **cadence**: quarterly to annual by dataset
- **coverage**: Hospital compare, physician and clinician utilisation, Part D prescriber-level and Medicare Advantage datasets with documented data dictionaries.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: False (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items?limit=1'` -> 0)
- **why**: Prescriber-level and hospital-level payment and utilisation data: the ground truth behind 'who prescribes what, and how much does Medicare pay for it'.
- **caveats**: Two different CMS surfaces exist and they behave differently: data.cms.gov/provider-data answers scripted calls, while data.cms.gov/data-api/v1/... is behind Akamai and returned 'Access Denied' (HTTP 403) to both curl and httpx with a contact User-Agent, so the Part D Spending by Drug files under /data-api are not scriptable as-is. One transient 25 s timeout was observed on this API.

### `dailymed-spl-api` - DailyMed SPL web services

- **publisher**: U.S. National Library of Medicine (NLM)
- **base**: https://dailymed.nlm.nih.gov/dailymed/services/v2
- **endpoints**: /spls.json?pagesize=1, /drugnames.json?drug_name=X, /spls/{setid}.xml
- **auth**: none - No key required.
- **rate limit**: Measured 0.8 s per call; NLM publishes a web-services guide at dailymed.nlm.nih.gov/dailymed/app-support-web-services.cfm.
- **format**: JSON and XML
- **cadence**: daily
- **coverage**: Every SPL label version with set IDs, versions and packaging, plus the original SPL XML for full structured content.
- **licence**: NLM: 'Information that is created by or for the US government on this site is within the public domain' (ncbi.nlm.nih.gov/home/about/policies/).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json?pagesize=1'` -> 200)
- **why**: Gives label history and the raw SPL XML when the openFDA label index has flattened a field away. Version history shows when an indication or warning actually changed, which is often the real signal.
- **caveats**: Label versions are per set ID; use the version list and pick the effective version rather than the first hit. Pagination is pagesize + page and the total is only in the response metadata.

### `ema-medicines-output` - EMA medicines output (authorised medicines and EPAR data)

- **publisher**: European Medicines Agency (EMA)
- **base**: https://www.ema.europa.eu/en/medicines/download-medicine-data
- **endpoints**: /documents/report/medicines-output-medicines-report_en.xlsx, /medicines/download-medicine-data (index)
- **auth**: none - No key required; direct XLSX download from the index page.
- **rate limit**: Static file host; 901,378 bytes in 0.5 s.
- **format**: bulk download (XLSX)
- **cadence**: daily to weekly
- **coverage**: Every centrally authorised medicine: EU authorisation dates, active substance, ATC code, therapeutic area, marketing authorisation holder and orphan/conditional status. The probe returned a 901 KB workbook with a 'Medicine' sheet.
- **licence**: EMA legal notice: content may be 'distributed, totally or in part ... for non-commercial and commercial purposes, provided that EMA is always acknowledged as the source of the material' (ema.europa.eu/en/about-us/legal-notice).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.ema.europa.eu/en/documents/report/medicines-output-medicines-report_en.xlsx'` -> 200)
- **why**: EU side of an approval timeline and an ATC-coded product list from the regulator, which is the citable counterpart to a US approval in a global revenue model.
- **caveats**: The workbook is an output report - it carries no prices and no volumes. Cleaner EPAR-style detail needs the per-product document pages. The spreadsheet's schema is not versioned, so pin the download date.

### `eu-ctis-public-api` - EU Clinical Trials Information System (CTIS) public API

- **publisher**: European Medicines Agency / European Commission (CTIS)
- **base**: https://euclinicaltrials.eu/ctis-public-api
- **endpoints**: /search (POST, JSON body: pagination/sort), /retrieve/{ctNumber}
- **auth**: none - No key for the public search endpoint. POST with Content-Type: application/json is required.
- **rate limit**: Not documented publicly; a GET to /search returns HTTP 403 'Missing Authentication Token', so the POST form is mandatory.
- **format**: JSON
- **cadence**: daily
- **coverage**: EU/EEA interventional trials authorised under the Clinical Trials Regulation (2022-present), with trial sites, sponsor, endpoints and decision documents.
- **licence**: EU legislation on public access to CTIS; EMA legal notice allows reuse 'for non-commercial and commercial purposes, provided that EMA is always acknowledged as the source' (ema.europa.eu/en/about-us/legal-notice).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -X POST -H 'Content-Type: application/json' -d '{"pagination":{"page":0,"size":2}}' -o /dev/null -w '%{http_code}' 'https://euclinicaltrials.eu/ctis-public-api/search'` -> 200)
- **why**: The only authoritative view of EU-authorised trials after the 2019 Clinical Trials Regulation; needed for European site counts, sponsor mapping and EU launch timing in a pharma model.
- **caveats**: The API is undocumented: /v3/api-docs returns the SPA shell, not an OpenAPI document. A GET to /search returns 403, so scripts must POST. /retrieve/{ctNumber} returns an empty JSON object {} for an unknown number rather than a 404, so a silent miss looks like a successful call.

### `europepmc` - Europe PMC REST API (literature, preprints, full text, grants)

- **publisher**: European Molecular Biology Laboratory - European Bioinformatics Institute (EMBL-EBI)
- **base**: https://www.ebi.ac.uk/europepmc/webservices/rest
- **endpoints**: /search?query=X&format=json&pageSize=N, /{source}/{id}/fullTextXML, /search?query=X&resultType=core
- **auth**: none - No key required. Some queries are rate-limited by IP.
- **rate limit**: Not published; the API returned HTTP 503 on two probes ~15 minutes apart and HTTP 200 on the third, so retry with backoff is necessary.
- **format**: JSON, XML
- **cadence**: daily
- **coverage**: ~45 M abstracts and records including PubMed, preprints, Agricola and patents, plus ~6 M open-access full texts, grant links and citation counts.
- **licence**: Europe PMC is aggregated content: abstracts are covered by EMBL-EBI terms of use, and full text is included only where the publisher permits. EMBL-EBI: 'For some Data Resources and Tools, additional specific terms and conditions and/or license agreements may apply' (ebi.ac.uk/about/terms-of-use).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=melanoma&format=json&pageSize=1'` -> 200)
- **why**: Broader than PubMed for the same query and it exposes full text for OA articles and a citation count, which is what a 'how strong is this evidence' paragraph needs.
- **caveats**: The service returned HTTP 503 twice during this session before succeeding, so treat it as flaky and cache results. Full text is limited to the OA subset; abstracts are reachable for almost everything. Licence varies per full-text record.

### `fda-orange-book-files` - FDA Orange Book data files (patents, exclusivity, therapeutic equivalence)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://www.fda.gov
- **endpoints**: /media/76860/download?attachment (data files ZIP), /drugs/drug-approvals-and-databases/orange-book-data-files (index)
- **auth**: none - No key required; direct ZIP download.
- **rate limit**: Static file host; one 1,097,768-byte ZIP in <1 s.
- **format**: bulk download (ZIP of pipe-delimited text)
- **cadence**: monthly (data files) with a daily web update
- **coverage**: Approved drug products with patent numbers and expiry dates, exclusivity codes and expiry, therapeutic equivalence ratings and the full product/ingredient/patent file set.
- **licence**: '...the contents of the FDA website (www.fda.gov) - both text and graphics - are not copyrighted. They are in the public domain and may be republished...' (fda.gov/about-fda/about-website/website-policies).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.fda.gov/media/76860/download?attachment'` -> 200)
- **why**: Loss-of-exclusivity and generic-entry timing come from this file, not from a label: patent expiry plus exclusivity is what a dated, defensible 'when does this franchise open' claim needs.
- **caveats**: Patent expiry dates are 'as submitted' and can extend (pediatric exclusivity, 180-day first-generic exclusivity, patent term extensions), so the file date matters. It lists no prices and is US-only; EPAR/EMA documents cover Europe.

### `fda-purple-book-files` - FDA Purple Book data files (licensed biological products and biosimilars)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://purplebooksearch.fda.gov
- **endpoints**: /downloads (monthly historical data-change files), https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-june-data-download.csv
- **auth**: none - No key required; the monthly CSV/XLSX files are direct downloads.
- **rate limit**: Static files; 56,275 bytes compressed (457,261 bytes decompressed) in 0.8 s.
- **format**: bulk download (CSV, XLSX)
- **cadence**: monthly
- **coverage**: Monthly historical change reports of BLA-licensed biological products: reference biologics, biosimilars and interchangeables with applicant, BLA number and licence type. Files exist for every month from 2020 to 2026 (158 file links counted on the downloads page).
- **licence**: '...the contents of the FDA website (www.fda.gov) - both text and graphics - are not copyrighted. They are in the public domain...' (fda.gov/about-fda/about-website/website-policies).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.accessdata.fda.gov/drugsatfda_docs/PurpleBook/2026/purplebook-search-june-data-download.csv'` -> 200)
- **why**: The biologic-side complement to the Orange Book. Biosimilar and interchangeable status with dates is what a biologics franchise model needs, and it is published as machine-readable monthly deltas.
- **caveats**: The machine-readable files are monthly change reports, not a full current snapshot - my June 2026 file is titled 'Purple Book Monthly Historical Data Changes Report' with 2,233 rows. The full current list is served through the Purple Book Search web UI. Filenames mix capitalisation ('june' vs 'May'), so a guessed month name can 404.

### `health-canada-dpd` - Health Canada Drug Product Database API

- **publisher**: Health Canada (Government of Canada)
- **base**: https://health-products.canada.ca/api/drug
- **endpoints**: /drugproduct/?lang=en&type=json, /activeingredient/?lang=en&type=json&id={drug_code}, /company/?lang=en&type=json
- **auth**: none - No key required.
- **rate limit**: Not published; the full product extract (15 MB) returned in one call.
- **format**: JSON
- **cadence**: daily to weekly
- **coverage**: Every drug product authorised for the Canadian market: DIN, brand name, class, company, number of active ingredients, plus separate endpoints for ingredients, forms, routes, companies and status.
- **licence**: Open Government Licence - Canada: 'Contains information licensed under the Open Government Licence - Canada' (open.canada.ca/en/open-government-licence-canada).
- **cost**: free
- **verified**: True (`python3 -c "import httpx;r=httpx.get('https://health-products.canada.ca/api/drug/drugproduct/?lang=en&type=json',headers={'User-Agent':'prime-agent research contact:faisalnazer2@gmail.com'},timeout=60,follow_redirects=True);print(r.status_code)"` -> 200)
- **why**: A third regulator's product list with its own identifiers (DIN), which is what a comparative approval-timing claim needs outside the US and EU.
- **caveats**: curl against health-products.canada.ca fails here with 'SSL certificate problem: unable to get local issuer certificate' - the probe used the httpx one-liner shown. The unbounded /drugproduct/ call returns ~15 MB of JSON, so filter with id= or download once and cache.

### `icd10cm-cdc-bulk` - CDC/NCHS ICD-10-CM code files (bulk distribution)

- **publisher**: U.S. Centers for Disease Control and Prevention (CDC/NCHS)
- **base**: https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD10CM
- **endpoints**: /2025/icd10cm-Code-Descriptions-2025.zip, /2025/icd10cm-table-index-2025.zip, /2025/icd-10-cm-conversion-table-FY2025.xlsx
- **auth**: none - No key required.
- **rate limit**: Static file host; no documented limit. The directory listing is HTML and parsable.
- **format**: bulk download (ZIP, XLSX, PDF)
- **cadence**: annual (fiscal-year releases, with mid-year addenda)
- **coverage**: Full ICD-10-CM code set with descriptions, the table/index files and the prior-year conversion table; the 2025 directory lists 7 files including a 19.9 MB table index.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: True (`python3 -c "import httpx;r=httpx.get('https://ftp.cdc.gov/pub/Health_Statistics/NCHS/Publications/ICD10CM/2025/',headers={'User-Agent':'prime-agent research contact:faisalnazer2@gmail.com'},timeout=60,follow_redirects=True);print(r.status_code)"` -> 200)
- **why**: Bulk code-to-description joins for a clinical model: the API is for lookups, this is for rebuilding the whole coding tree offline and for year-over-year code changes.
- **caveats**: curl on this host fails here with 'SSL certificate problem: unable to connect to local issuer' - the probe used the httpx one-liner shown. Use python/httpx for ftp.cdc.gov, not the local curl.

### `isrctn-registry-api` - ISRCTN registry API (UK and international trials)

- **publisher**: ISRCTN Registry, Springer Nature / BMC
- **base**: https://www.isrctn.com/api
- **endpoints**: /query/format/default?limit=N&q=(term), /query/format/default?limit=0&q=... (count only)
- **auth**: none - No key. A query expression in q= is required; limit=0 returns the count only.
- **rate limit**: Not documented; one 38 KB response in 0.8 s. No pagination or batching (the ctrdata R client states 'no pagination or batching').
- **format**: XML
- **cadence**: daily
- **coverage**: ~40k+ registered trials; probe query q=(melanoma) returned totalCount=389 with full trial records.
- **licence**: Trial metadata from contributions since 1 Jan 2019 is reusable 'without restriction on a CC0 basis'; other site content is 'strictly for your personal non-commercial use' (isrctn.com/page/terms).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.isrctn.com/api/query/format/default?limit=2&q=(melanoma)'` -> 200)
- **why**: Independent UK/global registry coverage that is not in ClinicalTrials.gov; useful for UK site counts and for trials whose results are published but never posted to the US register.
- **caveats**: The format token is 'default', not 'json' - /api/query/format/json returns HTTP 400. The response Content-Type is application/xml although the path says format/default. No pagination: filter server-side or get everything.

### `medicaid-nadac` - Medicaid NADAC drug acquisition cost (data.medicaid.gov)

- **publisher**: U.S. Centers for Medicare & Medicaid Services (CMS) / Medicaid.gov
- **base**: https://data.medicaid.gov/api/1
- **endpoints**: /datastore/query/{datasetId}/0?limit=N, /metastore/schemas/dataset/items?show-reference-ids=true&limit=N, CSV: https://download.medicaid.gov/data/nadac-national-average-drug-acquisition-cost-09-30-2026.csv
- **auth**: none - No key required.
- **rate limit**: Not published; one 10.4 MB CSV and 1.2 s datastore calls.
- **format**: JSON, CSV, XLSX
- **cadence**: weekly (NADAC survey cycles); one dataset per year plus a current file
- **coverage**: National Average Drug Acquisition Cost: what retail pharmacies actually pay per NDC, plus the underlying survey of invoice prices. Current file probed at 10,392,419 bytes.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://data.medicaid.gov/api/1/datastore/query/fbb83258-11c7-47f5-8b18-5f8e79f7e704/0?limit=1'` -> 200)
- **why**: The closest public thing to a real US acquisition price, published weekly with a documented survey method. It gives a defensible unit-cost baseline against list price, which is the core of a gross-to-net or price-erosion argument.
- **caveats**: NADAC is a survey-based acquisition cost for the retail setting, not net revenue: it excludes rebates, 340B and non-retail channels. It is keyed by NDC, which changes as packages are discontinued, so join through openFDA's NDC directory.

### `nhsbsa-open-data` - NHS Business Services Authority open data portal (English prescribing)

- **publisher**: NHS Business Services Authority (NHSBSA), UK
- **base**: https://opendata.nhsbsa.net/api/3/action
- **endpoints**: /package_list, /package_show?id=english-prescribing-dataset-epd-with-snomed-code, /datastore_search?resource_id={id}&limit=N
- **auth**: none - No key required.
- **rate limit**: CKAN datastore_search is paged (limit/offset) and capped per call; measured 1.5 s.
- **format**: JSON, CSV, XLSX, Parquet
- **cadence**: monthly
- **coverage**: English primary-care prescribing: one row per practice, BNF presentation and month, with items, quantity and actual cost. Monthly resources (e.g. EPD_SNOMED_202011) each have a datastore ID.
- **licence**: UK Open Government Licence v3.0: 'Contains public sector information licensed under the Open Government Licence v3.0' (nationalarchives.gov.uk/doc/open-government-licence/version/3/).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://opendata.nhsbsa.net/api/3/action/datastore_search?resource_id=e4e5508c-3f9e-4676-b5bb-e126ef724060&limit=1'` -> 200)
- **why**: Actual dispensed volume and cost by practice and month, which is the UK demand series behind a volume or share argument. It is also the only free source that shows practice-level uptake.
- **caveats**: Coverage is England only and the units are items/quantity/cost per practice-by-product-by-month, so aggregation must respect practice list sizes. Resource IDs are monthly; enumerate package_show before querying, because a stale resource ID returns an empty set rather than an error.

### `nice-syndication-api` - NICE syndication API (UK health technology appraisal decisions)

- **publisher**: UK National Institute for Health and Care Excellence (NICE)
- **base**: https://api.nice.org.uk/services
- **endpoints**: /guidance, /guidance?pathway=... (see the syndication API docs)
- **auth**: free_key - Registration required: apply for a syndication API key at nice.org.uk/about/what-we-do/nice-syndication-api. The probe without a key returned HTTP 401.
- **rate limit**: Not published; the syndication service is documented as suitable for moderate-volume calls.
- **format**: JSON
- **cadence**: as guidance publishes (weekly to monthly)
- **coverage**: NICE guidance, technology appraisals and recommendations with IDs, publication dates and recommendation text.
- **licence**: NICE content is subject to Crown copyright; the syndication API terms restrict redistribution of full documents but permit use of metadata. Confirm the current terms with the key.
- **cost**: free with registration
- **verified**: False (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.nice.org.uk/services/guidance'` -> 401)
- **why**: UK reimbursement decisions gate whether a product is actually paid for: a TA number and a recommendation date is what a market-access sentence needs to cite.
- **caveats**: UNVERIFIED BY ME: probed without a key and got HTTP 401 on https://api.nice.org.uk/services/guidance, so the service is live and key-gated but I obtained no data. The registration page (nice.org.uk/about/what-we-do/nice-syndication-api) returned 200.

### `nlm-clinical-tables` - NLM Clinical Tables API (ICD-10-CM, HCPCS, LOINC items, RxTerms)

- **publisher**: U.S. National Library of Medicine (NLM)
- **base**: https://clinicaltables.nlm.nih.gov/api
- **endpoints**: /icd10cm/v3/search?terms=X&sf=code,name&df=code,name&maxList=N, /hcpcs/v3/search?terms=X, /loinc_items/v3/search?terms=X
- **auth**: none - No key required.
- **rate limit**: Not published; measured 0.5-0.8 s per call.
- **format**: JSON
- **cadence**: quarterly to annual (tracks ICD-10-CM and HCPCS releases)
- **coverage**: ICD-10-CM diagnosis codes, HCPCS procedure codes, LOINC item names and RxTerms, all with autocomplete-style lookups.
- **licence**: US government work, public domain (17 U.S.C. 105); NLM terms ask for acknowledgement.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://clinicaltables.nlm.nih.gov/api/icd10cm/v3/search?terms=diabetes&sf=code,name&df=code,name&maxList=2'` -> 200)
- **why**: The fastest free route from a clinical phrase to a coded identifier. It is also the free partial substitute for LOINC's key-gated FHIR API, which matters when a model needs lab codes.
- **caveats**: The response is a positional array [count, codes, null, display], not a list of objects - parse by position. Parameter behaviour differs per resource: icd10cm returns an empty set without sf/df, while hcpcs answers a bare terms= query, so each resource needs its own call form.

### `nppes-npi-registry` - NPPES NPI Registry API (provider identity)

- **publisher**: U.S. Centers for Medicare & Medicaid Services (CMS)
- **base**: https://npiregistry.cms.hhs.gov/api
- **endpoints**: /?version=2.1&organization_name=X&state=MN&limit=1, /?version=2.1&npi={10 digits}
- **auth**: none - No key required.
- **rate limit**: CMS asks callers to limit to 200 requests per day per IP for the public API; heavy use needs the full NPPES download instead.
- **format**: JSON
- **cadence**: daily (NPPES weekly file, API near-real-time)
- **coverage**: Every US provider and organisation: NPI, taxonomy (specialty), practice addresses, enumeration date and status. ~9 M records.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://npiregistry.cms.hhs.gov/api/?version=2.1&organization_name=MAYO%20CLINIC&state=MN&limit=1'` -> 200)
- **why**: Provider identity resolution: it turns a name in an Open Payments or claims record into an NPI, a specialty and a location, which is what makes a prescriber or site-count claim checkable.
- **caveats**: A fabricated or inactive NPI returns HTTP 200 with {'result_count':0} (my first probe used a made-up 10-digit number) - a zero-result 200 looks like success. Use /?version=2.1&npi= for exact lookups and check result_count.

### `oecd-health-sdmx` - OECD health statistics via the SDMX REST API (pharmaceutical market and health expenditure)

- **publisher**: Organisation for Economic Co-operation and Development (OECD)
- **base**: https://sdmx.oecd.org/public/rest
- **endpoints**: /dataflow/OECD.ELS.HD/all/latest?format=json-structure-2.0.0&references=none, /data/OECD.ELS.HD,HEALTH_PHMC@DF_PHMC_SALES,1.0/.?startPeriod=2021&endPeriod=2021&format=jsondata
- **auth**: none - No key required.
- **rate limit**: Not published; the structure query returned 70,698 bytes in 0.6 s and a pharma-sales data query 45,973 bytes in 0.97 s.
- **format**: JSON (SDMX-JSON 2.0)
- **cadence**: quarterly to annual
- **coverage**: 86 health dataflows under OECD.ELS.HD, including 'Pharmaceutical market', 'Pharmaceutical consumption', 'Pharmaceutical sales', 'Health expenditure and financing', health care quality and prescribing in primary care, with country-year dimensions.
- **licence**: OECD terms page returned HTTP 403 to my probe, so I could not read them; OECD data is generally offered under CC BY 4.0. Verify before republication - not verified in this pass.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -H 'Accept: application/vnd.sdmx.data+json;version=2.0.0' -o /dev/null -w '%{http_code}' 'https://sdmx.oecd.org/public/rest/data/OECD.ELS.HD,HEALTH_PHMC@DF_PHMC_SALES,1.0/.?startPeriod=2021&endPeriod=2021&format=jsondata'` -> 200)
- **why**: Cross-country pharmaceutical spend and consumption series from the statistical publisher itself, which is how a market-size or per-capita-spend claim gets a comparable basis across 38 countries.
- **caveats**: The format token must be exactly 'json-structure-2.0.0' (or 'structure'/'sdmx-3.0'); 'json-structure' returns HTTP 406 with a message listing the acceptable values. Data URLs need the full flowRef agency,flow,version triple - my first guess returned 404.

### `open-targets-platform` - Open Targets Platform GraphQL API (target-disease evidence)

- **publisher**: Open Targets (EMBL-EBI, GSK, Sanofi, Bayer, AbbVie, Pfizer, Genentech)
- **base**: https://api.platform.opentargets.org/api/v4
- **endpoints**: /graphql (POST: target, disease, evidence, knownDrugs), /graphql (POST: { target(ensemblId:"ENSG00000157764"){ approvedSymbol } })
- **auth**: none - No key required.
- **rate limit**: Not published; the probe answered in 0.6 s. GraphQL means one query can replace many REST calls, but deep evidence queries are large.
- **format**: JSON (GraphQL)
- **cadence**: quarterly (Platform releases)
- **coverage**: Target-disease associations with per-datatype evidence: genetics, somatic mutations, expression, pathways, literature and known drugs, keyed by Ensembl gene ID.
- **licence**: Mixed per source: the licence table at platform-docs.opentargets.org/licence lists CC BY 4.0, CC0 1.0, EMBL-EBI terms and some sources marked 'Commercial use for Open Targets' - which restricts onward commercial redistribution of those parts.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -X POST -H 'Content-Type: application/json' -d '{"query": "{ target(ensemblId: \"ENSG00000157764\") { approvedSymbol } }"}' -o /dev/null -w '%{http_code}' 'https://api.platform.opentargets.org/api/v4/graphql'` -> 200)
- **why**: Gives a defensible association score with the underlying evidence classes, so a target's support can be described as genetics-plus-literature rather than asserted. It also carries the known-drug set for a target, which is a pipeline map.
- **caveats**: The evidence is heterogeneous and the association score is a model output, not a biological result - cite the underlying evidence, not the score alone. 'Commercial use for Open Targets' sources cannot simply be republished; check the per-source licence table before reusing a figure.

### `openfda-device-maude` - openFDA MAUDE device adverse-event endpoint

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/device/event
- **endpoints**: /event.json?limit=1, /event.json?search=device.brand_name:"X"
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. 26.1 M records: measured 4.2 s for one record - use narrow searches.
- **format**: JSON
- **cadence**: quarterly (meta.last_updated 2026-09-22 on probe)
- **coverage**: 26,136,889 device event reports: event type, device identity, manufacturer, patient outcome, report date.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/device/event.json?limit=1'` -> 200)
- **why**: The device analogue of FAERS, and the only structured public record of device failures - relevant to defence-medical equipment claims and to device-makers in a portfolio.
- **caveats**: Like FAERS this is a voluntary-report database with no denominator; MAUDE counts rose after the 2020 reporting change, so cross-year comparisons need the caveat stated.

### `openfda-device-udi` - openFDA device UDI endpoint (GUDID)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/device/udi
- **endpoints**: /udi.json?limit=1, /udi.json?search=device_description:"X"
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. Measured 1.8 s.
- **format**: JSON
- **cadence**: daily (meta.last_updated 2026-09-02 on probe)
- **coverage**: 5,182,695 device records with DI, brand/trade names, company, GMDN/device-listing data and recall flags.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/device/udi.json?limit=1'` -> 200)
- **why**: Medical-device identification for device-based claims: manufacturers, device classes and catalogue numbers that a device-safety or procurement sentence must pin to a UDI.
- **caveats**: Device records are self-reported by labelers, so company names are inconsistent; normalise before counting manufacturers.

### `openfda-drug-label` - openFDA drug label endpoint (SPL labelling)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/drug/label
- **endpoints**: /label.json?limit=1, /label.json?search=openfda.brand_name:"X", /label.json?search=openfda.generic_name:"Y"
- **auth**: none - No key for up to 1,000 requests/day per IP; a free key raises limits - register at open.fda.gov/apis/authentication/.
- **rate limit**: 40,000 requests/day and 240 requests/minute per IP with a key; 1,000/day and 240/minute without. Measured latency 1.5 s.
- **format**: JSON
- **cadence**: daily (meta.last_updated 2026-09-29 on probe)
- **coverage**: 262,887 label records on probe; full SPL labelling with indications, dosage, warnings, and nested openfda identifiers.
- **licence**: '...the content, data, documentation, code, and related materials on openFDA is public domain and made available with a Creative Commons CC0 1.0 Universal dedication' (open.fda.gov/terms/).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/label.json?limit=1'` -> 200)
- **why**: The label is the legal source for indication, dose and contraindication claims. Every 'what is this drug approved to do' sentence in a memo can cite a label revision date from here.
- **caveats**: Search syntax is Lucene-like and silently returns HTTP 404 with {'error':{'code':'NOT_FOUND'}} when a search matches nothing, which is easy to misread as a broken API. Use meta.results.total to null-test. Nested openfda fields omit values FDA has not normalised - absence of an ATC code in this index is not absence of an ATC code.

### `openfda-drug-shortages` - openFDA drug shortages endpoint

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/drug/shortages
- **endpoints**: /shortages.json?limit=1, /shortages.json?search=generic_name:"X"
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. Measured 1.2 s.
- **format**: JSON
- **cadence**: daily
- **coverage**: 1,599 shortage records on probe; fields include generic_name, package_ndc, dosage_form, therapeutic_category, initial_posting_date, update_date, update_type, discontinued_date and contact_info.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/shortages.json?limit=1'` -> 200)
- **why**: Supply-chain evidence: a shortage entry is a dated, citable primary record of a manufacturing or demand failure, which matters for defence-medical stockpile and for pricing power in a pharma thesis.
- **caveats**: The legacy dps.fda.gov API path returns 503/404 to scripts; the openFDA mirror is the machine path. My earlier probes of https://dps.fda.gov/drugshortages/ returned HTTP 301/503 - use api.fda.gov/drug/shortages.json instead.

### `openfda-drugsfda` - openFDA Drugs@FDA endpoint (approvals and application history)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/drug/drugsfda
- **endpoints**: /drugsfda.json?limit=1, /drugsfda.json?search=openfda.brand_name:"X"
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. Measured 1.1 s.
- **format**: JSON
- **cadence**: daily (meta.last_updated 2026-09-28 on probe)
- **coverage**: 29,357 application records: NDA/ANDA/BLA numbers, submission types and dates, review priority, applicant, products and strengths.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/drugsfda.json?limit=1'` -> 200)
- **why**: Approval dates and application types are the input to loss-of-exclusivity and generic-entry timing in an investment memo, and to 'when was this actually approved' questions.
- **caveats**: The endpoint covers the FDA application record, not the patent or exclusivity expiry - that is the Orange Book. It indexes submissions, so the same drug can appear under several application numbers.

### `openfda-enforcement-recalls` - openFDA enforcement (recall) endpoints - drug, device, food

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov
- **endpoints**: /drug/enforcement.json?limit=1, /device/enforcement.json?limit=1, /food/enforcement.json?limit=1
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. Drug enforcement measured 1.3 s.
- **format**: JSON
- **cadence**: weekly (drug enforcement meta.last_updated 2026-09-23 on probe)
- **coverage**: 17,988 drug recall records on probe (plus device and food recall classes) with classification, reason, quantity, distribution pattern and dates.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/enforcement.json?limit=1'` -> 200)
- **why**: Recall history is due-diligence evidence: a recalled lot, its class and its distribution list is a dated primary record of quality failure and is quotable in a memo.
- **caveats**: Recall 'classification' (I/II/III) is a severity class, not an outcome survey; voluntary recalls are included. Recalls are added and updated, so a re-run changes counts.

### `openfda-faers` - openFDA FAERS adverse-event endpoint

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/drug/event
- **endpoints**: /event.json?limit=1, /event.json?search=patient.reaction.reactionmeddrapt:"X"
- **auth**: none - No key; free key raises the daily limit - open.fda.gov/apis/authentication/.
- **rate limit**: Same openFDA limits as above (240/min; 1,000/day unkeyed). 20.7 M records means a broad query is slow: measured 3.0 s for one record.
- **format**: JSON
- **cadence**: quarterly (meta.last_updated 2026-07-30 on probe)
- **coverage**: 20,692,890 spontaneous adverse-event reports with drug, reaction (MedDRA), outcome, country and report date.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/event.json?limit=1'` -> 200)
- **why**: Post-market safety signal work: a reaction count with a report window is the difference between a defensible signal and a rumour in a clinical or investment memo.
- **caveats**: Report counts are not incidence: FAERS has no denominator and reporting is voluntary, so counts must never be divided by prescriptions to imply a rate. FAERS bulk quarterly ASCII/ZIP extracts remain available at https://fis.fda.gov/extensions/FPD-QDE-FAERS/FPD-QDE-FAERS.html (probed 200) if the full 20 M rows are needed offline.

### `openfda-ndc-directory` - openFDA NDC directory (every marketed package)

- **publisher**: U.S. Food and Drug Administration (FDA)
- **base**: https://api.fda.gov/drug/ndc
- **endpoints**: /ndc.json?limit=1, /ndc.json?search=generic_name:"X"
- **auth**: none - No key; free key optional.
- **rate limit**: Same openFDA limits. Measured 1.2 s.
- **format**: JSON
- **cadence**: daily (meta.last_updated 2026-09-28 on probe)
- **coverage**: 138,276 package records with NDC, labeler, dosage form, marketing category, marketing start/end dates and active ingredients.
- **licence**: Public domain / CC0 1.0 per open.fda.gov/terms/.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://api.fda.gov/drug/ndc.json?limit=1'` -> 200)
- **why**: The join key between pricing, volume and labelling sources: NADAC, ASP and Medicaid claims are all keyed by NDC, so this is where a price series attaches to a product.
- **caveats**: Includes finished and unfinished products; filter marketing_category to exclude bulk ingredients. Marketing end dates mark withdrawal from the listing, not real-world discontinuation.

### `pubchem-pug-rest` - PubChem PUG REST (chemical structure and properties)

- **publisher**: U.S. National Center for Biotechnology Information (NCBI/NLM)
- **base**: https://pubchem.ncbi.nlm.nih.gov/rest/pug
- **endpoints**: /compound/name/{name}/property/MolecularFormula,XLogP/JSON, /compound/cid/{cid}/synonyms/JSON
- **auth**: none - No key required.
- **rate limit**: NCBI asks for no more than 5 requests/second without a key; a key can be requested for heavier use.
- **format**: JSON and XML plus bulk download
- **cadence**: continuous
- **coverage**: ~120 M compounds with structure, computed properties, synonyms, bioassay links and literature links.
- **licence**: US government work, public domain (ncbi.nlm.nih.gov/home/about/policies/: 'Information that is created by or for the US government on this site is within the public domain.').
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/aspirin/property/MolecularFormula,XLogP/JSON'` -> 200)
- **why**: Chemistry grounding for a formulation or mechanism claim: molecular formula, mass, LogP and identifiers that resolve the same substance across ChEMBL, patents and labels.
- **caveats**: Computed properties are model estimates, not measured values, and should not be cited as physical constants. Large property requests need POST plus a list, not a long GET.

### `pubmed-eutils` - PubMed E-utilities (citations, MeSH indexing, full-text links)

- **publisher**: U.S. National Library of Medicine (NLM)
- **base**: https://eutils.ncbi.nlm.nih.gov/entrez/eutils
- **endpoints**: /esearch.fcgi?db=pubmed&term=X&retmode=json, /efetch.fcgi?db=pubmed&id=38000000&retmode=xml, /elink.fcgi?dbfrom=pubmed&linkname=pubmed_pubmed
- **auth**: none - No key for 3 requests/second; a free API key raises this to 10/second and is requested at ncbi.nlm.nih.gov/account.
- **rate limit**: 3 requests/second without a key, 10 with; NCBI blocks and asks for an email in the URL or User-Agent for heavy use.
- **format**: JSON and XML
- **cadence**: daily
- **coverage**: 35 M+ citations with abstracts, MeSH terms, publication types, and links to PMC full text. efetch returned 15,540 bytes of XML for one PMID.
- **licence**: US government work, public domain (17 U.S.C. 105); NLM terms ask for acknowledgement (nlm.nih.gov/databases/download/terms_and_conditions.html).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=melanoma&retmax=1&retmode=json'` -> 200)
- **why**: The citation backbone: a PMID plus MeSH terms makes a literature claim checkable, and publication-type filters separate RCTs from editorials in an evidence table.
- **caveats**: esearch caps retmax (10,000) and history is required for larger sets. MeSH indexing lags publication by months, so recent papers have no MeSH terms and must be found by text terms.

### `rxnav-rxnorm` - RxNav / RxNorm APIs (drug nomenclature and normalisation)

- **publisher**: U.S. National Library of Medicine (NLM)
- **base**: https://rxnav.nlm.nih.gov/REST
- **endpoints**: /drugs.json?name=X, /ndcstatus.json?ndc=00002143301, /rxcui/{rxcui}/allrelated.json
- **auth**: none - No key required.
- **rate limit**: Not published; measured 0.9 s per call. RxNorm asks for a limit of 20 requests/second per IP.
- **format**: JSON and XML
- **cadence**: weekly (RxNorm full release)
- **coverage**: RxNorm concepts with ingredient/clinical/branded forms, NDC-to-RxCUI mapping and current NDC status.
- **licence**: US government work, public domain (17 U.S.C. 105); NLM terms ask for acknowledgement (nlm.nih.gov/databases/download/terms_and_conditions.html: 'No charges, usage fees or royalties are paid to NLM for this data.').
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://rxnav.nlm.nih.gov/REST/drugs.json?name=lipitor'` -> 200)
- **why**: The normalisation layer between sources that spell drugs differently: it turns a label name, an NDC and a trial intervention into one identifier so counts do not double-count or split products.
- **caveats**: RxNorm has no prices, approvals or volumes. Ingredient-level matching needs tty filtering (IN/BN/SCD) or the same molecule appears several times.

### `usaspending-federal-awards` - USAspending award census (federal health and medical procurement)

- **publisher**: U.S. Department of the Treasury, Bureau of the Fiscal Service
- **base**: https://api.usaspending.gov/api/v2
- **endpoints**: /references/toptier_agencies/, /search/spending_by_award/ (POST), /agency/{code}/awards/
- **auth**: none - No key required.
- **rate limit**: Not published; one 52,705-byte response in 0.5 s (via httpx).
- **format**: JSON
- **cadence**: daily to weekly (award modifications)
- **coverage**: Every reported federal prime award and subaward with recipient, agency, NAICS/PSC code, obligation amount and period of performance.
- **licence**: US government work, public domain (17 U.S.C. 105).
- **cost**: free
- **verified**: True (`python3 -c "import httpx;r=httpx.get('https://api.usaspending.gov/api/v2/references/toptier_agencies/',headers={'User-Agent':'prime-agent research contact:faisalnazer2@gmail.com'},timeout=60,follow_redirects=True);print(r.status_code)"` -> 200)
- **why**: The money trail behind clinical and health-industrial claims: BARDA/ASPR medical countermeasure contracts, HHS and VA spending by recipient and year, and the prime/subaward split. ALREADY COVERED by the existing usaspending_prime_census code path in this harness - listed here only for completeness, with the health-agency query form.
- **caveats**: curl against api.usaspending.gov fails here with a local TLS error ('self signed certificate in certificate chain'); the probe used the httpx one-liner shown. Award amounts are obligations, not outlays, and multiple modifications of one award are not additional money - a naive sum overcounts.

### `who-disease-outbreak-news` - WHO Disease Outbreak News API

- **publisher**: World Health Organization (WHO)
- **base**: https://www.who.int/api/news
- **endpoints**: /diseaseoutbreaknews?$top=1, /diseaseoutbreaknews?$filter=PublicationDate gt 2026-01-01
- **auth**: none - No key required.
- **rate limit**: Not published; measured 0.4 s.
- **format**: JSON (OData)
- **cadence**: irregular (as outbreaks are reported)
- **coverage**: WHO-verified outbreak reports with title, publication date, summary, epidemiology, assessment and advice fields.
- **licence**: WHO open access CC BY-NC-SA 3.0 IGO for WHO publications (who.int/about/policies/publishing/copyright).
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://www.who.int/api/news/diseaseoutbreaknews?$top=1'` -> 200)
- **why**: A dated, authoritative outbreak feed for bio-event monitoring. Each item carries who/when/what fields, so a timeline can cite WHO rather than a news aggregator.
- **caveats**: The OData entity exposes a long projection list; select fields explicitly or the payload is large. Items are edited in place after publication, so re-pull before quoting.

### `who-gho-odata` - WHO Global Health Observatory OData API

- **publisher**: World Health Organization (WHO)
- **base**: https://ghoapi.azureedge.net/api
- **endpoints**: /Indicator?$top=1, /{IndicatorCode}?$filter=..., /Indicator?$filter=contains(IndicatorName,'X')
- **auth**: none - No key required.
- **rate limit**: Not published; measured 1.3 s. OData paging uses $top/$skip and returns up to 1,000 rows per page.
- **format**: JSON (OData)
- **cadence**: weekly to annual by indicator
- **coverage**: ~2,000 health indicators for 194 member states: mortality, immunisation, TB/HIV, health financing and health workforce, with country and year dimensions.
- **licence**: WHO open access is CC BY-NC-SA 3.0 IGO for WHO publications, with CC BY 3.0 IGO for some WHO-authored articles (who.int/about/policies/publishing/copyright). Non-commercial restriction applies.
- **cost**: free
- **verified**: True (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://ghoapi.azureedge.net/api/Indicator?$top=1'` -> 200)
- **why**: Country-level denominators and burden figures for a clinical or market-sizing model, from the publisher rather than a secondary aggregator.
- **caveats**: Indicator codes are the join key and are opaque (e.g. ABORTION_ADMISSIONS); enumerate /Indicator first. Some series stop years before the current year, so always read the latest observation, not the report date. CC BY-NC-SA restricts commercial redistribution.

### `who-icd11-api` - WHO ICD-11 API (ICD-11 MMS and classifications)

- **publisher**: World Health Organization (WHO)
- **base**: https://id.who.int/icd
- **endpoints**: /entity/{id}, /icd/release/11/{release}/mms, OAuth token: https://icdaccessmanagement.who.int/connect/token
- **auth**: free_key - OAuth2 client credentials. Register a free ICD API account at icd.who.int/icdapi (the 'ICD-11 API' sign-up page) to obtain client_id and client_secret; then POST to the token endpoint. The probe without a token returns HTTP 401.
- **rate limit**: Not published for the free tier; the API is design-limited and documented per-account.
- **format**: JSON
- **cadence**: irregular (ICD-11 release updates)
- **coverage**: Full ICD-11 classification: ~17,000 categories with multilingual titles, definitions, synonyms and mappings.
- **licence**: WHO: 'WHO's open access applies to: all publications published by WHO - CC BY-NC-SA 3.0 IGO' (who.int/about/policies/publishing/copyright). The NC clause restricts commercial reuse.
- **cost**: free with registration
- **verified**: False (`curl -s --compressed -m 30 -A 'prime-agent research contact:faisalnazer2@gmail.com' -o /dev/null -w '%{http_code}' 'https://id.who.int/icd/entity/257068234'` -> 401)
- **why**: ICD-11 is the coding standard WHO members will migrate to; for a model that must survive a coding change, the mapping between ICD-10 and ICD-11 is the asset.
- **caveats**: Probed without credentials: HTTP 401 on https://id.who.int/icd/entity/257068234. So it is live and key-gated, and I did not obtain data. The NC licence term on WHO products is the thing to check before quoting WHO text in a commercial memo. ICD-10-CM bulk files from CDC (separate entry) remain the key-free alternative for US coding.

## Legal, IP, scientific literature and archives

### `arxiv-export-api` - arXiv export API (already installed - defer to the arxiv skill)

- **publisher**: Cornell University / arXiv
- **base**: https://export.arxiv.org/api
- **endpoints**: /query?search_query=<field>:<term>&start=0&max_results=N, /query?id_list=<id>
- **auth**: none - No key. The operator already has this wired: the arxiv skill at ~/.agents/skills/arxiv/scripts governs every call with a 3.5-second cross-process pacing lock, 429 backoff and a ban sentinel.
- **rate limit**: arXiv policy: 1 request per 3 seconds; exceeding it returns 429 and can block the source IP for 30 minutes to several hours. The installed skill enforces 3.5 s spacing.
- **format**: XML | Atom
- **cadence**: daily
- **coverage**: 2.4M+ preprints in physics, mathematics, computer science, quantitative biology and economics, with versioned submissions and full-text PDF/LaTeX download.
- **licence**: Individual papers carry arXiv licences (often CC BY or arXiv's non-exclusive licence); metadata is free to harvest.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://export.arxiv.org/api/query?search_query=all:hypersonic&start=0&max_results=2"` -> 200)
- **why**: For hypersonics, quantum and ML-adjacent defence topics, the newest work appears here months before a journal. Already-installed capability: the skill must consume it, not rebuild it.
- **caveats**: http://export.arxiv.org 301-redirects to https. Rate limiting is enforced by source IP and bans the whole machine, so any new code must reuse the existing governor, not open its own connection. The Atom feed paginates with start/max_results only.

### `caselaw-access-project` - Caselaw Access Project (static.case.law)

- **publisher**: Harvard Law School Library Innovation Lab
- **base**: https://static.case.law
- **endpoints**: / (reporter index), /<reporter>/ (volume index), /<reporter>/VolumesMetadata.json, /<reporter>/<volume>.tar.csv (per-volume case text + metadata), /<reporter>/<volume>.pdf
- **auth**: none - No key, no account. Plain HTTPS GET.
- **rate limit**: Static object storage behind CloudFront; no published limit. Fetch whole volumes rather than case-by-case.
- **format**: JSON | CSV | bulk download
- **cadence**: irregular
- **coverage**: Every published US court decision through June 2018 (about 6.9 million cases, 40 million pages) as per-reporter volumes, with OCR text, metadata and page images. Post-2018 decisions are not included.
- **licence**: CAP states the data is free to use and redistribute; Harvard's terms page is https://case.law/terms/ (not re-read in this session - verify before republishing scans).
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://static.case.law/a2d/"` -> 200)
- **why**: Historical case law at zero cost and zero rate limit: ideal for tracing how a doctrine (patent eligibility, antitrust, government-contract damages) evolved, and for quoting an exact page.
- **caveats**: The REST API is retired; only static files remain, so there is no server-side search - you download volumes and search locally. Coverage stops at June 2018, so recent cases must come from CourtListener. My first guess of file naming (a2d/1.tar.gz) 404s: the real extensions are .tar, .tar.csv, .pdf, .zip plus VolumesMetadata.json / ReporterMetadata.json.

### `common-crawl-index` - Common Crawl CDX index + crawl metadata

- **publisher**: Common Crawl Foundation
- **base**: https://index.commoncrawl.org
- **endpoints**: /collinfo.json (list of crawls with cdx-api URLs), /<CC-MAIN-YYYY-WW>-index?url=<domain>&output=json&limit=N, https://data.commoncrawl.org/crawl-data/<crawl>/wet.paths.gz (WARC paths)
- **auth**: none - No key; the index is an HTTP API and the data lives on S3/HTTPS.
- **rate limit**: Not published; index queries are heavy and can return 504 (I hit one) - retry with a specific crawl ID and a narrow url= pattern.
- **format**: JSON | Parquet | bulk download
- **cadence**: monthly
- **coverage**: Monthly web crawls since 2013, each with billions of pages: raw WARC, extracted text (WET) and metadata (WAT), addressable per URL through the CDX index. Measured: collinfo.json listed crawls with the newest at CC-MAIN-2025-38 and answered in 0.8 s; that crawl's index returned records for defense.gov in 9.5 s.
- **licence**: Crawl data is provided under Common Crawl's terms (https://commoncrawl.org/terms-of-use); respect robots.txt and the terms of the crawled sites.
- **cost**: free (egress from AWS S3 is paid if you pull from S3 rather than the HTTPS mirror)
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://index.commoncrawl.org/CC-MAIN-2025-38-index?url=defense.gov&output=json&limit=2"` -> 200)
- **why**: Bulk web text without scraping: for NLP over defence or pharma news, or for checking how a site presented something in the past at corpus scale, this is the only free source with that volume.
- **caveats**: The index server is flaky under load: one request returned 504 Gateway Time-out, and a hand-constructed columnar-index path returned 404, so always read the exact cdx-api URL from collinfo.json rather than guessing. Coverage is a sample of the web, not the whole web, and the CDX index does not contain page text - the text is in the WET/WARC files.

### `congress-gov-v3` - Congress.gov API v3

- **publisher**: Library of Congress
- **base**: https://api.congress.gov/v3
- **endpoints**: /bill?limit=N&api_key=<key>, /bill/<congress>/<type>/<number>, /bill/<c>/<t>/<n>/text, /member, /committee, /nomination, /treaty, /hearing
- **auth**: free_key - api.data.gov key from https://api.data.gov/signup/; DEMO_KEY works for a probe.
- **rate limit**: Documented: 5,000 requests/hour per key.
- **format**: JSON | XML
- **cadence**: daily
- **coverage**: Bills, amendments, actions, votes, members, committees, hearings, nominations and treaties across Congresses, with linked full text. Measured: bill records with introducedDate, latestAction and sponsor fields returned immediately.
- **licence**: US government works, public domain; LOC content generally reusable with attribution.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.congress.gov/v3/bill?limit=2&api_key=DEMO_KEY"` -> 200)
- **why**: Traces defence authorisation and appropriations language, export-control bills and pharma pricing bills to a citable bill number and action date, which is how a 'what will be funded' claim gets a source.
- **caveats**: DEMO_KEY is heavily throttled; get a real key. Endpoint shapes differ per resource - /law/<congress>/<number> returned 404 in my probe, so check the resource path before assuming it exists. Responses include pagination objects (count/next) that must be followed.

### `courtlistener-bulk-data` - CourtListener + RECAP bulk data on S3

- **publisher**: Free Law Project
- **base**: https://com-courtlistener-storage.s3.amazonaws.com
- **endpoints**: /?list-type=2&max-keys=N&prefix=...&continuation-token=...
- **auth**: none - No credentials; the bucket allows anonymous ListObjectsV2 and object GET.
- **rate limit**: Not documented; S3 default request rates apply.
- **format**: bulk download
- **cadence**: daily
- **coverage**: Full opinion corpus and RECAP archive as compressed dumps (opinions, clusters, dockets, courts, citation graph), plus the same data as Postgres/Parquet-style exports. Measured: bucket listing returns a continuation token, so it is paged.
- **licence**: Same as CourtListener: public-domain opinions plus user-contributed RECAP filings. Attribution to Free Law Project expected.
- **cost**: free (egress from S3 is free for this public bucket)
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://com-courtlistener-storage.s3.amazonaws.com/?list-type=2&max-keys=2"` -> 200)
- **why**: Removes the API rate limit entirely for corpus work: 'find every opinion citing this statute' or 'all patent cases against this company' becomes a local grep instead of 125 requests a day.
- **caveats**: ListObjectsV2 is paged by continuation token, not by offset. Dumps are large (tens of GB); the API docs list the file layout. Verify the dump's freshness date before treating it as current.

### `courtlistener-rest-v4` - CourtListener REST API v4 (opinions + RECAP dockets)

- **publisher**: Free Law Project
- **base**: https://www.courtlistener.com/api/rest/v4
- **endpoints**: /search/?q=<query>&type=o&order_by=dateFiled+desc, /search/?q=<query>&type=r, /opinions/?, /clusters/?, /dockets/?court=scotus&page_size=N, /people/?page_size=N, /recap-fetch/ (Paid PACER fetch, token required)
- **auth**: none - Anonymous GET works for /search/ (probe 200, count=15714 for 'patent eligibility'). /opinions/ and /dockets/ returned 401 anonymously; an API token (header: Authorization: Token <key>) is free at https://www.courtlistener.com/help/api/rest/ (sign in, then /api/rest/v4/ profile page).
- **rate limit**: Documented for authenticated users: 5/minute, 50/hour, 125/day (https://wiki.free.law/c/courtlistener/help/api/rest/v4/rest-api-v47#rate-limits). Anonymous search succeeded in this session; no anonymous quota is documented, so treat anonymous access as best-effort.
- **format**: JSON
- **cadence**: real-time
- **coverage**: Federal and state opinions and dockets. Measured in-session: 15,714 opinion hits for 'patent eligibility'; the RECAP docket index reported 152,252 dockets and 1,623,119 documents for 'antitrust'.
- **licence**: Court opinions are public-domain US government works; RECAP documents are user-uploaded court filings. Free Law Project asks for a token and attribution; commercial use is governed by agreements they advertise in the API docs (https://free.law/contact/?issue_type=partnerships). Not verified against a formal licence page in this session.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://www.courtlistener.com/api/rest/v4/search/?q=patent+eligibility&type=o&order_by=dateFiled+desc"` -> 200)
- **why**: The only free machine-readable US case-law and docket index that answers 'what did a court decide' with a citable docket number, judge and filing date. For defence-industrial and pharma work it is where you find contract disputes, patent litigation, FDA suits and investor class actions.
- **caveats**: Two different access rules on one host: /search/ answers anonymously, /opinions/ and /dockets/ return 401 without a token. Pagination is cursor-based (the next URL carries an opaque cursor), so do not try page numbers. Rate limits are low (125 authenticated requests/day), which is why the bulk S3 dump matters for anything at corpus scale.

### `crossref-rest` - Crossref REST API

- **publisher**: Crossref (DOI registration agency)
- **base**: https://api.crossref.org
- **endpoints**: /works?query.bibliographic=<q>&rows=N&mailto=<email>, /works/<doi>, /works/<doi>/agency, /journals/<issn>, /members, /funders
- **auth**: none - No key. Include mailto= (or a User-Agent with contact) to enter the polite pool.
- **rate limit**: Measured in the response headers: x-rate-limit-limit: 1, x-rate-limit-interval: 1s, x-concurrency-limit: 1, x-api-pool: public-array - i.e. one request per second and one in flight on the public pool.
- **format**: JSON
- **cadence**: real-time
- **coverage**: 160M+ DOI records across publishers with title, authors, affiliations, funders, references and licence links. Measured: 709,254 results for a semaglutide cardiovascular bibliographic query.
- **licence**: Bibliographic metadata is free to use; Crossref requires no agreement for the public pool and asks for attribution of the DOI registration agency (https://www.crossref.org/terms/).
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.crossref.org/works?query.bibliographic=semaglutide+cardiovascular&rows=2&mailto=faisalnazer2@gmail.com"` -> 200)
- **why**: The citation backbone: it converts a claim about a paper into a DOI plus funder and reference list, which is the cheapest way to attach a source to a clinical or technical number.
- **caveats**: One request per second, one concurrency - a corpus job must queue. The polite pool is keyed to the mailto/UA; without it Crossref may throttle. Reference lists are publisher-deposited and incomplete for some members, and the 'agency' endpoint exists precisely because some DOIs are registered elsewhere.

### `epo-ops` - EPO Open Patent Services (OPS) 3.2

- **publisher**: European Patent Office
- **base**: https://ops.epo.org/3.2
- **endpoints**: /auth/accesstoken (OAuth2 client_credentials), /rest-services/published-data/publication/epodoc/<num>/biblio.json, /rest-services/published-data/search, /rest-services/register/publication/epodoc/<num>/biblio.json, /rest-services/family/publication/epodoc/<num>/biblio.json
- **auth**: free_key - OAuth2 client credentials: register a free OPS account at https://developers.epo.org/ , then POST client_id/client_secret to /3.2/auth/accesstoken (Basic auth) to receive a bearer token.
- **rate limit**: Documented Fair Use limit of 4 GB/month of retrieved data for the free tier; exceeding it triggers the rejection I measured.
- **format**: JSON | XML
- **cadence**: weekly
- **coverage**: Worldwide patent bibliographic data, families, legal status and EPO register data in DOCDB/INPADOC structure - the same backbone commercial patent tools resell.
- **licence**: EPO OPS terms of use and Fair Use policy (https://www.epo.org/service-support/ordering/fair-use.html, cited in the error body). Free tier is for reasonable non-commercial use; redistribution restricted.
- **cost**: free at 4 GB/month of data; paid volumes above that
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://ops.epo.org/3.2/rest-services/published-data/publication/epodoc/EP1000000/biblio.json"` -> 403)
- **why**: Patent families and legal status are what make a patent claim honest across jurisdictions: 'protected in the US' becomes 'granted in US, lapsed in DE, pending in CN' with dates.
- **caveats**: Anonymous probe returned 403 with '<error><code>403</code><message>This request has been rejected due to the violation of Fair Use policy</message>' - that is the anonymous/fair-use gate, not a dead service. The token endpoint /3.2/auth/accesstoken returns 401 without credentials, as expected. No data retrieved, hence verified=false.

### `eu-cellar-eurlex` - EU Cellar / EUR-Lex SPARQL endpoint

- **publisher**: Publications Office of the European Union
- **base**: https://publications.europa.eu/webapi/rdf/sparql
- **endpoints**: /webapi/rdf/sparql?query=<SPARQL>&format=application/sparql-results+json, https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:<celex> (human view)
- **auth**: none - No key for the public SPARQL endpoint. Send the query as the query parameter with Accept: application/sparql-results+json.
- **rate limit**: Not published; the endpoint is known to time out on heavy property-path queries - keep LIMIT small.
- **format**: JSON | XML | RDF
- **cadence**: daily
- **coverage**: The EU legal corpus in Cellar: treaties, regulations, directives, decisions and case law, addressable by CELEX number. Measured: a prefixed SPARQL query returned real CELEX values (e.g. 62024CC0505) with Cellar work URIs.
- **licence**: EU legal texts and metadata are reusable under the Commission's reuse decision (Decision 2011/833/EU); confirm current terms at https://eur-lex.europa.eu/ .
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -H 'Accept: application/sparql-results+json' -o /dev/null -w '%{http_code}' "https://publications.europa.eu/webapi/rdf/sparql?query=PREFIX%20cdm%3A%20%3Chttp%3A%2F%2Fpublications.europa.eu%2Fontology%2Fcdm%23%3E%20SELECT%20%3Fwork%20%3Fcelex%20WHERE%20%7B%3Fwork%20cdm%3Aresource_legal_id_celex%20%3Fcelex%7D%20LIMIT%203&format=application%2Fsparql-results%2Bjson"` -> 200)
- **why**: EU regulation drives defence export controls, chemicals and pharma market access; this is the primary machine path to the CELEX-numbered text that a memo can cite.
- **caveats**: SPARQL needs explicit PREFIX lines - my first query without PREFIX cdm: failed with 'Virtuoso 37000 Error SP030: Undefined namespace prefix'. Property-path queries time out (one 40 s failure in this session). eur-lex.europa.eu HTML with curl returned 202 (bot challenge), so use Cellar for machine access.

### `europe-pmc-rest` - Europe PMC REST API

- **publisher**: EMBL-EBI (Europe PMC funders)
- **base**: https://www.ebi.ac.uk/europepmc/webservices/rest
- **endpoints**: /search?query=<q>&format=json&pageSize=N, /<source>/<id>/fullTextXML (open-access full text), /MED/<pmid>/citations?format=json, /<source>/<id>/references, /search?query=<q>&resultType=core
- **auth**: none - No key.
- **rate limit**: Not published; the service asks for reasonable use and returns 503 under load (one citations call returned 503 during this session while search returned 200).
- **format**: JSON | XML
- **cadence**: daily
- **coverage**: 40M+ life-science records (PubMed plus Agricola, patents and preprints) with 8M+ open-access full texts, citation counts and reference lists - the full text is the differentiator.
- **licence**: Open-access full texts are available under their own licences (often CC BY); abstracts remain publisher copyright. Terms at https://europepmc.org/ .
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=semaglutide%20AND%20SRC%3AMED&format=json&pageSize=2"` -> 200)
- **why**: Gives the actual article XML, so a number from a trial can be quoted from the source rather than from a secondary summary - the operator's rule that every number traces to a source.
- **caveats**: fullTextXML only exists for open-access records (probe of PMC3258128 returned 200 XML; many other IDs will 404). One citations call returned 503 in this session, so retry with backoff. Query syntax is its own (SRC:MED, OPEN_ACCESS:Y), not PubMed's.

### `google-patents-bigquery` - Google Patents Public Datasets on BigQuery

- **publisher**: Google Cloud (with USPTO/EPO source data)
- **base**: https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/datasets
- **endpoints**: https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/datasets/patents, bigquery-public-data.patents.publications (SQL table), bigquery-public-data.patents.publications_202508 (sharded)
- **auth**: free_key - Google Cloud account with BigQuery API enabled; the free sandbox gives 1 TB of query processing per month and 10 GB of storage. Console browser at https://console.cloud.google.com/bigquery?p=bigquery-public-data&d=patents .
- **rate limit**: Billing/quotas rather than rate limits: 1 TB query bytes free per month, then about $6.25 per TB scanned (Google's published on-demand price; not re-verified here).
- **format**: bulk download | JSON
- **cadence**: quarterly
- **coverage**: The full patent corpus as SQL: titles, abstracts, claims, CPC classifications, citations, assignees, and family/legal-status tables. This is the only practical way to run corpus-scale patent queries at zero cost.
- **licence**: Public dataset hosted by Google from USPTO/EPO sources; Google's BigQuery public-data terms apply. Source data is public-domain government data.
- **cost**: free up to 1 TB of query data per month (BigQuery sandbox); metered beyond that
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://bigquery.googleapis.com/bigquery/v2/projects/bigquery-public-data/datasets"` -> 401)
- **why**: Answers questions no API can: 'how many US grants in CPC H04B did this assignee get per year since 2010', citation-network centrality, and patent-count time series that a memo can chart from the same SQL.
- **caveats**: The datasets REST path returns 401 because BigQuery requires OAuth, so verified=false. Console URL returned 200 (a docs/app page), which proves the dataset page exists but not queryability. Watch the renamed sharded tables (publications_YYYYMM) - queries against the old table name break. Query bytes are the cost unit: SELECT * on publications is expensive, always project/filter.

### `google-patents-search` - Google Patents full-text search (internal JSON endpoint)

- **publisher**: Google
- **base**: https://patents.google.com/xhr/query
- **endpoints**: /xhr/query?url=q%3D<urlEncodedQuery>, /xhr/result?patent_id=patent/<id>/en
- **auth**: none - No key. Plain GET with a browser-like Accept header.
- **rate limit**: Not published and not contractual; this is the site's own XHR endpoint, so treat it as fragile and low-volume.
- **format**: JSON
- **cadence**: weekly
- **coverage**: Full-text search across ~120 million patent publications with CPC/IPC filters, assignee and date facets, plus machine translation of non-English text. Measured: 44,132 results for 'hypersonic vehicle' in one call.
- **licence**: Google Patents aggregates DOCDB/INPADOC and national full texts; Google's terms govern use of the interface. This is a mirror of primary patent data, not the publisher - use USPTO/EPO for the record of truth.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://patents.google.com/xhr/query?url=q%3Dhypersonic%2Bvehicle&exp="` -> 200)
- **why**: The fastest way to go from a technology claim to the patent set behind it (who filed, when, in which countries) without a key or a quota, which makes it the discovery step before a USPTO/EPO record check.
- **caveats**: Undocumented endpoint: the response shape (results.cluster[].result[].patent) can change without notice and Google offers no SLA. It is a mirror, so cite the USPTO/EPO record, not this response. Small result sets only - no bulk crawling.

### `internet-archive-api` - Internet Archive item search + metadata API

- **publisher**: Internet Archive
- **base**: https://archive.org
- **endpoints**: /advancedsearch.php?q=<query>&fl[]=<field>&rows=N&output=json&page=N, /metadata/<identifier>, /download/<identifier>/<file>, /services/search/v1/scrape?q=<query>&count=N (requires fields= parameter)
- **auth**: none - No key for search, metadata or download.
- **rate limit**: Not published; the scrape API is the supported bulk path and requires an explicit fields= parameter (my call without it returned HTTP 400).
- **format**: JSON | XML | bulk download
- **cadence**: daily
- **coverage**: Tens of millions of items: digitised books and periodicals, government reports, TV/radio news archives, software and datasets, plus collection-level full text search. Measured: 7,877 items match 'hypersonic' in the general search; a collection-scoped query (collection:nasa_techdocs) returned records immediately.
- **licence**: Item-level: many are public domain or CC-licensed, some are lending-restricted. Metadata is CC0 per IA docs; check the item's rights field before redistributing a file.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://archive.org/advancedsearch.php?q=hypersonic&fl%5B%5D=identifier&fl%5B%5D=title&rows=2&output=json"` -> 200)
- **why**: Scanned public filings, old technical reports and broadcast news are exactly the corpora the operator OCRs. This finds the item, gives an identifier and a stable download URL, and the metadata API returns the file list.
- **caveats**: advancedsearch.php is Solr-backed and needs output=json with fl[] fields; deep paging (page>~100) is slow. Metadata is free-text and inconsistent across uploaders, so identifier is the only reliable key. Borrowing-restricted items expose metadata but not the file.

### `nasa-ads` - NASA Astrophysics Data System (ADS) API

- **publisher**: NASA / Smithsonian Astrophysical Observatory
- **base**: https://api.adsabs.harvard.edu/v1
- **endpoints**: /search/query?q=<query>&fl=<fields>&rows=N, /export/<fmt>/<bibcode>, /metrics, /v1/search/qtree
- **auth**: free_key - Free personal API token from https://ui.adsabs.harvard.edu/user/settings/token (create an ADS account, no charge). Pass as Authorization: Bearer <token>.
- **rate limit**: Documented at 5,000 requests/day per token (and a small burst limit); not re-verified here.
- **format**: JSON
- **cadence**: daily
- **coverage**: Millions of records in astronomy, planetary science, space physics, geophysics and the physics literature generally, with citation counts, bibcodes and full-text links - including NASA and aerospace grey literature.
- **licence**: ADS metadata is free for research use; abstracts and full texts belong to publishers (ADS links out).
- **cost**: free (token required)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.adsabs.harvard.edu/v1/search/query?q=hypersonic&fl=title,bibcode&rows=2"` -> 401)
- **why**: Aerospace and space-physics literature with citation metrics is a direct input to defence-industrial analysis, and bibcodes are stable citation keys that survive URL rot.
- **caveats**: Probe without a token returned 401, so no data was retrieved (verified=false). The token is per-user and must be requested from the account settings page - a step the operator has to take once. Query syntax is its own language (field:value pairs, e.g. abs:'hypersonic'), not free text by default.

### `nih-reporter` - NIH RePORTER API v2

- **publisher**: US National Institutes of Health
- **base**: https://api.reporter.nih.gov/v2
- **endpoints**: /projects/search (POST, JSON criteria: fiscal_years, advanced_text_search, include_fields)
- **auth**: none - No key or registration.
- **rate limit**: Not published; POST bodies cap the page size (offset/limit) so paging is explicit.
- **format**: JSON
- **cadence**: weekly
- **coverage**: Every NIH-funded project with fiscal year, institute, PI, organisation, funding amount and abstract, back to the 1980s. Measured: a FY2023 project-title search for 'hypersonic' returned total=0 - a true negative the API reports cleanly rather than erroring.
- **licence**: US government funded-research data, public domain; NIH publishes award data for reuse.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -X POST -H 'Content-Type: application/json' -d '{"criteria":{"fiscal_years":[2023],"advanced_text_search":{"operator":"and","search_field":"projecttitle","search_text":"hypersonic"}},"limit":2}' -o /dev/null -w '%{http_code}' "https://api.reporter.nih.gov/v2/projects/search"` -> 200)
- **why**: Government funding is the demand signal behind clinical capability: which institution, which PI, which amount, which year - all citable, and the basis for 'who is being paid to work on this'.
- **caveats**: POST-only with a JSON body; the search is field-scoped (projecttitle vs abstract vs all), and the wrong field returns a confident zero. include_fields is needed to keep responses small. Amounts are awarded, not obligated, so do not read them as money spent.

### `ntrs-nasa` - NASA Technical Reports Server (NTRS) API

- **publisher**: NASA Scientific and Technical Information Program
- **base**: https://ntrs.nasa.gov/api
- **endpoints**: /citations/search?q=<q>&page.size=N, /citations/<id>, /citations/<id>/downloads
- **auth**: none - No key or account.
- **rate limit**: Not published; responses are paged with page.size/page.from.
- **format**: JSON | bulk download
- **cadence**: daily
- **coverage**: Millions of NASA and NACA technical reports, conference papers and datasets from the 1910s to today, with full-text PDFs - the public face of aerospace grey literature, including hypersonics, propulsion and materials work.
- **licence**: NASA reports are US government works (public domain) unless marked otherwise; the search page states distribution limitations for some records.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://ntrs.nasa.gov/api/citations/search?q=hypersonic&page.size=1"` -> 200)
- **why**: Grey literature is where engineering numbers live (test conditions, material properties). NTRS gives a citable report number plus a machine-readable record, and the PDF is usually downloadable for OCR.
- **caveats**: My guessed download path /api/citations/<id>/downloads/<n>.pdf returned 404, so resolve the download URL from the citation record field rather than constructing it. Some records are export-controlled and show a distribution statement instead of a file - check before quoting.

### `ofac-sanctions-lists` - OFAC Sanctions List Service (SDN, consolidated and non-SDN lists)

- **publisher**: US Department of the Treasury, Office of Foreign Assets Control
- **base**: https://sanctionslistservice.ofac.treas.gov/api
- **endpoints**: /download/sdn.xml (redirects to a signed S3 object), /download/sdn.csv, /download/cons_prim.csv, /download/alt.csv, /PublicationPreview/exports/SDN.CSV
- **auth**: none - No key. No TLS workaround is needed: the system curl (/usr/bin/curl) and python httpx both reach it. The earlier failure came from the Anaconda curl on PATH - see caveats.
- **rate limit**: Not published; these are static file downloads refreshed on publication days.
- **format**: XML | CSV
- **cadence**: irregular
- **coverage**: US sanctions designations: SDN and non-SDN (SSI, NS-CMIC, FSE, CAPTA) lists with names, aliases, addresses, identifiers and the sanctions programme per entry. Measured: SDN.XML is 29.1 MB with Publish_Date 09/23/2026 and Record_Count 19391; the consolidated non-SDN primary CSV is 262,892 bytes.
- **licence**: US government works, public domain; Treasury publishes the lists for public use without agreement.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -k -L --max-time 60 -o /dev/null -w '%{http_code}' "https://sanctionslistservice.ofac.treas.gov/api/download/cons_prim.csv"` -> 200)
- **why**: US sanctions are the operative constraint on who a defence client or an investor can deal with; the record count and publish date let a deliverable state the screening basis as of a date.
- **caveats**: TLS, CORRECTED BY THE PARENT 2026-09-29: the earlier reading that these hosts serve an untrusted Entrust chain was WRONG - the fault was the curl binary, not the host. Measured side by side on sanctionslistservice.ofac.treas.gov: /Users/slimydog/opt/anaconda3/bin/curl (7.84.0, OpenSSL 1.1.1q) returned http=000 with a certificate error, while /usr/bin/curl (8.7.1, SecureTransport) returned 302 and python httpx returned 200. Cause: a second curl ships inside Anaconda and wins on PATH in a conda-activated shell, with its own CA bundle. Use /usr/bin/curl or httpx, and NEVER add -k - the host certificate is valid. Also: /api/download/sdn.xml 302s to a time-limited signed S3 URL, so do not cache that redirect.

### `openalex` - OpenAlex

- **publisher**: OurResearch (non-profit)
- **base**: https://api.openalex.org
- **endpoints**: /works?search=<q>&per_page=N&mailto=<email>, /works?filter=title.search:<q>, /authors/<id>, /institutions?search=<q>, /sources/<id>, /funders/<id>
- **auth**: none - No key. mailto= puts the caller in the polite pool; an API key exists for higher volume.
- **rate limit**: OpenAlex documents a 100,000 calls/day and 10 requests/second ceiling; the current docs site is a JavaScript app I could not read for the exact wording, so treat that as documented-not-verified. Measured: no throttling at 1 request/second with mailto.
- **format**: JSON
- **cadence**: daily
- **coverage**: 250M+ scholarly works with authors, institutions, funders, concepts, citation counts and open-access status, plus institution and funder registries. Measured: 11,065 works for a full-text 'solid-state battery defence' query; /institutions?search=Pentagon resolves organisations.
- **licence**: Data is CC0 (public domain dedication) per the OpenAlex project; the underlying abstracts remain the publishers'.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.openalex.org/works?search=solid-state+battery+defence&per_page=2&mailto=faisalnazer2@gmail.com"` -> 200)
- **why**: Answers the meta-questions the operator actually asks: who funds this field, which institutions produce it, and how citations flow - as JSON he can aggregate, at no cost and with CC0 reuse rights in a deliverable.
- **caveats**: Author and institution disambiguation is imperfect (merged/misspelled entities); the abstract is an inverted index that must be reconstructed; select= is essential because full records are large. Data licences of the underlying works are not covered by CC0.

### `openstates-v3` - OpenStates API v3 (US state legislation)

- **publisher**: Plural Policy (OpenStates project)
- **base**: https://v3.openstates.org
- **endpoints**: /bills?jurisdiction=<state>&per_page=N, /people?jurisdiction=<state>, /bills/<ocd-bill-id>, /committees
- **auth**: free_key - Header X-API-KEY or ?apikey=; key from https://openstates.org/account/profile/ (free account; the site now redirects to open.pluralpolicy.com).
- **rate limit**: Documented tiers; free accounts are limited (the site documents per-minute quotas).
- **format**: JSON
- **cadence**: daily
- **coverage**: All 50 US states plus DC and territories: bills, sponsors, votes, committees and legislators, with OCD-ID identifiers that join to Wikidata.
- **licence**: OpenStates data is published under an open licence (project docs state CC BY 4.0 for the bulk data collection); confirm current terms at https://openstates.org/ before commercial republication.
- **cost**: free (key required)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://v3.openstates.org/bills?jurisdiction=California&per_page=2"` -> 403)
- **why**: State law is where pharma pricing, Medicaid coverage, defence-site siting and state incentives are actually decided; this is the only free machine index of it.
- **caveats**: Probe without a key returned 403 with the exact message {"detail":"Must provide API Key as ?apikey or X-API-KEY. Login and visit https://openstates.org/account/profile/ for your API key."} - the service is live, it is key-gated. Both /bills and /people answered 403. No data was retrieved, so verified=false.

### `openstreetmap-overpass` - OpenStreetMap Overpass API + Nominatim geocoder

- **publisher**: OpenStreetMap Foundation / community (Geofabrik, FOSSGIS)
- **base**: https://overpass-api.de/api
- **endpoints**: /interpreter?data=[out:json];<overpass QL>, https://nominatim.openstreetmap.org/search?q=<q>&format=json, https://nominatim.openstreetmap.org/reverse?lat=<lat>&lon=<lon>&format=json
- **auth**: none - No key; a real User-Agent identifying the caller is required, and Nominatim asks for a contact email or link in it.
- **rate limit**: Nominatim: 1 request/second and no heavy bulk use. Overpass: fair-use, with per-IP slot limits; oversized queries return 504 rather than queueing.
- **format**: JSON | XML
- **cadence**: real-time
- **coverage**: Global infrastructure and place data: buildings, industrial sites, military ranges, airfields, pipelines, ports, hospitals and administrative boundaries, with tags rather than a fixed schema. Measured: a coordinate query near the Pentagon returned a node with lat/lon and ODbL notice; a way-level name query returned a result in 4 s.
- **licence**: Open Data Commons Open Database License (ODbL) 1.0 - attribution 'Data (c) OpenStreetMap contributors' is mandatory and derived databases must stay ODbL.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://overpass-api.de/api/interpreter?data=%5Bout%3Ajson%5D%3Bway%5Bname%3D%22Pentagon%22%5D%3Bout%201%3B"` -> 200)
- **why**: Geolocation and infrastructure mapping for defence-industrial and site work: where a facility actually is, what surrounds it, and which administrative area it sits in - all queryable, with an ODbL licence that is workable for internal analysis.
- **caveats**: My first Overpass query (a bounding-box city search) returned 504 Gateway Time-out in 10 s; the same endpoint answered a narrow way-name query in 4 s - keep queries narrow or use an alternate instance (overpass.kumi.systems timed out in this session). ODbL share-alike is a real constraint if a derived dataset is redistributed. Tag completeness varies by country, so absence of a facility is weak evidence.

### `osti-api` - OSTI.gov API (US Department of Energy science and technical information)

- **publisher**: US Department of Energy, Office of Scientific and Technical Information
- **base**: https://www.osti.gov/api/v1
- **endpoints**: /records?q=<query>&rows=N, /records/<osti_id>, /records/<osti_id>/fulltext
- **auth**: none - Documented as no key; OSTI also offers an API key for higher limits at https://www.osti.gov/api/ (registration page not reachable from this network in this session).
- **rate limit**: Not verifiable - the host did not answer.
- **format**: JSON | XML | bulk download
- **cadence**: daily
- **coverage**: DOE and DOE-contractor research: nuclear weapons stewardship, materials, computing, energy and national-laboratory reports (including declassified collections) with full-text links.
- **licence**: DOE-funded technical reports are generally US government works; some carry distribution limitations.
- **cost**: free
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -4 --max-time 60 -o /dev/null -w '%{http_code}' "https://www.osti.gov/api/v1/records?q=hypersonic&rows=2"` -> 0)
- **why**: The national-laboratory grey literature is where weapons, materials and computing details live, and it is the DOE counterpart to NTRS. If reachable, it is a unique primary source for defence-adjacent technical claims.
- **caveats**: UNREACHABLE from this machine on 2026-09-29: https://www.osti.gov/ itself timed out (curl exit 28, connect timeout of 15-60 s), http://www.osti.gov on port 80 timed out as well, and api.osti.gov does not resolve (NXDOMAIN). DNS for www.osti.gov resolves to 192.107.175.222, so this looks like a network path/geo block rather than a dead service. Not verified - test from another network before relying on it.

### `pacer` - PACER (Public Access to Court Electronic Records) + Case Locator

- **publisher**: Administrative Office of the US Courts
- **base**: https://pacer.uscourts.gov
- **endpoints**: https://pacer.uscourts.gov/ (info + login portal), https://pacer.uscourts.gov/ (Case Locator, authenticated, per-search billing)
- **auth**: paid_key - Requires a PACER account (https://pacer.uscourts.gov/register or the account-management page). The public site is readable; court records need the paid login. No anonymous REST path was found for the Case Locator - two guessed documentation URLs returned 404.
- **rate limit**: Not published for the Case Locator API; billing is per search/page rather than per second.
- **format**: JSON | XML | bulk download
- **cadence**: real-time
- **coverage**: Every federal district, bankruptcy and appellate docket plus the Case Locator index across all courts. The only authoritative source for filings that RECAP has not mirrored.
- **licence**: Court records are public; PACER charges statutory access fees. Terms at https://pacer.uscourts.gov/ (FAQ).
- **cost**: paid: $0.10 per page, with fees waived for a quarter in which total charges are $30 or less (quote from the PACER FAQ fetched at https://pacer.uscourts.gov/). Searching that returns no matches still bills $0.10.
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://pacer.uscourts.gov/"` -> 200)
- **why**: The authoritative federal court record. When a defence contractor or a pharma company is sued and the filing is not in RECAP, this is the only place the document exists.
- **caveats**: I could not verify a machine interface: https://pacer.uscourts.gov/help/pacer/case-locator-api and .../pacer-fees both returned 404, and the two anonymous attempts to reach the record path returned 200 only for the public info page. Treat 'PACER API' as account-gated and undocumented until the operator's own account shows the endpoints. Do not sign up or spend money on my account of it.

### `regulations-gov-v4` - Regulations.gov API v4 (US rulemaking dockets and comments)

- **publisher**: US General Services Administration / eRulemaking Program
- **base**: https://api.regulations.gov/v4
- **endpoints**: /documents?filter[searchTerm]=<q>&page[size]=N&api_key=<key>, /dockets?filter[searchTerm]=<q>, /comments?filter[docketId]=<id>
- **auth**: free_key - api.data.gov key (free) from https://api.data.gov/signup/; the API error message itself points to https://api.regulations.gov for key issuance.
- **rate limit**: Documented: 1,000 requests/hour with a registered key; DEMO_KEY is capped far lower.
- **format**: JSON
- **cadence**: daily
- **coverage**: Federal rulemaking dockets, proposed rules, supporting documents and every public comment, with docket and document IDs (the same IDs cited in the Federal Register).
- **licence**: US government works; public comments are posted publicly by the agency. No agreement required.
- **cost**: free (key required)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.regulations.gov/v4/dockets?page%5Bsize%5D=1"` -> 403)
- **why**: The comment record is evidence of who opposed or supported a rule: useful when a deliverable claims industry consensus, and the docket ID is the citation that pairs with the Federal Register notice.
- **caveats**: Anonymous probe returned 403 with {"error":{"code":"API_KEY_MISSING","message":"No api_key was supplied. Get one at https://api.regulations.gov:443"}}. DEMO_KEY requests failed differently - HTTP 503 'upstream connect error or disconnect/reset before headers' after 52 s, three times, for both /documents and /dockets - so DEMO_KEY is not usable for this API right now and a real key is required. No data retrieved, hence verified=false.

### `semantic-scholar-graph` - Semantic Scholar Academic Graph API

- **publisher**: Allen Institute for AI
- **base**: https://api.semanticscholar.org/graph/v1
- **endpoints**: /paper/<id or DOI:...>?fields=title,abstract,year,externalIds,citationCount, /paper/search?query=<q>&limit=N&fields=..., /paper/<id>/citations, /paper/<id>/references, /author/<id>, /recommendations
- **auth**: free_key - Anonymous access works at low volume; a free API key from the form linked in the error message (https://www.semanticscholar.org/product/api#api-key-form) raises the rate limit.
- **rate limit**: Measured: /paper/search returned HTTP 429 'Too Many Requests... apply for a key for higher rate limits' on the shared unauthenticated pool, while a single-paper lookup returned 200 in the same session. Documented limit for authenticated callers is 1 request/second.
- **format**: JSON
- **cadence**: weekly
- **coverage**: 200M+ papers with citation graph, references, abstracts, influential-citation flags and TLDR summaries, plus author disambiguation that is stronger than raw name matching.
- **licence**: Metadata available for reuse with attribution; the S2 corpus is built from publisher agreements, so full text is not redistributable.
- **cost**: free (key recommended)
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.semanticscholar.org/graph/v1/paper/DOI:10.1038/nature12373?fields=title,abstract,year"` -> 200)
- **why**: Citation-graph lookups are how a technical claim gets validated - who cites this paper, and does the citing work support or contradict it. The references endpoint also produces a reading list from one good paper.
- **caveats**: The unauthenticated pool is shared and 429s under any load - the search endpoint failed on first call while single-paper lookups worked. Get a free key before any batch job. Do not confuse /paper/<id> (200) with /paper/search (throttled hardest).

### `uk-legislation-api` - legislation.gov.uk data API (UK statutes and statutory instruments)

- **publisher**: The National Archives (UK)
- **base**: https://www.legislation.gov.uk
- **endpoints**: /<type>/<year>/<number>/data.xml, /<type>/<year>/<number>/data.akn, /<type>/<year>/<number>/data.feed (Atom), /<type>/data.feed?page=N, /<type>/<year>/<number>/contents/data.xml
- **auth**: none - No key. Plain GET; add a contact User-Agent.
- **rate limit**: Not published; the site asks heavy users to cache. Atom feeds page by ?page=N.
- **format**: XML | JSON (limited) | Atom | RDF
- **cadence**: daily
- **coverage**: Every UK Act, statutory instrument and retained EU law with point-in-time versions, plus a catalogue feed of new legislation. Measured: the Human Rights Act 1998 returned 305 KB of XML and a 243 KB Akoma Ntoso version.
- **licence**: Open Government Licence v3.0 for legislation and metadata (stated on the site); attribution required.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://www.legislation.gov.uk/ukpga/1998/42/data.xml"` -> 200)
- **why**: UK defence procurement, export licensing and pharma regulation sit in UK statutes; the Akoma Ntoso form gives citable section-level structure instead of a web page.
- **caveats**: Aliases matter: /ukpga/2023/1/data.json and /ukpga/1998/42/data.json both 404 - JSON is offered on only some endpoints, XML/AkN/Atom are the reliable formats. A wrong act number returns an HTML 404 page rather than an error document, so validate the year/number before parsing.

### `uk-national-archives-discovery` - UK National Archives Discovery API

- **publisher**: The National Archives (UK)
- **base**: https://discovery.nationalarchives.gov.uk/API
- **endpoints**: /search/records?sps.searchQuery=<q>&sps.resultsPageSize=N, /search/records?<field>=<value>&sps.resultsPage=N, /record/<iaid> (record detail)
- **auth**: none - No key; the API accepts plain GET with Accept: application/json.
- **rate limit**: Not published; the API asks for a descriptive User-Agent and moderate request rates.
- **format**: JSON
- **cadence**: weekly
- **coverage**: 32M+ catalogue descriptions from The National Archives and 2,500+ other UK archives, with department/series structure, dates, former references and holding archive. Measured: a keyword query for 'hypersonic' returned records with context fields (e.g. an Aeronautical Research Council series) and heldBy metadata.
- **licence**: Catalogue descriptions are published under the Open Government Licence; document images and transcriptions may have their own terms.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://discovery.nationalarchives.gov.uk/API/search/records?sps.searchQuery=hypersonic&sps.resultsPageSize=2"` -> 200)
- **why**: UK defence-industrial history (ministry files, establishment reports, contracts) is described here and nowhere else machine-readably. It is the evidence step for a claim about what was developed, by whom, and when, and the record reference (e.g. AIR/DSIR series) is a citable identifier.
- **caveats**: Results are catalogue descriptions, not document text - ordering or digitisation is separate. Query syntax is idiosyncratic (sps.* parameters) and the API returns a compact record unless you request more. Field names differ from the web UI's, so check the returned JSON for the keys that exist.

### `un-sc-sanctions-consolidated` - UN Security Council Consolidated Sanctions List (XML)

- **publisher**: United Nations Security Council
- **base**: https://scsanctions.un.org/resources/xml/en
- **endpoints**: /consolidated.xml (full list, all regimes), /consolidated.xml with ?_=<date> to bypass cache
- **auth**: none - No key. Direct file download; the human-facing page on un.org is Cloudflare-protected (202/empty body to a scripted client), but the XML file itself is open.
- **rate limit**: Not published; the file is a single 2.2 MB download refreshed on a schedule.
- **format**: XML
- **cadence**: daily
- **coverage**: Every individual and entity on a UN sanctions regime (Al-Qaida/ISIL, DPRK, Iran, Libya, Taliban, South Sudan, and others) with names, aliases, dates of birth, nationality, listing date and the narrative summary of why they were listed. Measured: 2,187,321 bytes, dateGenerated 2026-09-28T23:00:01Z.
- **licence**: UN documents are generally free to reproduce with attribution; the sanctions list itself is a public notice. Check UN terms for redistribution in a commercial product.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -L --max-time 60 -o /dev/null -w '%{http_code}' "https://scsanctions.un.org/resources/xml/en/consolidated.xml"` -> 200)
- **why**: 'Who is sanctioned' with the reason and the listing date. UN listings bind member states, so they are the highest-authority version of that claim for a defence-industrial deliverable.
- **caveats**: One file for all regimes - filter by the referenced regime in the record, not by URL. Names are transliterated inconsistently, so match on aliases as well. The dates are ISO timestamps in UTC; the file is regenerated daily, so pin the dateGenerated attribute when citing. OFAC/EU/UK lists are separate sources and are not merged here.

### `unpaywall` - Unpaywall API

- **publisher**: OurResearch (non-profit)
- **base**: https://api.unpaywall.org/v2
- **endpoints**: /v2/<doi>?email=<address>, /v2/<doi>?email=<address>&is_oa=true
- **auth**: free_key - The 'key' is an email address passed as ?email= (his own works and puts him in the polite pool). Registering a dedicated address is optional at https://unpaywall.org/products/api .
- **rate limit**: Documented 100,000 calls/day; the API asks for a real email so it can contact heavy users.
- **format**: JSON
- **cadence**: daily
- **coverage**: Open-access locations for 30M+ DOIs, including publisher-hosted and repository PDFs, with version and licence per location.
- **licence**: Data is open (CC0-style per Unpaywall docs); it links to publisher-hosted copies rather than redistributing them.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.unpaywall.org/v2/10.1038/nature12373?email=faisalnazer2@gmail.com"` -> 200)
- **why**: Turns a paywalled citation into a readable source. When a deliverable cites a paper, this is how the operator actually gets the PDF a machine can OCR.
- **caveats**: Coverage depends on Crossref DOIs - papers without a DOI cannot be looked up. Not every OA location is the version of record (check version/licence fields). The email is required and rate limits are tied to it.

### `usaspending-prime-census` - USAspending API v2 (already installed as usaspending_prime_census)

- **publisher**: US Department of the Treasury, Bureau of the Fiscal Service
- **base**: https://api.usaspending.gov/api/v2
- **endpoints**: /search/spending_by_award/ (POST), /search/spending_by_award_count/, /recipient/, /subawards/, /references/agency/<id>/, /download/
- **auth**: none - No key for the public API. NOTE the TLS caveat: from this machine plain curl fails; add -k (curl) or verify=False (requests/httpx) for *.usaspending.gov, which serves an Entrust-issued chain the local trust store does not complete.
- **rate limit**: Not published; the API consolidates the operator's existing census code, which already paces requests.
- **format**: JSON | CSV
- **cadence**: daily
- **coverage**: All federal prime awards, subawards, recipients, agencies and obligated amounts (FPDS/FFATA sourced) with NAICS, PSC, place of performance and set-aside fields. This is the 'who is buying what' backbone for defence-industrial work.
- **licence**: US government data, public domain; award records are published by Treasury for reuse.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -k -o /dev/null -w '%{http_code}' "https://api.usaspending.gov/api/v2/references/agency/456/"` -> 200)
- **why**: Already installed and working in his harness (the usaspending_prime_census skill). Listed here for completeness so the merged public-data skill routes to the existing census code instead of re-implementing award queries.
- **caveats**: Two traps worth carrying into any new client: (1) TLS - plain requests to api.usaspending.gov fail with 'self signed certificate in certificate chain' on this Mac (Entrust chain), so the code must set verify=False or install the intermediate; (2) the useful endpoints are POST with JSON filters, and the free-text keyword filter behaves differently from NAICS/PSC filters, which is the trap the existing census skill already documents.

### `uspto-open-data-portal` - USPTO Open Data Portal API (successor to PatentsView)

- **publisher**: United States Patent and Trademark Office
- **base**: https://api.uspto.gov/api/v1
- **endpoints**: /patent/applications/search?q=<query> (401 without key: route exists), /patent/applications/<applicationNumber>, /datasets/products/application (bulk product index), https://data.uspto.gov/apis (console + key management)
- **auth**: free_key - API key from https://account.uspto.gov/api-manager/ (USPTO API Manager), passed as the api_key header/param expected by api.uspto.gov; the ODP console at https://data.uspto.gov/apis issues and manages keys.
- **rate limit**: Not published on the pages I could read; USPTO documents per-plan limits in the ODP console.
- **format**: JSON | bulk download
- **cadence**: weekly
- **coverage**: Patent applications and grants (bibliographic, examiner, assignment, PTAB and citation data), trademark records and the bulk dataset products that replaced bulkdata.uspto.gov.
- **licence**: US government works, public domain (17 U.S.C. 105); USPTO bulk data is published for unrestricted reuse.
- **cost**: free (key required)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://api.uspto.gov/api/v1/patent/applications/search?q=hypersonic"` -> 401)
- **why**: Who patented what is a core input to defence-industrial and pharma analysis (assignee concentration, blocking patents, examiner behaviour). This is now the only USPTO machine surface.
- **caveats**: Route mapping by status code: 401 = route exists but needs a key (/patent/applications/search, /datasets/products/application); 403 {"message":"Missing Authentication Token"} = route does not exist (tried /patent/assignments, /trademarks/applications/search, /bulkdata/products). Every HTML path on data.uspto.gov returns the same 20,666-byte JavaScript shell with HTTP 200, so a 200 from that host proves nothing about the data. Not verified with data because I do not hold a key.

### `uspto-tsdr-trademarks` - USPTO TSDR API + trademark bulk data

- **publisher**: United States Patent and Trademark Office
- **base**: https://tsdrapi.uspto.gov
- **endpoints**: /ts/cd/casestatus/sn<serialNumber>/info, /ts/cd/case/<sn>/info, /ts/cd/case/<rn>/info (registrations)
- **auth**: free_key - USPTO API key (X-Api-Key header) from https://account.uspto.gov/api-manager/ . A probe sending X-Api-Key: demo returned 401, confirming the header is the gate.
- **rate limit**: Documented as 5 requests/second for TSDR (and a daily cap); not re-verified in this session.
- **format**: JSON
- **cadence**: daily
- **coverage**: Trademark status, prosecution history, ownership changes and documents for every live and dead US trademark application, keyed by 8-digit serial or registration number.
- **licence**: US government works, public domain; trademark records are published by USPTO for reuse.
- **cost**: free (key required)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://tsdrapi.uspto.gov/ts/cd/casestatus/sn88776655/info"` -> 401)
- **why**: Brand ownership and opposition history expose product-line strategy and shell-company structures that company filings hide; a trademark record is a dated, citable registration.
- **caveats**: The 401 body is a dated warning, quoted exactly: 'Beginning October 2, you'll need to register for an API key to download bulk data from our TSDR APIs. Register for an API key at https://account.uspto.gov/api-manager/.' I could not retrieve data without a key, so verified=false. The old developer.uspto.gov URLs now 301 to data.uspto.gov.

### `wayback-cdx-api` - Internet Archive Wayback CDX + timemap API

- **publisher**: Internet Archive
- **base**: https://web.archive.org
- **endpoints**: /cdx/search/cdx?url=<url>&output=json&limit=N&from=<yyyymmdd>&filter=statuscode:200, /web/timemap/link/<url>, /web/wayback/available?url=<url>&timestamp=<ts>
- **auth**: none - No key. Add a contact User-Agent; the CDX endpoint throttles aggressive crawlers (>~15 requests/minute can 429/503).
- **rate limit**: Not formally published: measured 16 s for a filtered CDX call, and the availability API answered instantly. Space requests and use limit=/filter=.
- **format**: JSON | XML
- **cadence**: daily
- **coverage**: Capture history for ~900 billion web resources since 1996, with timestamp, status code, MIME type, digest and length per capture; timemap returns the full capture list for one URL.
- **licence**: Archived page content belongs to its original publisher; IA's terms and robots-based exclusions apply (https://archive.org/about/terms.php).
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" --max-time 60 -o /dev/null -w '%{http_code}' "https://web.archive.org/cdx/search/cdx?url=sam.gov&output=json&limit=1&from=2024&filter=statuscode:200"` -> 200)
- **why**: Evidence of what a page said, and when: award notices, sanctions entries, procurement pages and price lists that were later edited or deleted. For a deliverable that must carry a source, a snapshot URL with a timestamp is the strongest citable form of a changed claim.
- **caveats**: web.archive.org was slow enough to time out on my first attempt at a 15 s limit (curl exit 28) and succeeded at 60 s - set generous timeouts and retry. CDX output is a list of TSV-style arrays, the first row being the header when output=json. Filters (statuscode, mimetype, timestamp) are the difference between a fast call and a timeout.

### `wikidata-sparql` - Wikidata Query Service (SPARQL)

- **publisher**: Wikimedia Deutschland / Wikimedia Foundation
- **base**: https://query.wikidata.org/sparql
- **endpoints**: /sparql?query=<SPARQL>&format=json, /sparql?query=...&format=csv
- **auth**: none - No key; a descriptive User-Agent is required by Wikimedia policy, and heavy users should use the query.wikidata.org endpoint responsibly.
- **rate limit**: Documented as 60 seconds of query time per query and a request rate limit per IP; long queries time out rather than queue.
- **format**: JSON | CSV | RDF
- **cadence**: real-time
- **coverage**: 100M+ structured entities with identifiers that join to external registries: company HQ, parent organisation, stock exchange listings, people and their positions, plus every Wikipedia language link. Measured: a SPARQL query returns results but itemLabel is empty unless you add SERVICE wikibase:label - the labelled version returned names correctly.
- **licence**: Wikidata is CC0 (public domain dedication); third-party content imported into it may carry attribution requirements.
- **cost**: free
- **verified**: True (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -H 'Accept: application/sparql-results+json' -o /dev/null -w '%{http_code}' "https://query.wikidata.org/sparql?query=SELECT%20%3Fitem%20%3FitemLabel%20WHERE%20%7B%3Fitem%20wdt%3AP31%20wd%3AQ11424.%20SERVICE%20wikibase%3Alabel%20%7B%20bd%3AserviceParam%20wikibase%3Alanguage%20%22en%22.%20%7D%7D%20LIMIT%202&format=json"` -> 200)
- **why**: Entity resolution with free reuse rights: turning a company or person name into a stable Q-id with headquarters, parent, and cross-references is what makes a cross-source join defensible, and CC0 removes licence risk from a published memo.
- **caveats**: Without SERVICE wikibase:label (or an explicit ?itemLabel filter) the label column comes back empty - the classic silent failure. Some statements have qualifiers and deprecated ranks; use the property's normal-rank statement. Entity coverage of private companies and defence suppliers is patchy by design, so treat missing data as unknown, not as false.

### `wipo-patentscope` - WIPO PATENTSCOPE (no public API - documented negative)

- **publisher**: World Intellectual Property Organization
- **base**: https://patentscope.wipo.int
- **endpoints**: /search/en/search.jsf (web UI only), /search/rss.jsf?query=<q> (404 - does not exist)
- **auth**: none - WIPO publishes no anonymous REST/RSS API for PATENTSCOPE; searching requires the JSF web UI and its session state.
- **rate limit**: Web UI behaviour; WIPO's terms discourage automated access.
- **format**: JSON | XML
- **cadence**: irregular
- **coverage**: PCT international applications and collections from many national offices, with useful coverage of non-US, non-EPO filings.
- **licence**: WIPO terms of use for PATENTSCOPE; automated extraction is restricted on the site. Use national offices (USPTO ODP, EPO OPS) for machine access to the same documents.
- **cost**: free (web only)
- **verified**: False (`curl -sS -A "prime-agent research contact:faisalnazer2@gmail.com" -o /dev/null -w '%{http_code}' "https://patentscope.wipo.int/search/rss.jsf?query=hypersonic"` -> 404)
- **why**: Kept in the inventory so nobody builds against it: PCT filings matter for who is protecting inventions internationally, but there is no machine interface, and a skill that assumes one will fail.
- **caveats**: Measured: /search/en/search.jsf returns 302 (session redirect) to a scripted client, /search/rss.jsf returns 404. A JSF-token-driven scrape is the only path and that is what WIPO's terms discourage, so this lane recommends against it.
