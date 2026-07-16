import type { Meta, StoryObj } from "@storybook/react";

import Notebook from "./index";
import type { NotebookBlockResponse, NotebookResponse } from "./types";

const block = (
  block_id: string,
  block_type: NotebookBlockResponse["block_type"],
  content_json: Record<string, unknown>,
  ref_id: string | null,
  block_index: number,
): NotebookBlockResponse => ({
  block_id, block_type, content_json, ref_id, block_index,
  created_at: "2026-07-16T12:00:00Z",
});

const populated: NotebookResponse = {
  notebook_id: "nb-fieldbook",
  title: "Recursive Fieldbook — The compounding moat",
  investigation_id: "inv-antarctic",
  document_id: null,
  content_class: "user_owned",
  created_at: "2026-07-16T10:00:00Z",
  updated_at: "2026-07-16T12:00:00Z",
  blocks: [
    block("b1", "prose", { text: "Each reading pass leaves a more useful substrate for the next question." }, null, 0),
    block("b2", "claim_card", { text: "Recursive capture compounds research context." }, "claim-abc", 1),
    block("b3", "note", { text: "A deleted source remains legible as historical context." }, null, 2),
    block("b4", "region_embed", { excerpt: "The fieldbook stores this excerpt with the reference." }, "region-7", 3),
    block("b5", "question_card", { question_text: "What evidence would overturn this claim?" }, "q-1", 4),
    block("b6", "latex", { latex: "I_{t+1} = I_t + Δcontext" }, null, 5),
    block("b7", "cross_doc_link", { from_document_id: "paper-a", to_document_id: "book-b", question_id: "q-1" }, null, 6),
  ],
};

const empty: NotebookResponse = { ...populated, notebook_id: "nb-empty", title: "Untitled fieldbook", blocks: [] };

const meta = {
  title: "Loop 1 / Recursive Fieldbook",
  component: Notebook,
  parameters: { layout: "fullscreen" },
} satisfies Meta<typeof Notebook>;

export default meta;
type Story = StoryObj<typeof meta>;

export const MissingId: Story = { args: { notebookIdOverride: null, executionEnabled: false } };
export const Loading: Story = { args: { notebookIdOverride: "nb-loading", initialLoading: true, executionEnabled: false } };
export const SafeFailure: Story = { args: { notebookIdOverride: "nb-failed", initialError: "Could not load notebook. Please try again.", executionEnabled: false } };
export const Empty: Story = { args: { notebookIdOverride: empty.notebook_id, initialNotebook: empty, executionEnabled: false } };
export const Populated: Story = { args: { notebookIdOverride: populated.notebook_id, initialNotebook: populated, executionEnabled: false } };
export const Mutating: Story = { args: { notebookIdOverride: populated.notebook_id, initialNotebook: populated, initialMutationPending: true, executionEnabled: false } };
export const MutationFailure: Story = { args: { notebookIdOverride: populated.notebook_id, initialNotebook: populated, initialError: "Could not append the block. Your notebook is unchanged.", executionEnabled: false } };
export const Night: Story = {
  args: Populated.args,
  decorators: [(Story) => <div className="rf-night bg-charcoal-2"><Story /></div>],
};
export const Narrow: Story = {
  args: Populated.args,
  parameters: { viewport: { defaultViewport: "mobile1" } },
  decorators: [(Story) => <div style={{ width: 375, height: 667, overflow: "hidden" }}><Story /></div>],
};
