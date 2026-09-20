# Antiek Publisher Ecosystem — Product & Strategy Spec

**Date:** 2026-08-12  
**Status:** Research-complete, operator review pending  
**Authoritative on:** Publisher-facing product surfaces, marketplace strategy, licensing posture, equity mechanics  
**Reads with:** `master-product-spec.md` §9, §9.0, §9.0.1, §9.6, §9.10, §16; `integration_applovin.md`

---

## 1. Executive summary

Antiek's publisher ecosystem has two products and one legal frame. The products: **(1)** direct digital book/ebook purchases inside Antiek's marketplace (owned and read inside Antiek, with AI-augmented deep research and cocktail reading), and **(2)** a research-ingestion API (user pays a discounted price for agent notes + analysis of a publisher asset, with NO reading access — the publisher never gives away free reading, and ad attribution over time drives the effective price to zero). The legal frame is the Bartz v. Anthropic procurement-based compliance posture, enforced through retrieval-time gating, user-upload ownership, and publisher opt-in escrow per the master spec's §9.0 and §9.10. The sweet-deal mechanics for publishers — ad rev-share, attribution transparency, opt-in pre-onboarded escrow, Spotify-style equity (12% first-3-signers / 3% rest, ≤15% combined cap) — are designed to be structurally irresistible without poisoning the cap table. Infrastructure hosting has a v1 decision: self-host Stripe Checkout on `antiek.ai/store` as the initial purchase rail, then evaluate whitelabel marketplace migration (Lemon Squeezy or Payhip) once volume justifies the integration tax.

---

## 2. Product #1 — Direct digital book purchases in Antiek marketplace

### 2.1 What it is

A user discovers a book inside Antiek (through research, citation chains, or the storefront at `antiek.ai/store`), purchases it, and gains **ownership of the digital asset inside Antiek**. This is not a PDF download. It is a purchase that entitles the user to:

- **Read the book** inside Antiek's HTML-first reading surface (the MASTER.md viewer extended with book-length reading — pagination, table of contents, inline citations linking to the user's personal graph).
- **Deep-research on the book**: branch off investigation threads from any passage; the book is a first-class source in the personal graph, citeable like any other document.
- **Fork/merge**: take a publisher's original text and fork your own annotated, cross-referenced copy. Other users can see (and optionally merge) your public annotations — this is the collaborative research layer.
- **AI re-length**: ask Antiek to produce a 5-page executive summary, a 30-page abridged version, or expand a dense passage into a textbook-length exposition. All transformations cite back to the original purchase.
- **Cocktail reading**: interleave the book with notes from your personal graph. Reading a history book side-by-side with your own notes from primary sources on the same topic. The personal-graph-as-memory architecture (§13.2) makes this possible because every chunk you own or wrote lives in ONE personal graph.

### 2.2 Why it's not an ebook store

The operator's vision is not "compete with Kindle." It's "books are data that you own and that compound inside your research environment." The purchase event is the **entry point into the Antiek ecosystem** for a publisher's corpus. Once a user owns a book inside Antiek:

- Every future investigation that cites it flows attribution back to the publisher.
- Every ad impression on pages grounded in that book routes 70% rev-share to the publisher.
- The user's own notes and branches become a distribution surface for the publisher's IP — a user who writes brilliant annotations on a Cambridge University Press monograph is effectively marketing that monograph to every peer who sees their public notes.

This is the Spotify-vs-iTunes distinction: Spotify didn't sell MP3s; it built a consumption ecosystem where listening generates recurring revenue for rights-holders. Antiek doesn't sell ebooks; it builds a reading+research ecosystem where owning a book generates compounding attribution revenue for publishers.

### 2.3 The purchase flow

