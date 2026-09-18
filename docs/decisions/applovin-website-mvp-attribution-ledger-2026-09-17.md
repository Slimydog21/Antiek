# Decision — AppLovin website MVP + attribution ledger sketch (no live production ads)

**Date:** 2026-09-17 (Asia/Riyadh)
**Status:** DECISION recorded (plan + locate priors). **No live AppLovin / MAX / pixel integration into production in this change.**
**Reads with:** `docs/integration_applovin.md`, `docs/master-product-spec.md` §9 / §9.0 / §9.1 / §9.8, `docs/specs/ad-v1-scalable-2026-08-12.md`, `docs/specs/publisher-ecosystem-2026-08-12.md`, `docs/decisions/read-frontend-sprints-on-existing-surface.md` (AdBorder), `docs/decisions/afa-synthesis-attribution-canonical.md`, Mini companion `~/Antiek/specs/antiek-frame-attribution/`
**Client chain (locked):** website → iPad → Duo → Android. **This doc scopes website only.** Duo / iPad / native MAX are roadmap notes, not build work.

---

## 1. Where the ideas already lived (forensic index)

| Idea | Authoritative home | What it already says |
|---|---|---|
| AppLovin / Axon / MAX | `docs/integration_applovin.md` (2026-07-02, merged #118) | **Copy the Axon learning loop in-substrate; never adopt the AppLovin network for web supply.** MAX has no web publisher SDK. W1+W2 INTEGRATE NOW; W3 demand DEFER; W4 MAX DEFER/possibly REJECT. R1–R8 REJECTs (pixel, Adjust, external auction as serving gate, network metrics as truth, …). |
| 70/30 Spotify-like payback | `master-product-spec.md` §9.1 + §9.0.1; `publisher-ecosystem-2026-08-12.md` §5 | Platform 30% / contributors 70%. Spotify is the *ecosystem* precedent (recurring attribution revenue, equity alignment) — not a royalty-per-stream copy. |
| Per-second / per-frame attribution | `integration_applovin.md` §7; substrate `frame_attention*.py`; Mini `~/Antiek/specs/antiek-frame-attribution/` | 1 Hz FrameSecond samples → window batch → largest-remainder cents → escrow. Six gaps S1–S6; S1 (server-minted value) shipped (#142 / AFA-S1 lineage). |
| `ad_eligible` gate | `substrate/rights/ad_eligibility.py`; books API + `apps/reading/src/api/books.ts`; Reading `index.tsx` | **T1 only** for arXiv (`ads_allowed(tier)`). Books serve payload exposes `ad_eligible`; UI mounts `AdBorder` only when `ad_eligible && pages.length > 0`. |
| Lemon / reading UI ad stub | `AdBorder.tsx` + `HouseSlot.tsx`; `read-frontend-sprints-on-existing-surface.md` | Thin **top/bottom** rails only — never beside the reading column. Default fill is **house** (honest placeholder title: no live ad / no revenue yet). |
| Manual sponsor → lead-gen → programmatic | `master-product-spec.md` §9.4 / §9.8 | Phase 2 footer sponsor → Phase 4 vertical lead-gen → Phase 5 auction only if scale warrants. |
| Publisher / write-surface payback | `publisher-ecosystem-2026-08-12.md`; Speak `spr-10-ai-graded-payout.md` | Publishers + on-platform research authors + write-page creators earn when ads show on surfaces that used their work; Speak payout is escrow-only until G2/G3. |
| Gap-ranked build plan | `docs/specs/ad-v1-scalable-2026-08-12.md` | Ranks 0–5: pricing/legal → trust → composition → audit → Axon labels → manual sponsor. |

**Drive:** no Antiek-specific AppLovin/payback notes found in Google Drive search (2026-09-17); repo + Mini specs are the corpus.

**Important doctrine reconciliation:** product intent “ads via AppLovin for website” means **Axon-style in-house ranking + Antiek-owned fill/ledger**, *not* dropping MAX/ALX or the Axon pixel onto the site. Verified AppLovin portfolio fact: **no JavaScript/web publisher SDK**. Website money path stays Antiek-served creatives (house → manual sponsor → lead-gen). Apple ads infra / MAX remain **phone/native later**.

---

## 2. Decision — dual structure (ledger vs creative)

### 2.1 Ledger (DuckDB / substrate) — source of payable truth

```
impression window
  → GET /api/ad/fill  (persist fill decision when Rank 4.1 lands)
  → AdBorder / house|sponsor creative (UI projection only)
  → 1 Hz frame samples (client) → POST /api/ad/frame-telemetry
  → server-minted window value (S1; client cents ignored)
  → IVT filter (S2) → attention weights
  → if synthesis surface: §9.3 share vector composition (S3; Option B default)
  → frame_attention_accruals  ← SINGLE payable ledger for reading attention
  → compose_split_pipeline (S5): carve-outs → 70/30 → per-doc → holders
  → ip_holders escrow (disbursable=False until G2 lawyer + G3 opt-in)
```

**Who gets paid from one impression** (sketch):

| Surface | Eligible payees (70% pool) | Gate |
|---|---|---|
| **Read** (book / paper page) | Document `ip_holder_id` (publisher/writer of cited book or T1 paper) | `ad_eligible` (T1 / monetization_eligible); private `user_owned` → $0 |
| **Research** (MASTER.md / synthesis) | Holders of documents whose chunks drove claims, via §9.3 Option B | Same + synthesis composition (S3) |
| **Write** (public note / writing page) | Note creator as IP holder (§9.0.1 / §13.9) | Public-graph contribution; ads only if surface marks eligible |
| Residuals | `UNATTRIBUTED_RIGHTS_BUCKET` | Never silent drop |

Weights: **per page** (which assets were on-screen) × **per second** (FrameSecond attention) × **insight contribution** (synthesis share vector). Cent conservation via shared largest-remainder primitive.

### 2.2 Creative (HTML / Lemon UI) — projection only

- Creative is an HTML/UI fill (`AdFillView`: `ad` | `house`) rendered by `AdBorder`.
- **Never** the revenue truth. AppLovin-reported metrics stay REJECT (R6).
- Desktop: non-disruptive top/bottom borders; reading column sacred.
- Phone UX: careful — same borders, denser; no interstitial/MAX until native app + W4 unlock.
- Stub already required by prior Read SPR-05: house fill + honest tooltip. **Keep stub; do not wire live AppLovin demand.**

---

## 3. Website-first integration steps (executable order)

**Do not** integrate live AppLovin Ads, MAX, Axon pixel, or Adjust.

1. **Keep / harden the existing Read stub** — `AdBorder` + house fill gated on `body.ad_eligible` (already shipped). Verify books API continues to map `ad_eligible` from `ads_allowed(tier)` / serve guard.
2. **Next executable website step (recommended):** implement **§9.8 Phase 2 manual sponsor slot** on the **MASTER.md / research synthesis footer** (and optionally reuse `AdBorder` bottom rail) behind a feature flag:
   - Fill kind: `BiddingPolicy.MANUAL_SPONSOR` (enum exists; code paths incomplete — see ad-v1 Rank 5).
   - Creative: static HTML sponsor card (operator-sold), **not** a network tag.
   - Ledger: still `$0` or flat monthly fee booked offline until Rank 0.1 pricing + legal gate; telemetry may record window + attribution shares with `disbursable=False`.
3. **Parallel substrate (no UI ads required):** close remaining W2 gaps S2→S5→S6 per `ad-v1-scalable` / Mini frame-attribution sprints; persist fill decisions (W1 step 0) for the Axon-style label loop.
4. **Write surface (after Read+Research footers feel non-harmful):** mount the same `AdBorder` pattern on public write pages when the page is ad-eligible — never inline mid-paragraph.
5. **Stop condition for “live ads”:** operator legal gate (§9.0) + at least one ACTIVE advertiser with settled pricing + server-minted non-zero value + IVT filter on. Until then, house/sponsor stub only.

### Lemon surfaces — where ads may show without harming reading

| Surface | Placement | Harm rule |
|---|---|---|
| Reading column | Top + bottom `AdBorder` only | Never left/right; never shrink column |
| MASTER.md / Research | Footer sponsor slot | Below thesis; no interstitial |
| Write (public) | Footer / bottom rail | Not inside editor canvas |
| Speak / private / settings | **No ads** | Out of scope |

---

## 4. Duo / iPad / Android — roadmap only

- **iPad / Duo / Android:** AppLovin MAX *might* become relevant only after a native app exists **and** W4 unlock criteria fire (`integration_applovin.md` §13.4). Recorded SSP Plan-B remains Google Ad Manager / Magnite, not AppLovin-by-default.
- **Apple ads infra for phone:** later, after website MVP proves the attribution ledger.
- **No native app work in this decision.**

---

## 5. Grade — ads / payback anatomy **/100**

| Dimension | Score | Note |
|---|---|---|
| Doctrine clarity (70/30, BYOT vs ads, legal gate) | 18/20 | Locked in §9; escrow ≠ disbursement is strong |
| Attribution design (page × second × insight) | 17/20 | Frame pipeline + §9.3 A/B/C real; S3 composition still the critical gap |
| AppLovin honesty (web vs native) | 18/20 | Spec correctly rejects web MAX/pixel; Axon-as-posture is the right read |
| UI stub / Lemon non-disruption | 14/15 | AdBorder + house honesty already good |
| End-to-end money readiness | 8/15 | Pricing ~$0, split composition unpublished, G2/G3 closed, multi-ledger risk |
| Cross-surface payback (read/research/write) | 7/10 | Read gated; synthesis composition + write footer still incomplete |
| **Total** | **82/100** | Anatomy is unusually complete for pre-revenue; payable close still blocked on composition + legal + pricing |

---

## 6. Explicit non-goals (this PR / this decision)

- No AppLovin SDK, pixel, MAX, ALX, or Adjust.
- No production revenue disbursement.
- No Duo/iPad/Android native work.
- No secrets in docs.

## 7. Next agent one-liner

Ship **BYOT capacity slider** (or close W2 S2 IVT / S3 synthesis composition) — Phase-2 manual sponsor now persists `ad_fill_decisions` via `POST /api/ad/fills` (research lens, $0 unpriced, `bidding_policy=manual_sponsor` in fills_json). Still no live network ads / disbursement.
