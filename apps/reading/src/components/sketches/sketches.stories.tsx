import type { Meta, StoryObj } from "@storybook/react";

import { SketchCanvas } from "./SketchCanvas";
import { SKETCH_NAMES, SKETCH_REGISTRY, type SketchName } from "./index";

function SketchGrid({
  reducedMotion,
  seed,
}: {
  reducedMotion: boolean;
  seed: string;
}) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
        gap: 16,
        padding: 16,
        background: "var(--page)",
      }}
    >
      {SKETCH_NAMES.map((name: SketchName) => {
        const def = SKETCH_REGISTRY[name];
        return (
          <figure key={name} style={{ margin: 0 }}>
            <figcaption
              style={{
                color: "var(--text-muted)",
                fontFamily: "ui-monospace, monospace",
                fontSize: 12,
                marginBottom: 8,
              }}
            >
              {def.label}
            </figcaption>
            <SketchCanvas
              render={def.render}
              params={{ ...def.defaultParams, seed, reducedMotion }}
              width={320}
              height={200}
              reducedMotion={reducedMotion}
              animate={!reducedMotion}
              aria-label={def.label}
              testId={`sketch-${name}`}
            />
          </figure>
        );
      })}
    </div>
  );
}

const meta = {
  title: "Sketches / Processing seed sketches",
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta;

export default meta;
type Story = StoryObj;

export const AllThree: Story = {
  name: "All three (animated)",
  render: () => <SketchGrid reducedMotion={false} seed="storybook-demo" />,
};

export const ReducedMotion: Story = {
  name: "Reduced motion (static)",
  render: () => <SketchGrid reducedMotion seed="storybook-demo" />,
};

export const AlternateSeed: Story = {
  name: "Alternate seed",
  render: () => (
    <SketchGrid reducedMotion={false} seed="artifact-xyz-alternate" />
  ),
};
