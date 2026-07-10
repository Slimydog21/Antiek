export interface HtmlRegionAnchor {
  anchorId: string;
  charStart: number;
  charEnd: number;
  exact: string;
  prefix: string;
  suffix: string;
  sourcePage: number | null;
}

export type HtmlRegionResolution =
  | { status: "resolved"; range: Range; drifted: false }
  | { status: "drift"; range: Range; drifted: true }
  | { status: "unresolved"; reason: "anchor-missing" | "text-missing" | "ambiguous" };

const CONTEXT = 32;

export function findCanonicalAnchor(reader: HTMLElement, anchorId: string): HTMLElement | null {
  for (const candidate of reader.querySelectorAll<HTMLElement>("[id^='antiek-anchor-']")) {
    if (candidate.id === anchorId) return candidate;
  }
  return null;
}

function textNodes(root: Node): Text[] {
  const document = root.ownerDocument ?? (root as Document);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) nodes.push(node as Text);
  return nodes;
}

function boundaryOffset(root: HTMLElement, container: Node, offset: number): number | null {
  if (container !== root && !root.contains(container)) return null;
  const range = root.ownerDocument.createRange();
  range.selectNodeContents(root);
  try {
    range.setEnd(container, offset);
  } catch {
    return null;
  }
  return range.toString().length;
}

function pageFor(node: Node, anchor: HTMLElement): number | null {
  let element = node.nodeType === Node.ELEMENT_NODE ? (node as Element) : node.parentElement;
  while (element && anchor.contains(element)) {
    const raw = element.getAttribute("data-source-page");
    if (raw !== null && /^\d+$/.test(raw) && Number(raw) > 0) return Number(raw);
    if (element === anchor) break;
    element = element.parentElement;
  }
  const raw = anchor.getAttribute("data-source-page");
  return raw !== null && /^\d+$/.test(raw) && Number(raw) > 0 ? Number(raw) : null;
}

export function regionFromRange(reader: HTMLElement, range: Range): HtmlRegionAnchor | null {
  if (range.collapsed || !reader.contains(range.commonAncestorContainer)) return null;
  const startElement = range.startContainer.nodeType === Node.ELEMENT_NODE
    ? range.startContainer as Element
    : range.startContainer.parentElement;
  const anchor = startElement?.closest<HTMLElement>("[id^='antiek-anchor-']");
  if (!anchor || !reader.contains(anchor) || !anchor.contains(range.endContainer)) return null;
  const charStart = boundaryOffset(anchor, range.startContainer, range.startOffset);
  const charEnd = boundaryOffset(anchor, range.endContainer, range.endOffset);
  if (charStart === null || charEnd === null || charEnd <= charStart) return null;
  const text = anchor.textContent ?? "";
  const exact = range.toString();
  if (!exact || text.slice(charStart, charEnd) !== exact) return null;
  return {
    anchorId: anchor.id,
    charStart,
    charEnd,
    exact,
    prefix: text.slice(Math.max(0, charStart - CONTEXT), charStart),
    suffix: text.slice(charEnd, charEnd + CONTEXT),
    sourcePage: pageFor(range.startContainer, anchor),
  };
}

function rangeAt(anchor: HTMLElement, start: number, end: number): Range | null {
  const range = anchor.ownerDocument.createRange();
  let cursor = 0;
  let began = false;
  for (const node of textNodes(anchor)) {
    const next = cursor + node.data.length;
    if (!began && start >= cursor && start <= next) {
      range.setStart(node, start - cursor);
      began = true;
    }
    if (began && end >= cursor && end <= next) {
      range.setEnd(node, end - cursor);
      return range;
    }
    cursor = next;
  }
  return null;
}

export function resolveHtmlRegion(reader: HTMLElement, region: HtmlRegionAnchor): HtmlRegionResolution {
  const candidate = findCanonicalAnchor(reader, region.anchorId);
  if (!candidate) {
    return { status: "unresolved", reason: "anchor-missing" };
  }
  const text = candidate.textContent ?? "";
  if (text.slice(region.charStart, region.charEnd) === region.exact) {
    const range = rangeAt(candidate, region.charStart, region.charEnd);
    return range ? { status: "resolved", range, drifted: false } : { status: "unresolved", reason: "text-missing" };
  }
  const matches: number[] = [];
  for (let at = text.indexOf(region.exact); at >= 0; at = text.indexOf(region.exact, at + 1)) {
    const prefix = text.slice(Math.max(0, at - region.prefix.length), at);
    const suffix = text.slice(at + region.exact.length, at + region.exact.length + region.suffix.length);
    if (prefix === region.prefix && suffix === region.suffix) matches.push(at);
  }
  if (matches.length !== 1) {
    return { status: "unresolved", reason: matches.length ? "ambiguous" : "text-missing" };
  }
  const range = rangeAt(candidate, matches[0], matches[0] + region.exact.length);
  return range ? { status: "drift", range, drifted: true } : { status: "unresolved", reason: "text-missing" };
}
