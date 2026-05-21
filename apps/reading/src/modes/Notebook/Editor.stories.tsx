import type { Meta, StoryObj } from "@storybook/react";

import EditorPanel from "./EditorPanel";

/**
 * NotebookEditor — TipTap-based block editor (S7-full). Five custom
 * Antiek block kinds + StarterKit defaults + slash menu + local
 * autosave.
 *
 * In a real workspace this opens via:
 *
 *   import { openNotebook } from "../../workspace/actions";
 *   openNotebook({ notebookId: "demo-1", kind: "NotebookEditor" });
 */
const meta = {
  title: "Loop 1 / NotebookEditor",
  component: EditorPanel,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof EditorPanel>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Blank: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-3xl mx-auto h-full bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night overflow-hidden">
        <EditorPanel notebookId="storybook-blank" />
      </div>
    </div>
  ),
};

export const WithSampleContent: Story = {
  render: () => (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-3xl mx-auto h-full bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night overflow-hidden">
        <EditorPanel
          notebookId="storybook-sample"
          initialContent={`
            <h1>NVDA Q4 risk model</h1>
            <p>
              Three independent groups report single-qubit gate error
              rates between 8&times;10<sup>-4</sup> and
              1.5&times;10<sup>-3</sup>. Cross-comparison is hampered
              by gate-set choice.
            </p>
            <antiek-note text="Open question: head-to-head benchmark with shared decomposition?"></antiek-note>
            <antiek-claim-card claim_id="claim-1234567890"></antiek-claim-card>
            <h2>Insights</h2>
            <p>
              Type <code>/</code> to insert a block:
              note, claim card, region embed, cross-doc link, synthesis
              section, headings, lists, blockquote, code.
            </p>
          `}
        />
      </div>
    </div>
  ),
};