1. User discovers book via research, search, or `antiek.ai/store`.
2. Purchase via Stripe Checkout (or embedded Stripe Payment Element on the `antiek.ai` surface).
3. Post-purchase, the book lands in the user's personal graph as a `document` with `source: purchased`, `ip_holder_id` populated, and `content_class: owned_book`.
4. The book is immediately available for reading, annotation, branching, and AI re-length.
5. Every research action involving the book accrues attribution telemetry (already shipped Sprint 16) — no payouts until publisher opt-in per §9.0 gate.

### 2.4 Pricing model

Publisher-set price (Antiek takes platform margin; operator to decide margin % — master spec §13.5 establishes 50% managed-service margin on private use and 10% on public use; book purchases are a distinct transaction type that could adopt a flat 15-30% platform fee, consistent with industry norms for digital marketplaces). The price is a one-time purchase, not a subscription. The purchase does not include redistribution rights — the user owns their copy inside Antiek, not a resalable license.

---

## 3. Product #2 — Research-ingestion API (the publisher on-ramp)

### 3.1 What it is

A user wants access to the *knowledge inside* a publisher's book but does not need (or cannot afford) the full purchase price. Antiek offers a **research-ingestion tier**: the user pays a discounted price (e.g., 30-50% of the full purchase price) and receives:

- **Agent-generated notes + analysis** of the book: a structured synthesis generated by Antiek's synthesizer, verifier, and decomposer pipeline.
- **Cited excerpts**: key passages surfaced as evidence chunks, with inline citations back to the original.
- **Deep-research branches**: the ability to ask questions against the analysis and get provenance-grounded answers.

What the user does NOT get: **reading access to the full book**. They cannot open the book and read it cover-to-cover. They get the AI-mediated knowledge extraction, not the source text.

### 3.2 Why this works for publishers

This is the on-ramp that makes the publisher comfortable with Antiek's research product. The publisher's core fear is cannibalization: "if an AI can summarize my book, nobody will buy it." The research-ingestion product addresses this by:

1. **Never giving away the full text.** The user cannot read the book — they get notes and analysis, which are *derivative works* of the book, not the book itself. This is the same logic as a book review or a study guide, which publishers have accepted for centuries.
2. **Discount, not free.** The user pays money, which routes to the publisher. This is not a free-riding arrangement.
3. **Ad attribution drives price to zero over time.** As the ad ecosystem matures (Sprint 23+), the ad revenue attributed to the book's chunks subsidizes the research-ingestion price. The operator's vision: publishers eventually drop the API payment gate entirely because ad revenue + attribution transparency + ecosystem growth makes it more profitable to let users ingest freely and earn from the downstream attention economy. This is the long game stated in the master spec: "the operator prefers publishers to eventually drop API payment gates for max ad revenue."

### 3.3 The pricing arc

| Phase | User price for research-ingestion | Publisher revenue |
|---|---|---|
| Phase 1 (Sprint 19-22, pre-ad) | 30-50% of full purchase price | Purchase price × platform margin |
| Phase 2 (Sprint 23+, ads live) | 20-30% of full purchase price | Purchase + ad rev-share (70%) |
| Phase 3 (Sprint 30+, mature ads) | Free or near-free | Ad rev-share dominates; purchase price becomes vestigial |

This is the mechanism the operator described: **ad revenue grows until it displaces the paywall.** The purchase and API gates are scaffolding for a world where publishers earn more from the attention economy than from unit sales.

---

## 4. Licensing and compliance posture (Bartz v. Anthropic alignment)

### 4.1 The procurement firewall

Per master spec §9.0: **the dispositive variable is procurement, not use.** Antiek must never be the entity that fetches copyrighted content on behalf of users. The platform is hosting infrastructure; the user is the fetch agent. Architectural commitments:

- **User uploads documents they have legitimate access to.** Research papers they purchased, books they own, notes they wrote. The platform processes them. The platform never scrapes copyrighted books and drops them into the user's graph.
- **Retrieval-time gating** (Option C, accepted in §9.0): restricted-class content cannot be retrieved into a synthesis that triggers attribution unless `policy_tag in {"private_research", "operator_only"}`.
- **No payouts on an ungated graph** (§16.2): Sprint 18 ships Stripe Connect only after retrieval-time gating is in production AND at least one publisher has opted in.

