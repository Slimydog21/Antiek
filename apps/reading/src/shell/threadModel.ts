/**
 * threadModel.ts — the frontend mirror of the SPR-06 thread VIEW.
 *
 * A "thread" is one graph entity's trajectory across the four workflows
 * (Research / Read / Write / Speak), referenced by the SAME node id at every
 * hop — a copy is a provenance bug. These types mirror the server-side
 * `substrate/seams/thread.py` / `interfaces/research/api/thread.py`
 * `ThreadResponse`; the breadcrumb + jump render this shape.
 *
 * Crucially this is a VIEW, not a stored entity (see thread.py rigor #2). The
 * frontend never mutates a thread; it reconstructs nothing — it renders what
 * GET /thread/{node_id} returns.
 */
import type { Workflow } from "./workflowTaxonomy";

/** One workflow's touch on the thread. `entityId` is the id the seam carried —
 *  the SAME canonical id at every hop (the no-duplicate invariant). */
export interface ThreadHop {
  workflow: Exclude<Workflow, "shared">;
  entityId: string;
  entityKind: string;
  /** The seam event that produced this hop (null on the origin hop). */
  seamEventId: string | null;
  seamActionType: string | null;
  provenanceRef: string | null;
  /** Whether the workflow this hop lands in has a built surface. An unbuilt hop
   *  renders as the SPR-04 honest stub, never a fake (intellectual honesty). */
  built: boolean;
  /** True only for the provisional write→speak seam. */
  viaProvisionalSeam: boolean;
}

/** An honest placeholder for a workflow the thread would touch but isn't built. */
export interface ThreadStub {
  workflow: Exclude<Workflow, "shared">;
  reason: string;
}

/** One entity's reconstructed cross-workflow trajectory. */
export interface Thread {
  canonicalEntityId: string;
  canonicalEntityKind: string;
  hops: ThreadHop[];
  stubs: ThreadStub[];
  isDegenerate: boolean;
}

/** The wire shape from GET /thread/{node_id} (snake_case from FastAPI). */
export interface ThreadResponseWire {
  canonical_entity_id: string;
  canonical_entity_kind: string;
  hops: Array<{
    workflow: Exclude<Workflow, "shared">;
    entity_id: string;
    entity_kind: string;
    seam_event_id: string | null;
    seam_action_type: string | null;
    provenance_ref: string | null;
    built: boolean;
    via_provisional_seam: boolean;
  }>;
  stubs: Array<{ workflow: Exclude<Workflow, "shared">; reason: string }>;
  is_degenerate: boolean;
}

/** Normalize the snake_case wire shape into the camelCase frontend model. */
export function threadFromWire(wire: ThreadResponseWire): Thread {
  return {
    canonicalEntityId: wire.canonical_entity_id,
    canonicalEntityKind: wire.canonical_entity_kind,
    isDegenerate: wire.is_degenerate,
    hops: wire.hops.map((h) => ({
      workflow: h.workflow,
      entityId: h.entity_id,
      entityKind: h.entity_kind,
      seamEventId: h.seam_event_id,
      seamActionType: h.seam_action_type,
      provenanceRef: h.provenance_ref,
      built: h.built,
      viaProvisionalSeam: h.via_provisional_seam,
    })),
    stubs: wire.stubs.map((s) => ({ workflow: s.workflow, reason: s.reason })),
  };
}

/**
 * The client-side no-duplicate check (mirrors thread.py
 * `assert_single_canonical_entity`). The breadcrumb's warrant is that every hop
 * references the one canonical id; if the server ever served a forked thread
 * (it refuses to — 409), the UI ALSO refuses to render continuity it can't
 * support. Returns the offending hop's id if a copy is present, else null.
 */
export function findForkedHop(thread: Thread): string | null {
  for (const hop of thread.hops) {
    if (hop.entityId !== thread.canonicalEntityId) return hop.entityId;
  }
  return null;
}
