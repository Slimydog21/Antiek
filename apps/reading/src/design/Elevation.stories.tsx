import type { Meta, StoryObj } from "@storybook/react";

import {
  cascadeOffset,
  ELEVATION_EXEMPT_SURFACES,
  shadowForStackDepth,
} from "./elevation";

const meta = {
  title: "Design / Elevation",
  parameters: { layout: "padded" },
} satisfies Meta;

export default meta;
type Story = StoryObj;

function DepthSwatch({
  depth,
  mode,
  label,
}: {
  depth: number;
  mode: "opaque-chunky" | "glass-scene";
  label: string;
}) {
  const shadow = shadowForStackDepth(depth, mode);
  const isGlass = mode === "glass-scene";
  return (
    <div className="flex flex-col gap-2">
      <span className="font-mono text-[11px] text-ink-mute dark:text-moonlight">
        {label}
      </span>
      <div
        className={
          (isGlass
            ? "bg-glass backdrop-blur-glass border-edge border-glass "
            : "bg-ice-0 dark:bg-charcoal-2 border-edge border-sun ") +
          "rounded-hog w-48 h-28 flex items-center justify-center text-sm " +
          shadow
        }
      >
        depth {depth}
      </div>
      <code className="text-[10px] break-all">{shadow}</code>
    </div>
  );
}

/** Opaque chunky tiers (panels) vs flat glass title-bar stamp (windows). */
export const OpaqueVsGlass: Story = {
  render: () => (
    <div className="space-y-8 p-6">
      <section>
        <h3 className="text-sm font-semibold mb-4">opaque-chunky (floating panels)</h3>
        <div className="flex flex-wrap gap-6">
          {[0, 1, 2, 3].map((d) => (
            <DepthSwatch key={d} depth={d} mode="opaque-chunky" label={`tier ${d}`} />
          ))}
        </div>
      </section>
      <section>
        <h3 className="text-sm font-semibold mb-4">glass-scene (workspace windows)</h3>
        <div className="flex flex-wrap gap-6">
          <DepthSwatch depth={0} mode="glass-scene" label="title-bar only" />
          <DepthSwatch depth={3} mode="glass-scene" label="depth ignored" />
        </div>
      </section>
      <section>
        <h3 className="text-sm font-semibold mb-2">Exempt (no stack chrome)</h3>
        <ul className="list-disc pl-5 text-xs text-ink-soft dark:text-starlight">
          {ELEVATION_EXEMPT_SURFACES.map((s) => (
            <li key={s}>{s}</li>
          ))}
        </ul>
      </section>
    </div>
  ),
};

/** Cascade offsets: 22px panels vs 28px windows. */
export const CascadeSteps: Story = {
  render: () => (
    <div className="relative h-64 w-full bg-ice-2 dark:bg-space-2 rounded-hog p-4">
      {[0, 1, 2, 3].map((i) => {
        const w = cascadeOffset(i, "windows");
        const p = cascadeOffset(i, "panels");
        return (
          <div key={i} className="absolute font-mono text-[10px]">
            <div
              style={{ left: 40 + w.x, top: 24 + w.y }}
              className="w-20 h-14 border border-glass bg-glass/80 rounded text-center pt-4"
            >
              win {i}
            </div>
            <div
              style={{ left: 200 + p.x, top: 24 + p.y }}
              className="w-20 h-14 border-edge border-sun bg-ice-0 dark:bg-charcoal-2 rounded-hog shadow-z1 text-center pt-4"
            >
              pan {i}
            </div>
          </div>
        );
      })}
    </div>
  ),
};