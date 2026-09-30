/**
 * readerEvents.ts — the reader's keymap seam. The dispatcher (entry chunk)
 * fires the contents toggle as a cancelable window event; the reader on
 * screen answers by cancelling it, so with no reader mounted the key is
 * "not mine" and stays the page's.
 */
export const READER_TOC_TOGGLE_EVENT = "antiek:reader:toc-toggle";
