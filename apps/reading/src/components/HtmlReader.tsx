import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DocumentRegionSelectedPayload } from "../generated/types";
import { findCanonicalAnchor, regionFromRange, resolveHtmlRegion, type HtmlRegionAnchor, type HtmlRegionResolution } from "./reader/htmlRegion";

export interface HtmlReaderSelection {
  investigationId: string;
  documentId: string;
  payload: DocumentRegionSelectedPayload;
  anchor: HtmlRegionAnchor;
}

export interface HtmlReaderProps {
  html: string;
  investigationId: string;
  documentId: string;
  initialAnchorId?: string;
  restoreRegion?: HtmlRegionAnchor;
  onRegionSelected: (selection: HtmlReaderSelection) => void | Promise<void>;
  onRestoreResult?: (result: HtmlRegionResolution) => void;
}

const FORBIDDEN = new Set(["script", "style", "iframe", "object", "embed", "svg", "math", "form", "input", "button", "textarea", "select", "link", "base", "video", "audio", "canvas", "noscript", "template", "picture", "source", "map", "area", "dialog"]);
const URL_ATTRIBUTES = new Set(["src", "href", "srcset", "action", "formaction", "poster", "ping", "xlink:href"]);

export function validateBornAntiekHtml(html: string): string {
  const parsed = new DOMParser().parseFromString(html, "text/html");
  if (parsed.querySelector("parsererror")) throw new Error("Invalid born-Antiek HTML");
  const ids = new Set<string>();
  for (const element of parsed.querySelectorAll("*")) {
    if (element.localName === "html" || element.localName === "head" || element.localName === "body") continue;
    if (element.localName === "title" && element.parentElement === parsed.head) continue;
    if (element.localName === "meta") {
      const name = element.getAttribute("name");
      const charset = element.getAttribute("charset");
      const allowed = charset?.toLowerCase() === "utf-8" || name === "antiek-document-id" || name === "antiek-projection-id";
      if (!allowed || Array.from(element.attributes).some((attribute) => !["name", "content", "charset"].includes(attribute.name.toLowerCase()))) {
        throw new Error("Rejected non-canonical metadata");
      }
      continue;
    }
    if (element.namespaceURI !== "http://www.w3.org/1999/xhtml" || FORBIDDEN.has(element.localName)) {
      throw new Error(`Rejected active or foreign HTML: <${element.localName}>`);
    }
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || name === "style" || URL_ATTRIBUTES.has(name)) {
        throw new Error(`Rejected active HTML attribute: ${attribute.name}`);
      }
    }
    if (element.id) {
      if (!element.id.startsWith("antiek-anchor-") || ids.has(element.id)) throw new Error(`Invalid canonical anchor ID: ${element.id}`);
      ids.add(element.id);
    }
  }
  return parsed.body.innerHTML;
}

export default function HtmlReader({ html, investigationId, documentId, initialAnchorId, restoreRegion, onRegionSelected, onRestoreResult }: HtmlReaderProps) {
  const readerRef = useRef<HTMLDivElement>(null);
  const [textScale, setTextScale] = useState(1);
  const validation = useMemo(() => {
    try {
      return { safeHtml: validateBornAntiekHtml(html), error: null } as const;
    } catch {
      return { safeHtml: null, error: "This document could not be opened because its HTML safety check failed." } as const;
    }
  }, [html]);
  const safeHtml = validation.safeHtml;

  useEffect(() => {
    const reader = readerRef.current;
    if (!reader || safeHtml === null) return;
    if (restoreRegion) {
      const result = resolveHtmlRegion(reader, restoreRegion);
      onRestoreResult?.(result);
      if (result.status !== "unresolved") {
        const target = findCanonicalAnchor(reader, restoreRegion.anchorId);
        target?.scrollIntoView?.({ block: "center" });
      }
      return;
    }
    if (initialAnchorId) {
      const target = findCanonicalAnchor(reader, initialAnchorId);
      target?.scrollIntoView?.({ block: "start" });
    }
  }, [safeHtml, initialAnchorId, restoreRegion, onRestoreResult]);

  const capture = useCallback(() => {
    const reader = readerRef.current;
    const selection = window.getSelection();
    if (!reader || !selection || selection.rangeCount !== 1 || selection.isCollapsed) return;
    const anchor = regionFromRange(reader, selection.getRangeAt(0));
    if (!anchor) return;
    const payload: DocumentRegionSelectedPayload = {
      action_type: "document.region_selected",
      region_id: `${documentId}:${anchor.anchorId}:${anchor.charStart}-${anchor.charEnd}`,
      page: anchor.sourcePage,
      char_start: anchor.charStart,
      char_end: anchor.charEnd,
      text_excerpt: anchor.exact.slice(0, 1000),
    };
    void onRegionSelected({ investigationId, documentId, payload, anchor });
  }, [documentId, investigationId, onRegionSelected]);

  if (safeHtml === null) {
    return <section aria-label="HTML document reader" className="flex h-full items-center justify-center p-6"><p role="alert">{validation.error}</p></section>;
  }

  return <section aria-label="HTML document reader" className="flex h-full flex-col">
    <div role="toolbar" aria-label="Reading controls" className="flex gap-2 border-b p-2">
      <button type="button" aria-label="Decrease text size" onClick={() => setTextScale((value) => Math.max(.75, value - .125))}>A−</button>
      <output aria-live="polite" aria-label="Text size">{Math.round(textScale * 100)}%</output>
      <button type="button" aria-label="Increase text size" onClick={() => setTextScale((value) => Math.min(2, value + .125))}>A+</button>
    </div>
    <div ref={readerRef} tabIndex={0} aria-label="Document content" className="flex-1 overflow-auto p-6 focus:outline focus:outline-2" style={{ fontSize: `${textScale}rem` }} onMouseUp={capture} onKeyUp={capture} dangerouslySetInnerHTML={{ __html: safeHtml }} />
  </section>;
}