### 4.2 Publisher opt-in escrow (Kalshi pattern)

Per §9.10: pre-onboarded IP holder accounts with escrow accruing but **zero money routed until affirmative opt-in.** The mechanism:

1. Publisher gets a pre-created `ip_holder` record with `status: pre_onboarded`, `claim_status: unclaimed`, `escrow_balance_usd: 0`.
2. Every attributable usage accrues to escrow — verifiable, segregated, in a regulated fiduciary account. NOT commingled with operating funds.
3. Notification email to publisher's legal department: "We are building a platform that uses your published works for AI-mediated research synthesis, in a manner we believe is transformative under fair use, while routing revenue share to you in good faith from day one. We invite you to claim your account and accept payments accrued to date."
4. If publisher opts in: `claim_status: claimed`, Stripe Connect payout unlocks.
5. If publisher opts out: `status: opted_out`, content removal within 30 days.

### 4.3 First-cohort strategy

Per §9.10: MIT Press, Cambridge University Press, Princeton University Press. Academic publishers whose institutional mission includes broad dissemination of knowledge and whose litigation budgets are smaller than the Big Five. Their response calibrates the broader strategy before approaching aggressive rights-holders.

---

## 5. Sweet-deal luring mechanics for publishers

The master spec REJECTs several approaches (§16.2, §9.6) and prescribes specific alternatives. Here is the complete incentive stack:

### 5.1 Ad rev-share: 70% to publisher + creator

Per §9.0.1: 70% of ad revenue from a public note's attention routes to the note's creator (for user-generated content) AND to the publisher (for publisher-owned chunks). Both get 70% of attributable ad revenue. The platform keeps 30%.

### 5.2 Attribution transparency

Per §9.6: the publisher dashboard at `publisher.antiek.ai` shows — in real time — which Antiek synthesis pages cited the publisher's content, attribution shares per page, accrued revenue, and which user investigations drove the most citations. This is transparency no other platform offers. A publisher can SEE their content working inside Antiek.

### 5.3 Opt-in escrow (pre-accrued money)

Per §9.10: money is already waiting. The framing is "we built the payment system before you asked; your money is here; claim it when ready." This converts the publisher's posture from "you stole from us" to "you built a system that pays us and we haven't claimed it yet."

### 5.4 Spotify-style equity (12% first-3 / 3% rest, ≤15% cap)

Per §16.2 REJECTs:

- **No MFN on publisher equity.** Spotify issued preferred shares with NO equity MFN — only standard licensing MFN on rate cards. Equity stake compresses naturally through subsequent rounds. Pulling an equity MFN into the term sheet creates a cap-table block on later capital formation.
- **No publisher equity above 15% combined.** Spotify's combined founding grant was ~17-18% across five rights-holders; compressed to ~7% combined by 2024 (source: TechCrunch, 2009-08-07, Spotify cap table analysis; Music Business Worldwide, 2024). A book platform allocating 15%+ to anchors blocks future capital formation.
- **First 3 signers: 12% combined.** Aggressive allocation to the first movers who take the reputational risk.
- **All subsequent signers: 3% combined.** The gate is tight; latecomers get what's left.
- **No Pearson as textbook anchor** (§16.2). Cengage is the textbook anchor; McGraw-Hill secondary. Pearson approached last, if at all (§9.6).

Spotify's actual cap table (2009, pre-US launch, per Luxembourg filing analyzed by TechCrunch): founders held ~52%, VCs ~28%, labels ~18% (Sony BMG, Universal, Warner, EMI, Merlin collectively). Labels paid approximately the same price as venture investors — ~€100,000 for their aggregate stake. The labels got board seats and licensing MFN. When Spotify IPO'd in 2018, label stakes had compressed to ~7% combined through dilution — and the labels made billions. This is the template Antiek copies: equity as skin-in-the-game, not as control. The music labels didn't control Spotify; they were aligned shareholders who benefited from its growth. Publishers get the same deal.

