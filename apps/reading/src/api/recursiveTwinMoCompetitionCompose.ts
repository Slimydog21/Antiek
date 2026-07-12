/**
 * Recursive twin note-taker over MO + model decision + HTML competition (pure).
 *
 * Operator vision: every competition/MO research pack has a twin note-taker
 * scaffold of insights/questions for the infinite information platform —
 * without writing twins or launching live workers.
 *
 * twin_written / prompts_injected / live_dispatch_authorized always false.
 * live_execution_authorized always false.
 */

import {
  composeRecursiveTwinNoteTaker,
  type RecursiveTwinNoteTakerCompose,
} from "./recursiveTwinNoteTakerCompose";
import {
  composeMoModelDecisionHtmlNativeCompetition,
  type MoModelDecisionHtmlNativeCompetitionCompose,
  type MoModelDecisionHtmlNativeCompetitionInput,
} from "./moModelDecisionHtmlNativeCompetitionCompose";

export interface RecursiveTwinMoCompetitionInput
  extends MoModelDecisionHtmlNativeCompetitionInput {
  parent_asset_id: string;
  /**
   * Optional override excerpt for twin note-taker. When omitted, derived from
   * MO goals + competition residuals/citations (caller-supplied content only).
   */
  source_excerpt?: string | null;
  existing_twin_asset_id?: string | null;
  focus_questions?: string[] | null;
  require_both_with_twin?: boolean;
}

export interface RecursiveTwinMoCompetitionCompose {
  parent_asset_id: string;
  mo_research: MoModelDecisionHtmlNativeCompetitionCompose;
  twin: RecursiveTwinNoteTakerCompose;
  pack_ready: boolean;
  twin_written: false;
  prompts_injected: false;
  live_dispatch_authorized: false;
  live_execution_authorized: false;
  live_router_authorized: false;
  pdf_view_authorized: false;
  store_mutated: false;
  notes: string[];
  authority: "recursive_twin_mo_competition_compose_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function deriveExcerpt(
  mo_research: MoModelDecisionHtmlNativeCompetitionCompose,
): string {
  const parts: string[] = [];
  for (const g of mo_research.mo.entry_readiness.entry.goals ?? []) {
    const title =
      typeof g === "object" && g && "title" in g
        ? String((g as { title?: string }).title ?? "")
        : "";
    if (title) parts.push(`goal: ${title}`);
  }
  // Fallback: use launch goals if entry shape differs
  if (parts.length === 0) {
    const launchGoals = mo_research.mo.launch as {
      brief?: { goals?: Array<{ statement?: string }> };
    };
    for (const g of launchGoals.brief?.goals ?? []) {
      if (g.statement) parts.push(`goal: ${g.statement}`);
    }
  }

  const qs =
    mo_research.research.competition_view.competition_pack.quality_write
      .quality_source;
  for (const c of qs.citations.citations) {
    parts.push(`cite: ${c.title}`);
  }
  for (const row of qs.competition.decisions) {
    if (row.residual) {
      parts.push(`residual: ${row.residual}`);
    } else if (row.decision_summary) {
      parts.push(
        `decision: ${row.competitor}/${row.area}: ${row.decision_summary}`,
      );
    }
  }

  const model =
    mo_research.research.decision.driver.decision.selected_model_id;
  parts.push(`model: ${model}`);

  const body = parts.join("\n").trim();
  return body.length > 0
    ? body
    : "MO competition research pack — twin scaffold from empty residual set";
}

function deriveFocusQuestions(
  mo_research: MoModelDecisionHtmlNativeCompetitionCompose,
  extra: string[] | null | undefined,
): string[] {
  const qs: string[] = [];
  if (extra != null) {
    for (const q of extra) {
      if (typeof q === "string" && q.trim()) qs.push(q.trim());
    }
  }
  for (const row of mo_research.research.competition_view.competition_pack
    .quality_write.quality_source.competition.decisions) {
    if (row.antiek_status === "behind" && row.residual) {
      qs.push(row.residual);
    }
  }
  return qs;
}

