/**
 * Recursive twin bind for every information asset (pure client).
 *
 * Operator vision: every information asset has a twin substrate of insights
 * and questions. This pure layer decides whether a twin *link* may be
 * proposed and carries only operator- or LLM-provided notes — never invents
 * content from asset text.
 *
 * twin_created is always false here (bind decision / payload only).
 */

export type TwinBindSource =
  | "operator"
  | "llm_note_taker"
  | "highlight_seed"
  | "unknown";

export interface RecursiveTwinBindInput {
  parent_asset_id: string;
  /** Optional existing twin id (rebind / ensure). */
  twin_id?: string | null;
  insights?: string[] | null;
  questions?: string[] | null;
  /**
   * Provenance of insights/questions.
   * llm_note_taker requires llm_filled=true with non-empty lists from caller.
   */
  source: TwinBindSource;
  /** Explicit: did an LLM fill insights/questions? Never invent true. */
  llm_filled: boolean;
  /** Explicit gate on parent asset body. */
  gated: boolean;
}

export interface RecursiveTwinBindDecision {
  parent_asset_id: string;
  twin_id: string | null;
  bind_allowed: boolean;
  /** Always false in pure layer — no twin store write. */
  twin_created: boolean;
  insights: string[];
  questions: string[];
  source: TwinBindSource;
  llm_filled: boolean;
  notes: string[];
  authority: "twin_bind_advisory";
}

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

function cleanStringList(value: unknown, name: string): string[] {
  if (value == null) return [];
  if (!Array.isArray(value)) {
    throw new Error(`${name} must be an array of strings or null`);
  }
  return value.map((item, i) => {
    if (typeof item !== "string") {
      throw new Error(`${name}[${i}] must be a string`);
    }
    return item.trim();
  }).filter(Boolean);
}

/**
 * Decide whether a recursive twin bind may proceed for an asset.
 * Never invents insights/questions from asset text.
 * twin_created always false.
 */
export function evaluateRecursiveTwinBind(
  input: RecursiveTwinBindInput,
): RecursiveTwinBindDecision {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  if (typeof input.gated !== "boolean") {
    throw new Error(
      "gated must be an explicit boolean from asset provenance (fail closed)",
    );
  }
  if (typeof input.llm_filled !== "boolean") {
    throw new Error("llm_filled must be an explicit boolean (fail closed)");
  }
  const parent = requireNonEmpty(input.parent_asset_id, "parent_asset_id");
  const source = input.source;
  if (
    source !== "operator" &&
    source !== "llm_note_taker" &&
    source !== "highlight_seed" &&
    source !== "unknown"
  ) {
    throw new Error("source must be operator|llm_note_taker|highlight_seed|unknown");
  }

  const notes: string[] = [];
  let twinId: string | null = null;
  if (input.twin_id != null && input.twin_id !== undefined) {
    if (typeof input.twin_id !== "string" || !input.twin_id.trim()) {
      throw new Error("twin_id must be non-empty string or null");
    }
    twinId = input.twin_id.trim();
  }

  if (input.gated === true) {
    notes.push("gated parent asset — bind_allowed=false");
    return {
      parent_asset_id: parent,
      twin_id: twinId,
      bind_allowed: false,
      twin_created: false,
      insights: [],
      questions: [],
      source,
      llm_filled: false,
      notes: [...notes, "twin_created=false", "insights/questions withheld"],
      authority: "twin_bind_advisory",
    };
  }

  const insights = cleanStringList(input.insights, "insights");
  const questions = cleanStringList(input.questions, "questions");

  if (input.llm_filled === true) {
    if (source !== "llm_note_taker") {
      throw new Error(
        "llm_filled=true requires source=llm_note_taker (no invent provenance)",
      );
    }
    if (insights.length === 0 && questions.length === 0) {
      throw new Error(
        "llm_filled=true requires non-empty insights or questions from caller (no invent)",
      );
    }
    notes.push("llm_note_taker payload accepted — content is caller-supplied only");
  } else {
    if (source === "llm_note_taker") {
      throw new Error(
        "source=llm_note_taker requires llm_filled=true with supplied lists",
      );
    }
    if (insights.length === 0 && questions.length === 0) {
      notes.push(
        "no insights/questions supplied — bind still allowed as empty twin scaffold",
      );
    } else {
      notes.push("operator/highlight insights-questions accepted as-supplied");
    }
  }

  if (source === "unknown") {
    notes.push("source=unknown — bind_allowed=false (provenance required)");
    return {
      parent_asset_id: parent,
      twin_id: twinId,
      bind_allowed: false,
      twin_created: false,
      insights: [],
      questions: [],
      source,
      llm_filled: false,
      notes: [...notes, "twin_created=false"],
      authority: "twin_bind_advisory",
    };
  }

  notes.push("bind_allowed=true — pure decision only");
  notes.push("twin_created=false");

  return {
    parent_asset_id: parent,
    twin_id: twinId,
    bind_allowed: true,
    twin_created: false,
    insights,
    questions,
    source,
    llm_filled: input.llm_filled,
    notes,
    authority: "twin_bind_advisory",
  };
}

export function formatTwinBindSummary(d: RecursiveTwinBindDecision): string {
  return (
    `parent=${d.parent_asset_id} · bind_allowed=${d.bind_allowed} · ` +
    `twin_created=false · insights=${d.insights.length} · questions=${d.questions.length}`
  );
}
