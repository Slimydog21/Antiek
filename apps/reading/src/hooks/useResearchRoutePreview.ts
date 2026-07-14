import { useCallback, useEffect, useRef, useState } from "react";

import {
  previewResearchRoutes,
  type ResearchRoutePreview,
} from "../lib/api";

type PreviewState =
  | { status: "idle" | "loading"; preview: null; error: null }
  | { status: "ready"; preview: ResearchRoutePreview; error: null }
  | { status: "error"; preview: null; error: string };

const PREVIEW_DEBOUNCE_MS = 300;

/** Debounced, abortable preview. A sequence guard also defeats responses that
 * race after an AbortSignal (some test/fetch implementations ignore abort). */
export function useResearchRoutePreview(question: string): PreviewState & {
  retry: () => void;
} {
  const [state, setState] = useState<PreviewState>({
    status: "idle",
    preview: null,
    error: null,
  });
  const [retryToken, setRetryToken] = useState(0);
  const sequence = useRef(0);
  const retry = useCallback(() => setRetryToken((value) => value + 1), []);

  useEffect(() => {
    const trimmed = question.trim();
    const current = ++sequence.current;
    if (trimmed.length < 3) {
      setState({ status: "idle", preview: null, error: null });
      return;
    }
    const controller = new AbortController();
    setState({ status: "loading", preview: null, error: null });
    const timer = window.setTimeout(() => {
      void previewResearchRoutes(trimmed, controller.signal).then(
        (preview) => {
          if (current === sequence.current) {
            setState({ status: "ready", preview, error: null });
          }
        },
        (error: unknown) => {
          if (controller.signal.aborted || current !== sequence.current) return;
          setState({
            status: "error",
            preview: null,
            error: error instanceof Error ? error.message : "Preview unavailable",
          });
        },
      );
    }, PREVIEW_DEBOUNCE_MS);
    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [question, retryToken]);

  return { ...state, retry };
}
