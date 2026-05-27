/**
 * Shared TTS (read-aloud / audiobook) service client — SPR-14 M2 + M3-voice-out.
 *
 * Text in, spoken audio out. This is the ONE client every surface calls to read
 * a model's response aloud; the per-surface voice UIs (SPR-04/05/08/09/10)
 * mount the `ReadAloud` control backed by this — they do not each re-implement
 * the network call, the §9.0 guard, or the length scoping.
 *
 * §16 — service, not self-host. Synthesis goes over the network to the backend
 * `POST /speech/tts` route (interfaces/research/api/speech.py), which directly
 * instantiates `OpenAITTSProvider` and calls `.synthesize()` → OpenAI's
 * `/v1/audio/speech` (gpt-4o-mini-tts). It is NOT routed through the dispatch
 * `tts` tier, and OpenAITTSProvider is NOT registered in bootstrap's default
 * providers — the dispatch-shaped `.call()` is an unused scaffold; the route
 * uses `.synthesize()`. MiMo-V2.5-TTS is the intended FUTURE provider, swapped
 * behind the same route. We CALL a specialized speech service (sharing the
 * operator OPENAI_API_KEY — no new credential mechanism); we do not run a TTS
 * model runtime inside Antiek. Reasoning + reconsider-if:
 * docs/decisions/voice-infrastructure.md.
 *
 * §9 provenance — TTS-out is MODEL-GENERATED. Read-aloud narrates text the model
 * already produced; it creates NO new user-sourced node, persists nothing, and
 * must never be labelled or stored as user content. Where a surface needs to
 * label narration, use `TTS_OUT_SOURCE_KIND` ("ai") — the shared `source_kind`
 * value for model-generated content (the value the voice-in builder defines in
 * the event schema; we depend on the string, not the generated type).
 *
 * §9.0 — a withheld region is NEVER read aloud. Before any text reaches the
 * network, `narrate` rejects a non-servable chunk: the body never crosses into
 * this client, the request body, or the audio output. See `assertServable`.
 *
 * LIVE vs STUBBED: the backend /speech/tts route (interfaces/research/api/
 * speech.py) calls `OpenAITTSProvider.synthesize()`, a REAL OpenAI
 * `/v1/audio/speech` call that is LIVE WHEN `OPENAI_API_KEY` is set and returns
 * 503 when it is absent (the no-key path, not a stub). (The dispatch-shaped
 * `OpenAITTSProvider.call()` does raise NotImplementedError, but this route does
 * not use it.) The client + control shape here is verified against a recorded
 * fixture (the tests inject a fake `fetch`/audio); a KEYED live round-trip was
 * NOT exercised this sprint — so the path is live-when-keyed, not stubbed, but
 * do not read these tests as proof playback works end-to-end.
 */

import { API_BASE, apiFetch } from "../lib/api";
import { getChunk } from "../lib/api";

/**
 * The shared `source_kind` value for model-generated content. The voice-in
 * builder defines the `source_kind: "user" | "ai" | "system"` enum in the event
 * schema; TTS-out is narration of existing MODEL text, so it is "ai". We surface
 * the literal (not the generated type) so this client does not depend on the
 * other builder's codegen. NOTE for the orchestrator: if a `SourceKind` TYPE is
 * later wanted here, import it from the generated types rather than redefining —
 * do NOT add a parallel enum. (See handoff: assumption ASSUMED, not verified.)
 */
export const TTS_OUT_SOURCE_KIND = "ai" as const;

/** Words-per-minute budget for narration scoping.
 *
 * How "X minutes" maps to text/scope: spoken English from a TTS engine lands
 * around 150 words/minute (a common audiobook/narration pace; conversational
 * speech is ~130–160 wpm). So an "explain for X minutes" request scopes the
 * narration to roughly `X * NARRATION_WPM` words. This is the budget the caller
 * (a surface, later the audiobook generator in SPR-08) uses to ask the model
 * for an appropriately-sized explanation BEFORE synthesis — the TTS service
 * speaks whatever text it is handed; the LENGTH lives in how much text the
 * upstream model is asked to produce. This client owns the budget math + the
 * bound; it does not itself call the model (that is the surface's dispatch).
 */
