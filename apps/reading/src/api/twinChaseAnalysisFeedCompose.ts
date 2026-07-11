/**
 * Twin chase/analysis feed compose (pure).
 *
 * Operator vision: after subagent chases complete and analysis intent forms,
 * feed caller-supplied findings/questions into the recursive twin note-taker
 * substrate so insights recursively inform future work.
 *
 * twin_written always false.
 * record_persisted always false.
 * prompts_injected always false.
 * live_dispatch_authorized always false.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
} from "./recursiveTwinNoteTakerCompose";

export interface ChaseFeedFinding {
  /** Source chase slot or instance id. */
  source_id: string;
  body: string;
  kind?: "insight" | "question" | "claim" | "data";
}

export interface TwinChaseAnalysisFeedInput {
  parent_asset_id: string;
  session_id: string;
  /** Caller-supplied findings from completed chases / analysis — never invented. */
  findings: ChaseFeedFinding[];
  /** Optional analysis summary excerpt (caller-supplied). */
  analysis_excerpt?: string | null;
  existing_twin_asset_id?: string | null;
  operator_ack: boolean;
  /**
   * When true, marks feed candidates for prompt-context bridge later.
   * Still prompts_injected=false.
   */
  mark_for_prompt_context?: boolean;
}

export interface TwinChaseAnalysisFeedCompose {
  session_id: string;
  parent_asset_id: string;
  finding_count: number;
  insight_count: number;
  question_count: number;
  twin: RecursiveTwinNoteTakerCompose;
  mark_for_prompt_context: boolean;
  /**
   * True when twin_propose_ready and ≥1 finding.
   */
  feed_ready: boolean;
  twin_written: false;
  record_persisted: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  notes: string[];
  authority: "twin_chase_analysis_feed_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Feed chase/analysis findings into twin note-taker scaffold (pure intent).
 */
export function composeTwinChaseAnalysisFeed(
  input: TwinChaseAnalysisFeedInput,
): TwinChaseAnalysisFeedCompose {
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
  if (!Array.isArray(input.findings) || input.findings.length === 0) {
    throw new Error("findings must be a non-empty array");
  }

  const mark_for_prompt_context =
    input.mark_for_prompt_context === undefined
      ? false
      : input.mark_for_prompt_context;
  if (typeof mark_for_prompt_context !== "boolean") {
    throw new Error("mark_for_prompt_context must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false — twin document not mutated",
    "record_persisted=false — session records not written",
    "prompts_injected=false — no live prompt mutation",
    "live_dispatch_authorized=false — no twin agent dispatch",
  ];

  const focus_questions: string[] = [];
  const insight_bodies: string[] = [];
  let insight_count = 0;
  let question_count = 0;
  const seenSource = new Set<string>();

  for (let i = 0; i < input.findings.length; i++) {
    const f = input.findings[i];
    if (!f || typeof f !== "object") {
      throw new Error(`findings[${i}] must be an object`);
    }
    const source_id = requireNonEmpty(
      f.source_id,
      `findings[${i}].source_id`,
    );
    if (seenSource.has(source_id)) {
      throw new Error(`duplicate findings source_id: ${source_id}`);
    }
    seenSource.add(source_id);
    const body = requireNonEmpty(f.body, `findings[${i}].body`);
    const kind = f.kind ?? "insight";
    if (
      kind !== "insight" &&
      kind !== "question" &&
      kind !== "claim" &&
      kind !== "data"
    ) {
      throw new Error(
        `findings[${i}].kind must be insight|question|claim|data`,
      );
    }
    if (kind === "question") {
      focus_questions.push(body);
      question_count += 1;
    } else {
      insight_bodies.push(`[${kind}/${source_id}] ${body}`);
      insight_count += 1;
    }
  }

  const analysis_excerpt =
    input.analysis_excerpt == null || input.analysis_excerpt === undefined
      ? null
      : requireNonEmpty(input.analysis_excerpt, "analysis_excerpt");

  const excerptParts = [
    analysis_excerpt ? `analysis: ${analysis_excerpt}` : null,
    ...insight_bodies,
  ].filter((x): x is string => x != null);
  if (excerptParts.length === 0 && focus_questions.length === 0) {
    throw new Error("no feedable content after normalization");
  }
  const source_excerpt =
    excerptParts.length > 0
      ? excerptParts.join("\n")
      : focus_questions.join("\n");

  notes.push(
    `finding_count=${input.findings.length} · insights=${insight_count} · questions=${question_count}`,
  );
  if (mark_for_prompt_context) {
    notes.push(
      "mark_for_prompt_context=true — candidates only; prompts_injected=false",
    );
  }

  const twin = composeRecursiveTwinNoteTaker({
    parent_asset_id,
    source_excerpt,
    existing_twin_asset_id: input.existing_twin_asset_id,
    operator_ack: input.operator_ack,
    focus_questions: focus_questions.length > 0 ? focus_questions : null,
  });
  notes.push(...twin.notes);

  const feed_ready =
    twin.twin_propose_ready && input.findings.length > 0 && input.operator_ack;
  if (!feed_ready) {
    notes.push(
      !input.operator_ack
        ? "feed_ready=false — operator_ack required"
        : "feed_ready=false",
    );
  } else {
    notes.push(
      "feed_ready=true — twin scaffold ready from chase feed; twin_written=false",
    );
  }

  if (
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false
  ) {
    throw new Error("invariant: twin honesty flags must remain false");
  }

  notes.push("twin_written=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");

  return {
    session_id,
    parent_asset_id,
    finding_count: input.findings.length,
    insight_count,
    question_count,
    twin,
    mark_for_prompt_context,
    feed_ready,
    twin_written: false,
    record_persisted: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    notes,
    authority: "twin_chase_analysis_feed_compose_advisory",
  };
}

export function formatTwinChaseAnalysisFeedSummary(
  c: TwinChaseAnalysisFeedCompose,
): string {
  return (
    `feed_ready=${c.feed_ready} · findings=${c.finding_count} · ` +
    `insights=${c.insight_count} · questions=${c.question_count} · ` +
    `twin_written=false · record_persisted=false · prompts_injected=false · ` +
    `live_dispatch_authorized=false`
  );
}
