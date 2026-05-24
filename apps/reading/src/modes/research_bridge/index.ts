/**
 * Barrel export for the Antiek Deep Research Bridge frontend kit.
 */

export { ResearchBlock } from "./ResearchBlock";
export type { ResearchBlockProps, ResearchBlockSize } from "./ResearchBlock";

export { BlockShelf } from "./BlockShelf";
export type { BlockShelfProps } from "./BlockShelf";

export { DropTarget } from "./DropTarget";
export type { DropTargetProps } from "./DropTarget";

export {
  beginBlockDrag, readBlockDrop, dragHasBlock, DRAG_MIME, DRAG_TEXT_MIME,
} from "./drag";

export type {
  DragPayload, ExtractedItemPayload, ResearchBlockSummary, ResearchSource,
} from "./types";
export { ALL_SOURCES, SOURCE_VISUAL } from "./types";

export { PromptCard } from "./PromptCard";
export type { PromptCardProps } from "./PromptCard";

export { GapFinderPage } from "./GapFinderPage";
export type { GapFinderPageProps } from "./GapFinderPage";

export { createHttpClient } from "./api_client";
export type {
  ResearchBridgeClient, PasteRequest, PasteResponse, ListPastesResponse,
  ExtractRequest, ExtractResponse, ListItemsResponse, FindGapsRequest,
  FindGapsResponse, GapClusterPayload, GapPromptPayload, GapRunPayload,
  WouldRunPercentageResponse,
} from "./api_client";

export {
  useExtract, useFindGaps, usePasteBack, usePastes, usePostPaste, useSignals,
} from "./hooks";
export type { AsyncState, PasteBackResult, SignalType, UsePastesOptions } from "./hooks";
