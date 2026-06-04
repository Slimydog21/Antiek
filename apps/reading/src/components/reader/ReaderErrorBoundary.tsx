import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";

/**
 * ReaderErrorBoundary — makes the reader's "never blank, never a throw" promise
 * TRUE (Reader SPR-03, D1).
 *
 * The rich `<Reader>` deserializes a SERVABLE doc's `structured_blocks` and
 * renders it through the typed-block dispatcher. The caller's `structuredDoc`
 * gate guards the doc's SHAPE (parse + a known-`type` block array), but a span-
 * or field-level skew that slips past it (a `paragraph` missing `spans`, a
 * `math` missing `tex`, a future inline-span the build predates) would reach
 * `InlineSpans` / `renderMath` and THROW during render. With NO boundary, a
 * render throw unmounts the whole reading surface to a blank screen — the exact
 * opposite of the promise.
 *
 * This boundary catches any render throw BELOW it and degrades to `fallback`
 * (the caller passes the legacy `<ReadingColumn>` for the SAME page, carrying
 * the SAME `articleRef` selection scope + the SAME §9.0 `data-akb-asset-id`
 * attribution). The reading surface stays up; only the rich body is swapped for
 * the legacy text body. It NEVER degrades to blank.
 *
 * `resetKey` (the open document id) lets a new book re-attempt the rich path:
 * when it changes, the boundary clears its caught-error state so a healthy doc
 * after a broken one renders rich again, instead of being stuck on the legacy
 * fallback for the session.
 */

export interface ReaderErrorBoundaryProps {
  /** The rich children to attempt (the typed-block `<Reader>`). */
  children: ReactNode;
  /** Rendered instead when a child render throws — the legacy `<ReadingColumn>`
   *  for the same page (same ref, same §9.0 attribution). */
  fallback: ReactNode;
  /** When this changes (the open document id), retry the rich path for the new
   *  document instead of staying degraded from a previous one's throw. */
  resetKey?: string;
  /** Optional hook so a host/test can observe a degrade (telemetry, asserts). */
  onError?: (error: Error, info: ErrorInfo) => void;
}

interface ReaderErrorBoundaryState {
  caught: boolean;
}

export default class ReaderErrorBoundary extends Component<
  ReaderErrorBoundaryProps,
  ReaderErrorBoundaryState
> {
  state: ReaderErrorBoundaryState = { caught: false };

  static getDerivedStateFromError(): ReaderErrorBoundaryState {
    return { caught: true };
  }

  componentDidUpdate(prev: ReaderErrorBoundaryProps): void {
    // A new document — clear the caught state so the rich path is re-attempted
    // for it (a broken doc must not poison every later doc this session).
    if (this.state.caught && prev.resetKey !== this.props.resetKey) {
      this.setState({ caught: false });
    }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    if (typeof console !== "undefined" && console.warn) {
      console.warn(
        "[Reader] rich render threw; degrading to the legacy reading body.",
        error,
      );
    }
    this.props.onError?.(error, info);
  }

  render(): ReactNode {
    return this.state.caught ? this.props.fallback : this.props.children;
  }
}