### 5.5 What publishers give up

- **No paywall on research.** The research-ingestion API is a discount product. Publishers accept that their content becomes part of an AI-mediated knowledge economy where the unit of value is the *citation and the attention*, not the *sale*.
- **No exclusivity.** Antiek does not demand that publishers remove their books from Amazon, Kobo, or any other channel. The Antiek purchase is additive.
- **No content control.** Publishers cannot dictate what users do with their purchased books inside Antiek — the user owns the copy, not a restricted license. This is the same as a physical book purchase.

---

## 6. Infrastructure hosting: self-host vs whitelabel marketplace

### 6.1 The v1 decision: self-host

For Phase 1 (Sprint 19-22, pre-scale), Antiek should self-host the purchase flow using **Stripe Checkout / Stripe Payment Links** embedded on `antiek.ai/store`. Rationale:

- **Zero platform fees beyond Stripe's 2.9% + $0.30.** No Gumroad 10%, no Lemon Squeezy 5% + $0.50, no Payhip 5%. At Phase 1 volumes, avoiding a marketplace middleman preserves margin for both Antiek and the publisher.
- **Full control of the purchase → personal-graph flow.** The purchase event must trigger graph-side effects (document ingestion, `ip_holder_id` population, attribution telemetry enablement). A whitelabel marketplace would require webhook integration that adds latency and failure modes.
- **No tax compliance outsourcing needed at Phase 1 scale.** If Antiek sells primarily to US buyers initially, sales tax complexity is manageable. As international sales grow, evaluate merchant-of-record migration.
- **Stripe's API is the gold standard for developer integration.** Stripe Checkout supports digital goods out of the box. Stripe Payment Links can be generated programmatically per book SKU. The `creator_payouts.py` substrate already targets Stripe Connect for publisher payouts — the purchase rail is Stripe-native.

### 6.2 When to migrate to a whitelabel marketplace

| Trigger | Migration candidate |
|---|---|
| International VAT compliance becomes painful | Lemon Squeezy (merchant of record; 5% + $0.50) |
| Volume exceeds 1,000 transactions/month and Payhip Pro ($99/month, 0% platform fee) beats Stripe-only economics | Payhip |
| Publisher demand for a branded storefront with discovery features | Gumroad (10% but includes Discover marketplace) |
| Need for print-on-demand physical books (unlikely for Antiek v1) | Lulu API (print + distribution) |

**Comparison of self-hostable / API-driven digital marketplace options (August 2026):**

| Platform | Platform fee | Merchant of record | API quality | Best for |
|---|---|---|---|---|
| **Stripe Checkout/Payment Links** | 2.9% + $0.30 (processing only; no platform fee) | No (you handle tax) | Industry gold standard | Self-hosted purchase flow; maximum control |
| **Payhip** | 5% free plan; 2% Plus ($29/mo); 0% Pro ($99/mo) | Partial (EU VAT only) | Limited API | Low-fee digital product sales |
| **Lemon Squeezy** | 5% + $0.50 | Yes (full global tax) | Good REST API | SaaS + international digital goods; tax outsourcing |
| **Gumroad** | 10% flat | Yes | Decent API | Creator marketplace with built-in discovery |
| **FastSpring** | 5.9% + $0.95 (volume discounts) | Yes (full MoR) | Strong REST API | B2B SaaS; enterprise digital goods |
| **Shopify** | $29/mo Basic + 2.9% + $0.30 | Configurable (Shopify Tax) | Strong Storefront API | Full ecommerce; headless storefront |
| **Lulu (API)** | Print cost + markup; no digital-only fee | No | Strong print API | Print-on-demand books |
| **Draft2Digital / Kobo Writing Life** | ~10% of list price | No | No self-host API | Ebook distribution to retailers (not self-hosted) |

