import { describe, expect, it } from "vitest";
import {
  composeHtmlNativeViewSessionAuthority,
  formatHtmlNativeViewSessionAuthoritySummary,
} from "./htmlNativeViewSessionAuthorityCompose";

describe("composeHtmlNativeViewSessionAuthority", () => {
  it("HTML ready pack across session + parity", () => {
    const c = composeHtmlNativeViewSessionAuthority({
      session_id: "sess-1",
      asset_id: "asset-1",
      html_projection_sha: "sha-html-ready",
      view_requested: true,
      twin_bound: true,
      twin_substrate_ready: true,
      claimed_format: "html",
      operator_ack: true,
    });
    expect(c.session.session_ready).toBe(true);
    expect(c.authority.human_viewable_html).toBe(true);
    expect(c.parity.both_html_ready).toBe(true);
    expect(c.pack_ready).toBe(true);
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.pdf_primary).toBe(false);
    expect(c.store_mutated).toBe(false);
    expect(c.pack_authority).toBe(
      "html_native_view_session_authority_compose_advisory",
    );
    expect(formatHtmlNativeViewSessionAuthoritySummary(c)).toMatch(
      /pdf_primary=false/,
    );
  });

  it("pdf claim blocks session package", () => {
    const c = composeHtmlNativeViewSessionAuthority({
      session_id: "sess-2",
      asset_id: "asset-2",
      html_projection_sha: "sha-html",
      view_requested: true,
      twin_bound: false,
      claimed_format: "pdf",
      operator_ack: true,
    });
    // session may block on claimed pdf; authority still prefers html sha
    expect(c.pdf_view_authorized).toBe(false);
    expect(c.pdf_primary).toBe(false);
    expect(c.store_mutated).toBe(false);
  });

  it("missing sha blocks pack_ready", () => {
    const c = composeHtmlNativeViewSessionAuthority({
      session_id: "sess-3",
      asset_id: "a",
      html_projection_sha: null,
      view_requested: true,
      twin_bound: true,
      operator_ack: true,
    });
    expect(c.authority.human_viewable_html).toBe(false);
    expect(c.pack_ready).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
  });

  it("operator_ack false blocks pack_ready", () => {
    const c = composeHtmlNativeViewSessionAuthority({
      session_id: "sess-4",
      asset_id: "a",
      html_projection_sha: "sha",
      view_requested: true,
      twin_bound: true,
      operator_ack: false,
    });
    expect(c.session.session_ready).toBe(true);
    expect(c.pack_ready).toBe(false);
  });
});
