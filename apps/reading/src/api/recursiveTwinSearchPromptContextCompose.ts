/**
 * Recursive twin note-taker → intelligent search → prompt context pack (pure).
 *
 * Operator vision: every information asset has a twin substrate of
 * insights/questions; search that substrate and leverage hits into prompt
 * context for the next research/write step — without inventing notes or
 * live-injecting prompts.
 *
 * twin_written always false.
 * remote_index_queried always false.
 * record_persisted always false.
 * prompts_injected always false.
 * live_router_authorized always false.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
} from "./recursiveTwinNoteTakerCompose";
import {
  searchTwinSubstrate,
  type TwinSearchRecord,
  type TwinSearchResult,
} from "./recursiveTwinIntelligentSearch";
import {
  composeWorkstationRecordPromptModelDecision,
  type WorkstationRecordPromptModelDecisionCompose,
} from "./workstationRecordPromptModelDecisionCompose";
import type { SessionRecordItem } from "./workstationSessionInsightRecordCompose";
import type { ModelOption } from "./modelDecisionPromptCompose";
import type { BenchTaskBest } from "./settingsModelDriverTabCompose";
import type { NotDiamondShadowRec } from "./settingsModelDriverTabCompose";

export interface RecursiveTwinSearchPromptContextInput {
  session_id: string;
  parent_asset_id: string;
  /** Source excerpt for twin note-taker scaffold (caller-supplied). */
  source_excerpt: string;
  existing_twin_asset_id?: string | null;
  focus_questions?: string[] | null;
  /** Twin substrate corpus to search (caller-supplied; never invented). */
  twin_records: TwinSearchRecord[];
  search_query: string;
  search_limit?: number;
  user_prompt: string;
  selected_model_id: string;
  models: ModelOption[];
  daily_cap_usd: number | null;
  spent_usd: number | null;
  projected_cost_usd_high?: number | null;
  projected_cost_usd_low?: number | null;
  bench_bests?: BenchTaskBest[] | null;
  focus_task?: string | null;
  nd_shadow?: NotDiamondShadowRec | null;
  operator_ack: boolean;
}

export interface RecursiveTwinSearchPromptContextCompose {
  session_id: string;
  parent_asset_id: string;
  twin_propose: RecursiveTwinNoteTakerCompose;
  search: TwinSearchResult;
  prompt_pack: WorkstationRecordPromptModelDecisionCompose;
  /**
   * True when twin_propose_ready (or existing twin), search composed,
   * and prompt_pack.pack_ready. Still never writes/injects/routes.
   */
  pack_ready: boolean;
  twin_written: false;
  remote_index_queried: false;
  record_persisted: false;
  prompts_injected: false;
  live_router_authorized: false;
  notes: string[];
  authority: "recursive_twin_search_prompt_context_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Map twin search hits → session records for prompt context bridge.
 * Snippets are caller-derived from corpus only.
 */
function hitsToSessionRecords(
  search: TwinSearchResult,
): SessionRecordItem[] {
  const records: SessionRecordItem[] = [];
  for (const hit of search.hits) {
    for (let i = 0; i < hit.snippets.length; i++) {
      const snip = hit.snippets[i];
      const isQuestion =
        hit.matched_fields.includes("questions") &&
        (snip.includes("?") || hit.matched_fields[0] === "questions");
      records.push({
        record_id: `${hit.twin_id}-s${i}`,
        kind: isQuestion ? "question" : "insight",
        body: snip,
        source_ref: hit.parent_asset_id,
      });
    }
  }
  return records;
}

/**
 * Twin propose + substrate search + prompt/model decision pack.
 * Never writes twins; never remote-indexes; never injects prompts.
 */
export function composeRecursiveTwinSearchPromptContext(
  input: RecursiveTwinSearchPromptContextInput,
): RecursiveTwinSearchPromptContextCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );

  const notes: string[] = [
    "twin_written=false — twin note-taker is propose/scaffold only",
    "remote_index_queried=false — twin search is pure local corpus",
    "record_persisted=false · prompts_injected=false · live_router_authorized=false",
  ];

  const twin_propose = composeRecursiveTwinNoteTaker({
    parent_asset_id,
    source_excerpt: input.source_excerpt,
    existing_twin_asset_id: input.existing_twin_asset_id,
    operator_ack: input.operator_ack,
    focus_questions: input.focus_questions,
  });
  notes.push(...twin_propose.notes.map((n) => `[twin] ${n}`));

  if (!Array.isArray(input.twin_records)) {
    throw new Error("twin_records must be an array");
  }
  const search = searchTwinSubstrate({
    query: input.search_query,
    records: input.twin_records,
    limit: input.search_limit,
  });
  notes.push(...search.notes.map((n) => `[search] ${n}`));
  notes.push(`search_hits=${search.hits.length}`);

  const sessionRecords = hitsToSessionRecords(search);
  // If no hits, still allow empty records path? workstation may require records —
  // seed one insight from focus_questions or source excerpt marker when ack.
  if (sessionRecords.length === 0 && input.operator_ack) {
    notes.push(
      "no twin search hits — seed scaffold insight from source_excerpt (caller text only)",
    );
    sessionRecords.push({
      record_id: "scaffold-excerpt",
      kind: "insight",
      body: input.source_excerpt.trim().slice(0, 500),
      source_ref: parent_asset_id,
    });
  }

  const prompt_pack = composeWorkstationRecordPromptModelDecision({
    session_id,
    parent_asset_id,
    records: sessionRecords,
    user_prompt: input.user_prompt,
    selected_model_id: input.selected_model_id,
    models: input.models,
    daily_cap_usd: input.daily_cap_usd,
    spent_usd: input.spent_usd,
    projected_cost_usd_high: input.projected_cost_usd_high,
    projected_cost_usd_low: input.projected_cost_usd_low,
    bench_bests: input.bench_bests,
    focus_task: input.focus_task,
    nd_shadow: input.nd_shadow,
    operator_ack: input.operator_ack,
  });
  notes.push(...prompt_pack.notes.map((n) => `[prompt] ${n}`));

  const pack_ready =
    twin_propose.twin_propose_ready === true &&
    prompt_pack.pack_ready === true &&
    input.operator_ack === true;

  if (pack_ready) {
    notes.push(
      "pack_ready=true — twin propose + search + prompt context advisory pack",
    );
  } else {
    notes.push(
      "pack_ready=false — twin, search, prompt pack, or operator_ack gate open",
    );
  }

  if (
    twin_propose.twin_written !== false ||
    twin_propose.prompts_injected !== false ||
    search.remote_index_queried !== false ||
    prompt_pack.record_persisted !== false ||
    prompt_pack.prompts_injected !== false ||
    prompt_pack.live_router_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("twin_written=false");
  notes.push("remote_index_queried=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_router_authorized=false");

  return {
    session_id,
    parent_asset_id,
    twin_propose,
    search,
    prompt_pack,
    pack_ready,
    twin_written: false,
    remote_index_queried: false,
    record_persisted: false,
    prompts_injected: false,
    live_router_authorized: false,
    notes,
    authority: "recursive_twin_search_prompt_context_compose_advisory",
  };
}

export function formatRecursiveTwinSearchPromptContextSummary(
  c: RecursiveTwinSearchPromptContextCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · hits=${c.search.hits.length} · ` +
    `twin_propose_ready=${c.twin_propose.twin_propose_ready} · ` +
    `would_exceed=${c.prompt_pack.would_exceed} · ` +
    `twin_written=false · remote_index_queried=false · prompts_injected=false`
  );
}
