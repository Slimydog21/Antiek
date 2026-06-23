import type { BlockKind } from "./api";

/** Map ANT-AHT block kind to Write palette / place_block kind. */
export function artifactKindToBlockKind(kind: string): BlockKind {
  if (kind === "insight") return "insight";
  if (kind === "question") return "open_question";
  return "claim";
}