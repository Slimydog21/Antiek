/**
 * Workstation recursive record pack (pure).
 *
 * Operator vision: live in the research workstation; record valuable data,
 * insights, and questions recursively so they inform all prompts.
 *
 * This pure layer packs caller-supplied records for prompt context injection
 * intent. record_persisted and prompts_injected are always false.
 */

export type RecordKind =
  | "insight"
  | "question"
  | "highlight"
  | "finding"
  | "open_thread";

export interface WorkstationRecordItem {
  record_id: string;
  kind: RecordKind;
  text: string;
  /** Optional source asset id. */
  asset_id?: string;
  /** Optional weight 0..1 for prompt prioritization (caller-supplied). */
  weight?: number | null;
}

export interface WorkstationRecursiveRecordPack {
  session_id: string;
  item_count: number;
  by_kind: Record<RecordKind, number>;
  /** Ordered texts ready for prompt context (caller-supplied only). */
  prompt_context_lines: string[];
  /** True when ≥1 item present. */
  pack_ready: boolean;
  /** Always false — pure pack does not write durable records. */
  record_persisted: false;
  /** Always false — pure pack does not inject into live prompts. */
  prompts_injected: false;
  notes: string[];
  authority: "workstation_recursive_record_pack_advisory";
}

const VALID_KINDS = new Set<RecordKind>([
  "insight",
  "question",
  "highlight",
  "finding",
  "open_thread",
]);

function requireNonEmpty(value: unknown, name: string): string {
  if (typeof value !== "string" || !value.trim()) {
    throw new Error(`${name} must be a non-empty string`);
  }
  return value.trim();
}

/**
 * Pack workstation records for recursive prompt-context intent.
 * Never invents content; never persists; never injects prompts.
 */
export function composeWorkstationRecursiveRecordPack(input: {
  session_id: string;
  items: WorkstationRecordItem[];
  /** Optional max lines for prompt_context_lines (positive int when set). */
  max_context_lines?: number | null;
}): WorkstationRecursiveRecordPack {
  if (!input || typeof input !== "object") {
    throw new Error("input must be an object");
  }
  const session_id = requireNonEmpty(input.session_id, "session_id");
  if (!Array.isArray(input.items)) {
    throw new Error("items must be an array");
  }

  let maxLines: number | null = null;
  if (input.max_context_lines !== undefined && input.max_context_lines !== null) {
    if (
      typeof input.max_context_lines !== "number" ||
      !Number.isInteger(input.max_context_lines) ||
      input.max_context_lines <= 0
    ) {
      throw new Error("max_context_lines must be a positive integer when set");
    }
    maxLines = input.max_context_lines;
  }

  const notes: string[] = [
    "record_persisted=false — pack intent only",
    "prompts_injected=false — does not mutate live prompts",
    "record texts are caller-supplied only (no invent)",
  ];

  const by_kind: Record<RecordKind, number> = {
    insight: 0,
    question: 0,
    highlight: 0,
    finding: 0,
    open_thread: 0,
  };

  const seenIds = new Set<string>();
  type Scored = { line: string; weight: number; order: number };
  const scored: Scored[] = [];

  for (let i = 0; i < input.items.length; i++) {
    const it = input.items[i];
    if (!it || typeof it !== "object") {
      throw new Error(`items[${i}] must be an object`);
    }
    const record_id = requireNonEmpty(it.record_id, `items[${i}].record_id`);
    if (seenIds.has(record_id)) {
      throw new Error(`duplicate record_id: ${record_id}`);
    }
    seenIds.add(record_id);

    const kind = it.kind;
    if (!VALID_KINDS.has(kind as RecordKind)) {
      throw new Error(
        `items[${i}].kind must be insight|question|highlight|finding|open_thread`,
      );
    }
    const k = kind as RecordKind;
    by_kind[k] += 1;

    const text = requireNonEmpty(it.text, `items[${i}].text`);
    let weight = 0.5;
    if (it.weight !== undefined && it.weight !== null) {
      if (
        typeof it.weight !== "number" ||
        !Number.isFinite(it.weight) ||
        it.weight < 0 ||
        it.weight > 1
      ) {
        throw new Error(`items[${i}].weight must be finite in [0, 1] when set`);
      }
      weight = it.weight;
    }

    let assetPart = "";
    if (it.asset_id != null) {
      const aid = requireNonEmpty(it.asset_id, `items[${i}].asset_id`);
      assetPart = ` @${aid}`;
    }

    scored.push({
      line: `[${k}]${assetPart} ${text}`,
      weight,
      order: i,
    });
  }

  // Higher weight first; stable by input order for ties.
  scored.sort((a, b) => {
    if (b.weight !== a.weight) return b.weight - a.weight;
    return a.order - b.order;
  });

  let prompt_context_lines = scored.map((s) => s.line);
  if (maxLines !== null && prompt_context_lines.length > maxLines) {
    notes.push(
      `max_context_lines=${maxLines} — truncated from ${prompt_context_lines.length}`,
    );
    prompt_context_lines = prompt_context_lines.slice(0, maxLines);
  }

  const item_count = input.items.length;
  const pack_ready = item_count >= 1;
  if (!pack_ready) {
    notes.push("pack_ready=false — empty items (no invent records)");
  } else {
    notes.push(
      `pack_ready=true · items=${item_count} · context_lines=${prompt_context_lines.length}`,
    );
  }
  notes.push("record_persisted=false");
  notes.push("prompts_injected=false");

  return {
    session_id,
    item_count,
    by_kind,
    prompt_context_lines,
    pack_ready,
    record_persisted: false,
    prompts_injected: false,
    notes,
    authority: "workstation_recursive_record_pack_advisory",
  };
}

export function formatWorkstationRecursiveRecordPackSummary(
  p: WorkstationRecursiveRecordPack,
): string {
  return (
    `record pack ${p.session_id} · items=${p.item_count} · ` +
    `ready=${p.pack_ready} · record_persisted=false · prompts_injected=false`
  );
}
