/**
 * Recursive twin note-taker compose (pure).
 *
 * Operator vision: every information asset has a twin document of insights
 * and questions proposed by an LLM (perfect note-taker). That substrate is
 * then mergeable and searchable. This pure layer proposes a twin generation
 * pack from caller-supplied content signals only.
 *
 * twin_written always false.
 * prompts_injected always false.
 * live_dispatch_authorized always false.
 */

export interface RecursiveTwinNoteTakerInput {
  parent_asset_id: string;
  /** Caller-supplied source excerpt/HTML for note-taking (never invented). */
  source_excerpt: string;
  /** Optional existing twin asset id if already bound. */
  existing_twin_asset_id?: string | null;
  /** Operator ack to propose twin generation. */
  operator_ack: boolean;
  /** Optional focus questions from the operator (caller-supplied). */
  focus_questions?: string[] | null;
}

export interface RecursiveTwinNoteTakerCompose {
  parent_asset_id: string;
  existing_twin_asset_id: string | null;
  source_excerpt_chars: number;
  focus_question_count: number;
  /**
   * Provisional twin scaffold sections (structure only — content from caller).
   * Does not invent insights/questions beyond focus_questions.
   */
  twin_scaffold_sections: string[];
  /** True when operator_ack and source_excerpt non-empty. */
  twin_propose_ready: boolean;
  /** Always false — pure layer never writes twin documents. */
  twin_written: false;
  /** Always false — pure layer never injects LLM prompts live. */
  prompts_injected: false;
  /** Always false — pure layer never dispatches note-taker agents. */
  live_dispatch_authorized: false;
  notes: string[];
  authority: "recursive_twin_note_taker_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Propose recursive twin note-taker pack for a parent asset.
 * Never invents insights; never writes twins; never dispatches.
 */
export function composeRecursiveTwinNoteTaker(
  input: RecursiveTwinNoteTakerInput,
): RecursiveTwinNoteTakerCompose {
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
  const source_excerpt = requireNonEmpty(
    input.source_excerpt,
    "source_excerpt",
  );

  const notes: string[] = [
    "twin_written=false — twin document not created/updated",
    "prompts_injected=false — no live LLM note-taker prompt injection",
    "live_dispatch_authorized=false — no automatic twin agent dispatch",
    "insights/questions not invented — scaffold only + caller focus_questions",
  ];

  let existing_twin_asset_id: string | null = null;
  if (
    input.existing_twin_asset_id != null &&
    input.existing_twin_asset_id !== undefined
  ) {
    existing_twin_asset_id = requireNonEmpty(
      input.existing_twin_asset_id,
      "existing_twin_asset_id",
    );
    notes.push(`existing_twin_asset_id=${existing_twin_asset_id}`);
  } else {
    notes.push("existing_twin_asset_id=null — new twin proposal");
  }

  const twin_scaffold_sections: string[] = [
    `<section data-role="source-excerpt" data-parent="${parent_asset_id}">${source_excerpt}</section>`,
    `<section data-role="insights-placeholder" data-parent="${parent_asset_id}"><!-- caller/LLM fills; pure layer does not invent --></section>`,
    `<section data-role="questions-placeholder" data-parent="${parent_asset_id}"><!-- caller/LLM fills; pure layer does not invent --></section>`,
  ];

  let focus_question_count = 0;
  if (input.focus_questions != null) {
    if (!Array.isArray(input.focus_questions)) {
      throw new Error("focus_questions must be an array when set");
    }
    for (let i = 0; i < input.focus_questions.length; i++) {
      const q = requireNonEmpty(
        input.focus_questions[i],
        `focus_questions[${i}]`,
      );
      twin_scaffold_sections.push(
        `<section data-role="focus-question" data-parent="${parent_asset_id}">${q}</section>`,
      );
      focus_question_count += 1;
    }
  }

  notes.push(
    `source_excerpt_chars=${source_excerpt.length} · focus_question_count=${focus_question_count}`,
  );

  const twin_propose_ready = input.operator_ack === true;
  if (!twin_propose_ready) {
    notes.push("twin_propose_ready=false — operator_ack required");
  } else {
    notes.push(
      "twin_propose_ready=true — provisional twin scaffold ready (still twin_written=false)",
    );
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");

  return {
    parent_asset_id,
    existing_twin_asset_id,
    source_excerpt_chars: source_excerpt.length,
    focus_question_count,
    twin_scaffold_sections,
    twin_propose_ready,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    notes,
    authority: "recursive_twin_note_taker_compose_advisory",
  };
}

export function formatRecursiveTwinNoteTakerSummary(
  c: RecursiveTwinNoteTakerCompose,
): string {
  return (
    `twin_propose_ready=${c.twin_propose_ready} · chars=${c.source_excerpt_chars} · ` +
    `focus_q=${c.focus_question_count} · twin_written=false · prompts_injected=false`
  );
}
