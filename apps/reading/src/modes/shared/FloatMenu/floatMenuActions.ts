import {
  apiFetch,
  postTypedEvent,
  searchBlocks,
  regionFromProvenance,
  ApiError,
  type BlockSearchHit,
  type DialogueRegion,
} from "../../../lib/api";
import type { MarginaliaNotedPayload } from "../../../generated/types";
import type { FloatMenuSelection } from "./useFloatMenuSelection";

/**
 * floatMenuActions — the four float-menu actions' data paths, in one place so
 * each one's DESTINATION and PROVENANCE LABEL are documented next to the call
 * (rigor #5). The four actions share the SAME selection context (one coherent
 * unit), so they live together, not split across files.
 *
 *   NOTE          → `postTypedEvent` (single-writer funnel, lib/api.ts:99) —
 *                   USER-sourced marginalia note (source_kind "user").
 *   DIALOGUE      → the substrate's `/thought-partner` endpoint (the SAME
 *                   dispatch AISidecar.tsx:164 uses) — the reply is
 *                   MODEL-sourced; the user's prompt (incl. a voice transcript)
 *                   is user-sourced and NEVER relabelled as the reply.
 *   SEARCH        → `searchBlocks` (corpus search, lib/api.ts:667) — RETRIEVAL-
 *                   sourced hits; never user content.
 *   DEEP-RESEARCH → handled by FloatMenu itself via the reused chase path
 *                   (ChaseSlideOver/ChaseThread + startInvestigation) — spawns a
 *                   MODEL/retrieval-sourced child investigation linked to the
 *                   source highlight.
 *
 * ════════════════════════════════════════════════════════════════════════
 * §9.0 NO-LEAK — withheld body never leaves the client
 * ════════════════════════════════════════════════════════════════════════
 * If a selection lands in a chunk the substrate withheld (`servable === false`,
 * a §9.0 restricted / taken-down source), the WITHHELD body must NOT be sent in
 * the SEARCH query or the DEEP-RESEARCH spawn_context. {@link outboundText}
 * is the single chokepoint: SEARCH and DEEP-RESEARCH route their selection
 * text through it, and it returns null for a withheld selection — the caller
 * then refuses the action with an honest message rather than leaking. (NOTE is
 * NOT gated by this: a marginalia note is the reader's OWN selected text on
 * their own reading surface; the no-leak guard governs OUTBOUND queries to the
 * corpus / a new investigation, not a note of one's own reading.)
 */

/** §9.0 chokepoint. Returns the selection text safe to send OUTBOUND (SEARCH /
 * DEEP-RESEARCH), or null when the selection crosses a withheld region and the
 * body must not leave the client. `servable === false` ⇒ withheld ⇒ null. A
 * `servable` of true or undefined (no chunk resolved — e.g. a free-prose
 * synthesis selection that maps to no withheld source) is allowed: undefined
 * means "the host could not resolve a withheld chunk", not "withheld". */
export function outboundText(selection: FloatMenuSelection): string | null {
  if (selection.provenance.servable === false) return null;
  return selection.text;
}

/** Human reason shown when the §9.0 guard blocks an outbound action. */
export const WITHHELD_OUTBOUND_REASON =
  "This selection includes a restricted source, so its text can’t be sent to search or a new research.";

// ─── NOTE ────────────────────────────────────────────────────────────────
//
// DESTINATION: `postTypedEvent` → /events/typed (the ONLY sanctioned client
//   writer; single-writer DuckDB funnel). NO side store.
// PROVENANCE: source_kind "user" — a marginalia note is human-authored. The
//   schema PINS source_kind to the literal "user" (events.py:MarginaliaNoted),
//   so this note can never be conflated with a model reply node in the graph
//   (§9). It carries the selection's chunk_id (provenance chain claim→chunk→
//   document; document_id rides the envelope). The excerpt is the reader's OWN
//   selected text, not retrieved body — so it is not a withheld-content
//   concern (a reader reading their own selection).

