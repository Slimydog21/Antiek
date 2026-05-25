import type { Meta, StoryObj } from "@storybook/react";

import { WriteEditor } from "./Editor";

/**
 * WriteEditor — the Write workflow's structured TipTap block editor
 * (specs/write/ SPR-04). Replaces CreationStudio's plain textarea: lego
 * blocks + prose, inline citations (click → trace-to-source intent), and
 * granular edit.captured emission underneath.
 *
 * Edit-capture POSTs are best-effort and swallowed when no backend is
 * present, so these stories render standalone.
 */
const meta = {
  title: "Write / Editor",
  component: WriteEditor,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof WriteEditor>;

export default meta;
type Story = StoryObj<typeof meta>;

function frame(children: React.ReactNode) {
  return (
    <div className="h-screen bg-ice-2 dark:bg-space-2 p-6">
      <div className="w-full max-w-3xl mx-auto bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z3 dark:shadow-z3-night p-6">
        {children}
      </div>
    </div>
  );
}

export const Empty: Story = {
  render: () =>
    frame(
      <WriteEditor deliverableId="story-dlv" sectionId="story-sec-empty" />,
    ),
};

export const WithProse: Story = {
  render: () =>
    frame(
      <WriteEditor
        deliverableId="story-dlv"
        sectionId="story-sec-prose"
        initialContent={
          "<p>The thesis holds because the mechanism is load-bearing, " +
          "not decorative.</p><p>Capital intensity rises with scale; the " +
          "moat is the data, not the model.</p>"
        }
      />,
    ),
};

export const WithLegoBlockAndCitation: Story = {
  render: () =>
    frame(
      <WriteEditor
        deliverableId="story-dlv"
        sectionId="story-sec-lego"
        initialContent={
          '<antiek-block block_kind="insight" provenance_kind="graph_node" ' +
          'node_id="node-abc" outline_block_id="oblk-1" section_id="story-sec-lego" ' +
          'text="Capital intensity rises with scale."></antiek-block>' +
          "<p>Drafting around the block. The claim traces to its source " +
          '<antiek-cite node_id="node-abc" provenance_kind="graph_node" ' +
          'section_id="story-sec-lego" label="node-abc"></antiek-cite></p>'
        }
      />,
    ),
};
