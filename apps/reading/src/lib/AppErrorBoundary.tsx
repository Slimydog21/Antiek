/**
 * AppErrorBoundary — the root safety net (FFX SPR-01 M1, closes F-01 / A-02).
 *
 * Before this existed, main.tsx rendered StrictMode → PostHogRoot →
 * BrowserRouter → <App/> with no boundary anywhere above ~50 lazy routes, so
 * one render throw (or a rejected lazy import after a deploy swapped the
 * hashed chunks) unmounted the whole root: 0 interactive elements, focus on
 * <body>. This boundary guarantees a floor instead: one sentence and two
 * actions that work even when the thing that threw is the router.
 *
 * Deliberate constraints (a reviewer should be able to rebuild each):
 *   - The fallback is plain Tailwind markup. No components/lemon/* import:
 *     this module is in the entry chunk, and the lemon manual chunk has
 *     ~7.5 KB of budget headroom — the fallback must not pull it in.
 *   - "Go to Home" is a raw <a href="/home">, not <Link>. A <Link> needs a
 *     live router; the router may be exactly what threw. A full-document
 *     navigation also discards whatever corrupted in-memory state caused the
 *     crash.
 *   - The fallback reads nothing from the router. Only the thin outer
 *     wrapper reads the pathname, and only to RESET the boundary (it is
 *     passed as a prop, never as a React `key` — a key would remount the
 *     entire app on every navigation).
 *
 * What a root boundary costs (steelman of per-route `errorElement`): when a
 * mode throws, the NavRail and Topbar die with it, because they live inside
 * the same tree. Scoped boundaries around each lazy route in App.tsx would
 * keep the shell alive and let the user move to another workflow in-app.
 * App.tsx is lane A's; when lane A adds scoped boundaries they nest INSIDE
 * this one and this one simply stops firing for mode errors — nothing here
 * needs undoing.
 *
 * It is a safety net, not a fix: the reader crash (A-01) still throws until
 * SPR-02 lands; this only turns its blank page into a recoverable one.
 */
import { Component } from "react";
import type { ErrorInfo, ReactNode } from "react";
import { useLocation } from "react-router-dom";

import { getChunkLoadFailure, isChunkLoadError } from "./chunkLoadRecovery";

/** The pathname for logging, read from the document — never from the router,
 *  which may be the thing that threw. Never throws itself. */
function documentPathname(): string {
  try {
    return window.location?.pathname || "(unknown)";
  } catch {
    return "(unknown)";
  }
}

function reloadPage(): void {
  try {
    window.location.reload();
  } catch {
    // A sandboxed frame can refuse reload; the Home anchor still works.
  }
}

interface BoundaryProps {
  children: ReactNode;
  /** Changing this clears a caught error (the router's pathname). */
  resetKey: string;
}

interface BoundaryState {
  error: unknown;
  hasError: boolean;
}

export const APP_ERROR_COPY = "Something broke on this page.";
export const STALE_DEPLOY_COPY = "A new version of Antiek was deployed. Reload to continue.";

class RootErrorBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { error: null, hasError: false };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { error, hasError: true };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error(
      `[antiek] app error boundary caught an error on ${documentPathname()}`,
      error,
      info?.componentStack ?? "",
    );
  }

  componentDidUpdate(prev: BoundaryProps): void {
    if (this.state.hasError && prev.resetKey !== this.props.resetKey) {
      this.setState({ error: null, hasError: false });
    }
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    // The fallback must not be able to throw past itself (critic F-03b):
    // anything the stale-deploy check throws degrades to the generic copy.
    let staleDeploy = false;
    try {
      staleDeploy = isChunkLoadError(this.state.error) || getChunkLoadFailure() !== null;
    } catch {
      staleDeploy = false;
    }
    return (
      <main
        role="alert"
        className="min-h-screen flex items-center justify-center p-8 bg-ice-2 dark:bg-space-2 text-ink dark:text-bright font-sans"
      >
        <div className="max-w-md text-center">
          <p className="text-lg font-semibold mb-6">{staleDeploy ? STALE_DEPLOY_COPY : APP_ERROR_COPY}</p>
          <div className="flex items-center justify-center gap-3">
            <button
              type="button"
              onClick={reloadPage}
              className="rounded-md px-4 py-2 text-sm font-semibold bg-sun text-ink hover:bg-sun-hover focus:outline-none focus-visible:ring-2 focus-visible:ring-ink dark:focus-visible:ring-bright focus-visible:ring-offset-2"
            >
              Reload
            </button>
            <a
              href="/home"
              className="rounded-md px-4 py-2 text-sm font-semibold underline underline-offset-2 focus:outline-none focus-visible:ring-2 focus-visible:ring-ink dark:focus-visible:ring-bright focus-visible:ring-offset-2"
            >
              Go to Home
            </a>
          </div>
        </div>
      </main>
    );
  }
}

/**
 * The reset key, read so that it can never throw. This wrapper runs OUTSIDE
 * the class boundary, so anything that throws here would unmount the root
 * with no recovery UI — the exact failure the boundary exists to prevent
 * (MiMo critic F-03: a throwing pathname getter did that). A missing router
 * context, a null location or a hostile getter all degrade to a constant
 * key: the boundary still catches and renders its fallback; it just cannot
 * auto-reset on navigation in that (already broken) state.
 */
function useResetKey(): string {
  try {
    // useLocation is a context read: calling it inside try keeps the hook
    // order unconditional while containing react-router's invariant throw.
    const location = useLocation() as { pathname?: unknown } | null | undefined;
    const pathname = location?.pathname;
    return typeof pathname === "string" ? pathname : "(no-pathname)";
  } catch {
    return "(no-router)";
  }
}

/**
 * Mount inside BrowserRouter, around the whole app tree. Resets on pathname
 * change so a crash on /read/x does not persist after back/forward to /home.
 */
export function AppErrorBoundary({ children }: { children: ReactNode }) {
  const resetKey = useResetKey();
  return <RootErrorBoundary resetKey={resetKey}>{children}</RootErrorBoundary>;
}

export default AppErrorBoundary;