export interface SaveNoteArgs {
  investigationId: string;
  selection: FloatMenuSelection;
  /** The note's text. For a typed note this is the composed comment; for a
   * voice note this is the user-sourced transcript (still source_kind "user" —
   * voice-in is human speech, never model output). */
  noteText: string;
  /** Optional stable id; defaults to a generated one. */
  noteId?: string;
}

export async function saveFloatMenuNote(
  args: SaveNoteArgs,
): Promise<{ eventId: string }> {
  const { investigationId, selection, noteText } = args;
  const noteId = args.noteId ?? `mn-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const payload: MarginaliaNotedPayload = {
    action_type: "marginalia.noted",
    note_id: noteId,
    note_text: noteText,
    excerpt: selection.text,
    // §9 load-bearing label: a marginalia note is the reader's own authorship.
    // (A voice note routed through here carries the SAME "user" label — voice-in
    // is human-authored. The §9 sin is letting a model reply inherit "user", or
    // a user note inherit a model label; we never do either.)
    source_kind: "user",
    // Provenance chain: the chunk the selection lands in (null when the host
    // resolved none — honest, never invented).
    chunk_id: selection.provenance.chunkId ?? null,
  };
  const emitted = await postTypedEvent({
    investigation_id: investigationId,
    // The document the selection sits in completes the claim→chunk→document
    // chain on the Event envelope (omitted when the host resolved none).
    document_id: selection.provenance.documentId ?? undefined,
    payload,
  });
  return { eventId: emitted.event_id };
}

// ─── SEARCH ──────────────────────────────────────────────────────────────
//
// DESTINATION: `searchBlocks(q)` → GET /blocks/search (corpus search,
//   lib/api.ts:667). REUSED — no new search endpoint built.
// PROVENANCE: the hits are RETRIEVAL-sourced (graph blocks); they are never
//   user content and are not relabelled.
// §9.0: the query text is routed through `outboundText` — a withheld selection
//   returns null and the caller refuses rather than sending the body to search.

export interface SearchResult {
  hits: BlockSearchHit[];
  count: number;
}

/** Run corpus search for the selection. Returns null when the §9.0 guard
 * blocks the outbound query (withheld selection) — the caller surfaces the
 * withheld reason. Internet search is OUT OF SCOPE this sprint (corpus only);
 * if a future internet tier is added it routes through this SAME guard. */
export async function searchFloatMenuSelection(
  selection: FloatMenuSelection,
): Promise<SearchResult | null> {
  const q = outboundText(selection); // §9.0 chokepoint
  if (q === null) return null; // withheld → do not query; no body leaves the client
  const { hits, count } = await searchBlocks(q);
  return { hits, count };
}

// ─── DIALOGUE ──────────────────────────────────────────────────────────────
//
// DESTINATION: the substrate's `/thought-partner` (one-shot) and
//   `/thought-partner/stream` (SSE) endpoints — the REAL model via the ONE
//   Hermes-routed dispatch tier (§16; role `user_agent`). SPR-06 replaced the
//   canned, passage-independent scaffold: the reply is now MODEL-sourced and
//   passage-DEPENDENT, or an honest 503 when no provider key is configured.
// PROVENANCE: the user's prompt is USER-sourced (the reader's selection +
//   typed/spoken follow-up — voice is human speech, source_kind "user"); the
//   model's reply is MODEL-sourced. The two are kept distinct in the return
//   shape (`prompt` vs `reply`) and NEVER conflated — relabelling a reply as
//   user content (or vice versa) is a §9 violation.
// ANCHOR + PERSIST (M3 + M4): when the selection resolves a Region (documentId
//   + chunkId [+ char range]) the thread is anchored to the exact span and
//   persisted to the graph through the single sanctioned writer, so it survives
//   reload. A selection over un-anchored prose still answers, just un-persisted.
// INERT-without-keys: when no provider key is configured the endpoint 503s; the
//   caller surfaces the shared AIActionFailure no-key state (honest), never a
//   fabricated reply. A green test means "the gesture is real and lights up with
//   keys," NOT "the operator can talk to a passage."

export interface DialogueReply {
  /** The user's prompt (selection ± a follow-up / voice transcript). Kept so
   * the surface can render it ABOVE the reply, visibly user-sourced. */
  prompt: string;
  /** The model's reply — MODEL-sourced, never relabelled as user content. */
  reply: string;
  /** The graph node the thread was anchored to (null when the selection carried
   * no resolvable Region). The client re-opens the same thread by re-selecting
   * the same span (the node is content-addressed on the Region). */
  threadNodeId?: string | null;
}

/** One prior turn carried into the next request (multi-turn). `question` is
 * user-sourced; `answer` is model-sourced — kept distinct (§9). */
export interface DialogueHistoryTurn {
  question: string;
  answer: string;
}

/** Build the user-sourced prompt for a dialogue over a selection. The
 * selection is the reader's own quoted text (user-sourced); an optional
 * follow-up (typed or a voice transcript) is also user-sourced. Kept for the
 * legacy single-field contract + as a UI label of what the reader asked. */
export function buildDialoguePrompt(
  selection: FloatMenuSelection,
  followUp?: string,
): string {
  const quote = `About this passage I selected:\n"${selection.text}"`;
  const tail = followUp && followUp.trim() ? `\n\n${followUp.trim()}` : "";
  return quote + tail;
}

/** Resolve the SPR-01 Region from a selection's provenance, or null when the
 * host resolved no anchor (no document / block — a free-prose selection). The
 * snake_case wire mapping lives in `lib/api.regionFromProvenance` (the substrate
 * field names belong with the API contract, never on the user-facing surface).
 * The §9.0 guard is separate: a WITHHELD selection still anchors a thread (the
 * thread is the reader's own conversation about their own selection), but its
 * body is never sent OUTBOUND to search / a child investigation — that guard is
 * `outboundText`, not this. */
export function regionOfSelection(
  selection: FloatMenuSelection,
): DialogueRegion | null {
  const { documentId, chunkId, charStart, charEnd } = selection.provenance;
  return regionFromProvenance({ documentId, chunkId, charStart, charEnd });
}

// ─── REWRITE (Write SPR-09 M4) ─────────────────────────────────────────────
//
// The Write surface (and ONLY Write) extends the shared menu with rewrite
// actions. The menu shows them iff the host passes `rewriteActions` — Read /
// Research / Speak hosts pass nothing and are unchanged (D-3: mode-gated, NOT a
// fork). The actions are intents the HOST fulfils against the SHIPPED
// creative_writer generate path (regenerate the paragraph the selection sits
// in) and the SHIPPED spawn path (startInvestigation) — the menu never forks a
// new model path. §9.0: any text sent to a model still routes through
// `outboundText` (a withheld selection is refused).

/** A rewrite intent the writer triggered over a highlighted span. The host
 * maps it to the SHIPPED generate/spawn paths; the menu only carries the
 * §9.0-safe text + the intent kind. */
export type RewriteIntentKind = "rewrite" | "stronger" | "sub_agent";

export interface RewriteIntent {
  kind: RewriteIntentKind;
  /** The §9.0-safe selection text (null ⇒ withheld; the host must refuse). */
  safeText: string | null;
}

/** The rewrite-action descriptor a Write host hands the FloatMenu. `onRewrite`
 * receives the intent (kind + §9.0-safe text); the host owns the actual
 * regenerate (creative_writer) / spin-a-sub-agent (startInvestigation). */
export interface RewriteActions {
  onRewrite: (intent: RewriteIntent, selection: FloatMenuSelection) => void;
}

/** The request body shared by the one-shot + streamed Dialogue endpoints: the
 * passage (the reader's own selection), an optional follow-up, the Region to
 * anchor to, and the prior turns (multi-turn). `prompt` is kept for the legacy
 * single-field contract. */
function dialogueBody(args: {
  investigationId: string;
  selection: FloatMenuSelection;
  followUp?: string;
  history?: DialogueHistoryTurn[];
}): string {
  return JSON.stringify({
    investigation_id: args.investigationId,
    // Passage = the reader's own quoted selection (user-sourced).
    passage: args.selection.text,
    follow_up: args.followUp ?? "",
    // Legacy field — the assembled quote, so a single-field client still works.
    prompt: buildDialoguePrompt(args.selection, args.followUp),
    region: regionOfSelection(args.selection),
    history: args.history ?? [],
  });
}

/** One-shot (non-streamed) dialogue over the selection via /thought-partner.
 * Throws `ApiError` (status carried) on failure so the caller can branch the
 * no-key 503 case onto AIActionFailure, exactly as VoiceChaseButton.tsx:56
 * does. Prefer {@link streamDialogueOverSelection} for the streamed panel; this
 * one-shot remains for non-streaming callers + as the test-simple path. */
export async function dialogueOverSelection(args: {
  investigationId: string;
  selection: FloatMenuSelection;
  followUp?: string;
  history?: DialogueHistoryTurn[];
}): Promise<DialogueReply> {
  const prompt = buildDialoguePrompt(args.selection, args.followUp);
  const resp = await apiFetch("/thought-partner", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: dialogueBody(args),
  });
  if (!resp.ok) {
    throw new ApiError(
      `POST /thought-partner failed: HTTP ${resp.status}`,
      resp.status,
      await resp.text(),
    );
  }
  const data = await resp.json();
  const reply: string = data.text ?? data.body ?? "";
  return { prompt, reply, threadNodeId: data.thread_node_id ?? null };
}

/** One SSE frame from the streamed Dialogue endpoint. */
export type DialogueStreamEvent =
  | { kind: "token"; text: string }
  | { kind: "thread"; node_id: string }
  | { kind: "done" }
  | { kind: "error"; status: number; detail: string };

/** Stream a dialogue turn over the selection via /thought-partner/stream (M2).
 * Calls `onEvent` for each SSE frame as it arrives — `token` frames render
 * progressively; a single `error` frame (no-key 503 / model 500) is the
 * recoverable failure the caller surfaces as AIActionFailure (NOT a frozen UI);
 * `done` marks a clean close, distinguishable from `error`.
 *
 * Robust to a mid-stream interruption: if the network drops, the reader's
 * `AbortSignal` fires, or the body ends WITHOUT a terminal `done`/`error`
 * frame, this resolves having delivered whatever arrived and the caller treats
 * a missing terminal frame as "interrupted" (recoverable), never a hang. */
export async function streamDialogueOverSelection(
  args: {
    investigationId: string;
    selection: FloatMenuSelection;
    followUp?: string;
    history?: DialogueHistoryTurn[];
    signal?: AbortSignal;
  },
  onEvent: (ev: DialogueStreamEvent) => void,
): Promise<void> {
  const resp = await apiFetch("/thought-partner/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: dialogueBody(args),
    signal: args.signal,
  });
  // A non-200 on the channel itself (rare — the endpoint puts errors in-band) is
  // still surfaced as a recoverable error frame, never a thrown frozen UI.
  if (!resp.ok || !resp.body) {
    onEvent({
      kind: "error",
      status: resp.status,
      detail: `stream channel HTTP ${resp.status}`,
    });
    return;
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    let chunk: ReadableStreamReadResult<Uint8Array>;
    try {
      chunk = await reader.read();
    } catch {
      // Mid-stream interruption (network drop / abort) — recoverable, not a hang.
      onEvent({ kind: "error", status: 0, detail: "stream interrupted" });
      return;
    }
    if (chunk.done) break;
    buffer += decoder.decode(chunk.value, { stream: true });
    // SSE frames are separated by a blank line; each carries a `data: …` line.
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      for (const line of frame.split("\n")) {
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice("data: ".length)) as DialogueStreamEvent);
        } catch {
          // A malformed frame is dropped (defensive) — never crashes the stream.
        }
      }
    }
  }
}
