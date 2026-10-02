import type { ReactNode } from "react";

/**
 * ErrorBanner — the one shared error callout (ui-audit Q4/S3), replacing the
 * copy-pasted `border-red-200 bg-red-50` strips that were duplicated across
 * 12+ modes with no dark variant.
 *
 * Recipe from Login.css:54 (the audit's named token-correct treatment): a
 * 3px emperor left bar over a 10% emperor veil, emperor text. Painted with
 * the `danger` alias — danger IS emperor (tokens.ts `danger` ==
 * accent.emperor) and flips day `#CE3623` / night `#FF6155` via the
 * `--danger-rgb` channels, so the callout is night-correct by construction,
 * no `dark:` overrides needed.
 *
 * Not for AI-action failures: those stay on `shared/AIActionFailure.tsx`,
 * which is deliberately un-dressed (one sentence, framed diagnostic, in-place
 * retry). Do not route AI-failure sites through this banner.
 *
 * `role="alert"` is the default because a banner that appears when a load or
 * mutation fails is a genuine alert; pass `role="status"` for quiet,
 * non-urgent contexts.
 */
type Props = {
  children: ReactNode;
  role?: "alert" | "status";
  className?: string;
};

export function ErrorBanner({ children, role = "alert", className = "" }: Props) {
  return (
    <div
      role={role}
      className={
        "rounded border-l-[3px] border-danger bg-danger/10 " +
        "px-3 py-2 text-sm text-danger " +
        className
      }
    >
      {children}
    </div>
  );
}

export default ErrorBanner;
