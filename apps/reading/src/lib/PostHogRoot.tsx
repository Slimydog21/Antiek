import { PostHogProvider } from "@posthog/react";
import type { ReactNode } from "react";

import { posthog, posthogEnabled } from "./posthogClient";

/** Wraps the app when analytics is configured; no-op otherwise (CI, local without keys). */
export function PostHogRoot({ children }: { children: ReactNode }) {
  if (!posthogEnabled) {
    return <>{children}</>;
  }
  return <PostHogProvider client={posthog}>{children}</PostHogProvider>;
}