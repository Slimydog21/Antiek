import type { ResearchArtifactBlock } from "./api";
import { artifactKindToBlockKind } from "./artifactBlocks";
import type { PaletteDragPayload } from "../modes/CreationStudio/BlockPalette";

export function artifactPalettePayload(
  block: ResearchArtifactBlock,
): PaletteDragPayload {
  return {
    from: "palette",
    block_kind: artifactKindToBlockKind(block.kind),
    block_id: block.node_id,
    label: block.label.slice(0, 120),
  };
}
