// Hand-written TS mirror of the per-second frame-attention telemetry CONTRACT.
//
// Source of truth: substrate/ad_inventory/frame_attention.py (SPR-05 M2).
// SPR-05's codegen (tools/codegen/emit_contracts.py) mirrors only the ACCRUAL
// *output* shape into src/generated/contracts.ts (AccrualContract +
// CONTRACT_SCHEMA_VERSION). It does NOT emit the telemetry INPUT shapes
// (WindowFrameBatch / FrameSecond / FrameAttentionSample), so the SPR-07
// emitter cannot type its wire payload against the generated file. These
// interfaces are therefore hand-written here, matching frame_attention.py
// field-for-field, and pinned by frameContract.test.ts.
//
// SEAM / FOLLOW-UP (handoff): the codegen omission is a real gap — a future
// SPR-05/codegen change could emit these input shapes the way it emits
// AccrualContract, at which point this file is replaced by an import from
// the generated contracts. Until then, the test is the drift guard: it pins
// the exact field set + the stamped schema version against the Python module's
// values, so the contract cannot silently diverge from the backend.

/**
 * The telemetry wire-shape version. Mirrors
 * ``frame_attention.FRAME_TELEMETRY_SCHEMA_VERSION``. Stamped onto every
 * batch the emitter flushes so a batch sent by an old emitter is identifiable
 * and a version mismatch is DETECTABLE at the seam, never a silent divergence.
 *
 * If this string and the Python constant drift, frameContract.test.ts fails —
 * that is the whole point of the pin.
 */
export const FRAME_TELEMETRY_SCHEMA_VERSION = "frame-telemetry-v1";

/**
 * The four product workflows a window can belong to. Mirrors
 * ``frame_attention.VALID_LENSES`` (validated at FrameSecond construction
 * on the backend).
 */
export const VALID_LENSES = ["read", "research", "write", "speak"] as const;
export type Lens = (typeof VALID_LENSES)[number];

/**
 * One IP asset's in-frame VISIBILITY for one second. Mirrors
 * ``frame_attention.FrameAttentionSample``. Ranges are the contract's
 * (the backend re-validates on ingest; the emitter MUST already conform):
 *
 *  - viewport_area_fraction ∈ [0,1] — fraction of the viewport this asset
 *    occupied this second (1.0 = filled the whole viewport).
 *  - prominence ∈ [0,1] — position/salience (1.0 = center/foreground).
 *  - focused_dwell_ms ∈ [0,1000] — focused, foregrounded dwell ms this second.
 *    Dwell while the tab is hidden/idle does NOT count and is not reported.
 *  - content_class — a HINT only; the backend resolves the authoritative
 *    value server-side and never trusts the client. The emitter leaves it
 *    undefined (the working region exposes no trustworthy class), which the
 *    backend treats as "resolve it".
 *  - chunk_id — the specific chunk in frame, or undefined for a cover/title
 *    card (the ASSET earns; the chunk is trace detail).
 */
export interface FrameAttentionSample {
  asset_id: string;
  viewport_area_fraction: number;
  prominence: number;
  focused_dwell_ms: number;
  content_class?: string | null;
  chunk_id?: string | null;
}

/**
 * One second of one window: the active lens + the in-frame assets. Mirrors
 * ``frame_attention.FrameSecond``. ``second_index`` is the 0-based second
 * offset within the window (second 0 = the first second the window was on
 * screen); the backend sums over it, it never becomes a row of its own.
 */
export interface FrameSecond {
  second_index: number;
  lens: Lens;
  samples: FrameAttentionSample[];
}

/**
 * The compact per-window batch the emitter flushes — the unit the backend
 * consumes, NOT one request per second. Mirrors
 * ``frame_attention.WindowFrameBatch``.
 *
 * ``ad_value_usd_cents`` is the window's total ad value for the seconds in
 * this batch, an INPUT priced by SPR-10's auction (out of scope here); the
 * emitter sends 0 until that pricing exists, which is honest (no fabricated
 * value). ``schema_version`` defaults to the stamped constant.
 */
export interface WindowFrameBatch {
  window_id: string;
  seconds: FrameSecond[];
  ad_value_usd_cents: number;
  schema_version: string;
}