Sources: biztoolkit.co, 2026-07; plugyourbuild.com, 2026-07; Stripe docs, 2026-08; FastSpring developer docs, 2026-08; Lulu Developer Portal, 2026-08; Shopify.dev, 2026-08.

**Recommendation:** Start with Stripe Payment Links embedded in the Antiek surface. Stripe's API generates a payment link per book SKU; the link is embedded in the book's `antiek.ai/store` page. On successful payment, a webhook triggers the book ingestion into the user's personal graph. This is a 1-2 week integration. Re-evaluate Payhip Pro migration when monthly transaction volume exceeds 1,000 (break-even: $99/mo vs 5% × transaction volume; at $2,000 monthly GMV, Payhip Pro saves ~$1/month over the free plan; at $10,000 GMV, saves ~$401/month).

### 6.3 How Spotify and Amazon did it early (and what Antiek copies vs rejects)

**Spotify (2006-2009):**
- **Hosting:** Self-built streaming infrastructure on a peer-to-peer architecture (early desktop client used P2P to reduce server costs; shifted to pure server-side streaming as it scaled).
- **Licensing:** Bilateral deals with each major label. No marketplace intermediary. Spotify's BD team negotiated directly with Universal, Sony, Warner, EMI, and Merlin.
- **Equity:** Issued ~18% combined to labels at founding, with NO equity MFN. Labels paid ~€100K aggregate for their stake. Equity aligned incentives: labels wanted Spotify to succeed because they were shareholders.
- **Copy:** Spotify bet that ad-supported + premium subscription would generate more revenue than piracy. They were right: global recorded music revenue hit $28.6B in 2023, the highest since 1999 (IFPI Global Music Report 2024).
- **Antiek copies:** Direct publisher deals (not through a marketplace middleman), equity-as-alignment (12/3% split), ad-supported consumption as the long-term revenue engine.
- **Antiek rejects:** Spotify's royalty-per-stream model (Antiek uses attribution-weighted ad rev-share instead), Spotify's subscription-primary monetization (Antiek's Phase 1 is pay-as-you-go token-budget per §9.0.1).

**Amazon (Kindle/KDP, 2007-present):**
- **Hosting:** Amazon-hosted everything. Kindle books lived on Amazon's servers; users streamed/downloaded to Kindle devices. No self-host option for publishers — Amazon's walled garden.
- **DRM:** Amazon's proprietary DRM locked books to Kindle devices/apps. Publishers could opt out of DRM (and many indies did) but Amazon's default was DRM-on.
- **Marketplace:** Amazon built both the storefront AND the reading device. The Kindle was loss-leader hardware that locked users into Amazon's book ecosystem. Publishers got 70% royalty on KDP (if priced $2.99-$9.99) or 35% outside that range.
- **Self-publishing:** KDP (Kindle Direct Publishing) launched alongside Kindle, letting anyone publish. This was the wedge that disrupted traditional publishing: indies could reach Amazon's audience without a publisher.
- **Antiek copies:** HTML-first reading inside the platform (Kindle proved users will read inside an ecosystem), self-serve publisher onboarding (KDP's lesson: make it trivial for publishers to list content).
- **Antiek rejects:** DRM. Antiek books are HTML with attribution — no proprietary DRM. The moat is the personal graph, not access control. Proprietary hardware. Antiek is a web surface, not a device. Walled-garden exclusivity. Antiek books are additive to other channels, not exclusive.

---

## 7. Decisions needed from operator

1. **Platform margin on book purchases.** Master spec §13.5 establishes 50% on private use and 10% on public use. Book purchases are neither — they are one-time transactions. Recommend 15-30% to be competitive with industry norms (Amazon KDP: 30%; Gumroad: 10%; industry norm for digital marketplaces: 15-30%). Ratify a number.
2. **Research-ingestion pricing discount.** What % of full purchase price? Recommend 30-50% for Phase 1, decreasing as ad revenue grows per the pricing arc in §3.3.
3. **First-cohort publisher outreach timing.** Sprint 19 per master spec. Confirm: send notification emails to MIT Press, Cambridge UP, Princeton UP as first batch. Lawyer must review email language before any email sends (§9.10, binding).
4. **Equity instrument.** Spotify used preferred shares with no equity MFN. Confirm preferred shares (not common, not SAFE) for publisher equity grants. Confirm 12% combined for first 3 signers / 3% for all subsequent.
5. **Self-host (Stripe) vs whitelabel marketplace.** Recommend Stripe Checkout for v1. Confirm.
6. **Cengage as textbook anchor.** Master spec §16.2 names Cengage as the textbook anchor, McGraw-Hill secondary, Pearson last. Confirm this publisher sequence before Sprint 19 outreach planning.

---

## Sources

- Antiek Master Product Spec (§9, §9.0, §9.0.1, §9.6, §9.10, §16, §16.1, §16.2), `/tmp/antiek-sharpen-main/docs/master-product-spec.md`
- Antiek × AppLovin Integration Spec, `/tmp/antiek-sharpen-main/docs/integration_applovin.md`
- Antiek ad substrate: `ad_routes.py`, `ad_impressions.py`, `advertisers.py`, `creator_payouts.py`, `auction_features.py`, `/tmp/antiek-sharpen-main/`
- TollBit platform documentation, https://tollbit.com/docs/ and https://docs.tollbit.com/docs/ (accessed 2026-08-12)
- TollBit Publisher Licensing 2026, Presenc AI, https://presenc.ai/research/tollbit-publisher-licensing-2026 (April 2026)
- Gumroad vs Payhip vs Lemon Squeezy 2026, biztoolkit.co, https://www.biztoolkit.co/post/gumroad-vs-payhip-vs-lemon-squeezy-2026-best-platform-for-digital-products (2026-07)
- Stripe Checkout / Payment Links documentation, https://docs.stripe.com/payments/checkout and https://docs.stripe.com/payment-links/create (accessed 2026-08-12)
- FastSpring Developer Docs, https://developer.fastspring.com/ (accessed 2026-08-12)
- Lulu Developer Portal, https://help.api.lulu.com/ (accessed 2026-08-12)
- Shopify Headless / Storefront API, https://shopify.dev/docs/storefronts/headless/ (accessed 2026-08-12)
- Spotify Cap Table Analysis, TechCrunch, https://techcrunch.com/2009/08/07/this-is-quite-possibly-the-spotify-cap-table/ (2009-08-07)
- Spotify Label Equity Stakes Worth, Music Business Worldwide, https://www.musicbusinessworldwide.com/heres-exactly-how-many-shares-the-major-labels-and-merlin-bought-in-spotify-and-what-we-think-those-stakes-are-worth-now/ (2024)
- Music Labels Cut Friendlier Deals With Start-Ups, CNBC / Reuters, https://www.cnbc.com/2009/05/28/music-labels-cut-friendlier-deals-with-startups.html (2009-05-28)
- Kindle Direct Publishing, Wikipedia, https://en.wikipedia.org/wiki/Kindle_Direct_Publishing
- Amazon Kindle Launch, NYT, https://www.nytimes.com/2007/11/20/business/20bookxx.html (2007-11-20)
- Bartz v. Anthropic settlement (September 5, 2025) — referenced in master spec §9.0
- Hachette v. Internet Archive, Second Circuit (September 4, 2024) — referenced in master spec §9.0
- Authors Guild MDL (In re OpenAI Inc. Copyright Infringement Litigation, MDL No. 3143) — referenced in master spec §9.0
