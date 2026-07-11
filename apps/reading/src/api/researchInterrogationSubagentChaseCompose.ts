/**
 * Research interrogation → subagent chase compose (pure).
 *
 * Operator vision: live in the research workstation; send subagents to chase
 * questions while interrogating/assessing/wrestling with information in front
 * of you. Pure plan of chase intents — never live-dispatches.
 *
 * live_dispatched always false.
 * pack_dispatched always false.
 * record_persisted always false.
 * prompts_injected always false.
 */

export type ChaseMode =
  | "single_question"
  | "swarm_fanout"
  | "collective_merge_after";

export type SourceFamilyHint =
  | "arxiv"
  | "substack"
  | "openalex"
  | "web"
  | "custom";

export interface ChaseQuestion {
  question_id: string;
  body: string;
  /** Optional higher = earlier in plan. */
  priority?: number;
}

export interface PlannedChaseSlot {
  slot_id: string;
  question_id: string;
  body: string;
  priority: number;
  selected_model_id: string | null;
  source_families: SourceFamilyHint[];
  /** Always false — slot is intent only. */
  live_dispatched: false;
}

export interface ResearchInterrogationSubagentChaseInput {
  session_id: string;
  parent_asset_id: string;
  questions: ChaseQuestion[];
  chase_mode: ChaseMode;
  would_exceed: boolean | null;
  operator_override?: boolean;
  selected_model_id?: string | null;
  source_families?: SourceFamilyHint[] | null;
  operator_ack: boolean;
  /**
   * When true, marks chase outputs as candidates for twin/session records.
   * Still does not persist (record_persisted stays false).
   */
  mark_for_twin_record?: boolean;
}

export interface ResearchInterrogationSubagentChaseCompose {
  session_id: string;
  parent_asset_id: string;
  chase_mode: ChaseMode;
  planned_slots: PlannedChaseSlot[];
  slot_count: number;
  budget_ready: boolean;
  would_exceed: boolean | null;
  mark_for_twin_record: boolean;
  /**
   * True when ≥1 planned slot, operator_ack, and budget_ready.
   * Never authorizes live dispatch.
   */
  chase_ready: boolean;
  live_dispatched: false;
  pack_dispatched: false;
  record_persisted: false;
  prompts_injected: false;
  notes: string[];
  authority: "research_interrogation_subagent_chase_compose_advisory";
}

const VALID_MODES = new Set<ChaseMode>([
  "single_question",
  "swarm_fanout",
  "collective_merge_after",
]);

const VALID_FAMILIES = new Set<SourceFamilyHint>([
  "arxiv",
  "substack",
  "openalex",
  "web",
  "custom",
]);

const SECRETISH = /sk-|api[_-]?key|secret/i;

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Compose a pure subagent chase plan from interrogation questions.
 * Never dispatches; never persists twin/session records; never injects prompts.
 */
