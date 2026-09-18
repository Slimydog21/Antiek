# Decision — Anti-Ek Speak remapping: DeepBlu → Speak → ad_fill attribution (no new ledger)

**Date:** 2026-09-18 (Asia/Riyadh)
**Status:** ratified (docs-only). Remaps prior DeepBlu vision onto **already-executed** Antiek Speak + the locked AppLovin attribution ledger. Does **not** introduce schema, payout APIs, or a second accruals table.
**Base tip at authoring:** `origin/main` @ `7f665826d` (#3140 ACU meter — Speak lane does not touch ACU).
**Reads with:** `docs/master-product-spec.md` §11 / §12 / §9; `docs/decisions/speak_workflow.md`; `docs/decisions/speak-private-public-spine.md`; `docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md` (#3103); `docs/decisions/afa-escrow-double-credit.md`; `docs/anti-ek-vision-map-2026-09-17.md`; Mini companions `~/Antiek/specs/antiek-speak-private-public/`, `~/Antiek/specs/antiek-frame-attribution/`.

---

## Verdict labels

| Label | Meaning here |
|---|---|
| **KEEP** | Load-bearing on `main`; reuse as-is |
| **ARCHIVE** | Origin / historical only — do not revive as a parallel product |
| **DEFER** | Real, but gated (legal / operator / live pricing) |

---

## KEEP — executed Speak + shared attribution

DeepBlu’s interview-as-acquisition vision was **already remapped** into Antiek Speak (fourth workflow: Research · Read · Write · Speak). Do not greenfield a Speak MVP or a second contribution ledger.

| Artifact | Path | Why KEEP |
|---|---|---|
| Speak substrate | `substrate/speak/` (schema, consent, async interview, claims, corroboration, publish, biography, write_composer, …) | Executed SPR-01..09 per `speak_workflow.md` |
| Contributor economics | `substrate/speak/contributor.py` | Interviewee → `ip_holders`; **reuses** `substrate/ad_inventory/attribution.py` Option B (`claim_confidence × (6 − source_tier)`); 70% `CREATOR_REV_SHARE`; accrue escrow, refuse pre-G2/G3 |
| Economics matrix | `substrate/speak/economics_mode.py` | Public publish ⇒ algorithmic 70% split with **no** creator override |
| AI-graded payout | `substrate/speak/payout_verifier.py` + `docs/decisions/spr-10-ai-graded-payout.md` | Escrow-only; requester cannot unilaterally deny |
| Private/public spine | `docs/decisions/speak-private-public-spine.md` + UI `Speak` / `SpeakIndex` / `SpeakInvite` | Honest gates; invite token = unauth door |
| Voice I/O | `docs/decisions/voice-infrastructure.md`; `acquisition/voice/`; `/voice/transcribe`; `/speech/tts` | Called ASR/TTS services; `ingest_voice_note` → `document_type=voice_note` |
| Accrual wire shape | `substrate/contracts/accrual.py` | `AccrualSource` ∈ `publisher_impression` \| **`speak_contribution`** \| `frame_attention_second` |
| Fill decisions | `substrate/ad_inventory/fill_decisions.py` → `ad_fill_decisions` | Durable fill ledger; honest `$0` / `unpriced` OK |
| Escrow topology | `docs/decisions/afa-escrow-double-credit.md` | Speak `contributor.py` is escrow writer #3 (`speak_contribution`, not a second ad path) |
| Biography posture | `docs/decisions/spr-11-biography-template-not-graph.md` | Biography = Research+Write+Speak **template**, not a fifth graph / separate DeepBlu product |
| Ads doctrine | `docs/decisions/applovin-website-mvp-attribution-ledger-2026-09-17.md` | Website MVP + 70/30; **Speak / private / settings = No ads** |

Tests already on tree: `tests/test_speak_*.py`, `tests/test_contributor_economics.py`, `tests/test_economics_matrix.py`, seam single-escrow writer.

---

## ARCHIVE — Desktop DeepBlu as origin only

| Path | Disposition |
|---|---|
| `~/Desktop/Deepblu/` (architecture specs, Prisma/Next/Expo app, `crates/deepblu-prosody*`, sync-core) | **ARCHIVE** — prior product; ideas absorbed into Speak + voice + attribution above |
| `~/Desktop/caffenagent/projects/deepblu`, `~/Desktop/moomba/projects/deepblu`, `.openclaw/.../deepblu-*` | **ARCHIVE** companions / assessments |

**Do not:** revive DeepBlu as a parallel Antiek product, fork a second biography store, or port Prisma models into DuckDB SoT.

Canon origin text remains `docs/master-product-spec.md` §11 (DeepBlu — interview-as-acquisition) and §12 (voice note ingestion), implemented as Speak + `acquisition/voice`.

---

## DEFER

| Item | Gate |
|---|---|
| Disbursement (Stripe / real balances) | G2 lawyer + G3 rights-holder opt-in (`gate_status.disbursement_allowed`) |
| Open public contribution ecosystem | G7 / `ANTIEK_SPEAK_PUBLIC_ECOSYSTEM` |
| Live priced network ads / non-zero settled CPM | AppLovin decision Phase stop-condition (§9.0 legal + ACTIVE advertiser + server-minted value) |
| PublicLane “Add your memory” → authed console | Product defect recorded in `speak-private-public-spine.md` (SPR-03 follow-on: feed CTA → invite token) |

Until then: accrue shares; show honest `$0` / escrow; never invent balances.

---

## Explicit MVP composition (hard to vary — dual structure)

Community voice notes that contribute to **books / research** and earn via ads use **existing** plumbing only:

```
voice / interview capture
  → Whisper (/voice/transcribe) + ingest_voice_note  OR  Speak async_interview + claims
  → DuckDB/graph SoT (voice_note docs · speak_* · deliverables)
  → public publish (when applicable) → Read/Research/Write HTML projections
  → ad_fill_decisions on Read/Research/Write  (Speak surface = No ads)
  → Option B / frame_attention share vector
  → AccrualContract (speak_contribution | publisher_impression | frame_attention_second)
  → ip_holders.accrue_escrow  (70% pool policy; disbursable=False)
```

### Community voice on a book/research deliverable

Pick **one** of these — both already exist:

1. **Speak project** attached to the investigation/deliverable (biography / interview path): claims → `contributor.accrue_contributions` → `speak_contribution` AccrualContract → escrow.
2. **`ingest_voice_note(..., investigation_id=…)`** so the transcript lands as a `voice_note` document on that investigation’s graph; map informant → `ip_holders` via the **same** `contributor.py` / Option B weighting — **not** a second accruals table.

**Forbidden in this remap:** new `voice_contribution_accruals` (or similar) table; parallel payout API; AppLovin live tags; second escrow writer outside the sanctioned seam.

### Where ads may show

Per #3103 / AppLovin decision:

| Surface | Ads |
|---|---|
| Read / Research / Write (ad-eligible) | Yes (house / manual sponsor / later settled) |
| **Speak / private / settings** | **No ads** (out of scope) |

Payback for Speak contributors happens when ads show on surfaces that **used** their contributed content — not by mounting ads inside Speak.

---

## Cross-links

- Vision map: `docs/anti-ek-vision-map-2026-09-17.md` (Speak spine KEEP; ads pillar → AppLovin decision; this doc is the Speak↔DeepBlu↔ledger remap).
- Execution record: `docs/decisions/speak_workflow.md`.
- Mini Speak specs: `~/Antiek/specs/antiek-speak-private-public/` (tracked `specs/speak/` may be absent at tip — companions remain authoritative HTML).

---

## Operator vision lock (2026-09-18) — public pay / private no-pay / dual push

Faisal’s product lock for Speak (UX must match `economics_mode` + spine — not a new money path):

### 1) PUBLIC Speak — community insights → pay when published

Anyone can contribute insights that feed **research / books**. When the work is **published** on Antiek (public publishing mode), contributors are paid via the existing **`speak_contribution` escrow** and the **70%** creator/contributor slice (`contributor.py` / `CREATOR_REV_SHARE`). Ads may appear on Read/Research/Write surfaces that use that content — **not** on the Speak surface.

### 2) PRIVATE projects — invite-only corpus; unmistakable no-payout UX

Example: biography of a parent — operator invites friends; they install / open invite links; answer **voice interview** questions; corpus builds in the background; further evidence surfaces new questions → **continuous pings** to invitees.

**Economics (already in code):** `substrate/speak/economics_mode.py` — `invitation=private` + `publishing=never_published` ⇒ **no algorithmic 70% split**; creator carries inference margin; **user plans / publisher economics do not apply**. Accrue/disburse paths must not imply a balance.

**UX requirement (not yet fully productized — required next):** every private / never-published Speak surface (create project, invites, invitee door, economics panel) must make it **unmistakable** that contributors **will NOT make money** on this private project unless/until it is **republished** on Antiek as public (at which point the binding public split applies — see `economics_mode`: public publishing ⇒ split with no creator override). Cite honesty contract in `docs/decisions/speak-private-public-spine.md` (economics view is read-only; no false close affordance).

### 3) PUSHES — dual model

| Push | Audience | Intent |
|---|---|---|
| **(a) Public profile-matched** | Open ecosystem (G7 when unlocked) | “What you’d add value to” — match contributor profile/expertise to public research/book gaps |
| **(b) Private friend invites** | Token invitees | Operator-commissioned remembrance / interview; continuous follow-up pings as gaps reopen |

Both pushes reuse existing invite / feed machinery (`speak_invites`, PublicLane, SpeakInvite) — do not invent a second notification stack in this remap. Continuous-ping for private is **Loop/substrate follow-up** on open questions from the growing corpus (master-spec §11 dashboard / voice follow-up), gated by consent.

### Mapping to KEEP code

| Vision cell | Existing enforcement |
|---|---|
| Public → 70% when published | `economics_mode.resolve_policy` (`split_applies == (publishing == public)`); `contributor.accrue_contributions` |
| Private never-published → $0 payback | Same matrix: `split_applies=False`; spine economics read |
| Unauth contribute door | Invite token `/speak/invite/:token` (feed CTA dead-end still open — SPR-03) |
| No ads on Speak | AppLovin decision table — Speak / private / settings out of scope |

---

## Next Speak gap (after this doc)

1. **Private economics notice (UX)** — unmistakable “you will NOT make money on this private project” on create/invite/invitee/economics surfaces; must mirror `economics_mode` private/never_published (no false payout chrome).
2. **PublicLane dead-end** — feed “Add your memory” must mint/link invite token (`/speak/invite/:token`), not authed `/speak/:id`; honest empty/G7 state (`speak-private-public-spine.md` SPR-03).
3. **Continuous ping (private)** — evidence→new questions→invitee nudges; reuse open-question / follow-up paths; consent-scoped.
4. **Dual push** — (a) public profile-matched “what you’d add value to”; (b) private friend invites — productize on existing invite/feed, G7 for open public.
5. Thin glue only if needed so community `voice_note` on research/book investigations resolve to an `ip_holder` for AccrualContract — still no new ledger.
