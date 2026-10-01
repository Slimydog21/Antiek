/**
 * tabId.ts — the one place a new tab_id is minted (A2b item 1).
 *
 * A tab_id is an opaque key: `t` + base64url of 16 random bytes, 23
 * characters of [A-Za-z0-9_-], inside THREAD-CONTRACT §1.6's "1 to 64 of
 * [A-Za-z0-9_-]". It encodes nothing about the tab (no kind, ref or
 * parent), so nothing may read meaning out of it: a tab is found by its
 * fields (documentSpace.findOpenTab / findClosedTab), never by its id.
 *
 * Uniqueness rests on the randomness: 128 bits make a collision across
 * every tab a workstation will ever open negligible, including tabs retired
 * outside the 200 the client can see (the server treats a known tab_id as a
 * restore, so a reused id would be one). The same-tree check below, and the
 * model's `duplicate_tab_id` refusal, are guards, not the guarantee.
 */
import type { TabTree } from "./tabTree";

const BYTES = 16;

function base64url(bytes: Uint8Array): string {
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

function draw(): string {
  const bytes = new Uint8Array(BYTES);
  globalThis.crypto.getRandomValues(bytes);
  return `t${base64url(bytes)}`;
}

/** A fresh opaque tab_id. With `tree`, one no tab of it holds, open or
 *  retired (a guard: see the header). */
export function newTabId(tree?: TabTree): string {
  let id = draw();
  if (!tree) return id;
  while (Object.hasOwn(tree.nodes, id) || Object.hasOwn(tree.history, id)) id = draw();
  return id;
}
