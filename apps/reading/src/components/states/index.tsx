import { useState } from "react";
import type { ReactNode } from "react";

import BrainMascot from "../../brand/BrainMascot";
import LemonButton from "../lemon/LemonButton";
import "./states.css";

/**
 * The shared loading, empty and error states (design spec §5, audit M9).
 *
 * One vocabulary for "not ready yet", "nothing here yet" and "that failed",
 * replacing ~60 loading strings, ~50 empty recipes and four error treatments:
 *
 *   LoadingState  names the thing that is opening and draws a skeleton of its
 *                 real geometry (list rows or prose lines).
 *   EmptyState    is neutral (never role=alert, never danger red), carries the
 *                 empty mascot pose, and invites the first action.
 *   ErrorState    says what failed and what is safe, offers ONE primary
 *                 "Try again", and keeps the raw technical message (e.g.
 *                 "Failed to fetch", "HTTP 500") off the screen: it is
 *                 reachable through "Copy error details" for a bug report.
 *
 * `variant="page"` fills and centres in its container (a whole surface that
 * could not load); `variant="inline"` is a flat bounded block in the flow.
 * Styles live in states.css so the primitives add almost no entry JS.
 */
type Variant = "page" | "inline";

export function LoadingState({
  label,
  shape = "list",
  rows = 3,
  variant = "page",
}: {
  /** What is opening, in the reader's words: "Opening the library". */
  label: string;
  /** The geometry being loaded: list rows, or the lines of a page. */
  shape?: "list" | "page";
  rows?: number;
  variant?: Variant;
}) {
  const bars = shape === "page" ? 7 : rows;
  return (
    <div role="status" aria-live="polite" className={variant === "page" ? "st st-page" : "st"}>
      <p className="st-body">{label}…</p>
      <div aria-hidden="true" data-skeleton={shape} className="st-skel">
        {Array.from({ length: bars }, (_, i) => (
          <span key={i} className="animate-pulse" />
        ))}
      </div>
    </div>
  );
}

export function EmptyState({
  title,
  body,
  action,
  art = true,
  variant = "page",
}: {
  title: string;
  body?: ReactNode;
  /** The first action, usually one primary button. */
  action?: ReactNode;
  /** The empty mascot pose. Decline it where the brand cast is wrong. */
  art?: boolean;
  variant?: Variant;
}) {
  return (
    <div className={`st st-${variant}`}>
      {art && (
        <span data-state-art aria-hidden="true">
          <BrainMascot mood="empty" size={64} />
        </span>
      )}
      <p className="st-title">{title}</p>
      {body && <p className="st-body">{body}</p>}
      {action && <div className="st-actions">{action}</div>}
    </div>
  );
}

export function ErrorState({
  title,
  body,
  detail,
  onRetry,
  variant = "page",
}: {
  /** What failed: "Couldn't open this book". */
  title: string;
  /** What is safe, and what to do next. */
  body?: ReactNode;
  /** The raw technical message, copied on request and never shown. */
  detail?: string | null;
  onRetry?: () => void;
  variant?: Variant;
}) {
  const [copy, setCopy] = useState<"idle" | "done" | "failed">("idle");
  const copyDetail = () => {
    Promise.resolve()
      .then(() => navigator.clipboard.writeText(detail ?? ""))
      .then(
        () => setCopy("done"),
        () => setCopy("failed"),
      );
  };
  return (
    <div role="alert" className={`st st-${variant}`}>
      <p className="st-title st-err">{title}</p>
      {body && <p className="st-body">{body}</p>}
      {(onRetry || detail) && (
        <div className="st-actions">
          {onRetry && (
            <LemonButton variant="primary" size="sm" onClick={onRetry}>
              Try again
            </LemonButton>
          )}
          {detail && (
            <LemonButton variant="tertiary" size="sm" onClick={copyDetail}>
              {copy === "done" ? "Copied" : copy === "failed" ? "Couldn't copy" : "Copy error details"}
            </LemonButton>
          )}
        </div>
      )}
    </div>
  );
}
