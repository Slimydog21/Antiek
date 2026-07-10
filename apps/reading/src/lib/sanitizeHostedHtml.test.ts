import { describe, expect, it } from "vitest";

import { sanitizeHostedHtml } from "./sanitizeHostedHtml";

describe("sanitizeHostedHtml", () => {
  it("preserves document structure while removing active content", () => {
    const result = sanitizeHostedHtml(
      '<article><h1>Aircraft</h1><img src="x" onerror="alert(1)"><script>alert(2)</script></article>',
    );
    expect(result).toContain("<article><h1>Aircraft</h1><img src=\"x\"></article>");
    expect(result).not.toContain("onerror");
    expect(result).not.toContain("script");
  });

  it("removes executable URLs, embedded documents, forms, and inline styles", () => {
    const result = sanitizeHostedHtml(
      '<a href="javascript:alert(1)" style="background:url(javascript:x)">bad</a><iframe srcdoc="x"></iframe><form><input></form>',
    );
    expect(result).toBe("<a>bad</a>");
  });

  it("keeps safe links isolated from the application opener", () => {
    const result = sanitizeHostedHtml('<a href="https://example.com/paper">paper</a>');
    expect(result).toContain('href="https://example.com/paper"');
    expect(result).toContain('rel="noopener noreferrer"');
  });
});
