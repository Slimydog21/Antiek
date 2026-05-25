/**
 * Pre-outline context window — pure state→request core (specs/write/ SPR-08).
 *
 * Before any formal outline, a writer drops lego blocks into a context
 * window and states an objective, then generates directly. This module is
 * the pure, testable core: it maps the context-window state to the
 * ``/write/context/promote`` request (SPR-08 M4) and enforces the
 * no-blocks-no-fabrication gate (rigor #3: "an objective with no blocks at
 * all — don't fabricate sources").
 *
 * The freeform generate path reuses the built endpoints rather than a
 * second generator: promote → generate the resulting section, so the
 * citation + voice_style + gap contracts (SPR-06) are identical to the
 * outline path. Provenance is preserved on promotion (node items stay
 * node-backed; user items stay user-originated — no fabricated citation).
 */

export interface ContextItem {
  /** Display label for the chip. */
  label: string;
  block_kind: "insight" | "open_question" | "claim" | "user_authored";
  /** Node-backed item (from the repository) carries node_id; a
   * user-originated item carries content. Exactly one is set. */
  node_id?: string;
  content?: string;
}

export interface ContextWindowState {
  title: string;
  objective: string;
  items: ContextItem[];
}

export interface PromoteBlockSpec {
  section_id: string; // placeholder; the backend creates the real section
  block_kind: "insight" | "open_question" | "operator_note" | "claim" | "user_authored" | "synthesized";
  provenance_kind: "graph_node" | "user_authored" | "synthesized" | "brainstorm";
  node_id: string | null;
  content: string | null;
  block_index: number;
}

export interface PromoteContextBody {
  title: string;
  deliverable_kind: string;
  objective: string;
  blocks: PromoteBlockSpec[];
}

const _NODE_KINDS = new Set(["insight", "open_question", "claim"]);

/** Map a context item to a promote block spec, preserving provenance:
 * a node item → graph_node + node_id; a user item → user_authored +
 * content (never a fabricated node). */
export function itemToSpec(item: ContextItem, index: number): PromoteBlockSpec {
  const isNode = !!item.node_id && _NODE_KINDS.has(item.block_kind);
  return {
    section_id: "__context__", // ignored by the backend; it creates the section
    block_kind: item.block_kind,
    provenance_kind: isNode ? "graph_node" : "user_authored",
    node_id: isNode ? item.node_id ?? null : null,
    content: isNode ? null : item.content ?? "",
    block_index: index,
  };
}

export function contextToPromoteRequest(
  state: ContextWindowState,
  deliverableKind = "general_essay",
): PromoteContextBody {
  return {
    title: state.title.trim() || (state.objective.trim().slice(0, 80) || "Untitled draft"),
    deliverable_kind: deliverableKind,
    objective: state.objective.trim(),
    blocks: state.items.map(itemToSpec),
  };
}

export interface Generatability {
  ok: boolean;
  reason: string;
}

/** The no-blocks-no-fabrication gate (SPR-08 rigor #3). An objective with
 * no blocks must NOT generate fabricated sources — it prompts for blocks
 * instead. */
export function generatability(state: ContextWindowState): Generatability {
  if (state.items.length === 0) {
    return {
      ok: false,
      reason: "Place at least one block — an objective alone won't fabricate sources.",
    };
  }
  if (!state.objective.trim()) {
    return { ok: false, reason: "State a writing objective (text or voice)." };
  }
  return { ok: true, reason: "" };
}
