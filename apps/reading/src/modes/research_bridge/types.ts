/**
 * Type definitions for the Antiek Deep Research Bridge frontend kit.
 *
 * Mirrors the API response shape from
 * ``interfaces/research/api/research_bridge.py``.
 */

export type ResearchSource =
  | "chatgpt"
  | "anthropic"
  | "grok"
  | "alphasense"
  | "other";

export const ALL_SOURCES: ResearchSource[] = [
  "chatgpt", "anthropic", "grok", "alphasense", "other",
];

export interface ResearchBlockSummary {
  document_id: string;
  source: ResearchSource;
  source_confidence: number;
  paste_byte_length: number;
  operator_label: string | null;
  session_id: string | null;
  pasted_at: string;
  title: string | null;
  insight_count?: number;
  open_question_count?: number;
  preview_text?: string;
}

export interface ExtractedItemPayload {
  item_id: string;
  summary: string;
  quote: string;
  quote_start_offset: number;
  quote_end_offset: number;
  llm_confidence: number;
  extractor_version: number;
  model_id: string;
}

export interface DragPayload {
  block_id: string;
  source: ResearchSource;
}

export const SOURCE_VISUAL: Record<
  ResearchSource,
  { label: string; tagColour: "default" | "sun" | "aurora" | "danger" | "muted" }
> = {
  chatgpt:    { label: "ChatGPT",    tagColour: "aurora" },
  anthropic:  { label: "Anthropic",  tagColour: "sun" },
  grok:       { label: "Grok",       tagColour: "muted" },
  alphasense: { label: "AlphaSense", tagColour: "default" },
  other:      { label: "Other",      tagColour: "muted" },
};
