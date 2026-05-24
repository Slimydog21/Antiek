import type { Meta, StoryObj } from "@storybook/react";

import { ResearchBridgeHome } from "./ResearchBridgeHome";
import { MOCK_BLOCKS } from "./mock_blocks";
import type { FindGapsResponse, ResearchBridgeClient } from "./api_client";

const meta = {
  title: "Research Bridge / ResearchBridgeHome",
  component: ResearchBridgeHome,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof ResearchBridgeHome>;

export default meta;
type Story = StoryObj<typeof meta>;

function stubClient(): ResearchBridgeClient {
  const run: FindGapsResponse = {
    run: {
      run_id: "rgrun-home", operator_label: null, session_id: null,
      scope_block_ids: [], scope_question_ids: [],
      cluster_model_id: "fake", total_input_tokens: 0, total_output_tokens: 0,
      total_cost_usd: 0, created_at: "2026-05-24",
    },
    clusters: [], prompts: [], grounding_drops: 0,
  };
  return {
    async postDetect(rawText) {
      const isAlpha = /alphasense|sell-side/i.test(rawText);
      return {
        source: isAlpha ? "alphasense" : "anthropic", confidence: 0.8,
        parser_version: 1,
        per_source: { chatgpt: 0.1, anthropic: 0.8, grok: 0.1, alphasense: 0.2 },
      };
    },
    async listPastes() { return { count: MOCK_BLOCKS.length, pastes: MOCK_BLOCKS }; },
    async postFindGaps() { return run; },
    async postSignal() { return { signal_id: "s" }; },
    async postPaste(req) {
      return {
        document_id: "doc-home-stub", source: req.source_override ?? "anthropic",
        source_confidence: 0.8, raw_sha256: "sha", paste_byte_length: req.raw_text.length,
        parser_version: 1, chunk_count: 1, per_source_scores: {},
      };
    },
    async postAnswer() { return { answer_id: "a" }; },
    async postExtract(documentId) {
      return {
        extraction_id: "x", document_id: documentId, extractor_version: 1,
        model_id: "fake", status: "ok", insights: [], open_questions: [],
        quote_drops: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0,
      };
    },
    async getGapRun() { return run; },
    async listItems(documentId) { return { document_id: documentId, insights: [], open_questions: [] }; },
    async getWouldRunPercentage() { return { would_run_count: 0, total_signalled: 0, percentage: 0, run_id: null }; },
  };
}

export const Default: Story = {
  render: () => (
    <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3">
      <ResearchBridgeHome client={stubClient()} />
    </div>
  ),
};

export const StartingOnGapFinder: Story = {
  render: () => (
    <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3">
      <ResearchBridgeHome client={stubClient()} initialTab="gaps" />
    </div>
  ),
};
