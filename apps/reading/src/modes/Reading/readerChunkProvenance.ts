function chunkRegion(node: Node, scope: HTMLElement): HTMLElement | null {
  const element = node instanceof Element ? node : node.parentElement;
  const region = element?.closest<HTMLElement>("[data-akb-chunk-id]") ?? null;
  return region && scope.contains(region) ? region : null;
}

/** Resolve a selection only when both boundaries belong to the same
 * authoritative reader chunk. A cross-chunk range remains asset-level. */
export function readerChunkIdForRange(
  scope: HTMLElement,
  range: Range,
): string | null {
  const start = chunkRegion(range.startContainer, scope)?.dataset.akbChunkId;
  const end = chunkRegion(range.endContainer, scope)?.dataset.akbChunkId;
  return start && start === end ? start : null;
}
