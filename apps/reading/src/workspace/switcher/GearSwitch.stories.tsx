import type { Meta, StoryObj } from "@storybook/react";

import { composePreBackendTree } from "../contracts/adapters/preBackend";
import { fixtureInputs, fixtureInputsWithMembers } from "../contracts/fixtures.test.helpers";
import { EMPTY_TREE } from "../contracts/treeStore";
import { GearSwitchView } from "./GearSwitch";
import { openUi, type SwitcherUi } from "./switcherKeys";
import { deriveSwitcher, type SwitcherModel } from "./switcherModel";

/**
 * GearSwitch — SPR-04 M2: the geared switch, closed (the path chip) and
 * open at each gear, in day and night, over models the REAL adapter and
 * the REAL derivation produced (a story can never show gears the model
 * refuses). Static: the stories render GearSwitchView with a fixed ui.
 */
const tree = composePreBackendTree(fixtureInputsWithMembers());
const bare = composePreBackendTree(fixtureInputs({ investigations: [], companionTabs: [] }));
const registry = composePreBackendTree(fixtureInputs());

const at = (model: SwitcherModel, gear: 1 | 2 | 3, cursor: string | null = null): SwitcherUi =>
  ({ ...openUi(model), gear, cursor: cursor ?? model.strips[gear - 1].tabs.find((t) => t.selected)?.key ?? model.strips[gear - 1].tabs[0]?.key ?? null });

const gear1 = deriveSwitcher(tree, { projectId: "default" });
const gear2 = deriveSwitcher(tree, { projectId: "default", subProjectId: "inv-root" });
const gear3 = deriveSwitcher(tree, { projectId: "default", subProjectId: "inv-root", agentId: "inv-child" });
const notLinked = deriveSwitcher(registry, { projectId: "p2" });
const noneListed = deriveSwitcher(bare, { projectId: "default" });
const stale = deriveSwitcher(tree, { projectId: "ghost" });
const unfed = deriveSwitcher(EMPTY_TREE, { projectId: "default" });

const meta = {
  title: "Workspace/GearSwitch",
  component: GearSwitchView,
  args: { model: gear1, ui: null },
  decorators: [(Story) => <div className="p-6 pb-64"><Story /></div>],
} satisfies Meta<typeof GearSwitchView>;
export default meta;

type Story = StoryObj<typeof meta>;
const day = { theme: "light" } as const;
const night = { theme: "dark" } as const;

export const ClosedDay: Story = { args: { model: gear3, ui: null }, globals: day };
export const ClosedNight: Story = { args: { model: gear3, ui: null }, globals: night };

export const Gear1Day: Story = { args: { model: gear1, ui: at(gear1, 1) }, globals: day };
export const Gear1Night: Story = { args: { model: gear1, ui: at(gear1, 1) }, globals: night };

export const Gear2Day: Story = { args: { model: gear2, ui: at(gear2, 2) }, globals: day };
export const Gear2Night: Story = { args: { model: gear2, ui: at(gear2, 2) }, globals: night };

export const Gear3Day: Story = { args: { model: gear3, ui: at(gear3, 3, "agent:inv-child") }, globals: day };
export const Gear3Night: Story = { args: { model: gear3, ui: at(gear3, 3, "agent:inv-child") }, globals: night };

/** The notch, held: the dialog one shadow step down. */
export const NotchDay: Story = { args: { model: gear2, ui: at(gear2, 2), notchOn: true }, globals: day };

export const NotLinkedDay: Story = { args: { model: notLinked, ui: at(notLinked, 2) }, globals: day };
export const NotLinkedNight: Story = { args: { model: notLinked, ui: at(notLinked, 2) }, globals: night };

export const NoneListedDay: Story = { args: { model: noneListed, ui: at(noneListed, 2) }, globals: day };
export const NoneListedNight: Story = { args: { model: noneListed, ui: at(noneListed, 2) }, globals: night };

export const StaleDay: Story = { args: { model: stale, ui: at(stale, 1) }, globals: day };
export const StaleNight: Story = { args: { model: stale, ui: at(stale, 1) }, globals: night };

export const UnfedDay: Story = { args: { model: unfed, ui: null }, globals: day };
export const UnfedNight: Story = { args: { model: unfed, ui: null }, globals: night };

/** The zen slot's click-only chip. */
export const ZenChipDay: Story = { args: { model: gear3, ui: null, surface: "zen" }, globals: day };
