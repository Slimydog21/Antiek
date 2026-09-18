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

## Next Speak gap (after this doc)

1. **PublicLane dead-end** — feed “Add your memory” must mint/link invite token (`/speak/invite/:token`), not authed `/speak/:id`; honest empty/G7 state.
2. Then: thin glue only if needed so community `voice_note` on research/book investigations always resolve to an `ip_holder` for AccrualContract — still no new ledger.
