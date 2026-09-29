import type { Meta, StoryObj } from "@storybook/react";

import type { SectionResponse } from "../lib/api";
import type { OutlineBlockView } from "../modes/Write/writeApi";
import { BlockCard, DropRefusedNote } from "./WriteOutlinePane";

/**
 * WriteOutlinePane's states that need no server: a block card with no
 * sources yet (the session-state copy), a block card with sources, and the
 * refusal a drop that is not a source document gets. Day and night.
 */
const SECTION: SectionResponse = {
  section_id: "s-1",
  deliverable_id: "d-1",
  parent_section_id: null,
  section_index: 1,
  title: "What Lack measured",
  prose_text: null,
  prose_provenance: null,
  block_count: 2,
};

const BLOCK: OutlineBlockView = {
  outline_block_id: "b-1",
  section_id: "s-1",
  block_kind: "insight",
  provenance_kind: "graph_node",
  node_id: "n-1",
  content: "Beak depth tracked seed hardness across the 1977 drought.",
  node_label: null,
  block_index: 0,
  is_user_originated: false,
};

function OutlineState({ state }: { state: "no-sources" | "sources" | "refused" }) {
  return (
    <div className="p-4" style={{ background: "var(--bg-page)" }}>
      <section
        aria-label="Outline"
        className="flex w-[320px] flex-col overflow-hidden rounded-lg border border-hairline bg-ice-1 dark:bg-charcoal-1"
      >
        {state === "refused" ? <DropRefusedNote onDismiss={() => {}} /> : null}
        <BlockCard
          section={SECTION}
          block={BLOCK}
          assigned={
            state === "sources"
              ? [
                  { document_id: "doc-1", document_title: "The Beak of the Finch" },
                  { document_id: "doc-2", document_title: "Darwin's Finches (Lack, 1947)" },
                ]
              : []
          }
          onUnassign={() => {}}
        />
      </section>
    </div>
  );
}

const meta = {
  title: "Workspace/WriteOutlinePane",
  component: OutlineState,
  args: { state: "no-sources" },
} satisfies Meta<typeof OutlineState>;
export default meta;

type Story = StoryObj<typeof meta>;

export const NoSourcesDay: Story = { args: { state: "no-sources" }, globals: { theme: "light" } };
export const NoSourcesNight: Story = { args: { state: "no-sources" }, globals: { theme: "dark" } };
export const SourcesDay: Story = { args: { state: "sources" }, globals: { theme: "light" } };
export const SourcesNight: Story = { args: { state: "sources" }, globals: { theme: "dark" } };
export const DropRefusedDay: Story = { args: { state: "refused" }, globals: { theme: "light" } };
export const DropRefusedNight: Story = { args: { state: "refused" }, globals: { theme: "dark" } };
