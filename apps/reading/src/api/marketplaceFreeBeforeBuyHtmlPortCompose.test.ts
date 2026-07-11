import { describe, expect, it } from "vitest";
import {
  composeMarketplaceFreeBeforeBuyHtmlPort,
  formatMarketplaceFreeBeforeBuyHtmlPortSummary,
} from "./marketplaceFreeBeforeBuyHtmlPortCompose";

describe("composeMarketplaceFreeBeforeBuyHtmlPort", () => {
  it("prefers free HTML port without purchase or host", () => {
    const c = composeMarketplaceFreeBeforeBuyHtmlPort({
      title: "Deep Learning",
      account_id: "acct-1",
      free_copy_available: true,
      free_html_projection_sha: "sha-free-1",
      purchase_ack: false,
      port_requested: true,
    });
    expect(c.path).toBe("prefer_free_html");
    expect(c.port_ready).toBe(true);
    expect(c.purchase_executed).toBe(false);
    expect(c.hosted).toBe(false);
    expect(c.pdf_view_authorized).toBe(false);
    expect(formatMarketplaceFreeBeforeBuyHtmlPortSummary(c)).toMatch(
      /purchase_executed=false/,
    );
  });

  it("blocks when free availability unknown", () => {
    const c = composeMarketplaceFreeBeforeBuyHtmlPort({
      title: "Book",
      account_id: "a",
      free_copy_available: null,
      purchase_ack: true,
      port_requested: true,
      purchase_html_projection_sha: "sha-p",
    });
    expect(c.path).toBe("blocked_unknown_free");
    expect(c.port_ready).toBe(false);
    expect(c.purchase_executed).toBe(false);
  });

  it("purchase path requires ack and sha for port_ready", () => {
    const noAck = composeMarketplaceFreeBeforeBuyHtmlPort({
      title: "Book",
      account_id: "a",
      free_copy_available: false,
      purchase_ack: false,
      port_requested: true,
      purchase_html_projection_sha: "sha-p",
    });
    expect(noAck.path).toBe("incomplete");
    expect(noAck.port_ready).toBe(false);

    const ready = composeMarketplaceFreeBeforeBuyHtmlPort({
      title: "Book",
      account_id: "a",
      free_copy_available: false,
      purchase_ack: true,
      port_requested: true,
      purchase_html_projection_sha: "sha-p",
    });
    expect(ready.path).toBe("purchase_then_port");
    expect(ready.port_ready).toBe(true);
    expect(ready.purchase_executed).toBe(false);
    expect(ready.hosted).toBe(false);
  });
});
