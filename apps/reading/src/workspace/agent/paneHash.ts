/**
 * paneHash.ts — the `#pane=agent:<id>` deep link (SPR-07 M5; posthog
 * carry-overs 1–2). The hash mirrors the ACTIVE agent pane via
 * history.replace (react-router's navigate with replace; never
 * history.push, so Back is never a pane toggle); on close it is replaced
 * with "". Open-state is never persisted: a reload with the pane open
 * comes back closed with the same tab selected; the deep link is the only
 * way the pane opens on load (AgentDeepLink.tsx, mounted by PanelLayout
 * when the first render's hash names a pane; repair C12).
 */
import { useEffect } from "react";
import { useInRouterContext, useNavigate } from "react-router-dom";

const PREFIX = "pane=agent:";

export function parsePaneHash(hash: string): { agentId: string } | null {
  const h = hash.startsWith("#") ? hash.slice(1) : hash;
  if (!h.startsWith(PREFIX)) return null;
  const agentId = decodeURIComponent(h.slice(PREFIX.length));
  return agentId ? { agentId } : null;
}

export function formatPaneHash(agentId: string): string {
  return `#${PREFIX}${encodeURIComponent(agentId).replace(/%3A/gi, ":")}`;
}

/** Mirrors the active pane into the hash while mounted; replaces it with
 *  "" on unmount. Render it only inside a router (AgentPane checks
 *  useInRouterContext: the pane also mounts in router-free hosts). */
export function PaneHashSync({ agentId, active }: { agentId: string; active: boolean }): null {
  const navigate = useNavigate();
  useEffect(() => {
    if (!active) return;
    const wanted = formatPaneHash(agentId);
    if (window.location.hash !== wanted) navigate({ hash: wanted }, { replace: true });
    return () => {
      if (parsePaneHash(window.location.hash)?.agentId === agentId) navigate({ hash: "" }, { replace: true });
    };
  }, [agentId, active, navigate]);
  return null;
}

export { useInRouterContext };
