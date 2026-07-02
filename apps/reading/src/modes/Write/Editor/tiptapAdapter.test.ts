import { describe, expect, it } from "vitest";
import type { JSONContent } from "@tiptap/core";

import { docToBlocks } from "./tiptapAdapter";

describe("docToBlocks", () => {
  it("keeps stable prose block ids and excludes citation atoms from plain text", () => {
    const doc: JSONContent = {
      type: "doc",
      content: [
        {
          type: "paragraph",
          attrs: { blockId: "blk-stable" },
          content: [
            { type: "text", text: "Mechanism first " },
            {
              type: "citation",
              attrs: { node_id: "node-1", label: "source" },
            },
            { type: "text", text: "then conclusion." },
          ],
        },
      ],
    };

    expect(docToBlocks(doc)).toEqual([
      {
        blockId: "blk-stable",
        kind: "prose",
        text: "Mechanism first then conclusion.",
      },
    ]);
  });

  it("maps lego blocks through outline provenance without copying content", () => {
    const doc: JSONContent = {
      type: "doc",
      content: [
        {
          type: "legoBlock",
          attrs: {
            outline_block_id: "oblk-7",
            node_id: "node-9",
            text: "Capital intensity rises with scale.",
          },
        },
      ],
    };

    expect(docToBlocks(doc)).toEqual([
      {
        blockId: "oblk-7",
        kind: "lego",
        nodeId: "node-9",
        outlineBlockId: "oblk-7",
        text: "Capital intensity rises with scale.",
      },
    ]);
  });

  it("assigns a generated block id when TipTap has not stamped a prose block yet", () => {
    const [block] = docToBlocks({
      type: "doc",
      content: [{ type: "paragraph", content: [{ type: "text", text: "Draft." }] }],
    });

    expect(block.kind).toBe("prose");
    expect(block.blockId.startsWith("blk-")).toBe(true);
    expect(block.text).toBe("Draft.");
  });
});
