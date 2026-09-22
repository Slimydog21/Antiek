import { expect, test, type Page } from "@playwright/test";

/**
 * account-memory-panel.spec.ts — SPR-11 Task 6's proof, against a REAL backend.
 *
 * The `memory-real` project boots an actual uvicorn (`--workers 1`) over an
 * actual throwaway DuckDB graph and an actual Vite dev server proxying to it.
 * Nothing here is mocked: there is no `page.route`, no stubbed response, no
 * fixture module. That is deliberate and it is the whole point of the task's
 * done-bar — a mocked component test would prove the panel can render a shape
 * the developer invented, which is precisely the failure this spec exists to
 * rule out. What it proves instead is that the panel speaks the contract the
 * deployed routes actually answer with: `AccountMemoryListResponse` from GET,
 * `AccountMemoryWriteResponse` from POST, the session cookie carried by the
 * app's own authenticated fetch wrapper, and the substrate's real bi-temporal
 * supersession semantics on a correction.
 *
 * Every write goes through the browser's own session, so the owner the rows are
 * written under is the same derived owner the panel reads back — the
 * `__operator__` sentinel is refused by `distinct_signed_owner`, and this suite
 * would 401 rather than pass if the e-mail fallback ever stopped resolving.
 */

const DEV_LOGIN_TOKEN = "playwright-memory-bootstrap";
const API_BASE = "http://localhost:8011";

/** A key unique to this run, so a re-run never collides with a stale row. */
function uniqueSubject(): string {
  return `e2e:reader:${Date.now()}:${Math.floor(Math.random() * 1e6)}`;
}

