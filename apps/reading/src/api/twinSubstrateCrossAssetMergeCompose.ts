/**
 * Twin substrate cross-asset merge compose (pure).
 *
 * Operator vision: every information asset has a twin of insights/questions;
 * that substrate can be merged, referenced, and leveraged across combining
 * contexts on the infinite information platform.
 *
 * merge_executed always false.
 * twin_written always false.
 * store_mutated always false.
 */

export interface TwinSubstrateSlice {
  parent_asset_id: string;
  twin_asset_id?: string;
  /** Caller-supplied insights only. */
  insights: string[];
  /** Caller-supplied questions only. */
  questions: string[];
}

export interface TwinSubstrateCrossAssetMergeInput {
  /** Operator-facing pack id for this merge proposal. */
  pack_id: string;
  slices: TwinSubstrateSlice[];
  operator_ack: boolean;
}

export interface TwinSubstrateCrossAssetMergeCompose {
  pack_id: string;
  parent_asset_ids: string[];
  parent_count: number;
  insight_count: number;
  question_count: number;
  /** Flattened caller-supplied insights (no invent). */
  insights: string[];
  /** Flattened caller-supplied questions (no invent). */
  questions: string[];
  /**
   * True when ≥2 parents, ≥1 insight or question total, operator_ack.
   * Still does not write twins or merge assets.
   */
  merge_ready: boolean;
  /** Always false — pure layer never executes twin merge. */
  merge_executed: false;
  /** Always false — pure layer never writes twin documents. */
  twin_written: false;
  /** Always false — no store mutation. */
  store_mutated: false;
  notes: string[];
  authority: "twin_substrate_cross_asset_merge_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Propose merging twin substrate across ≥2 parent assets.
 * Never invents insights/questions; never writes or merges.
 */
export function composeTwinSubstrateCrossAssetMerge(
  input: TwinSubstrateCrossAssetMergeInput,
): TwinSubstrateCrossAssetMergeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const pack_id = requireNonEmpty(input.pack_id, "pack_id");
  if (!Array.isArray(input.slices) || input.slices.length < 2) {
    throw new Error("slices must be an array of at least 2 parent twins");
  }

  const notes: string[] = [
    "merge_executed=false — cross-asset twin merge is intent only",
    "twin_written=false — twin documents not created/updated here",
    "store_mutated=false",
    "insights/questions are caller-supplied only (no invent)",
  ];

  const parent_asset_ids: string[] = [];
  const seenParents = new Set<string>();
  const insights: string[] = [];
  const questions: string[] = [];

  for (let i = 0; i < input.slices.length; i++) {
    const sl = input.slices[i];
    if (!sl || typeof sl !== "object") {
      throw new Error(`slices[${i}] must be an object`);
    }
    const parent = requireNonEmpty(
      sl.parent_asset_id,
      `slices[${i}].parent_asset_id`,
    );
    if (seenParents.has(parent)) {
      throw new Error(`duplicate parent_asset_id: ${parent}`);
    }
    seenParents.add(parent);
    parent_asset_ids.push(parent);

    if (sl.twin_asset_id != null) {
      requireNonEmpty(sl.twin_asset_id, `slices[${i}].twin_asset_id`);
    }
    if (!Array.isArray(sl.insights)) {
      throw new Error(`slices[${i}].insights must be an array`);
    }
    if (!Array.isArray(sl.questions)) {
      throw new Error(`slices[${i}].questions must be an array`);
    }
    for (let j = 0; j < sl.insights.length; j++) {
      const ins = requireNonEmpty(
        sl.insights[j],
        `slices[${i}].insights[${j}]`,
      );
      insights.push(ins);
    }
    for (let j = 0; j < sl.questions.length; j++) {
      const q = requireNonEmpty(
        sl.questions[j],
        `slices[${i}].questions[${j}]`,
      );
      questions.push(q);
    }
  }

  const parent_count = parent_asset_ids.length;
  const insight_count = insights.length;
  const question_count = questions.length;
  notes.push(
    `parents=${parent_count} · insights=${insight_count} · questions=${question_count}`,
  );

  const hasSubstrate = insight_count + question_count >= 1;
  const merge_ready =
    input.operator_ack && parent_count >= 2 && hasSubstrate;

  if (!input.operator_ack) {
    notes.push("merge_ready=false — operator_ack required");
  } else if (!hasSubstrate) {
    notes.push(
      "merge_ready=false — no insights/questions (no invent substrate)",
    );
  } else {
    notes.push("merge_ready=true — provisional cross-asset twin pack");
  }

  notes.push("merge_executed=false");
  notes.push("twin_written=false");
  notes.push("store_mutated=false");

  return {
    pack_id,
    parent_asset_ids,
    parent_count,
    insight_count,
    question_count,
    insights,
    questions,
    merge_ready,
    merge_executed: false,
    twin_written: false,
    store_mutated: false,
    notes,
    authority: "twin_substrate_cross_asset_merge_compose_advisory",
  };
}

export function formatTwinSubstrateCrossAssetMergeSummary(
  c: TwinSubstrateCrossAssetMergeCompose,
): string {
  return (
    `merge_ready=${c.merge_ready} · parents=${c.parent_count} · ` +
    `insights=${c.insight_count} · questions=${c.question_count} · ` +
    `merge_executed=false · twin_written=false`
  );
}
