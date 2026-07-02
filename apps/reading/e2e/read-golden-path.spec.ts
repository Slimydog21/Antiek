/**
 * read-golden-path.spec.ts -- activation SPR-05 proxy on the real Reader route.
 *
 * This is deliberately not a Storybook iframe test. It loads the shipped SPA at
 * /read/:documentId through RequireAuth (using the same test-side auth mock as
 * the AMS real-app gates), stubs only the backend book/chunk responses, and
 * asserts the real BookReader host:
 *
 *   1. rich typed blocks render at /read/doc-1;
 *   2. selecting text opens the shared FloatMenu;
 *   5. clicking a citation opens the source through the canonical Reader URL;
 *   6. the source page can return to the original document/page.
 *
 * Steps 3-4 remain provider-key activation work. Step 7 remains operator
 * dogfood, enforced by tools/activation/read_dogfood.py.
 */
import { expect, test, type Page, type Route } from "@playwright/test";

import { loginAndGotoApp } from "./_ams/auth";

const ORIGINAL_DOC_ID = "doc-1";
const SOURCE_DOC_ID = "doc-source-42";
const SOURCE_CHUNK_ID = "chunk-7";

async function json(route: Route, status: number, body: unknown): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    headers: { "access-control-allow-origin": "*" },
    body: JSON.stringify(body),
  });
}

function bookDetail(documentId: string, title: string) {
  return {
    document_id: documentId,
    title,
    author: "Activation Fixture",
    servability: "public_domain",
    servable_full_text: true,
    page_count: 1,
    cover_uri: null,
    ip_holder_id: null,
    taken_down: false,
    pagination_scheme: "structured-blocks",
    provenance: "read-golden-path-e2e",
    license_basis: "public_domain",
    toc: [{ title: "Chapter One", page_index: 0, level: 1 }],
  };
}

function originalDocumentJson(): string {
  return JSON.stringify({
    id: ORIGINAL_DOC_ID,
    title: "A Servable Book",
    schema_version: 1,
    blocks: [
      { type: "heading", level: 1, spans: [{ type: "text", text: "Chapter One" }] },
      {
        type: "paragraph",
        spans: [
          { type: "text", text: "A cited claim with enough text for selection " },
          {
            type: "citation",
            source_document_id: SOURCE_DOC_ID,
            chunk_id: SOURCE_CHUNK_ID,
            marker: "[1]",
          },
          { type: "text", text: "." },
        ],
      },
    ],
  });
}

function sourceDocumentJson(): string {
  return JSON.stringify({
    id: SOURCE_DOC_ID,
    title: "Source Work",
    schema_version: 1,
    blocks: [
      { type: "heading", level: 1, spans: [{ type: "text", text: "Source Work" }] },
      {
        type: "paragraph",
        spans: [{ type: "text", text: "The cited source body is visible." }],
      },
    ],
  });
}

function fullText(documentId: string, title: string, structuredBlocks: string) {
  return {
    document_id: documentId,
    servable: true,
    servability: "public_domain",
    full_text: title === "A Servable Book"
      ? "Chapter One\n\nA cited claim with enough text for selection [1]."
      : "Source Work\n\nThe cited source body is visible.",
    snippet: null,
    structured_blocks: structuredBlocks,
    representative_chunk_id: documentId === ORIGINAL_DOC_ID ? "doc-1-representative" : SOURCE_CHUNK_ID,
    title,
    author: "Activation Fixture",
    reason: "servable",
    tier: null,
    ad_eligible: false,
    canonical_url: null,
    license: null,
  };
}

async function installReaderStubs(page: Page): Promise<void> {
  await page.route(/\/books\?status=servable/, (route) =>
    json(route, 200, {
      count: 1,
      books: [bookDetail("house-doc", "House Recommendation")],
    }),
  );
  await page.route(/\/books\/doc-1\/full-text$/, (route) =>
    json(route, 200, fullText(ORIGINAL_DOC_ID, "A Servable Book", originalDocumentJson())),
  );
  await page.route(/\/books\/doc-source-42\/full-text$/, (route) =>
    json(route, 200, fullText(SOURCE_DOC_ID, "Source Work", sourceDocumentJson())),
  );
  await page.route(/\/books\/doc-1$/, (route) =>
    json(route, 200, bookDetail(ORIGINAL_DOC_ID, "A Servable Book")),
  );
  await page.route(/\/books\/doc-source-42$/, (route) =>
    json(route, 200, bookDetail(SOURCE_DOC_ID, "Source Work")),
  );
  await page.route(/\/chunks\/chunk-7$/, (route) =>
    json(route, 200, {
      chunk_id: SOURCE_CHUNK_ID,
      text: "The cited source body is visible.",
      section_path: "Page 1",
      token_count: 7,
      document_id: SOURCE_DOC_ID,
      document_title: "Source Work",
      source_tier: 1,
      servable: true,
      ip_holder_name: null,
      ip_holder_status: null,
      servability: "public_domain",
    }),
  );
  await page.route(/\/books\/[^/]+\/ad-impressions$/, (route) =>
    json(route, 200, {}),
  );
  await page.route(/\/trajectory\/read-/, (route) =>
    json(route, 200, { investigation_id: "read-e2e", count: 0, events: [] }),
  );
}

async function selectTextInsideReader(page: Page, needle: string): Promise<void> {
  const selected = await page.evaluate((wanted) => {
    const root = document.querySelector("[data-reader-root]");
    if (!root) return false;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const text = node.textContent ?? "";
      const start = text.indexOf(wanted);
      if (start !== -1) {
        const range = document.createRange();
        range.setStart(node, start);
        range.setEnd(node, start + wanted.length);
        const selection = window.getSelection();
        selection?.removeAllRanges();
        selection?.addRange(range);
        document.dispatchEvent(new Event("selectionchange"));
        return true;
      }
      node = walker.nextNode();
    }
    return false;
  }, needle);
  expect(selected).toBe(true);
}

test.describe("Read activation golden path on the real app route", () => {
  test("opens rich Reader, selects text, traces citation, and returns", async ({ page }) => {
    await installReaderStubs(page);
    await loginAndGotoApp(page, `/read/${ORIGINAL_DOC_ID}`, { settleMs: 200 });

    await expect(page.locator("[data-reader-root]")).toBeVisible();
    await expect(page.getByRole("heading", { name: "Chapter One" })).toBeVisible();
    await expect(page.getByText("A cited claim with enough text for selection")).toBeVisible();

    await selectTextInsideReader(page, "cited claim with enough text");
    await expect(page.getByRole("menu", { name: "Highlight actions" })).toBeVisible();
    await expect(page.getByRole("menuitem", { name: "Dialogue" })).toBeVisible();
    await page.keyboard.press("Escape");

    await page.getByRole("button", { name: "Open the cited source [1]" }).click();
    await expect(page).toHaveURL(
      /\/read\/doc-source-42\?chunk=chunk-7&from=doc-1&fromPage=0&fromTitle=A\+Servable\+Book$/,
    );
    await expect(
      page.getByRole("article").getByRole("heading", { name: "Source Work" }),
    ).toBeVisible();
    await expect(page.getByText("The cited source body is visible.")).toBeVisible();

    await page.getByRole("button", { name: /Return to A Servable Book/ }).click();
    await expect(page).toHaveURL(/\/read\/doc-1\?page=0$/);
    await expect(page.getByRole("heading", { name: "Chapter One" })).toBeVisible();
  });
});
