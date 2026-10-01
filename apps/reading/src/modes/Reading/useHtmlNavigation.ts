import { useCallback, useEffect, useRef } from "react";
import type { RefObject } from "react";
import { toast } from "../../components/lemon/LemonToast";
import { headingTitle, type ReaderPageWindow } from "./htmlPages";
import { windowForTocPage } from "./paginate";

type PendingDestination = {
  documentId: string;
  pages: readonly ReaderPageWindow[];
  index: number;
  fragmentId: string | null;
};

export function useHtmlNavigation({
  articleRef, documentId, pages, pageIndex, setPageIndex, loading,
}: {
  articleRef: RefObject<HTMLElement>;
  documentId: string;
  pages: readonly ReaderPageWindow[];
  pageIndex: number;
  setPageIndex: (index: number) => void;
  loading: boolean;
}): (index: number) => void {
  const pendingRef = useRef<PendingDestination | null>(null);

  const focusPending = useCallback(() => {
    const pending = pendingRef.current;
    if (!pending) return;
    if (pending.documentId !== documentId || pending.pages !== pages) {
      pendingRef.current = null;
      return;
    }
    if (pending.index !== pageIndex) return;
    pendingRef.current = null;
    const article = articleRef.current;
    if (!article) return;
    const page = pages[pageIndex];
    const target = pending.fragmentId === null
      ? Array.from(article.querySelectorAll<HTMLElement>("[data-antiek-html-body] :is(h1,h2,h3,h4,h5,h6)"))
        .find((heading) => page?.kind === "html" && headingTitle(heading.textContent ?? "") === page.headingTitle) ?? article
      : Array.from(article.querySelectorAll<HTMLElement>("[data-antiek-html-body] [id]"))
        .find((element) => element.id === pending.fragmentId);
    if (!target) {
      toast.warn("This link's destination is unavailable in this document.");
      return;
    }
    if (target.tabIndex < 0) target.tabIndex = -1;
    target.focus({ preventScroll: true });
    target.scrollIntoView?.({ block: "start" });
  }, [articleRef, documentId, pageIndex, pages]);

  useEffect(focusPending, [focusPending]);

  const navigate = useCallback((index: number) => {
    const destination = windowForTocPage(pages, index);
    if (destination === null) return;
    if (pages[destination].kind === "html") {
      pendingRef.current = { documentId, pages, index: destination, fragmentId: null };
    }
    setPageIndex(destination);
    if (destination === pageIndex) focusPending();
  }, [documentId, focusPending, pageIndex, pages, setPageIndex]);

  useEffect(() => {
    const article = articleRef.current;
    if (!article || pages[pageIndex]?.kind !== "html") return;
    const onClick = (event: MouseEvent) => {
      if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      if (!(event.target instanceof Element)) return;
      const link = event.target.closest("a[href]");
      if (!link || !article.contains(link)) return;
      const target = link.getAttribute("target");
      if (target && target.toLowerCase() !== "_self") return;
      const href = link.getAttribute("href");
      if (!href?.startsWith("#")) return;
      event.preventDefault();
      let id: string;
      try { id = decodeURIComponent(href.slice(1)); }
      catch {
        toast.warn("This link's destination is unavailable in this document.");
        return;
      }
      const destinations = pages.filter((page) => page.kind === "html" && page.fragmentIds.includes(id));
      // Duplicate IDs, including repeats within one fragment, are ambiguous.
      const destination = destinations.length === 1 ? destinations[0] : undefined;
      if (!destination) {
        toast.warn("This link's destination is unavailable in this document.");
        return;
      }
      pendingRef.current = { documentId, pages, index: destination.pageIndex, fragmentId: id };
      setPageIndex(destination.pageIndex);
      if (destination.pageIndex === pageIndex) focusPending();
    };
    article.addEventListener("click", onClick);
    return () => article.removeEventListener("click", onClick);
  }, [articleRef, documentId, focusPending, loading, pageIndex, pages, setPageIndex]);

  return navigate;
}
