/**
 * AgentDeepLink.tsx — the `#pane=agent:<agentId>` deep link's ONE consumer
 * (SPR-07 M5; repair C12). Mounted lazily by PanelLayout only when the
 * location's hash names a pane at first render, it opens that pane ONCE, on
 * mount: `p:<projectId>` is that project's pane, `x:<n>` a cross-project
 * one. Open-state is never persisted (paneHash.ts): a reload with the pane
 * open comes back closed unless this link is in the URL, and PaneHashSync
 * keeps the hash mirroring the active pane from then on. Later hash writes
 * are PaneHashSync's own and never re-open anything (mount-only on purpose:
 * a strip click that activates a pane must not have its focus stolen by a
 * second open).
 */
import { useEffect, useRef } from "react";
import { useLocation } from "react-router-dom";

import { openAgentPaneFromAgentId } from "./openAgentPane";
import { parsePaneHash } from "./paneHash";

export default function AgentDeepLink(): null {
  const { hash } = useLocation();
  const done = useRef(false);
  useEffect(() => {
    if (done.current) return;
    done.current = true;
    const parsed = parsePaneHash(hash);
    if (parsed) openAgentPaneFromAgentId(parsed.agentId);
    // Mount-only by design (see the header); `hash` is read once.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}
