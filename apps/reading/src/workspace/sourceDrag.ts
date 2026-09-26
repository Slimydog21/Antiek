/**
 * The drag MIME that carries a source document from the Write repository to
 * the outline pane's assign-source drop. Kept apart from WriteOutlinePane so
 * BlockRepository can set it without pulling the (lazy) pane into its chunk.
 */
export const SOURCE_DOCUMENT_MIME = "application/x-antiek-source-document";