/** Sign in for real and land on the panel. */
async function signInAndOpenPanel(page: Page): Promise<void> {
  await page.goto(
    `${API_BASE}/auth/dev-login?token=${DEV_LOGIN_TOKEN}&next=${encodeURIComponent("/memory")}`,
  );
  await expect(page).toHaveURL(/\/memory$/);
  await expect(page.getByTestId("memory-panel")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Account memory" })).toBeVisible();
}

/** Write one memory through the page's own session cookie, via the same
 *  same-origin proxy the panel uses. This is the seed, not a stub. */
async function seedMemory(
  page: Page,
  body: {
    subject: string;
    predicate: string;
    object: string;
    provenance: Record<string, unknown>;
    valid_from: string;
  },
): Promise<{ action: string; item: { memory_id: string; edge_id: string } }> {
  const result = await page.evaluate(async (payload) => {
    const response = await fetch("/account/memory", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return { status: response.status, body: await response.json() };
  }, body);
  expect(result.status, `seed POST failed: ${JSON.stringify(result.body)}`).toBe(200);
  return result.body;
}

/** Read the live list straight from the API, to check the panel against the
 *  substrate rather than against itself. */
async function listMemoryFromApi(
  page: Page,
): Promise<Array<{ subject: string; predicate: string; object: string }>> {
  const result = await page.evaluate(async () => {
    const response = await fetch("/account/memory?limit=50", { credentials: "include" });
    return { status: response.status, body: await response.json() };
  });
  expect(result.status).toBe(200);
  return result.body.items;
}

/** The group card for one fact, located by the (subject, predicate) pair the
 *  panel stamps on it. */
function rowFor(page: Page, subject: string, predicate: string) {
  return page.locator(
    `[data-testid="memory-row"][data-memory-subject="${subject}"][data-memory-predicate="${predicate}"]`,
  );
}

test.describe("account memory panel (real backend)", () => {
  test("renders a seeded memory with its provenance, then corrects it and keeps the superseded original", async ({
    page,
  }) => {
    const subject = uniqueSubject();
    const predicate = "prefers_citation_style";
    const original = "numbered footnotes";
    const corrected = "inline author-date";
    const provenanceSource = "e2e_account_memory_seed";

    await signInAndOpenPanel(page);

    // ── seed one memory through a real POST ─────────────────────────────────
    const seeded = await seedMemory(page, {
      subject,
      predicate,
      object: original,
      provenance: { source: provenanceSource, seeded_by: "playwright" },
      // Comfortably in the past: a correction's valid_from must be strictly
      // later than the version it replaces (substrate/memory/store.py).
      valid_from: "2026-09-01T10:00:00Z",
    });
    expect(seeded.action).toBe("ADD");

    await page.getByTestId("memory-reload").click();

    // ── the row renders, with provenance visible ────────────────────────────
    const row = rowFor(page, subject, predicate);
    await expect(row).toBeVisible();
    await expect(row.getByTestId("memory-subject")).toHaveText(subject);
    await expect(row.getByTestId("memory-predicate")).toHaveText(predicate);
    await expect(row.getByTestId("memory-object")).toHaveText(original);
    await expect(row.getByTestId("memory-valid-from")).toHaveText("2026-09-01 10:00:00Z");

    const provenanceText = row.getByTestId("memory-provenance");
    // The provenance the client sent, AND the `authority` the server stamps on
    // every write. Seeing the server's own field proves this text came from the
    // response body rather than from anything the page already knew.
    await expect(provenanceText).toContainText(`source=${provenanceSource}`);
    await expect(provenanceText).toContainText("seeded_by=playwright");
    await expect(provenanceText).toContainText("authority=antiek_session_cookie");

    // Nothing has been corrected yet, so there is no history to collapse.
    await expect(row.getByTestId("memory-history")).toHaveCount(0);

    // ── correct the fact, through the panel's single POST ───────────────────
    await row.getByTestId("memory-correct-button").click();
    const input = row.getByTestId("memory-correct-input");
    await expect(input).toHaveValue(original);
    await input.fill(corrected);
    await row.getByTestId("memory-correct-note").fill("operator changed house style");

    const writeResponse = page.waitForResponse(
      (response) =>
        response.url().includes("/account/memory") && response.request().method() === "POST",
    );
    await row.getByTestId("memory-correct-submit").click();
    const written = await writeResponse;
    expect(written.status()).toBe(200);
    // The substrate's reconciler classified this as a supersession, not an add.
    expect((await written.json()).action).toBe("SUPERSEDE");

    // ── the head is the corrected value ─────────────────────────────────────
    await expect(row.getByTestId("memory-object")).toHaveText(corrected);
    await expect(page.getByTestId("memory-notice")).toContainText("previous value is kept");

    // ── and the superseded original is still reachable, collapsed ───────────
    const history = row.getByTestId("memory-history");
    await expect(history).toBeVisible();
    const summary = history.getByTestId("memory-history-summary");
    await expect(summary).toHaveText("1 earlier version");

    // Collapsed, not hidden: expanding the disclosure is how the owner reaches
    // the version their correction replaced.
    await summary.click();
    const olderItem = history.getByTestId("memory-history-item");
    await expect(olderItem).toHaveCount(1);
    await expect(olderItem).toBeVisible();
    // `data-memory-edge-id` must be the edge the SEED created — proof the panel
    // retained the actual superseded row and did not invent a placeholder.
    await expect(olderItem).toHaveAttribute("data-memory-edge-id", seeded.item.edge_id);
    await expect(olderItem.getByTestId("memory-history-object")).toHaveText(original);
    await expect(olderItem.getByTestId("memory-history-provenance")).toContainText(
      `source=${provenanceSource}`,
    );

    // ── the substrate agrees: one current head, and it is the correction ────
    const live = await listMemoryFromApi(page);
    const forKey = live.filter((item) => item.subject === subject && item.predicate === predicate);
    expect(forKey).toHaveLength(1);
    expect(forKey[0].object).toBe(corrected);
  });

  test("shows every current fact the memory route returns, newest valid_from first", async ({
    page,
  }) => {
    const subject = uniqueSubject();
    await signInAndOpenPanel(page);

    await seedMemory(page, {
      subject,
      predicate: "reads_at",
      object: "night",
      provenance: { source: "e2e_account_memory_seed" },
      valid_from: "2026-09-02T08:00:00Z",
    });
    await seedMemory(page, {
      subject,
      predicate: "writes_in",
      object: "long form",
      provenance: { source: "e2e_account_memory_seed" },
      valid_from: "2026-09-03T08:00:00Z",
    });

    await page.getByTestId("memory-reload").click();

    await expect(rowFor(page, subject, "reads_at").getByTestId("memory-object")).toHaveText("night");
    await expect(rowFor(page, subject, "writes_in").getByTestId("memory-object")).toHaveText(
      "long form",
    );

    // Two distinct predicates on one subject are two facts, not two versions of
    // one — the collapse groups by (subject, predicate), never by subject alone.
    await expect(rowFor(page, subject, "reads_at").getByTestId("memory-history")).toHaveCount(0);
    await expect(rowFor(page, subject, "writes_in").getByTestId("memory-history")).toHaveCount(0);

    // Newest valid_from first: writes_in (09-03) must precede reads_at (09-02).
    const orderedKeys = await page
      .locator('[data-testid="memory-row"]')
      .evaluateAll((nodes) =>
        nodes.map((node) => {
          const el = node as HTMLElement;
          return `${el.dataset.memorySubject ?? ""}::${el.dataset.memoryPredicate ?? ""}`;
        }),
      );
    const readsAtIndex = orderedKeys.indexOf(`${subject}::reads_at`);
    const writesInIndex = orderedKeys.indexOf(`${subject}::writes_in`);
    expect(writesInIndex).toBeGreaterThanOrEqual(0);
    expect(writesInIndex).toBeLessThan(readsAtIndex);
  });
});
