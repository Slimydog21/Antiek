import type { Meta, StoryObj } from "@storybook/react";

import { SCENE_HOTSPOTS } from "./interactiveRegions";
import { productActionForSceneHotspot } from "./sceneHotspotProductRoutes";

/**
 * Documentation story — Flipbook-feel scenery → product routes.
 * Not a visual pixel regression; a readable inventory for design agents.
 */
function SceneryProductMapTable() {
  return (
    <div className="space-y-4 p-6 font-mono text-[13px]">
      <header>
        <h1 className="font-serif text-xl text-ink dark:text-bright">
          Flipbook scenery product map
        </h1>
        <p className="mt-1 text-shadow-1 dark:text-moonlight">
          Click only. Hover stays ambient. peak-left is reserved for shell-launch
          honesty proof (no navigation).
        </p>
      </header>
      <table
        data-testid="scenery-product-map-table"
        className="w-full border-collapse text-left"
      >
        <thead>
          <tr className="border-b border-rule dark:border-charcoal-1">
            <th className="py-2 pr-4">Hotspot</th>
            <th className="py-2 pr-4">Label</th>
            <th className="py-2 pr-4">Click route</th>
            <th className="py-2">Werner</th>
          </tr>
        </thead>
        <tbody>
          {SCENE_HOTSPOTS.map((h) => {
            const action = productActionForSceneHotspot(h.id, "click");
            return (
              <tr
                key={h.id}
                data-testid={`scenery-row-${h.id}`}
                className="border-b border-rule/50 dark:border-charcoal-1"
              >
                <td className="py-2 pr-4 text-ink dark:text-bright">{h.id}</td>
                <td className="py-2 pr-4 text-shadow-1 dark:text-moonlight">
                  {h.label}
                </td>
                <td className="py-2 pr-4">
                  {action ? action.route : "ambient"}
                </td>
                <td className="py-2">
                  {action?.wernerExperience ?? "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

const meta = {
  title: "Loop 0 / Flipbook scenery product map",
  component: SceneryProductMapTable,
  parameters: { layout: "padded" },
} satisfies Meta<typeof SceneryProductMapTable>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Inventory: Story = {};
