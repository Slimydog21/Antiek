import type { ComponentType } from "react";

/**
 * StationActivity — the contract for a thing Werner does at his fixed station.
 *
 * ─── THE NO-MOVE INVARIANT (why this type is shaped the way it is) ───────────
 * An activity declares appearance + a cursor-instrument; the contract grants
 * it no authority to move the penguin. This type deliberately
 * has NO whereabouts field, NO ref, NO setter that could steer Werner: an
 * activity may toggle ambient CSS classes and mount a cursor-instrument, and
 * that is ALL. The fixed-station model (2026-07-02 operator ratification,
 * docs/htmlspec/werner-fixed-station/DESIGN.md) is represented here BY TYPE: a
 * caller cannot pass a Werner ref, position, or movement command through the
 * activity surface. The companion activity-boundary test rejects direct
 * movement/navigation/network imports and APIs in implementation modules. The reel
 * (SPR-15) was a whole subsystem; an activity is a declaration.
 *
 * The registry that holds these (registry.ts) exists so SPR-03/04/05 add
 * activities as REGISTRATIONS, not rewrites, and so this invariant is stated
 * in exactly one place a maintainer will re-read before widening the catalog.
 * ─────────────────────────────────────────────────────────────────────────────
 */

/** The catalogued activities. Only ice-fishing exists today; the arcade
 *  (SPR-05) and the easter egg (SPR-04) widen this union later. */
export type ActivityId = "ice-fishing" | "research-lens";

/** The useMouseFollow read-seam fields an instrument is allowed to consume.
 *  Note what is ABSENT: any read of the penguin's own whereabouts. An
 *  instrument reads the CURSOR, never Werner. */
export type InstrumentSeamField = "live" | "pointerIdle" | "tabHidden";

/** Props every cursor-instrument accepts. `disabled` mirrors the mascot's
 *  reduced-motion / flag freeze; the instrument subscribes to the cursor seam
 *  (useMouseFollow) itself — it is handed no penguin state. */
export interface CursorInstrumentProps {
  disabled?: boolean;
}

/**
 * A cursor-instrument: the React component an activity mounts at the cursor
 * (for ice-fishing, the bait worm + the rod-tip→cursor line), plus a manifest
 * of which read-seam fields it consumes. The manifest is documentation the
 * type carries: an instrument declares WHICH cursor signals it reads, and is
 * given no such capability through this contract.
 */
export interface CursorInstrument {
  readonly render: ComponentType<CursorInstrumentProps>;
  readonly reads: readonly InstrumentSeamField[];
}

/**
 * How an activity becomes reachable. Only "default" is wired this sprint; the
 * easter-egg variant is declared now (SPR-04 will wire the sequence trigger)
 * so the registry's shape is stable across Wave 1 and downstream sprints add a
 * variant, not a field.
 */
export type ActivityUnlock =
  | { readonly kind: "default" }
  | { readonly kind: "route"; readonly policyId: "knowledge-work" }
  | { readonly kind: "easter-egg"; readonly sequenceId: string };

/**
 * A thing Werner does at his station: appearance (ambient CSS classes) + a
 * cursor-instrument + an unlock rule. Deliberately NO whereabouts field — see
 * the no-move invariant at the head of this file.
 */
export interface StationActivity {
  readonly id: ActivityId;
  readonly label: string;
  readonly ambient: {
    /** Class toggled while the pointer is ACTIVE, or null when the active
     *  state carries no ambient class (ice-fishing: the line-to-cursor is the
     *  instrument's job, so there is none). */
    readonly activeClass: string | null;
    /** Class toggled while the pointer is IDLE, or null when the activity keeps
     *  Werner in his neutral station pose. Ice fishing uses the own-hole
     *  never-catch gag ("werner-fishing"); research lens uses null. */
    readonly idleClass: string | null;
  };
  readonly instrument: CursorInstrument;
  readonly unlock: ActivityUnlock;
}
