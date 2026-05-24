/**
 * Typed API client for the Antiek Deep Research Bridge.
 *
 * Pass a custom ``fetchImpl`` to swap in a stub for tests / Storybook.
 * Production uses ``apiFetch`` (Cloudflare Access cookies +
 * VITE_API_BASE_URL).
 */

import { API_BASE, ApiError, apiFetch } from "../../lib/api";
import type {
  ExtractedItemPayload, ResearchBlockSummary, ResearchSource,
} from "./types";

export interface DetectResponse {
  source: ResearchSource;
  confidence: number;
  parser_version: number;
  per_source: Record<string, number>;
}

export interface PasteRequest {
  raw_text: string;
  operator_label?: string | null;
  session_id?: string | null;
  source_override?: ResearchSource | null;
  source_tier?: number;
  investigation_id?: string | null;
}

export interface PasteResponse {
  document_id: string;
  source: ResearchSource;
  source_confidence: number;
  raw_sha256: string;
  paste_byte_length: number;
  parser_version: number;
  chunk_count: number;
  per_source_scores: Record<string, number>;
}

export interface ListPastesResponse {
  count: number;
  pastes: ResearchBlockSummary[];
}

export interface ExtractRequest {
  regenerate?: boolean;
}

export interface ExtractResponse {
  extraction_id: string;
  document_id: string;
  extractor_version: number;
  model_id: string;
  status: "ok" | "cache_hit";
  insights: ExtractedItemPayload[];
  open_questions: ExtractedItemPayload[];
  quote_drops: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface ListItemsResponse {
  document_id: string;
  insights: ExtractedItemPayload[];
  open_questions: ExtractedItemPayload[];
}

export interface FindGapsRequest {
  scope_block_ids: string[];
  operator_label?: string | null;
  session_id?: string | null;
}

export interface GapClusterPayload {
  cluster_id: string;
  label: string;
  priority_rank: number;
  rationale: string | null;
}

export interface GapPromptPayload {
  prompt_id: string;
  cluster_id: string | null;
  order_index: number;
  prompt_text: string;
  target_provider: ResearchSource;
  expected_output_shape: string | null;
  depends_on_prior_order_index: number | null;
  rationale: string | null;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;
}

export interface GapRunPayload {
  run_id: string;
  operator_label: string | null;
  session_id: string | null;
  scope_block_ids: string[];
  scope_question_ids: string[];
  cluster_model_id: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost_usd: number;
  created_at: string;
}

export interface FindGapsResponse {
  run: GapRunPayload;
  clusters: GapClusterPayload[];
  prompts: GapPromptPayload[];
  grounding_drops: number;
}

export interface WouldRunPercentageResponse {
  would_run_count: number;
  total_signalled: number;
  percentage: number;
  run_id: string | null;
}

export interface ResearchBridgeClient {
  postDetect(rawText: string): Promise<DetectResponse>;
  postPaste(req: PasteRequest): Promise<PasteResponse>;
  listPastes(opts?: { limit?: number; source?: ResearchSource; sessionId?: string }): Promise<ListPastesResponse>;
  postExtract(documentId: string, req?: ExtractRequest): Promise<ExtractResponse>;
  listItems(documentId: string, opts?: { version?: number }): Promise<ListItemsResponse>;
  postFindGaps(req: FindGapsRequest): Promise<FindGapsResponse>;
  getGapRun(runId: string): Promise<FindGapsResponse>;
  postSignal(promptId: string, signalType: "would_run" | "skip"): Promise<{ signal_id: string }>;
  postAnswer(promptId: string, answerDocumentId: string): Promise<{ answer_id: string }>;
  getWouldRunPercentage(runId?: string): Promise<WouldRunPercentageResponse>;
}

async function _ok<T>(resp: Response): Promise<T> {
  if (!resp.ok) {
    const body = await resp.text();
    throw new ApiError(`${resp.status} ${resp.statusText}: ${body}`, resp.status, body);
  }
  return resp.json() as Promise<T>;
}

export function createHttpClient(
  options: { fetchImpl?: typeof apiFetch; baseUrl?: string } = {},
): ResearchBridgeClient {
  const f = options.fetchImpl ?? apiFetch;
  const base = options.baseUrl ?? API_BASE;

  return {
    async postDetect(rawText) {
      const r = await f(`${base}/research/detect`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ raw_text: rawText }),
      });
      return _ok<DetectResponse>(r);
    },
    async postPaste(req) {
      const r = await f(`${base}/research/pastes`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req),
      });
      return _ok<PasteResponse>(r);
    },
    async listPastes(opts) {
      const u = new URL(`${base || ""}/research/pastes`, "http://stub.local");
      if (opts?.limit !== undefined) u.searchParams.set("limit", String(opts.limit));
      if (opts?.source) u.searchParams.set("source", opts.source);
      if (opts?.sessionId) u.searchParams.set("session_id", opts.sessionId);
      const target = base ? u.toString() : `${u.pathname}${u.search}`;
      return _ok<ListPastesResponse>(await f(target));
    },
    async postExtract(documentId, req) {
      const r = await f(`${base}/research/pastes/${encodeURIComponent(documentId)}/extract`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req ?? {}),
      });
      return _ok<ExtractResponse>(r);
    },
    async listItems(documentId, opts) {
      const u = new URL(
        `${base || ""}/research/pastes/${encodeURIComponent(documentId)}/items`,
        "http://stub.local",
      );
      if (opts?.version !== undefined) u.searchParams.set("version", String(opts.version));
      const target = base ? u.toString() : `${u.pathname}${u.search}`;
      return _ok<ListItemsResponse>(await f(target));
    },
    async postFindGaps(req) {
      const r = await f(`${base}/research/gaps`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(req),
      });
      return _ok<FindGapsResponse>(r);
    },
    async getGapRun(runId) {
      return _ok<FindGapsResponse>(await f(`${base}/research/gaps/${encodeURIComponent(runId)}`));
    },
    async postSignal(promptId, signalType) {
      const r = await f(
        `${base}/research/gaps/prompts/${encodeURIComponent(promptId)}/signal`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ signal_type: signalType }),
        },
      );
      return _ok<{ signal_id: string }>(r);
    },
    async postAnswer(promptId, answerDocumentId) {
      const r = await f(
        `${base}/research/gaps/prompts/${encodeURIComponent(promptId)}/answer`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ answer_document_id: answerDocumentId }),
        },
      );
      return _ok<{ answer_id: string }>(r);
    },
    async getWouldRunPercentage(runId) {
      const u = new URL(`${base || ""}/research/gaps/signals/percentage`, "http://stub.local");
      if (runId) u.searchParams.set("run_id", runId);
      const target = base ? u.toString() : `${u.pathname}${u.search}`;
      return _ok<WouldRunPercentageResponse>(await f(target));
    },
  };
}