export function composeResearchInterrogationSubagentChase(
  input: ResearchInterrogationSubagentChaseInput,
): ResearchInterrogationSubagentChaseCompose {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  if (input.would_exceed !== null && typeof input.would_exceed !== "boolean") {
    throw new Error("would_exceed must be boolean or null");
  }
  const override =
    input.operator_override === undefined ? false : input.operator_override;
  if (typeof override !== "boolean") {
    throw new Error("operator_override must be boolean when set");
  }

  const session_id = requireNonEmpty(input.session_id, "session_id");
  const parent_asset_id = requireNonEmpty(
    input.parent_asset_id,
    "parent_asset_id",
  );
  if (!VALID_MODES.has(input.chase_mode)) {
    throw new Error(
      "chase_mode must be single_question|swarm_fanout|collective_merge_after",
    );
  }
  const chase_mode = input.chase_mode;

  if (!Array.isArray(input.questions) || input.questions.length === 0) {
    throw new Error("questions must be a non-empty array");
  }

  const mark_for_twin_record =
    input.mark_for_twin_record === undefined
      ? false
      : input.mark_for_twin_record;
  if (typeof mark_for_twin_record !== "boolean") {
    throw new Error("mark_for_twin_record must be boolean when set");
  }

  const notes: string[] = [
    "live_dispatched=false — chase plan is pure intent only",
    "pack_dispatched=false — collective merge after is intent only",
    "record_persisted=false — twin/session records not written",
    "prompts_injected=false — no live prompt mutation",
  ];

  let model_id: string | null = null;
  if (input.selected_model_id != null) {
    model_id = requireNonEmpty(
      input.selected_model_id,
      "selected_model_id",
    );
    if (model_id.length > 128 || SECRETISH.test(model_id)) {
      throw new Error(
        "selected_model_id must be a model id, not secret material",
      );
    }
    notes.push(`selected_model_id=${model_id} (operator authority)`);
  } else {
    notes.push(
      "selected_model_id=null — operator may choose before live chase",
    );
  }

  const families: SourceFamilyHint[] = [];
  if (input.source_families != null) {
    if (!Array.isArray(input.source_families)) {
      throw new Error("source_families must be an array when set");
    }
    const seen = new Set<string>();
    for (let i = 0; i < input.source_families.length; i++) {
      const f = input.source_families[i];
      if (!VALID_FAMILIES.has(f)) {
        throw new Error(
          `source_families[${i}] must be arxiv|substack|openalex|web|custom`,
        );
      }
      if (seen.has(f)) {
        throw new Error(`duplicate source_family: ${f}`);
      }
      seen.add(f);
      families.push(f);
    }
  }
  notes.push(`source_family_count=${families.length}`);

  // Validate + normalize questions
  const normalized: { question_id: string; body: string; priority: number }[] =
    [];
  const seenQ = new Set<string>();
  for (let i = 0; i < input.questions.length; i++) {
    const q = input.questions[i];
    if (!q || typeof q !== "object") {
      throw new Error(`questions[${i}] must be an object`);
    }
    const question_id = requireNonEmpty(
      q.question_id,
      `questions[${i}].question_id`,
    );
    const body = requireNonEmpty(q.body, `questions[${i}].body`);
    if (seenQ.has(question_id)) {
      throw new Error(`duplicate question_id: ${question_id}`);
    }
    seenQ.add(question_id);
    let priority = 0;
    if (q.priority !== undefined) {
      if (
        typeof q.priority !== "number" ||
        !Number.isFinite(q.priority) ||
        !Number.isInteger(q.priority)
      ) {
        throw new Error(`questions[${i}].priority must be a finite integer`);
      }
      priority = q.priority;
    }
    normalized.push({ question_id, body, priority });
  }

  // Mode gates
  if (chase_mode === "single_question" && normalized.length !== 1) {
    throw new Error("single_question mode requires exactly 1 question");
  }
  if (
    (chase_mode === "swarm_fanout" ||
      chase_mode === "collective_merge_after") &&
    normalized.length < 2
  ) {
    throw new Error(`${chase_mode} requires ≥2 questions`);
  }

  // Sort by priority desc, stable by question_id
  normalized.sort((a, b) => {
    if (b.priority !== a.priority) return b.priority - a.priority;
    return a.question_id.localeCompare(b.question_id);
  });

  const planned_slots: PlannedChaseSlot[] = normalized.map((q, idx) => ({
    slot_id: `chase_${session_id}_${idx + 1}_${q.question_id}`,
    question_id: q.question_id,
    body: q.body,
    priority: q.priority,
    selected_model_id: model_id,
    source_families: [...families],
    live_dispatched: false as const,
  }));

  notes.push(
    `planned_slots=${planned_slots.length} · chase_mode=${chase_mode}`,
  );
  if (chase_mode === "collective_merge_after") {
    notes.push(
      "collective_merge_after — merge intent only; pack_dispatched=false",
    );
  }
  if (mark_for_twin_record) {
    notes.push(
      "mark_for_twin_record=true — candidates only; record_persisted=false",
    );
  }

  // Budget gate (same honesty as launch packages)
  let budget_ready = false;
  if (input.would_exceed === null) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override (would_exceed unknown)",
      );
    } else {
      notes.push(
        "budget_ready=false — would_exceed unknown and no operator_override",
      );
    }
  } else if (input.would_exceed === true) {
    if (override) {
      budget_ready = true;
      notes.push(
        "budget_ready=true via operator_override despite would_exceed=true",
      );
    } else {
      notes.push("budget_ready=false — would_exceed=true");
    }
  } else {
    budget_ready = true;
    notes.push("budget_ready=true — would_exceed=false");
  }

  const chase_ready =
    input.operator_ack && budget_ready && planned_slots.length > 0;
  if (!input.operator_ack) {
    notes.push("chase_ready=false — operator_ack required");
  } else if (!budget_ready) {
    notes.push("chase_ready=false — budget gate closed");
  } else {
    notes.push(
      "chase_ready=true — pure chase plan ready; still live_dispatched=false",
    );
  }

  notes.push("live_dispatched=false");
  notes.push("pack_dispatched=false");
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");

  return {
    session_id,
    parent_asset_id,
    chase_mode,
    planned_slots,
    slot_count: planned_slots.length,
    budget_ready,
    would_exceed: input.would_exceed,
    mark_for_twin_record,
    chase_ready,
    live_dispatched: false,
    pack_dispatched: false,
    record_persisted: false,
    prompts_injected: false,
    notes,
    authority: "research_interrogation_subagent_chase_compose_advisory",
  };
}

export function formatResearchInterrogationSubagentChaseSummary(
  c: ResearchInterrogationSubagentChaseCompose,
): string {
  return (
    `chase_ready=${c.chase_ready} · mode=${c.chase_mode} · ` +
    `slots=${c.slot_count} · budget_ready=${c.budget_ready} · ` +
    `live_dispatched=false · pack_dispatched=false · ` +
    `record_persisted=false · prompts_injected=false`
  );
}
