// Tier-1 behavior event client (SPR-01 M6, TS half of the polyglot seam).
//
// Mirrors the API surface of substrate/behavior/api.py. Wave 2
// reading-surface code calls `emitBehaviorEvent` only; this module
// abstracts away whether the write is POSTed to an interfaces/research
// endpoint or stubbed (the production REST endpoint lands in a later
// sprint — today this is a no-op-on-the-wire client that returns
// the event id synchronously so call sites compile and pass type checks
// from day one).
//
// Stability contract (per SPR-01 M6): the exported signatures below
// MUST NOT change without bumping the consumer surfaces (SPR-04+).
// New optional fields are allowed.

// Closed vocabulary. Values mirror substrate/behavior/taxonomy.py
// BehaviorEventType.value. Keep in sync; if/when codegen extends to
// behavior taxonomy (tools/codegen/), this hand-written union goes
// away.
export const BehaviorEventType = {
  HIGHLIGHT_CREATED: "highlight_created",
  HIGHLIGHT_REMOVED: "highlight_removed",
  VOICE_NOTE_RECORDED: "voice_note_recorded",
  VOICE_NOTE_PLAYED: "voice_note_played",
  AI_PROMPT_SENT: "ai_prompt_sent",
  AI_RESPONSE_ACCEPTED: "ai_response_accepted",
  AI_RESPONSE_REJECTED: "ai_response_rejected",
  CITE_JUMP: "cite_jump",
  CROSS_DOC_LINK_SURFACED: "cross_doc_link_surfaced",
  CROSS_DOC_LINK_CLICKED: "cross_doc_link_clicked",
  CROSS_DOC_LINK_DISMISSED: "cross_doc_link_dismissed",
  CROSS_DOC_LINK_PREVIEWED: "cross_doc_link_previewed", // v2 — SPR-07 hover funnel
  READING_MODE_TOGGLED: "reading_mode_toggled",
  DOCUMENT_OPENED: "document_opened",
  DOCUMENT_CLOSED: "document_closed",
  DOCUMENT_IMPORTED: "document_imported", // v2 — SPR-06 universal-library import
  NOTEBOOK_BLOCK_DEMOTED: "notebook_block_demoted",
  NOTEBOOK_BLOCK_EDITED: "notebook_block_edited",
  NOTEBOOK_BLOCK_PROMOTED: "notebook_block_promoted", // v2 — SPR-11 Tier-2 → Tier-3 promote
} as const;

export type BehaviorEventTypeValue =
  (typeof BehaviorEventType)[keyof typeof BehaviorEventType];

// The closed set as a runtime array so we can validate dynamic strings
// (the InvalidEventType analog).
export const ALL_BEHAVIOR_EVENT_TYPES: readonly BehaviorEventTypeValue[] =
  Object.values(BehaviorEventType);

export class InvalidEventTypeError extends Error {
  constructor(eventType: string) {
    super(
      `unknown behavior event type ${JSON.stringify(eventType)}; ` +
        `valid: ${ALL_BEHAVIOR_EVENT_TYPES.join(", ")}`,
    );
    this.name = "InvalidEventTypeError";
  }
}

// The default user_id constant matches substrate.behavior.api.DEFAULT_USER_ID
// and the substrate.graph owner_user_id default.
export const DEFAULT_USER_ID = "__operator__";

// Argument shape for emit. Optional fields default the way the Python
// API does. State + action are intentionally loose (Record<string,
// unknown>) at the TS boundary — Wave 2 surfaces should be using the
// codegen-emitted per-event-type interfaces once those exist; today
// the closed taxonomy and the runtime JSON-schema validation on the
// server side are the canonical guards.
export interface EmitBehaviorEventOptions {
  eventType: BehaviorEventTypeValue;
  state: Record<string, unknown>;
  action: Record<string, unknown>;
  outcome?: Record<string, unknown>;
  userId?: string;
  sessionId?: string;
  documentId?: string;
}

export interface EmitBehaviorEventResult {
  eventId: string;
}

// Opaque event id. Format mirrors substrate.behavior.api._new_event_id
// so a string can be grepped across the polyglot seam.
function newEventId(): string {
  const hex = Math.floor(Math.random() * 0xffffffffffff)
    .toString(16)
    .padStart(12, "0");
  const ms = Date.now();
  return `evt-${hex}-${ms}`;
}

function assertKnownEventType(
  eventType: string,
): asserts eventType is BehaviorEventTypeValue {
  if (!(ALL_BEHAVIOR_EVENT_TYPES as readonly string[]).includes(eventType)) {
    throw new InvalidEventTypeError(eventType);
  }
}

// Web client emit. Returns synchronously with the opaque event id;
// the server-side queue + DP shuffler are invisible to the caller.
//
// Wire layer: until the REST endpoint lands (a later sprint that
// front-ends substrate/behavior/api.py), this function returns the
// minted id but does NOT POST anywhere — Wave 2 surfaces can call it
// at the right call sites with zero crash risk. The grep gate
// `rg "emit_behavior_event" apps/ --type ts` will find this exported
// definition; the verification gate "No production emit yet" asserts
// no surface CALLER imports this module.
export function emitBehaviorEvent(
  options: EmitBehaviorEventOptions,
): EmitBehaviorEventResult {
  // Validate the type at the boundary. Mirrors the Python
  // InvalidEventType raise.
  assertKnownEventType(options.eventType);

  // Mint the id BEFORE any side effect, matching the Python API's
  // privacy posture (the caller holds the id either way; we don't
  // leak consent state via the return value).
  const eventId = newEventId();

  // When the REST endpoint lands, the body below will POST to
  // /api/behavior/emit with the options + an Idempotency-Key header
  // set to eventId. For SPR-01 we keep the network call out so
  // Wave 2 callers can be written + type-checked without server
  // dependencies.
  //
  // Intentionally NOT exported: see the verification gate
  // `rg "emit_behavior_event" apps/ --type ts` — this module is
  // the ONLY place the function lives in TS land at SPR-01 closeout.
  void options.userId;
  void options.sessionId;
  void options.documentId;
  void options.outcome;
  void options.state;
  void options.action;
  void DEFAULT_USER_ID;

  return { eventId };
}
