import type { Meta, StoryObj } from "@storybook/react";
import { useState } from "react";

import LemonButton from "../../components/lemon/LemonButton";
import ChunkModal from "./ChunkModal";

/**
 * ChunkModal — pops over the trajectory when the operator clicks a chunk
 * citation in MasterMdViewer. Shows the source excerpt + a "view in PDF"
 * link. The modal hits the live chunk API by chunk_id; in Storybook the
 * `null` chunkId branch renders empty, and the populated branch will
 * fetch (or fail) depending on whether the dev backend is reachable.
 */
const meta = {
  title: "Loop 1 / ChunkModal",
  component: ChunkModal,
  parameters: { layout: "fullscreen" },
  tags: ["autodocs"],
} satisfies Meta<typeof ChunkModal>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Closed: Story = {
  args: { chunkId: null, onClose: () => {} },
};

export const OpenForChunk: Story = {
  args: { chunkId: "chunk-storybook-demo", onClose: () => alert("close") },
};

export const Toggleable: Story = {
  render: () => {
    const Inner = () => {
      const [id, setId] = useState<string | null>(null);
      return (
        <div className="p-10">
          <LemonButton onClick={() => setId("chunk-storybook-demo")}>
            Open chunk
          </LemonButton>
          <ChunkModal chunkId={id} onClose={() => setId(null)} />
        </div>
      );
    };
    return <Inner />;
  },
};
