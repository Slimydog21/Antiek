/**
 * Workstation session insight/question/data record compose (pure).
 *
 * Operator vision: while interrogating/assessing/wrestling in the research
 * workstation, record valuable data, insights, and questions recursively so
 * they inform all future prompts.
 *
 * record_persisted always false.
 * prompts_injected always false.
 * store_mutated always false.
 */

export type RecordKind = "insight" | "question" | "data" | "claim";

export interface SessionRecordItem {
  record_id: string;
  kind: RecordKind;
  /** Caller-supplied body — never invented. */
  body: string;
  /** Optional source asset / floating instance id. */
  source_ref?: string;
}

export interface WorkstationSessionInsightRecordInput {
  session_id: string;
  parent_asset_id: string;
  records: SessionRecordItem[];
  operator_ack: boolean;
  /**
   * When true, marks records as candidates for prompt-context bridge.
   * Still does not inject into live prompts (prompts_injected stays false).
   */
  mark_for_prompt_context?: boolean;
}

export interface WorkstationSessionInsightRecordCompose {
  session_id: string;
  parent_asset_id: string;
  record_ids: string[];
  record_count: number;
  insight_count: number;
  question_count: number;
  data_count: number;
  claim_count: number;
  mark_for_prompt_context: boolean;
  /** True when ≥1 record and operator_ack. */
  record_ready: boolean;
  /** Always false — pure layer never persists records. */
  record_persisted: false;
  /** Always false — pure layer never injects into live prompts. */
  prompts_injected: false;
  /** Always false — no store mutation. */
  store_mutated: false;
  notes: string[];
  authority: "workstation_session_insight_record_compose_advisory";
}

const VALID_KINDS = new Set<RecordKind>([
  "insight",
  "question",
  "data",
  "claim",
]);

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose a pure pack of session insights/questions/data for recursive memory.
 * Never persists; never injects into prompts live.
 */
export function composeWorkstationSessionInsightRecord(
  input: WorkstationSessionInsightRecordInput,
): WorkstationSessionInsightRecordCompose {
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
  if (!Array.isArray(input.records) || input.records.length === 0) {
    throw new Error("records must be a non-empty array");
  }

  const mark_for_prompt_context =
    input.mark_for_prompt_context === undefined
      ? false
      : input.mark_for_prompt_context;
  if (typeof mark_for_prompt_context !== "boolean") {
    throw new Error("mark_for_prompt_context must be boolean when set");
  }

  const notes: string[] = [
    "record_persisted=false — session records not written to store",
    "prompts_injected=false — prompt-context mark is advisory only",
    "store_mutated=false",
    "record bodies are caller-supplied only (no invent)",
  ];

  const record_ids: string[] = [];
  const seen = new Set<string>();
  let insight_count = 0;
  let question_count = 0;
  let data_count = 0;
  let claim_count = 0;

  for (let i = 0; i < input.records.length; i++) {
    const r = input.records[i];
    if (!r || typeof r !== "object") {
      throw new Error(`records[${i}] must be an object`);
    }
    const id = requireNonEmpty(r.record_id, `records[${i}].record_id`);
    if (seen.has(id)) {
      throw new Error(`duplicate record_id: ${id}`);
    }
    seen.add(id);
    if (!VALID_KINDS.has(r.kind)) {
      throw new Error(
        `records[${i}].kind must be insight|question|data|claim`,
      );
    }
    requireNonEmpty(r.body, `records[${i}].body`);
    if (r.source_ref != null) {
      requireNonEmpty(r.source_ref, `records[${i}].source_ref`);
    }
    record_ids.push(id);
    if (r.kind === "insight") insight_count += 1;
    else if (r.kind === "question") question_count += 1;
    else if (r.kind === "data") data_count += 1;
    else claim_count += 1;
  }

  const record_count = record_ids.length;
  notes.push(
    `records=${record_count} · insights=${insight_count} · questions=${question_count} · data=${data_count} · claims=${claim_count}`,
  );
  if (mark_for_prompt_context) {
    notes.push(
      "mark_for_prompt_context=true — candidates for record→prompt bridge (still prompts_injected=false)",
    );
  }

  const record_ready = input.operator_ack && record_count >= 1;
  if (!input.operator_ack) {
    notes.push("record_ready=false — operator_ack required");
  } else {
    notes.push(
      "record_ready=true — provisional session memory pack (still record_persisted=false)",
    );
  }

  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");
  notes.push("store_mutated=false");

  return {
    session_id,
    parent_asset_id,
    record_ids,
    record_count,
    insight_count,
    question_count,
    data_count,
    claim_count,
    mark_for_prompt_context,
    record_ready,
    record_persisted: false,
    prompts_injected: false,
    store_mutated: false,
    notes,
    authority: "workstation_session_insight_record_compose_advisory",
  };
}

export function formatWorkstationSessionInsightRecordSummary(
  c: WorkstationSessionInsightRecordCompose,
): string {
  return (
    `record_ready=${c.record_ready} · n=${c.record_count} · ` +
    `i=${c.insight_count} q=${c.question_count} · ` +
    `record_persisted=false · prompts_injected=false`
  );
}
