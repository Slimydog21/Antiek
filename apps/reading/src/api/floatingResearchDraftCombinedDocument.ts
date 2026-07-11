/**
 * Floating research → provisional combined draft document (pure).
 *
 * Operator vision: after floating deep research, create a draft version with
 * the combined document (parent + research findings) before fully merging.
 *
 * draft_written always false — provisional scaffold only; never mutates parent.
 * merge_executed always false.
 */

export type DraftSourceStatus = "proposed" | "open" | "completed" | "closed";

export interface FloatingDraftSource {
  instance_id: string;
  parent_asset_id: string;
  status: DraftSourceStatus;
  highlight?: string;
  /** Caller-supplied findings / HTML fragments — never invented. */
  findings?: string[];
}

export interface ProvisionalCombinedDraft {
  parent_asset_id: string;
  instance_ids: string[];
  /** Provisional HTML-ish sections for preview (caller-supplied content only). */
  sections: string[];
  section_count: number;
  /** True when ≥1 finding or highlight section present. */
  draft_ready: boolean;
  operator_ack: boolean;
  /** Always false — pure layer never writes draft asset. */
  draft_written: false;
  /** Always false — pure layer never merges into parent. */
  merge_executed: false;
  notes: string[];
  authority: "floating_research_draft_combined_document_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build a provisional combined draft document from parent excerpt + floating
 * research sources. Never invents findings; never writes assets.
 */
export function composeFloatingResearchDraftCombinedDocument(input: {
  parent_asset_id: string;
  /** Optional parent document excerpt/HTML (caller-supplied). */
  parent_excerpt?: string | null;
  sources: FloatingDraftSource[];
  operator_ack: boolean;
}): ProvisionalCombinedDraft {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (!Array.isArray(input.sources) || input.sources.length === 0) {
    throw new Error("sources must be a non-empty array");
  }

  const notes: string[] = [
    "draft_written=false — provisional combined document not persisted",
    "merge_executed=false — parent asset not mutated",
    "section content is caller-supplied only (no invent)",
  ];

  const sections: string[] = [];
  if (input.parent_excerpt != null && input.parent_excerpt !== undefined) {
    if (typeof input.parent_excerpt !== "string" || !input.parent_excerpt.trim()) {
      throw new Error("parent_excerpt must be non-empty string when set");
    }
    sections.push(
      `<section data-role="parent" data-asset="${parent_asset_id}">${input.parent_excerpt.trim()}</section>`,
    );
  } else {
    notes.push("parent_excerpt absent — draft scaffold without parent body");
  }

  const instance_ids: string[] = [];
  const seen = new Set<string>();

  for (let i = 0; i < input.sources.length; i++) {
    const s = input.sources[i];
    if (!s || typeof s !== "object") {
      throw new Error(`sources[${i}] must be an object`);
    }
    const id = requireNonEmpty(s.instance_id, `sources[${i}].instance_id`);
    const p = requireNonEmpty(
      s.parent_asset_id,
      `sources[${i}].parent_asset_id`,
    );
    if (p !== parent_asset_id) {
      throw new Error("all sources must share parent_asset_id");
    }
    if (
      s.status !== "proposed" &&
      s.status !== "open" &&
      s.status !== "completed"
    ) {
      throw new Error(
        `sources[${i}] status must be proposed|open|completed (not closed)`,
      );
    }
    if (seen.has(id)) {
      throw new Error(`duplicate instance_id: ${id}`);
    }
    seen.add(id);
    instance_ids.push(id);

    if (s.highlight != null) {
      if (typeof s.highlight !== "string" || !s.highlight.trim()) {
        throw new Error(
          `sources[${i}].highlight must be non-empty string when set`,
        );
      }
      sections.push(
        `<section data-role="highlight" data-instance="${id}">${s.highlight.trim()}</section>`,
      );
    }
    if (s.findings != null) {
      if (!Array.isArray(s.findings)) {
        throw new Error(`sources[${i}].findings must be string[] when set`);
      }
      for (let j = 0; j < s.findings.length; j++) {
        const f = s.findings[j];
        if (typeof f !== "string" || !f.trim()) {
          throw new Error(
            `sources[${i}].findings[${j}] must be non-empty string`,
          );
        }
        sections.push(
          `<section data-role="finding" data-instance="${id}">${f.trim()}</section>`,
        );
      }
    }
  }

  const hasResearchContent = sections.some(
    (sec) =>
      sec.includes('data-role="highlight"') ||
      sec.includes('data-role="finding"'),
  );
  const draft_ready = hasResearchContent;
  if (!draft_ready) {
    notes.push(
      "draft_ready=false — no highlight/finding content (no invent sections)",
    );
  } else {
    notes.push(
      `draft_ready=true · sections=${sections.length} · instances=${instance_ids.length}`,
    );
  }
  if (!input.operator_ack) {
    notes.push(
      "operator_ack=false — preview-only; still draft_written=false",
    );
  } else {
    notes.push(
      "operator_ack=true — ack for draft preview only; still draft_written=false",
    );
  }
  notes.push("draft_written=false");
  notes.push("merge_executed=false");

  return {
    parent_asset_id,
    instance_ids,
    sections,
    section_count: sections.length,
    draft_ready,
    operator_ack: input.operator_ack,
    draft_written: false,
    merge_executed: false,
    notes,
    authority: "floating_research_draft_combined_document_advisory",
  };
}

export function formatFloatingDraftCombinedSummary(
  d: ProvisionalCombinedDraft,
): string {
  return (
    `draft combined · sections=${d.section_count} · ready=${d.draft_ready} · ` +
    `draft_written=false · merge_executed=false`
  );
}
