/**
 * agentTabDomId.ts — the DOM id of an agent tab's button in the companion
 * strip. Shared by CompanionPane (which renders it) and the agent pane's
 * close path (which returns focus to it); a tiny module so neither imports
 * the other at module level (SPR-07).
 */
export function agentTabDomId(tabId: string): string {
  return `agenttab-${tabId.replace(/[^A-Za-z0-9-]/g, (c) => `_${c.charCodeAt(0).toString(36)}_`)}`;
}
