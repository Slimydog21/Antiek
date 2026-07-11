/**
 * Intelligent search over recursive twin substrate (pure client).
 *
 * Operator vision: search insights and questions across the twin note
 * substrate of the infinite information platform. This pure layer scores
 * caller-supplied twin records only — never invents hits or calls embeddings.
 */

export interface TwinSearchRecord {
  twin_id: string;
  parent_asset_id: string;
  insights: string[];
  questions: string[];
  source_label?: string;
}

export interface TwinSearchHit {
  twin_id: string;
  parent_asset_id: string;
  /** Which fields matched. */
  matched_fields: Array<"insights" | "questions" | "source_label">;
  /** Simple term-overlap score; never invented from missing text. */
  score: number;
  snippets: string[];
}

export interface TwinSearchResult {
  query: string;
  hits: TwinSearchHit[];
  /** Always false — pure search does not call remote index. */
  remote_index_queried: false;
  notes: string[];
  authority: "twin_intelligent_search_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function tokenize(q: string): string[] {
  return q
    .toLowerCase()
    .split(/[^a-z0-9]+/i)
    .map((t) => t.trim())
    .filter((t) => t.length >= 2);
}

function countOverlaps(haystack: string, tokens: string[]): number {
  const h = haystack.toLowerCase();
  let n = 0;
  for (const t of tokens) {
    if (h.includes(t)) n += 1;
  }
  return n;
}

/**
 * Search twin substrate records for query terms.
 * Never invents hits; empty query fails closed; empty corpus → 0 hits.
 */
export function searchTwinSubstrate(input: {
  query: string;
  records: TwinSearchRecord[];
  limit?: number;
}): TwinSearchResult {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const query = requireNonEmpty(input.query, "query");
  if (!Array.isArray(input.records)) {
    throw new Error("records must be an array");
  }
  let limit = 20;
  if (input.limit !== undefined && input.limit !== null) {
    if (
      typeof input.limit !== "number" ||
      !Number.isFinite(input.limit) ||
      input.limit < 1
    ) {
      throw new Error("limit must be a positive finite number when set");
    }
    limit = Math.floor(input.limit);
  }

  const notes: string[] = [
    "remote_index_queried=false — pure substrate scan only",
    "hits are term-overlap only (no invent embeddings)",
  ];

  const tokens = tokenize(query);
  if (tokens.length === 0) {
    throw new Error("query must contain at least one token of length >= 2");
  }

  const hits: TwinSearchHit[] = [];

  for (let i = 0; i < input.records.length; i++) {
    const r = input.records[i];
    if (!r || typeof r !== "object") {
      throw new Error(`records[${i}] must be an object`);
    }
    const twin_id = requireNonEmpty(r.twin_id, `records[${i}].twin_id`);
    const parent = requireNonEmpty(
      r.parent_asset_id,
      `records[${i}].parent_asset_id`,
    );
    if (!Array.isArray(r.insights) || !Array.isArray(r.questions)) {
      throw new Error(
        `records[${i}].insights and questions must be string arrays`,
      );
    }
    for (let j = 0; j < r.insights.length; j++) {
      if (typeof r.insights[j] !== "string") {
        throw new Error(`records[${i}].insights[${j}] must be a string`);
      }
    }
    for (let j = 0; j < r.questions.length; j++) {
      if (typeof r.questions[j] !== "string") {
        throw new Error(`records[${i}].questions[${j}] must be a string`);
      }
    }

    const matched_fields: TwinSearchHit["matched_fields"] = [];
    const snippets: string[] = [];
    let score = 0;

    for (const insight of r.insights) {
      const n = countOverlaps(insight, tokens);
      if (n > 0) {
        if (!matched_fields.includes("insights")) matched_fields.push("insights");
        score += n;
        if (snippets.length < 3) snippets.push(insight.trim().slice(0, 200));
      }
    }
    for (const q of r.questions) {
      const n = countOverlaps(q, tokens);
      if (n > 0) {
        if (!matched_fields.includes("questions")) matched_fields.push("questions");
        score += n;
        if (snippets.length < 3) snippets.push(q.trim().slice(0, 200));
      }
    }
    if (typeof r.source_label === "string" && r.source_label.trim()) {
      const n = countOverlaps(r.source_label, tokens);
      if (n > 0) {
        matched_fields.push("source_label");
        score += n * 0.5;
      }
    }

    if (score > 0 && matched_fields.length > 0) {
      hits.push({
        twin_id,
        parent_asset_id: parent,
        matched_fields,
        score,
        snippets,
      });
    }
  }

  hits.sort((a, b) => b.score - a.score);
  const limited = hits.slice(0, limit);
  notes.push(`hits=${limited.length} of ${hits.length} before limit=${limit}`);
  notes.push("remote_index_queried=false");

  return {
    query,
    hits: limited,
    remote_index_queried: false,
    notes,
    authority: "twin_intelligent_search_advisory",
  };
}

export function formatTwinSearchSummary(r: TwinSearchResult): string {
  return (
    `q=${r.query} · hits=${r.hits.length} · remote_index_queried=false`
  );
}
