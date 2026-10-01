import { useCallback, useEffect, useRef } from "react";

import { topModal } from "../../../workspace/escapeOverlay";

export function useIslandInteraction({ expanded, onCollapse }: {
  expanded: boolean;
  onCollapse: () => void;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const glyphRef = useRef<HTMLButtonElement>(null);
  const dismissRef = useRef<HTMLButtonElement>(null);
  const restoreFocus = useRef(false);

  const collapse = useCallback((returnToMark = false) => {
    restoreFocus.current = returnToMark;
    onCollapse();
  }, [onCollapse]);

  useEffect(() => {
    if (expanded) {
      dismissRef.current?.focus({ preventScroll: true });
      cardRef.current?.scrollIntoView?.({ block: "nearest", inline: "nearest" });
    } else if (restoreFocus.current) {
      restoreFocus.current = false;
      glyphRef.current?.focus({ preventScroll: true });
    }
  }, [expanded]);

  useEffect(() => {
    if (!expanded) return;
    function onKey(event: KeyboardEvent) {
      const card = cardRef.current;
      if (event.key !== "Escape" || event.defaultPrevented || !card || card.closest("[hidden]")) return;
      if (topModal()) return;
      const target = event.target instanceof Element ? event.target : document.activeElement;
      if (!target || !card.contains(target) || target.closest("[data-esc-overlay]") !== card) return;
      event.preventDefault();
      event.stopPropagation();
      collapse(true);
    }
    function onDocMouseDown(event: MouseEvent) {
      const card = cardRef.current;
      if (topModal()) return;
      if (card && event.target instanceof Node && !card.contains(event.target)) collapse();
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("mousedown", onDocMouseDown);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("mousedown", onDocMouseDown);
    };
  }, [expanded, collapse]);

  return { cardRef, glyphRef, dismissRef, collapse };
}