export const NARRATION_WPM = 150;

/** Degenerate-length bounds (stated, not silent — rigor #3 "degenerate length").
 *
 * A 0-minute (or negative) request is a no-op caller bug; an absurdly-large
 * request would ask the model for a runaway transcript. We REJECT both with a
 * stated bound rather than silently clamping to a surprising value, so the
 * caller sees the error and fixes the request. MAX_NARRATION_MINUTES = 120 (a
 * two-hour audiobook chapter is already the long end of the SPR-08 use case;
 * beyond it the request is almost certainly a bug or an abuse).
 */
export const MIN_NARRATION_MINUTES = 1;
export const MAX_NARRATION_MINUTES = 120;

export class TtsError extends Error {
  constructor(
    message: string,
    public readonly kind:
      | "withheld" // §9.0 — refused, never narrated (load-bearing)
      | "empty" // silent/empty text — no-op upstream, never reaches here
      | "degenerate_length" // 0-minute / absurdly-large — bounded
      | "unavailable" // 503 — TTS service not provisioned (stubbed today)
      | "network", // any other non-ok response
  ) {
    super(message);
    this.name = "TtsError";
  }
}

export interface NarrationBudget {
  /** Requested narration length in minutes. */
  minutes: number;
  /** The word budget the caller should ask the model to fill (minutes × wpm). */
  wordBudget: number;
}

/**
 * Map an "explain for X minutes" request to a word budget, with the degenerate
 * bound applied. Pure + synchronous so a surface can size its model prompt
 * before any synthesis. Throws `TtsError("degenerate_length")` on a 0/negative,
 * non-finite, or above-MAX request — the bound is stated in the message.
 */
export function narrationBudgetForMinutes(minutes: number): NarrationBudget {
  if (!Number.isFinite(minutes) || minutes < MIN_NARRATION_MINUTES) {
    throw new TtsError(
      `Narration length must be at least ${MIN_NARRATION_MINUTES} minute(s); got ${minutes}.`,
      "degenerate_length",
    );
  }
  if (minutes > MAX_NARRATION_MINUTES) {
    throw new TtsError(
      `Narration length is capped at ${MAX_NARRATION_MINUTES} minutes; got ${minutes}.`,
      "degenerate_length",
    );
  }
  return { minutes, wordBudget: Math.round(minutes * NARRATION_WPM) };
}

/**
 * Trim a model-produced explanation to the narration word budget, so a length
 * request actually scopes the spoken output. The model is asked for ~`wordBudget`
 * words; this is the deterministic backstop that keeps a too-long explanation
 * from over-running the requested minutes. Returns the trimmed text (whole words,
 * never a mid-word cut). The provenance of `text` is unchanged — it is still the
 * model's words, narrated, never relabelled as user content.
 */
export function scopeNarrationText(text: string, budget: NarrationBudget): string {
  const words = text.trim().split(/\s+/).filter(Boolean);
  if (words.length <= budget.wordBudget) return words.join(" ");
  return words.slice(0, budget.wordBudget).join(" ");
}

/**
 * §9.0 guard. Refuse to narrate a withheld region. If `chunkId` is given we
 * resolve the chunk and refuse when `servable === false` — the body (`text`) is
 * withheld by the endpoint anyway, but this is the belt-and-braces check that
 * the WITHHELD body never even reaches `synthesizeSpeech`. Returns nothing on
 * success; throws `TtsError("withheld")` otherwise.
 *
 * This mirrors the backend retrieval-time gate (RESTRICTED_CONTENT_CLASSES /
 * restricted_pending_opt_in in substrate/graph/search.py) on the read-aloud
 * path: §9.0 content is never opened, cited, OR narrated.
 */
export async function assertServable(chunkId: string): Promise<void> {
  const chunk = await getChunk(chunkId);
  if (chunk.servable === false) {
    throw new TtsError(
      "This source is withheld and cannot be read aloud.",
      "withheld",
    );
  }
}

