/**
 * researchContextPack — TS handoff shapes for engagement_spine research context.
 *
 * Mirrors:
 *   substrate/engagement_spine/research_context.py  (ResearchContextPack)
 *   substrate/engagement_spine/source_refs.py       (SourceReference)
 *   substrate/engagement_spine/twin_promote.py      (TwinContextUnit)
 *   substrate/engagement_spine/collective.py        (CollectiveResearchUnit)
 *
 * Pure prompt assembly for the workstation chrome. Backend remains source of
 * truth for promote_* / DuckDB; this module formats packs already returned by
 * API or Python substrate for display / next-prompt injection.
 * view_format is always "html" — PDF is never the human view surface.
 */

export type TwinKind = "insight" | "question";
export type SourceKind = "arxiv" | "substack" | "url" | "unknown";

export type TwinContextUnit = {
  unit_id: string;
  twin_note_id: string;
  kind: TwinKind;
  text: string;
  canonical_text: string;
  asset_id: string;
  investigation_id: string;
  source?: "twin_promote";
  view_format?: "html";
};

export type SourceReference = {
  ref_id: string;
  kind: SourceKind;
  raw: string;
  canonical_url?: string | null;
  external_id?: string | null;
  title_hint?: string | null;
};

export type ResearchContextPack = {
  asset_id: string;
  spawn_id?: string | null;
  investigation_id?: string | null;
  twin_units: TwinContextUnit[];
  source_references: SourceReference[];
  query?: string | null;
  view_format: "html";
  /** Residual (kk/kl): reserved spawn research_tier when spawn scoped. */
  research_tier?: "fast" | "deep" | "wrestle" | string | null;
};

export type CollectiveResearchUnit = {
  collective_id: string;
  spawn_ids: string[];
  asset_ids: string[];
  investigation_ids: string[];
  twin_units: TwinContextUnit[];
  source_references: SourceReference[];
  view_format: "html";
  /** Residual (ke): per-spawn closed tiers from merge. */
  research_tiers?: string[];
  /** Residual (ke): depth-max of members for continue-as-unit default. */
  recommended_research_tier?: "fast" | "deep" | "wrestle" | string;
};

/** Build the same compact prompt block shape as Python ResearchContextPack.prompt_block. */
export function formatResearchContextPromptBlock(
  pack: ResearchContextPack,
  opts?: { maxTwins?: number; maxRefs?: number },
): string {
  const maxTwins = opts?.maxTwins ?? 12;
  const maxRefs = opts?.maxRefs ?? 12;
  const lines: string[] = [`# Research context for asset \`${pack.asset_id}\``];
  if (pack.spawn_id) lines.push(`spawn: ${pack.spawn_id}`);
  if (pack.research_tier) lines.push(`research_tier: ${pack.research_tier}`);
  if (pack.investigation_id) lines.push(`investigation: ${pack.investigation_id}`);
  if (pack.query) lines.push(`query filter: ${pack.query}`);
  lines.push("", "## Twin-derived insights & questions");
  if (!pack.twin_units.length) {
    lines.push("(none)");
  } else {
    for (const u of pack.twin_units.slice(0, maxTwins)) {
      lines.push(`- [${u.kind}] (${u.unit_id}) ${u.text}`);
    }
  }
  lines.push("", "## Source references (arxiv / substack / url)");
  if (!pack.source_references.length) {
    lines.push("(none)");
  } else {
    for (const r of pack.source_references.slice(0, maxRefs)) {
      const cite = r.canonical_url || r.raw;
      const eid = r.external_id ? ` id=${r.external_id}` : "";
      lines.push(`- [${r.kind}]${eid} ${cite}`);
    }
  }
  return lines.join("\n") + "\n";
}

/** Collective multi-spawn prompt block — mirrors CollectiveResearchUnit.prompt_block. */
export function formatCollectivePromptBlock(
  unit: CollectiveResearchUnit,
  opts?: { maxTwins?: number; maxRefs?: number },
): string {
  const maxTwins = opts?.maxTwins ?? 20;
  const maxRefs = opts?.maxRefs ?? 20;
  const lines: string[] = [
    `# Collective deep-research unit \`${unit.collective_id}\``,
    `spawns (${unit.spawn_ids.length}): ${unit.spawn_ids.join(", ")}`,
    `assets: ${unit.asset_ids.join(", ")}`,
    "",
    "## Merged twin-derived insights & questions",
  ];
  if (!unit.twin_units.length) {
    lines.push("(none)");
  } else {
    for (const u of unit.twin_units.slice(0, maxTwins)) {
      lines.push(`- [${u.kind}|${u.asset_id}] (${u.unit_id}) ${u.text}`);
    }
  }
  lines.push("", "## Merged source references");
  if (!unit.source_references.length) {
    lines.push("(none)");
  } else {
    for (const r of unit.source_references.slice(0, maxRefs)) {
      lines.push(`- [${r.kind}] ${r.canonical_url || r.raw}`);
    }
  }
  return lines.join("\n") + "\n";
}

/**
 * Lightweight offline parse for arxiv/substack-looking strings (UI pre-validate).
 * Authoritative parse lives in Python source_refs; this only classifies for chrome.
 */
export function detectSourceKindClient(raw: string): SourceKind {
  const text = (raw || "").trim();
  if (!text) return "unknown";
  const lower = text.toLowerCase();
  if (lower.startsWith("arxiv:") || lower.includes("arxiv.org") || /^\d{4}\.\d{4,5}/.test(text)) {
    return "arxiv";
  }
  if (lower.includes("substack.com") || lower.startsWith("substack:") || /\/p\/[a-z0-9\-]+/i.test(text)) {
    return "substack";
  }
  if (lower.startsWith("http://") || lower.startsWith("https://")) return "url";
  return "unknown";
}

/** Ensure pack always declares HTML-first view (never PDF). */
export function assertHtmlViewFormat(pack: { view_format?: string }): void {
  if (pack.view_format && pack.view_format !== "html") {
    throw new Error(`research context view_format must be html, got ${pack.view_format}`);
  }
}