/**
 * Compose recursive twin note-taker over MO + model decision competition pack.
 * Never writes twins or launches workers.
 */
export function composeRecursiveTwinMoCompetition(
  input: RecursiveTwinMoCompetitionInput,
): RecursiveTwinMoCompetitionCompose {
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

  const require_both_with_twin =
    input.require_both_with_twin === undefined
      ? true
      : input.require_both_with_twin;
  if (typeof require_both_with_twin !== "boolean") {
    throw new Error("require_both_with_twin must be boolean when set");
  }

  const notes: string[] = [
    "twin_written=false · prompts_injected=false · live_dispatch_authorized=false",
    "live_execution_authorized=false · live_router_authorized=false",
    "pdf_view_authorized=false · store_mutated=false",
  ];

  const mo_research = composeMoModelDecisionHtmlNativeCompetition({
    mo: input.mo,
    research: input.research,
    operator_ack: input.operator_ack,
    require_both: input.require_both,
  });
  notes.push(...mo_research.notes.map((n) => `[mo_research] ${n}`));

  const source_excerpt =
    input.source_excerpt != null && String(input.source_excerpt).trim()
      ? String(input.source_excerpt).trim()
      : deriveExcerpt(mo_research);
  notes.push(
    input.source_excerpt != null && String(input.source_excerpt).trim()
      ? "source_excerpt caller-supplied"
      : "source_excerpt derived from MO goals + competition residuals/citations",
  );

  const focus = deriveFocusQuestions(mo_research, input.focus_questions);

  const twin = composeRecursiveTwinNoteTaker({
    parent_asset_id,
    source_excerpt,
    existing_twin_asset_id: input.existing_twin_asset_id,
    operator_ack: input.operator_ack,
    focus_questions: focus.length > 0 ? focus : null,
  });
  notes.push(...twin.notes.map((n) => `[twin] ${n}`));

  let pack_ready = false;
  if (require_both_with_twin) {
    pack_ready =
      mo_research.pack_ready === true &&
      twin.twin_propose_ready === true &&
      input.operator_ack === true;
  } else {
    pack_ready =
      input.operator_ack === true &&
      (mo_research.pack_ready === true || twin.twin_propose_ready === true);
  }

  if (pack_ready) {
    notes.push(
      "pack_ready=true — MO competition research + twin note-taker propose ready; still pure",
    );
  } else {
    notes.push(
      "pack_ready=false — mo_research, twin, or operator_ack gate open",
    );
  }

  if (
    mo_research.live_execution_authorized !== false ||
    mo_research.live_router_authorized !== false ||
    mo_research.twin_written !== false ||
    twin.twin_written !== false ||
    twin.prompts_injected !== false ||
    twin.live_dispatch_authorized !== false
  ) {
    throw new Error("invariant: honesty flags must remain false");
  }

  notes.push("twin_written=false");
  notes.push("prompts_injected=false");
  notes.push("live_dispatch_authorized=false");
  notes.push("live_execution_authorized=false");
  notes.push("live_router_authorized=false");
  notes.push("pdf_view_authorized=false");
  notes.push("store_mutated=false");

  return {
    parent_asset_id,
    mo_research,
    twin,
    pack_ready,
    twin_written: false,
    prompts_injected: false,
    live_dispatch_authorized: false,
    live_execution_authorized: false,
    live_router_authorized: false,
    pdf_view_authorized: false,
    store_mutated: false,
    notes,
    authority: "recursive_twin_mo_competition_compose_advisory",
  };
}

export function formatRecursiveTwinMoCompetitionSummary(
  c: RecursiveTwinMoCompetitionCompose,
): string {
  return (
    `pack_ready=${c.pack_ready} · ` +
    `mo_research_ready=${c.mo_research.pack_ready} · ` +
    `twin_propose_ready=${c.twin.twin_propose_ready} · ` +
    `sections=${c.twin.twin_scaffold_sections.length} · ` +
    `twin_written=false · live_execution_authorized=false · prompts_injected=false`
  );
}
