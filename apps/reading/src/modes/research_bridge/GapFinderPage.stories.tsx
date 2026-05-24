import type { Meta, StoryObj } from "@storybook/react";

import { GapFinderPage } from "./GapFinderPage";
import { MOCK_BLOCKS } from "./mock_blocks";
import type { FindGapsResponse, ResearchBridgeClient } from "./api_client";

const meta = {
  title: "Research Bridge / GapFinderPage",
  component: GapFinderPage,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof GapFinderPage>;

export default meta;
type Story = StoryObj<typeof meta>;

function makeStub(overrides: Partial<ResearchBridgeClient> = {}): ResearchBridgeClient {
  const defaultRun: FindGapsResponse = {
    run: {
      run_id: "rgrun-storybook",
      operator_label: "Prime Intellect thesis — verifier productisation",
      session_id: "S-prim-thesis",
      scope_block_ids: MOCK_BLOCKS.slice(0, 2).map((b) => b.document_id),
      scope_question_ids: ["rpoq-1", "rpoq-2", "rpoq-3"],
      cluster_model_id: "fake/claude-sonnet-4-6",
      total_input_tokens: 1245, total_output_tokens: 312,
      total_cost_usd: 0.0184, created_at: "2026-05-24T18:42:01",
    },
    clusters: [
      { cluster_id: "rgcl-a", label: "Anthropic verifier productisation timeline",
        priority_rank: 0, rationale: "Three open questions converge here." },
      { cluster_id: "rgcl-b", label: "Compute Marketplace customer commitments",
        priority_rank: 1, rationale: "Sell-side watching Jan 22 investor day." },
    ],
    prompts: [
      { prompt_id: "rgpr-1", cluster_id: "rgcl-a", order_index: 0,
        prompt_text: "What is the current status of Anthropic's internal verifier work (arXiv 2410.05678, 2411.08901, 2412.02345)? Has any shipped as a product?",
        target_provider: "anthropic", expected_output_shape: "List of launches + dates",
        depends_on_prior_order_index: null,
        rationale: "Anthropic deep-research tracks Anthropic's own launches best.",
        input_tokens: 100, output_tokens: 60, cost_usd: 0.0042 },
      { prompt_id: "rgpr-2", cluster_id: "rgcl-b", order_index: 1,
        prompt_text: "Find sell-side notes 2024-10-29 to 2025-01-22 on PRIM Compute Marketplace customer commitments. Cite 10-Q footnote 8.",
        target_provider: "alphasense", expected_output_shape: "Table of notes by firm + rating",
        depends_on_prior_order_index: null,
        rationale: "AlphaSense is the direct line into sell-side coverage.",
        input_tokens: 120, output_tokens: 80, cost_usd: 0.0058 },
    ],
    grounding_drops: 0,
  };
  return {
    async listPastes() { return { count: MOCK_BLOCKS.length, pastes: MOCK_BLOCKS }; },
    async postFindGaps() { return defaultRun; },
    async postSignal() { return { signal_id: "rgs-stub" }; },
    async postPaste(req) {
      return {
        document_id: "doc-paste-back-stub", source: req.source_override ?? "other",
        source_confidence: 0.92, raw_sha256: "sha-stub",
        paste_byte_length: req.raw_text.length, parser_version: 1,
        chunk_count: 1, per_source_scores: {},
      };
    },
    async postAnswer() { return { answer_id: "rga-stub" }; },
    async postExtract(documentId) {
      return {
        extraction_id: "rpex-stub", document_id: documentId, extractor_version: 1,
        model_id: "fake/extractor", status: "ok", insights: [], open_questions: [],
        quote_drops: 0, input_tokens: 100, output_tokens: 30, cost_usd: 0.001,
      };
    },
    async getGapRun() { return defaultRun; },
    async listItems(documentId) { return { document_id: documentId, insights: [], open_questions: [] }; },
    async getWouldRunPercentage() { return { would_run_count: 2, total_signalled: 3, percentage: 2 / 3, run_id: null }; },
    ...overrides,
  };
}

export const Idle: Story = {
  render: () => (
    <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3"><GapFinderPage client={makeStub()} /></div>
  ),
};

export const PreScopedAndReadyToFind: Story = {
  render: () => (
    <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3">
      <GapFinderPage client={makeStub()} initialScope={MOCK_BLOCKS.slice(0, 2).map((b) => b.document_id)} />
    </div>
  ),
};

export const PendingFindGaps: Story = {
  render: () => {
    const stub = makeStub({ postFindGaps: () => new Promise<FindGapsResponse>(() => undefined) });
    return (
      <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3">
        <GapFinderPage client={stub} initialScope={MOCK_BLOCKS.slice(0, 2).map((b) => b.document_id)} />
      </div>
    );
  },
};

export const ErrorState: Story = {
  render: () => {
    const stub = makeStub({
      async postFindGaps(): Promise<FindGapsResponse> { throw new Error("502 from cascade LLM provider"); },
    });
    return (
      <div className="h-screen p-4 bg-ice-1 dark:bg-charcoal-3">
        <GapFinderPage client={stub} initialScope={MOCK_BLOCKS.slice(0, 2).map((b) => b.document_id)} />
      </div>
    );
  },
};