/**
 * Low-level synthesis: text → spoken-audio Blob via the dispatch `tts` tier.
 * The backend /speech/tts route reads the `tts` tier config and routes to the
 * registered provider (MiMo-V2.5-TTS intended). Returns the audio Blob the
 * caller plays; throws `TtsError` on empty text, a 503 (service not provisioned
 * — the stubbed-today case), or any other failure.
 *
 * Empty/whitespace text is a no-op-not-a-crash at the boundary: we throw
 * `TtsError("empty")` BEFORE the network call so a silent caller bug surfaces as
 * a handled state, never a request that burns a synthesis on nothing. (The
 * ReadAloud control treats this as a quiet no-op.)
 */
export async function synthesizeSpeech(
  text: string,
  opts?: { voice?: string },
): Promise<Blob> {
  if (!text.trim()) {
    throw new TtsError("Nothing to read aloud (empty text).", "empty");
  }
  const resp = await apiFetch(`${API_BASE}/speech/tts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, voice: opts?.voice }),
  });
  if (resp.status === 503) {
    // 503 = the /speech/tts route has no OPENAI_API_KEY, so
    // OpenAITTSProvider.synthesize raises RuntimeError → 503. Honest
    // unavailable (the no-key path), not a silent failure.
    throw new TtsError("Read-aloud isn’t available right now.", "unavailable");
  }
  if (!resp.ok) {
    throw new TtsError(`Read-aloud failed (HTTP ${resp.status}).`, "network");
  }
  return resp.blob();
}

export interface NarrateOptions {
  /** Voice id passed through to the service (provider-defined). */
  voice?: string;
  /**
   * §9.0 — the source chunk this text came from. When present, the chunk is
   * checked for servability and a withheld region is REFUSED before any text is
   * sent. Omit only for text with no §9.0 provenance (e.g. a freshly-generated
   * model explanation that cites no withheld source).
   */
  chunkId?: string;
  /**
   * Length/time box. When present, the text is scoped to the minute budget
   * (`narrationBudgetForMinutes` → `scopeNarrationText`) before synthesis, so an
   * "explain for X minutes" request produces a correspondingly-sized narration.
   * A degenerate value (0 / negative / above the cap) throws — never silent.
   */
  minutes?: number;
}

export interface NarrationResult {
  audio: Blob;
  /** The text actually spoken (post-scoping). Still model-generated. */
  spokenText: string;
  /** Provenance of the narration. Always model-generated — see §9 note above. */
  sourceKind: typeof TTS_OUT_SOURCE_KIND;
  /** The applied budget, when a length box was requested. */
  budget?: NarrationBudget;
}

/**
 * The one read-aloud entry point a surface calls. Enforces, in order:
 *   1. §9.0 — refuse a withheld chunk (body never reaches the service).
 *   2. degenerate-length — a bad `minutes` throws with a stated bound.
 *   3. length scoping — text trimmed to the minute budget.
 *   4. empty-text — a no-op-not-a-crash boundary inside `synthesizeSpeech`.
 * Returns the audio Blob plus the model-generated provenance tag (never user).
 */
export async function narrate(
  text: string,
  opts: NarrateOptions = {},
): Promise<NarrationResult> {
  // 1. §9.0 FIRST — before scoping, before any text leaves the client.
  if (opts.chunkId) {
    await assertServable(opts.chunkId);
  }

  // 2 + 3. Length box (throws on degenerate; scopes otherwise).
  let spokenText = text;
  let budget: NarrationBudget | undefined;
  if (opts.minutes !== undefined) {
    budget = narrationBudgetForMinutes(opts.minutes);
    spokenText = scopeNarrationText(text, budget);
  }

  // 4. Synthesize (empty-text no-op guarded inside).
  const audio = await synthesizeSpeech(spokenText, { voice: opts.voice });

  return {
    audio,
    spokenText,
    sourceKind: TTS_OUT_SOURCE_KIND, // model-generated, never user
    budget,
  };
}
