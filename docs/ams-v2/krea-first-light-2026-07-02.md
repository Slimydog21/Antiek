# Krea first light — 2026-07-02 (live-key verification of the ALC adapter)

**What this is.** The first live Krea API call in this project's history, closing the
three `stream-spike.md` §3 rows recorded as `not measured (no key)` and executing the
living-caliber M2 "capped local smoke" with a real key. Run by the /infinite
orchestrator (session `08b5453e`) under the operator's 2026-07-02 directive ("Krea key
topped up → execute the dynamic-UI/design specs").

## Method (secret-safe, capped by construction)

- **Key custody:** the key lives in the Modal secret `krea-api-key` (env var
  `KREA_API_KEY`, 69 chars — note the name differs from the code's `KREA_API_TOKEN`;
  every consumer must alias). It was fetched by a Modal function *return* into one
  orchestrating process and injected into exactly two child-process envs (server,
  smoke). Never printed, never written to disk, never in shell history.
- **RUN A (zero-spend), inside Modal:** unbilled `GET /jobs/<nonexistent>` with the
  bearer → `404 {"message":"Job not found or unauthorized"}`. Auth-plausible but
  ambiguous by API design (404 conflates not-found with unauthorized); RUN B's
  accepted generation is the real auth proof.
- **RUN B, local:** uvicorn (`--workers 1`, port 8123) booted from this branch's tree
  (the ONLY tree with the live-correct model-in-path adapter) with
  `KREA_DAILY_UNIT_CAP=3`; server healthy in 128 s (cold-boot compile of a fresh
  worktree — budget ≥180 s for first boot). Then `tools/krea_smoke.py --base` (this
  branch's own first-contact procedure), then two timed fresh `/krea/scene` calls.

## Results

- **Smoke: PASS (exit 0).** `GET /health` 200 → fresh `calm|day|summer` scene 200,
  `cached:false`, real `https://gen.krea.ai/images/….png` URL → identical repeat
  `cached:true` (**de-bill proven**). This is simultaneously the proof that the
  **model-in-path wire shape (`bfl/flux-1-dev`) is the real API**: `origin/main`'s
  model-in-body adapter would have fallen back silently here.
- **Timed fresh generations (same cap-3 session):** `focus` 7.50 s, `energetic`
  7.17 s, both 200 with image URLs; cached repeat 0.01 s.
- **The three stream-spike rows (now measured, flux baseline):**
  - (i′) time-to-first-generated-frame: **7.17 s min / 7.33 s avg** (n=2)
  - (ii′) sustained generative fps: **0.136**
  - (iii) $/min at cap: **$0.33 at $0.04/unit** or **$0.057 at the runbook's
    $0.007/gen** — the unit price is the one number this run cannot see; the
    **operator's dashboard decrement (krea.ai/app/api) is ground truth** (expect
    exactly 3 fresh units from 2026-07-02).
- **Verdict impact:** the generative-stream **NO-GO stands, now on measured
  evidence** (7.17 s vs <500 ms required; 0.136 vs ≥10 gen fps required). The
  procedural floor remains the product; live art is the slow, budget-bounded tint.

## Spend accounting

3 fresh units total (smoke 1 + timed 2), hard-capped server-side. ≈$0.12 at
$0.04/unit; ≈$0.021 if flux bills $0.007/gen.

## Honesty ledger

- RUN A's 404 is not a clean auth discriminator (message says "or unauthorized");
  auth was proven by RUN B's accepted, completed generations.
- A first-attempt probe script derived a "prefix class" from the key value and
  printed its first 8 characters into a session task file — an 8/69-char partial
  leak, scrubbed from the file immediately; the class is withheld everywhere since.
  **Rotation was already operator-mandated** after the 2026-06-12 ledger leak
  (living-caliber SPR-09 step 0) and this incident reinforces it: rotate at the Krea
  dashboard, then `modal secret create krea-api-key --from-dotenv … --force`.
- The first server boot attempt used a 60 s health budget and failed on cold-boot
  compile (~128 s real); recorded so nobody misreads that as an app defect.

## Operator follow-ups

1. Confirm the dashboard decrement (exactly 3 units, 2026-07-02) and note the real
   unit price — it decides between $0.33/min and $0.057/min in stream-spike §5.
2. Rotate the key (mandated 2026-06-12; reinforced above), re-store to Modal.
3. Prod wiring stays as designed: `KREA_API_TOKEN` in `/etc/antiek/secrets.env`
   (alias from the rotated value) + backend restart — after this branch lands.
