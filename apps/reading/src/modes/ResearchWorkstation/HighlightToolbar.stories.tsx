import type { Meta, StoryObj } from "@storybook/react";
import { useRef } from "react";

import HighlightToolbar from "./HighlightToolbar";

/**
 * HighlightToolbar — anchors to user text selection inside `scopeRef`.
 * Renders nothing until the operator selects a span. The story below
 * gives the operator a scratch passage to select; selecting any text
 * inside the gold box surfaces the toolbar with a "Chase this" affordance.
 */
const meta = {
  title: "Loop 1 / HighlightToolbar",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

export const SelectableScope: Story = {
  render: () => {
    const Inner = () => {
      const scopeRef = useRef<HTMLDivElement>(null);
      return (
        <div className="p-10 bg-ice-2 dark:bg-space-2 min-h-screen text-ink dark:text-bright">
          <p className="font-mono text-xs uppercase tracking-wider text-shadow-1 dark:text-moonlight mb-3">
            Select any text inside the box below — the toolbar will appear.
          </p>
          <div
            ref={scopeRef}
            className="bg-ice-0 dark:bg-charcoal-2 border-edge border-sun rounded-hog shadow-z2 dark:shadow-z2-night p-6 font-serif text-lg leading-relaxed"
          >
            He's heading for the mountains, some seventy kilometres away.
            Even if we caught him and brought him back to the colony, he
            would immediately turn around and head back for the mountains.
            The other penguins waddled back to the sea. This one waddled
            inland.
          </div>
          <HighlightToolbar
            scopeRef={scopeRef}
            onChaseThis={(text) => alert(`Chase: ${text}`)}
          />
        </div>
      );
    };
    return <Inner />;
  },
};
