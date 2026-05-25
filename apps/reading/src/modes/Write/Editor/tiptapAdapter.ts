/**
 * Bridge between a live TipTap document and the pure `EditorBlock[]`
 * abstraction the locator + edit-capture cores operate on (specs/write/
 * SPR-04).
 *
 * - `BlockId` is a global attribute that stamps a stable `blockId` onto
 *   every top-level block (paragraph, heading) so locators survive edits
 *   (the same role `outline_block_id` plays for lego blocks). Ids are
 *   assigned lazily in `docToBlocks` when missing, and an `appendTransaction`
 *   in the editor persists them.
 * - `docToBlocks` flattens the TipTap JSON into `EditorBlock[]` for diffing.
 */

import { Extension } from "@tiptap/core";
import type { JSONContent } from "@tiptap/core";

import type { EditorBlock } from "./locator";
import { newBlockId } from "./locator";

/** Global attribute: a stable `blockId` on prose block types. */
export const BlockId = Extension.create({
  name: "blockId",
  addGlobalAttributes() {
    return [
      {
        types: ["paragraph", "heading", "blockquote"],
        attributes: {
          blockId: {
            default: null,
            parseHTML: (el: HTMLElement) => el.getAttribute("data-block-id"),
            renderHTML: (attrs: Record<string, unknown>) =>
              attrs.blockId != null ? { "data-block-id": String(attrs.blockId) } : {},
          },
        },
      },
    ];
  },
});

/** Concatenate the plain text of a TipTap node's inline content,
 * skipping atom nodes like citations (their text is not prose). */
function inlineText(content: JSONContent[] | undefined): string {
  if (!content) return "";
  let out = "";
  for (const child of content) {
    if (child.type === "text" && typeof child.text === "string") {
      out += child.text;
    }
  }
  return out.trim();
}

/**
 * Flatten a TipTap doc (JSONContent) into the `EditorBlock[]` abstraction.
 * Prose blocks get/keep a stable `blockId`; lego blocks surface their
 * `outline_block_id` as the blockId and carry their node reference.
 */
export function docToBlocks(doc: JSONContent): EditorBlock[] {
  const top = doc.content ?? [];
  const blocks: EditorBlock[] = [];
  for (const n of top) {
    if (n.type === "legoBlock") {
      const attrs = n.attrs ?? {};
      blocks.push({
        blockId: (attrs.outline_block_id as string | null) ?? newBlockId(),
        text: (attrs.text as string | null) ?? "",
        kind: "lego",
        nodeId: (attrs.node_id as string | null) ?? null,
        outlineBlockId: (attrs.outline_block_id as string | null) ?? null,
      });
    } else {
      const attrs = n.attrs ?? {};
      blocks.push({
        blockId: (attrs.blockId as string | null) ?? newBlockId(),
        text: inlineText(n.content),
        kind: "prose",
      });
    }
  }
  return blocks;
}
