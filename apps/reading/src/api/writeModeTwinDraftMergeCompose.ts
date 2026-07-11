/**
 * Write-mode twin draft merge compose (pure).
 *
 * Operator vision: recursive twin note-taker substrate of insights/questions
 * can be leveraged into writing — merge twin notes into a provisional HTML
 * write draft before full author commit.
 *
 * draft_written always false.
 * merge_executed always false.
 * store_mutated always false.
 */

export interface TwinWriteSlice {
  parent_asset_id: string;
  insights: string[];
  questions: string[];
}

export interface WriteModeTwinDraftMergeInput {
  draft_id: string;
  /** Optional existing write body (caller-supplied HTML/text). */
  base_draft_html?: string | null;
  slices: TwinWriteSlice[];
  operator_ack: boolean;
}

export interface WriteModeTwinDraftMergeCompose {
  draft_id: string;
  parent_asset_ids: string[];
  sections: string[];
  section_count: number;
  insight_count: number;
  question_count: number;
  /** True when ≥1 insight/question and operator_ack. */
  draft_ready: boolean;
  /** Always false — pure layer never writes draft assets. */
  draft_written: false;
  /** Always false — pure layer never merges into published write. */
  merge_executed: false;
  /** Always false — no store mutation. */
  store_mutated: false;
  notes: string[];
  authority: "write_mode_twin_draft_merge_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build a provisional write draft from twin substrate slices.
 * Never invents insights/questions; never writes assets.
 */
export function composeWriteModeTwinDraftMerge(
  input: WriteModeTwinDraftMergeInput,
): WriteModeTwinDraftMergeCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const draft_id = requireNonEmpty(input.draft_id, "draft_id");
  if (!Array.isArray(input.slices) || input.slices.length === 0) {
    throw new Error("slices must be a non-empty array");
  }

  const notes: string[] = [
    "draft_written=false — provisional write draft not persisted",
    "merge_executed=false — published write not mutated",
    "store_mutated=false",
    "twin content is caller-supplied only (no invent)",
  ];

  const sections: string[] = [];
  if (input.base_draft_html != null && input.base_draft_html !== undefined) {
    if (
      typeof input.base_draft_html !== "string" ||
      !input.base_draft_html.trim()
    ) {
      throw new Error("base_draft_html must be non-empty string when set");
    }
    sections.push(
      `<section data-role="base-draft" data-draft="${draft_id}">${input.base_draft_html.trim()}</section>`,
    );
  } else {
    notes.push("base_draft_html absent — twin-only draft scaffold");
  }

  const parent_asset_ids: string[] = [];
  const seen = new Set<string>();
  let insight_count = 0;
  let question_count = 0;

  for (let i = 0; i < input.slices.length; i++) {
    const sl = input.slices[i];
    if (!sl || typeof sl !== "object") {
      throw new Error(`slices[${i}] must be an object`);
    }
    const parent = requireNonEmpty(
      sl.parent_asset_id,
      `slices[${i}].parent_asset_id`,
    );
    if (seen.has(parent)) {
      throw new Error(`duplicate parent_asset_id: ${parent}`);
    }
    seen.add(parent);
    parent_asset_ids.push(parent);

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
      sections.push(
        `<section data-role="twin-insight" data-parent="${parent}">${ins}</section>`,
      );
      insight_count += 1;
    }
    for (let j = 0; j < sl.questions.length; j++) {
      const q = requireNonEmpty(
        sl.questions[j],
        `slices[${i}].questions[${j}]`,
      );
      sections.push(
        `<section data-role="twin-question" data-parent="${parent}">${q}</section>`,
      );
      question_count += 1;
    }
  }

  const hasTwin = insight_count + question_count >= 1;
  const draft_ready = input.operator_ack && hasTwin;

  notes.push(
    `parents=${parent_asset_ids.length} · insights=${insight_count} · questions=${question_count}`,
  );
  if (!input.operator_ack) {
    notes.push("draft_ready=false — operator_ack required");
  } else if (!hasTwin) {
    notes.push("draft_ready=false — no twin insights/questions (no invent)");
  } else {
    notes.push(
      `draft_ready=true · sections=${sections.length} (provisional only)`,
    );
  }

  notes.push("draft_written=false");
  notes.push("merge_executed=false");
  notes.push("store_mutated=false");

  return {
    draft_id,
    parent_asset_ids,
    sections,
    section_count: sections.length,
    insight_count,
    question_count,
    draft_ready,
    draft_written: false,
    merge_executed: false,
    store_mutated: false,
    notes,
    authority: "write_mode_twin_draft_merge_compose_advisory",
  };
}

export function formatWriteModeTwinDraftMergeSummary(
  c: WriteModeTwinDraftMergeCompose,
): string {
  return (
    `draft_ready=${c.draft_ready} · sections=${c.section_count} · ` +
    `insights=${c.insight_count} · questions=${c.question_count} · ` +
    `draft_written=false · merge_executed=false`
  );
}
