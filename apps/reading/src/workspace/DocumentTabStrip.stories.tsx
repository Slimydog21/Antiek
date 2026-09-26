import type { Meta, StoryObj } from "@storybook/react";

import {
  StoryStrip,
  depthFixture,
  emptyFixture,
  siblingsFixture,
  writeSectionFixture,
} from "./documentTabStories";

/**
 * DocumentTabStrip — the cockpit's left document tabs (DESIGN-MODEL §2a):
 * the path header, the sibling strip with its ↳n chip, and the tree panel.
 * Each depth the operator will actually reach, in day and night: 1 (a book
 * on its own), 4 (the path shows in full), 12 and 40 (the path compresses in
 * the middle; the panel caps its indent at six levels and badges depth), and
 * 174 siblings (the herdr workspace that made search, not scanning, the
 * way in). Every state has a story: loading, error, empty.
 *
 * The stories render the presentational DocumentTabStripView over trees built
 * by the real model, so a story can never show a tree the model refuses.
 */
const meta = {
  title: "Workspace/DocumentTabStrip",
  component: StoryStrip,
  args: { fixture: depthFixture(1) },
} satisfies Meta<typeof StoryStrip>;
export default meta;

type Story = StoryObj<typeof meta>;

const day = { theme: "light" } as const;
const night = { theme: "dark" } as const;

export const Depth1Day: Story = { args: { fixture: depthFixture(1) }, globals: day };
export const Depth1Night: Story = { args: { fixture: depthFixture(1) }, globals: night };

export const Depth4Day: Story = { args: { fixture: depthFixture(4) }, globals: day };
export const Depth4Night: Story = { args: { fixture: depthFixture(4) }, globals: night };

export const Depth12Day: Story = { args: { fixture: depthFixture(12) }, globals: day };
export const Depth12Night: Story = { args: { fixture: depthFixture(12) }, globals: night };

export const Depth40Day: Story = { args: { fixture: depthFixture(40) }, globals: day };
export const Depth40Night: Story = { args: { fixture: depthFixture(40) }, globals: night };

export const Siblings174Day: Story = { args: { fixture: siblingsFixture(174) }, globals: day };
export const Siblings174Night: Story = { args: { fixture: siblingsFixture(174) }, globals: night };

/** The tree panel at depth 12: every row under its own parent. */
export const TreePanelDepth12Day: Story = {
  args: { fixture: depthFixture(12), panelOpen: true },
  globals: day,
};
/** Depth 40: the indent stops at six levels; deeper rows carry dN. */
export const TreePanelDepth40Night: Story = {
  args: { fixture: depthFixture(40), panelOpen: true },
  globals: night,
};
/** 174 siblings in the panel: a virtualised window, every row reachable. */
export const TreePanelSiblings174Day: Story = {
  args: { fixture: siblingsFixture(174), panelOpen: true },
  globals: day,
};

export const LoadingDay: Story = { args: { fixture: depthFixture(1), status: "loading" }, globals: day };
export const LoadingNight: Story = { args: { fixture: depthFixture(1), status: "loading" }, globals: night };
export const ErrorDay: Story = { args: { fixture: depthFixture(1), status: "error" }, globals: day };
export const ErrorNight: Story = { args: { fixture: depthFixture(1), status: "error" }, globals: night };
export const EmptyPanelDay: Story = { args: { fixture: emptyFixture(), panelOpen: true }, globals: day };
export const EmptyPanelNight: Story = { args: { fixture: emptyFixture(), panelOpen: true }, globals: night };

/** Writing: a section tab is active. It is labelled by its heading and
 *  scopes the piece in place, so there is no "opens as window" note. */
export const WriteSectionDay: Story = { args: { fixture: writeSectionFixture() }, globals: day };
export const WriteSectionNight: Story = { args: { fixture: writeSectionFixture() }, globals: night };
