/**
 * Highlight → floating deep research + twin bind bridge (pure).
 *
 * Operator vision: from a single highlight, spin up a floating deep research
 * instance and propose a recursive twin of insights/questions together.
 *
 * Composes existing pure modules; never invents content, never live-dispatches,
 * never creates twin store rows.
 */

import {
  spawnFloatingFromHighlight,
  type FloatingDeepResearchInstance,
} from "./floatingDeepResearch";
import {
  evaluateRecursiveTwinBind,
  type RecursiveTwinBindDecision,
  type TwinBindSource,
} from "./recursiveTwinBind";

export interface HighlightFloatingTwinBridgeInput {
  parent_asset_id: string;
  highlight: string;
  /** Required gate provenance from reader host. */
  gated: boolean;
  /** Optional deep research prompt override. */
  prompt?: string;
  insights?: string[] | null;
  questions?: string[] | null;
  /**
   * Provenance for twin insights/questions.
   * Defaults to highlight_seed when not using llm_note_taker.
   */
  twin_source?: TwinBindSource;
  llm_filled?: boolean;
}

export interface HighlightFloatingTwinBridgeResult {
  parent_asset_id: string;
  highlight: string;
  floating: FloatingDeepResearchInstance;
  twin_bind: RecursiveTwinBindDecision;
  /** Always false — pure bridge does not dispatch research. */
  live_dispatched: false;
  /** Always false — pure bridge does not write twin store. */
  twin_created: false;
  notes: string[];
  authority: "highlight_floating_twin_bridge_advisory";
}

/**
 * From one highlight, propose floating DR spawn + twin bind together.
 * Fail closed on gated highlights. Honesty flags always false.
 */
export function bridgeHighlightToFloatingAndTwin(
  input: HighlightFloatingTwinBridgeInput,
): HighlightFloatingTwinBridgeResult {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.gated !== "boolean") {
    throw new Error(
      "gated must be an explicit boolean from highlight provenance (fail closed)",
    );
  }
  if (input.gated === true) {
    throw new Error(
      "gated/withheld highlight cannot bridge floating deep research or twin bind",
    );
  }

  const parent = String(input.parent_asset_id || "").trim();
  const highlight = String(input.highlight || "").trim();
  if (!parent) throw new Error("parent_asset_id must be a non-empty string");
  if (!highlight) throw new Error("highlight must be a non-empty string");

  const llm_filled =
    typeof input.llm_filled === "boolean" ? input.llm_filled : false;
  const twin_source: TwinBindSource =
    input.twin_source ??
    (llm_filled ? "llm_note_taker" : "highlight_seed");

  const floating = spawnFloatingFromHighlight({
    parent_asset_id: parent,
    highlight,
    prompt: input.prompt,
    gated: false,
    view_mode: "floating",
  });

  const twin_bind = evaluateRecursiveTwinBind({
    parent_asset_id: parent,
    insights: input.insights ?? null,
    questions: input.questions ?? null,
    source: twin_source,
    llm_filled,
    gated: false,
  });

  if (floating.live_dispatched !== false) {
    throw new Error("floating.live_dispatched must be false");
  }
  if (twin_bind.twin_created !== false) {
    throw new Error("twin_bind.twin_created must be false");
  }

  const notes = [
    "bridged highlight → floating deep research + twin bind",
    "live_dispatched=false",
    "twin_created=false",
    `floating.instance_id=${floating.instance_id}`,
    `twin.bind_allowed=${twin_bind.bind_allowed}`,
    ...floating.notes.slice(0, 2),
    ...twin_bind.notes.slice(0, 2),
  ];

  return {
    parent_asset_id: parent,
    highlight,
    floating,
    twin_bind,
    live_dispatched: false,
    twin_created: false,
    notes,
    authority: "highlight_floating_twin_bridge_advisory",
  };
}

export function formatBridgeSummary(
  r: HighlightFloatingTwinBridgeResult,
): string {
  return (
    `floating=${r.floating.instance_id} · twin_bind=${r.twin_bind.bind_allowed} · ` +
    `live_dispatched=false · twin_created=false`
  );
}
