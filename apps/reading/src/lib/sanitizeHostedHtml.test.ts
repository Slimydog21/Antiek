import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

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

  it("removes CSS and inert template containers", () => {
    const result = sanitizeHostedHtml(
      '<article><style>body{background:url(https://evil.example/x)}</style><template><img src="https://evil.example/t"></template><noscript>fallback</noscript><p>safe</p></article>',
    );
    expect(result).toBe(
      "<article><noscript>fallback</noscript><p>safe</p></article>",
    );
  });

  it.each([
    "javascript:alert(1)",
    "JAVASCRIPT:alert(1)",
    "java\tscript:alert(1)",
    "java\nscript:alert(1)",
    "vbscript:msgbox(1)",
    "data:text/html,<script>alert(1)</script>",
  ])("removes executable URL vector %s", (href) => {
    const result = sanitizeHostedHtml(`<a href="${href}">unsafe</a>`);
    expect(result).toBe("<a>unsafe</a>");
  });

  it("keeps every DOM HTML sink behind the shared sanitizer", () => {
    const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
    const rawSettingsDebt = "modes/Settings/index.tsx";
    let settingsDebtCount = 0;

    const visit = (directory: string): void => {
      for (const entry of readdirSync(directory, { withFileTypes: true })) {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) {
          visit(path);
          continue;
        }
        if (!entry.name.endsWith(".tsx")) continue;
        const source = readFileSync(path, "utf8");
        for (const match of source.matchAll(/dangerouslySetInnerHTML\s*=\s*\{\{/g)) {
          const sink = source.slice(match.index, match.index + 240);
          if (
            sink.includes("sanitizeHostedHtml(") ||
            sink.includes("__html: sanitizedHtml")
          )
            continue;
          const sourcePath = relative(srcRoot, path);
          if (sourcePath === rawSettingsDebt) {
            settingsDebtCount += 1;
            continue;
          }
          throw new Error(`raw DOM HTML sink outside sanitizer: ${sourcePath}`);
        }
      }
    };

    visit(srcRoot);
    expect(settingsDebtCount).toBe(6);
  });
});
