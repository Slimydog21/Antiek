# Voice infrastructure — ASR-in / TTS-out are CALLED services, not self-hosted models

**Decision date:** 2026-05-27 (SPR-14, Living Roadmap run)
**Status:** ✅ Built + verified. ASR-in is **live today** (Whisper-backed);
TTS-out client is built and fixture-verified (the voice-out half of this
sprint). MiMo-V2.5-ASR / MiMo-V2.5-TTS are the *intended future* backends
behind the same routes — a backend swap, operator-bound, not built here.
**Owner:** SPR-14 (voice infrastructure — the shared voice-in / voice-out
service every later voice feature consumes).
**Invariant context:** CLAUDE.md §16 (dispatch is Hermes-primary, no
self-hosted LLMs, no second runtime) + master-spec §9 (provenance:
voice-in is user-sourced, never conflated with model output) + §5 (voice
discipline) + `docs/decisions/dispatch-deepseek-mimo-wiring.md` (the
cost/preemptibility reasoning this doc reuses).

## The decision

Voice in (ASR — speech → text) and voice out (TTS — text → speech) are
**specialized services Antiek CALLS over the network**, exactly the way the
dispatch router calls a model provider. This is the legitimate §16 carve-out.
§16 forbids self-hosting an LLM **runtime** inside Antiek and forbids a
**second runtime/dispatcher**; it does **not** forbid calling a specialized
ASR/TTS endpoint. We:

- do **not** self-host MiMo-V2.5-ASR, MiMo-V2.5-TTS, Whisper, or any model
  inside Antiek;
- do **not** add a second runtime, a second dispatcher, or a second
  credential mechanism — voice shares the SAME operator credential (the
  `OPENAI_API_KEY` the OpenAI-compat providers + Whisper already use). (The
  `/speech/tts` route directly instantiates `OpenAITTSProvider` rather than
  going through the dispatch provider registry / `tts` tier, and ASR runs in
  the acquisition layer — both are CALLED services sharing the one key, not a
  second credential path.)
- persist captured audio + transcripts ONLY through the single-writer typed
  event funnel (`postTypedEvent → /events/typed → runtime/db_lock`), never a
  client-side side store. The audio blob rides by **reference** (`audio_ref`).

### What is live vs. intended (honesty — SPR-14 rigor #1)

| Service | Route | Backend TODAY | Intended future backend |
|---|---|---|---|
| ASR-in (speech → text) | `POST /voice/transcribe` (`interfaces/research/api/read_voice.py`) | **LIVE — Whisper-1** (`acquisition/voice/client.py:WhisperTranscriber`), gated on the operator OpenAI key (honest 503 when absent) | **MiMo-V2.5-ASR** — a backend swap behind the SAME route via the injected `Transcriber` Protocol; no new route, no new credential |
| TTS-out (text → speech) | `POST /speech/tts` (`interfaces/research/api/speech.py`) → client `apps/reading/src/api/tts.ts` | **live-when-keyed — OpenAI TTS.** The route directly calls `OpenAITTSProvider.synthesize()` → OpenAI `/v1/audio/speech` (gpt-4o-mini-tts), gated on `OPENAI_API_KEY` (503 when absent). NOT the dispatch `tts` tier; OpenAITTSProvider is not bootstrap-registered (its dispatch-shaped `.call()` is an unused scaffold). Client shape fixture-verified; a keyed live round-trip was not exercised this sprint. | **MiMo-V2.5-TTS** — swap the provider behind the same `/speech/tts` route |

"I called the real endpoint and it returned" ≠ "I asserted the client shape
against a fixture." ASR-in is the former (Whisper is genuinely serving
`/voice/transcribe` today). TTS-out is live-when-keyed (the `/speech/tts` route
makes a real OpenAI `/v1/audio/speech` call when `OPENAI_API_KEY` is set), but
this sprint only fixture-verified the client shape — a keyed round-trip was not
exercised. Today both real backends are OpenAI-family (Whisper + OpenAI TTS);
MiMo-V2.5-ASR/TTS are the intended future swaps behind the same routes — a
backend change, not new infrastructure and not a new credential.

## Why call a service instead of self-hosting the voice models

This is the same reasoning the dispatch decision settled
(`docs/decisions/dispatch-deepseek-mimo-wiring.md` §"Why API, not self-host"),
applied to ASR/TTS — cited, not re-derived with invented numbers:

1. **Cost at single-operator volume.** Self-hosting a model on rented GPUs
   costs roughly **100–1000×** more per unit of work than a hosted API/service
   at the volume one operator generates (the figure carried over from the
   dispatch decision — not a voice-specific per-minute price, which we do NOT
   invent here). A reserved GPU bills 24/7 whether or not a request is in
   flight; the service bills per call. A bursty single-operator voice workload
   on a fixed GPU rent is strictly worse economics.
2. **Stable endpoint vs. preemptible GPUs.** The only GPUs available to this
   project are **preemptible/spot-class** (per the §16 REJECT line on
   Modal/Daytona). A preemptible instance can be reclaimed mid-request, so it
   cannot hold a stable inference endpoint — a self-hosted voice model would
   need a hosted fallback anyway. The called service IS that stable endpoint;
   putting a self-host layer in front of it is pure complexity with no
   availability gain.
