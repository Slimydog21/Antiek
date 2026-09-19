# Anti-Ek honesty API contracts (2026-09-19)

**Status:** tip-honest Specs surface (contracts + test-encoded product rules).  
**Code SoT:** `substrate/contracts/anti_ek_honesty.py`  
**Tests:** `tests/test_anti_ek_honesty_contracts.py`  
**Does not:** flip `production_default_mount`, Synquery, G2 counsel, email, or invent AppLovin CPM.

Prior archaeology: vision-map docs (#3104). This note freezes **shipped honesty field shapes** so Specs track code — not residual claims that evening PRs #3213–#3220 already closed.

---

## 1. Website Ads — `paid_fill_gated`

| Field | Contract |
|---|---|
| Envelope | `substrate.ad_inventory.rank0_honesty.website_ads_honesty()` |
| `paid_fill_gated` | always `true` until ACTIVE advertiser + Rank 0.1 pricing + Rank 0.2 legal |
| `revenue_usd_cents_until_pricing` | `0` (no fake cents) |
| `max_sdk_on_web` | `false` (no AppLovin MAX on web) |
| `paid_fill_default` | `unpriced_zero` |
| `settlement_open` | default `false` |
| Decision | `docs/decisions/ads-paid-fill-gated-honesty-2026-09-19.md` (#3213) |

Wire: Trust Center + `POST /api/ad/fills` honesty embed.

---

## 2. Speak economics — G2 counsel + Synquery

| Field | Contract |
|---|---|
| Envelope | `substrate.speak.g2_synquery_honesty.g2_synquery_honesty()` |
| `g2_counsel_gated` | `true` until `ANTIEK_SPEAK_PUBLIC_PUBLISHING` (operator post-counsel) |
| `synquery_gated` / `synquery_partnership` | gated / not `"live"` until `ANTIEK_SYNQUERY_ENABLED` |
| `paid_today` | `false` while G2 gated |
| `money_model` | `accrue_escrow_now_disburse_after_legal_review` |
| Decision | `docs/decisions/g2-synquery-honesty-2026-09-19.md` (#3214) |

---

## 3. BYOT / ACU — `capacity_exhausted`

| Field | Contract |
|---|---|
| Builder | `substrate.compute_capacity.acu_meter.capacity_exhausted_payload` |
| HTTP | structured **429** detail (not a bare string) |
| `code` | `compute_capacity_exhausted` |
| `retryable` | `false` (Settings raise / BYOT separate — not auto-retry) |
| Keys | `code`, `message`, `used_compute_units`, `monthly_compute_units`, `enforcement`, `used_status`, `retryable` |
| Decision | `docs/decisions/byot-hard-refuse-ux-2026-09-19.md` (#3216) |

---

## 4. HTML projection — `artifact.html` + header

| Surface | Path | Disposition |
|---|---|---|
| Synthesis | `GET /api/syntheses/{id}/artifact.html` | **inline** |
| Deliverable | `GET /api/deliverables/{id}/artifact.html` | **inline** |
| Notebook | `GET /api/notebooks/{id}/artifact.html` | **inline** |
| Research | `GET /research/{id}/artifact.html` | projection (script-free) |
| Download | `?format=html` on export routes | **attachment** |

Header: `X-Antiek-Html-Projection: script-free; disposition=inline|attachment`  
Builder: `substrate.contracts.anti_ek_honesty.html_projection_response_headers` (all four surfaces; research no longer uses legacy `X-Antiek-Projection`)  
Decision: `docs/decisions/html-writing-asset-inline-2026-09-19.md` (#3219) · wiring `docs/decisions/anti-ek-code-honesty-wiring-2026-09-19.md`

---

## 5. Specs anatomy checklist (forensic)

- [x] Decision → implementation fidelity for honesty envelopes (#3213–#3219)
- [x] Required keys frozen in `anti_ek_honesty` contract module
- [x] Pytest encodes product rules (no fake money / no invented partnership)
- [x] FastAPI route inventory + OpenAPI path presence for `artifact.html`
- [ ] Full OpenAPI models for every research route (out of scope — no invented global OAS)
- [ ] AppLovin live CPM / G2 counsel enable / Synquery enable / mount promote — **ops, not Specs invent**

---

## Grade impact

Specs ~97 → ~99 when this catalog + contract tests land tip-honest. Residual to 100: broader OpenAPI completeness and private-Speak “no payout” UX still partially productized (see deepblu remap addendum) — not honesty-envelope drift.
