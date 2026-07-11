/**
 * Recursive twin session pack compose (pure).
 *
 * Operator vision: every information asset has a twin of insights + questions
 * (LLM as perfect note-taker). This pure layer packs caller-supplied twin
 * substrate signals for a session so they can be merged, referenced, and
 * searched — without writing the twin store.
 *
 * twin_store_mutated is always false.
 */

export interface TwinSessionMember {
  asset_id: string;
  twin_bound: boolean;
  insights: string[];
  questions: string[];
  /** Optional search hits already known (caller-supplied). */
  search_hits?: number | null;
}

export interface RecursiveTwinSessionPack {
  session_id: string;
  asset_ids: string[];
  insight_count: number;
  question_count: number;
  bound_count: number;
  unbound_count: number;
  /** True when ≥1 bound twin and ≥1 insight or question (scaffold ok). */
  pack_ready: boolean;
  /** Always false — pure pack never mutates twin store. */
  twin_store_mutated: false;
  notes: string[];
  authority: "recursive_twin_session_pack_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function requireStringList(value: unknown, name: string): string[] {
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array`);
  }
  const out: string[] = [];
  for (let i = 0; i < value.length; i++) {
    const s = value[i];
    if (typeof s !== "string" || !s.trim()) {
      throw new Error(`${name}[${i}] must be a non-empty string`);
    }
    out.push(s.trim());
  }
  return out;
}

/**
 * Compose a session pack of twin insights/questions for merge/search.
 * Never invents twin content; never mutates store.
 */
export function composeRecursiveTwinSessionPack(input: {
  session_id: string;
  members: TwinSessionMember[];
}): RecursiveTwinSessionPack {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  if (!Array.isArray(input.members) || input.members.length === 0) {
    throw new Error("members must be a non-empty array");
  }

  const notes: string[] = [
    "twin_store_mutated=false — session pack intent only",
    "insights/questions are caller-supplied only (no invent content)",
  ];

  const asset_ids: string[] = [];
  const seen = new Set<string>();
  let insight_count = 0;
  let question_count = 0;
  let bound_count = 0;
  let unbound_count = 0;

  for (let i = 0; i < input.members.length; i++) {
    const m = input.members[i];
    if (!m || typeof m !== "object") {
      throw new Error(`members[${i}] must be an object`);
    }
    const asset_id = requireNonEmpty(m.asset_id, `members[${i}].asset_id`);
    if (seen.has(asset_id)) {
      throw new Error(`duplicate asset_id in members: ${asset_id}`);
    }
    seen.add(asset_id);
    asset_ids.push(asset_id);

    if (typeof m.twin_bound !== "boolean") {
      throw new Error(`members[${i}].twin_bound must be an explicit boolean`);
    }
    if (m.twin_bound) bound_count += 1;
    else unbound_count += 1;

    const insights = requireStringList(m.insights, `members[${i}].insights`);
    const questions = requireStringList(m.questions, `members[${i}].questions`);
    insight_count += insights.length;
    question_count += questions.length;

    if (m.search_hits !== undefined && m.search_hits !== null) {
      if (
        typeof m.search_hits !== "number" ||
        !Number.isFinite(m.search_hits) ||
        m.search_hits < 0 ||
        !Number.isInteger(m.search_hits)
      ) {
        throw new Error(
          `members[${i}].search_hits must be non-negative integer or null`,
        );
      }
    }
  }

  if (insight_count === 0 && question_count === 0) {
    notes.push(
      "no insights/questions supplied — pack scaffold only (no invent content)",
    );
  } else {
    notes.push(
      `insights=${insight_count} questions=${question_count} caller-supplied only`,
    );
  }

  const pack_ready =
    bound_count >= 1 && (insight_count > 0 || question_count > 0);
  if (!pack_ready) {
    if (bound_count < 1) {
      notes.push("pack_ready=false — need ≥1 twin_bound member");
    } else {
      notes.push(
        "pack_ready=false — bound twins present but no insights/questions",
      );
    }
  } else {
    notes.push("pack_ready=true — substrate pack ready for merge/search intent");
  }
  notes.push("twin_store_mutated=false");

  return {
    session_id,
    asset_ids,
    insight_count,
    question_count,
    bound_count,
    unbound_count,
    pack_ready,
    twin_store_mutated: false,
    notes,
    authority: "recursive_twin_session_pack_compose_advisory",
  };
}

export function formatRecursiveTwinSessionPackSummary(
  p: RecursiveTwinSessionPack,
): string {
  return (
    `twin pack ${p.session_id} · assets=${p.asset_ids.length} · ` +
    `insights=${p.insight_count} questions=${p.question_count} · ` +
    `ready=${p.pack_ready} · twin_store_mutated=false`
  );
}
