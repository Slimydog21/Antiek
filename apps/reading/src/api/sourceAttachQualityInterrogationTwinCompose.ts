/**
 * Source attach quality + interrogation → twin chase feed (pure).
 *
 * Operator vision: arxiv/substack HTML sources attach under quality/budget
 * gates, chase questions in the research workstation, then feed source titles
 * + chase questions into the recursive twin note-taker substrate so insights
 * and questions recursively inform future prompts/search.
 *
 * remote_fetched / pdf_view_authorized / live_* / twin_written /
 * record_persisted / prompts_injected / store_mutated always false.
 */

import {
  composeSourceAttachQualityInterrogation,
  type SourceAttachQualityInterrogationCompose,
  type SourceAttachQualityInterrogationInput,
} from "./sourceAttachQualityInterrogationCompose";
import {
  composeTwinChaseAnalysisFeed,
  type ChaseFeedFinding,
  type TwinChaseAnalysisFeedCompose,
} from "./twinChaseAnalysisFeedCompose";

export interface SourceAttachQualityInterrogationTwinInput
  extends SourceAttachQualityInterrogationInput {
  /** Optional twin asset if already bound. */
  existing_twin_asset_id?: string | null;
  /** Optional analysis excerpt for twin feed (caller-supplied). */
  analysis_excerpt?: string | null;
  /**
   * When true (default), require source pack_ready AND twin feed_ready.
   * When false, pack_ready if either path ready (after operator_ack).
   */
  require_both?: boolean;
  /** Mark twin feed candidates for later prompt-context bridge. */
  mark_for_prompt_context?: boolean;
  /**
   * Optional extra findings for twin feed (caller-supplied; never invented).
   * When omitted, findings are derived from sources (data) + questions.
   */
  twin_findings?: ChaseFeedFinding[] | null;
}

export interface SourceAttachQualityInterrogationTwinCompose {
  session_id: string;
  parent_asset_id: string;
  source_interrogation: SourceAttachQualityInterrogationCompose;
  twin_feed: TwinChaseAnalysisFeedCompose;
  /**
   * True when source_interrogation.pack_ready and twin_feed.feed_ready
   * (or either when require_both=false) and operator_ack.
   */
  pack_ready: boolean;
  remote_fetched: false;
  pdf_view_authorized: false;
  live_dispatch_authorized: false;
  live_dispatched: false;
  twin_written: false;
  record_persisted: false;
  prompts_injected: false;
  store_mutated: false;
  notes: string[];
  authority: "source_attach_quality_interrogation_twin_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Derive twin feed findings from attached sources + chase questions.
 * Never invents insight text beyond caller-supplied titles/bodies.
 */
function deriveFindingsFromSourcesAndQuestions(
  sources: SourceAttachQualityInterrogationInput["sources"],
  questions: SourceAttachQualityInterrogationInput["questions"],
): ChaseFeedFinding[] {
  const findings: ChaseFeedFinding[] = [];
  for (const s of sources) {
    findings.push({
      source_id: `src-${s.source_id}`,
      body: s.title,
      kind: "data",
    });
  }
  for (const q of questions) {
    findings.push({
      source_id: `q-${q.question_id}`,
      body: q.body,
      kind: "question",
    });
  }
  return findings;
}

/**
 * Compose source attach/quality/interrogation + twin chase feed pack.
 * Never scrapes; never writes twin; never dispatches.
 */
export function composeSourceAttachQualityInterrogationTwin(
  input: SourceAttachQualityInterrogationTwinInput,
): SourceAttachQualityInterrogationTwinCompose {
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

  const require_both =
    input.require_both === undefined ? true : input.require_both;
  if (typeof require_both !== "boolean") {
    throw new Error("require_both must be boolean when set");
  }

  const mark_for_prompt_context =
    input.mark_for_prompt_context === undefined
      ? true
      : input.mark_for_prompt_context;
  if (typeof mark_for_prompt_context !== "boolean") {
    throw new Error("mark_for_prompt_context must be boolean when set");
  }

  const notes: string[] = [
    "remote_fetched=false — no live arxiv/substack scrape",
    "pdf_view_authorized=false — HTML-native sources only",
    "twin_written=false · record_persisted=false · prompts_injected=false",
    "live_dispatch_authorized=false · live_dispatched=false · store_mutated=false",
  ];

  const source_interrogation = composeSourceAttachQualityInterrogation({
    session_id: input.session_id,
    parent_asset_id: input.parent_asset_id,
    requested_families: input.requested_families,
    sources: input.sources,
    citations: input.citations,
    derive_citations_from_sources: input.derive_citations_from_sources,
    quality_overall: input.quality_overall,
    quality_floor: input.quality_floor,
    would_exceed: input.would_exceed,
    operator_override: input.operator_override,
    questions: input.questions,
    chase_mode: input.chase_mode,
    prior_records: input.prior_records,
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
    require_both: input.require_both,
  });
  notes.push(
    ...source_interrogation.notes.map((n) => `[source_interrogation] ${n}`),
  );

  let twin_findings: ChaseFeedFinding[];
  if (input.twin_findings != null) {
    if (!Array.isArray(input.twin_findings)) {
      throw new Error("twin_findings must be an array when set");
    }
    twin_findings = input.twin_findings;
    notes.push(`twin_findings=${twin_findings.length} caller-supplied`);
  } else {
    twin_findings = deriveFindingsFromSourcesAndQuestions(
      input.sources,
      input.questions,
    );
    notes.push(
      `twin_findings=${twin_findings.length} derived from sources+questions`,
    );
  }

  const twin_feed = composeTwinChaseAnalysisFeed({
    session_id,
    parent_asset_id,
    findings: twin_findings,
    analysis_excerpt: input.analysis_excerpt,
    existing_twin_asset_id: input.existing_twin_asset_id,
    operator_ack: input.operator_ack,
    mark_for_prompt_context,
  });
  notes.push(...twin_feed.notes.map((n) => `[twin_feed] ${n}`));

  let pack_ready = false;
  if (require_both) {
    pack_ready =
      source_interrogation.pack_ready === true &&
      twin_feed.feed_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (source_interrogation.pack_ready === true ||
        twin_feed.feed_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — source attach/interrogation + twin feed ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — source interrogation, twin feed, or operator_ack gate open",
    );
  }

  if (
    source_interrogation.remote_fetched !== false ||
    source_interrogation.pdf_view_authorized !== false ||
    source_interrogation.live_dispatched !== false ||
    source_interrogation.record_persisted !== false ||
    source_interrogation.prompts_injected !== false ||
    twin_feed.twin_written !== false ||
    twin_feed.record_persisted !== false ||
    twin_feed.prompts_injected !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("remote_fetched=false");
  notes.push("pdf_view_authorized=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("live_dispatched=false");
  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    source_interrogation,
    twin_feed,
    pack_ready,
    remote_fetched: false,
    pdf_view_authorized: false,
    live_dispatch_authorized: false,
    live_dispatched: false,
    twin_written: false,
    record_persisted: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority: "source_attach_quality_interrogation_twin_compose_advisory",
  };
}

export function formatSourceAttachQualityInterrogationTwinSummary(
  c: SourceAttachQualityInterrogationTwinCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `source_ready=${c.source_interrogation.pack_ready} · ` +
    `twin_feed_ready=${c.twin_feed.feed_ready} · ` +
    `findings=${c.twin_feed.finding_count} · ` +
    `remote_fetched=false · twin_written=false · live_dispatched=false`
  );
}
