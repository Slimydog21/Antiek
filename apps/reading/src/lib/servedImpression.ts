/**
 * Served-impression emission (Own Your Mind P0, 10-p0-implementation-brief §5).
 *
 * `surface.served_impression` is the audit-only "what was shown" event:
 * decoupled from training (no consumer trains on it in P0), emitted once per
 * surface render so the typed event log carries an honest record of which
 * surfaces were actually displayed.
 *
 * Discipline:
 *  - fire-and-forget: failures are swallowed (audit must never break UI)
 *  - once per mount: React StrictMode double-mounts in dev; a ref guards it
 *  - investigation_id "system": the reserved non-research namespace (same id
 *    the continuous daemon uses for its own events) — surface impressions are
 *    not research trajectories
 *  - ranked_position 0 / ranked_version "": no ranked stream exists yet; the
 *    fields exist so a future ranked surface can fill them without a schema
 *    bump (L8: log served impressions for audit, never train on them)
 */
import { useEffect, useRef } from "react";

import type { SurfaceServedImpressionPayload } from "../generated/types";
import { postTypedEvent, type TypedEventEnvelope } from "./api";

const SYSTEM_INVESTIGATION_ID = "system";
const OPERATOR_USER_ID = "__operator__";

export function emitServedImpression(input: {
  surface: string;
  itemKind: string;
  itemId: string;
}): void {
  const payload: SurfaceServedImpressionPayload = {
    action_type: "surface.served_impression",
    surface: input.surface,
    item_kind: input.itemKind,
    item_id: input.itemId,
    ranked_position: 0,
    ranked_version: "",
    timestamp: new Date().toISOString(),
    user_id: OPERATOR_USER_ID,
  };
  const envelope: TypedEventEnvelope = {
    investigation_id: SYSTEM_INVESTIGATION_ID,
    payload,
  };
  postTypedEvent(envelope).catch(() => {
    /* audit-only: never surface, never retry, never block the UI */
  });
}

/** Emit exactly once per mounted render of a surface (StrictMode-safe). */
export function useServedImpression(input: {
  surface: string;
  itemKind: string;
  itemId: string;
}): void {
  const emitted = useRef(false);
  useEffect(() => {
    if (emitted.current) return;
    emitted.current = true;
    emitServedImpression(input);
  }, [input.surface, input.itemKind, input.itemId]);
}
