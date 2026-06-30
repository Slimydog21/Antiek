// The single shell-level mount of the always-on ad border (SPR-07 M2).
//
// AppShell renders this ONCE. It derives the two inputs the border needs from
// the router — there is no per-lens fork, no per-route mount:
//
//   * lens — the active product workflow, from the pathname via the existing
//     workflowTaxonomy source of truth (workflowForPath). The `shared`
//     operator/governance bucket is not one of the four monetizable lenses, so
//     it maps to "research" (the default surface "/" already resolves to);
//     the border is still always on there, the telemetry is just stamped with
//     the default lens. The contract only admits the four VALID_LENSES.
//   * windowId — a stable id for the CURRENT lens session. It changes when the
//     lens changes, so each lens session is one WindowFrameBatch (second_index
//     restarts at 0 inside the new window). A fresh random suffix per lens
//     entry keeps two visits to the same lens from colliding in the trace.
//
// Splitting this off AppShell keeps AppShell's render free of ad-border state
// and lets the border be unit-tested without the whole shell (the shell test
// mocks this to null, exactly as it mocks the other heavy children).

import { useEffect, useMemo, useRef, useState } from "react";
import { useLocation } from "react-router-dom";

import { workflowForPath } from "../../shell/workflowTaxonomy";
import {
  READ_POSITION_EVENT,
  readStoredPosition,
} from "../../modes/Reading/usePosition";
import { AdBorder } from "./AdBorder";
import type { Lens } from "./frameContract";

/** Map a workflow to a telemetry lens. The four product workflows ARE the four
 *  lenses; the `shared` bucket (settings, operator, billing …) has no lens of
 *  its own and is stamped "research", the default surface. */
function lensForPath(pathname: string): Lens {
  const wf = workflowForPath(pathname);
  return wf === "shared" ? "research" : wf;
}

function pageFromRouteOrStorage(documentId: string, search: string): number {
  const raw = new URLSearchParams(search).get("page");
  if (raw === null) return readStoredPosition(documentId);
  const parsed = Number.parseInt(raw, 10);
  return Number.isFinite(parsed) && parsed >= 0 ? parsed : readStoredPosition(documentId);
}

export function AdBorderMount() {
  const { pathname, search } = useLocation();
  const lens = lensForPath(pathname);
  const readerDocumentId = useMemo(() => {
    if (pathname === "/read/meta-reading" || pathname.startsWith("/read/meta-reading/")) {
      return null;
    }
    const match = pathname.match(/^\/read\/([^/?#]+)/);
    return match ? decodeURIComponent(match[1]) : null;
  }, [pathname]);
  const routePageIndex = useMemo(
    () => (readerDocumentId ? pageFromRouteOrStorage(readerDocumentId, search) : null),
    [readerDocumentId, search],
  );
  const [trackedReaderPage, setTrackedReaderPage] = useState<{
    documentId: string;
    pageIndex: number;
  } | null>(() =>
    readerDocumentId && routePageIndex !== null
      ? { documentId: readerDocumentId, pageIndex: routePageIndex }
      : null,
  );

  useEffect(() => {
    if (!readerDocumentId) {
      setTrackedReaderPage(null);
      return;
    }
    setTrackedReaderPage({ documentId: readerDocumentId, pageIndex: routePageIndex ?? 0 });
  }, [readerDocumentId, routePageIndex]);

  useEffect(() => {
    if (!readerDocumentId) return;
    const onPosition = (event: Event) => {
      const detail = (event as CustomEvent<{ documentId?: string; pageIndex?: number }>).detail;
      if (detail?.documentId !== readerDocumentId) return;
      const next = detail.pageIndex;
      if (typeof next === "number" && Number.isFinite(next) && next >= 0) {
        setTrackedReaderPage({ documentId: readerDocumentId, pageIndex: next });
      }
    };
    window.addEventListener(READ_POSITION_EVENT, onPosition);
    return () => window.removeEventListener(READ_POSITION_EVENT, onPosition);
  }, [readerDocumentId]);
  const readerPageIndex =
    readerDocumentId && trackedReaderPage?.documentId === readerDocumentId
      ? trackedReaderPage.pageIndex
      : routePageIndex;

  // A new window each time the lens changes. The random suffix is allocated
  // once per lens value (useMemo keyed on lens) so re-renders within a lens
  // session keep the same window_id — the batch's trace anchor is stable for
  // the life of the session and only rolls over on a real lens switch.
  const sessionRef = useRef(Math.random().toString(36).slice(2, 10));
  const windowId = useMemo(
    () => `win:${lens}:${sessionRef.current}:${Math.random().toString(36).slice(2, 8)}`,
    [lens],
  );

  return (
    <AdBorder
      lens={lens}
      documentId={readerDocumentId}
      pageIndex={readerPageIndex}
      windowId={windowId}
    />
  );
}

export default AdBorderMount;
