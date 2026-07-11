/**
 * Collective floating deep research → cohesive unit prompt (pure).
 *
 * Operator vision: multi-select floating/sub-agent deep research instances
 * and prompt them as one cohesive unit (not only post-hoc analysis merge).
 *
 * live_dispatched is always false in this pure layer — pack intent only.
 * Never invents findings or context from instances; caller-supplied only.
 */

export type CohesiveMemberStatus =
  | "proposed"
  | "open"
  | "completed"
  | "closed";

export interface CohesiveFloatingMember {
  instance_id: string;
  parent_asset_id: string;
  status: CohesiveMemberStatus;
  highlight?: string;
  prior_prompt?: string;
  /** Optional operator-supplied context cards — never invented. */
  context?: string[];
}

export interface CohesiveUnitPromptIntent {
  parent_asset_id: string;
  instance_ids: string[];
  cohesive_prompt: string;
  /** Flattened caller-supplied context only. */
  context_cards: string[];
  member_count: number;
  operator_ack: boolean;
  /**
   * True only when operator_ack and ≥2 distinct members share parent.
   * Still does not authorize live dispatch.
   */
  pack_ready: boolean;
  /** Always false — pure intent never dispatches multi-agent pack. */
  live_dispatched: false;
  notes: string[];
  authority: "collective_floating_cohesive_prompt_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Build a cohesive-unit prompt pack from ≥2 floating research instances.
 * Never live-dispatches; never invents context.
 */
export function buildCollectiveFloatingCohesivePrompt(
  members: CohesiveFloatingMember[],
  input: {
    cohesive_prompt: string;
    operator_ack: boolean;
    /** Optional extra context cards from the operator. */
    extra_context?: string[] | null;
  },
): CohesiveUnitPromptIntent {
  if (!Array.isArray(members) || members.length < 2) {
    throw new Error("cohesive unit requires at least 2 members");
  }
  if (typeof input.operator_ack !== "boolean") {
    throw new Error("operator_ack must be an explicit boolean");
  }
  const cohesive_prompt = requireNonEmpty(
    input.cohesive_prompt,
    "cohesive_prompt",
  );

  const parent = requireNonEmpty(
    members[0]?.parent_asset_id,
    "members[0].parent_asset_id",
  );
  const ids: string[] = [];
  const context_cards: string[] = [];
  const notes: string[] = [
    "live_dispatched=false — cohesive pack intent only",
    "context cards are caller-supplied only (no invent)",
  ];

  for (let i = 0; i < members.length; i++) {
    const m = members[i];
    if (!m || typeof m !== "object") {
      throw new Error(`members[${i}] must be an object`);
    }
    const id = requireNonEmpty(m.instance_id, `members[${i}].instance_id`);
    const p = requireNonEmpty(
      m.parent_asset_id,
      `members[${i}].parent_asset_id`,
    );
    if (p !== parent) {
      throw new Error("cohesive unit requires same parent_asset_id");
    }
    if (
      m.status !== "proposed" &&
      m.status !== "open" &&
      m.status !== "completed"
    ) {
      throw new Error(
        `members[${i}] status must be proposed|open|completed (not closed)`,
      );
    }
    ids.push(id);

    if (m.highlight != null) {
      if (typeof m.highlight !== "string" || !m.highlight.trim()) {
        throw new Error(
          `members[${i}].highlight must be non-empty string when set`,
        );
      }
      context_cards.push(`[${id} highlight] ${m.highlight.trim()}`);
    }
    if (m.prior_prompt != null) {
      if (typeof m.prior_prompt !== "string" || !m.prior_prompt.trim()) {
        throw new Error(
          `members[${i}].prior_prompt must be non-empty string when set`,
        );
      }
      context_cards.push(`[${id} prior_prompt] ${m.prior_prompt.trim()}`);
    }
    if (m.context != null) {
      if (!Array.isArray(m.context)) {
        throw new Error(`members[${i}].context must be string[] when set`);
      }
      for (let j = 0; j < m.context.length; j++) {
        const c = m.context[j];
        if (typeof c !== "string" || !c.trim()) {
          throw new Error(
            `members[${i}].context[${j}] must be non-empty string`,
          );
        }
        context_cards.push(`[${id}] ${c.trim()}`);
      }
    }
  }

  const seen = new Set<string>();
  const unique = ids.filter((id) => {
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
  if (unique.length < 2) {
    throw new Error("cohesive unit requires at least 2 distinct instance_ids");
  }

  if (input.extra_context != null) {
    if (!Array.isArray(input.extra_context)) {
      throw new Error("extra_context must be string[] or null");
    }
    for (let j = 0; j < input.extra_context.length; j++) {
      const c = input.extra_context[j];
      if (typeof c !== "string" || !c.trim()) {
        throw new Error(`extra_context[${j}] must be non-empty string`);
      }
      context_cards.push(c.trim());
    }
  }

  if (context_cards.length === 0) {
    notes.push(
      "no context cards supplied — prompt pack scaffold only (no invent content)",
    );
  } else {
    notes.push(`context_cards=${context_cards.length} caller-supplied only`);
  }

  const pack_ready = input.operator_ack === true;
  if (!pack_ready) {
    notes.push("pack_ready=false — operator_ack required before dispatch gate");
  } else {
    notes.push(
      "pack_ready=true — still live_dispatched=false (pure layer never dispatches)",
    );
  }
  notes.push("live_dispatched=false");

  return {
    parent_asset_id: parent,
    instance_ids: unique,
    cohesive_prompt,
    context_cards,
    member_count: unique.length,
    operator_ack: input.operator_ack,
    pack_ready,
    live_dispatched: false,
    notes,
    authority: "collective_floating_cohesive_prompt_advisory",
  };
}

export function formatCohesivePromptSummary(
  intent: CohesiveUnitPromptIntent,
): string {
  return (
    `cohesive pack · members=${intent.member_count} · ` +
    `context=${intent.context_cards.length} · pack_ready=${intent.pack_ready} · ` +
    `live_dispatched=false`
  );
}
