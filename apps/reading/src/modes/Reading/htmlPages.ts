import type { TocItem } from "../../api/books";
import type { PageWindow } from "./paginate";
import { windowForTocPage } from "./paginate";

/** Serialized display fragments have no text-coordinate authority. */
export interface HtmlPageWindow {
  kind: "html";
  pageIndex: number;
  pageNumber: number;
  text: string;
  headingTitle: string | null;
  fragmentIds: readonly string[];
}

export type ReaderPageWindow = PageWindow | HtmlPageWindow;
export type HtmlPagination =
  | { kind: "ready"; pages: HtmlPageWindow[] }
  | { kind: "unsafe"; pages: [] };

const TAGS = new Set(
  "h1 h2 h3 h4 h5 h6 p br hr ul ol li dl dt dd blockquote pre code em strong i b u s sub sup small mark a img figure figcaption table caption thead tbody tfoot tr th td section article div span".split(" "),
);
const GLOBAL_ATTRIBUTES = new Set(["id", "title", "lang", "dir"]);
const ATTRIBUTES: Readonly<Record<string, ReadonlySet<string>>> = {
  a: new Set(["href", "target", "rel"]),
  img: new Set(["alt", "width", "height"]),
  ol: new Set(["start"]),
  th: new Set(["colspan", "rowspan", "scope"]),
  td: new Set(["colspan", "rowspan"]),
};

function passive(root: HTMLElement): boolean {
  for (const element of root.querySelectorAll("*")) {
    const tag = element.localName;
    if (element.namespaceURI !== "http://www.w3.org/1999/xhtml" || !TAGS.has(tag)) return false;
    for (const attribute of element.attributes) {
      if (!GLOBAL_ATTRIBUTES.has(attribute.name) && !ATTRIBUTES[tag]?.has(attribute.name)) return false;
      if (attribute.name === "href") {
        // Mirror the existing server's passive URL policy. Never repair or
        // relabel an unsafe served body as sanitized HTML.
        const href = attribute.value.replace(/[\u0000-\u001f\u007f]/g, "").trim();
        try {
          const url = new URL(href, "https://reader.invalid/");
          if (url.protocol !== "https:" && url.protocol !== "http:") return false;
        } catch {
          return false;
        }
      }
    }
  }
  return true;
}

export function headingTitle(text: string): string {
  return text.replace(/[\t\n\r\f ]+/g, " ").trim();
}

/** Parse in an inert div context, like the mounted reader body. A template's
 * document prevents resource loading during validation. Server sanitization
 * remains the admission authority; this check refuses active markup without
 * mutating the source or manufacturing a projection. */
export function paginateHtml(html: string, splitHeadings = true): HtmlPagination {
  if (!html.trim()) return { kind: "ready", pages: [] };
  const template = document.createElement("template");
  const root = template.content.ownerDocument.createElement("div");
  root.innerHTML = html;
  if (!passive(root)) return { kind: "unsafe", pages: [] };
  const headings = splitHeadings
    ? Array.from(root.querySelectorAll("h1, h2, h3, h4, h5, h6"))
      .filter((heading) => headingTitle(heading.textContent ?? ""))
    : [];
  const idsByPage = Array.from({ length: Math.max(1, headings.length) }, () => new Set<string>());
  const idCounts = new Map<string, number>();
  for (const element of root.querySelectorAll("[id]")) {
    let index = 0;
    for (let i = 1; i < headings.length; i += 1) {
      if (headings[i] === element || (headings[i].compareDocumentPosition(element) & Node.DOCUMENT_POSITION_FOLLOWING)) {
        index = i;
      }
    }
    if (element.id) {
      idsByPage[index].add(element.id);
      idCounts.set(element.id, (idCounts.get(element.id) ?? 0) + 1);
    }
  }
  for (const ids of idsByPage) {
    for (const id of ids) if (idCounts.get(id) !== 1) ids.delete(id);
  }
  if (headings.length === 0) {
    return { kind: "ready", pages: [{
      kind: "html", pageIndex: 0, pageNumber: 1, text: html,
      headingTitle: null, fragmentIds: [...idsByPage[0]],
    }] };
  }
  const pages = headings.map((heading, index): HtmlPageWindow => {
    const range = root.ownerDocument.createRange();
    if (index === 0) range.setStart(root, 0);
    else range.setStartBefore(heading);
    if (index + 1 < headings.length) range.setEndBefore(headings[index + 1]);
    else range.setEnd(root, root.childNodes.length);
    const fragment = root.ownerDocument.createElement("div");
    fragment.append(range.cloneContents());
    // Cloned ancestors do not create another fragment destination.
    for (const element of fragment.querySelectorAll("[id]")) {
      if (!idsByPage[index].has(element.id)) element.removeAttribute("id");
    }
    return {
      kind: "html", pageIndex: index, pageNumber: index + 1,
      text: fragment.innerHTML, headingTitle: headingTitle(heading.textContent ?? ""),
      fragmentIds: [...idsByPage[index]],
    };
  });
  return { kind: "ready", pages };
}

export function readerToc(
  toc: readonly TocItem[], pages: readonly ReaderPageWindow[], readable: boolean, htmlSections: boolean,
): TocItem[] {
  return toc.map((entry) => {
    const index = readable ? windowForTocPage(pages, entry.page_index) : null;
    const page = index === null ? undefined : pages[index];
    const matches = page && (page.kind === "text" || (
      htmlSections && page.headingTitle === headingTitle(entry.title)
    ));
    return { ...entry, page_index: matches ? entry.page_index : null };
  });
}