3. **§16 + the second-runtime line.** A self-hosted ASR/TTS model is a serving
   runtime inside Antiek — exactly the second runtime §16 rejects, and one the
   substrate/dispatch boundary lint would not contain. Calling a specialized
   service is vendor-pluggable and stays on the right side of that boundary.

### Steelman of self-hosting (SPR-14 rigor #2 — honored)

Self-hosting MiMo-V2.5-ASR/TTS inside Antiek would remove a network
dependency, give latency control over the round-trip, and avoid per-call cost
at high volume. That is a real argument — and it is overridden here by §16 +
the cost/preemptibility reasoning above: at single-operator volume the
per-call economics dominate (≈100–1000×), the available GPUs are
preemptible-only (no stable endpoint to self-host onto), and a serving runtime
inside Antiek is the second runtime §16 forbids. Calling the service keeps the
latency cost (a network hop) while avoiding all three.

## Reconsider-if

Flip to (or add) a self-hosted voice path **only** if BOTH economics and
availability invert — a **named** reconsider event, not silent drift:

- **Sustained volume saturates dedicated GPUs 24/7.** If voice volume grows
  such that reserved GPUs would run hot around the clock, the 100–1000×
  multiplier collapses and self-host amortizes. This is a multi-user /
  Sprint-22+ concern, not a single-operator one.
- **A hard data-residency / confidentiality ruling rules out every hosted
  service.** If a legal or contractual constraint (e.g. under the §9.0 legal
  gate) forbids sending audio/transcript content to any third-party service,
  self-host becomes the only compliant option.

Even then the change is "add a `providers/`-style adapter behind the same
plumbing + a serving-runtime decision," never a second dispatcher.

## §9 provenance rationale (why voice-in is user-sourced, TTS-out model-generated)

The voice path crosses the §9 provenance boundary in BOTH directions, and the
two directions get **different** labels — conflating them is a §9 violation:

- **Voice-IN is `source_kind = "user"`.** A spoken capture is human-authored.
  The `VoiceCapturedPayload` schema (`substrate/schemas/events.py`) pins
  `source_kind` to the literal `"user"`, so a voice transcript node can NEVER
  be persisted as anything else — the no-conflation invariant is enforced by
  the type, not by convention. A voice transcript node is therefore
  **distinguishable in the one graph** from a model-output node by that single
  field.
- **TTS-OUT is `source_kind = "ai"`.** Narration is the reading-aloud of model
  text; it is generated content, not user content, so the voice-out half
  labels it `"ai"`.
- **§9.0 is never narrated.** A withheld §9.0 region must never be read aloud —
  its body must never reach the TTS client or the audio output. That guard is
  the voice-out half of this sprint (`apps/reading/src/components/voice/ReadAloud.tsx`
  + `apps/reading/src/api/tts.ts`).

`source_kind` is **one shared vocabulary** — `"user" | "ai" | "system"`
(`ProvenanceSourceKind` in `substrate/schemas/events.py`, emitted to
`apps/reading/src/generated/types.ts`) — deliberately NOT voice-specific, so
every authored-vs-generated distinction across the graph uses the same three
values. Voice-in uses `"user"`; the voice-out / model path uses `"ai"`;
`"system"` is for machine/non-authored emissions.

## Consumers (blast radius)

This is a Wave-1 foundation service. The per-surface voice UIs are OUT OF
SCOPE here and live in their own sprints; each CONSUMES this service rather
than re-implementing capture/transcription or playback:

- **SPR-04** — float-menu voice (highlight → speak a note/dialogue/search).
- **SPR-05** — voice prompt (speak a research/ask prompt).
- **SPR-08** — talk-to-book + audiobook (TTS narration, length/time-boxed).
- **SPR-09** — voice-to-draft (speak into the Write surface).
- **SPR-10** — async interview (Speak workflow).

A change to the shared hook / clients / event schema ripples to all five —
hence one hook, two clients, one event path, one provenance vocabulary.

## Companion artifacts

- `apps/reading/src/hooks/useVoiceCapture.ts` — the shared, host-agnostic
  capture+transcribe hook (record → transcribe → user-sourced label →
  persist via typed event).
- `apps/reading/src/api/asr.ts` — the ASR client (thin wrapper over the live
  `/voice/transcribe` route).
- `apps/reading/src/api/tts.ts` + `apps/reading/src/components/voice/ReadAloud.tsx`
  — the TTS client + read-aloud control + §9.0 guard (the voice-out half).
- `substrate/schemas/events.py` — `SourceKind` + `VoiceCapturedPayload`
  (EVENT_SCHEMA_VERSION bumped to 17).
- `apps/reading/src/hooks/useVoiceCapture.test.ts` +
  `tests/test_voice_capture_event.py` — the provenance + failure-input tests.
- `docs/decisions/dispatch-deepseek-mimo-wiring.md` — the cost/preemptibility
  reasoning this decision reuses.
