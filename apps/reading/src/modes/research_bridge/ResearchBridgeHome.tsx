/**
 * ResearchBridgeHome — the "one product, two modes" shell.
 *
 * The spec's central design decision is that the bridge is ONE
 * product with two modes over a shared substrate, not two products.
 * This shell is where that decision becomes visible: Paste and
 * Gap-finder are tabs on the same surface, and a paste saved on the
 * Paste tab is immediately in scope on the Gap-finder tab (both read
 * the same /research/pastes).
 *
 * Mode A (outline writing) is intentionally NOT a tab here: it's
 * served by Antiek's existing deliverables/sections surface, and the
 * SPR-04 patch already routes paste-derived insights into
 * /blocks/search so they're draggable there. Adding a redundant
 * outline tab would be two surfaces for one job — the opposite of
 * hard-to-vary.
 */

import { useMemo, useState } from "react";
import { LemonButton } from "../../components/lemon";
import { GapFinderPage } from "./GapFinderPage";
import { PastePage } from "./PastePage";
import { createHttpClient } from "./api_client";
import type { ResearchBridgeClient } from "./api_client";

type Tab = "paste" | "gaps";

export interface ResearchBridgeHomeProps {
  /** Injectable for tests / stories. Production omits it and the
   *  shell builds the real HTTP client once. */
  client?: ResearchBridgeClient;
  initialTab?: Tab;
  initialSessionId?: string | null;
  className?: string;
}

export function ResearchBridgeHome({
  client: injectedClient,
  initialTab = "paste",
  initialSessionId = null,
  className,
}: ResearchBridgeHomeProps) {
  // Build the real client once if none injected. useMemo so the
  // child hooks' deps don't churn on every render.
  const client = useMemo(
    () => injectedClient ?? createHttpClient(),
    [injectedClient],
  );
  const [tab, setTab] = useState<Tab>(initialTab);

  const tabButton = (id: Tab, label: string) => (
    <LemonButton
      size="sm"
      variant={tab === id ? "primary" : "tertiary"}
      onClick={() => setTab(id)}
      aria-pressed={tab === id}
      aria-label={`Switch to ${label} tab`}
    >
      {label}
    </LemonButton>
  );

  return (
    <div className={["flex flex-col gap-3 h-full", className ?? ""].filter(Boolean).join(" ")}>
      <header className="flex items-center gap-3 border-b-2 border-ink dark:border-bright pb-2">
        <h1 className="text-lg font-bold text-ink dark:text-bright">Deep Research Bridge</h1>
        <nav className="flex gap-1" role="tablist" aria-label="Bridge modes">
          {tabButton("paste", "Paste")}
          {tabButton("gaps", "Gap-finder")}
        </nav>
      </header>

      <div className="flex-1 min-h-0">
        {tab === "paste" && (
          <PastePage
            client={client}
            initialSessionId={initialSessionId}
            onPasteSaved={() => { /* stays on paste; operator switches when ready */ }}
          />
        )}
        {tab === "gaps" && (
          <GapFinderPage client={client} initialSessionId={initialSessionId} />
        )}
      </div>
    </div>
  );
}
